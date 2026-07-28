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
| Acknowledge a legitimate fold: re-stamp the integrity hash | `make loop-ack PLAN_FILE=docs/plans/<file>.md` |
| Reset loop state (removes hash/consistency/snapshot artifacts) | `make loop-reset PLAN_FILE=docs/plans/<file>.md` |
| Check convergence status of the plan-review loop | `make loop-status PLAN_FILE=docs/plans/<file>.md` |

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

For substantive plans (multi-day work, cross-cutting changes, high-risk), write the plan to `docs/plans/YYYY-MM-DD-<slug>.md` rather than chat, then run the **cross-direction** plan review each integer iteration — `make review-plan-by-codex` for a Claude-authored plan, `make review-plan-by-claude` for a Codex-authored plan (run only the cross direction, **not both**; see the Commands table) — and stop when no importance-3 findings remain. See `docs/plans/README.md` for the filename convention, the when-to-stop rule, and the `make review-plan-consistency-by-claude` self-check cadence (numbered `N.5`, between integer iterations).

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

- **Tier-1 (after each focused commit, before push)**: `make review-commit-by-claude` or `make review-commit-by-codex` — use the same AI as the implementer. Catches plan-impl drift, tests-passing-for-wrong-reason, contracts the author missed.
- **Tier-2 (after push)**: `claude[bot]` (via `.github/workflows/claude-review.yml`) + `chatgpt-codex-connector[bot]` auto-fire on PR open / draft→ready; re-trigger via `@claude review this` or `@codex review` comments. Catches the "could only be discovered by running" class.

Both feed the same (a/b/c/d) triage rule above. Full pattern in `CONTRIBUTING.md`.

## Launching reviews from plan mode (`/dev-review`)

To run a review from inside plan mode — without an exit-plan-mode / return cycle — invoke the **`/dev-review`** slash command, Claude's front-end to the `make review` dispatcher:

- `/dev-review commit` — Tier-1 review of the latest commit. The session IS the implementer, so it dispatches `make review MODE=commit ACTOR=claude` directly (same-AI Tier-1); no question.
- `/dev-review plan [PLAN_FILE] [ITERATION]` — the plan's author may be Claude or Codex, so the command `AskUserQuestion`s the author first (never a silent default that could mis-route a Codex-authored plan), then dispatches the correct cross-direction review.

You never pick the reviewer or list both review directions — `make review` is the single source of dispatch truth. Do **not** rely on `export REVIEWER=…`: each Bash tool call is a fresh shell, so an export there won't reach a later `make` (the command passes `ACTOR=` inline instead). `REVIEWER` is a convenience for a hand-run `make review` in a single terminal only.

## Cross-session state recovery

If you're starting a fresh session, just resumed after compaction, or are uncertain whether work X is already done: run `make status` BEFORE proposing changes. It synthesizes git history, open PRs, the active plan's iteration + implementation log tails, active lessons (`LESSONS.md`), local repo state, and tool availability — cheap to run, and it prevents proposing work that's already shipped. If `docs/plans/` holds multiple plan files, pass `make status PLAN_FILE=docs/plans/<active>.md` to override the mtime auto-detect.

## Pre-coding: regression safety + outcome measurement

Before writing code, state (1) **regression safety** — auto-testable vs manual check — and (2) **outcome measurement** — metric for user-facing, or "no business metric — internal change" for refactors/docs. Both go at the *start* of the task. Full wording in `CONTRIBUTING.md`'s "Pre-coding" section.

## Self-improvement loop (LESSONS.md)

At session start: read `LESSONS.md` "Active" section and apply the rules. In a **writable implementation session** (you're the driver, free to edit files): after any user push-back that changes your approach, OR any Tier-1/2 finding that surfaced a new mistake-class, append an entry to `LESSONS.md` "Active" directly — format `### YYYY-MM-DD: <one-line mistake>` + **Trigger** + **Rule** + **Status**: Active — and commit it alongside the implementation. In a **read-only review session** (you're a reviewer, or told "Do NOT edit files"): do NOT append to `LESSONS.md`; propose the lesson in your review output instead (see `AGENTS.md` for the reviewer-side protocol). Promotion to `CLAUDE.md` (rare; FUNDAMENTAL shifts only) + archival cadence: see `LESSONS.md` "How to use this file".

## Mandatory human-approval gate

After the loop converges and BEFORE any `git add` / `git commit`: (1) post a final-plan summary, (2) wait for **explicit user approval**, (3) fold any changes and re-show, (4) commit only on **approve**. Canonical wording: `docs/plans/README.md` step 3.

## Focused commits

One logical change per commit, imperative title, body explaining "why". **Never** `git add .` or `git add -A` — pick files explicitly (see `LESSONS.md` 2026-05-17 `git add -A` entry for the session-state leak this prevents). Per-change checklist: `CONTRIBUTING.md`.

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
  `apply_pipeline._cli_layer_path_safety`, which `cli.main` calls on the whole
  planned set. Both must remain in place — the CLI-layer check is the actual
  safety boundary (renderer-layer can be monkey-patched), and what must survive
  is the CALL in `cli.main`, not merely the function's existence.
- The "Triaging review findings" rule is byte-identical across three
  templates and three dogfood docs. Drift fails the dogfood test.
