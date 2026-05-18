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

## Cross-session state recovery

If you're starting a fresh session, just resumed after compaction, or are uncertain whether work X is already done: run `make status` BEFORE proposing changes. It synthesizes git history (current branch + recent main), open PRs, the active plan's iteration + implementation log tails, active lessons (`LESSONS.md`), local repo state, and tool availability. Cheap to run; prevents the failure mode where the agent proposes work that's already shipped.

If multiple plan files are present in `docs/plans/`, `make status` prints a loud WARN listing the top 3 by mtime — pass `make status PLAN_FILE=docs/plans/<active>.md` when the auto-detect might be wrong.

## Self-improvement loop (LESSONS.md)

At session start: read `LESSONS.md` "Active" section. Apply the rules during this session.

**Reviewer (you) is a read-only context for `LESSONS.md`**: this `AGENTS.md` is read by automated reviewers (Codex GitHub bot, `make review-plan-by-codex`, `make review-commit-by-claude`, and any session told "Do NOT edit files"). Appending to `LESSONS.md` from such a session would violate the read-only contract.

- **If you (the reviewer) surface a new mistake-class** during a finding: propose the lesson in your review output (or in the plan's `## Lessons surfaced` section if reviewing a plan). The driver triages reviewer-proposed lessons in a later writable session — appends real ones to `LESSONS.md`; rejects duplicates or project-local noise.
- **Do NOT edit `LESSONS.md` directly from a review session.**

(Writable-session drivers append directly per the same instructions in `CLAUDE.md`.)

## Tone

Concise, evidence-based comments win. Avoid suggesting wholesale rewrites; small
targeted fixes are far more useful. If a finding can't be expressed in 1-2
sentences with a clear "do X" or "change Y to Z", consider whether it's
actionable enough to be worth flagging.
