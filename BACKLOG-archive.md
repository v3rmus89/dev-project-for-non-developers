# Backlog archive — closed and superseded items

Entries that shipped or were superseded, moved out of [BACKLOG.md](BACKLOG.md)
so that file shows only what is still open. Each entry keeps the closure note it
carried when it was closed (which PR shipped it, what changed); nothing is
rewritten on the way in.

Section headings mirror `BACKLOG.md`. A section whose items are ALL closed moved
here whole, intro included; a section that still has open items keeps its intro
prose in `BACKLOG.md`.

Newest sections at the top, matching `BACKLOG.md`.

---

## Follow-ups from adopt-mode hardening (PR #48)

### ✅ Adopt's `make install-hooks` next-step can name an absent target (owns-a-Makefile subcase) (imp-1) — DONE in PR #48

**Status**: ✅ DONE in PR #48 (commit folding Tier-2 codex round-4 P2). Initially
parked as plan-faithful (the plan gates only `make install`), then **folded** when
the Tier-2 codex round-4 review independently flagged it as a P2 affecting the
**common** owns-a-Makefile case (e.g. the live bot, whose `install:` registers
hooks and which has no `install-hooks` target). `_print_post_apply_guidance` now
gates `make install-hooks` on `base_makefile_written` (the skill's Makefile, which
defines the recipe, actually landed — WRITE/OVERWRITE, not SKIP); when the target
owns its Makefile, the line is omitted (and the now-empty `next steps:` header is
suppressed). **Source**: surfaced during PR #48 implementation; confirmed by Tier-2.

**Why it was real**: Bucket C gave the adopt success path the shared
`_print_post_apply_guidance` helper, which gated off the greenfield
`cd … && make install` line but still printed `make install-hooks`. In the
owns-a-Makefile subcase the skill's `Makefile` — which defines `install-hooks` —
is SKIPped, so `make install-hooks` failed with `No rule to make target`.
(Distinct from "Adopt-mode does not add `pre-commit` to the target's dev
dependencies" under "PR #7 follow-ups", the **no-Makefile** subcase where
`install-hooks` exists but its `pre-commit install` step fails on a missing dep.)

---

## Follow-ups from C4 (downstream-app plan-review catch-up)

C4 re-synced `downstream-app`' whole plan-review subsystem with the skill (the
loop-status numeric-ordering fix shipped in skill PR #43). Three follow-ups were
parked during it — two surfaced by downstream-app' Tier-1, one carried over from
skill PR #42.

### ✅ CommonMark-correct fence tracker shared by the fact extractor + fact-roots parser (`fact-check-nested-fence-tracker`) — DONE in PR #45

**Status**: ✅ shipped 2026-06-12 — one CommonMark-correct `_FenceTracker`
(stores the opening fence's marker char + run length; closes only on a same-marker
fence whose run length ≥ the opener's) now backs both `extract_active_text` and
`parse_fact_roots` in `scripts/extract-plan-facts.py`, so nested / variable-length
/ tilde-vs-backtick fences no longer drop active facts or mis-parse a `## Fact
roots` block. Commit `08f39bc`.

---

### ✅ Surface a malformed LATEST review in `loop-status` (`loop-status-malformed-latest`) — DONE in PR #45

**Status**: ✅ shipped 2026-06-12 — `loop-status.py` now takes the plan stem,
locates the newest review file(s) for the plan by name, and emits a distinct
`malformed-latest` status (exit 1) when that newest review has no parseable
verdict fence, instead of silently collapsing to `no-iters` (exit 0). Applied in
`scripts/loop-status.py` + `shared/scripts-loop-status.py.tmpl` + the Makefile
`loop-status` target + `tests/test_loop_status.py`. Commit `08f39bc`.

---

### ✅ Exact single-token allowlist for the `review` dispatcher (`review-dispatcher-exact-allowlist`) — DONE in PR #45

**Status**: ✅ shipped 2026-06-12 — `_REVIEW_MODE` / `_REVIEW_ACTOR` now require an
exact single-token match (`$(and $(filter 1,$(words $(MODE))),$(filter plan commit,$(MODE)))`
and the `ACTOR` analogue), so a mixed value like `MODE='commit junk'` resolves to
NEEDS-ASK instead of silently dispatching. Applied in the skill `Makefile` +
`shared/Makefile.review.tmpl`. Commit `08f39bc`.

---

## Follow-ups from the interactive-intake work (skill PR #8)

### ✅ PR #9 — smart stack suggestion from a plain-English project description — DONE

**Status**: shipped — see
[docs/plans/archive/2026-05-22-skill-pr9-smart-stack-suggestion.md](docs/plans/archive/2026-05-22-skill-pr9-smart-stack-suggestion.md).
The interactive intake gained an optional "describe your project" step: a
deterministic keyword `stack_suggest` engine maps the description to a
*language* suggestion that pre-fills the language-menu default (the user still
confirms). Resolved decisions: deterministic signal scorer, not an LLM (keeps
the "pure offline CLI, no `.env`" invariant); language-only, not package
manager (a brief carries no uv-vs-pip signal); superpowers patterns referenced,
StackShare data used as CC0 inspiration, no code vendored.

---

## Follow-ups from the info-architecture refactor

### ✅ Mirror the gh-repo-create hint into adopt-mode's `_main_apply_adopt` success path (imp-2) — DONE in PR #48

**Status**: ✅ DONE in PR #48 (Bucket C, commit `7841564`) — extracted into the shared `_print_post_apply_guidance` helper, called from BOTH the v1 and adopt success paths. **Source**: scoped out of the info-architecture refactor PR (`refactor/tighten-info-architecture`, 2026-05-21).

**Why parked**: that PR added the gh-repo-create hint to the **v1**
`--apply` post-apply success block in `bootstrap_lib/cli.py` (inside
`if args.github_review != "none":`). The adopt-mode apply path
(`_main_apply_adopt`, `bootstrap_lib/cli.py:589`) has its own success
printout and does NOT print the hint. Mirroring it there was deliberately
left as a separate follow-up to keep the IA-refactor PR focused (per that
plan's NOT-in-scope list and the iter-3 Codex 1 decision: "out of scope
regardless of merge order").

**Triggers to pick up**: a user runs `--apply --mode=adopt` with
`--github-review != none` and is confused that no repo-creation hint
appears, OR the next PR that touches `_main_apply_adopt`'s success block
for any reason.

**Rough effort**: ~30 min — extract the hint block into a small helper
(it is already self-contained) and call it from both `main()`'s v1
success path and `_main_apply_adopt`; add a parallel test in
`tests/test_bootstrap_cli.py` or `tests/test_mode_adopt_smoke.py`.

---

## Code-review follow-ups from PR #1

### ✅ `write_manifest` not atomic — DONE in PR #40

**Status**: ✅ shipped 2026-06-09 — `write_manifest` now routes through
`bio.atomic_write` (tmp+rename). Commit `42ba339`.

---

### ✅ `--restore` + non-`none` `--github-review` silently ignored — DONE in PR #40

**Status**: ✅ shipped 2026-06-09 — `default=None` makes explicit values
detectable; `_resolve_mode` restore path now flags `--github-review` in the
bad-flags list. Commit `0654648`.

---

### ✅ `load_manifest` error path opaque — DONE in PR #40

**Status**: ✅ shipped 2026-06-09 — `load_manifest` wrapped in
`try/except (OSError, json.JSONDecodeError, KeyError, ValueError)` with a
one-line stderr message. Commit `0654648` + Tier-1 fold `6897dfc`.

---

### ✅ `_apply` bare `except Exception` loses traceback — DONE in PR #40

**Status**: ✅ shipped 2026-06-09 — `DEV_PROJECT_SETUP_TRACEBACK=1`
gates `traceback.print_exc()` in all four apply/adopt exception handlers.
Commit `0654648` + Tier-1 fold `6897dfc`.

---

## Skill follow-ups

### ✅ Add Node-TS language support (`languages/nodejs/`) — DONE in PR #2

**Status**: shipped 2026-05-15 via PR #2 (Plan PR #3 + the implementation PR).

**What landed**: Biome + vitest + TypeScript + Husky v9 + lint-staged, framework-agnostic Node-TS (no React/Vue/Svelte; those parked separately — see entry below).

**Loop convergence**: Codex 4 iters + Claude 1 iter; zero importance-3 findings at convergence; documented trade-offs and autonomous decisions in [`docs/plans/archive/2026-05-15-skill-pr2-nodejs-language.md`](docs/plans/archive/2026-05-15-skill-pr2-nodejs-language.md).

---

### ✅ Add Go language support (`languages/go/`) — DONE in PR #3

**Status**: shipped 2026-05-16 via PR #3 (Plan PR + implementation PR).

**What landed**: gofumpt + golangci-lint v2 + native git hooks via `core.hooksPath` (no pre-commit framework, no Husky — fully Native Go). Tools install project-local via `GOBIN="$(CURDIR)/bin"`. Module path auto-derived: `github.com/{owner}/{repo}` when `--github-*` set, else bare `{project_name}`. Pinned `gofumpt v0.9.2` + `golangci-lint v2.12.2`.

**Loop convergence**: Codex 5 iterations (trajectory 3→4→1→1→0 imp-3); stopping rule met at iter-5. See [`docs/plans/archive/2026-05-15-skill-pr3-go-language.md`](docs/plans/archive/2026-05-15-skill-pr3-go-language.md).

---

## PR #4 follow-ups

### ✅ Cross-session / post-compaction state recovery — DONE in PR #5

**Status**: shipped 2026-05-18 via Plan PR #5 + Impl PR #5a (`make status`
target with 7 sections — Current branch / Recent main / Open PRs /
Active plan / Active lessons / Local repo state / Health checks) +
Impl PR #5b (Implementation-log section per plan; `make status` tails
both iter-log and impl-log with fence-aware extraction). Cross-session
recovery instruction lives in BOTH `shared/CLAUDE.md.tmpl` AND
`shared/AGENTS.md.tmpl` plus dogfood mirrors.

The "optional tracked `STATUS.md`" follow-up was NOT implemented —
`make status` reads + synthesizes, no state file to drift.

Related parked item still open: `sync-plan-to-ui` (plan-mode UI ↔ repo
plan file drift detector). Different problem, separate trigger.

---

## PR #7 follow-ups

### ✅ Adopt-mode skips the greenfield smoke placeholders for an existing project (imp-2) — DONE in PR #48

**Status**: ✅ DONE in PR #48 (Bucket A, commit `c936920`) — `render.GREENFIELD_ONLY_PLACEHOLDERS` (per-language) is filtered from the adopt planned set in `_main_apply_adopt` before analyze. **Source**: PR #7 adopt-mode trial against `downstream-app` (recorded during skill PR #8).

**Why parked**: an `--apply --mode=adopt` run emitted the greenfield smoke
placeholders `src/main.py` (`print("hello from <project>")`) and
`tests/test_smoke.py` (`assert True`) into `downstream-app`, which already
has real source under `src/downstream_app/` and a real test suite. Adopt
mode should not scaffold greenfield-only placeholder code into a project
that already has code.

**Triggers to pick up**: the next adopt-mode change, or a user reports a
stray `src/main.py` / `tests/test_smoke.py` after an adopt run.

**Rough effort**: ~1-2h — gate the `src/main.py` + `tests/test_smoke.py`
emit on greenfield-vs-adopt in the adopt apply path.

---

### ✅ Update CLAUDE.md + shared/CLAUDE.md.tmpl: Codex GitHub bot IS configured (imp-2) — DONE

**Status**: ✅ shipped 2026-05-21 — the info-architecture refactor PR (`refactor/tighten-info-architecture`) replaced the stale "Codex GitHub bot is NOT configured" caveat in `CLAUDE.md` + `shared/CLAUDE.md.tmpl` with a positive both-bots description (`claude[bot]` + `chatgpt-codex-connector[bot]`). **Source**: discovered 2026-05-19 during PR #16 Tier-2 review verification.

**Why parked**: Both `CLAUDE.md:97` and `shared/CLAUDE.md.tmpl:131` (the
generated-project template that dogfoods this) state "Codex GitHub bot
is NOT configured in this project. Retroactively adding it is non-trivial
today — see BACKLOG for the planned `--enable-github-review` flag." This
is stale — `chatgpt-codex-connector[bot]` actively reviewed PR #16
(twice, on commits `94bcdaa` and `d8ca64b`, surfacing 1 P1 + 3 P2 real
findings). The Codex bot has been wired up at some point and CLAUDE.md
hasn't caught up.

**Why not folded into PR #7**: touches `shared/CLAUDE.md.tmpl` (the
generated-project template), which is a code change with byte-identity
tests downstream (`tests/test_triage_byte_identity.py`). Better as a
small focused PR that updates both files in lockstep + verifies the
byte-identity test still passes + updates `--enable-github-review`
BACKLOG entry (which assumed Codex bot wasn't there).

**Triggers to pick up**: next session that touches CLAUDE.md or the
shared template for any reason.

**Rough effort**: ~30 min — edit both files in lockstep (keep wording
byte-identical), update `--enable-github-review` BACKLOG entry to note
"Codex bot is already configured; this flag would just toggle it per
generated project," run `make test` to confirm byte-identity test
passes.

---

### ✅ Adoption-mode: orchestrator-level test for rule (a0) via subprocess git path (imp-1) — DONE

**Status**: ✅ DONE (verified 2026-06-09, backlog audit). **Source**: Tier-1 review on `analyze_target` impl commit (PR #17).

**What closed it**: `tests/test_adopt_engine.py::test_report_does_not_leak_gitignore_pattern_via_rule_a0` does a real `_git_init(tmp_path)` + `.gitignore` write, calls `analyze_target(...)` end-to-end, and asserts the rule-(a0) `manual review needed` SKIP via the full subprocess path (and that the gitignore pattern is not leaked) — closing the orchestrator-path gap described below.

**Why parked**: `TestRecommendPolicyRules.test_rule_a0_...` exercises rule
(a0) at the unit layer (feeds `ignored_by_git=".gitignore:..."` directly
into TargetMeta). `TestAnalyzeTarget.test_downstream_app_shaped_fixture` is
the only orchestrator-level integration test, and it doesn't `git init`
`tmp_path` — so `_check_ignored_by_git` returns `None` for every file,
and the (a0) path through the full subprocess pipeline is never exercised
end-to-end. The git plumbing IS exercised by
`TestComputeTargetMeta.test_ignored_by_git_for_missing_file`, so coverage
isn't zero — just split.

**Triggers to pick up**:
- A future regression where the subprocess error-handling in
  `_check_ignored_by_git` changes and breaks (a0)'s orchestrator path.
- During the live `--apply --mode=adopt` trial against downstream-app if
  AGENTS.md misfires.

**Rough effort**: ~15 min — add one test that does `_git_init(tmp_path)`,
writes `.gitignore` ignoring `Makefile`, then calls `analyze_target` with
`{"Makefile": b"..."}` and asserts SKIP/manual_review=True via the full
subprocess path.

---

## PR #6 follow-ups

### ✅ Fix `make review-plan-by-claude` + `review-plan-consistency-by-claude` + `review-commit-by-claude` plan-mode-exit-declined bug — DONE in PR #6 Step 13

**Status**: done.

**Summary**: All five Claude-direction review targets used `claude --print --permission-mode plan --add-dir ... --output-format text "..."`. The `--permission-mode plan` flag caused the subagent to enter plan mode, generate its findings, then politely decline ExitPlanMode (correctly per its own guidance: research task, not implementation). The harness then wrote `"The user declined the exit. The findings above stand as the deliverable for the consistency self-check"` to the output file INSTEAD of the actual findings. Surfaced during PR #6 iter-1.5 self-check; spread across all 5 affected targets confirmed during iter-2.

**Fix**: Removed `--permission-mode plan` from all 5 occurrences in `shared/Makefile.review.tmpl` + same 5 in `Makefile` (the skill-repo's dogfood). The prompts already say "Do NOT edit any files" (file-edit safety covered at the prompt layer); without plan mode, no ExitPlanMode call attempts, no spurious "declined" output. Verified by re-running `make review-plan-consistency-by-claude` against the converged PR #6 plan file — output is now the actual findings list, not the decline message.

**Triggers met**: Surfaced during PR #6 plan loop; user decision (2026-05-19) co-landed in PR #6 impl rather than as a separate small PR.

**Effort**: ~30 min including the verification run.

---

### ✅ Adoption-mode UX redesign (analyze-then-decide-with-owner) — DONE in PR #7

**Status**: done.

**Summary**: PR #7 ships `--mode=adopt` — a per-file adoption modifier of
`--apply` that runs the analyze-then-decide-with-owner UX:
1. **Analyze** every planned file in target → `TargetMeta` (size, sha256,
   line count, heading count, dependency-groups flag, python-version pin,
   gitignored-by-git source:line reference)
2. **Recommend** a policy per file via Scope #5 rules a0/a..h (`SKIP` /
   `WRITE` / `OVERWRITE` / `WRITE_NEW` / `APPEND_MERGE`) — rule (h)
   default is `SKIP` with `manual_review_needed=true` (the core safety
   guarantee against destructive WRITE on existing files)
3. **Decide** per-file via stdin prompt with per-file allowed-actions
   matrix (`[r]ecommended` / `[s]kip` / `[d]iff` / `[n]ew` / `[a]ppend`
   (`.gitignore` only) / `[o]verwrite` (typed `OVERWRITE` confirmation
   required) / `[?]help` / `[q]uit`). `--auto-accept-recommendations`
   and `--non-interactive` flags give the CI contract.
4. **Apply** per the agreed policies via v2 manifest (`format_version=2`)
   with per-policy restore matrix — `--restore` correctly undoes each
   policy without clobbering pre-existing files (closes the iter-1 #3
   safety hole where rules (b)/(c)/(e) had classified existing files
   as `WRITE` while `WRITE`'s restore deleted them).

Heuristics are content-driven, not policy-table-driven. APPEND_MERGE is
restricted to `.gitignore` only (line-level idempotent merge). `.new`
collision rule fails loud at plan-time if `<original>.new` already
exists.

**Triggers met**: PR #7 plan loop converged after 7 Codex iterations +
8 consistency self-checks; impl shipped across 13 focused commits
(scaffold → engine → manifest v2 → CLI flags → interactive decide →
apply + main wiring → smoke fixtures → docs); Tier-1 on every commit
caught 2 imp-3 safety holes that the plan loop missed at integration
boundaries (rule (a0) gitignore-pattern leak in report; v2 manifest
unresolved-relpath silent-restore failure across cwds).

**Effort**: ~2 weeks across plan + impl, informed by downstream-app trial.

---

### ✅ Real-project trial on `~/code/downstream-app/` — DONE

**Status**: shipped. PR #7's `--mode=adopt` engine + the live trial against
`downstream-app/` both landed; `docs/trial-report-pr7.md` is the one-time
structured trial write-up (all four deliverables — trial plan, trial report,
`--mode=adopt` implementation, surfaced polish — complete).

The trial's downstream value also materialised later: dogfooding adopt-mode
into `downstream-app` is exactly what surfaced the config-shadowing bug, fixed in
the 2026-05-21 config-shadowing fix
([docs/plans/archive/2026-05-21-skill-config-shadowing-fix.md](docs/plans/archive/2026-05-21-skill-config-shadowing-fix.md)).

---

### ✅ Tighten CLAUDE.md two-tier review wording from "or" to explicit same-AI / cross-AI split (imp-2) — DONE

**Status**: ✅ shipped 2026-05-21 — the info-architecture refactor PR (`refactor/tighten-info-architecture`) tightened the Tier-1 wording to "use the same AI as the implementer" in `CLAUDE.md` + `shared/CLAUDE.md.tmpl`'s Two-tier section, and replaced the bare `# or review-commit-by-codex` phrasing in `CONTRIBUTING.md` + `shared/CONTRIBUTING.md.tmpl` with the same-AI clarification.

**Why parked** (historical): CLAUDE.md's former "Tier-1 (after each focused commit, before push): `make review-commit-by-claude` or `make review-commit-by-codex`" presents both targets as equally valid options. The discipline (per LESSONS.md 2026-05-19 entry, surfaced via user push-back during PR #6 impl) is that Tier-1 uses the **same AI as the implementer** (Claude→Claude, Codex→Codex), and cross-AI review only fires at Tier-2 (claude[bot] + chatgpt-codex-connector). The "or" wording is too permissive and led to me using Codex for Tier-1 on Steps 2–3 before the user caught it.

**Triggers to pick up**:
- Next plan-review session opens (this is a fundamental-shift candidate per LESSONS.md's "Promotion to CLAUDE.md only for FUNDAMENTAL shifts" rule).
- Any other contributor hits the same "or" ambiguity.

**Rough effort**: ~30 min — one CLAUDE.md edit + same edit in `shared/CLAUDE.md.tmpl` + parametrized test in `tests/test_triage_byte_identity.py` to assert both files have the same updated wording. Likely needs a tiny plan PR since it changes the workflow contract.

---

## PR #5 follow-ups

### ✅ "When adding a new Make target with overlapping semantics, audit + mirror the existing guards" (process lesson) — DONE in PR #5c

**Status**: shipped 2026-05-18 — captured as `LESSONS.md` entry #6.

**Source**: PR #5b Codex Tier-2 fold (`61f0101`). When I added
`review-commit-by-{codex,claude}` (semantically overlapping
`review-plan-by-{codex,claude}`), I missed the `test -f "$(PLAN_FILE)"`
guard that the plan-review targets already had. Codex caught it.

For generated projects: the lesson is project-local and doesn't ship in
the shared template (which starts empty). Generated projects accumulate
their own equivalent if/when they encounter the pattern.

---
