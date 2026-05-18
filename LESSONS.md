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

## Archived

(No archived lessons yet. Move solved/obsolete "Active" entries here once the pattern hasn't fired for 3+ sessions.)
