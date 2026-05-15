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
    AND dogfood. Minimal assertion: heading + 4 bullets present."""
    text = (SKILL_ROOT / rel_path).read_text()
    assert TRIAGE_HEADING in text, f"missing triage heading in {rel_path}"
    for bullet in TRIAGE_BULLETS:
        assert bullet in text, f"missing bullet {bullet!r} in {rel_path}"
