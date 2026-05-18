# Skill PR #5 — Observability + self-improvement layer

## Context

PR #1–#4 built the per-PR workflow (plan-review loop → mandatory human-approval → Tier-1 / Tier-2 reviews → triage rule with four-questions). What's still missing:

1. **Post-compaction blindness** — `TodoWrite` is session-ephemeral; after conversation compaction the agent retains partial memory but loses the explicit task list. Empirically produces confident-but-wrong suggestions (proposing work that's already done; adding to plans that are half-implemented). User flagged this from another project.

2. **No record of "what shipped vs what planned"** — plan body is frozen at approval; the iteration log only captures plan-review fold history; commit messages are per-commit; PR description is summary-only. Nothing captures *deviations during impl* (decisions made mid-impl that weren't in the plan, issues hit, fixes that surfaced). Future readers (or post-compaction-me) can't reconstruct what actually happened.

3. **User corrections live nowhere structured** — when the user pushes back ("the premise is wrong", "we already tried that"), the resulting rule sometimes goes into CLAUDE.md (e.g. four-questions framework), sometimes into BACKLOG, sometimes nowhere. No append-only log of "mistakes I should not repeat".

4. **`/simplify` is a useful Claude Code skill we don't reference** — catches code-quality smells that Tier-1 (plan-impl drift) and Tier-2 ("only-discovered-by-running") don't. Particularly valuable after multiple iter folds when review fatigue leaves cruft.

This PR adds the observability + self-improvement layer that closes all four gaps. **PR #5 was originally "real-project trial" — that becomes PR #6** because real-project trial benefits from this layer existing (we'll capture lessons + impl-log entries throughout the trial).

### Design principles

- **CLAUDE.md stays small and stable** — only fundamental shifts (like the four-questions framework) belong there. Operational guidance lives in LESSONS.md. Rare exception: a lesson that turns out to be a fundamental principle CAN promote to CLAUDE.md, but only via plan-review (not as a default workflow).
- **Capture is semi-automatic** (closes Codex iter-2 #5 — earlier "no manual rituals" was inconsistent with the Tier-1-proposes-driver-pastes design). The Tier-1 prompt proposes impl-log entries; the driver pastes them. This is an explicit acknowledged trade-off: full automation (Tier-1 writing the file directly) would require granting Tier-1 write permission OR shipping a helper script. We pick paste-by-driver as the lower-complexity option. If the manual ritual proves brittle in practice, the BACKLOG entry "Helper script to auto-append a reviewed impl-log row" can be picked up then.
- **Make status synthesizes; doesn't duplicate** — `make status` reads git + gh + the latest plan; it does NOT maintain its own state file (no `STATUS.md` to drift).
- **Lessons graduate by archival, not by promotion** — most old lessons stay in LESSONS.md as historical record. Default archival criteria (matches the CLAUDE.md instruction in Bucket D): move to "Archived" once EITHER (a) the pattern hasn't fired for 3+ sessions OR (b) the underlying problem is solved structurally. Rare promotion exception: a lesson that turns out to be a fundamental principle can promote to CLAUDE.md via plan-review. Promotion is an explicit decision, not automatic.

## Scope

### IN scope

| # | Change | Where |
|---|---|---|
| 1 | `make status` target — cross-session/compaction recovery, fully self-contained (no external `make doctor` dep) | `shared/Makefile.review.tmpl` + skill `Makefile` |
| 2 | Implementation log section in plan files + **mandated workflow step**: append the Tier-1-suggested row + create a SEPARATE docs-only commit before push. CONTRIBUTING.md step 9 gets a new clarifying note that docs-only impl-log commits qualify for the **existing** "trivial diff → skip Tier-1" exemption (the exemption itself was added in PR #4; this PR only adds the note pointing at it, so docs-only commits don't loop). | Plan-file convention; `shared/docs-plans-README.md.tmpl` + skill `docs/plans/README.md`; `shared/CONTRIBUTING.md.tmpl` step 9 extension: mandate text + clarifying note about the pre-existing trivial-diff exemption |
| 3 | Tier-1 prompt extension — propose impl-log row alongside findings | `tier1_prompt` macro in `shared/Makefile.review.tmpl` |
| 4 | `LESSONS.md` + self-improvement loop | NEW file at repo root + `shared/LESSONS.md.tmpl` for generated projects |
| 5 | **Renderer wiring** for `LESSONS.md` so generated projects actually receive the file | `bootstrap_lib/render.py` `SHARED_TEMPLATE_MAP` entry + smoke-test expected paths in all 3 language smoke tests |
| 6 | Status-recovery + self-improvement instructions in **BOTH** `CLAUDE.md` AND `AGENTS.md` (template + dogfood) — original BACKLOG entry mentioned both surfaces; Codex auto-reviewer reads `AGENTS.md`, not `CLAUDE.md` | `shared/CLAUDE.md.tmpl`, `shared/AGENTS.md.tmpl`, dogfood `CLAUDE.md`, `AGENTS.md` |
| 7 | `/simplify` as optional step | `shared/CONTRIBUTING.md.tmpl` step 9 + skill `CONTRIBUTING.md` |
| 8 | Tests for new targets, prompt extension, lessons schema, mandated-impl-log-step doc, renderer wiring | `tests/` |
| 9 | BACKLOG cleanup — close "Cross-session state recovery" entry as done; renumber README PR sequence | `BACKLOG.md`, `README.md`, `SKILL.md` |

### NOT in scope

- **No auto-pruning of LESSONS.md** — manual archive/delete only. Heuristic: human-judged at session start ("is this still firing?").
- **No `STATUS.md` tracked file** — `make status` synthesizes on demand. Would otherwise drift.
- **No git-hook to enforce impl-log updates** — too heavy. Tier-1 proposes, driver appends, manual ritual.
- **No `/simplify` make-target wrapper** — `/simplify` is a Claude Code skill; doc reference only. Other CLIs (non-Claude-Code sessions) don't have it; CONTRIBUTING.md wording must gate it accordingly (closes Codex iter-2 #7).
- **No helper script for impl-log row append** — paste-by-driver acknowledged as the trade-off (closes Codex iter-2 #5). New BACKLOG entry tracks this if it proves brittle.
- **No renumbering of merged PRs** — they keep their numbers (PR #1–#4 stay shipped). Only the README's "Build sequence" updates: this is now PR #5; real-project trial becomes PR #6.

## Subsystem breakdown

### Bucket A — `make status` target

New target in `shared/Makefile.review.tmpl` (and dogfood `Makefile`). Synthesizes state from existing artifacts; no own state file.

Output sections:
1. **Current branch activity** (closes Codex iter-6 #1 — original design only showed `origin/main` history, missing the feature branch's unmerged commits which is exactly the work the agent needs to see post-compaction): print current branch name + `git log --oneline -10 HEAD`. Primary "what have I been doing" view for the recovery session.

2. **Recent main activity** (secondary section, "what's already shipped"): `git log --oneline -10 <ref>` with fallback chain (closes Codex iter-2 #2): try `origin/main` → `main` → `HEAD`. Print the ref name + 10 commits. Fresh-bootstrap repos (local commits, no remote) get useful output via `HEAD` fallback. Falls back to `(no commits yet)` if even `HEAD` fails. NOTE: when current branch == main, this duplicates section 1 — benign redundancy

3. **Open PRs** — `gh pr list --state open --json number,title,headRefName,isDraft` (one line each; falls back to `(gh CLI not available)` if missing or unauthed)

4. **Active plan** — selected via `PLAN_FILE=` override; falls back to `ls -t docs/plans/*.md | grep -vE 'README\.md$'` (mtime-sorted, README.md filtered — closes Codex iter-2 #1; generated projects ALWAYS have `docs/plans/README.md` via the renderer). Handles five cases: (a) override given and file exists → use it; (b) override given but file missing → print "(PLAN_FILE not found: ...)" in this section + continue with other sections; (c) no override, one candidate → use it; (d) no override, multiple candidates → print WARN listing top-3 by mtime + use top-1; (e) no override, zero candidates → print `(no plan files)` and skip iter-log + impl-log subsections. Outputs the file path + tail of iteration log (~20 lines) + tail of impl log (~20 lines)

5. **Active lessons** — `LESSONS.md` "Active" section, up to ~50 lines (should be small by design; if it exceeds 50 lines, the prune ritual is overdue)

6. **Local repo state** — `git status --short` (so the agent sees uncommitted changes; guarded with `git rev-parse --is-inside-work-tree`)
7. **Health checks** — **INLINED** (closes Codex iter-1 #1): direct `command -v git`, `command -v gh`, `command -v claude`, `command -v codex` checks with `"  ok       <tool>"` / `"  advisory <tool> not on PATH"` lines (matching the recipe and contracts exactly). Does NOT invoke `make doctor` (which is skill-repo-only — generated language Makefiles don't have it). Self-contained; works identically in skill repo + every generated project.

Make recipe shape (illustrative; impl PR delivers the actual text — but it must satisfy every prose contract above):
```makefile
PLAN_FILE ?=

# Note: `status` joins the existing review-section .PHONY block in
# shared/Makefile.review.tmpl + skill Makefile; the standalone .PHONY
# line above is illustrative only in this sketch.

status:	## Synthesize current project state (for new sessions / post-compaction)
	@echo "── Current branch activity ──"
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  branch=$$(git rev-parse --abbrev-ref HEAD 2>/dev/null); \
	  if git rev-parse --verify HEAD >/dev/null 2>&1; then \
	    echo "(branch: $$branch)"; \
	    git log --oneline -10 HEAD; \
	  else echo "(branch: $$branch; no commits yet)"; fi; \
	else echo "(not a git repo)"; fi
	@echo ""
	@echo "── Recent main activity ──"
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  ref=""; \
	  if git rev-parse --verify origin/main >/dev/null 2>&1; then ref="origin/main"; \
	  elif git rev-parse --verify main >/dev/null 2>&1; then ref="main"; \
	  elif git rev-parse --verify HEAD >/dev/null 2>&1; then ref="HEAD"; \
	  fi; \
	  if [ -n "$$ref" ]; then \
	    echo "(ref: $$ref)"; \
	    git log --oneline -10 "$$ref"; \
	  else echo "(no commits yet)"; fi; \
	else echo "(not a git repo)"; fi
	@echo ""
	@echo "── Open PRs ──"
	@if command -v gh >/dev/null 2>&1; then \
	  gh pr list --state open --json number,title,headRefName,isDraft --jq '.[] | "#\(.number)  [\(if .isDraft then "draft" else "ready" end)]  \(.title)"' 2>/dev/null \
	    || echo "(gh CLI unauthed or repo not on github)"; \
	else echo "(gh CLI not available)"; fi
	@echo ""
	@echo "── Active plan ──"
	@if [ -n "$(PLAN_FILE)" ] && [ ! -f "$(PLAN_FILE)" ]; then \
	  echo "(PLAN_FILE not found: $(PLAN_FILE))"; \
	elif [ -n "$(PLAN_FILE)" ]; then \
	  echo "$(PLAN_FILE) (PLAN_FILE override)"; \
	  # extract iteration log + impl log from $(PLAN_FILE) via fence-aware awk
	elif ls docs/plans/*.md >/dev/null 2>&1; then \
	  candidates=$$(ls -t docs/plans/*.md | grep -vE 'README\.md$$'); \
	  if [ -z "$$candidates" ]; then \
	    echo "(no plan files)"; \
	  else \
	    count=$$(echo "$$candidates" | wc -l | tr -d ' '); \
	    latest=$$(echo "$$candidates" | head -1); \
	    echo "$$latest (auto-detected by mtime; pass PLAN_FILE=... to override)"; \
	    if [ "$$count" -gt 1 ]; then \
	      echo "!!! WARN: $$count PLAN FILES PRESENT — top 3 by mtime (pass PLAN_FILE=... to override):"; \
	      echo "$$candidates" | head -3 | sed 's/^/  - /'; \
	    fi; \
	    # tail iteration log + impl log from $$latest
	  fi; \
	else echo "(no plan files)"; fi
	@echo ""
	@echo "── Active lessons ──"
	@if [ -f LESSONS.md ]; then awk '/^## Active/,/^## Archived/' LESSONS.md | head -50; else echo "(no LESSONS.md)"; fi
	@echo ""
	@echo "── Local repo state ──"
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  git status --short || true; \
	else echo "(not a git repo)"; fi
	@echo ""
	@echo "── Health checks ──"
	@for tool in git gh claude codex; do \
	  if command -v $$tool >/dev/null 2>&1; then echo "  ok       $$tool"; \
	  else echo "  advisory $$tool not on PATH"; fi; \
	done
```

Recipe contracts (each must hold in the impl PR):
- Recent main activity: fallback chain `origin/main` → `main` → `HEAD`; "(no commits yet)" when even HEAD is unreachable; "(not a git repo)" when not inside a worktree.
- Open PRs: `gh` missing → `(gh CLI not available)`; `gh` present but unauthed/not-github → `(gh CLI unauthed or repo not on github)`.
- Active plan: `PLAN_FILE=` override wins when the file exists; missing override file → "(PLAN_FILE not found: ...)"; otherwise mtime-sorted candidates with README filtered via `grep -vE 'README\.md$$'`; zero → `(no plan files)`; one → use it; multiple → use top-1 + **loud WARN** listing top-3 by mtime. User-decision (2026-05-18, post-iter-5 human-approval gate): accept this design rather than tightening to "require PLAN_FILE in multi-plan mode". Rationale: the WARN+candidate-list is the safety mechanism — the human sees what's being picked + can re-invoke with `PLAN_FILE=<correct>` if wrong; tightening would add friction to the recovery command itself. The WARN line MUST be visually prominent (e.g. `!!!` markers + ALL-CAPS keyword) so a recovering agent reads it before acting on the tail.
- Active lessons: tail to ~50 lines.
- Local repo state: `git status --short` guarded.
- Health checks: inlined `command -v` for `git gh claude codex`. Output format: `"  ok       <tool>"` when present, `"  advisory <tool> not on PATH"` when absent. Never fails the target.
- **Section extraction must be fence-aware** (closes Codex iter-4 #1): the active-plan section parser must skip content inside ` ```...``` ` fenced code blocks. Plan files contain example markdown sections inside fences (e.g. this plan's Bucket B has an example `## Implementation log` inside a fence; the REAL section is the top-level un-fenced one). Implementation: awk that tracks fence state with a toggle on `^```` lines, OR sed that operates only on lines outside fenced regions. Also: legacy plans (PR #1–#4) have iteration logs but no impl-log section → fall back to `(no Implementation log section yet)`.
- **`status` declared `.PHONY`** (closes Codex iter-4 #5): added to the `.PHONY:` block alongside the existing review targets in `shared/Makefile.review.tmpl` + skill `Makefile`. Without this, a file named `status` (e.g. accidentally created) would cause `make status` to no-op silently. Regression test: create a file `status` in the fixture, invoke `make status`, assert the recipe still runs.

**No CLI dependency beyond `git` (already required).** Every section guarded; exits 0 in every case (fresh-bootstrap, no-git, no-gh, no-lessons, no-plans). Skill-repo `Makefile` mirrors the rendered template (byte-identical region).

### Bucket B — Implementation log convention + **mandated workflow step**

Plan files gain a new section AFTER the evidence table, BEFORE the "Critical files to read" section (closes Codex iter-2 #3 — earlier wording said "at END" but plans typically have Critical-files at the bottom; convention is now "Implementation log + Lessons surfaced go AFTER Evidence table; Critical-files-to-read goes LAST"):

```markdown
## Implementation log (this PR)

Updated as commits land on the impl branch. Captures what shipped, deviations from plan, issues hit. Tier-1 review proposes entries; driver appends BEFORE next commit/push.

| Commit | What landed | Deviations from plan | Issues faced |
|---|---|---|---|
| <sha1> | <bucket A: what> | <none / specifics> | <none / specifics> |
| <sha2> | ... | ... | ... |

## Lessons surfaced (this PR)

Patterns worth appending to `LESSONS.md` "Active" (or, if fundamental enough, to `CLAUDE.md` after plan-review).

- ...
```

**Mandated workflow step** (closes Codex iter-1 #4 — proposes-but-not-enforced was the gap; clarified in iter-3 #1 to address commit-SHA concern). Documented in:

- **`shared/CONTRIBUTING.md.tmpl` step 9** (the Tier-1 sub-bullet): after running `make review-commit-by-*` against a focused code commit, the driver:
  1. Triages findings per (a/b/c/d) + four-questions
  2. Pastes the Tier-1-suggested impl-log row into the plan's Implementation log section (or notes `N/A — trivial diff` if no row warranted)
  3. **Creates a separate docs-only commit** for the impl-log update (e.g. `git commit -m "Append impl-log row for <short-sha>"`). This is a deliberate trade-off (closes Codex iter-3 #1): the alternative — amending the reviewed code commit — would change the SHA and invalidate the Tier-1 review's audit trail. Docs-only commits qualify as "trivial diff" per CONTRIBUTING and therefore skip Tier-1, so they don't loop.
  4. Pushes (both code commit + impl-log commit) together
- **`shared/docs-plans-README.md.tmpl`**: workflow section 2 extended with the impl-log convention + the mandated-append step + the docs-only-commit pattern.
- **Dogfood mirrors**: skill `CONTRIBUTING.md` + `docs/plans/README.md` same updates.

**Tier-1 plan-file binding** (closes Codex iter-3 #4 + iter-6 #2 + Tier-2 #1): the macro signature becomes `tier1_prompt(commit_ref, plan_file=None)`. The macro treats BOTH `None` AND empty-string as "unbound" (Jinja's `{% if plan_file %}` does the right thing for both). ALL THREE Tier-1 entrypoints honor the binding:

1. **`review-commit-by-{codex,claude}` Makefile targets** accept `PLAN_FILE=docs/plans/<file>.md` and pass `$(PLAN_FILE)` to the macro at render time. When unset, `$(PLAN_FILE)` renders to empty string → macro takes the unbound branch.
2. **CONTRIBUTING.md.tmpl's subagent template** (the in-session Claude Code path): shows TWO explicit prompt variants (closes Codex Tier-2 #1 — earlier single-variant template with literal `<PLAN_FILE>` placeholder baked the placeholder string into the rendered prompt, defeating the unbound fallback):
   - **Variant A — "If you have a plan to check drift against"**: uses `{{ tier1_prompt('<SHA>', '<PLAN_FILE>') }}`. Driver substitutes BOTH `<SHA>` and `<PLAN_FILE>`.
   - **Variant B — "If you have no plan binding (code-correctness only)"**: uses `{{ tier1_prompt('<SHA>') }}`. Driver substitutes only `<SHA>`. Macro's unbound branch fires → canonical fallback text.
   Driver picks the variant matching their current task. The docs make it explicit which is which.
3. **In-session ad-hoc subagent** (no make, no CONTRIBUTING template): driver constructs the prompt using either variant directly.

**Canonical PLAN_FILE prompt phrases** (one source of truth — used identically across all 3 entrypoints; closes self-check 6.5 #5):
- **When PLAN_FILE IS set**: "check this commit against `docs/plans/<file>.md`'s plan body; flag any deviation as plan-impl drift findings"
- **When PLAN_FILE is unset**: "no plan binding; limit findings to code-correctness, do not infer a plan file by mtime"

Avoids the reviewer picking the wrong plan from a multi-plan repo. CONTRIBUTING.md step-9 sub-bullet now reads `make review-commit-by-claude PLAN_FILE=docs/plans/<active>.md` (PLAN_FILE listed as recommended, with the unbound-fallback caveat documented).

**Test scope for PLAN_FILE runtime passthrough** (user-decided 2026-05-18, post-iter-5: P2 deferred to impl PR per "real but deferrable" framing): the impl PR's `tests/test_makefile_review_targets.py` MUST include Make-level argv-capture tests, not just template-level macro tests. Specifically: invoke `make review-commit-by-codex PLAN_FILE=docs/plans/x.md` via shim, capture argv, assert the rendered prompt contains the plan reference; separately invoke without `PLAN_FILE=`, assert the prompt contains the fallback text. Cover Claude target too (parameterize the existing shim test). This is the only iter-5 item explicitly carried as "must-do during impl" rather than being fully resolved in the plan.

A new doc-test in `tests/test_shared_templates.py` asserts the Tier-1 sub-bullet of step 9 contains "append" + "impl-log" / "Implementation log" wording (so the mandated step doesn't quietly disappear).

Documentation in `shared/docs-plans-README.md.tmpl` + dogfood. Explains the convention.

### Bucket C — Tier-1 prompt extension

Extend the `tier1_prompt(commit_ref, plan_file=None)` macro in `shared/Makefile.review.tmpl` (signature now takes optional plan_file per iter-3 #4 + iter-6 #2 folds) to also instruct the reviewer to propose an impl-log row:

Current macro prompt ends:
> "...AND identify any other files where the same fix should apply for consistency. Do NOT edit files. If there are no importance-3 findings, say so explicitly."

Extension (closes Codex iter-5 #1 — uses plain text, NO backticks, since the rendered prompt is passed as a double-quoted shell arg and backticks would trigger command substitution):
> "...AND identify any other files where the same fix should apply for consistency. Do NOT edit files. If there are no importance-3 findings, say so explicitly. ALSO output a suggested implementation-log row for this commit. Use this exact table-row shape (no backticks; the literal pipe characters and angle-bracket placeholders): | short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |. The driver will append this to the plan's Implementation log section."

A new regression test in `tests/test_makefile_review_targets.py` invokes `make review-commit-by-codex` via a shim that captures argv, then asserts the captured prompt contains no backtick characters AND no `$(` substring (the two shell-substitution traps).

Since the macro is single-source, this change propagates to both Makefile recipes AND `CONTRIBUTING.md.tmpl`'s subagent template.

### Bucket D — `LESSONS.md` + self-improvement loop

**New file at skill repo root: `LESSONS.md`.**

Format:
```markdown
# Lessons

Append-only log of mistakes + the rules that prevent recurrence. Read the
"Active" section at session start. Move solved/obsolete entries to "Archived".

## Active

### YYYY-MM-DD: <one-line mistake>

**Trigger**: <what happened that surfaced this>
**Rule**: <what to do differently>
**Status**: Active

---

### ...

## Archived

### YYYY-MM-DD: <one-line mistake> (archived YYYY-MM-DD)

(Same fields. Kept as historical record; not re-read at session start.)
```

**Initial seed entries** for the skill repo's own `LESSONS.md` — using the exact schema the test will enforce (closes Codex iter-4 #3 — earlier numbered-list format would fail the schema test):

```markdown
### 2026-05-17: Don't apply reviewer's suggested fix without verifying premise

**Trigger**: PR #4 iter-4 #2 — Codex framed a hypothetical as imp-3 blocker. User push-back revealed the premise was wrong (Claude `--print --permission-mode plan` did NOT have the speculated invocation failure).

**Rule**: For every reviewer finding, run the four questions BEFORE deciding (a/b/c/d). Q1 specifically: is the premise correct? Spot-check against the file the reviewer cites. (See CLAUDE.md triage section.)

**Status**: Active

---

### 2026-05-17: Conditional Jinja branches can contradict surrounding non-conditional prose

**Trigger**: PR #4 Codex Tier-2 P2 — `none`-mode rendered "use BOTH tiers" (unconditional intro) then conditional "Tier-2 NOT configured" body. Tier-1 review missed it; Tier-2 caught it.

**Rule**: When adding `{% if %}` / `{% elif %}` branches to a template, audit the surrounding non-conditional prose for assumptions that hold only in some branches. If they do, move them inside the conditional or rewrite branch-agnostic.

**Status**: Active

---

### 2026-05-17: Don't use `git add -A` or `git add .` — pick files explicitly

**Trigger**: PR #4 — accidentally committed `.claude/scheduled_tasks.lock` session state via `git add -A`. CLAUDE.md already forbade `git add .` but didn't explicitly cover `-A`.

**Rule**: Always `git add path1 path2 ...`. Bulk-add flags (`-A`, `.`, `-u` outside review) catch session state, debug files, generated artifacts. Skill repo's `.gitignore` was extended too, but the discipline still matters.

**Status**: Active
```

This block becomes the literal contents of the skill repo's `LESSONS.md` `## Active` section (after the file's header and the `## Active` heading itself). **Shared template `shared/LESSONS.md.tmpl`** for generated projects ships with the file header + EMPTY Active/Archived sections (no seed entries — generated projects accumulate their own lessons from real corrections). Skill repo and shared template diverge here intentionally.

**CLAUDE.md additions** (small, as a standalone section — NOT inside the byte-identical triage block; the triage block stays focused on review-finding triage):

```markdown
## Self-improvement loop (LESSONS.md)

At session start: read `LESSONS.md` "Active" section. Apply the rules during this session.

**Writable-session-only append rule** (closes Codex iter-3 #5 — `AGENTS.md` is read by review-only contexts that explicitly cannot edit files):

- **In a writable implementation session** (you're the driver, free to edit files): after ANY user push-back that changes your approach, OR any Tier-1/2 finding that surfaced a new mistake-class, append a new entry to `LESSONS.md` "Active" directly. Format: `### YYYY-MM-DD: <mistake>` + Trigger + Rule + Status. Commit alongside the implementation.
- **In a read-only review session** (you're a reviewer running `make review-plan-by-codex`, `make review-commit-by-claude`, or any session that's been told "Do NOT edit files"): do NOT append to `LESSONS.md`. Instead, propose the lesson in your review output (or in the plan's `## Lessons surfaced` section if reviewing a plan). The DRIVER triages reviewer-proposed lessons in a later writable session: appends real ones to `LESSONS.md`; rejects duplicates or project-local noise.

Promote to `CLAUDE.md` only for FUNDAMENTAL shifts (rare; needs plan-review). Move to `LESSONS.md` "Archived" once the pattern hasn't fired for 3+ sessions OR the underlying problem is solved structurally.
```

**Critically: this addition goes in CLAUDE.md proper (not the byte-identical triage block)** because it's a stable workflow rule that benefits from being read alongside the per-task instructions. NOT a one-off lesson.

**Mirrored in AGENTS.md** (closes Codex iter-1 #3): the original BACKLOG entry called for "CLAUDE.md / AGENTS.md instruction". Codex's GitHub auto-reviewer + other AI reviewers read `AGENTS.md`, not `CLAUDE.md`. Both the **status-recovery instruction** AND the **self-improvement loop instruction** land in BOTH `shared/CLAUDE.md.tmpl` AND `shared/AGENTS.md.tmpl` (with dogfood mirrors). New dogfood test asserts both surfaces carry the instructions.

**Status-recovery instruction text** (same in CLAUDE.md + AGENTS.md):
```markdown
## Cross-session state recovery

If you're starting a fresh session, just resumed after compaction, or are uncertain whether work X is already done: run `make status` BEFORE proposing changes. It synthesizes git history + open PRs + the active plan's iteration log + impl log + active lessons. Cheap to run; prevents the failure mode where the agent proposes work that's already shipped.
```

### Bucket E-pre — Renderer wiring for `LESSONS.md` (closes Codex iter-1 #2)

Without this, `shared/LESSONS.md.tmpl` would exist but never get written to generated projects — every CLAUDE.md / AGENTS.md instruction that says "read LESSONS.md" would point at a non-existent file.

| File | Change |
|---|---|
| `bootstrap_lib/render.py` | Extend `SHARED_TEMPLATE_MAP` with `"LESSONS.md": "LESSONS.md.tmpl"` |
| `tests/test_smoke_python_generated.py` | Add `LESSONS.md` to the expected-files-on-disk assertion (the post-`--apply` directory listing check) |
| `tests/test_smoke_nodejs_generated.py` | Same |
| `tests/test_smoke_go_generated.py` | Same |
| `tests/test_bootstrap_cli.py` (if it asserts on dry-run output paths) | Add `LESSONS.md` to expected dry-run output |

Dogfood smoke also asserts the skill repo's own `LESSONS.md` exists with the 3 seed entries.

### Bucket E — `/simplify` as optional step

Documentation only — no make target wrapper (Claude Code skill, not general CLI).

In `shared/CONTRIBUTING.md.tmpl` step 9 (the existing Tier-1 sub-bullet), add:
> "...Triage findings per the (a/b/c/d) framework in `CLAUDE.md` (with the four-questions check).
> - **Blockers**: ...
> - **Optional /simplify pass** (Claude Code sessions only, substantive PRs only — >200 lines OR multi-commit OR multiple iter folds): after Tier-1 fold + before push, run `/simplify` (a Claude Code skill — not available in Codex CLI or generic terminals) to catch reuse / dead code / cruft accumulated across folds. Skip for trivial diffs, or if not in a Claude Code session, or do a manual cruft pass instead."

The gating phrasing ("Claude Code sessions only", "skip if unavailable", "manual cruft pass instead") closes Codex iter-2 #7 — generated projects are used by non-Claude-Code workflows too. Doc-test in `tests/test_shared_templates.py` asserts the wording contains "Claude Code" + "skip" + "optional".

Dogfood `CONTRIBUTING.md` mirrors.

### Bucket F — Tests

| File | Asserts |
|---|---|
| `tests/test_status_target.py` (NEW) | `make status` runs without error in a fresh-bootstrap fixture. Output contains the section headings. With shim `gh`, asserts PR section renders correctly. With no `gh`, asserts graceful fallback (not error). **PLAN_FILE override test**: pass explicit `PLAN_FILE=...` and assert the override appears in output. **Multi-plan WARN test** (closes Codex iter-1 #5): fixture with 2 recent plan files; assert WARN line fires + asserts top-3 candidates are listed. **Non-git-dir test**: status in a non-git tmpdir falls back to `(not a git repo)` without erroring. **Content assertions** (closes Codex iter-3 #3 — heading-only assertions would let empty sections pass): (a) fixture plan has a known iteration-log row + impl-log row → `make status` output CONTAINS those exact strings (not just the section heading); (b) fixture `LESSONS.md` has a known Active entry title → `make status` output CONTAINS that title; (c) fixture has both `<date>-foo.md` AND `docs/plans/README.md` → `make status` plan-detect EXCLUDES README; (d) bad `PLAN_FILE=does-not-exist.md` → `make status` prints graceful error in the Active-plan section (doesn't crash the whole target). **Contract-coverage assertions** (closes Codex iter-6 #3 — Bucket A contracts demand these but Bucket F hadn't enumerated explicit tests): (e) **fence-aware extraction**: fixture plan has a fenced ` ```markdown ` block containing `## Implementation log` (example/sample) AND a real `## Implementation log` section below; assert `make status` output picks the REAL section, not the fenced sample. (f) **Legacy no-impl-log plan**: fixture plan has iteration log but no `## Implementation log` section; assert fallback line `(no Implementation log section yet)`. (g) **Local-commits-no-remote**: fixture git repo has commits on HEAD but no origin/main configured; assert "Current branch activity" section shows the HEAD commits. (h) **`status` file regression**: create a file named `status` in the fixture root; invoke `make status`; assert the recipe still runs (i.e. `.PHONY` declaration is effective). |
| `tests/test_shared_templates.py` (extend) | (a) `tier1_prompt` macro contains the impl-log-row instruction (substring assertion). (b) `tier1_prompt` byte-identity test (existing) — extend to **parameterized** over `PLAN_FILE` argument: assert both the `commit_ref='HEAD'` + no-PLAN_FILE variant AND the `commit_ref='HEAD', plan_file='docs/plans/x.md'` variant render byte-identically between Makefile recipe and CONTRIBUTING.md template (closes self-check 4.5 #6). **Plus empty-string equivalence test** (closes Codex Tier-2 #1): assert `tier1_prompt('HEAD', '')` produces the same rendered text as `tier1_prompt('HEAD')` — i.e. empty plan_file is treated as unbound, not as a literal plan-path placeholder. (c) **NEW**: `shared/CONTRIBUTING.md.tmpl` step-9 sub-bullet contains the mandate wording — substrings: "append" + ("impl-log" or "Implementation log"). Dogfood `CONTRIBUTING.md` same assertion (closes Codex iter-1 #4 + self-check #5). (d) **NEW**: `shared/CONTRIBUTING.md.tmpl` `/simplify` sub-bullet contains the gating wording — substrings: "Claude Code" + "skip" + "optional" (closes self-check 5.5 #4). (e) **NEW**: `shared/CONTRIBUTING.md.tmpl` subagent-template section contains BOTH variants — substrings: "If you have a plan to check drift against" AND "If you have no plan binding" (closes Codex Tier-2 #1 — single-variant template would let a driver bake the literal `<PLAN_FILE>` placeholder into the prompt). |
| `tests/test_lessons_file_schema.py` (NEW) | `LESSONS.md` parses: has `# Lessons`, `## Active`, `## Archived` headings. Each active entry has Trigger + Rule + Status fields. **Skill-repo `LESSONS.md` has 3 seed entries** (closes self-check #6). Test the shared template renders cleanly too — and asserts the shared template Active section is EMPTY (no seeds), differentiating skill repo from generated projects. |
| `tests/test_makefile_review_targets.py` (extend) | Shim test for `make status`: invoke + assert exit 0 + section headings in stdout. Cover skill repo + a freshly-bootstrapped python generated project. |
| `tests/test_dogfood_doc_sanity.py` (extend) | (a) Assert root `LESSONS.md` exists + has Active + Archived sections + the 3 seed entries (specific entry-1/2/3 titles in Active). (b) Assert both root `CLAUDE.md` and `AGENTS.md` contain the "Cross-session state recovery" instruction AND the "Self-improvement loop" instruction (closes Codex iter-1 #3 + self-check #6). |
| `tests/test_smoke_python_generated.py`, `test_smoke_nodejs_generated.py`, `test_smoke_go_generated.py` (extend) | Two distinct extension paths (closes self-check 5.5 #3 — Bucket E-pre + this row now describe the SAME changes): **(a) dry-run path**: each file's existing dry-run stdout substring assertion (Python/Node use a list; Go uses a smaller language-specific list) gets `LESSONS.md` added. **(b) post-apply path**: each file's existing `target / <name>` on-disk assertion block gets `target / "LESSONS.md"` added, with content check for "# Lessons" + "## Active" + "## Archived" headings. Both paths together close the renderer-wiring guarantee. |
| `tests/test_bootstrap_cli.py` (extend if applicable) | Add `LESSONS.md` to any explicit shared-files enumeration tests (e.g. dry-run output coverage). |

### Bucket G — Active docs + BACKLOG

- `README.md`: Build sequence — add PR #5 (this); move "real-project trial" to PR #6.
- `SKILL.md`: brief mention of `make status` + LESSONS.md.
- `docs/usage.md`: new "Observability" section with `make status` example.
- `BACKLOG.md`:
  - Close "Cross-session / post-compaction state recovery" entry → DONE in PR #5.
  - Update the consolidated Boxette adoption entry (`Retroactively add triage rule + two-tier review docs to Boxette`) to ALSO include LESSONS.md template + observability layer.
  - **Add new entry** (closes Codex iter-4 #4): "Helper script to auto-append a reviewed impl-log row to the plan file" — currently the workflow relies on the driver manually pasting the Tier-1-suggested row into the plan + creating a docs-only commit. A small helper (`make append-impl-log PLAN_FILE=... ROW='...' ` or a script reading the Tier-1 output) would automate this. **Trigger**: if driver-forgets-to-paste happens twice in any post-PR-#5 implementation. **Rough effort**: ~1 hour.
- `shared/BACKLOG.md.tmpl`: no change needed (the entries there are workflow-tooling not project-content).

## Implementation rollout (user-decided 2026-05-18)

This plan ships across **3 sequential implementation PRs** rather than one. Rationale: 9 buckets × ~1000-line diff in a single impl PR is too large to Tier-1/Tier-2 review effectively. Splitting keeps each impl PR ~200-400 lines, with shorter cycle time per PR. Plan PR stays as ONE document — the impl PRs each reference the same plan and implement different buckets.

### Impl PR #5a — Observability foundation

- **Bucket A**: `make status` target (`shared/Makefile.review.tmpl` + skill `Makefile`)
- **Bucket D** (partial): `LESSONS.md` + self-improvement loop in shared/CLAUDE.md.tmpl + shared/AGENTS.md.tmpl + dogfood mirrors. Skill repo's `LESSONS.md` with the 3 seed entries. Cross-session-recovery instruction in BOTH files.
- **Bucket E-pre**: renderer wiring (`bootstrap_lib/render.py` + smoke-test expected paths in all 3 languages)
- **Bucket F** (subset): `tests/test_status_target.py` (NEW), `tests/test_lessons_file_schema.py` (NEW), `tests/test_dogfood_doc_sanity.py` (extend for cross-session-recovery + self-improvement instruction assertions + LESSONS seed entries), env-scrubber extension if needed.
- **Verification**: `make status` works end-to-end (skill repo + freshly-bootstrapped python generated project); LESSONS.md exists with 3 seeds + passes schema test; cross-session recovery instructions land in both CLAUDE.md AND AGENTS.md.

Standalone value: post-PR-#5a, the agent has `make status` + LESSONS infrastructure. The other 2 PRs layer on top.

### Impl PR #5b — Tier-1 + implementation-log

- **Bucket B**: Implementation log convention + mandated workflow step (CONTRIBUTING.md step 9 extension) + plan-file structural convention (`shared/docs-plans-README.md.tmpl` + dogfood). Docs-only-commit pattern for impl-log row append.
- **Bucket C**: Tier-1 prompt extension (impl-log row instruction, no backticks) + `tier1_prompt(commit_ref, plan_file=None)` macro signature update + Makefile recipe passthrough + CONTRIBUTING.md subagent template binding.
- **Bucket F** (subset): `tests/test_shared_templates.py` extensions — 3 new assertions in 5b (impl-log instruction, parameterized byte-identity over PLAN_FILE, step-9 mandate wording); the 4th assertion (`/simplify` gating wording) lands in 5c alongside that doc. `tests/test_makefile_review_targets.py` extensions: argv-capture test for backticks/`$(`-free prompt + Make-runtime PLAN_FILE passthrough test (set + unset for both codex + claude targets, the P2 impl-deferral item from iter-5).
- **Verification**: Tier-1 review on a fixture commit returns an impl-log-row proposal in the documented format; macro byte-identity holds across both PLAN_FILE states; Make-level PLAN_FILE actually reaches the rendered prompt.

Requires 5a merged first (depends on LESSONS being present in renderer + cross-session recovery being a known concept).

### Impl PR #5c — `/simplify` + active docs + BACKLOG

- **Bucket E**: `/simplify` doc gating in `shared/CONTRIBUTING.md.tmpl` step 9 + dogfood mirror.
- **Bucket G**: `README.md` (PR #5 line + PR #6 = real-project trial), `SKILL.md` (mention `make status` + LESSONS), `docs/usage.md` (Observability section). `BACKLOG.md`: close "Cross-session / post-compaction state recovery"; update Boxette adoption entry; add helper-script-to-append-impl-log-row entry with trigger.
- **Bucket F** (final subset): `tests/test_shared_templates.py` final assertion (d) for `/simplify` gating wording.
- **Cleanup commit**: any drift items found during 5a or 5b that need follow-up.

Lightest of the three. Doc + BACKLOG-heavy.

### Cross-PR sanity check

Each impl PR runs its own Tier-1 + Tier-2 review loop. The Plan PR (this document) is the shared contract. If 5a+5b reveal that the plan's design choices need revisiting before 5c, the plan body gets a "Implementation log (this PR)" entry documenting the deviation — then 5c can proceed with eyes open.

## Architecture decisions specific to this PR

- **`make status` reads, doesn't write.** No state file, no drift. Output is ephemeral synthesis.
- **Tier-1 proposes impl-log entries; driver appends.** Automated capture without granting Tier-1 write permission.
- **LESSONS.md is repo-local, not session-local.** Survives session compaction; visible in git history.
- **No promotion path from LESSONS.md → CLAUDE.md by default.** Only fundamental shifts (rare; need plan-review). Most lessons stay in LESSONS.md or get archived.
- **Implementation log lives IN the plan file**, not a parallel file. Single source for plan-to-shipped trail; future readers see plan + impl together.
- **`/simplify` mentioned but not enforced.** Optional, doc-only.

## Risks + mitigations (PR-#5-specific)

| Risk | Mitigation |
|---|---|
| `make status` becomes too verbose / unreadable | Tail each section appropriately: git log -10, gh pr list (one line per PR), latest plan iter+impl log tails (~20 lines each), Active lessons (~50 lines — it's the most-read section), git status --short. Section dividers. Plain text, no fancy formatting. |
| LESSONS.md balloons over time | Manual archival ritual (CLAUDE.md instructs). Active section should stay ≤~50 lines (the same threshold the `make status` recipe tails to); if it grows beyond that, prune. |
| Tier-1 prompt extension makes the prompt too long | Already long; one extra sentence is marginal. Measure on PR #6 actual runs. |
| Implementation log section never gets populated | Tier-1 ALWAYS suggests entries (mandatory for substantive PRs per CONTRIBUTING.md). If skipped on trivial PRs, that's correct — no log row needed. |
| `make status` `gh` dependency confuses users without `gh` | Section gracefully degrades to "(gh CLI not available)" — doesn't fail status. Doctor target already advisories about gh. |
| Adding 4+ new things at once = bloated PR | Each bucket is small; they share theme (observability). One Plan PR + one Impl PR keeps cycle short. |

## Verification

### Phase 1 — pre-implementation evidence (this plan PR)

1. **Plan-review loop** (Codex skeptical pass — run until convergence per the project's stopping rule: no imp-3 findings remain AND remaining 1/2 findings are folded or accepted; or human-approval gate fires at the 3-consecutive-iters-at-imp-3=1-2 plateau). Historically this specific plan required 6 Codex iters + 5 author consistency self-checks (1.5, 2.5, 3.5, 4.5, 5.5) before convergence — the scope (`make status` + LESSONS + Tier-1 extensions + observability docs across 9 buckets) generates more cross-section issues than smaller PRs. The trajectory was: imp-3 count 4 → 0 → 2 → 1 → 2 → 2 (iter-6 expected to be the convergence point):
   ```bash
   make review-plan-by-codex PLAN_FILE=docs/plans/2026-05-17-skill-pr5-observability-and-self-improvement.md ITERATION=1
   ```
2. **Pre-next-iter consistency self-check** (the very feature we shipped in PR #4):
   ```bash
   make review-plan-consistency-by-claude PLAN_FILE=docs/plans/2026-05-17-skill-pr5-observability-and-self-improvement.md ITERATION=N
   ```
3. **Mandatory human-approval gate** — surface final-plan summary; wait for approve.

### Phase 2 — post-implementation gates

1. `make check` green (existing 234 → ~240+ passing).
2. `make status` runs in skill repo + outputs all 7 sections (Current branch activity, Recent main activity, Open PRs, Active plan, Active lessons, Local repo state, Health checks).
3. `LESSONS.md` exists at root with 3 seed entries.
4. Tier-1 review (via `make review-commit-by-claude` or in-session subagent) on the first impl commit proposes an impl-log row.
5. Draft impl PR opened; `claude[bot]` Tier-2 fires (this repo is `--github-review=claude` mode). Codex Tier-2 GitHub bot is NOT configured in this skill repo (per `CLAUDE.md` line 97); `make review-commit-by-codex` (local Tier-1) serves as the Codex-side evidence instead (closes Codex iter-3 #2 — earlier gate wording demanded an impossible "Codex Tier-2 fires"). The planned `--enable-github-review` BACKLOG entry tracks retroactively adding Codex Tier-2 to this repo when desired.
6. Plan file's Implementation log section gets populated across impl commits (dogfood: this PR's own plan file gets its impl log populated as we ship).

## Iteration log (this plan)

| Iter | Findings | Verdict |
|---|---|---|
| 1 (codex) | 5 (4× imp-3, 1× imp-2) | do not implement yet; all 5 folded. Applied four-questions framework BEFORE deciding (a/b/c/d): every premise verified empirically (made doctor not in generated Makefiles ✓; SHARED_TEMPLATE_MAP doesn't list LESSONS.md ✓; original BACKLOG entry said "CLAUDE.md / AGENTS.md" ✓; CONTRIBUTING step 9 doesn't mandate row-append ✓; mtime-based plan-detect IS unreliable ✓). Folds: P1 inline health checks in `make status`; P2 add renderer wiring as Bucket E-pre; P3 mirror status-recovery + self-improvement loop in AGENTS.md; P4 mandate impl-log row append in CONTRIBUTING step 9; P5 add PLAN_FILE override for make status + multi-candidate warning |
| 1.5 (claude consistency self-check, between fold and iter-2) | 8 internal contradictions/drifts | dogfood of PR #4's `make review-plan-consistency-by-claude` target. 8 issues caught: glob-pattern drift (prose vs recipe), WARN-threshold drift (~24h claim missing in recipe), section-length cap inconsistent (10-line claim vs 50-line lessons recipe), CLAUDE.md placement contradiction ("byte-identical block or near-by" vs "NOT triage block"), missing test row for step-9 mandate, missing 3-seed-entry assertion home, "archived not promoted" vs "promotion allowed for fundamental", scope row 8 coverage scattered. All 8 folded as part of this iter (no separate iter row — this is the in-between self-check; iter-2 starts fresh after these fixes). Empirical: the new self-check target saved an entire Codex iter |
| 2 (codex) | 7 (0× imp-3, 6× imp-2, 1× imp-1) | needs another iter — all 7 folded. **Zero imp-3 = convergence trajectory**. Four-questions framework applied; all premises verified. Folds: P1 README.md filter in plan-detect; P2 fallback chain for "Recent main activity" (origin/main → main → HEAD); P3 plan-structure convention clarified + this plan's order verified; P4 evidence rows added for the 1.5 self-check; P5 "no manual rituals" → "semi-automatic capture" rename + BACKLOG path documented; P6 precise per-test wording for LESSONS smoke assertion; P7 `/simplify` Claude-Code-only gating wording. **Next iter expected: 0 imp-3 + ≤2 polish items** (trajectory matches PR #4: 5 → 5 → 5 → 5 → 5 → 5 with imp-3 4 → 2 → 1 → 2 → 2 → 2; here we already at 0 imp-3 after iter-2) |
| 2.5 (claude consistency self-check) | 6 substantive drifts between iter-2 fold prose and recipe | self-check pre-iter-3 caught: stale "4 buckets" heading, fallback chain in prose but not in recipe, README regex pattern mismatch (`grep -v README.md` vs `grep -vE 'README\.md$$'`), "entire" vs `head -50` for lessons, fallback message strings out of sync ("(no origin/main yet)" vs "(no commits yet)"), recipe didn't actually print top-3 candidates as prose claimed. All 6 folded by rewriting the Bucket A recipe sketch to satisfy the prose contracts + adding a "Recipe contracts" sub-list as the binding source of truth |
| 3 (codex) | 5 (2× imp-3, 3× imp-2) | needs another iter — all 5 folded. **imp-3 count bumped from 0 → 2** because iter-2 folds introduced cross-section issues that idea-(a)'s "where else does this affect" was supposed to catch but didn't. Self-criticism: I missed Q3 (cross-section impact) on the iter-2 "semi-automatic capture" fold (didn't think through commit-SHA implications) and the "AGENTS.md gets LESSONS append" fold (didn't think through read-only context). Folds: P1 docs-only impl-log commit pattern; P2 Codex Tier-2 acceptance gate waived (this repo is `claude` mode); P3 content assertions (not just headings) for status target; P4 PLAN_FILE optional input to review-commit-by-* targets; P5 writable-vs-read-only context split for LESSONS append. **Lesson for me: when folding a finding, treat Q3 (cross-section) more aggressively for second-order effects, not just textual mirrors** |
| 3.5 (claude consistency self-check) | 8 drifts (mostly wording-alignment) | pre-iter-4 self-check. Findings: (a) LESSONS size threshold mismatch (~50 lines vs <20 entries); (b) WARN wording prose vs recipe drift; (c) archive criteria stated 2 different ways; (d) health-check output wording drift ("missing" prose vs "not on PATH" recipe); (e) evidence row said "4 content assertions" but lists 5; (f) bad-PLAN_FILE handling required by tests but missing from recipe contracts; (g) docs-only-commit "trivial diff" exemption used but not added to scope; (h) vestigial "reviewer-notes" reference. All 8 folded via wording alignment + scope row 2 extension + bucket A case-(b) addition for missing-file PLAN_FILE override |
| 4 (codex) | 5 (1× imp-3, 4× imp-2) | needs another iter — all 5 folded. **imp-3 trajectory: 4 → 0 → 2 → 1**. Folds: P1 fence-aware section extraction for plan-tail (real implementation detail — this plan itself has fenced example + real section); P2 bad-PLAN_FILE handling actually wired into recipe; P3 seed entries rewritten in literal LESSONS.md schema format; P4 helper-script BACKLOG entry explicitly added to Bucket G with trigger; P5 `status` declared `.PHONY` + regression test. All real per four-questions. Convergence trajectory holding |
| 5 (codex) | 4 (2× imp-3, 1× imp-2, 1× imp-1) | **3-consecutive-iters at imp-3=1-2 plateau triggered** (iter-3: 2, iter-4: 1, iter-5: 2 — meets the project rule). P1 (backtick prompt — critical shell-substitution class) FOLDED in this iter (cannot defer; would break impl). P4 (iteration log bookkeeping) folded. **P2 + P3 surfaced to user via human-approval gate per the plateau rule. User decisions** (2026-05-18): P2 = (b) deferred to impl PR — Make-level argv-capture tests for PLAN_FILE runtime passthrough must be added to `tests/test_makefile_review_targets.py` during impl, NOT just the template-level tier1_prompt parameterization. P3 = (b) accepted-as-designed — multi-plan WARN+top-1 stays; the WARN line + top-3 candidate list IS the safety mechanism (human sees + re-invokes if wrong). User explicitly chose the "show the data, let human decide" approach over "tighten to require PLAN_FILE". One more iter requested |
| 6 (codex) | 4 (2× imp-3, 1× imp-2, 1× imp-1) | all 4 folded. **imp-3 trajectory now: 4 → 0 → 2 → 1 → 2 → 2** (3-iter plateau persists). Both imp-3 are real: P1 (current branch missing from status — feature-branch unmerged work invisible to recovery) is a real design gap; P2 (PLAN_FILE binding incomplete in subagent path) is a real coverage gap. Both folded properly: P1 via new "Current branch activity" section, P2 via macro signature update + subagent template binding. P3 + P4 trivial test/wording. **Decision (user, 2026-05-18)**: option (b) ship Plan PR now + option (c) split impl into 3 PRs. Rationale: 6 iters of substantive findings indicates 9-bucket scope generates more cross-section issues than one PR can fold; splitting impl into 5a/5b/5c preserves the converged plan while making each impl PR review-able. Plan PR ships as the shared contract; the 3 impl PRs each reference it |
| 6.5 (claude consistency self-check) | 9 drifts (user-prompted; almost forgot this step!) | self-check 6.5 was ALMOST SKIPPED — I committed + pushed the Plan PR straight from iter-6 fold to commit, in "ship now" mode. User pushed back ("why did not we do 6th self-check?"); ran it before merging. Findings: (1) Verification said "6 sections" but iter-6 added 7th; (2) recipe sketch missing the new "Current branch activity" block; (3) "four cases" enumeration was actually 5 (a-e); (4) Bucket C still had pre-iter-6 macro signature `tier1_prompt(commit_ref)`; (5) three different "no PLAN_FILE" fallback strings across surfaces; (6) content-assertion count "5" vs Bucket F's 4 lettered (a-d); (7) Impl PR #5b "4 new assertions" but only 3 land there (4th deferred to 5c); (8) `.PHONY status` recipe shows standalone block but contract says join existing; (9) iter-6 row left "options surfaced" without recording user's decision. All 9 folded as a follow-up commit on the open Plan PR. **Lesson surfaced for LESSONS.md once impl session opens**: "After folding any Codex iter's findings, ALWAYS run consistency self-check before committing the plan — even when 'ship now' mode is active. The self-check ritual matters MORE when in a hurry, not less." Caught 9 drifts that would have been Tier-2 review findings or impl-time landmines |
| Tier-2 (codex, GitHub PR review) | 1 imp-2 | Codex Tier-2 on PR #9 found that the CONTRIBUTING.md.tmpl subagent template would render with the literal `<PLAN_FILE>` placeholder as a non-empty string at bootstrap time — making the macro take the "PLAN_FILE is set" branch and ask reviewers to check drift against a placeholder path. Real bug introduced by iter-6 #2 fold (the macro signature update). **Premise verified** via four-questions: Jinja's `{% if plan_file %}` would treat `'<PLAN_FILE>'` as truthy. Fold: subagent template now ships TWO explicit variants — Variant A "with plan binding" uses `tier1_prompt('<SHA>', '<PLAN_FILE>')`, Variant B "code-correctness only" uses `tier1_prompt('<SHA>')`. Driver picks. Macro also treats empty-string equivalent to None for the unbound branch. Bucket F test row adds two new assertions: empty-string equivalence + both-variants-present substring check. **Lesson surfaced**: "When extending a Jinja macro inside a string-substituted template (like the CONTRIBUTING.md subagent block), trace what literal placeholder text becomes after rendering — `<PLAN_FILE>` is a non-empty string, not None." Will go to LESSONS.md once impl opens |

## Evidence table — what was folded and where

| Iter | Importance | Finding | Action |
|---|---|---|---|
| 1 | 3 | **(a) fold** — Codex iter-1 #1: `make status` invokes `make doctor` but generated language Makefiles (python/nodejs/go) don't define `doctor` — only skill-repo `Makefile` does. Verified by grepping the language Makefiles. Status would fail in every generated project | Bucket A recipe now inlines health checks directly (`command -v` for git/gh/claude/codex). Self-contained; works identically in skill repo + every generated project |
| 1 | 3 | **(a) fold** — Codex iter-1 #2: shared template `LESSONS.md.tmpl` would never reach generated projects without extending `bootstrap_lib/render.py`'s `SHARED_TEMPLATE_MAP`. Verified by reading `render.py:9` (no LESSONS.md entry) + smoke tests' expected-paths sets | Added new Bucket E-pre: renderer wiring + smoke-test expected-path updates for all 3 languages. CLAUDE/AGENTS.md "read LESSONS.md" instructions now point at a file that actually exists |
| 1 | 3 | **(a) fold** — Codex iter-1 #3: original BACKLOG entry's component-2 said "A `CLAUDE.md` / `AGENTS.md` instruction" but the plan only put the status-recovery + self-improvement instructions in CLAUDE.md. Codex's GitHub auto-reviewer + other AI reviewers read AGENTS.md, not CLAUDE.md. Verified by reading the original BACKLOG entry | Bucket D extended: both instructions land in BOTH `shared/CLAUDE.md.tmpl` AND `shared/AGENTS.md.tmpl` (plus dogfood mirrors). New dogfood-doc test asserts both surfaces carry both instructions |
| 1 | 3 | **(a) fold** — Codex iter-1 #4: Tier-1 "proposes" the impl-log row but CONTRIBUTING.md.tmpl step 9 doesn't require the driver to append it. Without enforcement the workflow doesn't actually deliver the "what shipped vs what planned" observability. Verified by reading step 9 of `shared/CONTRIBUTING.md.tmpl` | Bucket B extended: step 9 sub-bullet now MANDATES appending the suggested impl-log row (or marking N/A for trivial) BEFORE next commit / push. Same in `docs-plans-README.md.tmpl`. New doc-test asserts the mandate wording is present |
| 1 | 2 | **(a) fold** — Codex iter-1 #5: `ls -t docs/plans/*.md` is unreliable after checkouts, touching old plans, or when plan+impl files coexist. A wrong "active plan" defeats the whole post-compaction-recovery purpose | Bucket A `make status` now supports `PLAN_FILE=` override; falls back to mtime auto-detect; emits WARN when multiple recent candidates. New test in `tests/test_status_target.py` with multi-plan fixture asserts the warning fires |
| 1.5 | self-check | **8 contradictions caught by `make review-plan-consistency-by-claude` between iter-1 fold and iter-2** (closes Codex iter-2 #4 — earlier evidence table only listed iter-1 #1-5, not the self-check fixes). Findings: (a) glob-pattern drift (prose vs recipe); (b) WARN-threshold drift (~24h claim vs recipe count>1); (c) section-length cap inconsistent (10-line claim vs lessons-section 50-line head); (d) CLAUDE.md placement contradiction ("byte-identical block or near-by" vs "NOT triage block"); (e) test row for step-9 mandate missing from Bucket F; (f) 3-seed-entry assertion location missing; (g) "archived not promoted" vs "promotion allowed" (Design principle softened); (h) Bucket F coverage scattered (observational only) | All 8 folded into prose alignment + Bucket B/F updates. The self-check target paid for itself on iter-1.5 by catching what would otherwise have been iter-2 + iter-3 findings. Empirical: ~6 findings collapsed into one cheaper subagent pass |
| 2 | 2 | **(a) fold** — Codex iter-2 #1: `make status` plan-detect didn't filter `docs/plans/README.md` (which is always emitted) → fresh projects would see README as "the active plan" | Bucket A's plan-detect recipe now filters README via `grep -vE 'README\.md$'`; explicit handling for 0/1/N candidate cases; test in `test_status_target.py` covers fresh-bootstrap with only README |
| 2 | 2 | **(a) fold** — Codex iter-2 #2: "Recent main activity" assumed `origin/main` exists; fresh-bootstrap projects have local commits but no remote → would report "no origin/main" when there ARE relevant commits | Bucket A now uses fallback chain `origin/main` → `main` → `HEAD` with ref-name label. Test covers local-commits-no-remote case |
| 2 | 2 | **(a) fold** — Codex iter-2 #3: this plan's own section order violated the new Implementation-log-after-Evidence convention (Critical-files-to-read was placed BEFORE Implementation log; should be LAST). Plan was self-inconsistent | Bucket B prose now specifies "Implementation log + Lessons surfaced AFTER Evidence; Critical-files-to-read LAST". This plan's own section ordering already matches (Evidence → Impl log → Lessons surfaced → Critical files) |
| 2 | 2 | **(a) fold** — Codex iter-2 #4: 8 self-check folds documented in iteration log but not in evidence table → violated the plan's own triage rule | Added the 1.5 row above |
| 2 | 2 | **(a) fold** — Codex iter-2 #5: Design principle "no manual rituals" conflicted with the mandated driver-pastes-impl-log-row step. Internal contradiction | Renamed design principle to "Capture is semi-automatic"; explicitly acknowledged the trade-off; documented BACKLOG path (helper script) if it proves brittle |
| 2 | 2 | **(a) fold** — Codex iter-2 #6: smoke-test assertion wording was vague — Python/Node use dry-run stdout substring sets, Go uses smaller per-language list. Implementer could update the wrong assertion | Bucket F now specifies precise per-file changes + adds a common post-apply `target / "LESSONS.md"` assertion covering the actual file-write path |
| 2 | 1 | **(a) fold** — Codex iter-2 #7: `/simplify` wording in CONTRIBUTING.md read like a normal command, but it's Claude-Code-only. Generated projects' non-Claude users would see an un-runnable step | Bucket E wording now gates "Claude Code sessions only", explicit "skip if unavailable", "manual cruft pass instead" fallback. Doc-test asserts the gating wording is present |
| 2.5 | self-check | **6 wording-alignment drifts** caught by `make review-plan-consistency-by-claude` between iter-2 fold and iter-3 trigger: (1) stale "4 buckets" heading; (2) fallback chain in prose missing from recipe; (3) README regex pattern mismatch (`grep -v README.md` vs `grep -vE 'README\.md$$'`); (4) "entire" prose vs `head -50` recipe for Active lessons; (5) fallback message strings out of sync; (6) recipe didn't actually print top-3 candidates as prose claimed | All 6 folded by rewriting the Bucket A recipe sketch + adding "Recipe contracts" sub-list as the binding source of truth |
| 3.5 | self-check | **8 wording-alignment + scope drifts** caught between iter-3 fold and iter-4 trigger: (a) LESSONS size threshold mismatch (~50 lines vs <20 entries); (b) WARN wording prose vs recipe drift; (c) archive criteria stated 2 different ways; (d) health-check output wording drift ("missing" prose vs "not on PATH" recipe); (e) evidence row counted 4 content assertions but listed 5; (f) bad-PLAN_FILE handling required by tests but missing from recipe contracts; (g) docs-only-commit "trivial diff" exemption used but not added to scope; (h) vestigial "reviewer-notes" reference | All 8 folded via wording alignment + scope row 2 extension + Bucket A case-(b) addition for missing-file PLAN_FILE override |
| 4.5 | self-check | **8 drifts** caught pre-iter-5 — including the meta-finding that 2.5 + 3.5 self-check rows were missing from this very evidence table (the plan was violating its own iter-2 #4 rule). Other findings: inverted convention wording in iter-2 #3 row; health-check "missing" prose drift NOT fully fixed by 3.5; content-assertion 4-vs-5 count only half-fixed; Bucket D paragraph duplication; tier1_prompt byte-identity claim now in tension with new PLAN_FILE parameter; trivial-diff exemption "new vs existing" framing ambiguous; `$` vs `$$` regex representation inconsistency between prose and Makefile contexts | All 8 folded; the 2.5 + 3.5 rows now added (this and the previous two rows); inverted convention wording fixed; remaining wording polish applied; tier1_prompt test row updated to parameterized over PLAN_FILE values |
| 3 | 3 | **(a) fold** — Codex iter-3 #1: impl-log row append was specified as "before push" but didn't say HOW it becomes a durable commit. Amend-the-reviewed-commit changes the SHA (invalidates Tier-1 audit); skip-the-commit means the row never ships | CONTRIBUTING.md step 9 now explicitly says: create a SEPARATE docs-only commit for the impl-log row (e.g. "Append impl-log row for <short-sha>"). Trade-off acknowledged: docs-only commits qualify as trivial diff per CONTRIBUTING so they don't loop on Tier-1. Push both code commit + impl-log commit together. Plan-level convention in `docs-plans-README.md.tmpl` documents the same |
| 3 | 3 | **(a) fold** — Codex iter-3 #2: Verification phase 2 step 5 required "Codex Tier-2 fires" but this skill repo is `--github-review=claude` mode, NOT `both-docs`. Codex GitHub bot is NOT configured per the existing CLAUDE.md line 97. Gate was unsatisfiable as written | Step 5 reworded: claude[bot] Tier-2 fires (configured); Codex Tier-2 waived since not configured in this repo; `make review-commit-by-codex` (local Tier-1) serves as Codex-side evidence. References the existing `--enable-github-review` BACKLOG entry as the retroactive-config path |
| 3 | 2 | **(a) fold** — Codex iter-3 #3: `tests/test_status_target.py` assertions only checked section headings → empty-section bug would pass while defeating the recovery purpose | Test row extended with 4 lettered content assertions (a)-(d): (a) known iteration-log row content + known impl-log row content, (b) known LESSONS active title, (c) README exclusion from plan-detect, (d) bad-PLAN_FILE graceful handling. Iter-6 fold added 4 more lettered assertions (e)-(h) for contract coverage = 8 total assertions in 8 labels |
| 3 | 2 | **(a) fold** — Codex iter-3 #4: Tier-1 `review-commit-by-*` recipes don't take `PLAN_FILE=`, but the prompt asks reviewers to check "plan-impl drift" — without a plan reference, the reviewer picks an unspecified plan (mtime drift again) | `tier1_prompt` macro extended to take an optional plan-file argument; Makefile recipes pass it through. CONTRIBUTING.md step 9 says to invoke `make review-commit-by-claude PLAN_FILE=docs/plans/<active>.md`. When unset, prompt falls back to the canonical phrase: "no plan binding; limit findings to code-correctness, do not infer a plan file by mtime" (later strengthened in iter-6 #2 to apply to ALL Tier-1 entrypoints, not just Makefile recipes) |
| 3 | 2 | **(a) fold** — Codex iter-3 #5: Bucket D's LESSONS.md append instruction would land in BOTH `CLAUDE.md` AND `AGENTS.md` (per iter-1 #3 fold). AGENTS.md is read by review-only contexts (`make review-plan-by-codex`, etc.) which are explicitly told "Do NOT edit files". Append-during-review would violate read-only contract + dirty the repo mid-review | CLAUDE.md / AGENTS.md instruction split: in writable impl session, driver appends directly; in read-only review session, propose lesson in review output OR the plan's `Lessons surfaced` section. Driver triages reviewer-proposed lessons later in a writable session |
| 4 | 3 | **(a) fold** — Codex iter-4 #1: `make status` plan-section extraction was specified at conceptual level but the implementation detail "ignore fenced code blocks" was missing. Real risk: this very plan has an example `## Implementation log` inside a fenced block AND a real section at the bottom; a naive grep/awk would pick the fence. Legacy plans (PR #1–#4) lack impl-log entirely. Both must be handled | Bucket A contracts now require fence-aware extraction (awk that toggles fence-state on ` ```` lines); legacy plans fall back to "(no Implementation log section yet)". Test row in Bucket F asserts both cases (fence-skip + legacy-fallback) |
| 4 | 2 | **(a) fold** — Codex iter-4 #2: prose said "PLAN_FILE not found → print error + continue" but the recipe sketch just echoed `$(PLAN_FILE)` regardless. Test would fail or silently pass with stale data | Recipe sketch now has explicit `if [ -n "$(PLAN_FILE)" ] && [ ! -f "$(PLAN_FILE)" ]` branch printing `(PLAN_FILE not found: ...)` |
| 4 | 2 | **(a) fold** — Codex iter-4 #3: seed lessons were written as numbered list, but the schema test would enforce `### YYYY-MM-DD:` headings + Trigger/Rule/Status fields. Implementer copying the seeds verbatim would produce a schema-failing LESSONS.md | Seeds rewritten in literal LESSONS.md format with proper `### YYYY-MM-DD:` headings + bold Trigger/Rule/Status fields. Block is the literal file contents (modulo file header + section heading) |
| 4 | 2 | **(a) fold** — Codex iter-4 #4: design referenced "BACKLOG entry tracks this" for the helper-script-to-append-impl-log-row path, but Bucket G never actually added it. Promise was implicit only | Bucket G now lists the new BACKLOG entry explicitly with trigger ("if driver-forgets-to-paste happens twice post-PR-#5") + rough effort (~1 hour) |
| 4 | 2 | **(a) fold** — Codex iter-4 #5: new `status` Make target wasn't declared `.PHONY`. A file named `status` (e.g. accidentally created) would cause `make status` to no-op silently | Bucket A's recipe sketch now starts with `.PHONY: status`; shared template + dogfood Makefile `.PHONY:` line extended. Regression test creates a `status` file in the fixture + asserts the recipe still runs |
| 5 | 3 | **(a) fold** — Codex iter-5 #1: Tier-1 prompt extension I drafted used literal backticks in the example impl-log-row, exactly the shell-substitution class the existing `tier1_prompt` macro's defensive comment block warns against. Verified by reading the macro comment + tracing how the prompt becomes a double-quoted shell arg in the rendered recipe. **Lesson surfaced** (will be added to `LESSONS.md` once the impl session opens): "when extending a Jinja macro that's invoked inside a shell-quoted arg, re-read the macro's defensive comment block before adding examples — markdown formatting backticks WILL be interpreted as shell command substitution." | Rewrote the extension instruction in plain text (no backticks; literal pipe characters + angle-bracket placeholders). Added a new regression test (argv-capture shim) asserting the rendered prompt contains zero backticks AND zero `$(` substrings |
| 5 | 3 | **(b) defer to impl PR** — Codex iter-5 #2: `tier1_prompt` macro's new optional PLAN_FILE arg is template-level; runtime passthrough at the Make level (`make review-commit-by-codex PLAN_FILE=...`) is untested by the planned tests. Wrong-plan drift could regress without anyone noticing. **User decision (2026-05-18 human-approval gate): (b) defer to impl PR with explicit framing**. The impl PR's `tests/test_makefile_review_targets.py` MUST add Make-level argv-capture tests over PLAN_FILE set/unset for both codex + claude targets. Documented in Bucket C "Test scope for PLAN_FILE runtime passthrough" paragraph as a must-do during impl, NOT a "can be skipped" item |
| 5 | 2 | **(b) accepted-as-designed** — Codex iter-5 #3: `make status` multi-plan behavior (top-1 + WARN) still uses mtime to pick when 2+ candidates exist. Codex argued for tighter behavior (refuse to pick by mtime; require PLAN_FILE). **User decision (2026-05-18 human-approval gate): (b) keep current design**. Rationale: the WARN+candidate-list IS the safety mechanism — the human sees what's being picked + can re-invoke with explicit `PLAN_FILE=`; tightening would add friction to the recovery command itself. Bucket A prose updated to require the WARN line be "loud" (`!!!` markers + ALL-CAPS keyword) so a recovering agent reads it before acting on the tail |
| 5 | 1 | **(a) fold** — Codex iter-5 #4: iteration log had a 4.5 self-check row but no iter-5 row + Phase 1 verification still said "expect 1-2 iters" while this is iter 5 | Added iter-5 + 5.5 rows to iteration log + this batch of evidence rows. Phase 1 verification reworded to be historical/generic (not iter-count-specific) |
| 5.5 | self-check | **4 drifts** caught pre-iter-6: (1) iter-5 findings in iteration log but missing from evidence table — same rule violation iter-2 #4 fold was supposed to retire (now fixed by this batch of evidence rows); (2) WARN-line "loud" prose vs recipe drift (recipe has `WARN:` uppercase but no `!!!` markers as prose example suggests); (3) smoke-test assertion described differently between Bucket E-pre and Bucket F; (4) `/simplify` doc-test promised in Bucket E but not enumerated in Bucket F test row | All 4 folded: evidence rows added (this batch); WARN format aligned recipe-side; Bucket E-pre vs Bucket F descriptions reconciled; Bucket F test row 1 extended with the `/simplify` gating assertion |
| 6 | 3 | **(a) fold** — Codex iter-6 #1: `make status` "Recent main activity" used `origin/main → main → HEAD` fallback chain, so on a feature branch with `origin/main` present, it printed main history NOT the current branch's unmerged work — exactly the work the agent needs to see post-compaction | Bucket A restructured: section 1 is now "Current branch activity" (current branch name + `git log -10 HEAD`), section 2 is "Recent main activity" (the original fallback chain, kept as secondary for "what's already shipped"). Bucket F adds explicit "local-commits-no-remote" test |
| 6 | 3 | **(a) fold** — Codex iter-6 #2: PLAN_FILE binding was added to Makefile targets but the CONTRIBUTING.md.tmpl subagent template still invoked `tier1_prompt('<SHA>')` without the plan arg. In-session subagent reviews (the Claude Code path) could silently do unbound plan-drift checks | Macro signature now `tier1_prompt(commit_ref, plan_file=None)`. Subagent template invokes `{{ tier1_prompt('<SHA>', '<PLAN_FILE>') }}`. When plan_file is unset/empty, the rendered prompt says "no plan binding; limit findings to code-correctness, do not infer a plan file by mtime" — silent unbound drift impossible |
| 6 | 2 | **(a) fold** — Codex iter-6 #3: Bucket A contracts (fence-aware extraction, legacy no-impl-log fallback, .PHONY regression) demanded specific tests but Bucket F's test row didn't enumerate them. Implementer could ship without coverage of contracts the plan claimed were enforced | Bucket F's `tests/test_status_target.py` row extended with 4 contract-coverage assertions: (e) fence-aware extraction picks real section not fenced sample; (f) legacy plan no-impl-log fallback prints the expected line; (g) local-commits-no-remote shows HEAD commits; (h) file-named-`status` regression confirms `.PHONY` effective |
| 6 | 1 | **(a) fold** — Codex iter-6 #4: Phase 1 verification said "expect 1-2 iters" while this is iter 6 | Reworded as historical/generic: "run until convergence per stopping rule, OR human-approval gate at plateau. Historically this specific plan required 6 iters" + trajectory documented |

## Implementation log (this PR)

| Commit | What landed | Deviations from plan | Issues faced |
|---|---|---|---|
| f04624d | PR #5a impl: `make status` + LESSONS scaffold + renderer wiring + cross-session-recovery & self-improvement-loop docs in CLAUDE.md+AGENTS.md (Buckets A, D-partial, E-pre, F-subset) | none (Bucket F's smoke-test "post-apply path" deferred to Tier-1 fold) | none |
| f62feb9 | PR #5a Tier-1 self-review fold: 6 findings — smoke-test post-apply LESSONS assertions; real-plan-coexists-with-README test; "(no open PRs)" message; LESSONS in DOGFOOD_FILES_TO_SCAN; awk anchor; seed-entry assertion tightened | none | none |
| 4689d0b | PR #5a merged to main | none | Codex Tier-2 didn't auto-fire on ready-state (pattern: needed explicit @codex review). Worth a BACKLOG entry in PR #5c |
| 318bc71 | PR #5b impl: tier1_prompt(commit_ref, plan_file=None) macro + Makefile shell-IF passthrough + CONTRIBUTING dual-variant subagent template + step-9 MANDATED impl-log row append + plan-file structural convention (Buckets B, C, F-subset) | none | none |
| 39d9f6c | PR #5b Tier-1 self-review fold: 5 findings — claude without-PLAN_FILE test; apostrophe-s canonical phrasing; convention permits PR-specific subsections; tightened p_starts assertion; step-9 dogfood mirror test | none | Tier-1 reviewer noted PR #5b is the first commit to actually dogfood the impl-log-append workflow it ships — this very row is the proof |

## Lessons surfaced (this PR)

- **Codex Tier-2 auto-fire on ready-state is unreliable** — twice in PR #5 / #5a we marked a PR ready and waited 15+ min before triggering Codex explicitly with `@codex review`. Either (a) document the pattern (always `@codex review` post-ready) or (b) investigate the GitHub-app trigger config. Going into the BACKLOG in PR #5c.

(Other lessons captured directly in `LESSONS.md` per the writable-session-only append rule.)

## Lessons surfaced (this PR)

(Empty until impl PR finds something new.)

## Critical files to read before each iter's review

For Codex / Claude:
- `docs/plans/2026-05-16-skill-pr4-two-tier-review-loop-improvements.md` — most recent precedent (similar workflow PR shape)
- `shared/Makefile.review.tmpl` — where `make status` lives + where `tier1_prompt` macro is
- `shared/CONTRIBUTING.md.tmpl` — where `/simplify` doc lands + Tier-1 step
- `shared/CLAUDE.md.tmpl` — where self-improvement loop instructions land
- `BACKLOG.md` — "Cross-session / post-compaction state recovery" entry being closed out
- `tests/test_makefile_review_targets.py` — pattern for shim-based tests for the new `make status` target
