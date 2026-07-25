# Pre-expansion structural refactors (weight reduction before the language roadmap)

## Context

A full-repo investigation (2026-07-05 session) found no correctness defects but four
kinds of structural weight that will tax every future PR:

1. **Duplicated verbatim surfaces.** Six helper scripts exist twice — the working copy
   under `scripts/` and a byte-identical template copy under `shared/` — with
   `tests/test_selftest_overlap.py:31` (`_SCRIPT_TEMPLATE_PAIRS`) failing on drift.
   The test makes the duplication safe but every change is still two hand-edits, and
   the template copies pass through Jinja at render time, so any future `{{` or `{%`
   token in a script would explode under `StrictUndefined` even though the file is
   meant to be verbatim.
2. **AI prompts embedded in Make recipes.** The repo `Makefile` (511 lines) embeds
   9 prompt strings (5 distinct texts: plan-review, commit-review plan-bound,
   commit-review unbound, consistency, fact-check-interpret), each a ~2,000-character
   single-line double-quoted shell word. `shared/Makefile.review.tmpl` (459 lines)
   holds the same texts (the Tier-1 pair via the `tier1_prompt` macro at
   `shared/Makefile.review.tmpl:16`, invoked from the recipes and from
   `shared/CONTRIBUTING.md.tmpl`), and `scripts/ab-replay.py:69` hand-mirrors the
   plan-review text a THIRD time with its own `<<PLAN>>`/`<<ITER>>` placeholder
   scheme — its comment (`scripts/ab-replay.py:66`) warns that `str.format` is
   unsafe because the prompt contains literal JSON-fence braces, a constraint the
   Bucket B substitution helper inherits (AD2). This design already produced one
   incident class: LESSONS.md 2026-06-09 — backticks in prompt text become shell
   command substitution inside a double-quoted recipe word. Every new review
   variant multiplies copies.
3. **`bootstrap_lib/cli.py` is becoming a god module.** 1,283 lines holding four
   jobs: flag/mode validation, the interactive adopt decide-phase UI, the adopt apply
   orchestrator, and ~200 lines of post-apply guidance printing. The user's roadmap
   (a front-end language next, Node/Go adopt-mode after) lands mostly in this file;
   splitting it before that work keeps each future diff small and reviewable.
4. **Process artifacts outweigh the product.** 18 pre-existing plan files under
   `docs/plans/` (19 counting this plan) trip the `make status` multi-plan WARN on
   every run; `BACKLOG.md` is 1,347 lines
   with closed items interleaved; hot-path comments carry review-case citations
   ("closes Codex iter-22 P1") whose tracker-ID half duplicates what git blame and
   the plans' evidence tables already record.

This plan sequences five behavior-preserving refactor buckets to land BEFORE the
front-end-language plan. Rationale for the ordering: Bucket A creates the verbatim-ship
mechanism that Bucket B's prompt files need (prompt files must ship to generated
projects WITHOUT gaining a second template copy — otherwise Bucket B recreates the
exact duplication Bucket A removes); Bucket C shrinks the file the language roadmap
will grow; Buckets D/E are independent hygiene.

### Pre-coding declarations (CONTRIBUTING.md)

- **Regression safety**: auto-testable. All buckets are behavior-preserving for
  generated output except Bucket B (which changes HOW prompts reach the review CLIs,
  covered by `tests/test_makefile_review_targets.py`'s recipe tests and new
  prompt-file tests) and Bucket D (repo-file moves, covered by
  `tests/test_status_target.py` fixtures plus one manual `make status` run).
  The full suite (1,032 tests collected at plan time) plus `make check` gates every
  implementation PR.
- **Outcome measurement**: no business metric — internal change (refactor/hygiene).

## Scope

### IN scope

| # | Item | Bucket |
|---|---|---|
| 1 | Verbatim-ship mechanism in `bootstrap_lib/render.py`: shared files that are byte-verbatim (currently the six `scripts/*.py` templates) ship from their single working copy; delete the six `shared/scripts-*.tmpl` duplicates | A |
| 2 | Extract the five distinct review-prompt texts from `Makefile` / `shared/Makefile.review.tmpl` into `prompts/` files shipped verbatim; recipes build the prompt at runtime via a small substitution helper; retire the `tier1_prompt` macro; point `scripts/ab-replay.py` at the same prompt file (removes the third hand-mirrored copy); merge the dormant optional `/simplify` pass into the Tier-1 prompt focus list (no evidence it ever fired — see AD7) | B |
| 3 | Split `bootstrap_lib/cli.py` into focused modules (decide-phase UI, apply pipelines, post-apply guidance); update test imports; no compatibility re-exports | C |
| 4 | `docs/plans/archive/` for completed plans + `BACKLOG.md` split into active vs. closed; repo-wide sweep of every repo-local `docs/plans/` reference (12 files at plan time, including the `DEFAULT_PLAN` constants at `scripts/ab-replay.py:58` and `scripts/verify-v13-5.py:78`); rewrite the moved plans' own relative links; a general link-existence test so future moves cannot silently break in-tree links; document the archive convention in `docs/plans/README.md`; add the adopted-project sync runbook to `docs/usage.md` + the `--mode=upgrade` BACKLOG entry | D |
| 5 | Comment de-citation pass over `bootstrap_lib/` + `scripts/` (keep the constraint, drop the tracker-ID); rename `scripts/verify-v13-5.py` to a descriptive name; move `bootstrap_lib/render.py:211`'s function-local `import tempfile` to module top | E |

### NOT in scope (with reasons)

| Item | Why not |
|---|---|
| Any new language (front-end, Node/Go adopt) | Separate roadmap plans; this plan is their prerequisite, not their vehicle |
| Reducing the safety layering (two-layer path checks, TOCTOU re-checks) | Deliberate defense-in-depth, not duplication debt |
| Comment de-citation inside `tests/` | Test docstrings often ARE the pinned-contract documentation; churn/value ratio poor — revisit only if Bucket E proves painless |
| Review-loop feature additions | Opposite direction of this plan; a BACKLOG policy note ("new review-loop features need an A/B-measured win first") is added in Bucket D's PR |
| Repo-wide make-expansion hardening (`PLAN_FILE`/`ITERATION` `$(shell)` injection) | Already parked in `BACKLOG.md`; Bucket B neither fixes nor worsens it (values still flow through make vars) |
| `--mode=upgrade` re-adopt engine (durable per-file record + auto-update of unmodified files) | Feature, not a behavior-preserving refactor; Bucket D adds the BACKLOG entry with a concrete pick-up trigger instead |

## Subsystem breakdown

### Bucket A — verbatim-ship mechanism (dedup `scripts/` ↔ `shared/`)

**Problem.** `SHARED_TEMPLATE_MAP` (`bootstrap_lib/render.py:9`) routes six script
entries through Jinja even though they are byte-verbatim copies of `scripts/*.py`;
`tests/test_selftest_overlap.py:31` enforces the byte-identity by hand.

**Change (intent level).**
- Add a `SHARED_VERBATIM_MAP` alongside `SHARED_TEMPLATE_MAP` in
  `bootstrap_lib/render.py`: output rel-path → skill-repo source path, an ARBITRARY
  repo-relative path (Tier-2 codex P1). The initial six sources merely happen to
  live under `scripts/`; the map must NOT hard-code that prefix, because Bucket B
  ships `prompts/*.txt` through this same mechanism (source under `prompts/`, not
  `scripts/`). `render_all` and `planned_paths` emit these entries by reading bytes
  directly — no Jinja.
- Remove the six `scripts/*` entries from `SHARED_TEMPLATE_MAP`; delete the six
  `shared/scripts-*.tmpl` files.
- `planned_paths()` must include verbatim entries so the intake collision check and
  `tests/test_render.py`'s planned-paths-equals-render-keys property stay true.
- Replace the six-pair byte-identity parametrization in
  `tests/test_selftest_overlap.py` with: (a) every `SHARED_VERBATIM_MAP` source file
  exists and is non-empty; (b) rendered output for those rel-paths is byte-equal to
  the source file (the property becomes structural rather than hand-synced);
  (c) the existing executable-bit/shebang assertions keep firing against the same
  rel-paths.
- Retarget the shared-template SCAN tests (Tier-2 codex P1, verified): the six
  deleted `scripts-*.tmpl` names are members of
  `tests/test_shared_templates.py::SHARED_TEMPLATES_TO_SCAN`, and
  `test_shared_template_renders_without_undefined_error` +
  `test_no_boxette_isms_in_shared_templates` call `get_template()` on each — after
  deletion those raise `TemplateNotFound` and turn `make check` red. Drop the six
  script entries from `SHARED_TEMPLATES_TO_SCAN` (the verbatim files are no longer
  Jinja templates, so "renders without undefined" and "no boxette-isms in a
  *rendered template*" no longer apply); the byte-equality property from the bullet
  above is their replacement coverage.
- Grep-the-suite discipline (Tier-2 meta): this enumeration is necessary but NOT
  verified-exhaustive. Before implementing Bucket A, grep the full `tests/` tree for
  each deleted template basename (`scripts-run-with-clean-env.py.tmpl`, …) and
  retarget every hit; the two scan tests above are the ones known at plan time.
- Verify the executable-bit path end-to-end: generated `scripts/*.py` must keep mode
  0755 via `manifest.default_mode_for` — the lookup over the
  `manifest.EXECUTABLE_TARGETS` set, the same single mechanism Bucket B extends for
  its new helper — exactly as today (smoke tests
  `tests/test_smoke_python_generated.py` already execute generated scripts).

**Why not a sync-copier make target instead?** It keeps two files per script and
adds a step to forget; the map removes the second file entirely. The trade-off — 
`shared/` stops being the complete inventory of shipped files — is repaid by
`render.py` becoming that inventory (both maps in one module), and is documented in
`docs/usage.md`.

**Effect on adopt mode.** None by design: the planned rel-paths are identical before
and after; only the byte source changes. `tests/test_adopt_engine.py` /
`tests/test_mode_adopt_smoke.py` must pass unchanged (any planned-set count they pin
stays the same number).

### Bucket B — prompt extraction (depends on Bucket A)

**Problem.** Nine prompt strings embedded in the repo `Makefile` — plus the
template's macro-sourced copies and ab-replay's hand-mirror; shell-quoting hazard class (LESSONS.md
2026-06-09); prompt diffs unreadable; every review variant multiplies copies; the
`tier1_prompt` macro plus three byte-identity/shape tests in
`tests/test_shared_templates.py` exist only to police the copies.

**Change (intent level).**
- New top-level `prompts/` directory (ships to generated projects at the same
  rel-path, via Bucket A's verbatim map): `plan-review.txt`,
  `commit-review-plan-bound.txt`, `commit-review-unbound.txt`,
  `plan-consistency.txt`, `fact-check-interpret.txt`. Files contain the current
  prompt texts verbatim except that make-expanded values become named placeholders
  (`{PLAN_FILE}`, `{ITERATION}`, `{KEY}`, `{COMMIT_REF}`, `{VERIFICATION_JSON}`).
  `{VERIFICATION_JSON}` replaces the fact-check recipes' current in-recipe command
  substitution (`VERIFICATION JSON: $$(cat '$(FACT_CHECK_VERIFY_OUT)')`) — once the
  prompt is inert file data the shell no longer expands that, so the helper must
  inject the JSON itself (iter-1 FN1).
- New `scripts/render-review-prompt.py` (shipped verbatim like its six siblings).
  Two DISTINCT executable-bit requirements, both needed (Tier-2 codex P2):
  (i) generated projects — add it to `manifest.EXECUTABLE_TARGETS` so the written
  copy lands 0755; (ii) THIS repo — the skill's own review recipes exec
  `$(CURDIR)/scripts/render-review-prompt.py` directly, so the committed file must
  itself be `chmod +x` (0755) or the live Bucket B smoke fails even while generated
  targets are fine. Add the helper to `tests/test_selftest_overlap.py::_EXECUTABLE_SCRIPTS`
  (today just `extract-codex-session-id.py`) so the repo-level bit is guarded.
  The helper reads a prompt file and
  substitutes placeholders from a KNOWN-TOKEN REGISTRY (`{PLAN_FILE}`,
  `{ITERATION}`, `{KEY}`, `{COMMIT_REF}`, `{VERIFICATION_JSON}`), never
  `str.format` and never blind brace parsing — the prompt texts contain literal
  JSON-fence braces that must pass through untouched (the exact hazard
  `scripts/ab-replay.py:66` documents). Each token resolves from environment
  variable `NAME`, else from the content of the file named by environment variable
  `NAME_FILE` (how the recipes pass the verification JSON), else the helper fails
  loud (exit 2, naming the token) when the prompt file still contains a registry
  token after substitution. Unknown braces are inert data. Environment-variable
  passing avoids a second layer of shell quoting for values like paths.
- Recipes in `Makefile` + `shared/Makefile.review.tmpl` build `PROMPT` via command
  substitution from that helper, then pass `"$$PROMPT"` exactly as today. Command
  substitution output is not re-parsed as shell syntax, so backticks / `$(` / quotes
  in prompt files are inert data — the 2026-06-09 hazard class is structurally
  eliminated, not merely tested against.
- Token env vars must be visible INSIDE the substitution (Tier-2 codex P1): a
  same-line assignment (`PLAN_FILE=… PROMPT="$$(helper …)"`) does NOT export the
  vars into the command-substitution subshell, so the helper would see missing env
  and fail loud every run. The required shape prefixes the vars inside the
  substitution: `PROMPT="$$(PLAN_FILE="$(PLAN_FILE)" ITERATION="$(ITERATION)" …
  $(CURDIR)/scripts/render-review-prompt.py …)" || exit $$?`. The exact per-recipe
  var set is an implementation detail; the contract is "every registry token the
  prompt file needs is provided inside the substitution." A test asserts the
  recipe-built prompt actually receives the values (resolved, not literal `{TOKEN}`).
- Fail-loud propagation (Tier-2 codex P2, verified): make's default shell has no
  `-e`, and recipe commands are `;`-chained, so a bare `PROMPT="$$(helper …)";
  codex exec … "$$PROMPT"` would swallow the helper's exit-2 and invoke the CLI
  with an empty prompt — defeating the whole point of the fail-loud helper. Every
  helper invocation MUST guard the substitution: `PROMPT="$$(helper …)" || exit
  $$?` (or split the assignment onto its own `&&`-joined line). A regression test
  asserts each review recipe's helper call carries the guard (grep the rendered
  recipe for `scripts/render-review-prompt.py` NOT followed by an un-guarded `;`).
- Retire the `tier1_prompt` macro. `shared/CONTRIBUTING.md.tmpl` (and the dogfood
  `CONTRIBUTING.md`) stop inlining the Tier-1 prompt text; they instead document
  BOTH manual-subagent variants exactly as today's two macro call sites do
  (iter-1 FN4): read `prompts/commit-review-plan-bound.txt` substituting
  `{COMMIT_REF}` + `{PLAN_FILE}`, or `prompts/commit-review-unbound.txt`
  substituting `{COMMIT_REF}` only. A test asserts both file paths are referenced
  by the rendered CONTRIBUTING (template and dogfood copies).
- `scripts/ab-replay.py` / `scripts/ab_replay_lib.py` drop their hand-mirrored
  prompt constant and its private `<<PLAN>>`/`<<ITER>>` scheme; they read
  `prompts/plan-review.txt` and substitute via the same known-token rules
  (iter-1 FN6). `tests/test_ab_replay_lib.py` retargets its prompt assertions to
  the shared file. ab-replay must SUPPLY every token the shared file carries
  (Tier-2 codex P2, verified: its current prompt has no `{KEY}`/JSON footer, but
  `plan-review.txt` does): ab-replay already receives the plan path and iteration,
  so it computes `{KEY}` the same way the Makefile does (sha256 of
  `realpath(repo):realpath(plan)`, first 12 hex) rather than needing a no-KEY
  prompt variant — one shared prompt, all consumers supply all tokens. The
  retargeted `tests/test_ab_replay_lib.py` covers the KEY-resolved path (no
  unresolved-token failure).
- Merge the dormant `/simplify` rule into Tier-1 (user request, 2026-07-05). The
  two Tier-1 commit-review prompt files gain one focus item — reuse / dead code /
  cruft accumulated across fold rounds — so the simplification lens runs every
  time Tier-1 runs, for BOTH AIs (the old rule at `CONTRIBUTING.md:136` /
  `shared/CONTRIBUTING.md.tmpl:211` was optional, Claude-Code-only, and has no
  evidence of firing in any shipped PR record — nothing records or enforces it). That sub-bullet shrinks to one line: simplification
  is part of Tier-1's focus; `/simplify` remains an optional interactive extra in
  Claude Code sessions. `tests/test_shared_templates.py`'s simplify-wording test
  retargets to assert the new one-liner plus the prompt-file focus item instead
  of the old gating words. `README.md`'s historical PR #5 description is
  untouched (history, not guidance).
- Test surgery in `tests/test_shared_templates.py`: the macro byte-identity test, the
  `None`-vs-empty-string macro test, and the no-backticks shell-safety test are
  replaced by: (a) each prompt file exists, is non-empty, and contains only
  placeholders the recipes provide; (b) each review target invokes
  `scripts/render-review-prompt.py` with its exact prompt file, AND none of the
  four lead phrases shared by the five prompt texts ("Review the plan file",
  "Review commit HEAD", "Read the plan file", "Interpret these fact-check
  results") remains inline in `Makefile` or `shared/Makefile.review.tmpl` — the
  narrow "no `Review …` text" form would miss a partial extraction that left the
  consistency/fact-check prompts inline (iter-2 FN2); (c) key-phrase
  assertions (calibration wording, cross-section instruction, JSON-fence contract)
  retarget from rendered recipe strings to the prompt files; (d) a fact-check
  data-flow test proving sample verification JSON demonstrably reaches the built
  prompt for BOTH the codex and claude fact-check recipes (iter-1 FN1 — the
  regression this whole placeholder design exists to prevent).
- `tests/test_makefile_review_targets.py` is TWO test classes, not one — retarget
  the prompt-shape half (Tier-2 codex P1, verified): the `REVIEW_RESOLVE=1`
  dispatcher-resolution tests are unaffected and keep their coverage, BUT
  `test_tier1_prompt_has_no_backticks_in_rendered_recipe` (greps the rendered
  recipe for `"Review commit`) and `test_plan_review_prompt_has_calibration_and_is_shell_safe`
  (greps for `"Review the plan file at`) assert on inline prompt text that Bucket B
  moves OUT of the recipe — they turn `make check` red as written. Rewrite both to
  validate the helper/prompt-file path: the shell-safety + calibration + no-backtick
  properties they check now live in the prompt FILES (assert against the files),
  and the recipe-side assertion becomes "the recipe invokes
  `scripts/render-review-prompt.py` with the right prompt file + guard" (shares the P2
  guard test above). A THIRD prompt-shape test also breaks and is NOT caught by a
  lead-phrase grep: `test_makefile_tier1_prompt_contains_key_phrases` slices the
  `review-commit-by-codex` recipe block and asserts prompt-BODY phrases
  (`tests that pass for the wrong reason`, `plan-impl drift`, `Tier-1`,
  `Do NOT edit files`) that move into the prompt file — retarget it to assert
  against `prompts/commit-review-*.txt` (Tier-2 codex P1).
- Grep-the-suite discipline, and its limit (Tier-2 meta — this class regenerated
  across two Tier-2 rounds, so make the DISCIPLINE load-bearing, not the list):
  the specific tests named in this bucket
  (`test_tier1_prompt_has_no_backticks_in_rendered_recipe`,
  `test_plan_review_prompt_has_calibration_and_is_shell_safe`,
  `test_makefile_tier1_prompt_contains_key_phrases`, the
  `SHARED_TEMPLATES_TO_SCAN` scans) are the ones KNOWN at plan time and are
  explicitly NOT claimed exhaustive. Before implementing, grep `tests/` for any
  inline fragment of the five prompt texts — lead phrases AND body phrases — and
  retarget every hit; `make check` green is the acceptance gate that guarantees
  completeness. The plan does not, and cannot by inspection, enumerate every
  affected test; that is implementation-discovery work the grep + `make check`
  covers by construction.
- Downstream migration: extend `scripts/migrate-selftest-block.py` to also copy the
  `prompts/` files and the new helper when it re-syncs the sentinel block (today it
  moves only the Makefile block; without this, a migrated downstream Makefile would
  reference prompt files it doesn't have). Dry-run default preserved. This
  extension gets the script its FIRST test coverage (none exists today — verified;
  iter-2 FN3): a tmp-fixture test drives dry-run (diff names the prompt files +
  helper) and `--apply` (files copied, helper landed 0755, sentinel block
  replaced), then proves the wired path end-to-end by running the migrated
  fixture's `make review` with the `REVIEW_RESOLVE=1` hook — target resolution
  without invoking a real CLI.

**Placement decision.** Top-level `prompts/` (not `scripts/` — they are data, not
executables; not `docs/` — they are load-bearing runtime inputs). Adopt-mode targets
receive them as ordinary rule-(a) WRITEs (new paths, no collisions expected), and the
planned-set count in adopt tests grows by the number of prompt files + 1 (helper) —
those fixtures are updated in the same PR, called out in each test's diff.

### Bucket C — split `bootstrap_lib/cli.py`

**Change (intent level).** Move, verbatim where possible, into three new modules:

| New module | Moves (today all in `bootstrap_lib/cli.py`) |
|---|---|
| `bootstrap_lib/adopt_ui.py` | `_AdoptionAbort`, `_ALWAYS_ACTIONS`, `_allowed_actions_for`, `_ACTION_HELP`, `_print_action_help`, `_show_decide_diff`, `_user_decision`, `_prompt_one_file`, `_interactive_decide` |
| `bootstrap_lib/apply_pipeline.py` | `_prepare_apply`, `_apply_writes`, `_apply_adoption_writes`, `_maybe_pause_after_first_write`, `_cli_layer_path_safety`, `_drop_planned_file`, `_main_apply_adopt` |
| `bootstrap_lib/guidance.py` | `_print_post_apply_guidance`, `_format_restore_hint`, `_MAKE_TARGET_RE`, `_makefile_target_names`, `_compute_colliding_targets`, `_REVIEW_MACHINERY_SENTINEL`, `_makefile_has_review_machinery` |

`cli.py` keeps: parser construction, `CLIError`, `_resolve_mode`, `_build_context`,
`_resolve_package_manager`, `_maybe_print_advisory`, `_print_dry_run`, `_print_diff`,
`_should_run_intake`, `main`. Target: `cli.py` under ~500 lines with `main()` reading
as a dispatch table.

**Import-cycle rule (iter-1 FN2).** `_main_apply_adopt` orchestrates the decide-phase
UI and the post-apply guidance, so `bootstrap_lib/apply_pipeline.py` MUST import
`bootstrap_lib/adopt_ui.py` and `bootstrap_lib/guidance.py`. The layered dependency
direction is:

- `cli` → `apply_pipeline`, `guidance`, `adopt_ui` (cli's v1 path calls guidance
  directly; the v1 failure paths use `_format_restore_hint`)
- `apply_pipeline` → `adopt_ui`, `guidance`, and the base layer
- `adopt_ui` and `guidance` are LEAF orchestration modules: they import only the
  base layer (`adopt`, `manifest`, `io`, `paths`, `render`, `detect`) and stdlib,
  never each other, never `apply_pipeline`, never `cli`
- nothing imports `cli`

The two lazy `bootstrap_lib.adopt` imports inside `_apply_adoption_writes` and
`_main_apply_adopt` guard against a `cli`↔`adopt` cycle that does not exist today
(`bootstrap_lib/adopt.py` imports nothing from the package); in
`bootstrap_lib/apply_pipeline.py` they become ordinary top-of-module imports.

**No compatibility re-exports.** Tests importing moved names
(`tests/test_interactive_decide.py`, `tests/test_bootstrap_cli.py`,
`tests/test_adopt_apply_e2e.py`, `tests/test_sigterm_mid_apply.py`,
`tests/test_restore.py`, others found by grep at impl time) are updated to the new
module paths in the same commit. One name, one home; the moved code keeps its
docstrings and comments byte-for-byte (Bucket E touches comments, not this bucket —
keeps each diff reviewable as pure movement).

### Bucket D — process-weight reduction (plans archive + backlog split)

- Create `docs/plans/archive/`; move all plan files whose implementation PR is merged
  (everything except any plan still awaiting implementation — at plan time, all 18
  pre-existing plans are completed or superseded; this plan file, the 19th in the
  directory, stays active). The `make status`
  plan auto-detect globs `docs/plans/*.md` non-recursively, so archived plans drop
  out of the candidate set with no Makefile change; verify by running `make status`
  after the move (expected: this plan is the single candidate, WARN gone).
- Repo-wide reference sweep (iter-1 FN5 — the surface is 12 files, not two): every
  repo-local `docs/plans/2026-*` reference updates to the `archive/` path —
  markdown links (`CLAUDE.md`, `BACKLOG.md`, `docs/usage.md`,
  `docs/design-notes/2026-06-01-continue-thread-ab-result.md` — 4), docstring/comment
  citations (`bootstrap_lib/adopt.py:3`, `tests/test_stack_suggest.py:15`,
  `scripts/ab_replay_lib.py:3` — 3), and the `DEFAULT_PLAN` constants
  (`scripts/ab-replay.py:58`, `scripts/verify-v13-5.py:78` — 2) = 9 touched; with
  the 3 deliberately-untouched files below that is the 12-file total.
  Two reference classes are deliberately UNTOUCHED: the generic example path in
  `CONTRIBUTING.md:220` / `shared/CONTRIBUTING.md.tmpl:271` (a placeholder
  illustration, not a real file) and the external GitHub URL at `README.md:27`
  (points at a different repository).
- The moved plans' own relative links are rewritten one directory deeper — ALL
  relative forms, not only `../`-style (Tier-2 codex P1, verified). Two sub-classes,
  both flagged by the general link test below:
  - `../`-form links (iter-2 FN1 — 4 plan files, e.g. a two-levels-up Makefile
    link in `docs/plans/2026-06-01-continue-thread-ab-measurement.md`, a
    parent-relative README link in `docs/plans/2026-05-15-skill-pr2-nodejs-language.md`):
    each needs one more `../` after the move.
  - bare-filename links that are ALREADY broken today (Tier-2 codex P1): e.g.
    `[Makefile](Makefile)` and `[CLAUDE.md](CLAUDE.md)` in
    `docs/plans/2026-05-27-skill-pr10-harvest-plan-tango-improvements.md:421,428`
    resolve to `docs/plans/Makefile` NOW (never existed) and
    `docs/plans/archive/Makefile` after the move; `[…](README.md)` in
    `docs/plans/2026-05-15-skill-pr2-nodejs-language.md:137` resolves correctly to
    `docs/plans/README.md` today but breaks on move. These must be normalized to
    repo-root-relative (a two-levels-up Makefile path, a one-level-up README path
    post-move) as part of the sweep — NOT exempted, or the test bakes existing rot
    into permanent exceptions.
    The general link test would fail `make check` on the bare-filename breaks the
    FIRST time it runs (before the move even matters), so the sweep must precede or
    accompany the test in the same commit.
- New link-existence test, GENERAL form (iter-2 FN1): for every tracked markdown
  file, each markdown-link-form reference to an in-repo path — not only
  `docs/plans/…` targets — must resolve to an existing file relative to the
  linking file's directory. The test MUST parse markdown structurally, skipping
  inline-code spans and fenced code blocks (Tier-2 codex P1): a backtick-wrapped
  `` `[Makefile](Makefile)` `` is a code span, NOT a live link, so it is exempt —
  this plan file itself shows such link-syntax examples inside backticks (the
  bare-filename cases above), and a naive `\[..\]\(..\)` regex would wrongly flag
  them. Only real (un-backticked, un-fenced) links are checked; external URLs and
  intra-page anchors are exempt by construction. Locks the whole link-rot class,
  including archived plans' own links, against this and future moves.
- `DEFAULT_PLAN` existence assertions added to `tests/test_ab_replay_lib.py` and
  `tests/test_verify_v13_5.py` (replaces the iter-0 draft's unusable `--help` smoke
  — iter-1 FN3 verified `scripts/verify-v13-5.py` has no `--help` path; it exits 4
  treating the flag as a plan path).
- Split `BACKLOG.md`: active/parked items stay; closed/superseded items move to
  `BACKLOG-archive.md` with their closure notes. `shared/BACKLOG.md.tmpl` is
  untouched (generated projects start with a fresh, small backlog). Check
  `tests/test_dogfood_doc_sanity.py` for any BACKLOG-shape assertions before moving.
- Add the archive convention (one paragraph: move on implementation-PR merge;
  `make status` only surfaces active plans) to BOTH `docs/plans/README.md` AND its
  shared template `shared/docs-plans-README.md.tmpl` — they are byte-locked by
  `tests/test_selftest_overlap.py::test_overlap_docs_plans_readme`, so editing only
  the dogfood copy turns `make check` red (Tier-2 codex P1). Add the
  review-loop-feature A/B gate note to `BACKLOG.md` (from NOT-in-scope table).
- Sync runbook (user request, 2026-07-05): a short "bringing an adopted project up
  to date" section in `docs/usage.md`, listing the per-project sync commands in
  order — `scripts/propagate-shared-rules.py` for the shared markdown sections
  (section-level replacement: the safe channel for MIXED-OWNERSHIP files like a
  downstream CLAUDE.md holding project details next to the shared rules; its only
  guard for owner edits INSIDE a managed section is the dry-run diff, so read it
  before `--apply`), `scripts/migrate-selftest-block.py` for the review block +
  prompt files + helper, and a plain adopt re-run for newly added planned files —
  each dry-run first. This documents the CURRENT story honestly; it is the right
  answer at 2-3 adopted projects, not at 10.
- New `BACKLOG.md` entry for the scaling answer: a `--mode=upgrade` engine keyed
  to an OWNERSHIP model, not whole files (user input, 2026-07-05: mixed-ownership
  files — a downstream CLAUDE.md holds project details AND the shared rules — can
  never hash-match as whole files, so per-file tracking would never auto-update
  them and whole-file replacement would destroy the owner's half). Three classes:
  (i) skill-owned whole files (scripts, prompts, CI workflow) — file-hash
  tracking, auto-update when untouched; (ii) MANAGED REGIONS inside mixed files
  (the shared `##` sections; the Makefile sentinel block) — region-hash tracking,
  auto-update only while the region still matches what the skill last wrote,
  per-region consent when the owner edited inside it (closing today's
  `propagate-shared-rules.py` gap, where in-section owner edits are overwritten
  with only the dry-run diff as guard); regions heading-matched at first,
  upgradeable to sentinel comments the first run inserts; (iii) owner files —
  never auto-touched. Durable record written at apply/adopt time. Explicit
  trigger to pick up: the 3rd real adopted project, OR the 2nd time one skill
  change requires touching every adopted project by hand — whichever comes first.
  Grounding fact: today's manifests are `mkstemp` temp files
  (`bootstrap_lib/manifest.py:102`) — rollback artifacts, not durable records —
  so the engine needs a durability design of its own. Out of scope here: this
  plan is behavior-preserving, and a lockfile written into targets is a feature.

### Bucket E — comment + naming hygiene

- **De-citation rule** applied over `bootstrap_lib/` and `scripts/`: where a comment
  is "tracker citation + constraint", keep the constraint, drop the citation ("closes
  Codex iter-22 P1", "Tier-2 codex round-4 P2", "iter-2 FN2"…). Where a comment is
  citation-only, delete it. Where the citation names the SOURCE of a contract that
  is otherwise invisible (e.g. "LESSONS.md 2026-06-09" pointing at a live rule),
  keep a plain-language pointer to the durable document (LESSONS/CONTRIBUTING),
  never to a review iteration number. No percent target (LESSONS.md 2026-05-25:
  enumerate pinned surfaces instead) — the pinned surfaces here are docstrings
  asserted by tests, found by grepping test assertions for quoted docstring
  fragments before editing; anything pinned stays.
- Rename `scripts/verify-v13-5.py` → `scripts/verify-codex-thread-continuation.py`
  (what it verifies, not the plan-internal ID it came from); update all references
  (`tests/test_verify_v13_5.py` module name included) found by repo-wide grep.
- `bootstrap_lib/render.py:211`: hoist the function-local `import tempfile` to the
  module's import block.

## Architecture decisions

- **AD1 — verbatim map over sync-copier.** One working copy per shipped verbatim
  file; `render.py` holds both maps as the complete shipped-file inventory. Rejected:
  a sync-copier make target (keeps two copies + a forgettable step); Jinja `include`
  tricks (still passes content through Jinja).
- **AD2 — env-substituted prompt files over sed/inline.** A known-token registry
  resolves each placeholder from environment variable `NAME` or file content at
  `NAME_FILE`, with fail-loud handling for a registry token left unresolved; all
  other braces are inert (prompts contain literal JSON-fence braces — `str.format`
  and blind brace parsing are structurally excluded, per the hazard
  `scripts/ab-replay.py:66` already documents). No value ever re-enters shell
  parsing. All consumers — Make recipes AND `scripts/ab-replay.py` — use the same
  files and rules. Rejected: `sed` substitution (delimiter collisions with
  arbitrary paths); keeping prompts inline (status quo hazard); per-actor prompt
  files (codex/claude share texts today — variants exist per REVIEW MODE, not per
  actor).
- **AD3 — top-level `prompts/`.** Data files, separated from executables
  (`scripts/`) and prose (`docs/`). Cost: one more top-level dir in generated
  projects and adopt targets; accepted for greppability and because the alternative
  (nesting under `scripts/`) misfiles data as code.
- **AD4 — no re-exports after the cli split.** Tests are the only consumers of the
  moved private names; updating imports once beats maintaining two names forever.
- **AD5 — archive by move, not delete.** Plans stay in-tree (institutional memory,
  README's stated purpose) and drop out of the non-recursive status glob naturally.
- **AD6 — movement and rewording never share a commit.** Bucket C commits are pure
  code movement; Bucket E commits are pure comment/name edits. Reviewers can verify
  "moved verbatim" and "reworded, no behavior" separately.
- **AD7 — simplification folds into Tier-1, not a separate pass.** The optional
  `/simplify` step has no evidence of ever firing in a shipped PR record — and by
  its own design nothing records or enforces it (no forcing function; one document
  deep — drivers work from CLAUDE.md's checklist, which never mentions it; and
  Claude-Code-only in a two-AI repo). This plan's own origin demonstrates the need
  it was meant to cover: cruft accumulates through fold rounds — exactly the
  commits Tier-1 already reviews. One reviewer pass with a simplification focus
  item beats a second pass that recorded history never shows happening. Rejected:
  mandatory standalone pass with a logged outcome (adds a step to every
  substantive PR and stays single-AI); deleting the concept outright (the need is
  demonstrated — this plan exists because cruft accumulated).

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Bucket B breaks a review recipe in a way only a live CLI run reveals (LESSONS.md 2026-05-30: shim tests prove branching, not real-CLI acceptance) | `make preflight-review-tooling` after wiring, plus one real `make review-plan-fact-check-by-codex` smoke against this very plan file before the Bucket B PR is marked ready |
| Prompt-file placeholder drift (a recipe stops exporting a var the file needs) | Helper fails loud on an unresolved registry token; a test enumerates each prompt file's tokens against the recipe-provided set; the fact-check data-flow test proves the `{VERIFICATION_JSON}` file-backed token end-to-end |
| Adopt-mode planned-set counts pinned in tests silently absorb the new `prompts/` files | Bucket B's PR updates those fixtures explicitly; reviewer instructed to check each count delta equals (prompt files + 1 helper) |
| cli split churns `git blame` on the hottest file | Accepted cost; AD6's pure-movement commits keep `git log --follow` usable |
| Archived-plan paths break in-tree references (12 files at plan time, not just the two script constants) — AND the moved plans' own relative links break: `../`-form (4 files) one level deeper, PLUS bare-filename links already broken today (Tier-2 codex P1) | Bucket D sweeps every repo-local `docs/plans/` reference and rewrites ALL relative-link forms (incl. normalizing the pre-existing bare-filename breaks) in the same commit; the general link-existence test + `DEFAULT_PLAN` existence assertions lock both classes permanently |
| Plan under-enumerates which tests break when a bucket deletes/changes a string (three surfaced at Tier-2: scan list, Makefile prompt-shape tests, bare links) | Buckets A + B carry an explicit grep-the-suite step (every deleted template basename, every inline prompt lead-phrase) so the implementer retargets ALL consumers, not only the ones named at plan time; `make check` is the backstop |
| De-citation deletes a comment a test pins (docstring assertions) | Pre-edit grep of test assertions for docstring fragments (LESSONS.md 2026-05-25 discipline); `make check` gates |
| Downstream repos (e.g. call-details) re-sync the Makefile block but lack `prompts/` | `scripts/migrate-selftest-block.py` extended in the same PR to carry the prompt files + helper; its dry-run diff shows the new files; the new fixture test (the script's first coverage) gates dry-run, `--apply`, helper exec-bit, and migrated-target resolution |

## Verification

- Every bucket: `make check` green (full suite; no skips beyond the pre-existing
  environment-gated ones).
- Bucket A: byte-equality property test (rendered output == `scripts/` source);
  the retargeted `SHARED_TEMPLATES_TO_SCAN` tests green (no `TemplateNotFound`);
  generated-project smoke tests still execute the shipped scripts (exec bit).
- Bucket B: `make preflight-review-tooling`; one live fact-check run against this
  plan; the `REVIEW_RESOLVE=1` dispatcher tests in
  `tests/test_makefile_review_targets.py` unchanged AND its two prompt-shape tests
  retargeted to the prompt files (green, not red); the fail-loud-guard test (every
  recipe's `scripts/render-review-prompt.py` call carries `|| exit $$?`); placeholder
  enumeration test; the retargeted simplify-wording test green;
  `tests/test_selftest_overlap.py` byte-identity between repo `Makefile` block and
  rendered `shared/Makefile.review.tmpl` unchanged in mechanism.
- Bucket C: suite green with imports updated; `rg -n 'from bootstrap_lib.cli import'`
  shows only names that still live there; module line counts reported in the PR body.
- Bucket D: `make status` run manually → single active plan, no WARN; the new
  link-existence test green; `DEFAULT_PLAN` existence assertions green in
  `tests/test_ab_replay_lib.py` + `tests/test_verify_v13_5.py` (no `--help` smoke —
  iter-1 FN3).
- Bucket E: `make check` (ruff RUF002/RUF003 ASCII rule per LESSONS.md 2026-06-01);
  diff reviewed as comment-only (no AST change — spot-checked with `python -m compileall`
  or equivalent at impl).

## Implementation rollout

One implementation PR per bucket, in order **A → B → C → D → E**; each independently
shippable and revertable. B depends on A (verbatim mechanism). C/D/E are independent
of A/B and each other. The front-end-language plan should not start before A–C are
merged (C is its direct prerequisite; A/B remove the surfaces it would otherwise have
to duplicate into).

## Iteration log (this plan)

| Iter | Reviewer | Date | Findings (3/2/1) | Verdict |
|------|----------|------|------------------|---------|
| 0.5 | Fact-check (deterministic + Codex interpretation) | 2026-07-05 | n/a (41 ✓ / 14 benign / 1 n.v.) | **clean** — 41/41 load-bearing facts verified; all 14 `failed` are benign: 12 are files this plan PROPOSES to create (6 prompt-file tokens — the five bare filenames plus one `prompts/`-prefixed path — the three Bucket C modules, `BACKLOG-archive.md`, the renamed verifier, the substitution helper; the checker cannot distinguish proposed from existing), plus 2 prose-token noise items reworded after the run (a bare `.tmpl`, a bare `apply_pipeline.py`). 1 `not_verifiable` is the known cli-flag-token class (`--help`). |
| 1 | Codex | 2026-07-05 | 3/3/0 | needs-iter (verdict "do-not-implement") → **all 6 folded (a)**. Premises verified empirically before folding: ran `verify-v13-5.py --help` (exit 4 — FN3 confirmed), read `ab-replay.py:66-69` (FN6 confirmed, surfaces the literal-brace/`str.format` constraint now in AD2), enumerated the FN5 reference surface (12 files, larger than the 4 the reviewer cited). See Evidence table. 0 imp-3 remain after folds. |
| 1.5 | Claude self-check (1 pass) | 2026-07-05 | 0 imp-3 (3 doc-drifts, all fixed) | (i) plan-count ambiguity fixed — 18 pre-existing plans + this file = 19 in-dir; Context and Bucket D now both say so; (ii) iter-0.5 row's proposed-file enumeration made explicit (6 prompt-file tokens + 3 modules + 3 singles = 12; the checker's "11" was a miscount the glossed wording invited); (iii) exec-bit mechanism unified (`default_mode_for` reading `EXECUTABLE_TARGETS` — one mechanism, previously described from two angles). Between 1.5 and 2, one user scope addition folded: the dormant `/simplify` rule merges into the Tier-1 prompt focus (Bucket B bullet + AD7). **Pass 2** (post-folds, pre-iter-2, required for `loop-ack`): 1 sequencing nit — the `/simplify` fold inserted AD7 before AD6; reordered, numbering preserved. 9 explicit cross-checks clean (plan counts, prompt arithmetic, token registry, split-table disjointness, verbatim-six, sweep surface, D-before-E naming, log↔evidence mapping). Cap reached (2 passes). |
| 2 | Codex | 2026-07-05 | 0/3/1 | **converged** — 0 imp-3; all 4 findings folded (a). FN1 (imp-2, archived plans' own `../`-form relative links break — premise verified, 4 plan files): sweep rewrites them + link test generalized to ALL in-repo markdown links. FN2 (imp-2): the inline-prompt assertion would have missed the consistency/fact-check texts — test now pins helper invocation per target + all four lead phrases gone. FN3 (imp-2): migration extension gains an acceptance fixture — the script's FIRST test coverage (verified: none exists). FN4 (imp-1): "never fired" softened to "no evidence in shipped PR records" — decision unchanged. Second user scope addition folded after iter 2: adopted-project sync runbook (`docs/usage.md`) + `--mode=upgrade` BACKLOG entry with concrete trigger (Bucket D). **Stop: 0 imp-3, all imp-2/1 folded — README stop rule; no ritual iter 3.** |
| 2.5 | Claude self-check (1 pass) | 2026-07-05 | 0 imp-3 (0 contradictions, 1 soft ambiguity) | **Internally consistent** — 9 cross-checks reconcile (plan counts, log↔evidence arithmetic, token registry, verbatim-six, sweep surface, exec-bit mechanism, split graph, D-before-E naming, 12-proposed-files arithmetic). Soft ambiguity tidied: Bucket B's opener scoped "nine" to the Makefile with the template + ab-replay copies named separately. After the pass, folded together: third user scope input (mixed-ownership files → `--mode=upgrade` BACKLOG entry rewritten to the region-based ownership model; runbook names the section-safe channel + its dry-run-diff caveat) and one fact-check prose-noise reword (the quoted parent-relative README-link example). Stopped at 1 pass. |
| T2 | Codex Tier-2 (PR #49, ready-for-review) | 2026-07-06 | 3 P1 / 1 P2 | **all 4 folded (a)** — premises verified against cited files before folding (all correct). All four are one meta-class: the plan's test-surgery enumeration was incomplete, so `make check` would go red for an implementer following it verbatim. P1a: archive sweep must cover bare-filename links (already broken today) + all `../`-forms, not just `../`. P1b: `test_makefile_review_targets.py` prompt-shape tests grep inline prompt text Bucket B removes — retarget them (dispatcher tests unaffected). P1c: six `scripts-*.tmpl` in `SHARED_TEMPLATES_TO_SCAN` → `TemplateNotFound` after Bucket A deletes them — drop the entries. P2: `;`-chained recipes swallow the fail-loud helper's exit-2 → guard every `PROMPT="$$(…)"` with `|| exit $$?`. Added grep-the-suite discipline to Buckets A/B so a THIRD under-enumeration can't surface at impl. claude[bot] Tier-2 errored twice (infra) — no cross-check landed; re-trigger optional. |
| T2b | Codex Tier-2 (PR #49, on fold commit `010aa8d`) | 2026-07-06 | 4 P1 / 3 P2 | **all 7 folded (a)** — premises verified (all correct). Two sub-classes. GENUINE design/feasibility gaps in the T2 folds: P1 map-source (Bucket A restricted verbatim sources to `scripts/` but Bucket B ships `prompts/` through it → generalize to arbitrary repo-relative); P1 env-var visibility (same-line `VAR=… PROMPT="$$(…)"` doesn't reach the subshell → prefix inside the substitution); P1 self-broken-links (my own backticked `[Makefile](Makefile)` examples → require the link test to skip inline-code spans, exempting them by construction); P2 helper repo-exec-bit (`EXECUTABLE_TARGETS` covers generated projects only; the skill's own recipes exec it → also commit +x + `_EXECUTABLE_SCRIPTS`); P2 ab-replay `{KEY}` (its prompt lacks the JSON footer `plan-review.txt` carries → ab-replay computes KEY from its plan path, one shared prompt). TEST-ENUMERATION class (3rd instance — README-mirror test, `test_makefile_tier1_prompt_contains_key_phrases`): folded the named tests BUT reframed the discipline as load-bearing — the plan explicitly does NOT claim an exhaustive test list; grep-the-suite + `make check` green is the completeness gate (execution-based verification per the same-class-regeneration rule). **Stop rule invoked: no more folding of individual missed-test names — the discipline covers them structurally.** |
| T2.5 | Claude self-check (after T2 fold) | 2026-07-06 | 0 imp-3 (2 doc-drifts) | Both fixed: (i) "12 files" sweep count vs an 8-item enumeration — `scripts/ab_replay_lib.py` was the omitted 12th (now 9 touched + 3 untouched); (ii) evidence FN2 import-arrow shorthand implied cli→guidance only via apply_pipeline — corrected to direct edges. |
| T2b.5 | Claude self-check (after T2b fold) | 2026-07-06 | 0 imp-3 (2 doc-drifts) | Both fixed: (i) T2b log header "4 P1 / 3 P2" vs evidence table showing 5 P1 — verified against Codex's actual badges (map-source was P2, not P1, so the header was right and one evidence row was mislabeled — checker's suggested reconciliation was wrong, per the 2026-05-17 verify-the-fix lesson); (ii) the T2.5/T2b.5 consistency passes had evidence rows but no iteration-log parent — added both, relabeled the prior `3.5` rows to `T2.5`. Converged: 0 imp-3, plan internally consistent. |

## Evidence table — what was folded and where

| Iter | Finding | Decision | Where folded |
|------|---------|----------|--------------|
| 1 | FN1 (imp-3): fact-check prompt extraction loses the in-recipe `$$(cat …)` verification-JSON expansion | (a) fold | Bucket B prompt-file bullet (`{VERIFICATION_JSON}` placeholder), helper bullet (file-backed token via `NAME_FILE`), AD2, test-surgery item (d) data-flow test, risk table placeholder row |
| 1 | FN2 (imp-3): flat module graph can't support the moves — `_main_apply_adopt` calls adopt-UI + guidance helpers | (a) fold | Bucket C "Import-cycle rule" rewritten as a layered graph (`cli → {apply_pipeline, guidance, adopt_ui}` direct edges; `apply_pipeline → {adopt_ui, guidance}`; `adopt_ui`/`guidance` are leaves importing only the base layer) |
| 1 | FN3 (imp-3): Bucket D verification named a `--help` smoke the current verifier doesn't implement (exit 4, verified) and a rename that happens in Bucket E | (a) fold | Bucket D bullets + Verification: replaced with `DEFAULT_PLAN` existence assertions + link-existence test; rename stays pure Bucket E scope (no argparse addition — keeps AD6's pure-rename framing) |
| 1 | FN4 (imp-2): CONTRIBUTING migration dropped the plan-bound Tier-1 subagent variant | (a) fold | Bucket B CONTRIBUTING bullet: both variants documented with their substitution sets + discoverability test |
| 1 | FN5 (imp-2): archive move breaks more in-tree links than the two script constants | (a) fold | Bucket D repo-wide sweep bullet (12-file surface, two deliberately-untouched classes named), link-existence test, Scope row 4, risk table archive row |
| 1 | FN6 (imp-2): `scripts/ab-replay.py` remains a third hand-maintained prompt copy | (a) fold | Context copy inventory, Scope row 2, Bucket B ab-replay bullet, AD2 (single ruleset for all consumers), Critical files |
| 1.5 | consistency (i): plan-count 18-vs-19 ambiguity between Context and Bucket D | (a) fold | Context item 4, Bucket D first bullet |
| 1.5 | consistency (ii): iter-0.5 row enumeration read as 11 vs stated 12 | (a) fold — wording clarified; the 12 was correct | Iteration log row 0.5 |
| 1.5 | consistency (iii): exec-bit mechanism named two ways across Buckets A/B | (a) fold | Bucket A executable-bit bullet |
| — | user request (2026-07-05): dormant `/simplify` rule — rephrase or retire | (a) fold — merged into Tier-1 prompt focus list; alternatives documented | Scope row 2, Bucket B `/simplify` bullet, AD7, Bucket B verification |
| 1.5-p2 | consistency pass 2: AD list ordered AD7 before AD6 (fold-insertion artifact) | (a) fold — physically reordered; AD7 keeps its number (evidence rows reference it) | Architecture decisions section |
| 2 | FN1 (imp-2): archive move breaks the moved plans' own relative links | (a) fold — verified, 4 plan files carry `../` links | Bucket D relative-link bullet + generalized link test, Scope row 4, archive risk row |
| 2 | FN2 (imp-2): "no inline `Review …` text" assertion misses the consistency/fact-check lead phrases | (a) fold | Bucket B test surgery (b) |
| 2 | FN3 (imp-2): migration extension had no acceptance test (script has zero coverage today) | (a) fold — fixture test specified incl. exec-bit + `REVIEW_RESOLVE=1` end-to-end | Bucket B migration bullet, downstream risk row |
| 2 | FN4 (imp-1): "/simplify never fired" claim exceeds recorded evidence | (a) fold — softened to "no evidence in shipped PR records"; decision unchanged | Scope row 2, Bucket B `/simplify` bullet, AD7 |
| — | user request (2026-07-05): pipeline-change propagation to N adopted projects | (a) fold — runbook documented now; `--mode=upgrade` engine parked with explicit trigger | Bucket D runbook + BACKLOG-entry bullets, NOT-in-scope row, Scope row 4 |
| — | user request (2026-07-05): mixed-ownership files (project details + shared rules in one CLAUDE.md) defeat per-file upgrade hashing | (a) fold — BACKLOG entry rewritten to the three-class region-based ownership model; runbook marks the section-safe channel + its in-section-edit caveat | Bucket D BACKLOG-entry bullet, runbook bullet |
| T2 | codex P1a: archive/link test would fail `make check` on bare-filename links (already broken today) not covered by the `../`-only rewrite | (a) fold — verified `2026-05-27...:421,428` + `2026-05-15-pr2...:137` | Bucket D relative-link bullet (both sub-classes), archive risk row |
| T2 | codex P1b: `test_makefile_review_targets.py` prompt-shape tests grep inline prompt text Bucket B removes → red `make check` | (a) fold — verified the two tests + their needles | Bucket B new test-surgery bullet (two-class split), Bucket B verification implied |
| T2 | codex P1c: six `scripts-*.tmpl` in `SHARED_TEMPLATES_TO_SCAN` → `TemplateNotFound` after Bucket A deletes them | (a) fold — verified list membership + the two parametrized tests | Bucket A scan-retarget bullet + grep-the-suite bullet |
| T2 | codex P2: `;`-chained recipe swallows the helper's fail-loud exit-2, invoking the CLI with an empty prompt | (a) fold — verified make's default non-`-e` shell + recipe style | Bucket B fail-loud-propagation bullet (`|| exit $$?` guard + test) |
| T2 | meta (Tier-2 pattern): plan's test-surgery enumeration is necessary but not verified-exhaustive | (a) fold — grep-the-suite discipline added | Buckets A + B grep bullets, new risk row |
| T2b | codex P2: `SHARED_VERBATIM_MAP` restricted to `scripts/` sources, but Bucket B ships `prompts/` through it | (a) fold — map accepts arbitrary repo-relative sources | Bucket A source bullet |
| T2b | codex P1: same-line env-var assignment not visible inside `PROMPT="$$(…)"` substitution → helper fails loud every run | (a) fold — prefix vars inside the substitution; test the resolved prompt | Bucket B recipe-env bullet |
| T2b | codex P1: the plan's own backticked `[Makefile](Makefile)` examples would fail the general link test | (a) fold — link test must skip inline-code spans + fenced blocks | Bucket D link-test bullet |
| T2b | codex P1: `test_makefile_tier1_prompt_contains_key_phrases` asserts prompt-body phrases a lead-phrase grep misses | (a) fold — named + discipline reframed as non-exhaustive, `make check` is the gate | Bucket B key-phrases + grep-limit bullets |
| T2b | codex P2: helper needs repo-level +x (skill's own recipes exec it), not just generated-project `EXECUTABLE_TARGETS` | (a) fold — commit +x + add to `_EXECUTABLE_SCRIPTS` | Bucket B helper bullet |
| T2b | codex P2: ab-replay reading shared `plan-review.txt` hits unresolved `{KEY}` (its prompt lacks the JSON footer) | (a) fold — ab-replay computes KEY from its plan path; one shared prompt | Bucket B ab-replay bullet |
| T2b | codex P1: README archive-convention edit must touch `shared/docs-plans-README.md.tmpl` too (byte-locked mirror) | (a) fold — both copies named | Bucket D archive-convention bullet |
| T2.5 | consistency (after T2 fold): "12 files" sweep count vs enumeration (8 named) | (a) fold — `scripts/ab_replay_lib.py` was the omitted 12th; enumeration now sums to 9 touched + 3 untouched | Bucket D sweep bullet |
| T2.5 | consistency (after T2 fold): evidence FN2 arrow implied cli reaches guidance only via apply_pipeline | (a) fold — arrow shows direct cli edges | Evidence table FN2 row |
| T2b.5 | consistency (after T2b fold): T2b log header "4 P1 / 3 P2" vs evidence table (map-source row mislabeled P1) | (a) fold — map-source is P2 per Codex's badge; header was right, one evidence row wrong (verified against Codex labels, not the checker's guessed fix) | Evidence table T2b map-source row |
| T2b.5 | consistency (after T2b fold): T2.5/T2b.5 consistency passes had evidence rows but no iteration-log parent | (a) fold — added both rows to the iteration log; relabeled `3.5`→`T2.5` to avoid implying a phantom integer iter 3 | Iteration log |

## Implementation log (this PR)

Bucket A (branch `refactor/bucket-a-verbatim-ship`):

| Commit | Change | Tier-1 | Notes |
|---|---|---|---|
| `cd50117` | `SHARED_VERBATIM_MAP` in `bootstrap_lib/render.py` (arbitrary repo-relative sources, `read_bytes`, same `_emit_in_mode` filter as shared templates); six `scripts/*` entries out of `SHARED_TEMPLATE_MAP`; six `shared/scripts-*.tmpl` deleted; hand-synced byte-identity params replaced by structural verbatim properties (map disjointness, source exists+non-empty, rendered output == source); six entries dropped from `SHARED_TEMPLATES_TO_SCAN`; fact-check fixture retargeted; `docs/usage.md` "Shipped-file inventory" section; BACKLOG shipping-mechanism wording | 0 imp-3 / 0 imp-2 / 3 imp-1 | `tests/fixtures/fact-check/meta-plan-snapshot.md` was a live breaker OUTSIDE the plan's known-breaker list — the grep-the-suite discipline caught it (corpus invariant: referenced files exist). `make check` 1023 passed / 4 skipped (net -5: -6 byte-identity params, -12 scan params, +13 new) |
| (this commit) | Tier-1 folds: F1 (a) — brace-sentinel fixture + `test_verbatim_entries_bypass_jinja` proves the ship path bypasses Jinja and exercises a non-`scripts/` source path (the Bucket B contract); F3 (a) — `planned_paths` docstring reflow. F2 (c) rejected — `BACKLOG.md` DONE-entry template ref is a past-tense historical record; Bucket D archives closed entries | — | New LESSONS.md entry: tautological-property-test class (expected value and code-under-test reading the same bytes) |
| (fold 2) | Tier-2 cross-AI review folds — local codex stand-in on gpt-5.6-sol (GitHub Codex connector down: OpenAI backend 5xx outage; claude[bot] blocked pending PR #51's model-pin fix). 0 imp-3 / 3 imp-2, verdict needs-another-iteration; all 3 folded (a). FN1: verbatim sources now pass `validate_target_path` before reading (absolute / `..` / symlink escape rejected — codex empirically shipped `/etc/hosts` through the unguarded join) + 2 negative tests in `tests/test_render.py`. FN2: verbatim-source genericity scan restored (`test_no_boxette_isms_in_verbatim_sources`, parametrized over the map so Bucket B prompts inherit it) — the plan's "byte-equality is the replacement coverage" under-enumerated the retired scan's properties; deliberate beyond-plan strengthen. FN3: inventory claims precisified in `docs/usage.md` + `render.py` comment (adopt's post-`render_all` standalone `Makefile.review` injection, `.new` companions, `--dry-run` scope) | — | New LESSONS.md entry: replacement-coverage property enumeration |

## Lessons surfaced (this PR)

(none yet)

## Critical files to read before each iter's review

- `bootstrap_lib/render.py` (template maps, `planned_paths`, `render_makefile_review`)
- `bootstrap_lib/cli.py` (the split target — full file)
- `Makefile` + `shared/Makefile.review.tmpl` (prompt embeddings, sentinel block)
- `tests/test_selftest_overlap.py` (byte-identity pairs + sentinel-block test)
- `tests/test_shared_templates.py` (macro/prompt shape tests + `SHARED_TEMPLATES_TO_SCAN` — both retargeted)
- `tests/test_makefile_review_targets.py` (dispatcher tests unchanged; prompt-shape tests retargeted — Tier-2 P1b)
- `scripts/migrate-selftest-block.py` (downstream migration path)
- `scripts/ab-replay.py` + `scripts/ab_replay_lib.py` (third prompt copy being retired; the literal-brace constraint)
- `docs/plans/README.md` (archive convention lands there)
