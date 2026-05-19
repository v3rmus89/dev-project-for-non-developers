# Skill PR #7 — hybrid real-project trial + adoption-mode redesign

> Hybrid PR (per user decision 2026-05-19): runs the **real-project trial** on `~/Desktop/Code/Boxette/call-details/` AND ships the **adoption-mode UX redesign** (`--mode=adopt` analyze-then-decide-with-owner). The trial's `--dry-run` / `--diff` is the empirical data source for the adoption-mode recommendation heuristics; the trial ends with a real `--apply --mode=adopt` against `call-details/` using the new policies.

## Context

PR #1–#6 shipped: Python + Node-TS + Go (PR #1–#3), two-tier code review + plan-loop improvements (PR #4), observability + self-improvement layer (PR #5), uv support for Python (PR #6). The current adoption contract (PR #1, unchanged through PR #6) is **all-or-nothing**: `bootstrap.py --apply` aborts with "collision detected" if any target file already exists, unless `--overwrite-existing` is passed (which then overwrites every colliding file). For a real-world existing project like `call-details/` — which has 4 high-value files the skill writes (`CLAUDE.md`, `pyproject.toml`, `.python-version`, `.gitignore`) AND 15 cleanly-writable files — neither option is acceptable: aborting blocks the user from any benefit; overwriting destroys irreplaceable domain content (call-details' `CLAUDE.md` has 97 lines of PII rules, architecture map, business TZ, onlinepbx specifics).

**Empirical collision baseline** (closes Codex iter-1 #2 — earlier draft claimed 8 collisions including `README.md`, `uv.lock`, `src/`, `tests/`; verified false via actual `bootstrap.py --dry-run --language python --project-name call-details --out ~/Desktop/Code/Boxette/call-details/`):

- **4 MODIFY (collisions, existing files the skill would write)**: `.gitignore`, `.python-version`, `CLAUDE.md`, `pyproject.toml`
- **15 CREATE (clean writes, no target file exists)**: `.editorconfig`, `.github/pull_request_template.md`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `AGENTS.md`, `BACKLOG.md`, `CONTRIBUTING.md`, `LESSONS.md`, `Makefile`, `docs/plans/README.md`, `pytest.ini`, `ruff.toml`, `scripts/run-with-clean-env.py`, `src/main.py`, `tests/test_smoke.py`

`README.md` and `uv.lock` exist in `call-details/` but the skill never writes them, so they're not collisions. `src/` and `tests/` directories exist but the skill writes `src/main.py` and `tests/test_smoke.py` — file-inside-existing-directory, not collision.

PR #7 ships `--mode=adopt` to replace the all-or-nothing dichotomy with a **per-file analyze-then-decide-with-owner** contract. Per user 2026-05-19, the contract is **content-driven** (not a hardcoded policy table) — different projects need different choices; the analyzer + recommendation engine is the value, not a static rule set.

### Sequencing within PR #7

The trial and the redesign are intertwined because each informs the other:

1. **Phase A — Trial baseline (no new code yet).** Run `bootstrap.py --dry-run --language python --project-name call-details --out ~/Desktop/Code/Boxette/call-details/` (PR #6 contract) to confirm the collision manifest. (Already run during plan iter-1 fold; results captured in the empirical baseline above.) Run `bootstrap.py --diff --language python --project-name call-details --out ~/Desktop/Code/Boxette/call-details/` to inspect each of the 4 collisions in detail. Capture findings as a per-file empirical dataset.
2. **Phase B — Adoption-mode design informed by Phase A.** Use Phase A's per-file evidence to draft the recommendation heuristics. Validate the heuristics against the call-details collision set: does each rule produce a recommendation a thoughtful human would agree with?
3. **Phase C — Adoption-mode implementation.** Ship `--mode=adopt` per the validated design. Comprehensive test coverage (unit + integration + smoke).
4. **Phase D — Trial completion.** Phase D **preflight** (closes Codex iter-1 #4 — `call-details/` is currently a live working repo; the restore manifest only protects bootstrap-written paths, not unrelated dirty state): (i) capture `git -C <target> rev-parse HEAD` + `git status --short` + current branch; (ii) require clean `git status --short` OR explicit owner waiver naming the unrelated dirty paths; (iii) create a fresh `feat/pr7-trial-adoption` branch in the target (`git -C <target> checkout -b ...`); (iv) record the planned-files list. THEN run `bootstrap.py --apply --mode=adopt --language python --project-name call-details --out ~/Desktop/Code/Boxette/call-details/` for real. Owner reviews each interactive prompt. After apply: (v) record `git -C <target> diff --stat HEAD~0`; (vi) verify the restore manifest restores cleanly via `bootstrap.py --restore <manifest>` round-trip on a copy of the target. Document everything in `docs/trial-report-pr7.md`.
5. **Phase E — Trial-surfaced docs + BACKLOG only** (closes Codex iter-1 #7 — earlier "small fixes / docs improvements / BACKLOG entries" was open-ended scope creep; this PR already changes CLI grammar + manifest format + interactive UX + restore behaviour + tests + docs + live-repo trial). Phase E is **limited to docs additions and BACKLOG entries**. Any code polish that the trial surfaces becomes a follow-up PR unless it blocks the adoption-mode acceptance gates (in which case it folds into a Phase B/C iteration before that gate).

### Pre-loop user-decided scope constraints (before iter-1)

- **New flag is `--mode=adopt`** (closes Codex iter-1 #1 — earlier draft was contradictory: claimed `--mode=adopt` both joined the existing mutually-exclusive `--dry-run`/`--diff`/`--apply` group AND required explicit `--apply --mode=adopt`). Resolution: `--mode=adopt` is an **adoption modifier** that REQUIRES explicit `--apply` (write safety — never auto-implies an apply); is **invalid** with `--dry-run`, `--diff`, or `--restore`. NOT a fourth element of the mode-group. Use `--diff` (PR #6 contract) for read-only inspection; `--apply --mode=adopt` for the per-file analyze-then-decide-with-owner write.
- **Adoption-mode replaces collision-abort for `--apply` when `--mode=adopt` is set** — explicit opt-in; the existing collision-abort behaviour stays the default for unset `--mode=adopt`. `--overwrite-existing` is still a separate escape hatch for nuclear-override use cases.
- **Trial target is `~/Desktop/Code/Boxette/call-details/` exactly** (no fixture copy) — the empirical data is most valuable from the real target. Use `--dry-run` / `--diff` extensively before any `--apply --mode=adopt`; the analyze-phase's recommendations get owner confirmation before any write.
- **Trial-report artifact is `docs/trial-report-pr7.md`** (NOT `docs/lessons.md` — that name collides with the live `LESSONS.md`; renamed per Codex iter-3 #3 fold during the Plan PR #6 loop). The trial-report is a frozen snapshot of "how the skill behaved during this trial"; LESSONS.md is the ongoing per-session append-only log.
- **NO uv-binary version pin in CI** — PR #6's pre-loop user decision stays; PR #7 doesn't revisit.
- **NO migration tool (pip → uv)** — separately parked in BACKLOG (b) from PR #6.

## Scope

### IN scope

| # | Change | Where |
|---|---|---|
| 1 | New CLI flag `--mode=adopt` (closes Codex iter-1 #1 — resolves the contradictory framing in the iter-1 draft). **`--mode=adopt` is an adoption modifier, NOT a fourth mode in the mutually-exclusive `--dry-run`/`--diff`/`--apply` group.** Help text: `"Adoption modifier. Requires --apply. Enables per-file analyze-then-decide-with-owner UX for safe adoption into existing projects (see docs/usage.md). Invalid with --dry-run, --diff, --restore. For read-only inspection, use --diff."` Validation in `cli.py`: `--mode=adopt` without `--apply` → CLIError; `--mode=adopt` with `--dry-run`/`--diff`/`--restore` → CLIError. ALSO add `--auto-accept-recommendations` (bool flag, only meaningful with `--mode=adopt`) + `--non-interactive` (bool flag, mutually exclusive with `--auto-accept-recommendations`; only meaningful with `--mode=adopt`). | `bootstrap_lib/_flags.py` |
| 2 | New module `bootstrap_lib/adopt.py` — the analyze + recommend engine. Functions: `analyze_target(target_root, planned_files) -> AdoptionPlan`; `recommend_policy(rel_path, target_content, skill_content) -> PolicyRecommendation`; `format_recommendation_report(plan) -> str`. | `bootstrap_lib/adopt.py` (NEW) |
| 3 | Per-file `PolicyRecommendation` data class: `policy: Literal["WRITE","SKIP","OVERWRITE","WRITE_NEW","APPEND_MERGE"]`; `reason: str`; `confidence: Literal["high","medium","low"]`; `manual_review_needed: bool`. NamedTuple via class-syntax (per PR #6 Claude iter-2 #2 lesson). | `bootstrap_lib/adopt.py` |
| 4 | `AdoptionPlan` data class — wraps `PolicyRecommendation`s + the analyze-phase metadata (per-file: target file existence, size, sha256 of existing content, recognized "shape" markers). | `bootstrap_lib/adopt.py` |
| 5 | Recommendation heuristics (content-driven; informed by Phase A empirical data above — call-details collision set is `{.gitignore, .python-version, CLAUDE.md, pyproject.toml}`): (a) target file doesn't exist → `WRITE`; (b) target file is empty / whitespace-only → `WRITE`; (c) target content matches skill's template render byte-for-byte → `WRITE` (no-op rewrite; safe); (d) target file is `.gitignore` AND skill's patterns are NOT all already present → `APPEND_MERGE` with `manual_review_needed=false` (line-level idempotent: only append patterns missing from the target — closes Codex iter-1 #5; if all patterns already present → `SKIP` "already covered"); (e) target file is `.python-version` AND target's Python-version matches skill's `python_version` (3.12) → `WRITE` (byte-identical no-op); else `SKIP` with note "target pins a different Python version"; (f) target file is `CLAUDE.md`/`AGENTS.md`/`CONTRIBUTING.md`/`BACKLOG.md`/`LESSONS.md` AND non-trivial (>20 lines OR contains custom section headings not in skill template) → `WRITE_NEW` with `manual_review_needed=true` ("preserve target's domain content; merge manually with `diff -u <orig> <orig>.new`"); (g) target file is `pyproject.toml` AND non-trivial (has `[project] dependencies`, `[tool.*]`, or `[dependency-groups]` table) → `SKIP` with `manual_review_needed=true` ("project's pyproject.toml is the source of truth for deps; review the diff manually with `bootstrap.py --diff` for any worth-adopting fields"); **(h) DEFAULT for any existing non-empty file not matching rules (a)-(g) → `SKIP` with `manual_review_needed=true`** (closes Codex iter-1 #3 — earlier draft allowed unknown existing files to fall through to destructive WRITE; this is the core safety guarantee of adoption-mode and the reason `--mode=adopt` is safer than `--overwrite-existing`). `--auto-accept-recommendations` REFUSES to apply any policy with `manual_review_needed=true` — it falls back to interactive prompt OR fails with exit 2 if `--non-interactive` is also set. | `bootstrap_lib/adopt.py` |
| 6 | Interactive decide-phase UX: print the recommendation report (per-file rows), then for each conflicted file ask `"Apply [r]ecommended (default) / [s]kip / [o]verwrite / [n]ew / [a]ppend / [d]iff / [?]help / [q]uit ?"`. `--auto-accept-recommendations` skips the prompts; `--non-interactive` forces failure if any prompt would otherwise fire (CI-safety). | `bootstrap_lib/cli.py` + `bootstrap_lib/adopt.py` |
| 7 | Apply-phase wiring: when `--mode=adopt`, the existing `_apply_writes` machinery runs per the agreed `AdoptionPlan` rather than the all-or-nothing collision check. New restore-manifest entry types for `.new` writes and `APPEND_MERGE`. **`.new` collision rule** (closes Codex iter-1 #5 — earlier draft didn't say what happens if `<original>.new` already exists): if `<original>.new` exists at apply time, fail-loud with exit 2 + clear message ("`<original>.new` already exists — rename or remove it before running `--mode=adopt`; bootstrap will NOT overwrite an existing `.new` file"). Alternative (`<original>.new.<N>` rotation) parked as a future BACKLOG entry — fail-loud is safer for the non-developer audience's first encounter. **`APPEND_MERGE` semantics**: read target file line-by-line; for each line in skill's content, append ONLY if the line is not already present in target (set-comparison after stripping); preserves order of new additions; idempotent — running twice produces same result. Restore semantics: `.new` file is removed; append-merge restores by truncating target to the captured pre-append length. | `bootstrap_lib/cli.py` + `bootstrap_lib/manifest.py` |
| 8 | `--diff` mode extension: per-file `policy` annotation in the unified-diff header (e.g. `--- a/CLAUDE.md (target: 97 lines, domain-rich)` / `+++ b/CLAUDE.md (recommendation: WRITE_NEW)`) so the user sees the recommendation alongside the diff before running `--apply --mode=adopt`. | `bootstrap_lib/cli.py` |
| 9 | Tests: unit tests for `analyze_target` + `recommend_policy` (rule-by-rule); integration tests for `--mode=adopt` end-to-end against synthetic fixtures matching call-details collision shapes; interactive-prompt test via PTY mock OR `--auto-accept-recommendations` flag; `--non-interactive` failure path test | `tests/` (NEW: `test_adopt_engine.py`, `test_mode_adopt_smoke.py`; extensions to `test_bootstrap_cli.py`) |
| 10 | Active-docs updates: `README.md` "Status" + "Build sequence" (PR #7 ✅); `SKILL.md` invocation block + adoption-mode paragraph; `docs/usage.md` new "Adoption mode (`--mode=adopt`)" section covering analyze → recommend → decide → apply with a worked example based on call-details; `BACKLOG.md` close PR #7 entries + add PR #7 follow-ups. | `README.md`, `SKILL.md`, `docs/usage.md`, `BACKLOG.md` |
| 11 | NEW: `docs/trial-report-pr7.md` — one-time structured trial-experience write-up. Sections: (a) Trial target shape (call-details file inventory + collision set — counts + filenames + sha256s ONLY, no content excerpts); (b) Phase A empirical findings (per-file: target size + sha256, skill template sha256, recommended policy, reasoning); (c) Phase B → C design iterations (what heuristics started as, what the trial changed); (d) Phase D apply result (was `call-details/` better off after? was anything broken? — branch SHAs + `git diff --stat` summary, NOT diff content); (e) Skill UX gaps surfaced (what was confusing for a non-developer); (f) Recommendations for future skill polish (BACKLOG additions). **Privacy boundary** (closes Codex iter-1 #6 — call-details contains `secrets/`, `data/`, customer domain content; the skill repo will eventually be public): NO secrets, NO transcript / customer / PII data, NO raw file excerpts. Safe content: filenames, file sizes, sha256 hashes, structural categories ("X-line file with Y section headings"), policy decisions + reasoning. If in doubt about a section: summarize without quoting. NOT the same as ongoing `LESSONS.md`. | `docs/trial-report-pr7.md` (NEW) |
| 12 | LESSONS.md append (impl-session) for any new mistake-class surfaced during PR #7 work | `LESSONS.md` |

### NOT in scope

- **No `--mode=replace` / `--mode=overwrite` aliases.** `--overwrite-existing` already exists for that purpose; not bundling a renaming-bikeshed into PR #7.
- **No per-file policy table in CLI args** (e.g. `--policy CLAUDE.md=skip,Makefile=write`). Per user 2026-05-19: content-driven analysis + interactive decide-phase, NOT a flag soup.
- **No automatic content merging for `pyproject.toml` deps** (e.g. union user-deps + skill-deps). Adoption-mode recommends SKIP for pyproject — user reviews the diff manually. Auto-merge of TOML structure is a future BACKLOG entry.
- **No template-vs-existing semantic understanding for arbitrary files.** Heuristics use file-name + size + sha256 + shape markers; no LLM-call inside the bootstrap engine.
- **No retroactive adoption mode for PR #1–#6 generated projects.** Adoption-mode is a forward-looking adoption-time tool, not a re-adoption / sync tool.
- **No undo/redo within an interactive session.** If user picks the wrong policy, they `q`uit, fix their thinking, re-run. Restore manifest still works after the fact.
- **No `--mode=adopt` for Node or Go.** PR #7 trial uses a Python target; adoption-mode is python-first for now. Same-language-extension is parked for follow-up.

## Subsystem breakdown

### Bucket A — CLI flag + plumbing

| File | Change |
|---|---|
| `bootstrap_lib/_flags.py` | Add `--mode={dry-run,diff,apply,adopt}` mutually-exclusive flag (replaces the current `--dry-run` / `--diff` / `--apply` separate switches OR adds `--mode` as a new flag that overrides them — pick in iter-1 based on backwards compat). **Decision: add `--mode` as a new flag**, default `None`, which then resolves to one of the existing modes if `--mode` is unset. `--mode=adopt` is the only new value. Help text: `"Apply mode. 'adopt' enables per-file analyze-then-decide-with-owner UX for safe adoption into existing projects (see docs/usage.md). Default: derived from --dry-run/--diff/--apply (backward-compat)."` ALSO add `--auto-accept-recommendations` (bool flag) + `--non-interactive` (bool flag, mutually exclusive with `--auto-accept-recommendations`). |
| `bootstrap_lib/cli.py` | `_resolve_mode` learns the new `--mode=adopt` value. Adoption mode runs the analyze phase BEFORE the existing collision check; if analyze produces a clean plan (all `WRITE` policies, no conflicts), proceeds as normal apply. If conflicts exist, the recommend + decide phases run. `_apply_writes` learns the per-file policies. Restore-mode invalid-flag list extends with `--mode`, `--auto-accept-recommendations`, `--non-interactive`. |

### Bucket B — Adoption engine

| File | Change |
|---|---|
| `bootstrap_lib/adopt.py` (NEW) | The full analyze-then-recommend engine. ~250-400 lines. Functions: `analyze_target(target_root: Path, planned_files: dict[str, bytes]) -> AdoptionPlan`; `recommend_policy(rel_path: str, target_path: Path, skill_content: bytes, target_meta: TargetMeta) -> PolicyRecommendation`; `format_recommendation_report(plan: AdoptionPlan) -> str` (the user-facing report). Data classes: `PolicyRecommendation`, `AdoptionPlan`, `TargetMeta` (file shape: exists, size, sha256, content_sample). All NamedTuple via class-syntax. |
| `bootstrap_lib/manifest.py` | Extend manifest entry type to include `policy: str` (one of WRITE/SKIP/OVERWRITE/WRITE_NEW/APPEND_MERGE) + `target_path` (for WRITE_NEW: where the .new file goes; for APPEND_MERGE: where the appended-to original is). Restore semantics extended accordingly. |
| `bootstrap_lib/render.py` | No changes (render is mode-agnostic — produces the planned_files dict; adopt.py consumes it). |

### Bucket C — Interactive decide-phase UX

| File | Change |
|---|---|
| `bootstrap_lib/cli.py` | New `_interactive_decide(plan: AdoptionPlan) -> AdoptionPlan` function. For each conflicted file, prompts the user with the recommendation + alternative options. Uses stdin (no prompt-toolkit dep — non-developer audience shouldn't need extra installs). `--auto-accept-recommendations` short-circuits to "yes to all recommendations". `--non-interactive` fails with exit 2 if any prompt would fire. |
| `docs/usage.md` | Document the prompt UX with example output |

### Bucket D — Tests

| File | Asserts |
|---|---|
| NEW: `tests/test_adopt_engine.py` | Unit tests for `recommend_policy` rule-by-rule (one test per heuristic rule a-h above, plus negative tests for files that should fall through to default WRITE). `analyze_target` tests with synthetic file fixtures. `format_recommendation_report` golden-output test (assert structure, not byte-equal). |
| NEW: `tests/test_mode_adopt_smoke.py` | End-to-end `--mode=adopt --auto-accept-recommendations` against a synthetic fixture matching call-details collision shape (8 collisions + 12 clean writes). Asserts: collision-abort does NOT fire; per-file policies match expected; restore manifest captures the policies; restore works (each policy type's restore semantics tested). |
| `tests/test_bootstrap_cli.py` (extended) | `--mode=adopt` valid + invalid combinations; `--mode=adopt` in restore mode → error; `--non-interactive` with conflicts → exit 2; `--auto-accept-recommendations` + `--non-interactive` mutually exclusive |
| `tests/test_manifest.py` (extended) | New policy fields serialize/deserialize cleanly; restore handles each policy type |

### Bucket E — Trial execution

**This bucket is unique to PR #7 — it's the trial, not test code.** Phase A runs after PR #7 plan converges + Phase A subagent task. Phase D runs after PR #7 impl ships.

| Phase | Activity | Deliverable |
|---|---|---|
| A (pre-impl, post-plan-converge) | Run `bootstrap.py --dry-run --language python --out ~/Desktop/Code/Boxette/call-details/` (PR #6 contract). Run `--diff` for each collision. Inspect target's actual file contents per collision. | Empirical findings dataset in `docs/trial-report-pr7.md` Section (a) + (b). Adjusts the heuristic rules in Bucket B's recommend_policy if needed. |
| D (post-impl) | Run `bootstrap.py --apply --mode=adopt --out ~/Desktop/Code/Boxette/call-details/` for real. Owner reviews each interactive prompt. Files actually adopted. | Trial-report Section (d) — was call-details/ better off after? Anything broken? Any user-facing UX gaps? |

### Bucket F — Active docs + LESSONS

| File | Change |
|---|---|
| `README.md` | Status section: PR #7 ✅; Build sequence: PR #7 ✅ hybrid trial + adoption-mode redesign; mention `--mode=adopt` in the feature list as "safe adoption into existing projects". |
| `SKILL.md` | Invocation block adds `[--mode {dry-run,diff,apply,adopt}] [--auto-accept-recommendations] [--non-interactive]`. New short paragraph describing adoption mode. |
| `docs/usage.md` | New "Adoption mode (`--mode=adopt`)" section (~2 pages). Worked example based on `call-details/`: dry-run output, recommendation report, interactive prompt sequence, final apply, restore. |
| `BACKLOG.md` | Close PR #7 entries (c), (d), (e) from PR #6's BACKLOG; add PR #7 follow-ups (any surfaced by trial — likely: per-file diff annotations richer rendering, undo within interactive session, language extension to Node/Go). |
| `LESSONS.md` | Append entry (impl-session) for any new mistake-class. Already-known candidate: "Restore-manifest extensions for new policy types must preserve backward-compat with PR #6 manifests" (probable test surface). |

## Architecture decisions

- **`--mode=adopt` is opt-in, not a default.** Plain `--apply` keeps the existing PR #1 collision-abort contract. Backwards-compatible. Users adopt the new mode deliberately.
- **Analyze phase reads target files but writes NOTHING.** Pure analysis. The decide-phase is where the contract becomes mutable; apply-phase is where the writes happen.
- **Recommendation heuristics are content-driven, not policy-table-driven** (per user 2026-05-19). Heuristics inspect: file existence, size, sha256-vs-skill-template, recognized shape markers (frontmatter, section headings, code patterns). Different projects produce different recommendations.
- **Interactive decide UX uses stdin, not prompt-toolkit.** Keep the non-developer audience's prereqs minimal (no `pip install prompt-toolkit`). Plain readline-style prompts.
- **`.new` writes go alongside the original** (`CLAUDE.md.new` next to `CLAUDE.md`). User's existing file is untouched. Visual diff via the user's normal git/editor tooling.
- **APPEND_MERGE only for `.gitignore`** initially. Other files (e.g. `README.md` with a "Status" section append) are too risky for automated merging — recommend SKIP with manual diff.
- **The trial-report (`docs/trial-report-pr7.md`) is a one-time deliverable**, not a recurring artifact. PR #8+ won't add to it. Future trials get their own report.
- **Restore-manifest format-version bumps to 2** for the new policy fields. Existing v1 manifests still restore correctly (engine checks `format_version` and dispatches).

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Interactive prompts hang on non-TTY stdin (CI runners) | Detect `sys.stdin.isatty()`; if False AND `--auto-accept-recommendations` not set AND there are conflicts → exit 2 with `--non-interactive`-equivalent error. Test via fixture-injected pipe stdin. |
| Heuristics misfire on call-details — produce a recommendation set the user rejects | Phase A (Trial baseline) is the empirical validation pass. If a heuristic produces "wrong" recommendations against the real target, adjust the rule BEFORE finalizing Bucket B. The plan-loop iter-2+ should hold off the Bucket B design lock until Phase A data is in. |
| Restore-manifest v2 backward-compat breaks for users with v1 manifests | `format_version` check in `load_manifest`; v1 manifests dispatch to legacy restore. Test fixture: a v1 manifest from PR #1–#6's apply paths still restores cleanly. |
| `WRITE_NEW` files (`CLAUDE.md.new`) confuse the user — they don't know to merge | Apply-phase final summary print lists every `.new` written + says "merge each `.new` file into the original manually; review with `diff -u CLAUDE.md CLAUDE.md.new`". Same for APPEND_MERGE summary. |
| Tests-passing-for-wrong-reason: the synthetic fixture matches call-details so well that the tests pass via fixture-magic, not contract | Phase A trial is the contract-validation: run the unit tests + the smoke test, THEN run the real trial against `call-details/` — if behaviour diverges, the synthetic fixture was wrong. Phase D documents any divergence. |
| Adoption-mode complexity makes the skill harder for non-developers (the audience) | `--mode=adopt` is opt-in. Greenfield users (the primary audience) never see it. Adoption-mode is for the smaller "existing project owner" audience who already understand "merge conflicts" conceptually. |

## Verification (acceptance criteria)

### Phase 1 — pre-implementation evidence (this plan PR)

1. **Bidirectional plan-review loop**:
   ```bash
   make review-plan-by-codex  PLAN_FILE=docs/plans/2026-05-19-skill-pr7-hybrid-trial-adoption-mode.md ITERATION=N
   make review-plan-by-claude PLAN_FILE=docs/plans/2026-05-19-skill-pr7-hybrid-trial-adoption-mode.md ITERATION=N
   ```
   (BACKLOG f bug fix landed in PR #6, so the make targets work without the manual workaround.)

2. **Pre-next-iter consistency self-check**:
   ```bash
   make review-plan-consistency-by-claude PLAN_FILE=docs/plans/2026-05-19-skill-pr7-hybrid-trial-adoption-mode.md ITERATION=<upcoming>
   ```

3. **Pre-task gate** (per `CLAUDE.md` pre-coding discipline merged in `511a181`): impl PR opening message must state regression safety + outcome measurement.

4. **Mandatory human-approval gate** satisfied.

### Phase 2 — post-implementation gates

1. `make check` green in skill repo (existing 351 tests + ~30 new adoption tests; expected ~380 total)
2. `make doctor` green
3. Generated-project smoke walks for all four combinations still pass (python+pip, python+uv, nodejs, go)
4. `--mode=adopt --auto-accept-recommendations` smoke walk against synthetic call-details-shaped fixture passes
5. `--mode=adopt` interactive smoke walk via PTY mock passes
6. `--non-interactive` failure-path test passes
7. Restore-manifest v2 backward-compat with v1 manifest test passes
8. Trial against live `~/Desktop/Code/Boxette/call-details/` — Phase A run committed via `docs/trial-report-pr7.md` Section (a)+(b); Phase D run committed via Section (d)
9. claude[bot] + Codex auto-review return clean
10. Draft impl PR opened from `feat/skill-pr7-hybrid-trial-adoption-mode` branch

## Iteration log (this plan)

| Iter | Findings | Verdict |
|---|---|---|
| 1 (codex) | 7 (4× imp-3, 3× imp-2) | do not implement yet — all 7 folded. Four-questions framework applied; every premise verified empirically. **The reviewer actually ran the dry-run against the live target** (impressive) and caught that my plan's "8 collision files" baseline was off — actual collisions are 4, not 8 (`README.md` + `uv.lock` exist but aren't bootstrap writes; `src/`/`tests/` are dirs not file collisions). Verified locally via `bootstrap.py --dry-run --language python --project-name call-details --out ~/Desktop/Code/Boxette/call-details/` before folding. Folds: P1 CLI contract — `--mode=adopt` is now an adoption MODIFIER requiring `--apply`, NOT a fourth mode in the mutually-exclusive group (resolves the iter-1-draft contradiction); P2 collision baseline corrected to 4 MODIFY + 15 CREATE; P3 default for unknown existing non-empty files = `SKIP` with `manual_review_needed=true` (NOT `WRITE` — was the core `--overwrite-existing` danger under a safer-looking name); P4 Phase D preflight (branch/SHA capture, clean-status check, trial branch creation, restore-manifest round-trip verification); P5 `.new` collision rule (fail-loud if exists) + `APPEND_MERGE` idempotence semantics (line-level only-append-missing); P6 trial-report privacy boundary (no secrets / customer / raw excerpts; safe content = names + sizes + hashes + structural categories); P7 Phase E scoped to docs+BACKLOG only (code polish becomes follow-up PRs). Next: consistency self-check before Claude iter-2 |

## Evidence table — what was folded and where

| Iter | Importance | Finding | Action |
|---|---|---|---|
| 1 | 3 | **(a) fold** — Codex iter-1 #1: CLI contract contradictory — plan said `--mode=adopt` joined the mutually-exclusive `--dry-run`/`--diff`/`--apply` group AND required explicit `--apply --mode=adopt`. Cannot both be true. Plus trial commands missing `--project-name` (current `_resolve_mode` requires it). Implementer couldn't know intended argparse contract | Resolved: `--mode=adopt` is an adoption modifier that REQUIRES `--apply` (write safety — never auto-implies an apply); is invalid with `--dry-run`/`--diff`/`--restore`. NOT a fourth element of mode-group. Updated Pre-loop scope, Scope #1, Bucket A row, Sequencing, Verification commands (added `--project-name call-details` to every trial invocation). |
| 1 | 3 | **(a) fold** — Codex iter-1 #2: "8 collision files" baseline was false. Codex actually ran the dry-run + file-existence check against the live target and found 4 actual collisions (`CLAUDE.md`, `pyproject.toml`, `.gitignore`, `.python-version`); `README.md` + `uv.lock` exist in target but skill never writes them; `src/`/`tests/` are dirs (bootstrap writes files inside, not the dirs) | Re-ran dry-run locally during fold: confirmed 4 MODIFY + 15 CREATE. Updated Context "Empirical collision baseline" subsection with verbatim file lists. Updated heuristic rules in Scope #5 to match real collision set (4 files with specific heuristics: .gitignore APPEND_MERGE, .python-version WRITE-if-version-matches-else-SKIP, CLAUDE.md WRITE_NEW, pyproject.toml SKIP). Dropped misfiring rule (h) "src/ or tests/ directories populated → SKIP" since the bootstrap doesn't write directory entries. |
| 1 | 3 | **(a) fold — CRITICAL SAFETY** — Codex iter-1 #3: tests row said "files that should fall through to default WRITE" — for adoption into existing projects, an existing non-empty unrecognized file defaulting to WRITE recreates the `--overwrite-existing` danger under a safer-looking mode, especially with `--auto-accept-recommendations` | Default for unknown existing non-empty file is now `SKIP` with `manual_review_needed=true` (NOT `WRITE`). Only `WRITE` for: missing target, empty target, or byte-identical target. `--auto-accept-recommendations` REFUSES policies with `manual_review_needed=true` — falls back to interactive prompt OR fails with exit 2 if `--non-interactive` also set. This is the core safety guarantee that distinguishes `--mode=adopt` from `--overwrite-existing`. |
| 1 | 3 | **(a) fold** — Codex iter-1 #4: live apply against `call-details/` has no clean-state preflight. Target's `git status --short` is already dirty (modified `.claude/settings.json`, untracked `.claude/scheduled_tasks.lock`, untracked `tools/`). Restore manifest only protects bootstrap-written paths — no clean experiment boundary or audit trail for the live repo | Phase D preflight added: capture branch/SHA, require clean `git status --short` OR explicit owner waiver naming the dirty paths, create a fresh `feat/pr7-trial-adoption` branch in the TARGET (not the skill repo), record planned-files list; run apply; record `git diff --stat`; verify restore-manifest round-trip on a copy of the target before declaring success. Sequencing section updated. |
| 1 | 2 | **(a) fold** — Codex iter-1 #5: `.new` and `APPEND_MERGE` policies lacked collision/idempotence rules. `WRITE_NEW` would clobber a stale `<path>.new`; `APPEND_MERGE` "contains skill's patterns" wording was ambiguous (re-append vs only-missing) | `.new` collision rule: fail-loud with clear message if `<original>.new` already exists (alternative rotation-suffix parked as future BACKLOG). `APPEND_MERGE` semantics: line-level set-comparison after stripping; append only missing lines; preserves order of new additions; running twice produces same result. Restore semantics extended to truncate-to-captured-pre-append-length. Scope #7 + Bucket B updated. |
| 1 | 2 | **(a) fold** — Codex iter-1 #6: trial-report privacy boundary missing. Live target contains `secrets/`, `data/`, customer-domain operational docs; future skill repo is public-bound | Privacy-boundary subsection added to trial-report row (Scope #11): NO secrets / customer / PII data / raw file excerpts. Safe content = filenames + sizes + sha256 hashes + structural categories + policy decisions. Default policy: summarize without quoting. |
| 1 | 2 | **(a) fold** — Codex iter-1 #7: Phase E was open-ended scope creep — "Any small fixes / docs improvements / BACKLOG entries". PR already changes CLI grammar + manifest format + interactive UX + restore behaviour + tests + docs + live-repo trial | Phase E narrowed: docs additions + BACKLOG entries only. Code polish that the trial surfaces becomes a follow-up PR unless it blocks the adoption-mode acceptance gates (in which case it folds into Phase B/C before that gate). Sequencing wording updated. |

## Lessons surfaced

(filled in as reviewer-proposed lessons accumulate)

## What we are NOT doing in this PR

- **No CLI policy table.** Content-driven analyze + interactive decide only.
- **No automatic content merge for non-`.gitignore` files.** `WRITE_NEW` is the safe recommendation; user merges manually.
- **No retroactive adoption mode for already-bootstrapped projects.** PR #7 is forward-only.
- **No `--mode=adopt` for Node or Go.** Python-first.
- **No prompt-toolkit dependency.** Plain stdin.
- **No undo within interactive session.** User quits + re-runs.

## Critical files to read before each iter's review

For Codex / Claude:

- `docs/plans/2026-05-18-skill-pr6-uv-support.md` — closest precedent; documents the BACKLOG (c) framing of analyze-then-decide-with-owner that PR #7 implements
- `docs/plans/README.md` — workflow doc
- `bootstrap_lib/_flags.py` — current flag structure
- `bootstrap_lib/cli.py` lines 34-101 — current `_resolve_mode` + collision-abort logic (the existing PR #1 contract)
- `bootstrap_lib/manifest.py` — current manifest format (PR #7 extends to v2)
- `bootstrap_lib/detect.py` (post-PR-#6) — `DetectionResult` NamedTuple class-syntax precedent
- `bootstrap_lib/render.py` — `render_all` produces the planned_files dict that adopt.py consumes
- `~/Desktop/Code/Boxette/call-details/` (the trial target — DO NOT EDIT; read-only inspection)
- `BACKLOG.md` PR #6 follow-ups section (c), (d), (e) — what PR #7 is supposed to close
- The 8 known collision files in `call-details/` to confirm the empirical baseline before iter-1 review
