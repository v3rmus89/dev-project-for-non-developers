## Summary

<!-- One or two bullets explaining the why, not the what. -->

## Test plan

- [ ] `make check` clean locally
- [ ] Smoke walked if behaviour / UI / API / data shape changed

## Plan-review loop

<!--
Pick the case that applies. Delete the others.

  - **Plan PR** (adds or updates a file under `docs/plans/`): fill in iteration
    count and confirm the stopping rule. Evidence belongs in the plan body's
    Iteration log + Evidence table, not here.
  - **Implementation PR** (references an already-merged plan): link the plan
    and note which sections this PR implements.
  - **Neither** (typo / docs touch-up / hotfix): delete this whole section.
-->

**Plan PR:**
- [ ] Plan file: `docs/plans/YYYY-MM-DD-<slug>.md`
- [ ] Local plan-review iterations run: ___ (codex direction) / ___ (claude direction)
- [ ] Stopping rule met: no remaining importance-3 findings; 1/2 findings folded or accepted in the plan body

**Implementation PR:**
- [ ] References plan: `docs/plans/YYYY-MM-DD-<slug>.md`
- [ ] Sections implemented in this PR: ___


## AI-reviewer checklist (advisory, not blocking)

The reviewers below run automatically on every PR. Tick "triaged" once you've
read their comments — OR tick "waived" with a one-line reason if a reviewer
didn't run (token outage, fork PR without secrets, integration disabled, etc.).
The real gates are green CI + green local `make check` + the plan-review-loop
stopping rule.

- [ ] `claude[bot]` (from `.github/workflows/claude-review.yml`) — triaged / waived (reason: ___)

If a reviewer surfaces an importance-3 issue while it IS running, fold it
before merging.

