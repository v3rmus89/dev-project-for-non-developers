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
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from bootstrap_lib import render

SKILL_ROOT = Path(__file__).resolve().parent.parent

SKILL_REPO_CONTEXT = {
    "project_name": "dev-project-setup",
    "project_import_name": "dev_project_setup",
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
