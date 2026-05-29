# Bucket A Architecture: In-Plan-Mode Skill Wrapper

Design pre-work for PR-2. Each sub-design below covers: options considered,
options REJECTED with reasoning, and acceptance criteria. Required by the
meta-plan before opening a plan-review loop (to avoid PR #10's 7-iter
non-plateau caused by open architectural choices).

---

## Sub-design 1: `.gitignore` parent-ignore neutralization

### Problem

`bootstrap_lib/adopt.py` rule (a0): if the planned file is ignored by git
(`git check-ignore` returns a source), the adopter SIPs with
`manual_review_needed=True`. The Skill file (`SKILL.md`) lives under `.claude/`
(e.g. `.claude/commands/dev-project-setup.md`). If the target repo's root
`.gitignore` contains a blanket `.claude/` pattern, rule (a0) fires and the
Skill is never written — even if the user wants it.

The current `APPEND_MERGE` policy can ADD patterns to `.gitignore` but cannot
**neutralize** an existing parent-level ignore — `!.claude/` appended to
`.gitignore` does not override a `.claude/` rule in the SAME file that
appears earlier. To override, the negation must appear AFTER the original rule
in the same file.

### Options considered

**Option A: In-place line insertion** — insert `!.claude/SKILL.md` immediately
after the matching `.claude/` rule line in `.gitignore`.

*Rejected*: Fragile. The adopt logic would need to detect the exact position of
the source rule (via `git check-ignore -v` output), then do a targeted line
insert. The `.gitignore` file is generated/checked in and must not be
re-formatted by the adopter. Worse: if there are multiple matching rules
(inherited `.gitignore`s in parent dirs), the source may be outside the
target repo entirely — uneditable.

**Option B: NEUTRALIZE policy** — a new policy that appends a block at the
END of `.gitignore`:
```
# dev-project-setup: un-ignore the skill file managed below
!.claude/
.claude/*
!.claude/commands/
.claude/commands/*
!.claude/commands/dev-project-setup.md
```
The 5-line block uses the "re-ignore then un-ignore" pattern that works because
later rules take precedence within the same file.

*Selected*. The block is self-contained, append-only, and carries its own
sentinel comment so it can be identified and removed by `--restore`.

**Option C: WRITE_NEW to a separate `.claude/.gitignore`** — create a repo-scoped
`.gitignore` inside `.claude/` that un-ignores the Skill file.

*Rejected*: Less portable (Git < 1.7.4 doesn't support directory `.gitignore`s),
and creates a new file that itself could be ignored depending on the repo's
config. Adds adoption surface.

**Option D: Instruct the user to fix their `.gitignore`** — keep rule (a0) as-is,
emit a clearer advisory, and let the owner fix the ignore manually.

*Rejected*: This is the status quo and is exactly the ergonomics problem PR-2
is solving. The Skill file is a first-class deliverable; requiring manual
`.gitignore` surgery defeats the purpose of adopt-mode automation.

### Acceptance criteria

1. `recommend_policy(".claude/commands/dev-project-setup.md", ..., target_meta.ignored_by_git="<source>")` returns `policy="NEUTRALIZE"` (a new policy value) when the parent `.gitignore` contains `.claude/` or `.claude/**`.
2. `apply_neutralize(target_gitignore_path)` appends the 5-line block from Option B.
3. `--restore` on a NEUTRALIZE target removes the appended block (sentinel-delimited) and leaves the rest of `.gitignore` unchanged.
4. `recommend_policy` still returns `SKIP` with `manual_review_needed=True` for ignored paths that are NOT `.claude/`-pattern-ignored (other ignore sources → still conservative default).
5. Existing `APPEND_MERGE` contract is unchanged; NEUTRALIZE is a parallel policy path.

---

## Sub-design 2: `pre_skip_check` — analyze-phase signal without violating manifest contract

### Problem

The current adoption flow is:
1. `render_all` → generate planned files in memory
2. `plan_adoption_entries` → call `recommend_policy` for each file → build manifest
3. `apply` → write/overwrite/skip each file per manifest

The problem for the Skill file: step 3 applies the Skill AFTER the `.gitignore`
rewrite (step 3 processes files in manifest order). If the Skill was planned as
WRITE but the `.gitignore` NEUTRALIZE hasn't happened yet, the Skill file gets
written to disk as a git-ignored file — which is wrong.

PR #10 iter-6 F3 noted that a "mid-apply gate" (check `.gitignore` state mid-apply
and abort/restart) violates the atomic-write/restore contract: the manifest must
fully describe what was written for `--restore` to work.

### Options considered

**Option A: Two-pass apply** — pass 1 applies `.gitignore` mutations (NEUTRALIZE/
APPEND_MERGE); pass 2 re-evaluates `recommend_policy` for any file that was in
a SKIP/a0 state and re-applies.

*Rejected*: Breaks the "manifest is written before any apply" contract. Pass 2
would produce NEW entries not in the original manifest, making `--restore`
incomplete. Also: between pass 1 and pass 2, the repo is in a partially-applied
state; if the process is interrupted, restore is broken.

**Option B: Pre-apply dependency ordering** — in `plan_adoption_entries`,
detect that a NEUTRALIZE entry must be ordered before any WRITE entry that
depends on it (i.e., any entry that rule (a0) would have SKIP-ed but NEUTRALIZE
unblocks). Build the manifest with an explicit `depends_on` field; apply in
topological order.

*Selected*. The manifest is still built fully before any apply. The `apply`
function processes entries in topological order: NEUTRALIZE entries first, then
their dependents. `--restore` reverses the topological order. No mid-apply
re-evaluation is needed; the full dependency graph is computed at plan time.

**Option C: Separate pre-phase** — a new `pre_apply` CLI mode that runs only
`.gitignore` mutations and reports the new `ignored_by_git` state for
re-inspection.

*Rejected*: Requires the user to run two commands. Defeats the "one-command
adopt" ergonomics goal.

**Option D: `pre_skip_check` as a manifest field** — add a boolean
`requires_gitignore_neutralize: bool` to each manifest entry; `apply` checks
this field and runs NEUTRALIZE first.

*This is essentially Option B expressed differently*: the topological dependency
is encoded as a manifest field. Accepted as the concrete implementation shape for
Option B.

### Acceptance criteria

1. `plan_adoption_entries` returns a manifest where NEUTRALIZE entries have `sort_key=0` and WRITE entries that depend on a NEUTRALIZE have `sort_key=1` (or equivalent dependency encoding).
2. `apply` processes entries in ascending `sort_key` order.
3. `--restore` processes entries in descending `sort_key` order (removes Skill before un-neutralizing `.gitignore`).
4. If the process is interrupted after NEUTRALIZE but before WRITE, `--restore` correctly reverts `.gitignore` to its pre-neutralize state.
5. Existing manifest entries (no NEUTRALIZE dependency) are unaffected.

---

## Sub-design 3: 3-branch × 2-mode acceptance harness (6 branches)

### Problem

The Skill wrapper must invoke the correct review target depending on who is the
implementer (Claude, Codex, or Other) AND which mode (plan-review or commit-review):

| | Plan-review | Commit-review |
|---|---|---|
| Claude | `review-plan-by-codex` | `review-commit-by-claude` (same-AI) |
| Codex | `review-plan-by-claude` | `review-commit-by-codex` (same-AI) |
| Other | `AskUserQuestion` to pick | `AskUserQuestion` to pick |

The Skill must never offer both cross-AI options simultaneously (anti-pattern from
PR #10 iter-4 F5). Tier-1 commit review is always same-AI. Tier-2 (GitHub bots) is
always cross-AI and happens automatically on PR open — the Skill does not invoke it.

### Options considered

**Option A: Single branching Skill** — one `dev-project-setup` Skill that reads
a `REVIEWER` env var (or AskUserQuestion) and branches to the correct target.

*Selected*. The Skill already uses `AskUserQuestion` for the "Other" case per
iter-4 F5. The branch logic is:
1. If current session AI == Claude → cross-direction = Codex target
2. If current session AI == Codex → cross-direction = Claude target
3. If Other → AskUserQuestion: which AI authored the plan/commit?

**Option B: Two separate Skills** (`dev-project-setup-claude`, `dev-project-setup-codex`).

*Rejected*: CLAUDE.md and AGENTS.md surface rules reference a single Skill name.
Splitting creates confusion about which to invoke and requires updating AGENTS.md
(which is auto-populated for the Codex reader).

**Option C: No explicit branch — always offer AskUserQuestion**.

*Rejected*: Friction. If the Skill is invoked from a Claude Code session, the AI
is known — forcing a question creates unnecessary interruption.

### Acceptance criteria (6-branch harness)

| Branch | Input | Expected Skill behavior |
|--------|-------|------------------------|
| Claude, plan-review | invoke Skill in Claude session | runs `make review-plan-by-codex PLAN_FILE=...` |
| Claude, commit-review | invoke Skill in Claude session | runs `make review-commit-by-claude` |
| Codex, plan-review | invoke Skill in Codex session | runs `make review-plan-by-claude PLAN_FILE=...` |
| Codex, commit-review | invoke Skill in Codex session | runs `make review-commit-by-codex` |
| Other, plan-review | invoke Skill, Other AI | AskUserQuestion → selects cross-direction target |
| Other, commit-review | invoke Skill, Other AI | AskUserQuestion → selects same-AI target |

All 6 branches must have an automated acceptance test (Skill invocation with mocked
`make` target + assertion on which target was invoked). V-21 (from PR #10) pins the
byte-identity of the Skill template against the dogfood Skill — this harness is a
separate concern.

---

## Open questions before plan PR

1. **NEUTRALIZE policy naming**: should it be a new `Policy` literal value, or
   a new `PolicyRecommendation.sub_policy` field that augments SKIP?  
   Recommendation: new `Policy` literal value (`"NEUTRALIZE"`) — it has distinct
   apply and restore semantics from SKIP.

2. **Sort key vs depends_on graph**: for the simple case (one NEUTRALIZE, one
   dependent WRITE), a sort key is sufficient. If multiple NEUTRALIZE steps are
   needed in the future, a full dependency graph is cleaner. Recommendation: start
   with `sort_key` (simpler manifest schema); extend to DAG only if needed.

3. **6-branch harness test isolation**: should each branch test be a pytest test
   or an integration smoke? Given that `make` targets themselves are tested in
   `test_makefile_review_targets.py`, the Skill branch test should mock `make` at
   the subprocess level and assert the correct target was invoked. This is already
   the pattern for existing Skill tests.

---

_Last updated: 2026-05-29 (pre-plan-review, pre-Codex-focused-review)_
