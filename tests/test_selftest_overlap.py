"""Selftest: deterministic templates rendered for the skill repo's own
context must match the committed dogfood copies byte-for-byte.

5 overlap checks (Codex iter-6 finding #2):
1. .editorconfig
2. .github/workflows/claude-review.yml
3. .github/pull_request_template.md
4. docs/plans/README.md
5. The review-section block of the skill repo's Makefile (bracketed by
   SELFTEST-OVERLAP-BEGIN/END sentinel comments) vs the rendered
   shared/Makefile.review.tmpl.

6+ Script byte-identity checks (Tier-1 review F7 on PR-0):
   Each scripts/*.py that is shipped as a verbatim shared/*.tmpl must
   stay byte-identical so that a future edit to one without the other
   is caught immediately.
"""

from __future__ import annotations

import difflib
import os
import subprocess
from pathlib import Path

import pytest

from bootstrap_lib import render

# Pairs that must stay byte-identical: (scripts/<name>.py, shared/<tmpl-name>.tmpl)
_SCRIPT_TEMPLATE_PAIRS = [
    ("scripts/run-with-clean-env.py", "scripts-run-with-clean-env.py.tmpl"),
    ("scripts/loop-status.py", "scripts-loop-status.py.tmpl"),
    ("scripts/extract-plan-facts.py", "scripts-extract-plan-facts.py.tmpl"),
    ("scripts/extract-codex-session-id.py", "scripts-extract-codex-session-id.py.tmpl"),
    ("scripts/verify-plan-facts.py", "scripts-verify-plan-facts.py.tmpl"),
    ("scripts/propagate-shared-rules.py", "scripts-propagate-shared-rules.py.tmpl"),
]

# scripts/*.py that the review recipes exec directly and that must carry the
# executable bit in the skill repo (the bootstrap sets it via EXECUTABLE_TARGETS
# for generated projects; the dogfood copy must match).
_EXECUTABLE_SCRIPTS = [
    "scripts/extract-codex-session-id.py",
]

SKILL_ROOT = Path(__file__).resolve().parent.parent

SKILL_REPO_CONTEXT = {
    "project_name": "dev-project-setup",
    "language": "python",
    "python_version": "3.12",
    "enable_smoke": False,
    "github_owner": "v3rmus89",
    "github_repo": "dev-project-for-non-developers",
    "github_review_mode": "claude",
}


def _render(tmpl_name, context):
    env = render.build_env("python")
    return env.get_template(tmpl_name).render(**context)


def _assert_byte_equal(rendered, dogfood_path, label):
    actual = dogfood_path.read_text()
    if rendered != actual:
        diff = "\n".join(
            difflib.unified_diff(
                actual.splitlines(),
                rendered.splitlines(),
                fromfile=f"dogfood:{label}",
                tofile=f"rendered:{label}",
                lineterm="",
            )
        )
        pytest.fail(f"{label} drift:\n{diff}")


def test_overlap_editorconfig():
    rendered = _render("editorconfig.tmpl", SKILL_REPO_CONTEXT)
    _assert_byte_equal(rendered, SKILL_ROOT / ".editorconfig", ".editorconfig")


def test_overlap_claude_review_workflow():
    rendered = _render("claude-review.yml.tmpl", SKILL_REPO_CONTEXT)
    _assert_byte_equal(
        rendered,
        SKILL_ROOT / ".github" / "workflows" / "claude-review.yml",
        ".github/workflows/claude-review.yml",
    )


def test_overlap_pull_request_template():
    rendered = _render("pull_request_template.md.tmpl", SKILL_REPO_CONTEXT)
    _assert_byte_equal(
        rendered,
        SKILL_ROOT / ".github" / "pull_request_template.md",
        ".github/pull_request_template.md",
    )


def test_overlap_docs_plans_readme():
    rendered = _render("docs-plans-README.md.tmpl", SKILL_REPO_CONTEXT)
    _assert_byte_equal(
        rendered,
        SKILL_ROOT / "docs" / "plans" / "README.md",
        "docs/plans/README.md",
    )


def test_overlap_makefile_review_section():
    """5th overlap check (Codex iter-5 finding #5): extract the section
    between SELFTEST-OVERLAP-BEGIN and SELFTEST-OVERLAP-END from the skill
    repo's Makefile, diff against the rendered shared/Makefile.review.tmpl
    (which has its OWN sentinel comments — we want the inner text to match)."""
    rendered = _render("Makefile.review.tmpl", SKILL_REPO_CONTEXT)
    dogfood_makefile = (SKILL_ROOT / "Makefile").read_text()

    def _extract_between_sentinels(text, begin_marker, end_marker):
        lines = text.splitlines()
        start = next((i for i, line in enumerate(lines) if begin_marker in line), None)
        end = next((i for i, line in enumerate(lines) if end_marker in line), None)
        if start is None or end is None:
            return None
        # Include the sentinel lines themselves
        return "\n".join(lines[start : end + 1])

    BEGIN = "SELFTEST-OVERLAP-BEGIN: shared/Makefile.review.tmpl"
    END = "SELFTEST-OVERLAP-END: shared/Makefile.review.tmpl"

    dogfood_block = _extract_between_sentinels(dogfood_makefile, BEGIN, END)
    rendered_block = _extract_between_sentinels(rendered, BEGIN, END)

    assert dogfood_block is not None, "missing sentinel block in skill-repo Makefile"
    assert rendered_block is not None, "missing sentinel block in rendered template"

    if dogfood_block != rendered_block:
        diff = "\n".join(
            difflib.unified_diff(
                dogfood_block.splitlines(),
                rendered_block.splitlines(),
                fromfile="dogfood:Makefile review-section",
                tofile="rendered:Makefile.review.tmpl section",
                lineterm="",
            )
        )
        pytest.fail(f"Makefile review-section drift:\n{diff}")


def test_standalone_makefile_review_matches_inline_fragment():
    """R-B2 (adopt-mode Bucket B): `render.render_makefile_review` must produce
    the SAME fragment bytes that `{% include 'Makefile.review.tmpl' %}` inlines
    into the generated Makefile. Adopt writes the standalone `Makefile.review`
    when the target owns a Makefile; it cannot be allowed to drift from the
    inline form. Compare the sentinel-delimited SELFTEST-OVERLAP block (the
    fragment's own body) across both render paths."""
    standalone = render.render_makefile_review(SKILL_REPO_CONTEXT, language="python").decode()
    inline_makefile = render.render_all(SKILL_REPO_CONTEXT, language="python")["Makefile"].decode()

    def _block(text):
        lines = text.splitlines()
        begin = next(i for i, line in enumerate(lines) if "SELFTEST-OVERLAP-BEGIN" in line)
        end = next(i for i, line in enumerate(lines) if "SELFTEST-OVERLAP-END" in line)
        return "\n".join(lines[begin : end + 1])

    assert _block(standalone) == _block(inline_makefile), (
        "standalone Makefile.review fragment drifted from the inline Makefile include"
    )


def test_overlap_dev_review_command():
    """V-21 (S4): the dogfood `.claude/commands/dev-review.md` must equal the
    rendered `shared/claude-commands-dev-review.md.tmpl`. The template carries no
    Jinja directives (project-agnostic `make` targets; PLAN_FILE/ITERATION are
    runtime args, not render vars), so render == source == dogfood. It is still
    loaded THROUGH the Jinja env like every other overlap template."""
    rendered = _render("claude-commands-dev-review.md.tmpl", SKILL_REPO_CONTEXT)
    _assert_byte_equal(
        rendered,
        SKILL_ROOT / ".claude" / "commands" / "dev-review.md",
        ".claude/commands/dev-review.md",
    )


def test_dev_review_command_is_not_git_ignored():
    """S3 / Verification 3: this skill repo ignores `.claude/` (`.gitignore`, to
    keep local session state out of git), so the dogfood command would be
    uncommittable — and V-21 would read an untracked file — without the Part-1
    un-ignore exception. Assert `git check-ignore` reports NO match for the
    command file, while a sibling `.claude/` path stays ignored (the exception
    un-ignores ONLY the command)."""
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not a git work tree")
    cmd = subprocess.run(
        ["git", "check-ignore", ".claude/commands/dev-review.md"],
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
    )
    # rc=1 == path matched NO effective ignore (the trailing `!`-negation wins);
    # rc=0 would mean the un-ignore exception is missing/broken.
    assert cmd.returncode == 1, (
        f".claude/commands/dev-review.md is git-ignored (rc={cmd.returncode}, "
        f"matched {cmd.stdout!r}) — the Part-1 .gitignore un-ignore exception is missing"
    )
    sibling = subprocess.run(
        ["git", "check-ignore", ".claude/settings.local.json"],
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
    )
    assert sibling.returncode == 0, (
        ".claude/settings.local.json should stay ignored — the exception must "
        "un-ignore ONLY the managed command file, not all of .claude/"
    )


@pytest.mark.parametrize("script_rel,tmpl_name", _SCRIPT_TEMPLATE_PAIRS)
def test_script_template_byte_identity(script_rel, tmpl_name):
    """Each scripts/*.py verbatim template must be byte-identical to its
    shared/*.tmpl counterpart — edits to one without the other cause drift."""
    script_text = (SKILL_ROOT / script_rel).read_text(encoding="utf-8")
    tmpl_text = (SKILL_ROOT / "shared" / tmpl_name).read_text(encoding="utf-8")
    if script_text != tmpl_text:
        diff = "\n".join(
            difflib.unified_diff(
                script_text.splitlines(),
                tmpl_text.splitlines(),
                fromfile=f"scripts/{script_rel.split('/')[-1]}",
                tofile=f"shared/{tmpl_name}",
                lineterm="",
            )
        )
        pytest.fail(f"{script_rel} vs {tmpl_name} byte-identity drift:\n{diff}")


@pytest.mark.parametrize("script_rel", _EXECUTABLE_SCRIPTS)
def test_review_script_is_executable(script_rel):
    """Bucket F Scope G: scripts the review recipe execs directly (e.g.
    extract-codex-session-id.py, called as $(CURDIR)/scripts/...) must carry
    the executable bit in the skill repo. The bootstrap sets it for generated
    projects via EXECUTABLE_TARGETS; this guards the dogfood copy from drifting
    to 0644 (which would break the seed path's extraction step)."""
    path = SKILL_ROOT / script_rel
    assert path.exists(), f"{script_rel} missing"
    assert os.access(path, os.X_OK), f"{script_rel} is not executable (expected +x)"


def test_makefile_review_section_carries_thread_mode_machinery():
    """Bucket F Scope B/C parity guard. test_overlap_makefile_review_section
    proves Makefile and the rendered template are byte-IDENTICAL — but two
    identical files could BOTH be missing the THREAD_MODE branch (a delete on
    both sides passes byte-identity). This asserts the machinery is actually
    PRESENT in both surfaces, so an accidental removal fails loudly."""
    rendered = _render("Makefile.review.tmpl", SKILL_REPO_CONTEXT)
    dogfood = (SKILL_ROOT / "Makefile").read_text()
    needles = [
        "THREAD_MODE       ?= fresh",
        "THREAD_FILE       = /tmp/plan-review-$(KEY).thread",
        "THREAD_JSONL_FILE = /tmp/plan-review-$(KEY).session.jsonl",
        'if [ "$(THREAD_MODE)" = "continue" ]; then',
        "codex exec resume",
        "scripts/extract-codex-session-id.py",
        "no rollout found for thread id",
        '[ "$${KEEP_THREAD_JSONL:-}" = "1" ] || rm -f "$(THREAD_JSONL_FILE)"',
    ]
    for needle in needles:
        assert needle in rendered, f"rendered Makefile.review.tmpl missing: {needle!r}"
        assert needle in dogfood, f"dogfood Makefile missing: {needle!r}"


def test_makefile_review_section_carries_review_dispatcher():
    """PR-2 parity guard (same shape as the THREAD_MODE one above):
    test_overlap_makefile_review_section proves the two surfaces are
    byte-IDENTICAL — but a delete on BOTH sides also passes byte-identity. This
    asserts the `make review` dispatcher machinery is actually PRESENT in both
    the rendered template and the dogfood Makefile, so an accidental removal
    fails loudly rather than silently."""
    rendered = _render("Makefile.review.tmpl", SKILL_REPO_CONTEXT)
    dogfood = (SKILL_ROOT / "Makefile").read_text()
    needles = [
        "ACTOR          ?= $(REVIEWER)",
        'if [ "$(REVIEW_RESOLVE)" = "1" ]; then',
        "review:",
        'plan:claude)   TARGET="review-plan-by-codex"',
        'plan:codex)    TARGET="review-plan-by-claude"',
        'commit:claude) TARGET="review-commit-by-claude"',
        'commit:codex)  TARGET="review-commit-by-codex"',
        'TARGET="NEEDS-ASK"',
    ]
    for needle in needles:
        assert needle in rendered, f"rendered Makefile.review.tmpl missing: {needle!r}"
        assert needle in dogfood, f"dogfood Makefile missing: {needle!r}"
