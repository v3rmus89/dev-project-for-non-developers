# AGENTS.md — guidance for AI reviewers

Codex's GitHub review (and other AI reviewers) read this file for repo-specific
guidance. **Keep it concise** — too many rules dilute the signal each individual
rule carries.

This repo is `dev-project-for-non-developers` — the skill itself
(`dev-project-setup`). Python 3.12, Jinja2 templates, no runtime
dependencies beyond `jinja2` + `pyyaml`. All non-trivial logic is in
`bootstrap_lib/`.

## What to flag with high confidence

### Safety-contract regressions

The skill's safety contract — `--dry-run` default, atomic writes,
crash-safe restore — is the load-bearing guarantee. Flag anything that:

- Lets `--dry-run` / `--diff` touch the filesystem.
- Skips writing the restore manifest before the first apply write.
- Lets restore clobber a user edit (any path where `current SHA ≠ sha256_after`
  AND `current SHA ≠ sha256_before` should SKIP, not write back).
- Removes path-safety validation at the renderer OR CLI layer (two-tier
  defense is intentional — closes iter-7 / iter-8 findings).
- Re-introduces the removed `--install-hooks` bootstrap flag without
  fixing the underlying dual-venv problem first (it was removed in iter-16).

### Template drift

- Every `${{ ... }}` GitHub Actions token in any `.tmpl` MUST be wrapped in
  `{% raw %}...{% endraw %}`. `StrictUndefined` will raise `UndefinedError`
  otherwise.
- `bootstrap_lib/_flags.py` is the single source of truth for the shim's
  argparse AND `cli.py`'s argparse. Don't hand-mirror flags in two places.
- The "Triaging review findings" rule is byte-identical across
  `CLAUDE.md.tmpl` / `AGENTS.md.tmpl` / `docs-plans-README.md.tmpl` AND
  their dogfood counterparts at the skill repo root. Drift fails
  `tests/test_dogfood_doc_sanity.py`'s triage-rule presence scan.

### Selftest invariants

`tests/test_selftest_overlap.py` diffs 5 deterministic renderings against
the skill repo's hand-written copies. Adding a substitution variable to
any selftested template means updating its render context in the test;
silent drift fails the test.

## What NOT to flag

- Style nits — `make format` (ruff) handles those automatically.
- Items explicitly parked in `BACKLOG.md`.
- Direct `--install-hooks` flag — parked, see `BACKLOG.md`.

## Local quality gate

Code must pass `make check`. The same suite runs in CI. If a change wouldn't
pass `make check`, that's a blocker.

## Dispatching reviews (Codex)

To launch a review yourself, call the **`make review`** dispatcher directly — there is no Claude slash command you can invoke (`.claude/commands/*` is a Claude Code feature with no `codex` equivalent):

- `make review MODE=commit ACTOR=codex` — same-AI Tier-1 review of the latest commit (Codex is the implementer).
- `make review MODE=plan ACTOR=codex PLAN_FILE=docs/plans/<file>.md [ITERATION=N]` — cross-direction review of a Codex-authored plan.

Pass `ACTOR=codex` **inline on the same invocation** (or call the explicit `review-commit-by-codex` / `review-plan-by-claude` target). A separate `export REVIEWER=codex` is unreliable — each tool call is a fresh shell, so the export won't reach a later `make`. `REVIEWER` is a convenience for a hand-run `make review` in one interactive terminal only.

## Plan Review Guidance

For files under `docs/plans/`, review the **plan itself**, not code style.
Be skeptical — your job is to surface risks, not to validate the direction.

Flag:

- Unsafe sequencing (step N depends on step N+2)
- Hidden assumptions (claims about repo state, third-party services, or
  subscriptions that aren't verified)
- Missing verification (no acceptance criteria, no test plan)
- Missing rollback / adoption path
- Phases that are too large to land safely
- Unclear ownership or acceptance criteria
- Manual steps that should be automated
- Hidden dependency on subscriptions, API keys, GitHub permissions, or
  local tooling not mentioned in setup
- Contradictions between the plan and current repository state
- Places where the plan says "later" but the dependency is actually
  needed earlier

Treat serious planning risks as **importance 3**.

For each finding return:

- importance score: 1 / 2 / 3 (3 = blocker, 2 = improvement, 1 = polish)
- what is wrong or risky
- why it matters
- concrete suggested change

End with a stop/go verdict: "ready after minor edits" / "needs another
iteration" / "do not implement yet". If there are no importance-3
findings, say so explicitly.

Avoid ordinary code-review nits unless the plan contains code that's
materially wrong. Style nits on plan text are noise.

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

## Cross-session state recovery

If you're starting a fresh session, just resumed after compaction, or are uncertain whether work X is already done: run `make status` BEFORE proposing changes. It synthesizes git history, open PRs, the active plan's iteration + implementation log tails, active lessons (`LESSONS.md`), local repo state, and tool availability — cheap to run, and it prevents proposing work that's already shipped. If `docs/plans/` holds multiple plan files, pass `make status PLAN_FILE=docs/plans/<active>.md` to override the mtime auto-detect.

## Self-improvement loop (LESSONS.md)

At session start: read `LESSONS.md` "Active" section and apply the rules.

This `AGENTS.md` is a **read-only context** for `LESSONS.md` — it is read by automated reviewers and any session told "Do NOT edit files". If you (the reviewer) surface a new mistake-class, propose the lesson in your review output (or the plan's `## Lessons surfaced` section); do NOT edit `LESSONS.md` directly. The driver triages reviewer-proposed lessons in a later writable session — real ones land in `LESSONS.md`, duplicates and project-local noise are rejected.

## Tone

Concise, evidence-based comments win. Avoid suggesting wholesale rewrites; small
targeted fixes are far more useful. If a finding can't be expressed in 1-2
sentences with a clear "do X" or "change Y to Z", consider whether it's
actionable enough to be worth flagging.
