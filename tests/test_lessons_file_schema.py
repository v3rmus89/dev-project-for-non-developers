"""LESSONS.md schema + dual-mode (skill repo has seeds, shared template empty).

Closes Bucket F items for PR #5a:
- Schema test: well-formed structure + entry format
- Skill repo has the 3+ seed entries (from PR #1-#4 lessons)
- Shared template ships EMPTY (no seeds) — generated projects accumulate their own
"""

from __future__ import annotations

import re
from pathlib import Path

from bootstrap_lib import render

SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_LESSONS = SKILL_ROOT / "LESSONS.md"

# Match `### YYYY-MM-DD: <one-line mistake>`
ENTRY_HEADING_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2}): (.+)$", re.MULTILINE)


def _extract_active_section(text: str) -> str:
    """Extract everything between `## Active` and `## Archived`."""
    start = text.index("## Active")
    end = text.index("## Archived")
    return text[start:end]


def _extract_archived_section(text: str) -> str:
    """Extract everything from `## Archived` to end."""
    start = text.index("## Archived")
    return text[start:]


def test_lessons_file_has_required_headings():
    """Both skill repo + shared template render must have the canonical structure."""
    skill_text = SKILL_LESSONS.read_text()
    env = render.build_env("python")
    template_text = env.get_template("LESSONS.md.tmpl").render(
        project_name="test-proj",
        language="python",
        python_version="3.12",
        node_version="24",
        go_version="1.26",
        enable_smoke=False,
        github_owner="",
        github_repo="",
        github_review_mode="none",
    )
    for surface_name, text in [
        ("skill LESSONS.md", skill_text),
        ("shared template", template_text),
    ]:
        assert text.startswith("# Lessons"), f"{surface_name} missing top-level heading"
        assert "## How to use this file" in text, f"{surface_name} missing usage section"
        assert "## Active" in text, f"{surface_name} missing Active section"
        assert "## Archived" in text, f"{surface_name} missing Archived section"


def test_skill_lessons_has_seed_entries():
    """Skill repo's own LESSONS.md ships with the 5 seed entries surfaced from
    PR #1-#5 plan loops (3 originally planned + 2 captured during PR #5 plan loop:
    self-check skipped + Jinja placeholder literal). Generated projects do NOT
    get these (the shared template ships empty).

    Closes Tier-1 P6: assertion tightened to match the docstring's claim of 5
    entries. If a future cleanup drops one, the test catches it instead of
    silently lying."""
    text = SKILL_LESSONS.read_text()
    active = _extract_active_section(text)
    entries = ENTRY_HEADING_RE.findall(active)
    assert len(entries) >= 5, (
        f"Expected ≥5 seed entries in Active section per the docstring's claim, "
        f"found {len(entries)}: {entries}"
    )
    # Spot-check that specific seed lessons are present
    titles = [title for _, title in entries]
    title_text = " | ".join(titles).lower()
    assert "premise" in title_text, "Seed lesson about verifying reviewer premise missing"
    assert "jinja" in title_text, "Seed lesson about Jinja branches missing"
    assert "git add" in title_text, "Seed lesson about git add -A missing"
    assert "self-check" in title_text or "consistency" in title_text, (
        "Seed lesson about always running self-check missing (PR #5 plan-loop lesson)"
    )
    assert "placeholder" in title_text or "literal" in title_text, (
        "Seed lesson about Jinja literal placeholders missing (PR #5 Codex Tier-2 lesson)"
    )


def test_skill_lessons_entries_have_required_fields():
    """Each Active entry must have **Trigger**, **Rule**, **Status** fields."""
    text = SKILL_LESSONS.read_text()
    active = _extract_active_section(text)
    # Split by `### ` to get each entry (skip pre-first-entry header text)
    raw_entries = active.split("### ")[1:]  # first split chunk is pre-### text
    for entry in raw_entries:
        # The entry's heading is `YYYY-MM-DD: ...` (matched by our regex elsewhere)
        first_line = entry.split("\n", 1)[0]
        assert ENTRY_HEADING_RE.match(f"### {first_line}"), (
            f"Entry has malformed heading: {first_line!r}"
        )
        assert "**Trigger**:" in entry, f"Entry missing Trigger field: {first_line}"
        assert "**Rule**:" in entry, f"Entry missing Rule field: {first_line}"
        assert "**Status**:" in entry, f"Entry missing Status field: {first_line}"


def test_shared_lessons_template_ships_empty():
    """Generated projects accumulate their own lessons — shared template MUST
    NOT include seed entries (that'd be the skill repo's own history leaking)."""
    env = render.build_env("python")
    text = env.get_template("LESSONS.md.tmpl").render(
        project_name="test-proj",
        language="python",
        python_version="3.12",
        node_version="24",
        go_version="1.26",
        enable_smoke=False,
        github_owner="",
        github_repo="",
        github_review_mode="none",
    )
    active = _extract_active_section(text)
    entries = ENTRY_HEADING_RE.findall(active)
    assert len(entries) == 0, (
        f"Shared template Active section should be EMPTY (generated projects start fresh) "
        f"but found {len(entries)} entries: {entries}"
    )


def test_lessons_template_renders_for_all_languages():
    """Shared template should render cleanly regardless of language context."""
    env = render.build_env("python")
    for language in ["python", "nodejs", "go"]:
        text = env.get_template("LESSONS.md.tmpl").render(
            project_name="test-proj",
            language=language,
            python_version="3.12",
            node_version="24",
            go_version="1.26",
            enable_smoke=False,
            github_owner="",
            github_repo="",
            github_review_mode="none",
        )
        assert "# Lessons" in text, f"language={language} render missing header"
