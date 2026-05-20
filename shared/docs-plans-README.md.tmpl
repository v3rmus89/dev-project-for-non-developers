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
   **Between folding an iteration's findings and invoking the next reviewer
   iteration**, run the consistency self-check:
   ```bash
   make review-plan-consistency-by-claude PLAN_FILE=docs/plans/YYYY-MM-DD-<slug>.md ITERATION=N
   ```
   (Where N matches the upcoming reviewer iter.) Fix any contradictions it
   reports before the next Codex/Claude pass — cheaper than letting the
   next reviewer find them.
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

## Plan-file structural convention

Plans grow over iterations. To keep `make status` extraction reliable and
human readers oriented, plan files follow a fixed section order from top
to bottom:

1. `# <Title>` and `## Context` (the immutable scope/rationale)
2. `## Scope` (IN-scope + NOT-in-scope tables)
3. `## Subsystem breakdown` (Buckets A, B, C, …)
4. `## Architecture decisions` / `## Risks + mitigations` / `## Verification` (plus any PR-specific notes such as `## Implementation rollout` for plans that split implementation across multiple impl PRs)
5. `## Iteration log (this plan)` — one row per Codex/Claude review iter
   (and per consistency self-check; e.g. iter 1.5, 2.5, …)
6. `## Evidence table — what was folded and where` — one row per finding
7. `## Implementation log (this PR)` — one row per implementation commit;
   Tier-1 review proposes the row, driver pastes it in a separate
   docs-only commit (see `CONTRIBUTING.md` step 9)
8. `## Lessons surfaced (this PR)` — reviewer-proposed lessons the driver
   triages later (real ones → `LESSONS.md`; duplicates/noise rejected)
9. `## Critical files to read before each iter's review` — last, for
   reviewer onboarding

Sections 5-8 are typed/appended as the loop runs. Reviewers reading the
plan should expect sections 1-4 to be stable per-iter; sections 5-8 grow
monotonically. `make status` tails section 5 (Iteration log) and section
7 (Implementation log) for the active plan in recovery output, with
fence-aware extraction (fenced markdown code blocks that contain example
`## Implementation log` text are skipped — only the top-level real
section matches).

**Bootstrap exception.** A plan that creates the plan-review infrastructure
itself (Phase 2.7 in the source project) necessarily lands its plan + tooling
+ dogfood evidence in one PR — there is no earlier plan-review machinery to
reference. Plans that build on existing infrastructure follow the plan PR →
implementation PR split.

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
