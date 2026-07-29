# Skill PR #4 — Two-tier code review + plan-loop improvements

## Context

The skill currently ships:
- **Tier-2 GitHub auto-review** (Codex bot + `claude[bot]` workflow) — opt-in via `--github-review={none,claude,both-docs}`.
- **Plan-review loop** via `make review-plan-by-{codex,claude}` (synchronous local).

What's weak / missing:

1. **No Tier-1 commit-level review.** Acme uses a manual subagent-spawn pattern after each focused commit; the user named this "really a genius thing". That's the catcher for *tests passing for the wrong reason* / plan-impl drift / contracts the author missed. The skill has nothing analogous.
2. **Plan-review loop drifts under iteration.** PR #3 took 7+ iterations to converge. Repeating failure mode: Codex flags an issue → Claude folds → fold introduces a contradiction with a different section of the plan → next Codex iteration catches the new contradiction. Result: subscription tokens burned, ceremony fatigue.

### Honest skeptical reactions to the user's two ideas

| User's idea | My take | Decision |
|---|---|---|
| **(a)** Reviewer prompt should also flag *where else in the plan* a finding has effect ("three paragraphs above already says X — that needs to change too"). The "explain why important + advise how to fix" half of the idea is **already in the existing prompt** (`why it matters` + `concrete suggested change` fields). The new value is the cross-section impact analysis. | Genuinely good. PR #3's iter-6→7 trajectory is exactly this pattern — Codex iter-6 flagged a worktree bug on Makefile.tmpl:17; the iter-6 fold introduced a parallel bug on Makefile.tmpl:24 that iter-7 had to catch. If iter-6 had been instructed to look beyond the flagged line, iter-7 would not have been needed. Asymmetric payoff: even 30% useful "also check X" hints save iterations. Marginal token cost (~300 chars to a ~1400-char prompt). | **Adopt.** |
| **(b)** Claude (author) re-reads whole plan after each fold to catch self-introduced contradictions before invoking next Codex iter. | Right intuition, wrong implementation. In-chat re-read = whole plan tokens × N iterations in driving session — that's what's burning the subscription. Implement as a fresh Claude subagent via a new Makefile target: same scope (full plan), isolated context, focused prompt ("find contradictions only — don't critique design"). User chose this refinement. | **Adopt as fresh-subagent target.** |

### Additional ideas I considered and did NOT include (open for redirection)

- **Alternate reviewers between iterations.** Currently both Codex + Claude fire per iter; findings are largely independent so loop cost doubles. Could alternate. Risk: Claude sometimes catches what Codex misses; alternating means iter-N might be blind to that class. Skipped — fix the contradiction problem first and see if loop length drops on its own.
- **Tighter convergence threshold post-iter-3** ("only fold imp-3, park all imp-1/2"). Already implied by the "watch trajectory" rule; making it normative changes ship quality. Out of scope.
- **Compact the prompt itself.** Current prompt is small relative to the plan content the reviewer reads. Marginal savings. Skipped.

## Scope

**PR shape: Plan PR (#7) → Impl PR (#8).** Both improvements bundle into ONE design since they share the (a/b/c/d) triage rule and the byte-identical `Makefile.review.tmpl` region. Per user decision.

**Tier-1 trigger model**: documentation + Makefile targets, no auto-fire post-commit hook. Per user decision.

### IN scope

| # | Change | Where |
|---|---|---|
| 1 | Tier-1 commit-review targets (`review-commit-by-codex`, `review-commit-by-claude`) | `shared/Makefile.review.tmpl` (byte-identical region) + skill-repo `Makefile` |
| 2 | Tier-1 workflow docs | `shared/CLAUDE.md.tmpl`, `shared/AGENTS.md.tmpl`, `shared/CONTRIBUTING.md.tmpl` + skill-repo `CLAUDE.md` |
| 3 | Plan-review prompt enhancement (idea **a**) — append "also identify other plan sections this finding affects" | `review-plan-by-{codex,claude}` recipes (both repo + shared template) |
| 4 | New consistency self-check target (idea **b**) — `review-plan-consistency-by-claude` | Same Makefile + shared template |
| 5 | Loop-workflow doc update describing when to run the self-check + the two-tier review | `shared/CLAUDE.md.tmpl`, `docs/plans/README.md`, skill-repo `CLAUDE.md` |
| 6 | Tests for new targets, new prompt content, byte-identity | `tests/test_shared_templates.py`, `tests/test_selftest_overlap.py` (existing — gates byte-identical region) |
| 7 | BACKLOG cleanup | Move "Retroactively add triage rule to Acme" → now actionable; add `--enable-github-review` + `review-plan-fact-check-by-*` entries (skill-repo + template backlogs as appropriate) |
| 8 | Triage rule extension — "four questions to ask before deciding (a/b/c/d)" | Byte-identical block in `shared/CLAUDE.md.tmpl` + `shared/AGENTS.md.tmpl` + `shared/docs-plans-README.md.tmpl` (and the three dogfood mirrors). NEW `tests/test_triage_byte_identity.py` enforces (closes Codex iter-6 #2 — existing dogfood test only checked heading presence, not full block identity) |
| 9 | Env scrubber: drop new review-target Make variables before nested CLI invocation | `scripts/run-with-clean-env.py` + `shared/scripts-run-with-clean-env.py.tmpl`: extend `EXACT_DROP` with `REVIEW_COMMIT_SHA`, `REVIEW_COMMIT_OUT_CODEX`, `REVIEW_COMMIT_OUT_CLAUDE`, `PLAN_CONSISTENCY_OUT`. Extend `tests/test_env_scrubber.py` to assert all four are dropped. Closes Codex iter-6 #4 — without this, command-line Make vars set via `make VAR=val target` leak into the nested codex/claude process |

### NOT in scope

- No post-commit git hook auto-fire for Tier-1.
- No changes to GitHub Tier-2 workflows (`claude-review.yml`, Codex GH integration).
- No reviewer alternation, no convergence-threshold change.
- No new CLI flag (`--review-mode` etc.); the Makefile targets are the surface area.

## Subsystem breakdown

### Bucket A — Tier-1 commit-review Makefile targets

In the byte-identical SELFTEST-OVERLAP region of `shared/Makefile.review.tmpl` (mirrored in skill-repo `Makefile`).

**Single-source prompt via Jinja macro** (closes Codex iter-2 #4 — earlier draft had the prompt duplicated in Makefile recipe AND CONTRIBUTING.md template, drift between them was possible. Jinja `{% macro %}` makes drift impossible by construction).

**`{% raw %}` wrapper migration** (closes Codex iter-5 #4): the current `shared/Makefile.review.tmpl` wraps its entire body in `{% raw %}{% endraw %}` (verified: file starts with `{% raw %}# ── Plan-review automation` and ends with `# SELFTEST-OVERLAP-END: shared/Makefile.review.tmpl{% endraw %}`). Inside `raw`, Jinja statements like `{% macro %}` and `{{ tier1_prompt(...) }}` render LITERALLY — they do not evaluate. The macro design requires the wrapper to be relocated so that:
- The macro definition lives OUTSIDE the raw block (top of file).
- The macro call sites in the Makefile recipes are OUTSIDE the raw block (Jinja must evaluate `{{ tier1_prompt('HEAD') }}` for it to substitute the rendered prompt).
- The rest of the Makefile body — `$(VAR)`, `$$(shell ...)`, etc. — can stay inside raw blocks if defensive isolation is desired, OR raw can be removed entirely (Make's `$()` syntax doesn't actually collide with Jinja's `{{ }}` / `{%  %}`; the original raw wrapper was probably defensive overkill).

Plan: remove `{% raw %}` wrapper from `shared/Makefile.review.tmpl` entirely. Verify by rendering the template through the existing `bootstrap_lib.render` pipeline against a test context and asserting the existing `review-plan-by-*` recipes produce byte-identical output to the current `Makefile` (existing `tests/test_selftest_overlap.py` Makefile-review-section check enforces this). If any Make-vs-Jinja collision surfaces during impl, fall back to selective raw blocks around the affected recipes only — but expectation is that none will.

The shared template `shared/Makefile.review.tmpl` defines the prompt as a macro at the top (outside any raw block):

```jinja2
{%- macro tier1_prompt(commit_ref) -%}
Review commit {{ commit_ref }} on this branch. Run 'git log -1 --stat {{ commit_ref }}' and 'git show {{ commit_ref }}' to see the diff, then VERIFY against the actual codebase — not just the diff. This is a Tier-1 code review. Focus on: tests that pass for the wrong reason, plan-impl drift (does the commit match what the plan says?), missing-await / sys.path / module-init bugs that the diff alone cannot reveal, contract bugs the author may have missed (function callers? config consumers?), missing edge-case coverage, semantic-boundary mismatches between docs and code, regressions in nearby code touched by the commit's imports/exports. Return findings ordered by importance (3=blocker, 2=improvement, 1=polish). For each finding: file:line, importance, what is wrong, why it matters, concrete suggested fix, AND identify any other files where the same fix should apply for consistency. Do NOT edit files. If there are no importance-3 findings, say so explicitly.
{%- endmacro -%}
```

**Critical**: the macro body contains NO backticks and NO `$()` — those would trigger shell command substitution when the macro is rendered into a Makefile recipe and passed as a double-quoted shell arg. Single quotes (`'git log ...'`) are fine because they're literal characters in the prompt text, not shell quotes. (Closes Codex iter-3 #1: prior draft had backticks around `git log` / `git show`; shell would have run them locally and injected the OUTPUT into the prompt, mangling it for large commits and risking argv-length limits. Real bug.)

The macro is invoked from BOTH the Makefile recipe (`{{ tier1_prompt('HEAD') }}`) AND `shared/CONTRIBUTING.md.tmpl`'s subagent prompt section (`{{ tier1_prompt('<SHA>') }}` — `<SHA>` is rendered as a literal placeholder for the human to substitute). Single source of truth at the macro level. Bucket E still adds a defensive byte-identity test on the two RENDERED strings to catch the case where someone forgets the `{% from ... import %}` and inlines a divergent prompt.

**Makefile recipes** (output paths keyed by commit SHA per Codex iter-1 #7; git-aware guards per Codex iter-2 #3):

```makefile
# Output paths keyed by commit SHA (closes Codex iter-1 #7)
REVIEW_COMMIT_SHA        ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo nogit)
REVIEW_COMMIT_OUT_CODEX  ?= /tmp/review-commit-$(REVIEW_COMMIT_SHA)-by-codex.md
REVIEW_COMMIT_OUT_CLAUDE ?= /tmp/review-commit-$(REVIEW_COMMIT_SHA)-by-claude.md

# All review-section targets declared phony (closes Codex iter-3 #2):
.PHONY: review-plan-by-codex review-plan-by-claude \
        review-commit-by-codex review-commit-by-claude \
        review-plan-consistency-by-claude \
        preflight-review-tooling
# Note: `_require-git-and-commit` removed — guards inlined in each
# consumer recipe (closes Codex iter-4 #1; prereq target with `exit 0`
# does NOT halt the consumer in Make).

review-commit-by-codex:	## Codex review of the most recent commit (Tier-1)
	@if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  echo "skipping: not a git repo"; exit 0; \
	fi; \
	if ! git rev-parse --verify HEAD >/dev/null 2>&1; then \
	  echo "skipping: no commits yet — Tier-1 reviews a specific commit; make one first"; exit 0; \
	fi; \
	if ! command -v codex >/dev/null 2>&1; then \
	  echo "codex CLI not found. Install + log in first (see CONTRIBUTING.md)."; exit 1; \
	fi; \
	$(CURDIR)/scripts/run-with-clean-env.py -- \
	  codex exec \
	    -C "$(CURDIR)" \
	    --sandbox read-only \
	    --color never \
	    --output-last-message "$(REVIEW_COMMIT_OUT_CODEX)" \
	    "{{ tier1_prompt('HEAD') }}" \
	  && cat "$(REVIEW_COMMIT_OUT_CODEX)"

review-commit-by-claude:	## Claude review of the most recent commit (Tier-1)
	@if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  echo "skipping: not a git repo"; exit 0; \
	fi; \
	if ! git rev-parse --verify HEAD >/dev/null 2>&1; then \
	  echo "skipping: no commits yet — Tier-1 reviews a specific commit; make one first"; exit 0; \
	fi; \
	if ! command -v claude >/dev/null 2>&1; then \
	  echo "claude CLI not found. Install + log in first (see CONTRIBUTING.md)."; exit 1; \
	fi; \
	$(CURDIR)/scripts/run-with-clean-env.py -- \
	  claude --print --permission-mode plan --add-dir "$(CURDIR)" \
	    --output-format text \
	    "{{ tier1_prompt('HEAD') }}" \
	  > "$(REVIEW_COMMIT_OUT_CLAUDE)" \
	  && cat "$(REVIEW_COMMIT_OUT_CLAUDE)"
```

**Failure preservation** (closes Codex iter-5 #1): the recipes end with `&& cat` (not `; cat`). If the paid CLI exits nonzero (auth failure, rate-limit, sandbox error), `cat` does NOT run and `make` returns nonzero. A `; cat` chain would have hidden the failure because `cat` succeeds on any pre-existing output file. New shim test in Bucket E injects a fake CLI that exits 42 and asserts the make target also exits nonzero.

**Dirty-worktree warning** (closes Codex iter-6 #3): the prompt asks the reviewer to "verify against the actual codebase". If the worktree has uncommitted changes (staged or unstaged), the codebase the reviewer sees may NOT match the commit being reviewed — reviewer could flag bugs that are already fixed in unstaged changes, or vice versa. Add a soft check BEFORE invoking the paid CLI: `if ! git diff --quiet || ! git diff --cached --quiet; then echo "WARN: worktree has uncommitted changes; reviewer will see the dirty state, not just HEAD"; fi`. WARN-and-proceed (not block) — legitimate uses exist (reviewing the commit you just made while staging the next one). Shim tests in Bucket E assert the warning fires for staged + unstaged dirt + still invokes the CLI.

The git-aware guards (`git rev-parse --is-inside-work-tree` for worktree-safety, `git rev-parse --verify HEAD` for no-commits-yet safety) are INLINED into each recipe in the same shell scope using `\` continuation — so the early `exit 0` actually halts the whole recipe (closes Codex iter-4 #1; same combined-shell pattern as PR #3's Go install-hooks). A separate prereq target would NOT have halted the consumer.

Why a Makefile target (vs pure docs):
- Generated projects get it for free; not Claude-Code-only.
- Byte-identical selftest gates both targets + the macro against drift.
- Discoverable via `make help`.
- Works for both Claude users (in-session subagent OR `make review-commit-by-claude`) and Codex users (just the Makefile target).

### Bucket B — Plan-review prompt enhancement (idea a)

Append to the existing `review-plan-by-codex` + `review-plan-by-claude` prompts (single new sentence at the end, before "End with a stop/go verdict"):

> "**For each finding, also identify any OTHER sections of the same plan that need updating for consistency if this finding is folded.** Look at headings, tables, the iteration log, the evidence table, the architecture-decisions section — flag any place where the plan text would contradict the folded change. This catches the failure mode where folding one finding silently introduces a new contradiction with another section."

Length: ~+300 chars on a ~1400-char prompt. The byte-identical region grows but stays under selftest control.

### Bucket C — Consistency self-check target (idea b refined)

New Makefile target in the same byte-identical region:

```makefile
# Output path keyed by plan slug + iteration (closes Codex iter-1 #7)
PLAN_CONSISTENCY_OUT ?= /tmp/review-plan-consistency-$(notdir $(basename $(PLAN_FILE)))-iter-$(ITERATION).md

review-plan-consistency-by-claude:	## Self-check: scan plan for self-contradictions after a fold (PLAN_FILE=... [ITERATION=N])
	@test -n "$(PLAN_FILE)" || \
	  { echo "Usage: make review-plan-consistency-by-claude PLAN_FILE=docs/plans/<file>.md [ITERATION=N]"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	@command -v claude >/dev/null 2>&1 || \
	  { echo "claude CLI not found."; exit 1; }
	$(CURDIR)/scripts/run-with-clean-env.py -- \
	  claude --print --permission-mode plan --add-dir "$(CURDIR)" \
	    --output-format text \
	    "Read the plan file at $(PLAN_FILE) in full. Your ONLY job: find internal contradictions, doc-drift between sections, and places where the latest fold's wording is inconsistent with adjacent rows / tables / sections. Do NOT critique the design, scope, completeness, or correctness — that is the Codex/Claude full-review job. Just identify pairs: 'Section X says A, Section Y says B, they disagree because Z'. If the plan is internally consistent, say so explicitly. Output as a numbered list. Be terse." \
	  > "$(PLAN_CONSISTENCY_OUT)" \
	  && cat "$(PLAN_CONSISTENCY_OUT)"
```

**When to run** (documented in `shared/CLAUDE.md.tmpl`):

After a Codex/Claude review iteration's findings are folded into the plan, AND BEFORE invoking the next iteration of `review-plan-by-codex`, run this target with the SAME `ITERATION=N` as the next planned reviewer run (closes Codex iter-2 #5 + iter-6 #5 — the Makefile defaults `ITERATION ?= 1`, so omitting it doesn't produce empty suffix but it DOES clobber the `iter-1` output every time, hiding earlier runs):

```bash
make review-plan-consistency-by-claude PLAN_FILE=docs/plans/<file>.md ITERATION=2
```

If it returns contradictions, fix them BEFORE the next reviewer pass. This closes the "fold-introduces-drift" failure mode at the cheapest moment (a single focused subagent, not a full reviewer pass).

Cost analysis: one Claude subagent invocation per fold-iteration. Prompt is narrow ("find contradictions only"), plan size is small (~200-line markdown for a typical PR plan). Total tokens per call: plan size + ~500-char prompt = a fraction of a full reviewer pass. Net effect: pays for itself if it saves ≥1 reviewer iteration per loop.

### Bucket D — Workflow documentation

#### `shared/CLAUDE.md.tmpl` (and mirror in skill-repo `CLAUDE.md`)

Add new short section "**Two-tier code review**" *after* the existing "Triaging review findings" section (closes Codex iter-4 #7 — the section references "(a/b/c/d) triage rule above", which is only correct if Two-tier comes AFTER the triage rule, not between Plan-review-loop and triage). CLAUDE.md is the FIRST thing Claude reads each session — must stay terse; full pattern + prompt template live in `CONTRIBUTING.md`.

THREE Jinja-conditional variants (closes Codex iter-2 #1 — earlier draft grouped `claude` + `both-docs` together, but tests distinguish them: `claude` gets ONLY `claude[bot]`; `both-docs` adds Codex docs; only `both-docs` mentions `@codex review`):

**`github_review_mode == 'both-docs'` variant** (Tier-2 with both bots):

```markdown
## Two-tier code review

For substantive implementation PRs (multi-commit / cross-cutting), use BOTH tiers; neither catches what the other does.

- **Tier-1 (after each focused commit, before push)**: `make review-commit-by-claude` or `make review-commit-by-codex`. Catches plan-impl drift, tests-passing-for-wrong-reason, contracts the author missed.
- **Tier-2 (after push)**: `claude[bot]` auto-fires on PR open / draft→ready via `.github/workflows/claude-review.yml`. Codex (configured via web UI per `docs/codex-github-review-setup.md`) reviews on PR open + draft→ready; re-trigger after subsequent pushes with `@codex review`. Catches "could only be discovered by running" class.

Both tiers feed the same (a/b/c/d) triage rule above. Full pattern (prompt template + when-to-skip rules) in `CONTRIBUTING.md`.
```

**`github_review_mode == 'claude'` variant** (claude[bot] only, no Codex docs):

```markdown
## Two-tier code review

For substantive implementation PRs (multi-commit / cross-cutting), use BOTH tiers; neither catches what the other does.

- **Tier-1 (after each focused commit, before push)**: `make review-commit-by-claude` or `make review-commit-by-codex`. Catches plan-impl drift, tests-passing-for-wrong-reason, contracts the author missed.
- **Tier-2 (after push)**: `claude[bot]` auto-fires on PR open / draft→ready via `.github/workflows/claude-review.yml`. Re-trigger after subsequent pushes by commenting `@claude review this` on the PR. Catches "could only be discovered by running" class. (Codex GitHub bot is NOT configured in this project. Retroactively adding it is non-trivial today — see BACKLOG for the planned `--enable-github-review` flag.)

Both tiers feed the same (a/b/c/d) triage rule above. Full pattern (prompt template + when-to-skip rules) in `CONTRIBUTING.md`.
```

**`github_review_mode == 'none'` variant** (no Tier-2):

```markdown
## Two-tier code review

For substantive implementation PRs (multi-commit / cross-cutting), run `make review-commit-by-claude` or `make review-commit-by-codex` after each focused commit, before push. This is Tier-1: catches plan-impl drift, tests-passing-for-wrong-reason, contracts the author missed.

This project did NOT enable GitHub auto-review at bootstrap (`--github-review=none`); Tier-2 is therefore not configured. Adding it retroactively is non-trivial today — see BACKLOG for the planned `--enable-github-review` flag (closes Codex iter-2 #2 — the `bootstrap.py --apply` re-run path needs all args + `--overwrite-existing` + a diff/inspection step, too clunky for user-facing docs).

Triage Tier-1 findings per the (a/b/c/d) rule above. Full pattern (prompt template + when-to-skip rules) in `CONTRIBUTING.md`.
```

**Skill-repo dogfood** uses the `claude` variant — the repo IS in `--github-review=claude` mode (confirmed via `tests/test_selftest_overlap.py:33` `SKILL_REPO_CONTEXT["github_review_mode"] = "claude"` and the existence of `.github/workflows/claude-review.yml`). Earlier draft wrongly said `none` (closes Codex iter-2 #1).

The Acme calibration anecdote stays only in THIS plan body (Context section) — NOT in shared / dogfood docs (closes Codex iter-1 #2; `tests/test_shared_templates.py` `FORBIDDEN_TERMS` includes `acme`, would fail).

Also extend the existing "Plan review loop" section with one line:

> "Between folding an iteration's findings and invoking the next iteration's reviewer, run `make review-plan-consistency-by-claude PLAN_FILE=... ITERATION=N` (where N is the upcoming reviewer iteration). If it surfaces contradictions, fix them before triggering the next iteration — much cheaper than letting the next reviewer pass find them."

#### `shared/CONTRIBUTING.md.tmpl`

(closes Codex iter-1 #1 — Tier-1 must run AFTER the focused commit so `git show HEAD` reviews the right change, not before commit):

Insert as a sub-bullet under existing step 9 (Commit) rather than a fractional step number — GitHub Markdown ordered lists require integer markers, `9.5.` would render as plain text and break the list (closes Codex iter-3 #4):

```markdown
9. **Commit in focused units** (existing step):
   - One commit per logical change.
   - Imperative title + body explaining "why".
   - Keep formatting-only commits separate from logic.
   - **For substantive PRs, run Tier-1 review on the commit you just made (before push)**:
     ```bash
     make review-commit-by-claude    # or review-commit-by-codex
     ```
     Triage findings per the (a/b/c/d) framework in `CLAUDE.md`.
     - **Blockers**: fix and either `git commit --amend` (if not yet pushed) or create a follow-up focused commit. Then **rerun `make review-commit-by-*`** on the corrected commit until no importance-3 findings remain (closes Codex iter-3 #5 — earlier draft skipped re-review after amend; weakened the "after each focused commit" contract). Then `make check`. THEN push.
     - For trivial diffs (typo, single-line refactor): skip Tier-1; rely on {% if github_review_mode in ['claude', 'both-docs'] %}Tier-2 + `make check`{% else %}`make check`{% endif %} (closes Codex iter-4 #3 — `none`-mode users have no Tier-2; the unconditional wording was misleading for the default mode).
```

ALSO add a new section "**Tier-1 review — prompt template for in-session subagents**" at the bottom of CONTRIBUTING.md.tmpl (closes Codex iter-1 #6). Renders via the same `tier1_prompt` Jinja macro defined in `shared/Makefile.review.tmpl` (closes Codex iter-2 #4 — single source of truth):

```jinja2
{% from 'Makefile.review.tmpl' import tier1_prompt %}

### Tier-1 review — prompt template for in-session subagents

Claude Code sessions (only) can run Tier-1 via a fresh `general-purpose` subagent instead of the Makefile target — useful when you want to ask follow-up questions interactively. Pass the subagent this prompt verbatim (substituting your commit SHA for `<SHA>`; get it from `git log -1 --pretty=%H`):

> "{{ tier1_prompt('<SHA>') }}"

(For non-Claude-Code sessions, just run `make review-commit-by-claude` or `make review-commit-by-codex` — the same prompt fires, rendered with `HEAD` instead of `<SHA>`.)
```

#### `docs/plans/README.md` (BOTH `shared/docs-plans-README.md.tmpl` AND dogfood `docs/plans/README.md`)

Update the loop description: insert the self-check step + reference the new Two-tier section. **Must update both halves of the byte-identical pair** — `tests/test_selftest_overlap.py:80` enforces byte-identity of `shared/docs-plans-README.md.tmpl` (rendered with skill-repo context) vs dogfood `docs/plans/README.md`. Updating one half alone fails the selftest (closes Codex iter-5 #2).

Same byte-identity discipline applies to every selftested pair touched by this PR:
- `shared/CLAUDE.md.tmpl` ↔ skill-repo `CLAUDE.md` (new dogfood test added in Bucket E)
- `shared/AGENTS.md.tmpl` ↔ skill-repo `AGENTS.md` (existing `tests/test_dogfood_doc_sanity.py` byte-identity check covers the triage block)
- `shared/docs-plans-README.md.tmpl` ↔ `docs/plans/README.md` (existing `tests/test_selftest_overlap.py:80`)
- `shared/Makefile.review.tmpl` ↔ skill-repo `Makefile` (existing `tests/test_selftest_overlap.py` Makefile review-section check)
- `shared/CONTRIBUTING.md.tmpl` ↔ skill-repo `CONTRIBUTING.md` (manual mirror — no selftest currently; in scope to add)
- `shared/BACKLOG.md.tmpl` ↔ skill-repo `BACKLOG.md` (manual mirror; no selftest)

Every Bucket-D edit must touch BOTH halves of any selftested pair. Tests will surface drift; this note exists so the impl PR doesn't miss the dogfood half.

#### Skill-repo `CLAUDE.md` (root, dogfood overlay)

Mirror the `claude` variant — the skill repo IS in `--github-review=claude` mode (see Bucket D verification above). **Drift between rendered template + dogfood doc is NOT currently checked by `tests/test_selftest_overlap.py`** (closes Codex iter-4 #5 — earlier draft incorrectly claimed this; the existing selftest covers .editorconfig, claude-review.yml, pull_request_template.md, docs/plans/README.md, Makefile review-section — but NOT root `CLAUDE.md`). Bucket E adds a NEW dogfood test for this drift surface.

#### Triage rule extension — "think before deciding" (user-directed)

The existing "Triaging review findings" section is byte-identical across three templates (`shared/CLAUDE.md.tmpl`, `shared/AGENTS.md.tmpl`, `shared/docs-plans-README.md.tmpl`) and three dogfood docs (root `CLAUDE.md`, `AGENTS.md`, `docs/plans/README.md`). `tests/test_dogfood_doc_sanity.py` enforces byte-identity.

Insert a new subsection at the END of the existing triage block, BEFORE the "Calibration" paragraph:

```markdown
**Before deciding (a/b/c/d), ask these four questions** — addresses the failure mode where the driver applies the reviewer's suggested fix verbatim without checking whether the fix is the right one:

1. **Is the premise correct?** Does the reviewer actually understand the current state of the code/plan, or is it inferring from incomplete info? Spot-check the reviewer's claim against the file it cites. If wrong → (c) reject the imp-3 framing.
2. **Is the suggested fix the best fix, or just *a* fix?** What else solves the same problem? Often there's a smaller / more localized fix the reviewer didn't see. If the reviewer's fix introduces complexity the alternative doesn't → use the alternative.
3. **What else does this finding imply?** If the bug is X, are there *other* instances of X in the plan you should audit while you're here? Same shape as the reviewer's own "where else does this affect" instruction — apply it to yourself.
4. **Does folding introduce a contradiction with another section of the plan?** Re-read the sections the fold touches before saving. (The `make review-plan-consistency-by-claude` target does this systematically — run it after every fold.)

These four questions add ~30 seconds per finding. They catch the failure mode where the driver folds in the suggested fix only to find the reviewer was extrapolating, OR the fix introduces a new contradiction the next iter has to catch.
```

The byte-identical region grows ~12 lines. Same `tests/test_dogfood_doc_sanity.py` invariant covers it.

### Bucket E — Tests

| File | New / Updated assertion |
|---|---|
| `tests/test_shared_templates.py` | Assert `Makefile.review.tmpl` renders new targets (`review-commit-by-codex`, `review-commit-by-claude`, `review-plan-consistency-by-claude`). Assert the plan-review prompt inside the rendered Makefile contains `"OTHER sections of the same plan"`. **Macro-rendered prompt invariant** (closes Codex iter-2 #4): extract the rendered Tier-1 prompt from BOTH the Makefile recipe (`tier1_prompt('HEAD')`) and the CONTRIBUTING.md template block (`tier1_prompt('<SHA>')`); normalize by substituting the commit ref placeholder; assert they are byte-identical (full-text equality, not just key-phrase substring). Drift impossible by macro construction, but the test asserts the invariant explicitly. Assert THREE CLAUDE.md Two-tier variants render correctly: `claude` variant mentions `claude[bot]` but NOT `@codex review` / `chatgpt-codex-connector`; `both-docs` variant mentions both; `none` variant mentions neither and references the planned `--enable-github-review` BACKLOG entry (closes Codex iter-2 #1). |
| `tests/test_makefile_review_targets.py` (existing — closes Codex iter-1 #5 + iter-4 #6 + iter-6 #1) | Extend with shim-based execution tests for the 3 new targets. **Hermetic git setup**: create a tempdir, `git init -q`, `git -c user.name=test -c user.email=test@example.com commit --allow-empty -m "fixture"`, then test. (1) `review-commit-by-codex` materializes `$(REVIEW_COMMIT_OUT_CODEX)`; output path's SHA fragment matches `git rev-parse --short HEAD` from the test fixture (NOT a fixed-7-char assertion — `core.abbrev` config can vary). (2) Same for `review-commit-by-claude`. (3) `review-plan-consistency-by-claude PLAN_FILE=... ITERATION=N` writes `$(PLAN_CONSISTENCY_OUT)` keyed by slug+iter. (4) **Shim-argv regression test** (closes Codex iter-3 #1 properly): the shim captures the argv passed to it; assert it contains the literal strings `git show HEAD` and `git log -1 --stat HEAD` (NOT the OUTPUT of executing those — i.e., no SHA hashes from real commits in the prompt, just the literal command text). This catches the backtick / `$()` regression class. (5) **Non-git and no-commit guards**: cd to a non-git tempdir + invoke target → exit 0, no shim invocation. Init git but no commit + invoke → exit 0, no shim invocation. Closes iter-4 #1 (the prereq-target bug). (6) **Failure-preservation shim** (closes Codex iter-6 #1 explicitly — was claimed but not enumerated): for each of the 3 output-bearing targets (`review-commit-by-codex`, `review-commit-by-claude`, `review-plan-consistency-by-claude`), pre-create a stale `$(REVIEW_COMMIT_OUT_*)` / `$(PLAN_CONSISTENCY_OUT)` file with bogus content; inject a shim CLI returning exit 42; invoke the target; assert make exits nonzero AND the stale file is NOT echoed as a "success" output. Locks down the `;` → `&&` regression class. Same `$(CURDIR)` stale-PWD robustness as the existing plan-review targets. |
| `tests/test_triage_byte_identity.py` (NEW — closes Codex iter-6 #2) | Extract the "Triaging review findings" block from EACH of: `shared/CLAUDE.md.tmpl`, `shared/AGENTS.md.tmpl`, `shared/docs-plans-README.md.tmpl`, dogfood `CLAUDE.md`, dogfood `AGENTS.md`, dogfood `docs/plans/README.md`. Extract = read between the `## Triaging review findings` heading and the NEXT `##` heading. Normalize by rendering shared/ templates against skill-repo context. Assert all 6 extracted blocks are byte-identical. The existing `test_dogfood_doc_sanity.py` and `test_shared_templates.py` only check heading + bullet PRESENCE (verified empirically), NOT full byte-identity — so the prior plan claim "existing test covers byte-identity" was wrong (closes iter-6 #2). This new test is the actual byte-identity gate for the triage block (which now includes the new four-questions sub-section). |
| `tests/test_dogfood_doc_sanity.py` (extend — closes Codex iter-4 #5 + user-directed triage-extension scope) | (1) Add a targeted assertion: the Two-tier code review section and the Plan-review-loop self-check line in skill-repo's root `CLAUDE.md` must be byte-identical (modulo project-name substitution) to what `shared/CLAUDE.md.tmpl` renders for the skill repo's `claude`-mode context. Catches root-CLAUDE.md drift that the existing `tests/test_selftest_overlap.py` does NOT cover. (2) Extend the existing triage-rule byte-identity test to verify the new "Before deciding (a/b/c/d), ask these four questions" subsection lands identically across all three templates AND all three dogfood docs (CLAUDE.md / AGENTS.md / docs/plans/README.md in both shared/ and skill repo). The four-question text appears in the byte-identical block, so the existing assertion grows automatically; this row just makes the dependency explicit. |
| `tests/test_selftest_overlap.py` | Existing — gates byte-identity. New targets land inside the SELFTEST-OVERLAP-BEGIN/END region; test should keep passing. |
| `tests/test_python_templates.py`, `tests/test_nodejs_templates.py`, `tests/test_go_templates.py` (closes Codex iter-3 #3) | Each language's template-test file has the "generated project Makefile contains expected targets" assertion. Extend each with the 3 new target names. (Earlier draft pointed at `tests/test_bootstrap_cli.py` — that file tests CLI flag handling, not Makefile content; wrong target.) |
| `tests/test_dogfood_doc_sanity.py` | Already runs the Acme-isms scan against `CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING.md` / PR template. Confirm new Tier-1 docs don't reintroduce forbidden strings (Acme / Telegram / etc.). |

### Bucket F — Active docs + BACKLOG

- `README.md`: under "Build sequence", add PR #4 line: "Two-tier code review + plan-loop improvements". Move "real-project trial" to PR #5.
- `SKILL.md`: brief mention that generated projects ship Tier-1 + Tier-2 review patterns.
- `docs/usage.md`: section "Code review workflow" listing the 3 new Makefile targets + when each fires.
- **`shared/CONTRIBUTING.md.tmpl` + skill-repo `CONTRIBUTING.md` — extend the existing CLI requirements section** (closes Codex iter-5 #5). Current wording says "codex CLI required for `make review-plan-by-codex`" / "claude CLI required for `make review-plan-by-claude`". Generalize each to list ALL local review targets: `review-plan-by-*`, `review-commit-by-*`, `review-plan-consistency-by-claude`. Same generalization in `docs/usage.md`'s tool-setup section. Otherwise generated docs under-document the CLI dependency for Tier-1.
- `BACKLOG.md` (skill repo) AND `shared/BACKLOG.md.tmpl` (template — closes Codex iter-4 #4: generated `CLAUDE.md`'s `none`-variant points users at "BACKLOG for the planned `--enable-github-review` flag", so the entry must exist in BOTH the skill repo's backlog AND in the template that becomes generated projects' BACKLOG.md):
  - "Retroactively add triage rule to Acme's plan-review docs" — skill-repo BACKLOG only; now actionable as a follow-up side-task (Acme can copy from this PR's shared/CLAUDE.md + CONTRIBUTING.md sections).
  - **New entry** (closes Codex iter-2 #2; lands in BOTH backlogs): "Add `bootstrap.py --enable-github-review={claude,both-docs}` for retroactive Tier-2 adoption". Trigger: "a `--github-review=none` user wants to add bots later". Rough effort: ~half a day. Adds a one-flag mode that runs the equivalent of `bootstrap.py --apply` but writes ONLY the github-review-conditional files (`.github/workflows/claude-review.yml`, the `docs/codex-github-review-setup.md` overlay, the PR template's reviewer checklist) with `--overwrite-existing` semantics on those specific files. Until this lands, `--github-review=none` is effectively a one-way choice.
  - "Investigate Codex/Claude alternation per iteration for token reduction" — skill-repo BACKLOG only; trigger "if subscription limits still hit after PR #4 lands".
  - **New entry** (user-directed Q2 discussion after iter-4): "Add `review-plan-fact-check-by-{claude,codex}` subagent target" — separate from idea-(b) consistency check. Scope: a narrow subagent that reads the plan + the current repo, and for every file path / test name / line number / module reference in the plan, verifies it matches reality. Catches the plan-vs-repo factual-mismatch class of findings (~25% of what Codex finds across iter-1→4) before Codex does. Trigger: "if iter-N reviews on upcoming PRs keep finding plan-vs-repo factual mismatches". Not in PR #4 scope — feature creep risk; empirical evidence needed first. Skill-repo BACKLOG only.

## Verification

### Phase 1 — plan PR

(closes Codex iter-1 #3 — Phase-1 verification must use targets/prompts that exist NOW; the new ones are deliverables of Phase 2):

1. Bidirectional plan-review loop on THIS plan using the **CURRENT** `review-plan-by-{codex,claude}` targets (no idea-(a) prompt extension yet — that's a Phase 2 deliverable). Meta-validation of idea **a** is deferred to Phase 2 (we'll re-run a one-shot review of this same plan with the new prompt to confirm the cross-section instruction surfaces additional findings).
2. After each iteration's folding pass, the author manually re-reads the plan in full to scan for self-introduced contradictions BEFORE invoking the next reviewer. This simulates the idea-(b) `review-plan-consistency-by-claude` target manually until Phase 2 ships the real target. (Both Claude Code and Codex CLI authors can do this — open the file, read top-to-bottom, flag drift.)
3. Active-surface grep (existing pattern, extended with `Tier-1|review-commit|review-plan-consistency`).
4. Human-approval gate before commit.

### Phase 2 — impl PR

1. Full pytest green (211 baseline + ~8–12 new assertions for the new targets / prompts / dogfood drift / shim-argv / hermetic-git / non-git skip / no-commit skip).
2. `make help` in skill repo shows the 3 new targets. `make help` in a freshly-bootstrapped project (each of python / nodejs / go) shows the same 3 targets.
3. `make review-commit-by-claude` on a **deliberately flawed fixture commit** returns findings in the documented format (closes Codex iter-5 #3 — a clean commit can correctly return zero findings, so "any tiny commit returns findings" is nondeterministic). Use a fixture commit that introduces a known Tier-1-detectable defect (e.g., a function whose docstring claims X but body does Y; or a test asserting against a hardcoded value the production code can't actually produce). Assert findings count ≥ 1 AND the output contains the (a/b/c/d) framework's "importance" labels. Live-CLI runs against arbitrary commits are advisory smoke only.
4. **Empirical spike — does Claude consistency check actually work?** (closes Codex iter-4 #2 — answers the open question from iter-4 about whether `claude --print --permission-mode plan` will return findings for the consistency-check prompt, or only a summary like it did for the full-review prompt in iter-1):
   - Create a fixture plan file with a DELIBERATE contradiction (e.g., `Section A: "X = 1"` + later `Section B: "X = 2"`).
   - Run `make review-plan-consistency-by-claude PLAN_FILE=<fixture> ITERATION=1`.
   - **Pass criterion**: output identifies the X=1 vs X=2 contradiction (as a numbered list, per the prompt's output-format ask). NOT a summary like "review complete — findings persisted".
   - If empirically broken: impl PR includes a fix (alternative permission mode, `claude` without `--permission-mode plan`, or swap to `codex exec` — same proven pattern as `review-plan-by-codex`). The plan stays as-is; the fix is impl-PR scope.
   - **Fallback always works**: even if the CLI target proves unreliable, the documented manual procedure (re-read plan after each fold) is still in place — demonstrated 6 drift catches across 3 self-checks in this plan's own review loop.
5. `make review-plan-consistency-by-claude PLAN_FILE=docs/plans/2026-05-15-skill-pr3-go-language.md ITERATION=1` runs to completion (smoke test on a real plan, in addition to the fixture spike above).
6. `tests/test_selftest_overlap.py` green (byte-identity preserved across the macro, both target recipes, and the dogfood Makefile). `tests/test_dogfood_doc_sanity.py` green on the new root-CLAUDE.md drift test.
7. **Advisory** (closes Codex iter-2 #6 — not a hard CI gate): if `claude[bot]` is configured on the impl PR (the skill repo IS in `claude` mode, so it should be), the bot's review SHOULD find at most polish-class issues — but external bot firing depends on GitHub App install / secret presence / Codex web-UI setup that the plan can't enforce. Document as observed evidence in the PR summary, not as a blocking acceptance gate.

## Critical files to read before each iter's review

For Codex / Claude reviewers of this plan:
- `Makefile` (skill repo) — current `review-plan-by-*` recipes; the SELFTEST-OVERLAP region
- `shared/Makefile.review.tmpl` — the template counterpart
- `shared/CLAUDE.md.tmpl` — current "Plan review loop" + "Triaging review findings" sections; where new docs land
- `shared/CONTRIBUTING.md.tmpl` — step list to extend
- `docs/plans/README.md` — current loop guidance
- `tests/test_selftest_overlap.py` — what the byte-identical invariant checks
- `tests/test_shared_templates.py` — assertion patterns to mirror
- This repo's `CLAUDE.md` (root) — mirror target

## What we are NOT doing in this PR

- No post-commit hook auto-fire for Tier-1 (manual only).
- No changes to GitHub Tier-2 workflows.
- No reviewer-alternation per iteration.
- No convergence-threshold tightening.
- No new CLI flag — Makefile targets are the surface.
- No `pip install -e .` console-script packaging (parked separately).

## Iteration log (this plan)

| Iter | Findings | Verdict |
|---|---|---|
| 1 (codex) | 7 (4× imp-3, 3× imp-2) | do not implement yet — all 7 folded into iter-2 draft (Phase-1-verification-vs-Phase-2-deliverable, Acme in dogfood docs, Tier-1-before-commit, Tier-2 conditional on github_review_mode, subagent prompt template missing, test coverage skipped existing file, fixed /tmp paths). All real |
| 1 (claude) | 0 actionable — returned summary only (known `--permission-mode plan` quirk for review-style prompts; Claude treats prompt as a task and outputs its plan rather than findings) | Treated as no-op. Recorded in BACKLOG: "Investigate alternative Claude CLI invocation for plan reviews (`--permission-mode acceptAll`? different model? skip Claude direction entirely for plan reviews?)" |
| 1 (self-check) | 4 drift items | Applied idea-(b) manually before iter-2: caught (1) prompt-text divergence Bucket-A vs Bucket-D, (2) ambiguous "Tier-1 commit-review prompt" in test row, (3) Claude-Code-specific "single Read tool call" wording, (4) vague "re-bootstrap" in 'none' variant. All folded before Codex iter-2 |
| 2 (codex) | 6 (2× imp-3, 4× imp-2) | do not implement yet — all 6 folded into iter-3 draft. iter-2 found NEW issues not visible in iter-1 (deeper plan-vs-repo state checks): Tier-2 mode trichotomy wrong (claude / both-docs not interchangeable; skill repo is `claude` not `none`), `bootstrap.py --apply` re-run path not runnable, git-worktree guard regression (knew about it from PR #3, missed in this draft), prompt-drift test too weak, missing ITERATION docs, Phase-2 acceptance over-promised. This validates running iter-2 even after a clean iter-1 + self-check — the self-check catches doc-drift WITHIN the plan, but cross-checks against repo state require Codex |
| 3 (codex) | 5 (1× imp-3, 4× imp-2) | needs another iteration — all 5 folded. iter-3 imp-3 was a REAL CORRECTNESS BUG: the Jinja macro embedded backticks around `git log` / `git show` for prose readability, but the macro renders into a Makefile recipe that passes the prompt as a double-quoted shell arg — backticks would have triggered command substitution, locally executing `git log`/`git show` and injecting their output into the prompt (mangled prompt + argv-length risk on large commits). Removed backticks; used single quotes for prose. Plus 4 imp-2 (missing .PHONY, wrong test file refs, invalid `9.5.` ordered-list marker, missing "rerun Tier-1 after amend" instruction). **iter-3 also validates idea-(a): Codex caught the shell-injection bug by checking how the prompt would be processed downstream, not just the prompt's content — the new idea-(a) "where else does this affect" prompt clause is exactly this kind of cross-section impact thinking. Implementation should ship the prompt enhancement** |
| 4 (codex) | 7 (2× imp-3, 4× imp-2, 1× imp-1) | needs another iteration — 6/7 folded straightforwardly; 1 (iter-4 #2 on Claude consistency target feasibility) reframed after user pushback as "verify empirically in Phase 2, not a plan blocker". iter-4 imp-3 #1 was another REAL CORRECTNESS BUG: `_require-git-and-commit` as a Make PREREQUISITE doesn't halt the consumer target on `exit 0` — guards now inlined in each consumer recipe in the same shell scope. Trajectory: findings count went 7→6→5→7 (slight uptick), but imp-3 went 4→2→1→1-real-folded. Still earning value per iter. User's question on iter-4 #2 led to triage refinement: pre-folding hypotheticals is the failure mode the plan loop is supposed to AVOID; "do not implement yet" verdicts based on speculative invocation failures should be challenged. **Lesson for future iters: when the reviewer extrapolates from one data point to a new context, verify empirically before folding** |
| 4 (post-fold, user-directed extension) | 2 new scope items added after Q1/Q2 discussion | Q1: triage rule extended with four "before deciding" reasoning questions — addresses the failure mode where the driver applies the reviewer's suggested fix verbatim without verifying the premise / considering alternatives / auditing cross-section impact / checking for new contradictions. Lands in the byte-identical triage block (CLAUDE.md / AGENTS.md / docs-plans-README.md × shared + dogfood = 6 files; existing test enforces). Q2: deferred `review-plan-fact-check-by-*` subagent as BACKLOG entry with empirical trigger — feature creep risk, no PR #4 inclusion |
| 5 (codex, applied four-questions framework at triage) | 5 (2× imp-3, 3× imp-2) | needs another iteration — all 5 folded. Applied the new four-questions framework BEFORE deciding (a/b/c/d): every finding's premise verified (Q1) — all 5 correct. P1 (`; \ cat` hides CLI failures) and P2 (selftested-pair both-halves) and P4 (`{% raw %}` wrapper breaks macro) all real correctness issues; P3 ("any tiny commit returns findings" nondeterminism) and P5 (CLI requirements docs miss new targets) doc-completeness. Trajectory: 7 → 6 → 5 → 7 → 5; imp-3 4 → 2 → 1 → 2 → 2 (plateau). Findings shifting from design to infrastructure-correctness — getting closer to polish-only |
| 6 (codex, four-questions applied) | 5 (2× imp-3, 3× imp-2) | **3-consecutive-iters-at-imp-3=2 plateau triggered** (per project convergence rule). All 5 folded. P1 + P2 were verification-coverage gaps not new bugs: P1 (failure-preservation shim test not enumerated in Bucket E) — added explicit per-target rows. P2 (claimed existing dogfood test enforced triage byte-identity — empirically false: existing test only checks heading presence) — added NEW `test_triage_byte_identity.py` to lock down the actual byte-identity invariant. P3 (dirty-worktree handling) — added WARN-and-proceed in commit-review recipes. P4 (env scrubber missing new vars) — added to EXACT_DROP + test. P5 (ITERATION default — clobbers iter-1 not empty suffix) — corrected rationale wording. **Per four-questions framework, all 5 premises were verified empirically before folding (checked test sources, scrubber source, Makefile defaults)** |

## Evidence table — what was folded and where

| Iter | Importance | Finding | Action |
|---|---|---|---|
| 1 | 3 | **(a) fold** — Codex iter-1 #1: Tier-1 step inserted at CONTRIBUTING step 8.5 (between Verify and Commit) but the target prompt reviews `git show HEAD` — would review the PRECEDING commit, not the one about to push. Off-by-one in workflow positioning | Moved to step 9.5 (between Commit at 9 and Push at 10). Wording explicitly: "after the focused commit you just made, before push". Added blockers path: amend or follow-up commit, rerun `make check`, then push |
| 1 | 3 | **(a) fold** — Codex iter-1 #2: planned to put "Calibration (from Acme's first substantive PR)" line into `shared/CLAUDE.md.tmpl` + dogfood `CLAUDE.md`, but `tests/test_shared_templates.py` `FORBIDDEN_TERMS` includes `acme` (case-insensitive). Plan would fail its own no-Acme-isms scan | Calibration anecdote stays only in THIS plan's Context section (where Acme references are allowlisted as historical attribution per plan-1 invariants). Shared / dogfood Two-tier sections do NOT carry it |
| 1 | 3 | **(a) fold** — Codex iter-1 #3: Phase 1 verification stipulated "use the NEW prompts" and "run `make review-plan-consistency-by-claude`", but those don't exist until Phase 2 lands. Verification depended on deliverables it was supposed to verify | Rewrote Phase 1: use CURRENT `review-plan-by-{codex,claude}` targets; simulate consistency self-check via manual full-file Read by author. Meta-validation of new prompt + new target deferred to Phase 2 self-test |
| 1 | 3 | **(a) fold** — Codex iter-1 #4: drafted Two-tier section for `shared/CLAUDE.md.tmpl` unconditionally referenced `claude[bot]` + `@codex review` auto-fire, but those bots only exist when `github_review_mode in ['claude', 'both-docs']`. For `mode=none` users (the default), the prose is misleading | Split into two Jinja-conditional variants: `claude/both-docs` mentions Tier-2 + bots; `none` says "Tier-2 not configured; re-bootstrap to enable, or wire manually". Same split in CONTRIBUTING.md. New test asserts `none` variant doesn't mention bots |
| 1 | 2 | **(a) fold** — Codex iter-1 #5: test bucket listed `test_shared_templates.py` + `test_selftest_overlap.py` + `test_bootstrap_cli.py` but missed `tests/test_makefile_review_targets.py` — the existing behavioral coverage for `review-plan-by-*` (shim CLIs + output materialization). New targets need parallel shim tests | Added `test_makefile_review_targets.py` row to Bucket E with 3 specific new tests: shim-verified materialization of `$(REVIEW_COMMIT_OUT_CODEX|CLAUDE)`, slug+iter keying of `$(PLAN_CONSISTENCY_OUT)`, `$(CURDIR)` stale-PWD robustness mirroring the existing assertions |
| 1 | 2 | **(a) fold** — Codex iter-1 #6: CLAUDE.md section referenced "a prompt template in CONTRIBUTING.md" for the in-session subagent path, but the planned CONTRIBUTING.md change only added the `make` invocation, not the template itself. Dangling reference | Added a new "Tier-1 review — prompt template for in-session subagents" section at the bottom of CONTRIBUTING.md.tmpl with the full prompt (parameterized by `<SHA>`). Kept it bottom-of-file so it doesn't bloat the per-change checklist at the top |
| 1 | 2 | **(a) fold** — Codex iter-1 #7: new targets wrote to fixed `/tmp/review-commit-by-codex.md` etc. — second run clobbers the first. Existing `review-plan-by-*` uses `PLAN_REVIEW_OUT_{CODEX,CLAUDE}` keyed by plan slug + iteration; new targets should follow same convention | Added `REVIEW_COMMIT_OUT_{CODEX,CLAUDE} ?= /tmp/review-commit-$(git rev-parse --short HEAD)-by-*.md` (SHA-keyed) and `PLAN_CONSISTENCY_OUT ?= /tmp/review-plan-consistency-$(notdir $(basename $(PLAN_FILE)))-iter-$(ITERATION).md`. Both overridable via Make variables. Mirrors the existing convention exactly |
| 1 (self-check) | 2 | **(a) fold** — applied idea-(b) manually (since the target doesn't exist yet): full-plan re-read after iter-1 fold surfaced 4 self-introduced drift items: (1) Bucket-A Tier-1 prompt and Bucket-D subagent prompt template diverged textually after iter-1 #6 fold (different ending clauses, slightly different focus wording) — risks the "single source of truth" claim; (2) Bucket-E test row said "Tier-1 commit-review prompt" without specifying WHICH prompt (Makefile recipe vs CONTRIBUTING.md template) — ambiguous; (3) Phase-1 step 2 used Claude-Code-specific "single Read tool call" wording — not agent-neutral; (4) 'none'-variant of Two-tier section said "re-bootstrap" without specifying how. | (1) Aligned both prompts; (2) disambiguated test row; (3) Phase-1 step 2 reworded agent-neutral; (4) 'none'-variant gave an explicit command. **All four were folded BEFORE Codex iter-2 — none surfaced again in iter-2. Empirical validation that idea-(b) catches in-plan drift cheaply.** |
| 2 | 3 | **(a) fold** — Codex iter-2 #1: Tier-2 mode handling collapsed `claude` and `both-docs` together; in reality `claude` mode emits ONLY `claude[bot]` (no Codex bot, no `@codex review`), and the skill repo itself is in `claude` mode (per `tests/test_selftest_overlap.py:33` + `.github/workflows/claude-review.yml`'s existence), not `none` as I'd claimed | Replaced the two-variant model with THREE explicit Jinja variants: `none` / `claude` / `both-docs`. `claude` variant mentions only `claude[bot]` + `@claude review this`; `both-docs` mentions both bots + `@codex review`; `none` says no Tier-2. Skill-repo dogfood overlay uses `claude` variant. Test asserts all three variants render correctly with the right bot mentions and absences |
| 2 | 3 | **(a) fold** — Codex iter-2 #2: `none`-mode adoption command `bootstrap.py --apply --github-review=claude` isn't actually runnable — CLI requires `--language`, `--project-name`, `--out`, `--github-owner`, `--github-repo`, AND `--overwrite-existing` for existing files. Telling users to "just re-bootstrap" was a paper promise | Removed the re-bootstrap promise from the 'none'-variant CLAUDE.md section. Parked retroactive adoption as a BACKLOG entry: "Add `bootstrap.py --enable-github-review={claude,both-docs}` for a single-flag retroactive Tier-2 install". Until that lands, `--github-review=none` is documented as a one-way choice |
| 2 | 2 | **(a) fold** — Codex iter-2 #3: commit-review Makefile target used `test -d .git` (same bug PR #3 already fixed for Go hooks). Worktrees have `.git` as a file, not a directory — silently bypasses the guard. Also no `git rev-parse --verify HEAD` check, so brand-new repo with no commits would reach `git show HEAD` and fail inside the reviewer | Replaced with a shared `_require-git-and-commit` phony helper using `git rev-parse --is-inside-work-tree` + `git rev-parse --verify HEAD`. Same pattern as `languages/go/Makefile.tmpl`'s install-hooks. Both commit-review targets depend on the helper. Tests added: clean skip messages for non-git + no-commits scenarios |
| 2 | 2 | **(a) fold** — Codex iter-2 #4: prompt-drift test was weak — only checked 2 key phrases in each prompt. Drift in any of the 15+ other clauses would slip through. The "byte-identical" claim wasn't actually enforced | Moved the Tier-1 prompt to a Jinja macro `tier1_prompt(commit_ref)` defined once in `shared/Makefile.review.tmpl`. Both the Makefile recipes AND `shared/CONTRIBUTING.md.tmpl`'s subagent section invoke the macro. Drift is impossible by construction (one source). Test asserts the rendered text from both call sites is byte-identical after normalizing the commit_ref placeholder |
| 2 | 2 | **(a) fold** — Codex iter-2 #5: `review-plan-consistency-by-claude` doc examples omitted `ITERATION=N`. Without it, `$(PLAN_CONSISTENCY_OUT)` defaults to `...iter-.md` (empty suffix) and every run clobbers the previous | Added `ITERATION=N` to all invocation examples in CLAUDE.md "Plan review loop" extension + Phase-2 verification step 4 + the in-line usage example in Bucket C |
| 2 | 2 | **(a) fold** — Codex iter-2 #6: Phase-2 acceptance step 6 said "claude[bot] + Codex auto-review fire on impl PR" as a hard gate, but bot firing depends on external setup (GitHub App install, OAuth token secret, Codex web-UI repo enablement) that the plan can't enforce | Made step 6 advisory: "if `claude[bot]` is configured ... document as observed evidence in the PR summary, not as a blocking acceptance gate". Listed the external prerequisites |
| 2 (self-check) | 1 | **(a) fold** — full-plan re-read after iter-2 fold caught one inconsistency: the `claude` variant of the Two-tier CLAUDE.md section said "(Codex GitHub bot is NOT configured ... bootstrap with `--github-review=both-docs` next time if you want both reviewers)" — but the `none` variant correctly pointed at the planned BACKLOG `--enable-github-review` flag. The `claude` variant's "next time bootstrap" was both misleading (retroactive add IS possible via web UI + doc overlay) AND inconsistent with the `none`-variant treatment. | Aligned: `claude`-variant now also points at the planned BACKLOG `--enable-github-review` flag. Single fallback story across both variants. **Confirms idea-(b) catches the same class of drift in iter-2 as it did in iter-1 — runs ~5 min, saves an iter-3 round-trip on this finding** |
| 3 | 3 | **(a) fold** — Codex iter-3 #1: macro text had backticks around `git log` / `git show` (for prose readability), but the macro renders into Makefile recipes that pass the prompt as a double-quoted shell argument — backticks would execute the commands LOCALLY at render time, injecting their stdout into the prompt and risking argv-length issues for large diffs. Real correctness bug | Rewrote the macro to use single quotes (`'git log ...'` as literal prompt text) and removed backticks entirely. Also replaced `**bold**` markdown with `AND` (caps) since the rendered prompt is plain text to a CLI, not markdown. New shim test in Bucket E asserts the rendered prompt passed to the CLI contains the literal command text, NOT the output of `git log` execution |
| 3 | 2 | **(a) fold** — Codex iter-3 #2: new targets (`review-commit-by-*`, `review-plan-consistency-by-claude`, `_require-git-and-commit`) not declared `.PHONY`. If a user creates a file named `review-commit-by-codex`, `make` would skip the recipe | Added `.PHONY: review-plan-by-codex review-plan-by-claude review-commit-by-codex review-commit-by-claude review-plan-consistency-by-claude _require-git-and-commit preflight-review-tooling` at the top of `shared/Makefile.review.tmpl`'s review block. All review-section targets declared phony from a single place |
| 3 | 2 | **(a) fold** — Codex iter-3 #3: Bucket E listed `tests/test_bootstrap_cli.py` as the home of "generated project Makefile targets" assertion, but that file tests CLI flag handling. The actual assertion lives in three language-specific files: `test_python_templates.py`, `test_nodejs_templates.py`, `test_go_templates.py` | Updated Bucket E test row to point at the three correct files |
| 3 | 2 | **(a) fold** — Codex iter-3 #4: `9.5.` is not a valid Markdown ordered-list marker — GitHub renders it as plain text and breaks the list. Workflow positioning, not just style | Moved Tier-1 to a sub-bullet under existing step 9 (Commit) rather than a fractional step. Sub-bullet renders cleanly across all Markdown variants |
| 3 | 2 | **(a) fold** — Codex iter-3 #5: blocker-fix workflow said "fix → `make check` → push" without re-running Tier-1 on the corrected commit. That skips the new review tier on the amended commit, weakening the "after each focused commit" contract | Updated step 9 sub-bullet: blockers → fix + amend OR follow-up commit → **rerun `make review-commit-by-*`** until no imp-3 → then `make check` → push. Restores the "every commit gets Tier-1" property |
| 3 (self-check) | 1 | **(a) fold** — full-plan re-read caught one contradiction: Bucket A line 70 claimed "no test needed because macro makes drift impossible", but Bucket E test row still mandated a byte-identity test on the two rendered prompts. The macro DOES make drift impossible IF the import is used correctly — but someone could forget `{% from ... import %}` and inline a divergent prompt. Defensive test is correct; Bucket A wording was overconfident | Updated Bucket A line 70: macro is single source of truth at the macro level; Bucket E adds a defensive byte-identity test on rendered strings to catch inlining mistakes. Aligned both buckets |
| 4 | 3 → fold as imp-3 | **(a) fold** — Codex iter-4 #1: `_require-git-and-commit` as a Make PREREQUISITE with `exit 0` in its recipe does NOT halt the consumer target. Make sees the prereq exit cleanly and proceeds into `review-commit-by-codex` regardless. Non-git / no-commit projects would still invoke the paid CLI with a bogus `HEAD` — guard contract is false | Inlined the guard into each consumer recipe (same shell scope using `\` continuation, so `exit 0` actually halts). Removed the separate `_require-git-and-commit` target. Same pattern as PR #3's Go install-hooks (combined-shell recipe with early exit). New tests use the in-process shim to assert non-git and no-commit cases exit 0 WITHOUT invoking the reviewer |
| 4 | 3 → triaged as imp-2 (not imp-3 blocker) | **(c) reject imp-3 framing** + **(a) fold as imp-2 with Phase-2 spike** — Codex iter-4 #2 inferred that the new consistency target would fail the same way `review-plan-by-claude` did in this loop (empty summary, no findings). The inference is weak: the consistency-check prompt is narrow + deterministic + has a different output-format ask than the full-review prompt; the failure observed in iter-1 was on a DIFFERENT prompt shape that `--permission-mode plan` likely interprets as "propose a plan to do this task". Also the consistency check is a CHEAP PRE-SCREEN — Codex catches drift in the very next iter anyway; worst case we lose the pre-screen value, not the feature. Manual application of idea-(b) (demonstrated 3× in this loop with 6 drift catches) is the documented fallback if the CLI target proves unreliable | Plan keeps the target as designed (`claude --print --permission-mode plan`). Phase-2 verification adds an empirical spike step: run `review-plan-consistency-by-claude` against a fixture plan with deliberate contradictions; confirm findings are returned. If empirically broken, impl PR swaps CLI flags or invocation (codex / different permission mode / SDK script) — that's an impl decision, not a plan blocker. **User triage call: don't pre-fold a hypothetical; verify empirically** |
| 4 | 2 | **(a) fold** — Codex iter-4 #3: CONTRIBUTING.md trivial-diff exception says "rely on Tier-2 + make check" — but `--github-review=none` users have no Tier-2; the wording is misleading for the default mode | Made the trivial-diff exception Jinja-conditional. `mode=none`: "rely on `make check`". `mode=claude` or `both-docs`: "rely on Tier-2 + `make check`". New render test asserts each variant |
| 4 | 2 | **(a) fold** — Codex iter-4 #4: generated CLAUDE.md `none`-variant points users to "BACKLOG for the planned `--enable-github-review` flag", but Bucket F only updates skill-repo `BACKLOG.md`, NOT `shared/BACKLOG.md.tmpl` (which renders into generated projects' BACKLOG.md). Generated projects would have a dangling pointer | Bucket F now updates BOTH `BACKLOG.md` (skill repo) AND `shared/BACKLOG.md.tmpl` (template) with the `--enable-github-review` entry. Render test asserts the generated BACKLOG.md contains it |
| 4 | 2 | **(a) fold** — Codex iter-4 #5: plan said "Drift between rendered CLAUDE.md template + dogfood `CLAUDE.md` fails `tests/test_selftest_overlap.py`", but that test does NOT actually check root `CLAUDE.md` (it checks .editorconfig, claude-review.yml, pull_request_template.md, docs/plans/README.md, and the Makefile review-section). Claude reads root CLAUDE.md first; drift would silently slip through CI | Added explicit dogfood test for the root `CLAUDE.md` Two-tier section: assert it renders byte-identical to `shared/CLAUDE.md.tmpl` for the skill repo's `claude` mode context. Or, alternatively, extend `test_selftest_overlap.py` to cover root CLAUDE.md. (Bucket E updated to call this out) |
| 4 | 2 | **(a) fold** — Codex iter-4 #6: evidence table claimed "shim regression test for backticks" but Bucket E didn't actually specify it. Also brittle "7-char SHA" assertion would break if `core.abbrev` is configured differently | Bucket E now explicitly lists: (1) shim-argv regression test asserting the rendered prompt contains literal `git show HEAD` / `git log -1 --stat HEAD` strings (not command output), (2) hermetic git commit setup via `git -c user.name=... -c user.email=... commit --allow-empty`, (3) commit-SHA comparison against `git rev-parse --short HEAD` (whatever the local config returns), NOT a fixed length |
| 4 | 1 | **(a) fold** — Codex iter-4 #7: Two-tier section planned to land "after Plan review loop" but says "(a/b/c/d) triage rule above". The triage rule is AFTER the plan-review-loop section, so "above" would be wrong | Place the new Two-tier section AFTER the "Triaging review findings" section (not before). Wording "above" is then correct |
| 5 | 3 | **(a) fold** — Codex iter-5 #1: commit-review recipes ended with `; \ cat $(REVIEW_COMMIT_OUT_*)` — `;` chains in shell run the second command regardless of the first's exit. If the paid CLI exited nonzero (auth fail, rate-limit, sandbox error) but a stale output file existed from a prior run, `cat` would succeed and `make` would return 0. Reviewer ran the four-questions check (Q1 premise verified by tracing shell semantics), confirmed real bug | Replaced `; \ cat` with `&& cat` on all three review-output-bearing targets (review-commit-by-codex, review-commit-by-claude, review-plan-consistency-by-claude — Q3 cross-section check caught the third instance). New shim test injects a CLI returning exit 42 + asserts the make target exits nonzero |
| 5 | 3 | **(a) fold** — Codex iter-5 #2: planned to update only dogfood `docs/plans/README.md` for the new self-check workflow line, but `shared/docs-plans-README.md.tmpl` is byte-identity-paired via `tests/test_selftest_overlap.py:80`. Single-side update would fail selftest. Q1 premise verified (read the selftest test directly). Q3 cross-section: same risk applies to EVERY selftested-pair edit in Bucket D | Made Bucket D's docs/plans/README.md row explicit: update both halves. Added a "selftested pairs" reference table to Bucket D listing all six pairs the PR touches, with the corresponding test for each. Future Bucket-D edits MUST consult the table |
| 5 | 2 | **(a) fold** — Codex iter-5 #3: Phase-2 step 3 said `make review-commit-by-claude` on "a tiny smoke commit" must return findings. A clean trivial commit can correctly return zero findings — assertion is nondeterministic | Phase-2 step 3 now uses a deliberately flawed fixture commit (function-docstring-vs-body mismatch, or test-vs-impl impossibility). Asserts findings count ≥ 1 AND output contains importance labels. Live runs against arbitrary commits become advisory smoke only |
| 5 | 2 | **(a) fold** — Codex iter-5 #4: `shared/Makefile.review.tmpl` wraps its entire body in `{% raw %}{% endraw %}` (verified empirically: head + tail of file show the wrapper). Inside raw, `{% macro tier1_prompt %}` would render LITERALLY — the macro design wouldn't work. Q1 premise: verified via reading the actual file | Bucket A now specifies the raw-wrapper migration explicitly: macro definition + call sites OUTSIDE raw; rest of file can stay inside raw blocks OR raw can be removed entirely (verify via render-pipeline byte-identity test). Plan default is to remove raw entirely — Make's `$()` doesn't actually collide with Jinja `{{ }}` |
| 5 | 2 | **(a) fold** — Codex iter-5 #5: existing `shared/CONTRIBUTING.md.tmpl` and `docs/usage.md` say "Codex/Claude CLI required for `make review-plan-by-*`" — Tier-1 + consistency targets add new dependencies on the same CLIs but the docs would still scope the requirement to plan-review only. Generated docs would under-document Tier-1's CLI dependency | Bucket F now extends the CLI-requirements sections in CONTRIBUTING.md.tmpl + docs/usage.md to enumerate ALL local review targets (`review-plan-by-*`, `review-commit-by-*`, `review-plan-consistency-by-claude`) as Codex/Claude CLI consumers |
| 6 | 3 | **(a) fold** — Codex iter-6 #1: plan claimed a failure-preservation shim test would be added but Bucket E test row didn't enumerate it. Verification gap — same `;` vs `&&` regression could re-emerge after impl. Q1 verified by reading Bucket E directly | Added explicit failure-preservation test enumeration in Bucket E test row: for each of 3 output-bearing targets, pre-create stale output + shim exits 42 + assert make exits nonzero + stale not echoed |
| 6 | 3 | **(a) fold** — Codex iter-6 #2: plan claimed "existing `tests/test_dogfood_doc_sanity.py` byte-identity check covers triage block" but Q1 premise verification (read the test directly) showed the existing test only asserts heading-presence + bullet-presence, NOT full byte-identity. Drift across the six triage copies would silently pass `make check` | Added NEW `tests/test_triage_byte_identity.py` (in scope row 8): extracts the triage block from all six surfaces (3 templates + 3 dogfood docs), normalizes via render-with-skill-context, asserts byte-identity. Replaces the prior "existing test covers it" claim with a real test |
| 6 | 2 | **(a) fold as WARN-not-block** — Codex iter-6 #3: commit-review recipes don't guard against dirty worktree; reviewer sees dirty codebase not just HEAD. Q2 (best fix?) considered: strict block would frustrate legitimate use (review the commit you just made while staging the next). Chose WARN-and-proceed: detect via `git diff --quiet` + `git diff --cached --quiet`; print WARN to stderr; invoke CLI | Added warning step to both commit-review recipes (Bucket A). Bucket E shim tests assert WARN fires for staged + unstaged dirt AND CLI still invokes |
| 6 | 2 | **(a) fold** — Codex iter-6 #4: 4 new Make variables (`REVIEW_COMMIT_SHA`, `REVIEW_COMMIT_OUT_CODEX`, `REVIEW_COMMIT_OUT_CLAUDE`, `PLAN_CONSISTENCY_OUT`) introduced by this PR are NOT in `scripts/run-with-clean-env.py`'s `EXACT_DROP` set. Command-line Make vars (`make REVIEW_COMMIT_OUT_CODEX=... target`) would leak into nested codex/claude env. Q1 verified by grepping the scrubber source | Added new in-scope row 9: extend `EXACT_DROP` in both the script + template + `tests/test_env_scrubber.py` |
| 6 | 2 | **(a) fold** — Codex iter-6 #5: plan rationale said "without ITERATION the suffix is empty (`iter-.md`)", but Q1 premise verification (read Makefile:77) showed `ITERATION ?= 1` defaults — so the actual failure mode is clobbering `iter-1` repeatedly, NOT empty suffix. Premise of the rationale was wrong | Corrected rationale in Bucket C: "Makefile defaults `ITERATION ?= 1` so omitting it clobbers iter-1 output every run, hiding earlier reviewer passes" |
