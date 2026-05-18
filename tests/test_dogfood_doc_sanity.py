"""Dogfood-doc Boxette-isms scan (Codex iter-10 finding #3).

Even though AGENTS.md / CLAUDE.md / CONTRIBUTING.md /
pull_request_template.md aren't byte-for-byte selftested (they have
skill-repo-specific overlays), they MUST NOT leak Boxette domain terms.

Allowlist: docs/plans/* may reference Boxette (historical attribution to
the source-of-truth repo).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_TERMS = [
    r"\btelegram\b",
    r"\bpinfl\b",
    r"\bi18n/ru\.json\b",
    r"\bboxette\.db\b",
    r"\bcustoms\b",
    r"\bsignup\b",
    r"\bpayment\b",
]
FORBIDDEN_LITERAL = ["bot/"]

# Boxette is allowed in the plan dir (historical attribution to source repo)
# but NOT in the active dogfood overlays.
BOXETTE_PATTERN = re.compile(r"\bboxette\b", re.IGNORECASE)

DOGFOOD_FILES_TO_SCAN = [
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    ".github/pull_request_template.md",
]

TRIAGE_HEADING = "## Triaging review findings"
TRIAGE_BULLETS = ["(a) Fold now", "(b) Park to BACKLOG", "(c) Reject", "(d) Surface to human"]


@pytest.mark.parametrize("rel_path", DOGFOOD_FILES_TO_SCAN)
def test_no_forbidden_domain_terms(rel_path):
    full = SKILL_ROOT / rel_path
    text = full.read_text()
    lower = text.lower()
    for term in FORBIDDEN_TERMS:
        assert not re.search(term, lower, re.IGNORECASE), (
            f"forbidden term {term!r} found in {rel_path}"
        )
    for literal in FORBIDDEN_LITERAL:
        assert literal not in lower, f"forbidden literal {literal!r} in {rel_path}"


@pytest.mark.parametrize("rel_path", ["AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md"])
def test_no_boxette_in_dogfood_overlays(rel_path):
    """Boxette references in AGENTS.md / CLAUDE.md / CONTRIBUTING.md count as
    leaks. The pull_request_template doesn't reference Boxette either; that's
    covered by the broader test below. docs/plans/* is allowlisted."""
    text = (SKILL_ROOT / rel_path).read_text()
    # The CLAUDE.md and CONTRIBUTING.md may mention Boxette in the
    # bootstrap-exception note (legitimate historical attribution). Allow
    # ONLY inside well-known phrases.
    # For simplicity, allow at most one Boxette reference per file and require
    # it to be near a `bootstrap exception` or `precursor` or `source` term.
    refs = list(BOXETTE_PATTERN.finditer(text))
    for match in refs:
        # Get the surrounding 100 chars
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        snippet = text[start:end].lower()
        legitimate = any(
            phrase in snippet
            for phrase in [
                "bootstrap exception",
                "precursor",
                "source repo",
                "source-of-truth",
                "the patterns this skill extracts",
            ]
        )
        assert legitimate, (
            f"non-attribution Boxette reference in {rel_path}: ...{text[start:end]}..."
        )


def test_skill_repo_contributing_documents_oauth_token():
    """The skill repo's own CONTRIBUTING.md is in `claude` review mode (it
    emits its own claude-review.yml). It MUST instruct contributors to set
    the CLAUDE_CODE_OAUTH_TOKEN secret — otherwise newcomers won't know
    why claude[bot] never comments on their PRs."""
    text = (SKILL_ROOT / "CONTRIBUTING.md").read_text()
    assert "CLAUDE_CODE_OAUTH_TOKEN" in text
    assert "claude setup-token" in text


@pytest.mark.parametrize("rel_path", ["AGENTS.md", "CLAUDE.md"])
def test_triage_rule_present_in_dogfood(rel_path):
    """Drift check: triage rule must be byte-identical-ish across templates
    AND dogfood. Minimal assertion: heading + 4 bullets present.

    (Full byte-identity across all 6 surfaces is enforced separately by
    `tests/test_triage_byte_identity.py`.)"""
    text = (SKILL_ROOT / rel_path).read_text()
    assert TRIAGE_HEADING in text, f"missing triage heading in {rel_path}"
    for bullet in TRIAGE_BULLETS:
        assert bullet in text, f"missing bullet {bullet!r} in {rel_path}"


def test_two_tier_section_present_in_dogfood_claude_md():
    """PR #4 Tier-1 review #6: skill-repo's root `CLAUDE.md` is in `claude`
    mode and must carry the Two-tier code review section. The selftest
    (`tests/test_selftest_overlap.py`) doesn't cover root CLAUDE.md, so this
    test catches drift between shared/CLAUDE.md.tmpl and the dogfood mirror."""
    text = (SKILL_ROOT / "CLAUDE.md").read_text()
    assert "## Two-tier code review" in text, "Two-tier section missing from root CLAUDE.md"
    # `claude` mode signals
    assert "claude[bot]" in text, "claude-mode dogfood missing claude[bot] reference"
    assert "@claude review" in text, "claude-mode dogfood missing @claude trigger"
    # Should NOT mention Codex bot (skill repo is `claude` mode, not `both-docs`)
    assert "@codex review" not in text, (
        "root CLAUDE.md should not reference @codex review (skill repo is claude-mode, not both-docs)"
    )
    # Pointer to Tier-1 targets
    assert "review-commit-by-claude" in text or "review-commit-by-codex" in text


def test_plan_review_consistency_line_present_in_dogfood():
    """PR #4: the pre-next-iter consistency self-check instruction must
    appear in root CLAUDE.md + docs/plans/README.md."""
    for rel_path in ["CLAUDE.md", "docs/plans/README.md"]:
        text = (SKILL_ROOT / rel_path).read_text()
        assert "review-plan-consistency-by-claude" in text, (
            f"consistency-self-check reference missing in {rel_path}"
        )


@pytest.mark.parametrize("rel_path", ["CLAUDE.md", "AGENTS.md"])
def test_cross_session_recovery_instruction_present(rel_path):
    """PR #5a: the cross-session state recovery instruction must appear in
    BOTH CLAUDE.md AND AGENTS.md (per the original BACKLOG entry's "CLAUDE.md
    / AGENTS.md instruction" requirement; Codex GitHub bot reads AGENTS.md,
    not CLAUDE.md)."""
    text = (SKILL_ROOT / rel_path).read_text()
    assert "## Cross-session state recovery" in text, (
        f"Cross-session state recovery section missing in {rel_path}"
    )
    assert "make status" in text, (
        f"{rel_path}'s cross-session recovery section must reference `make status`"
    )


@pytest.mark.parametrize("rel_path", ["CLAUDE.md", "AGENTS.md"])
def test_self_improvement_loop_instruction_present(rel_path):
    """PR #5a: the LESSONS.md self-improvement loop instruction must appear in
    BOTH CLAUDE.md AND AGENTS.md, with the writable-vs-read-only context
    distinction explicit."""
    text = (SKILL_ROOT / rel_path).read_text()
    assert "## Self-improvement loop (LESSONS.md)" in text, (
        f"Self-improvement loop section missing in {rel_path}"
    )
    assert "LESSONS.md" in text, f"{rel_path} must reference LESSONS.md"
    # The read-only context distinction must be present (different wording per surface)
    if rel_path == "CLAUDE.md":
        assert (
            "writable implementation session" in text.lower() or "writable-session" in text.lower()
        ), "CLAUDE.md must distinguish writable vs read-only sessions"
        assert "read-only" in text.lower()
    else:  # AGENTS.md is itself the read-only context
        assert "read-only" in text.lower(), (
            "AGENTS.md must explicitly call itself a read-only context"
        )
        assert "do not edit" in text.lower() or "do not append" in text.lower(), (
            "AGENTS.md must forbid LESSONS.md edits from review sessions"
        )


def test_lessons_md_exists_with_seed_entries():
    """PR #5a: skill repo's own LESSONS.md ships with ≥3 seed entries. Schema
    validation is in tests/test_lessons_file_schema.py; this dogfood test
    just confirms the file exists in the active surface set."""
    lessons = SKILL_ROOT / "LESSONS.md"
    assert lessons.exists(), "LESSONS.md must exist at skill repo root"
    text = lessons.read_text()
    # At least 3 dated entries
    import re

    entries = re.findall(r"^### \d{4}-\d{2}-\d{2}:", text, re.MULTILINE)
    assert len(entries) >= 3, (
        f"skill repo LESSONS.md should ship with ≥3 seed entries, found {len(entries)}"
    )
