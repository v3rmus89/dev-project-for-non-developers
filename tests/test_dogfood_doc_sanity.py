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
    "LESSONS.md",
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
    """PR #4 Tier-1 review #6: skill-repo's root `CLAUDE.md` must carry the
    Two-tier code review section. The skill repo itself runs BOTH GitHub
    review bots (`claude[bot]` + `chatgpt-codex-connector[bot]`, verified on
    PR #16), so its dogfood Two-tier section describes both — intentionally
    diverging from `shared/CLAUDE.md.tmpl`'s `claude`-mode Jinja branch,
    which describes only `claude[bot]`. The selftest
    (`tests/test_selftest_overlap.py`) doesn't cover root CLAUDE.md; this
    test pins the dogfood section's content directly."""
    text = (SKILL_ROOT / "CLAUDE.md").read_text()
    assert "## Two-tier code review" in text, "Two-tier section missing from root CLAUDE.md"
    # Skill repo runs both bots — the dogfood Two-tier section describes both.
    assert "claude[bot]" in text, "dogfood Two-tier missing claude[bot] reference"
    assert "@claude review" in text, "dogfood Two-tier missing @claude trigger"
    assert "@codex review" in text, (
        "dogfood Two-tier missing @codex trigger (skill repo runs both bots — verified on PR #16)"
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


def test_readme_step3_names_approval_mechanisms_and_claude_md_is_agnostic():
    """V-20: docs/plans/README.md step-3 block mentions both delivery mechanisms
    (plan-mode ExitPlanMode + chat keyword). CLAUDE.md gate paragraph stays
    path-agnostic — does NOT enumerate either mechanism, pointing to README step 3
    for the canonical wording instead."""
    readme = (SKILL_ROOT / "docs/plans/README.md").read_text()
    assert "ExitPlanMode" in readme, (
        "docs/plans/README.md step 3 must mention ExitPlanMode as a plan-mode delivery mechanism"
    )
    assert "approve" in readme and "changes:" in readme, (
        "docs/plans/README.md step 3 must mention chat keywords as a delivery mechanism"
    )

    claude_md = (SKILL_ROOT / "CLAUDE.md").read_text()
    gate_start = claude_md.find("## Mandatory human-approval gate")
    assert gate_start != -1, "Mandatory human-approval gate section missing from CLAUDE.md"
    next_sec = claude_md.find("\n## ", gate_start + 1)
    gate_text = claude_md[gate_start:next_sec] if next_sec != -1 else claude_md[gate_start:]
    assert "ExitPlanMode" not in gate_text, (
        "CLAUDE.md gate paragraph must not enumerate ExitPlanMode (point to README step 3 instead)"
    )
    assert "**approve** / **changes:" not in gate_text, (
        "CLAUDE.md gate paragraph must not enumerate the specific chat-keyword list "
        "(use 'explicit user approval' and point to README step 3)"
    )
    assert "explicit user approval" in gate_text, (
        "CLAUDE.md gate paragraph must use path-agnostic 'explicit user approval' phrasing"
    )


def test_backlog_has_deferred_bucket_entries():
    """V-22: BACKLOG.md carries durable entries for deferred Buckets A + F (iter-7 F2 fold).
    Both slugs present; each entry has Trigger + Starting requirements subsections;
    iter-1..6 F-series finding numbers referenced."""
    import re

    text = (SKILL_ROOT / "BACKLOG.md").read_text()
    assert "skill-wrapper-pr-followup" in text, (
        "BACKLOG.md must contain skill-wrapper-pr-followup entry (deferred Bucket A)"
    )
    assert "continue-thread-pr-followup" in text, (
        "BACKLOG.md must contain continue-thread-pr-followup entry (deferred Bucket F)"
    )
    for slug in ("skill-wrapper-pr-followup", "continue-thread-pr-followup"):
        idx = text.find(slug)
        assert idx != -1
        vicinity = text[idx : idx + 3000]
        assert "Trigger" in vicinity, f"BACKLOG entry '{slug}' must have a Trigger subsection"
        assert "Starting requirements" in vicinity, (
            f"BACKLOG entry '{slug}' must have a Starting requirements subsection"
        )
    f_refs = re.findall(r"iter-[1-6] F\d+", text)
    assert len(f_refs) >= 4, (
        f"BACKLOG must have ≥4 iter-1..6 F-series finding references, found {len(f_refs)}"
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


def test_fact_check_workflow_in_contributing():
    """PR-0: both dogfood CONTRIBUTING.md and the rendered template must document
    the fact-check pre-pass (iter 0.5) within the Plan checklist step."""
    from bootstrap_lib import render

    dogfood = (SKILL_ROOT / "CONTRIBUTING.md").read_text()
    env = render.build_env("python")
    rendered = env.get_template("CONTRIBUTING.md.tmpl").render(
        project_name="fixture",
        language="python",
        python_version="3.12",
        enable_smoke=False,
        github_owner="owner",
        github_repo="repo",
        github_review_mode="claude",
    )

    for surface_name, text in [("dogfood", dogfood), ("rendered", rendered)]:
        assert "review-plan-fact-check-by-codex" in text, (
            f"{surface_name} CONTRIBUTING.md must reference review-plan-fact-check-by-codex"
        )
        assert "iter 0.5" in text, (
            f"{surface_name} CONTRIBUTING.md must reference iter 0.5 for the fact-check pre-pass"
        )
