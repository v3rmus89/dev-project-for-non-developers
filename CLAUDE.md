# dev-project-setup — Claude Instructions

## Commands

| Task | Command |
|---|---|
| Install dev deps into venv | `make install` |
| Register git hooks | `make install-hooks` |
| Run tests | `make test` |
| Lint + format-check (CI-equivalent) | `make lint` |
| Auto-fix lint + apply format | `make format` |
| Run all local checks (= CI) | `make check` |
| Check local prereqs | `make doctor` |
| Local Codex review of a plan | `make review-plan-by-codex PLAN_FILE=docs/plans/<file>.md` |
| Local Claude review of a plan | `make review-plan-by-claude PLAN_FILE=docs/plans/<file>.md` |
| Self-check plan for internal contradictions (Tier-1) | `make review-plan-consistency-by-claude PLAN_FILE=docs/plans/<file>.md ITERATION=N` |
| Tier-1 Codex review of the most recent commit | `make review-commit-by-codex` |
| Tier-1 Claude review of the most recent commit | `make review-commit-by-claude` |

The full per-change workflow is in `CONTRIBUTING.md`. Pre-commit hooks
(ruff on commit) and pre-push hooks (pytest on push) fire automatically
once `make install-hooks` is run on a git-initialised clone.

## What this repo is

`dev-project-for-non-developers` (repo name; audience-focused) ships the
`dev-project-setup` skill (action-focused). Bootstrap a working dev
workflow into Python / Node-TS / Go projects. PR #1 ships Python only.

Single source of truth for what's in scope and why:
[docs/plans/2026-05-15-skill-pr1-minimal-python-bootstrap.md](docs/plans/2026-05-15-skill-pr1-minimal-python-bootstrap.md).

## Plan review loop

For substantive plans (multi-day work, cross-cutting changes, high-risk),
write the plan to `docs/plans/YYYY-MM-DD-<slug>.md` rather than chat. Then
run a local bidirectional review:

```bash
make review-plan-by-codex  PLAN_FILE=docs/plans/YYYY-MM-DD-<slug>.md ITERATION=1
make review-plan-by-claude PLAN_FILE=docs/plans/YYYY-MM-DD-<slug>.md ITERATION=1
```

Filename convention: outputs land at
`/tmp/plan-review-<slug>-by-codex-iter-N.md` and `-by-claude-iter-N.md` so
per-reviewer iteration counters stay independent. Read both, revise the
plan, and repeat with `ITERATION=2` / `3` as needed.

**Bootstrap exception**: PR #1's own plan was reviewed via Boxette's
`make review-plan` (the precursor, Codex direction only) because the
bidirectional loop is PART of what PR #1 ships. From PR #2 onward, this
repo's `make review-plan-by-*` targets are the loop.

**When to stop**:

- No importance-3 findings remain, AND
- Remaining 1/2 findings are either folded in or explicitly accepted as
  trade-offs in the plan.

**Pre-next-iter consistency self-check**: between folding an iteration's findings and invoking the next reviewer iteration, run:

```bash
make review-plan-consistency-by-claude PLAN_FILE=docs/plans/YYYY-MM-DD-<slug>.md ITERATION=N
```

(Where N matches the upcoming reviewer iter.) This is a narrow subagent that finds contradictions you may have introduced while folding — much cheaper than letting the next reviewer pass catch them. Fix any reported contradictions before triggering the next Codex/Claude review.

## Triaging review findings

When you receive a Codex review (in Claude Code) or a Claude review (in Codex), do **NOT fold every finding by default** — triage each one:

- **(a) Fold now** — the plan is wrong, contradictory, or would break the implementation; fold into the plan body and document in the evidence table.
- **(b) Park to BACKLOG** — real but deferrable; add a `BACKLOG.md` entry with an explicit trigger, note in the evidence table as `parked: <reason>`.
- **(c) Reject** — stylistic, out-of-scope, or implementation-review territory; note as `rejected: <reason>` so the decision is documented.
- **(d) Surface to human (`ask me`)** — use sparingly, only when the finding would materially change the PR's user-facing surface; otherwise decide (a/b/c) and surface the decision in the end-of-loop final-plan summary.

Only (a) folds modify the plan body during the iteration; (b), (c), and (d) still produce an evidence-table entry — the decision matters even when no plan text changes.

**Before deciding (a/b/c/d), ask these four questions** — they catch the failure mode where the driver folds the reviewer's suggested fix without checking whether it is the right one:

1. **Is the premise correct?** Spot-check the reviewer's claim against the file it cites. If wrong → (c) reject the imp-3 framing.
2. **Is the suggested fix the best fix, or just *a* fix?** Often there is a smaller, more localized fix the reviewer didn't see.
3. **What else does this finding imply?** If the bug is X, audit the plan for other instances of X while you're here.
4. **Does folding introduce a contradiction with another section of the plan?** Re-read the sections the fold touches before saving (`make review-plan-consistency-by-claude` does this systematically).

See `CONTRIBUTING.md` for the full triage discipline: imp-3 calibration and the plateau rule.

## Two-tier code review

For substantive implementation PRs (multi-commit / cross-cutting), use BOTH tiers; neither catches what the other does.

- **Tier-1 (after each focused commit, before push)**: `make review-commit-by-claude` or `make review-commit-by-codex`. Catches plan-impl drift, tests-passing-for-wrong-reason, contracts the author missed.
- **Tier-2 (after push)**: `claude[bot]` auto-fires on PR open / draft→ready via `.github/workflows/claude-review.yml`. Re-trigger after subsequent pushes by commenting `@claude review this` on the PR. Catches "could only be discovered by running" class. (Codex GitHub bot is NOT configured in this project. Retroactively adding it is non-trivial today — see BACKLOG for the planned `--enable-github-review` flag.)

Both feed the same (a/b/c/d) triage rule above (with the four-questions check). Full pattern (prompt template + when-to-skip rules) in `CONTRIBUTING.md`.

## Cross-session state recovery

If you're starting a fresh session, just resumed after compaction, or are uncertain whether work X is already done: run `make status` BEFORE proposing changes. It synthesizes git history (current branch + recent main), open PRs, the active plan's iteration + implementation log tails, active lessons (`LESSONS.md`), local repo state, and tool availability. Cheap to run; prevents the failure mode where the agent proposes work that's already shipped.

If multiple plan files are present in `docs/plans/`, `make status` prints a loud WARN listing the top 3 by mtime — pass `make status PLAN_FILE=docs/plans/<active>.md` when the auto-detect might be wrong.

## Pre-coding: regression safety + outcome measurement

Before writing code for any task, state two things up front (in the plan, or in the first response if there's no plan):

1. **Regression safety.** What's auto-testable (unit / integration / CI) and what isn't (UI feel, visual layout, AI output quality, onboarding flow). For non-auto-testable parts, name the manual check (smoke walk, screenshot diff, manual checklist). "No tests needed" is a valid answer when you explain why (e.g., one-off script, throwaway).

2. **Outcome measurement.** For user-facing features: name the metric that says it worked + the log/event that captures it. For internal/dev/bugfix/refactor tasks: explicitly say "no business metric applies — internal change" so we know it was considered, not forgotten.

Both go at the *start* of the task, not after the code is written.

## Self-improvement loop (LESSONS.md)

At session start: read `LESSONS.md` "Active" section. Apply the rules during this session.

**Writable-session-only append rule** — `AGENTS.md` is read by review-only contexts that explicitly cannot edit files; appending lessons from those contexts would violate the read-only contract:

- **In a writable implementation session** (you're the driver, free to edit files): after ANY user push-back that changes your approach, OR any Tier-1/2 finding that surfaced a new mistake-class, append a new entry to `LESSONS.md` "Active" directly. Format: `### YYYY-MM-DD: <one-line mistake>` + **Trigger** + **Rule** + **Status**: Active. Commit alongside the implementation.
- **In a read-only review session** (you're a reviewer running `make review-plan-by-codex`, `make review-commit-by-claude`, or any session that's been told "Do NOT edit files"): do NOT append to `LESSONS.md`. Instead, propose the lesson in your review output (or in the plan's `## Lessons surfaced` section if reviewing a plan). The driver triages reviewer-proposed lessons in a later writable session: appends real ones to `LESSONS.md`; rejects duplicates or project-local noise.

Promote to `CLAUDE.md` only for FUNDAMENTAL shifts (rare; needs plan-review). Move to `LESSONS.md` "Archived" once the pattern hasn't fired for 3+ sessions OR the underlying problem is solved structurally.

## Mandatory human-approval gate

After the loop converges and BEFORE any `git add` / `git commit`:

1. Post a final-plan summary in chat: Scope, key decisions, anything the
   user should push back on (especially decisions made autonomously during
   folding).
2. Wait for **approve** / **changes: …** / **read full file first**.
3. If "changes": fold them, show the summary again.
4. Only on **approve** proceed to commit + draft PR.

See `docs/plans/README.md` step 3 for the canonical wording.

## Focused commits

Use **focused commits** — one logical change per commit. Imperative title,
body explaining "why". Keep formatting-only commits separate from logic.

```bash
git status
git add path/to/file1 path/to/file2
git commit -m "brief description of what changed"
git push
```

**Do NOT** use `git add .` — it can stage unrelated edits and produces
unfocused commits. Always pick files explicitly.

## Python version

Always use `python3.12` for this repo. The Makefile's `venv` target
invokes `python3.12 -m venv venv` explicitly, so the system `python3`
(which may be 3.9.x on macOS) is not consulted.

## Environment

- Virtualenv at `venv/` — created by `make install`.
- No `.env` file required for the skill itself; bootstrap is a pure CLI.
- Templates live under `languages/python/` (per-language) and `shared/`
  (cross-language). Renderer maps in `bootstrap_lib/render.py`.

## Key implementation invariants

- `bootstrap.py` shim is Python 3.6-compatible. Do NOT add walrus, match,
  or `str | None` union syntax. The shim runs the version check BEFORE
  importing `bootstrap_lib/cli.py` (which uses 3.12 syntax).
- `bootstrap_lib/_flags.py` is the single source of truth for argparse
  flag definitions. Both the shim's `--help` path and `cli.py`'s full
  parser consume it. `tests/test_shim_cli_help_consistency.py` enforces
  byte-equal help output.
- Path-safety runs at two layers: inside `render.render_all` AND inside
  `cli.py`'s apply planning. Both must remain in place — the CLI-layer
  check is the actual safety boundary (renderer-layer can be monkey-patched).
- The "Triaging review findings" rule is byte-identical across three
  templates and three dogfood docs. Drift fails the dogfood test.
