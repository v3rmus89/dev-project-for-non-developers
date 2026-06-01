---
name: dev-review
description: Launch the correct review from inside plan mode via the `make review` dispatcher — cross-direction for plan review, same-AI for commit review.
argument-hint: "plan [PLAN_FILE] [ITERATION] | commit"
allowed-tools: Bash, AskUserQuestion
---

# /dev-review — run the right review without leaving plan mode

You are the Claude session acting as the implementer/driver. This command runs
the `make review` dispatcher so the correct reviewer is chosen automatically:
**plan** review is cross-direction (a Claude-authored plan is reviewed by Codex,
a Codex-authored plan by Claude); **commit** review is same-AI Tier-1. You never
pick the reviewer or list review directions yourself — `make review` is the
single source of dispatch truth.

Argument syntax:

- `/dev-review commit` — Tier-1 review of the most recent commit.
- `/dev-review plan [PLAN_FILE] [ITERATION]` — skeptical review of a plan file.

Parse the first token of `$ARGUMENTS` as the mode, then follow the matching
section below.

## commit

The implementer IS this Claude session, so the reviewer is Claude by
construction (same-AI Tier-1) — do NOT ask anyone. Run exactly:

```
make review MODE=commit ACTOR=claude
```

(Append `PLAN_FILE=docs/plans/<active>.md` to bind the plan-drift check when a
plan is in flight.)

## plan

The plan's **author** may be Claude OR Codex, and a wrong guess mis-routes the
review to the wrong reviewer. So ASK first — use `AskUserQuestion` with the
question "Who authored this plan?" and two options: **Claude** (the default) and
**Codex**. Do NOT silently default, and do NOT offer the user a choice of review
*direction* — the dispatcher derives the correct cross-direction from the author
alone.

Then run exactly — substitute the author's answer for `<author>`; use the
`[PLAN_FILE]` / `[ITERATION]` arguments if given, otherwise the active
plan-mode file and iteration 1:

```
make review MODE=plan ACTOR=<author> PLAN_FILE=<plan-file> ITERATION=<n>
```

`make review` picks the correct cross-direction reviewer from `ACTOR` alone. You
only supply the author.
