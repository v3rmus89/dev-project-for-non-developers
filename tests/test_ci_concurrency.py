"""CI-minutes guards for the shipped ci.yml templates.

Two classes of Actions-billing waste this locks down:

1. Missing `concurrency` — a push-push-push burst on one branch bills every
   in-flight run instead of superseding the older ones.
2. An unfiltered `on: push` — that fires on EVERY branch, so a PR branch is
   billed twice per push (once for `push`, once for `pull_request`).

The concurrency block is byte-identical across all three languages on purpose;
`test_concurrency_block_identical_across_languages` fails if one drifts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from bootstrap_lib import render

SKILL_ROOT = Path(__file__).resolve().parent.parent

# (language, extra render context) — python renders twice, once per package manager,
# because the pip/uv branch straddles the block we care about.
CASES = [
    ("python", {"python_version": "3.12", "package_manager": "pip"}),
    ("python", {"python_version": "3.12", "package_manager": "uv"}),
    ("nodejs", {"node_version": "24"}),
    ("go", {"go_version": "1.26"}),
]

EXPECTED_GROUP = "${{ github.workflow_ref }}"
EXPECTED_CANCEL = "${{ github.ref != 'refs/heads/main' }}"

# PyYAML is a YAML 1.1 parser, which folds the bare key `on` to the boolean True.
# GitHub's own parser is 1.2 and reads it as the string "on". Look up the trigger
# block defensively so this test does not depend on which side of that quirk we
# are on.
_ON_KEYS = (True, "on")


def _render(lang: str, ctx: dict) -> str:
    return render.build_env(lang).get_template("ci.yml.tmpl").render(**ctx)


def _triggers(data: dict) -> dict:
    for key in _ON_KEYS:
        if key in data:
            return data[key]
    raise AssertionError(f"no trigger block found; keys={list(data)}")


@pytest.mark.parametrize("lang, ctx", CASES, ids=lambda v: v if isinstance(v, str) else "")
def test_ci_yml_has_concurrency_group(lang, ctx):
    """Every shipped CI template supersedes its own in-flight runs."""
    data = yaml.safe_load(_render(lang, ctx))
    concurrency = data.get("concurrency")
    assert concurrency is not None, f"{lang}: ci.yml.tmpl lost its concurrency block"
    # Keyed on workflow_ref, not workflow: groups are repository-global rather
    # than per-file, and `github.workflow` is only the display name — two
    # workflows both named `CI` would share a group and cancel each other.
    # workflow_ref is the file path + ref, so it is unique without a ref suffix.
    assert concurrency["group"] == EXPECTED_GROUP
    assert concurrency["cancel-in-progress"] == EXPECTED_CANCEL


@pytest.mark.parametrize("lang, ctx", CASES, ids=lambda v: v if isinstance(v, str) else "")
def test_ci_yml_does_not_cancel_in_progress_on_main(lang, ctx):
    """cancel-in-progress must stay conditional, never a bare `true`.

    A generated project may gate a deploy (Railway/Vercel), a release job, or a
    required status check on the main-branch run; cancelling that would strand a
    merge undeployed. Downgrading to `true` has to be a deliberate local edit.
    """
    data = yaml.safe_load(_render(lang, ctx))
    cancel = data["concurrency"]["cancel-in-progress"]
    assert cancel is not True, f"{lang}: cancel-in-progress is an unconditional true"
    assert "refs/heads/main" in str(cancel)


@pytest.mark.parametrize("lang, ctx", CASES, ids=lambda v: v if isinstance(v, str) else "")
def test_ci_yml_push_is_branch_filtered(lang, ctx):
    """`on: push` must stay scoped to main, or PR branches get billed twice."""
    triggers = _triggers(yaml.safe_load(_render(lang, ctx)))
    assert "push" in triggers, f"{lang}: push trigger disappeared"
    push = triggers["push"]
    assert isinstance(push, dict) and push.get("branches") == ["main"], (
        f"{lang}: `on: push` is not filtered to [main] (got {push!r}) — an "
        "unfiltered push trigger double-bills every PR-branch commit"
    )


def test_concurrency_block_identical_across_languages():
    """The block is duplicated across three templates; catch drift in one."""
    blocks = {}
    for lang in ("python", "nodejs", "go"):
        text = (SKILL_ROOT / "languages" / lang / "ci.yml.tmpl").read_text()
        match = re.search(r"^concurrency:\n(?:[ \t]+.*\n)+", text, re.MULTILINE)
        assert match, f"{lang}: no concurrency block in ci.yml.tmpl"
        blocks[lang] = match.group(0)
    distinct = set(blocks.values())
    assert len(distinct) == 1, f"concurrency block drifted across languages: {blocks}"


@pytest.mark.parametrize("lang, ctx", CASES, ids=lambda v: v if isinstance(v, str) else "")
def test_ci_yml_raw_guards_survive_jinja(lang, ctx):
    """`${{ ... }}` must reach the output intact.

    The GitHub expression syntax embeds Jinja's own `{{ }}` delimiters, so the
    block needs `{% raw %}` guards. Without them Jinja silently eats the
    expression and emits `$-` / `$`, which GitHub then treats as a literal
    group name — every branch shares one group and pushes cancel each other
    across branches.
    """
    rendered = _render(lang, ctx)
    assert EXPECTED_GROUP in rendered, f"{lang}: group expression was mangled by Jinja"
    assert EXPECTED_CANCEL in rendered, f"{lang}: cancel expression was mangled by Jinja"
