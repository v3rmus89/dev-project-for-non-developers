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

### 2026-06-13: A gate keyed on the analyze-phase recommendation can be invalidated by the interactive decide phase

**Trigger**: PR #48 (adopt-mode hardening) Tier-2 codex P2 — Bucket B decided whether to emit the standalone `Makefile.review` (and its `include` hint) from the Makefile's *recommendation* (`SKIP`), computed before `_interactive_decide`. But adopt prompts the owner on their own Makefile, and `[o]verwrite` turns the active Makefile into the skill's (which inlines the fragment) — leaving the standalone redundant and the hint duplicate-target-inducing. The gate read pre-decision state to decide a post-decision fact.

**Rule**: In the adopt pipeline (analyze → report → **decide** → plan → apply), any branch whose correctness depends on a file's FINAL action must read the *decided* plan (or be re-checked after `_interactive_decide`), never the analyze-phase recommendation. Recommendations are owner-overridable defaults ([r]/[s]/[n]/[o]); only the decided policy is load-bearing for what gets written. (Paired note: claude[bot]'s suggested sync-assertion cited a non-existent `analysis.policy` field — the 2026-05-17 "verify the reviewer's suggested fix" lesson holding; it was addressed by a shared helper instead.)

**Status**: Active

---

### 2026-06-09: A plan that proposes Makefile-embedded prompt text must keep that text shell-safe

**Trigger**: Plan-review-loop guardrails plan, iter-1 FN1 — the C1 calibration text proposed for the plan-review prompt used backticks around `make check`, which become shell command substitution once the prompt is built as a double-quoted Makefile arg (`@PROMPT="…"`). The existing no-backtick regression test guarded only the Tier-1 commit-review prompt, so the plan-review prompts were an unguarded gap and the backticks slipped into the plan.

**Rule**: When a plan proposes text that will be embedded in a double-quoted shell/Makefile argument (review prompts, recipe strings), keep it shell-safe — no backticks, no `$(`, no literal double-quotes; use single quotes for inner quoting. Extend the shell-safety regression test to cover EVERY such prompt, not only the one you are touching.

**Status**: Active

---

### 2026-06-09: When a rule routes findings to a verifier as a safety net, confirm the verifier actually checks that class

**Trigger**: Same plan, iter-1 FN2 — the C1 carve-out down-ranked CLI/API findings to imp-2 on the theory the fact-check pre-pass would catch them, but the verifier marks CLI flags `not_verifiable` and never introspects API signatures. The "safety net" had a hole that would have hidden real feasibility blockers.

**Rule**: Before a rule delegates a class of checks to a tool ("the X pre-pass will catch this"), verify the tool's REAL coverage of that class — run it, read which classes it reports vs marks not-verifiable. If it cannot actually check the class, do not down-rank on its account; keep the dependency at full severity until a verifier that covers it exists.

**Status**: Active

---

### 2026-06-09: When a rule names a verification tool, make sure that tool is in the repo's documented toolchain

**Trigger**: Same plan, iter-2 FN3 — the C2 runbook rule mandated `shellcheck`, which is not installed in this env nor listed in `make doctor`. A rule that names an absent tool recreates the tool-mismatch it exists to prevent.

**Rule**: Before a rule or plan requires a tool, confirm it is in the repo's documented toolchain (`make doctor`), or soften to "tool X (or a documented equivalent), added to doctor when first needed." Do not mandate a tool the project cannot run.

**Status**: Active

---

### 2026-06-01: Don't propagate an operational "must-do" from loosely-worded memory without checking the cited source

**Trigger**: Before the live A/B run I told the user to "quit Codex.app" for a clean codex env, citing `feedback-codex-timeout`. User pushed back ("we discussed it shouldn't be quit"). Checking the sources: `feedback-codex-timeout` is about repo-size *review timeouts*, nothing about the app; the real control (per memory `codex-json-resume-behavior` + LESSONS 2026-05-30) is a connected MCP server's OAuth health — the codex CLI loads MCPs from `~/.codex/config`, independent of the desktop app. A loose parenthetical observation ("env flaky while Codex.app was running") had hardened into a stated requirement via a mis-citation.

**Rule**: Before stating an operational precondition as a requirement, open the memory/source it rests on and confirm it actually says that. Correlation in an observation log ("X was running when it broke") is not a verified causal control. When you catch a mis-citation, fix the memory so it can't resurface.

**Status**: Active

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

---

### 2026-05-30: Shim/fake-CLI tests prove recipe branching, not that the REAL CLI accepts the flags

**Trigger**: PR-1 (Bucket F) commit 2 — I copy-pasted the fresh-path `-C`/`--sandbox`/`--color` flags onto the `codex exec resume` invocation. My shim-based smoke test passed (a fake `codex` accepts any argv), but the real `codex exec resume` rejects those flags (`unexpected argument`) because the subcommand's flag set is a strict subset of `codex exec`'s. Tier-1 caught it by running the real CLI. Re-introduced the same class as the 2026-05-27 over-defensive-folds entry.

**Rule**: A fake-CLI shim validates a Makefile recipe's branching and argv *construction*, NOT that the real subcommand *accepts* those flags — subcommands often take a narrower flag set than their parent (`codex exec resume` ⊂ `codex exec`). Before copy-pasting flags from one invocation onto a sibling subcommand, check that subcommand's `--help`, and rely on a live gate (here: the V-13.5 verifier) or a real-CLI smoke to catch rejections. When a shim test covers the branch, also assert the argv *excludes* flags the real subcommand rejects, so the regression cannot silently reappear.

**Status**: Active

---

### 2026-05-30: Env-vs-feature failure classifiers must be calibrated against REAL failure strings

**Trigger**: PR-1 (Bucket F) — the V-13.5 verifier's `looks_like_env_failure` heuristic was written from *imagined* env-error strings (auth / quota / network). The FIRST live run hit a real one it didn't cover: a connected MCP server's expired OAuth token (`TokenRefreshFailed` / `invalid_grant` from a Meta-ads MCP, `mcp.facebook.com`) aborted codex before it emitted `session_meta`. The gate correctly blocked (non-zero, merge-blocking) but mislabelled the environment failure as "probe DID NOT RUN — file a bug" instead of "environment unavailable — rerun".

**Rule**: A heuristic that classifies external-tool failures (env-vs-feature, transient-vs-permanent) can only be calibrated against REAL failure output, not imagined strings. Treat the first live run of such a classifier as calibration data: capture the actual failure text and fold the unmatched env signatures back in. Prefer SPECIFIC machine-error tokens (`invalid_grant`, `TokenRefreshFailed`) over bare words (`connection`, `network`) that false-positive on prose. And note: a connected MCP server is part of the environment — its auth/transport failures are env-unavailable, NOT a bug in the code under test.

**Status**: Active

---

### 2026-05-30: This clone has no pre-commit hook — run `make format` before every commit, not just targeted pytest

**Trigger**: PR-1 re-impl commit `408baad` shipped two rewritten test files that failed `ruff format --check` (caught only later by `make check`, which then halts at `lint` before running tests). I had run targeted `pytest` after the commit, not `make lint`. Investigation: this clone has NO `.git/hooks/pre-commit` and no `core.hooksPath` override (`make install-hooks` was never run here), so the "ruff on commit" hook CLAUDE.md describes does NOT fire — nothing checks lint/format at commit time.

**Rule**: Do not assume the pre-commit hook exists — in this clone it doesn't. Before EACH `git commit`, run `make format` (auto-applies) or at minimum `./venv/bin/ruff format --check . && ./venv/bin/ruff check .`, in addition to the targeted tests. Relying on a final `make check` catches format drift LATE — after intermediate commits have already shipped it, and (no rebase here) you then need an extra style commit to fix forward. Optionally run `make install-hooks` once to close the gap structurally.

**Status**: Active

---

### 2026-06-01: ruff RUF002/RUF003 reject ambiguous unicode (`×`, `…`) in Python comments/docstrings

**Trigger**: PR-2 implementation — `make format` failed three separate times (commits 1, 3, 6's test edits) because I wrote `ACTOR×MODE` (U+00D7 MULTIPLICATION SIGN) and `Other × plan` in test docstrings/comments. ruff's RUF002 (docstring) / RUF003 (comment) flag these as ambiguous vs the ASCII `x`, and they are NOT auto-fixed by `ruff check --fix`, so each one halted `make format` until hand-edited. Cost ~3 extra format round-trips.

**Rule**: In Python comments and docstrings, use ASCII only — `x` not `×`, `...` not `…`, `->` not `→`, `'` not `’`. Markdown/prose files (`.md`, templates) are fine (not linted by ruff). When writing test names/docstrings that describe a cross-product, write `ACTOR x MODE` or `ACTOR-MODE`, never `×`. If `make format` errors with RUF002/RUF003, the fix is a literal ASCII swap (no `--unsafe-fixes` needed).

**Status**: Active

## Archived

(No archived lessons yet. Move solved/obsolete "Active" entries here once the pattern hasn't fired for 3+ sessions.)
