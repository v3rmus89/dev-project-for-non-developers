# Plans

Substantive plans land here as markdown files before implementation.

## When to write a plan here

Use this directory for plans that meet **any** of:

- Estimated >2 days of work
- Cross-cutting change (touches multiple modules)
- New architectural commitment (a new dependency, new pattern, new doc convention)
- High-risk: auth, payments, schema migrations, anything touching real user data

For everything else (typo fixes, one-line refactors, in-chat scratch plans), keep
planning in chat. The plan-review loop overhead exceeds the value for small
changes.

## File naming

```
docs/plans/YYYY-MM-DD-<slug>.md
```

Date is the day the plan was first committed (not the day work starts). Slug is
short, dash-separated, all lowercase.

Plan-review outputs use this convention:

```
/tmp/plan-review-<slug>-by-codex-iter-N.md
/tmp/plan-review-<slug>-by-claude-iter-N.md
```

The `-by-codex-` / `-by-claude-` infix keeps per-reviewer iteration counters
independent.

## Workflow

Two distinct PR types:

- **Plan PR** — adds or updates a file under `docs/plans/`. The PR description
  records the loop convergence (iteration count, evidence table).
- **Implementation PR** — references an already-merged plan. The PR description
  links to `docs/plans/<slug>.md` and lists which sections it implements.

1. Write the plan to `docs/plans/YYYY-MM-DD-<slug>.md`.
2. Run the bidirectional review loop and **triage each finding** (see below):
   ```bash
   make review-plan-by-codex  PLAN_FILE=docs/plans/YYYY-MM-DD-<slug>.md ITERATION=1
   make review-plan-by-claude PLAN_FILE=docs/plans/YYYY-MM-DD-<slug>.md ITERATION=1
   ```
3. **MANDATORY HUMAN-APPROVAL GATE** — after the loop converges and BEFORE
   any `git add` or `git commit`:
   - Post a final-plan summary in chat (Scope + key decisions + anything
     the user should push back on)
   - Wait for the user's explicit **approve** / **changes: …** / **read
     full file first** response
   - If "changes": fold them and re-show the summary
   - Only on **approve** proceed to commit
4. Commit the approved plan on a feature branch and open a draft **plan PR**.
5. After plan approval and merge, **implementation PRs** that reference the
   plan land on subsequent branches.

**Bootstrap exception.** A plan that creates the plan-review infrastructure
itself (Phase 2.7 in the source project) necessarily lands its plan + tooling
+ dogfood evidence in one PR — there is no earlier plan-review machinery to
reference. Plans that build on existing infrastructure follow the plan PR →
implementation PR split.

## Triaging review findings

When you receive a Codex review (in Claude Code) or a Claude review (in Codex), do **NOT fold every finding by default**. The loop converges faster — and produces a tighter plan — when each finding is triaged. For each finding decide:

- **(a) Fold now** — the plan is wrong, contradictory, or would produce a broken implementation without this change. Fold into the plan body. Document in the evidence table.
- **(b) Park to BACKLOG** — the finding is real and worth fixing, but deferrable. Add an entry to `BACKLOG.md` with an explicit trigger (e.g. "fix when first user reports stale `.git/hooks/` after skill repo move"). Note in the evidence table as `parked: <reason>`.
- **(c) Reject** — the finding is stylistic, out-of-scope for this PR, or implementation-review territory (will be caught during code review of the implementation PR, not now). Note in the evidence table as `rejected: <reason>` so the decision is documented even though no plan-text changes.
- **(d) Surface to human (`ask me`) — use sparingly, only when the change is material** — pause folding and surface to the human ONLY when the finding would materially change the PR's user-facing surface: a documented CLI flag being removed/renamed/added, a deliverable being dropped or expanded, the safety/risk model shifting in a way the user might disagree with. **Default is NOT (d)** — for smaller UX choices, reasonable implementation defaults, scope-trim decisions that aren't surprising, decide as (a/b/c) using engineering judgment and surface ALL such autonomous decisions in the end-of-loop final-plan summary (the existing mandatory-human-approval gate). The bar for (d): *if you imagine showing the change to the user 30 seconds before merge, would they be surprised by the decision?* If yes, (d) now. If no, decide and surface in the final summary. Note (d) outcomes in the evidence table as `surfaced: <user's decision>`.

Only (a) folds modify the plan body during the iteration. (b), (c), and (d) still produce evidence-table entries — the decision matters even when no plan text changes. (d) additionally pauses the loop for a human turn before the iteration proceeds. This makes engineering judgment visible to future reviewers and to the implementer.

**Calibration**: imp-3 should mean "if we ship without this, the PR doesn't work" — not "if we shipped this, an adversarial test could fail." Imp-3 ≠ "would be more correct." When in doubt about whether a finding is a real blocker, ask: *can the PR ship with a working `make check` and a green smoke walk without this change?* If yes, it's at most imp-2, and probably (b) or (c).

**No strict iteration cap** — but watch the trajectory. If imp-3 count plateaus at 1-2 across 3 consecutive iterations and the findings are increasingly narrow edge cases, the loop is at diminishing returns; surface the remaining items to the human-approval gate with explicit framing ("these are real but deferrable; ship plan + fold during implementation"). The human decides whether to continue iterating or accept.

## Stopping the loop

Stop when **both** are true:

- No importance-3 (blocker) findings remain
- Remaining 1/2 findings are either folded in or explicitly accepted as
  trade-offs in the plan

Suggested iteration counts:

| Plan size | Reviews |
|---|---|
| Small (1 day, single module) | 1 |
| Medium (2–4 days, cross-cutting) | 2 |
| Large / high-risk | 3 |
| 4th iteration | Only if iteration 3 still finds importance-3 issues |

**Do not iterate as a ritual.** Stop the moment the rule is met.

## Why this directory exists

Plans become institutional memory. Future-you (and future Claude/Codex sessions)
read `docs/plans/` to understand why decisions were made. The version-controlled
markdown is more durable than chat history.

See also: `CLAUDE.md` ("Plan review loop"), `AGENTS.md` ("Plan Review Guidance"),
`Makefile` (`review-plan-by-codex` / `review-plan-by-claude` targets).
