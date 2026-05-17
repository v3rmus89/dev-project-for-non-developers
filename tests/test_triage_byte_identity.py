"""Triage-rule byte-identity test (closes Codex iter-6 #2 from PR #4 plan loop).

The "Triaging review findings" section must be byte-identical across all six
surfaces:
- shared/CLAUDE.md.tmpl (rendered against skill-repo context)
- shared/AGENTS.md.tmpl (rendered against skill-repo context)
- shared/docs-plans-README.md.tmpl (rendered against skill-repo context)
- root CLAUDE.md (dogfood)
- root AGENTS.md (dogfood)
- docs/plans/README.md (dogfood)

The existing tests/test_dogfood_doc_sanity.py only checks heading + bullet
presence; this test enforces the FULL block (including the four-questions
extension added by PR #4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bootstrap_lib import render

SKILL_ROOT = Path(__file__).resolve().parent.parent

TRIAGE_HEADING = "## Triaging review findings"
# Block ends at the next `##` heading
NEXT_SECTION_PATTERN = "\n## "


def _extract_triage_block(text: str) -> str:
    start = text.index(TRIAGE_HEADING)
    rest = text[start + len(TRIAGE_HEADING) :]
    end = rest.index(NEXT_SECTION_PATTERN)
    return rest[:end].strip()


SKILL_REPO_CONTEXT = {
    "project_name": "dev-project-setup",
    "project_import_name": "dev_project_setup",
    "language": "python",
    "python_version": "3.12",
    "node_version": "24",
    "go_version": "1.26",
    "enable_smoke": False,
    "github_owner": "v3rmus89",
    "github_repo": "dev-project-for-non-developers",
    "github_review_mode": "claude",
}


def _rendered(tmpl_name: str) -> str:
    env = render.build_env("python")
    return env.get_template(tmpl_name).render(**SKILL_REPO_CONTEXT)


def test_triage_block_byte_identical_across_six_surfaces():
    """The triage block + four-questions extension must be byte-identical
    across three templates (rendered) AND three dogfood docs. Drift between
    any pair fails the test."""
    surfaces = {
        "shared/CLAUDE.md.tmpl": _extract_triage_block(_rendered("CLAUDE.md.tmpl")),
        "shared/AGENTS.md.tmpl": _extract_triage_block(_rendered("AGENTS.md.tmpl")),
        "shared/docs-plans-README.md.tmpl": _extract_triage_block(
            _rendered("docs-plans-README.md.tmpl")
        ),
        "CLAUDE.md": _extract_triage_block((SKILL_ROOT / "CLAUDE.md").read_text()),
        "AGENTS.md": _extract_triage_block((SKILL_ROOT / "AGENTS.md").read_text()),
        "docs/plans/README.md": _extract_triage_block(
            (SKILL_ROOT / "docs" / "plans" / "README.md").read_text()
        ),
    }

    # Pick one canonical to diff everything against
    canonical_key = "shared/CLAUDE.md.tmpl"
    canonical = surfaces[canonical_key]

    drift = {}
    for name, block in surfaces.items():
        if name == canonical_key:
            continue
        if block != canonical:
            # Find first diff offset for the failure message
            for i, (a, b) in enumerate(zip(canonical, block, strict=False)):
                if a != b:
                    drift[name] = (
                        f"diverges at char {i}: "
                        f"canonical has {canonical[i : i + 60]!r}, {name} has {block[i : i + 60]!r}"
                    )
                    break
            else:
                drift[name] = f"length diff: canonical={len(canonical)}, {name}={len(block)}"

    assert not drift, "Triage block drift:\n" + "\n".join(f"  {k}: {v}" for k, v in drift.items())


@pytest.mark.parametrize(
    "surface",
    [
        "shared/CLAUDE.md.tmpl",
        "shared/AGENTS.md.tmpl",
        "shared/docs-plans-README.md.tmpl",
        "CLAUDE.md",
        "AGENTS.md",
        "docs/plans/README.md",
    ],
)
def test_four_questions_extension_present(surface):
    """The four 'before deciding' questions added by PR #4 must appear in every
    surface that carries the triage rule (3 templates + 3 dogfood docs)."""
    if surface.startswith("shared/"):
        text = _rendered(surface.replace("shared/", ""))
    else:
        text = (SKILL_ROOT / surface).read_text()
    block = _extract_triage_block(text)
    assert "Before deciding (a/b/c/d), ask these four questions" in block, (
        f"four-questions header missing in {surface}"
    )
    assert "Is the premise correct?" in block, f"Q1 missing in {surface}"
    assert "Is the suggested fix the best fix" in block, f"Q2 missing in {surface}"
    assert "What else does this finding imply?" in block, f"Q3 missing in {surface}"
    assert "Does folding introduce a contradiction" in block, f"Q4 missing in {surface}"
