# Contributing to dev-project-setup

The per-change workflow for the skill repo itself.

---

## One-time setup (fresh clone)

```bash
cd /path/to/dev-project-for-non-developers
make install        # creates venv if missing, installs deps
make install-hooks  # registers pre-commit + pre-push git hooks (requires .git/)
make doctor         # verifies local prereqs are present
```

Prereqs are documented in [docs/usage.md](docs/usage.md) — `python3.12`,
`make`, `git`, network access to PyPI; optional `claude` / `codex` CLIs
for the local review targets.

### Codex CLI (required for `make review-plan-by-codex` and `make review-commit-by-codex`)

```bash
# Install (see https://developers.openai.com/codex):
brew install --cask codex     # or per the official docs

# Log in (one-time; opens browser):
codex login

# Verify:
command -v codex && codex --version
```

### Claude CLI (required for `make review-plan-by-claude`, `make review-commit-by-claude`, and `make review-plan-consistency-by-claude`)

```bash
# Install:
npm install -g @anthropic-ai/claude-code   # or per the official docs

# Log in:
claude login

# Verify:
command -v claude && claude --version
```

If either CLI is unavailable, the corresponding `make review-*-by-*`
target exits cleanly with an install hint.

### GitHub Actions secret for `claude[bot]` PR review (required)

This repo emits `claude-review.yml` (`--github-review=claude` mode). The
workflow needs an OAuth token to post reviews — without the secret, the
workflow runs but the action exits with an auth failure.

One-time setup:

1. **Install the Claude Code GitHub App** on your account:
   https://github.com/apps/claude
2. **Generate the OAuth token** (opens browser):
   ```bash
   claude setup-token
   ```
3. **Add it as a repo secret**:
   `Settings → Secrets and variables → Actions → New repository secret`
   - Name: `CLAUDE_CODE_OAUTH_TOKEN`
   - Value: paste the token

The same token works across multiple repos (per-user, not per-repo).
Generating a new token does not invalidate older ones.

---

## Pre-coding: regression safety + outcome measurement

Before writing code for any task, state two things up front (in the plan, or in the first response if there's no plan):

1. **Regression safety.** What's auto-testable (unit / integration / CI) and what isn't (UI feel, visual layout, AI output quality, onboarding flow). For non-auto-testable parts, name the manual check (smoke walk, screenshot diff, manual checklist). "No tests needed" is a valid answer when you explain why (e.g., one-off script, throwaway).

2. **Outcome measurement.** For user-facing features: name the metric that says it worked + the log/event that captures it. For internal/dev/bugfix/refactor tasks: explicitly say "no business metric applies — internal change" so we know it was considered, not forgotten.

Both go at the *start* of the task, not after the code is written.

---

## Per-change checklist

1. **Plan**: substantive change → `docs/plans/YYYY-MM-DD-<slug>.md` plus
   the bidirectional review loop. Trivial change → skip planning.
   Between iterations: fold findings, run `make review-plan-consistency-by-claude`, then `make loop-ack` (re-stamps the integrity hash before the next review). `make loop-status` shows convergence state; `make loop-reset` discards loop state for the plan.
   For multi-day or cross-file plans, run the fact-check pre-pass as **iter 0.5** (before the first main review):
   ```bash
   make review-plan-fact-check-by-codex PLAN_FILE=docs/plans/<file>.md
   ```
   This validates that every file path, symbol, and Makefile target cited in the plan actually exists, catching fact-drift before it pollutes the main review.

2. **Workspace check**:
   ```bash
   git status --short
   ```

3. **Sync**:
   ```bash
   git pull --ff-only
   ```

4. **Verify baseline**:
   ```bash
   make check
   ```

5. **Branch**:
   ```bash
   git checkout -b feat/my-thing
   ```

6. **Implement**. State the Pre-coding contract first (regression safety + outcome measurement — see the section above). Tests for new helpers, defensive cases for new public APIs.

7. **Auto-fix + verify**:
   ```bash
   make format
   make check
   ```

8. **Commit focused units**:
   - One logical change per commit. Imperative title, body explaining "why".
   - **Do NOT** `git add .` — pick files explicitly.
   - **For substantive PRs, run Tier-1 review on the commit you just made (before push)**:
     ```bash
     make review-commit-by-claude PLAN_FILE=docs/plans/<active>.md  # use review-commit-by-codex when Codex implemented
     ```
     Tier-1 uses the **same AI as the implementer** (Claude→Claude, Codex→Codex); cross-AI review is Tier-2's job.
     Pass `PLAN_FILE=` when you want the reviewer to check plan-impl drift against a specific plan; omit for code-correctness-only review (see `CLAUDE.md` Tier-1 section for the dual-variant subagent path).
     Triage findings per the (a/b/c/d) framework in `CLAUDE.md` (with the four-questions check).
     - **Blockers**: fix and either `git commit --amend` (if not yet pushed) or create a follow-up focused commit. Then **rerun `make review-commit-by-*`** on the corrected commit until no importance-3 findings remain. Then `make check`. THEN push.
     - **MANDATED: append the Tier-1-suggested impl-log row to the plan's `## Implementation log` section before push**. The reviewer outputs a single markdown table row in the documented format (`| short-sha | what landed | deviations | issues |`). Paste it into your plan file, then create a SEPARATE docs-only commit (e.g. `git commit -m "Append impl-log row for <short-sha>"`). The docs-only commit qualifies as a trivial diff and is exempt from Tier-1 (no recursion). Amending the reviewed commit to include the row would change the SHA and invalidate the audit trail — the docs-only pattern keeps both stable. For commits that don't warrant a row (e.g. trivial-diff Tier-1-skips), mark `N/A` in the impl-log instead.
     - **Optional `/simplify` pass** (Claude Code sessions only — not available in Codex CLI or generic terminals; skip if unavailable). Substantive PRs only: >200 lines OR multi-commit OR multiple iter folds. After Tier-1 fold + before push, run `/simplify` to catch reuse / dead code / cruft accumulated across folds. For trivial diffs OR non-Claude-Code sessions, skip — or do a manual cruft pass if you suspect accumulation.
     - For trivial diffs (typo, single-line refactor): skip Tier-1 entirely; rely on Tier-2 + `make check`. Docs-only impl-log commits also qualify as trivial and don't loop back through Tier-1.

9. **Push** and open a draft PR:
   ```bash
   git push -u origin <branch>
   gh pr create --draft
   ```

10. **Watch CI** — merge only when green. PR #1 is the bootstrap exception:
    its workflow files are part of what it ships, so CI may skip on PR #1
    itself. From PR #2 onward, CI runs.

---

## Branch naming

```
feat/<thing>
fix/<thing>
docs/<thing>
refactor/<thing>
```

---

## Emergency override

`git push --no-verify` skips the pre-push pytest hook. Use only in a real
emergency. Add a note in the commit message explaining why.

Routine "tests are slow / I'll fix it later" is not legitimate use.

---

## Skill repo specifics

When editing the skill itself, mind these invariants:

- `bootstrap.py` is Python 3.6-compatible. The shim runs version + jinja2
  checks BEFORE importing 3.12-syntax modules in `bootstrap_lib/`.
- `bootstrap_lib/_flags.py` is the single source of truth for argparse.
  Don't hand-mirror flags in `bootstrap.py`.
- Path-safety runs at TWO layers (renderer + CLI). Both must remain.
- The "Triaging review findings" rule is byte-identical across
  `shared/CLAUDE.md.tmpl` / `shared/AGENTS.md.tmpl` /
  `shared/docs-plans-README.md.tmpl` AND the dogfood `CLAUDE.md` /
  `AGENTS.md`. Drift fails `tests/test_dogfood_doc_sanity.py`.
- Five selftest overlap checks (`.editorconfig`,
  `.github/workflows/claude-review.yml`,
  `.github/pull_request_template.md`, `docs/plans/README.md`, and the
  Makefile review-section block) diff rendered templates against the
  committed dogfood copies. If you change a selftested template, the
  dogfood file must update in lockstep — and vice versa.

---

## Triaging review findings (full discipline)

The (a/b/c/d) options and the four-questions check live in `CLAUDE.md` —
always-on session context. This section carries the verbose triage
discipline that doesn't need to be always-on: imp-3 calibration and the
plateau rule.

**Calibration**: imp-3 should mean "if we ship without this, the PR doesn't work" — not "if we shipped this, an adversarial test could fail." Imp-3 ≠ "would be more correct." When in doubt about whether a finding is a real blocker, ask: *can the PR ship with a working `make check` and a green smoke walk without this change?* If yes, it's at most imp-2, and probably (b) or (c).

**No strict iteration cap** — but watch the trajectory. If imp-3 count plateaus at 1-2 across 3 consecutive iterations and the findings are increasingly narrow edge cases, the loop is at diminishing returns; surface the remaining items to the human-approval gate with explicit framing ("these are real but deferrable; ship plan + fold during implementation"). The human decides whether to continue iterating or accept.

**Second trigger — same-class regeneration.** Even when findings are *not* narrow edge cases: if importance-3 findings keep appearing past ~iteration 5 but cluster in **one artifact or theme** (e.g. the deploy runbook, or CLI/API signatures), that is not convergence — it is the wrong verification tool for that artifact. Stop folding; extract the artifact and verify by execution (`shellcheck` / `--dry-run` / `--help` / the fact-check pre-pass), or escalate to the human-approval gate. Signals: findings concentrate in one section; findings are about syntax / flags / exit-codes / signatures rather than design. (Distinct from the architectural-blocker split below, which is about *design* holes; this is about *artifact-class* mismatch.)

**Architectural-blocker split (advisory, not a cap)**: distinct from the plateau rule above. If a review surfaces a *new architectural blocker* — not a narrow edge case, but a design hole that keeps regenerating importance-3 findings — at **iter ≥3**, consider splitting the PR rather than continuing to fold: carve the blocked piece into a follow-up (with the iter-1..N findings as its starting requirements) and ship the unblocked remainder. PR #10 ran to 7 iterations without plateauing because two adopt-engine blockers surfaced late and kept regenerating imp-3s; splitting at iter 3 instead of iter 6 would have saved ~3 iterations. This is a judgment call for the human-approval gate, not an automatic trigger.

**Keep executable runbooks out of the plan.** A plan describes deploy/rollback at *intent* fidelity: the sequence of steps, what is in scope, ordering constraints that matter for safety (e.g. "restore the DB backup *before* re-rendering"), and which failure modes the operator must verify. It does **not** embed line-level executable scripts — bash with traps / `set -euo pipefail`, `awk`/`grep` output parsing, DB backup/restore, or internal-API heredocs. Executable artifacts belong in a real file (`scripts/deploy/<task>.sh`) and are verified by *execution* — `shellcheck` (or a documented equivalent; add it to `make doctor` when shell deploy scripts are introduced), a `--dry-run`, and `--help` / source checks for every CLI flag and API signature — then reviewed as code (Tier-1). Static cross-review converges on design but not on executable correctness; trying to make a runbook line-perfect in the plan body regenerates importance-3 findings every iteration (the post-2b doc-layout loop: 19 iterations, ~30 of 40 blockers were CLI/bash mechanics). **Boundary:** ordering / scope / which-failure-to-check → plan; syntax / flags / quoting / exact signatures → script.

---

## Tier-1 review — prompt template for in-session subagents

Claude Code sessions (only) can run Tier-1 via a fresh `general-purpose` subagent instead of the Makefile target — useful when you want to ask follow-up questions interactively. Substitute your commit SHA for `<SHA>` (get it from `git log -1 --pretty=%H`). **Pick ONE variant** matching your situation:

### Variant A — If you have a plan to check drift against

Substitute BOTH `<SHA>` and `<PLAN_FILE>` (your active plan path, e.g. `docs/plans/2026-05-17-foo.md`):

> "Review commit <SHA> on this branch. Run 'git log -1 --stat <SHA>' and 'git show <SHA>' to see the diff, then VERIFY against the actual codebase — not just the diff. This is a Tier-1 code review. Focus on: tests that pass for the wrong reason, plan-impl drift (does the commit match what the plan says?), missing-await / sys.path / module-init bugs that the diff alone cannot reveal, contract bugs the author may have missed (function callers? config consumers?), missing edge-case coverage, semantic-boundary mismatches between docs and code, regressions in nearby code touched by the commit's imports/exports. Check this commit against <PLAN_FILE>'s plan body; flag any deviation as plan-impl drift findings. Return findings ordered by importance (3=blocker, 2=improvement, 1=polish). For each finding: file:line, importance, what is wrong, why it matters, concrete suggested fix, AND identify any other files where the same fix should apply for consistency. Do NOT edit files. If there are no importance-3 findings, say so explicitly. ALSO output a suggested implementation-log row for this commit. Use this exact table-row shape (no backticks; the literal pipe characters and angle-bracket placeholders): | short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |. The driver will append this to the plan's Implementation log section."

### Variant B — If you have no plan binding (code-correctness only)

Substitute only `<SHA>`. The macro emits the unbound prompt; reviewer will limit findings to code-correctness and won't infer a plan file by mtime:

> "Review commit <SHA> on this branch. Run 'git log -1 --stat <SHA>' and 'git show <SHA>' to see the diff, then VERIFY against the actual codebase — not just the diff. This is a Tier-1 code review. Focus on: tests that pass for the wrong reason, plan-impl drift (does the commit match what the plan says?), missing-await / sys.path / module-init bugs that the diff alone cannot reveal, contract bugs the author may have missed (function callers? config consumers?), missing edge-case coverage, semantic-boundary mismatches between docs and code, regressions in nearby code touched by the commit's imports/exports. No plan binding; limit findings to code-correctness, do not infer a plan file by mtime. Return findings ordered by importance (3=blocker, 2=improvement, 1=polish). For each finding: file:line, importance, what is wrong, why it matters, concrete suggested fix, AND identify any other files where the same fix should apply for consistency. Do NOT edit files. If there are no importance-3 findings, say so explicitly. ALSO output a suggested implementation-log row for this commit. Use this exact table-row shape (no backticks; the literal pipe characters and angle-bracket placeholders): | short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |. The driver will append this to the plan's Implementation log section."

(For non-Claude-Code sessions, just run `make review-commit-by-claude PLAN_FILE=docs/plans/<active>.md` — or `make review-commit-by-codex PLAN_FILE=...` when Codex is the implementer; Tier-1 uses the same AI as the implementer, cross-AI review is Tier-2's job. The Makefile passes through `PLAN_FILE` to the same macro. Omit `PLAN_FILE` for the unbound variant.)
