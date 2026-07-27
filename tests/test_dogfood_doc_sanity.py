"""Dogfood-doc private-domain-term scan (Codex iter-10 finding #3).

Even though AGENTS.md / CLAUDE.md / CONTRIBUTING.md /
pull_request_template.md aren't byte-for-byte selftested (they have
skill-repo-specific overlays), they MUST NOT leak domain terms from the
private origin project this skill was extracted from.

Allowlist: docs/plans/* may reference the origin project (historical
attribution to the source-of-truth repo).

NOTE: the literals in FORBIDDEN_TERMS and ORIGIN_PROJECT_PATTERN are the real
private-project terms on purpose. They ARE the detector -- genericizing them
would leave this guard green while detecting nothing.
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

# The origin project is allowed in the plan dir (historical attribution to the
# source repo) but NOT in the active dogfood overlays.
ORIGIN_PROJECT_PATTERN = re.compile(r"\bboxette\b", re.IGNORECASE)

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
def test_no_origin_project_refs_in_dogfood_overlays(rel_path):
    """Origin-project references in AGENTS.md / CLAUDE.md / CONTRIBUTING.md count
    as leaks. The pull_request_template doesn't reference it either; that's
    covered by the broader test below. docs/plans/* is allowlisted."""
    text = (SKILL_ROOT / rel_path).read_text()
    # The CLAUDE.md and CONTRIBUTING.md may mention the origin project in the
    # bootstrap-exception note (legitimate historical attribution). Allow
    # ONLY inside well-known phrases.
    # For simplicity, allow at most one such reference per file and require
    # it to be near a `bootstrap exception` or `precursor` or `source` term.
    refs = list(ORIGIN_PROJECT_PATTERN.finditer(text))
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
            f"non-attribution origin-project reference in {rel_path}: ...{text[start:end]}..."
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


def _render_shared(tmpl_name):
    """Render a shared/*.tmpl for the skill repo's own (claude) context."""
    from bootstrap_lib import render

    env = render.build_env("python")
    return env.get_template(tmpl_name).render(
        project_name="fixture",
        language="python",
        python_version="3.12",
        enable_smoke=False,
        github_owner="owner",
        github_repo="repo",
        github_review_mode="claude",
    )


@pytest.mark.parametrize("rel_path", ["CLAUDE.md", "shared/CLAUDE.md.tmpl"])
def test_dev_review_dispatch_convention_in_claude_surfaces(rel_path):
    """S5/S6: the Claude dispatch convention (invoke /dev-review; commit→ACTOR=claude
    directly, plan→ask the author; REVIEWER is terminal-only because a per-tool-call
    export does not persist) must be present in BOTH the dogfood CLAUDE.md AND the
    rendered shared/CLAUDE.md.tmpl — a Risks-table failure mode is the instruction
    landing in one surface but not the other. The Codex wording differs (it can't
    invoke a slash command) and is asserted separately on the AGENTS surfaces."""
    if rel_path.endswith(".tmpl"):
        text = _render_shared("CLAUDE.md.tmpl")
    else:
        text = (SKILL_ROOT / rel_path).read_text()
    assert "/dev-review" in text, f"{rel_path} missing the /dev-review dispatch convention"
    assert "single source of dispatch truth" in text, (
        f"{rel_path} missing the make-review-is-dispatch-truth note"
    )
    assert "REVIEWER" in text, (
        f"{rel_path} must note REVIEWER is terminal-only (not a per-tool-call export)"
    )


@pytest.mark.parametrize("rel_path", ["AGENTS.md", "shared/AGENTS.md.tmpl"])
def test_dev_review_dispatch_convention_in_agents_surfaces(rel_path):
    """S5/S6 (Codex mirror): Codex CANNOT invoke a Claude slash command, so BOTH
    the dogfood AGENTS.md AND the rendered shared/AGENTS.md.tmpl must tell it to
    run `make review ACTOR=codex …` directly, passing ACTOR=codex inline (a
    separate `export REVIEWER` is unreliable — each tool call is a fresh shell,
    iter-4 FN3)."""
    if rel_path.endswith(".tmpl"):
        text = _render_shared("AGENTS.md.tmpl")
    else:
        text = (SKILL_ROOT / rel_path).read_text()
    assert "make review" in text and "ACTOR=codex" in text, (
        f"{rel_path} missing the Codex `make review ACTOR=codex` dispatch convention"
    )
    assert "fresh shell" in text, (
        f"{rel_path} must explain ACTOR=codex is passed inline because each tool call "
        "is a fresh shell (no persistent REVIEWER export)"
    )


def test_dev_review_command_body_six_branch_dispatch():
    """6-branch acceptance (S7 / 1D). The dispatcher resolve-mode tests cover 4
    branches (Claude/Codex x plan/commit); these are the other 2 (Other x {plan,
    commit}), asserted on the command body — mode-asymmetric per iter-3 FN1:

    - Other x commit → emits `make review MODE=commit ACTOR=claude` DIRECTLY, with
      NO AskUserQuestion (the session is the implementer by construction);
    - Other x plan  → AskUserQuestions the author, THEN emits the chosen-direction
      `make review MODE=plan ACTOR=<answer> …` form.

    And it NEVER lists both cross-AI directions at once (PR #10 iter-4 F5)."""
    body = (SKILL_ROOT / ".claude" / "commands" / "dev-review.md").read_text()

    commit_idx = body.find("\n## commit")
    plan_idx = body.find("\n## plan")
    assert commit_idx != -1, "command missing a `## commit` section"
    assert plan_idx != -1, "command missing a `## plan` section"
    assert commit_idx < plan_idx, "expected the `## commit` section before `## plan`"
    commit_section = body[commit_idx:plan_idx]
    plan_section = body[plan_idx:]

    # Other x commit: direct ACTOR=claude, no ask.
    assert "make review MODE=commit ACTOR=claude" in commit_section, (
        "commit branch must dispatch `make review MODE=commit ACTOR=claude` directly"
    )
    assert "AskUserQuestion" not in commit_section, (
        "commit branch must NOT ask — the session is the implementer by construction"
    )

    # Other x plan: ask the author first, then emit the chosen-direction form.
    assert "AskUserQuestion" in plan_section, (
        "plan branch must AskUserQuestion the author (never a silent default)"
    )
    assert "make review MODE=plan ACTOR=" in plan_section, (
        "plan branch must emit `make review MODE=plan ACTOR=<author> …`"
    )

    # Never offers both cross-AI directions — the dispatcher owns direction.
    assert not ("review-plan-by-codex" in body and "review-plan-by-claude" in body), (
        "command must NOT list both cross-AI review directions (PR #10 iter-4 F5)"
    )


def test_usage_doc_documents_neutralize_and_dev_review():
    """S12 / iter-4 FN5: docs/usage.md's normative tables must carry the
    NEUTRALIZE adopt-rule row + the v2-restore sentinel-removal row, and the
    `/dev-review` front-end, so the docs cannot silently drift from the engine."""
    text = (SKILL_ROOT / "docs" / "usage.md").read_text()
    # adopt-mode rule table: the `.claude/`-class → NEUTRALIZE policy (vs broad → SKIP)
    assert "`NEUTRALIZE`" in text, "usage.md must document the NEUTRALIZE policy"
    assert "`.claude/`-class" in text, (
        "usage.md must document the `.claude/`-class NEUTRALIZE trigger"
    )
    # v2 restore matrix: sentinel-based block removal (NOT whole-file SHA)
    assert "sentinel match" in text, (
        "usage.md restore docs must describe NEUTRALIZE sentinel-based block removal"
    )
    # the /dev-review front-end + its dispatcher
    assert "/dev-review" in text, "usage.md must document the /dev-review command"
    assert "make review" in text, "usage.md must document the make review dispatcher"


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


def test_architectural_blocker_split_advisory_in_contributing():
    """Side-workstream item 2 (meta-plan ``what-else-i-want-majestic-rain``):
    both dogfood CONTRIBUTING.md and the rendered template must carry the
    *advisory* (NOT a hard rule) to consider splitting a PR when a new
    architectural blocker surfaces at iter >=3. Presence-only — the guidance
    must exist; it is explicitly a judgment call, never enforced."""
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
        assert "Architectural-blocker split" in text, (
            f"{surface_name} CONTRIBUTING.md must carry the architectural-blocker-split advisory"
        )
        assert "consider splitting the PR" in text, (
            f"{surface_name} CONTRIBUTING.md advisory must say to consider splitting the PR"
        )


def test_runbook_rule_in_contributing():
    """C2 (plan-review-loop over-iteration guardrails): both dogfood
    CONTRIBUTING.md and the rendered template must carry the "keep executable
    runbooks out of the plan" rule — a plan describes deploy/rollback at intent
    fidelity, while line-level scripts live in a real file and are verified by
    execution + Tier-1, not the static review loop. Presence-only; the dogfood
    copy may carry a repo-specific example (the post-2b loop) that the generic
    template omits — the same divergence as the architectural-blocker split."""
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
        assert "Keep executable runbooks out of the plan" in text, (
            f"{surface_name} CONTRIBUTING.md must carry the runbooks-out-of-plan rule"
        )
        # The boundary line is the operational crux (what stays in the plan vs
        # what moves to a script) and is identical across both surfaces.
        assert "ordering / scope / which-failure-to-check" in text, (
            f"{surface_name} CONTRIBUTING.md runbook rule must state the plan/script boundary"
        )


def test_runbook_rule_cross_referenced_in_docs_plans_readme():
    """C2: docs/plans/README.md "Stopping the loop" cross-references the runbook
    rule. test_selftest_overlap.test_overlap_docs_plans_readme keeps README and
    its .tmpl byte-identical, but a delete on BOTH sides would still pass that
    byte-identity check — this presence guard makes an accidental removal of the
    cross-reference fail loudly (same shape as the Makefile-machinery guards)."""
    readme = (SKILL_ROOT / "docs/plans/README.md").read_text()
    assert "Executable runbooks stay out of the plan body" in readme, (
        "docs/plans/README.md must cross-reference the runbook rule under 'Stopping the loop'"
    )


def test_circuit_breaker_second_trigger_in_contributing():
    """C3 (plan-review-loop over-iteration guardrails): both dogfood
    CONTRIBUTING.md and the rendered template must carry the circuit-breaker's
    *second trigger* — when imp-3 findings keep regenerating past ~iter 5 but
    cluster in one artifact/theme (a deploy runbook, CLI/API signatures), that is
    an artifact-class mismatch, not convergence: stop folding and switch to
    execution-based verification or the gate. Distinct from the architectural-
    blocker split (which is about design holes). Identical text in both surfaces
    (no repo-specific example), so this also implicitly guards the dogfood/tmpl
    parity for C3."""
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
        assert "Second trigger — same-class regeneration" in text, (
            f"{surface_name} CONTRIBUTING.md must carry the circuit-breaker second trigger"
        )
        # The crux that distinguishes it from the architectural-blocker split:
        # this is an artifact-class mismatch (wrong verification tool), not a
        # design hole.
        assert "artifact-class" in text, (
            f"{surface_name} CONTRIBUTING.md second trigger must name the artifact-class mismatch"
        )


def test_circuit_breaker_in_docs_plans_readme():
    """C3: docs/plans/README.md "Stopping the loop" carries the same-class-
    regeneration stop signal. Byte-equality to the .tmpl is enforced by
    test_selftest_overlap.test_overlap_docs_plans_readme; this presence guard
    catches a delete-on-both-sides that byte-identity alone would pass."""
    readme = (SKILL_ROOT / "docs/plans/README.md").read_text()
    assert "Same-class regeneration is not convergence" in readme, (
        "docs/plans/README.md must carry the circuit-breaker stop signal under 'Stopping the loop'"
    )


def test_cap_consistency_self_check_in_contributing():
    """Cap-consistency rule (sibling of C3, scoped to the N.5 self-check): both
    dogfood CONTRIBUTING.md and the rendered template must carry the rule that
    caps the consistency self-check (`make review-plan-consistency-by-claude`) at
    ~2 passes — when a pass surfaces only cosmetic / self-inflicted nits (each fold
    spawning the next), that is same-class regeneration applied to the self-check,
    not convergence. Distinct from C3's *second trigger*, which is an executable
    *artifact*-class mismatch in the cross-review loop. The dogfood carries a
    repo-specific example (the guardrails plan's own 5-pass run) that the .tmpl
    strips, so this guards only the shared rule text."""
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
        assert "Cap the consistency self-check" in text, (
            f"{surface_name} CONTRIBUTING.md must carry the consistency-self-check cap rule"
        )
        # The crux distinguishing it from C3's artifact-class second trigger: this
        # fires on cosmetic / self-inflicted churn in the self-check, where each
        # fold spawns the next nit rather than resolving a real contradiction.
        assert "self-inflicted" in text, (
            f"{surface_name} CONTRIBUTING.md cap rule must name the self-inflicted-churn signal"
        )


def test_cap_consistency_self_check_in_docs_plans_readme():
    """docs/plans/README.md "Stopping the loop" carries the consistency-self-check
    cap stop signal. Byte-equality to the .tmpl is enforced by
    test_selftest_overlap.test_overlap_docs_plans_readme; this presence guard
    catches a delete-on-both-sides that byte-identity alone would pass."""
    readme = (SKILL_ROOT / "docs/plans/README.md").read_text()
    assert "Cap the consistency self-check at ~2 passes" in readme, (
        "docs/plans/README.md must carry the consistency-self-check cap stop signal "
        "under 'Stopping the loop'"
    )
