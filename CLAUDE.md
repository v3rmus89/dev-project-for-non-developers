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

When you receive a Codex review (in Claude Code) or a Claude review (in Codex), do **NOT fold every finding by default**. The loop converges faster — and produces a tighter plan — when each finding is triaged. For each finding decide:

- **(a) Fold now** — the plan is wrong, contradictory, or would produce a broken implementation without this change. Fold into the plan body. Document in the evidence table.
- **(b) Park to BACKLOG** — the finding is real and worth fixing, but deferrable. Add an entry to `BACKLOG.md` with an explicit trigger (e.g. "fix when first user reports stale `.git/hooks/` after skill repo move"). Note in the evidence table as `parked: <reason>`.
- **(c) Reject** — the finding is stylistic, out-of-scope for this PR, or implementation-review territory (will be caught during code review of the implementation PR, not now). Note in the evidence table as `rejected: <reason>` so the decision is documented even though no plan-text changes.
- **(d) Surface to human (`ask me`) — use sparingly, only when the change is material** — pause folding and surface to the human ONLY when the finding would materially change the PR's user-facing surface: a documented CLI flag being removed/renamed/added, a deliverable being dropped or expanded, the safety/risk model shifting in a way the user might disagree with. **Default is NOT (d)** — for smaller UX choices, reasonable implementation defaults, scope-trim decisions that aren't surprising, decide as (a/b/c) using engineering judgment and surface ALL such autonomous decisions in the end-of-loop final-plan summary (the existing mandatory-human-approval gate). The bar for (d): *if you imagine showing the change to the user 30 seconds before merge, would they be surprised by the decision?* If yes, (d) now. If no, decide and surface in the final summary. Note (d) outcomes in the evidence table as `surfaced: <user's decision>`.

Only (a) folds modify the plan body during the iteration. (b), (c), and (d) still produce evidence-table entries — the decision matters even when no plan text changes. (d) additionally pauses the loop for a human turn before the iteration proceeds. This makes engineering judgment visible to future reviewers and to the implementer.

**Before deciding (a/b/c/d), ask these four questions** — addresses the failure mode where the driver applies the reviewer's suggested fix verbatim without checking whether the fix is the right one:

1. **Is the premise correct?** Does the reviewer actually understand the current state of the code/plan, or is it inferring from incomplete info? Spot-check the reviewer's claim against the file it cites. If wrong → (c) reject the imp-3 framing.
2. **Is the suggested fix the best fix, or just *a* fix?** What else solves the same problem? Often there's a smaller / more localized fix the reviewer didn't see. If the reviewer's fix introduces complexity the alternative doesn't → use the alternative.
3. **What else does this finding imply?** If the bug is X, are there *other* instances of X in the plan you should audit while you're here? Same shape as the reviewer's own "where else does this affect" instruction — apply it to yourself.
4. **Does folding introduce a contradiction with another section of the plan?** Re-read the sections the fold touches before saving. (The `make review-plan-consistency-by-claude` target does this systematically — run it after every fold.)

These four questions add ~30 seconds per finding. They catch the failure mode where the driver folds in the suggested fix only to find the reviewer was extrapolating, OR the fix introduces a new contradiction the next iter has to catch.

**Calibration**: imp-3 should mean "if we ship without this, the PR doesn't work" — not "if we shipped this, an adversarial test could fail." Imp-3 ≠ "would be more correct." When in doubt about whether a finding is a real blocker, ask: *can the PR ship with a working `make check` and a green smoke walk without this change?* If yes, it's at most imp-2, and probably (b) or (c).

**No strict iteration cap** — but watch the trajectory. If imp-3 count plateaus at 1-2 across 3 consecutive iterations and the findings are increasingly narrow edge cases, the loop is at diminishing returns; surface the remaining items to the human-approval gate with explicit framing ("these are real but deferrable; ship plan + fold during implementation"). The human decides whether to continue iterating or accept.

## Two-tier code review

For substantive implementation PRs (multi-commit / cross-cutting), use BOTH tiers; neither catches what the other does.

- **Tier-1 (after each focused commit, before push)**: `make review-commit-by-claude` or `make review-commit-by-codex`. Catches plan-impl drift, tests-passing-for-wrong-reason, contracts the author missed.
- **Tier-2 (after push)**: `claude[bot]` auto-fires on PR open / draft→ready via `.github/workflows/claude-review.yml`. Re-trigger after subsequent pushes by commenting `@claude review this` on the PR. Catches "could only be discovered by running" class. (Codex GitHub bot is NOT configured in this project. Retroactively adding it is non-trivial today — see BACKLOG for the planned `--enable-github-review` flag.)

Both feed the same (a/b/c/d) triage rule above (with the four-questions check). Full pattern (prompt template + when-to-skip rules) in `CONTRIBUTING.md`.

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
