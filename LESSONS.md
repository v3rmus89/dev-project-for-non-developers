# Lessons

Append-only log of mistakes + the rules that prevent recurrence. Read the
"Active" section at session start. Move solved/obsolete entries to "Archived"
once the pattern hasn't fired for 3+ sessions OR the underlying problem is
solved structurally.

## How to use this file

- **At session start**: read the "Active" section. Apply the rules during this session.
- **After ANY user push-back that changes your approach**, OR any Tier-1/2 finding that surfaced a new mistake-class:
  - **In a writable implementation session**: append a new entry to "Active" directly. Commit alongside the implementation.
  - **In a read-only review session** (e.g. `make review-plan-by-codex`, `make review-commit-by-claude`, or any session told "Do NOT edit files"): do NOT append. Propose the lesson in the review output instead. Driver triages reviewer-proposed lessons in a later writable session.
- **Entry format**:
  ```
  ### YYYY-MM-DD: <one-line mistake>

  **Trigger**: <what happened that surfaced this>

  **Rule**: <what to do differently>

  **Status**: Active
  ```
- **Promotion to CLAUDE.md** is rare and only via plan-review (for fundamental shifts). Default path: solved → archive in this file.

## Active

### 2026-05-17: Don't apply reviewer's suggested fix without verifying premise

**Trigger**: PR #4 iter-4 #2 — Codex framed a hypothetical as imp-3 blocker. User push-back revealed the premise was wrong (Claude `--print --permission-mode plan` did NOT have the speculated invocation failure).

**Rule**: For every reviewer finding, run the four questions BEFORE deciding (a/b/c/d). Q1 specifically: is the premise correct? Spot-check against the file the reviewer cites. (See CLAUDE.md triage section.)

**Status**: Active

---

### 2026-05-17: Conditional Jinja branches can contradict surrounding non-conditional prose

**Trigger**: PR #4 Codex Tier-2 P2 — `none`-mode rendered "use BOTH tiers" (unconditional intro) then conditional "Tier-2 NOT configured" body. Tier-1 review missed it; Tier-2 caught it.

**Rule**: When adding `{% if %}` / `{% elif %}` branches to a template, audit the surrounding non-conditional prose for assumptions that hold only in some branches. If they do, move them inside the conditional or rewrite branch-agnostic.

**Status**: Active

---

### 2026-05-17: Don't use `git add -A` or `git add .` — pick files explicitly

**Trigger**: PR #4 — accidentally committed `.claude/scheduled_tasks.lock` session state via `git add -A`. CLAUDE.md already forbade `git add .` but didn't explicitly cover `-A`.

**Rule**: Always `git add path1 path2 ...`. Bulk-add flags (`-A`, `.`, `-u` outside review) catch session state, debug files, generated artifacts. Skill repo's `.gitignore` was extended too, but the discipline still matters.

**Status**: Active

---

### 2026-05-18: After folding any Codex iter's findings, ALWAYS run consistency self-check before committing the plan

**Trigger**: PR #5 plan loop — I skipped self-check 6.5 in "ship now" mode and went straight from iter-6 fold to commit + push. User pushed back asking why. Ran the self-check; found 9 real drifts that would have been Tier-2 review findings or impl-time landmines.

**Rule**: After ANY iter's findings get folded, run `make review-plan-consistency-by-claude PLAN_FILE=... ITERATION=N` BEFORE the commit that ships those folds. The ritual matters MORE when in a hurry, not less — that's exactly when cross-section misses accumulate. No exceptions for "ship now" mode.

**Status**: Active

---

### 2026-05-18: When extending a Jinja macro inside a string-substituted template, trace what literal placeholders become after rendering

**Trigger**: PR #5 Codex Tier-2 — my iter-6 fold extended `tier1_prompt` to take `plan_file=None` and updated CONTRIBUTING.md.tmpl's subagent template to invoke `{{ tier1_prompt('<SHA>', '<PLAN_FILE>') }}`. At bootstrap render time the literal `<PLAN_FILE>` placeholder becomes a non-empty string → macro's `{% if plan_file %}` treats it as truthy → "PLAN_FILE is set" branch fires with a placeholder path. Defeats the unbound-fallback contract.

**Rule**: When extending a Jinja macro that's invoked inside another template (especially one that ships to generated projects with literal `<PLACEHOLDER>` text the user later substitutes), trace what the rendered output actually contains. Empty-string and `None` are different in Jinja. Test the macro with `None`, empty string, AND literal placeholder text to confirm the branch logic.

**Status**: Active

---

### 2026-05-18: When adding a new Make target with semantics overlapping an existing one, audit + mirror the existing target's guards

**Trigger**: PR #5b Codex Tier-2 (`61f0101`) — I added `review-commit-by-{codex,claude}` recipes mirroring the structure of `review-plan-by-{codex,claude}` but missed the `test -f "$(PLAN_FILE)"` guard that the plan-review targets already had. Tier-1 self-review missed it; Codex Tier-2 caught it.

**Rule**: When introducing a new Make target whose semantics overlap an existing one (e.g. same arg-pattern, same external CLI invocation, similar input validation), before writing the new recipe READ the existing target's full body and enumerate its guards (`test -n`, `test -f`, `command -v`, etc.). Mirror each guard that applies. Add a comment cross-referencing the source target if useful. Same applies to new commit-review variants of existing plan-review targets, new test fixtures of existing fixtures, etc.

**Status**: Active

---

### 2026-05-18: Commit messages must not claim tests/files exist without verifying

**Trigger**: PR #5c Tier-1 self-review (`c089051`) — my commit message claimed "/simplify wording assertions in tests/test_shared_templates.py still pass (test (d) for 'Claude Code' + 'skip' + 'optional' substrings)" but no such test had been added. The plan explicitly required it (Bucket F test (d)); I assumed I'd already done it and wrote the commit body to match. Tier-1 reviewer caught the lie.

**Rule**: Before claiming in a commit message that a test or file exists, verify it exists. Quick check: `grep -rn "<substring from claim>" tests/` (or the relevant dir). If the grep returns zero hits, either (a) add the missing piece OR (b) reword the commit message to be honest. Never write "test X still passes" without confirming X exists.

**Status**: Active

---

### 2026-05-25: Percent-based trim targets don't transfer between repos with different test surfaces

**Trigger**: Phase 4 of the project-CLAUDE.md hygiene initiative arrived with a ~50% line-count target derived from call-details PR #22 (199→106 lines, -48%). Applied blindly to this repo it would have required trimming sections pinned by `tests/test_triage_byte_identity.py` (6-surface byte-identity) + `tests/test_dogfood_doc_sanity.py` (Two-tier, Cross-session, Self-improvement, plan-consistency presence) — which means also editing `shared/CLAUDE.md.tmpl` and the tests, propagating to every downstream `dev-project-setup` consumer. Out of scope for a hygiene pass. Surfaced via pre-edit audit before any files were touched.

**Rule**: Before adopting a percent-based trim target from a prior PR, enumerate which sections in the new repo are pinned by tests (or other load-bearing invariants like template-mirroring contracts). The trim ceiling is the unpinned section set, not the aspirational percent. If the unpinned set falls short of the target, surface that to the user with three options — (a) extend scope to template + tests + downstream surface, (b) accept the smaller trim, (c) skip the trim — rather than picking unilaterally or stealth-breaking a test. Auto-mode "make the reasonable call" does not extend to load-bearing constraints the source prompt didn't account for.

**Status**: Active

---

### 2026-05-19: Tier-1 commit review must use the SAME AI (fresh subagent), not the cross-AI

**Trigger**: PR #6 Impl Step 2-3 — I used `make review-commit-by-codex` for Tier-1 (Codex reviewing Claude's commits). User push-back: *"our rule is tier 1 commit review should be done by the same AI but just new subagent, no? only tier 2 review we have cross review"*. The rule was implicit in the workflow (same-author = same-AI Tier-1; Tier-2 = cross-AI via GitHub bots) but CLAUDE.md's "or" wording made both targets look equivalent. I'd separately defaulted to Codex because the `review-commit-by-claude` make target hits the `--permission-mode plan` exit-declined bug (BACKLOG f).

**Rule**: When the implementer is Claude (this session), Tier-1 commit review uses a **fresh Claude subagent**, not Codex. Invoke via the `Agent` tool with `subagent_type: general-purpose` (or `claude` default) and pass the canonical Tier-1 prompt from `shared/Makefile.review.tmpl`'s `tier1_prompt` macro. The Codex Tier-1 target (`make review-commit-by-codex`) is for when Codex is the implementer (symmetric). Cross-AI review only fires at Tier-2 (claude[bot] + chatgpt-codex-connector on PR open / draft→ready). If `review-commit-by-claude` is broken (e.g. the plan-mode bug), use the Agent-tool subagent as the immediate workaround; fix the make target separately. CLAUDE.md's current "or" wording for the Tier-1 targets is too permissive — tightening it to explicit same-AI/cross-AI split is tracked in BACKLOG.md as a PR #6 follow-up.

**Status**: Active

---

### 2026-05-27: Over-defensive folds can introduce new imp-3 findings

**Trigger**: PR #10 iter-3 F2 added `-C / --sandbox` flags to `codex exec resume` "defensively"; iter-4 F2 verified empirically that the CLI rejects them (`unexpected argument`) — resume INHERITS those settings, so the defensive add would have shipped a broken Bucket F. Surfaced in PR #10's `## Lessons surfaced`; promoted here 2026-05-29 per the meta-plan (`what-else-i-want-majestic-rain.md`) side-workstream item 1.

**Rule**: When folding a "this might be unsafe" finding, prefer adding a *verification step* (test, gate, runtime check) over adding *defensive command-line flags or guards you haven't tested*. Defensive additions assert a contract that may not exist; verification steps probe what's actually true. Corollary (the meta-plan's own evidence — imp-3 trajectory 2→1→3→3→1→2→3): over-defensive folds are a recurring driver of imp-3 regressions across review iters — when an iter's imp-3 count rises right after a defensive fold, suspect the fold.

**Status**: Active

## Archived

(No archived lessons yet. Move solved/obsolete "Active" entries here once the pattern hasn't fired for 3+ sessions.)
