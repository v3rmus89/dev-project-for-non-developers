# Backlog — parked decisions and future work

Items here are explicit "we will do this someday" decisions, recorded so they
don't get lost between sessions. Each item lists **why it's parked**, **what
triggers picking it up**, and **rough effort**.

Newer items at the top.

---

## Code-review follow-ups from PR #1

### `write_manifest` not atomic (imp-2)

**Status**: parked.

**Why parked**: `bootstrap_lib/manifest.py:119` writes the manifest directly
to its final path with `fsync`, but does NOT use a tmp-then-rename pattern.
If the process is killed mid-write of the manifest itself (before any
target-file writes), a partially-written JSON manifest can be left in
`$TMPDIR`. Since the manifest is written BEFORE any target write, an
interrupted manifest write means there's nothing to restore — worst case
is `--restore` fails with `JSONDecodeError` on a manifest that wouldn't
have done anything anyway. Benign failure mode, inconsistent with the
atomic-write discipline elsewhere.

**Triggers to pick up**:
- First user reports a `JSONDecodeError` from `--restore`.
- Anyone reviewing the safety contract notices the asymmetry.

**Rough effort**: ~10 min. Route the manifest write through
`bootstrap_lib.io.atomic_write` (or duplicate the pattern locally).

---

### `--restore` + non-`none` `--github-review` silently ignored (imp-2)

**Status**: parked.

**Why parked**: `bootstrap_lib/cli.py:34-64`'s `_resolve_mode` rejection
list for restore mode covers `--language`, `--out`, `--apply`, etc., but
the comment at line 57-58 acknowledges `--github-review` non-default values
can't be detected with argparse's `default="none"`. Result:
`bootstrap.py --restore m.json --github-review both-docs` silently ignores
the flag rather than rejecting it. Cosmetic UX hole, no safety impact —
the flag has no effect in restore mode either way.

**Triggers to pick up**: user gets confused that `--github-review` doesn't
error in restore mode.

**Rough effort**: ~10 min. Change argparse `default` to `None` and treat
`None` as `"none"` in `_build_context`; then the rejection-list check can
also catch non-None `args.github_review` in restore mode.

---

### `load_manifest` error path opaque (imp-1)

**Status**: parked.

**Why parked**: `bootstrap_lib/cli.py:209-212` calls `load_manifest` +
`restore_from_manifest` without wrapping them. A non-existent restore
path or malformed JSON raises `FileNotFoundError` / `json.JSONDecodeError`
and the user sees a Python traceback. The apply path catches errors at
line 251; restore should do the same.

**Triggers to pick up**: anyone reports a confusing traceback from
`--restore`.

**Rough effort**: ~5 min. Wrap in `try/except (OSError, JSONDecodeError,
KeyError)` and emit a one-line stderr message.

---

### `_apply` bare `except Exception` loses traceback (imp-1)

**Status**: parked.

**Why parked**: `bootstrap_lib/cli.py:249-253`'s catch reduces apply
failures to `f"apply failed: {e}"`. Path-safety errors and validation
errors are caught earlier, so this is a last-resort net — but it
disappears the stack trace for debugging mid-apply issues (e.g. an
`os.chmod` permission error or unexpected disk-full).

**Triggers to pick up**: first opaque mid-apply failure where debug
requires the actual stack.

**Rough effort**: ~5 min. Gate the traceback on
`DEV_PROJECT_SETUP_TRACEBACK=1` env var (or always print, since this
path is rare).

---

## Skill follow-ups

### Direct `--install-hooks` flag with target-venv creation

**Status**: parked (removed from PR #1's CLI in iter-16).

**Why parked**: running `pre-commit install` from the skill repo's
interpreter would tie target-project hooks to the skill repo's venv, so
hooks break if the skill repo moves or is rebuilt. The clean fix (create
the target venv first, install pre-commit there, then run `pre-commit
install` via the target's interpreter) is bigger than PR #1 can absorb.

For now, hook adoption is the generated project's `make install-hooks`
target — see `docs/usage.md`'s "Post-bootstrap hook adoption" section.

**Triggers to pick up**:
- User requests a one-step bootstrap-with-hooks for a common workflow.
- Frequent forgotten-`make install-hooks` after bootstrap in real adoption.

**Rough effort**: ~half a day. Needs to (1) create target venv during
bootstrap when `--install-hooks` is passed, (2) install pre-commit into
THAT venv, (3) invoke pre-commit via the target venv's Python, (4)
record hooks as restorable in the manifest (or document them as out of
manifest scope).

---

### Retroactively add triage rule + two-tier review docs + observability layer to Boxette

**Status**: now actionable as a follow-up side-task (post-PR-#5).

**Why parked**: the "Don't fold by default — triage" rule was developed
during this skill's plan-review loop. PR #4 added the four-questions
extension + Two-tier code review section. PR #5 added `make status` for
cross-session recovery + `LESSONS.md` self-improvement loop + plan-file
Implementation log convention. Boxette (the source repo this skill
extracts patterns from) doesn't have any of these yet. PR #4 + #5 ship
the relevant `shared/CLAUDE.md.tmpl` / `shared/AGENTS.md.tmpl` /
`shared/CONTRIBUTING.md.tmpl` / `shared/docs-plans-README.md.tmpl` /
`shared/Makefile.review.tmpl` / `shared/LESSONS.md.tmpl` sections;
Boxette can adopt by copying.

**Triggers to pick up**: anyone working on Boxette's plan-review workflow,
OR the next substantive Boxette plan-review starts.

**Rough effort**: ~2 hours — copy (1) the triage block with four-questions
extension, (2) the Two-tier code review section, (3) `make status` target,
(4) `LESSONS.md` scaffold, (5) cross-session-recovery + self-improvement-loop
instructions in CLAUDE.md + AGENTS.md, (6) plan-file structural convention
in docs/plans/README.md.

---

### Console-script packaging for the skill (`pip install -e .` + entry_points)

**Status**: parked.

**Why parked**: PR #1 ships only the
`./venv/bin/python bootstrap.py` invocation path to keep the deployment
surface minimal. A console-script entry point would let users run
`dev-project-setup --apply ...` after `pip install -e .` on the skill
repo, but adds packaging surface area.

**Triggers to pick up**: first user who installs the skill via `pip` and
asks why there's no shell entry-point.

**Rough effort**: ~1 hour. Add `[project.scripts]` to `pyproject.toml`,
verify `pip install -e .` works in a fresh venv, document in `docs/usage.md`.

---

### ✅ Add Node-TS language support (`languages/nodejs/`) — DONE in PR #2

**Status**: shipped 2026-05-15 via PR #2 (Plan PR #3 + the implementation PR).

**What landed**: Biome + vitest + TypeScript + Husky v9 + lint-staged, framework-agnostic Node-TS (no React/Vue/Svelte; those parked separately — see entry below).

**Loop convergence**: Codex 4 iters + Claude 1 iter; zero importance-3 findings at convergence; documented trade-offs and autonomous decisions in [`docs/plans/2026-05-15-skill-pr2-nodejs-language.md`](docs/plans/2026-05-15-skill-pr2-nodejs-language.md).

---

### Add frontend variants to nodejs language template

**Status**: parked.

**Why parked**: PR #2 ships framework-agnostic Node-TS (Biome + vitest + TypeScript). A true browser frontend needs additional opinionated picks: a bundler (Vite is the obvious default), a framework (React / Vue / Svelte / SvelteKit / Next.js), DOM-testing setup (jsdom or happy-dom for vitest), a dev server config. PR #2 keeps nodejs framework-agnostic so the skill stays small.

**Triggers to pick up**:
- Sandeep starts his first frontend project (most likely trigger).
- A second contributor needs a frontend variant.

**Rough effort**: ~half a day per variant. Simplest adoption path: "scaffold with `npm create vite@latest my-app -- --template react-ts` FIRST, then apply the skill on top to add Makefile / Husky / CI / plan-review-loop". The skill's nodejs scaffold composes additively. If we want a one-shot bootstrap: add `--frontend=react-vite|sveltekit|none` to `bootstrap.py` invoking the appropriate `npm create` underneath, then layering the universal scaffolds on top.

**Rough order of preference**: React+Vite first (most demand), SvelteKit second (Sandeep's stated curiosity), Vue third only if requested.

---

### ✅ Add Go language support (`languages/go/`) — DONE in PR #3

**Status**: shipped 2026-05-16 via PR #3 (Plan PR + implementation PR).

**What landed**: gofumpt + golangci-lint v2 + native git hooks via `core.hooksPath` (no pre-commit framework, no Husky — fully Native Go). Tools install project-local via `GOBIN="$(CURDIR)/bin"`. Module path auto-derived: `github.com/{owner}/{repo}` when `--github-*` set, else bare `{project_name}`. Pinned `gofumpt v0.9.2` + `golangci-lint v2.12.2`.

**Loop convergence**: Codex 5 iterations (trajectory 3→4→1→1→0 imp-3); stopping rule met at iter-5. See [`docs/plans/2026-05-15-skill-pr3-go-language.md`](docs/plans/2026-05-15-skill-pr3-go-language.md).

---

### Go project layout option (cmd/<name>/ vs root-level main.go)

**Status**: parked.

**Why parked**: PR #3 ships top-level `main.go` + `main_test.go` (Go's idiomatic single-binary layout). Multi-binary projects use `cmd/<name>/main.go`; library projects use no `main.go` at all. A future option flag (`--go-layout=root|cmd|library`) could let the user pick at bootstrap time.

**Triggers to pick up**: first user needs a multi-binary Go scaffold, or a Go library template.

**Rough effort**: ~half a day.

---

### Bump pinned Go tool versions (gofumpt, golangci-lint)

**Status**: parked.

**Why parked**: PR #3 pinned `GOFUMPT_VERSION ?= v0.9.2` and `GOLANGCI_LINT_VERSION ?= v2.12.2` (verified upstream as of 2026-05). The Go ecosystem moves quickly; rather than chase the latest at every plan iteration, PR #3 freezes the verified pin.

**Triggers to pick up**:
- ~6 months elapsed since the last pin.
- A user reports gofumpt v0.9.2 doesn't handle a Go 1.26+ syntax feature.
- golangci-lint upstream deprecates v2.12.x.

**Rough effort**: ~15 min. Update the two Makefile vars in `languages/go/Makefile.tmpl`, re-run smoke walk.

---

### Switch generated CI to `actions/cache` for Go tool binaries

**Status**: parked.

**Why parked**: PR #3 ships `setup-go@v5` with `cache: false` (because stdlib-only smoke project has no `go.sum`, and `setup-go`'s cache keys on `go.sum`). Tool binaries (gofumpt, golangci-lint) get re-installed on every CI run via `make install` — fast enough for current scope (~10-15s).

**Triggers to pick up**: first project where CI time on tool installs becomes a real concern.

**Rough effort**: ~half a day. Explicit `actions/cache@v4` step in `ci.yml.tmpl` keyed on Makefile vars, restore `./bin/` from cache.

---

### Broader `make selftest-bootstrap` coverage

**Status**: parked.

**Why parked**: `tests/test_selftest_overlap.py` covers 5 deterministic
overlap checks. Broader coverage (the full skill-repo `Makefile`,
`pyproject.toml`, `requirements-dev.txt`, the overlay docs) needs
context-dependent diffing that's larger than PR #1 can absorb.

**Triggers to pick up**: first drift incident between an overlay doc and
its template that the existing 5 checks miss.

**Rough effort**: ~half a day.

---

### `docs/upgrading.md` and `docs/design-notes.md`

**Status**: parked.

**Why parked**: the merged plan's directory tree included these. PR #1
keeps scope tight to `docs/usage.md`.

**Triggers to pick up**: first significant breaking change in a future PR
that needs upgrade-path docs.

**Rough effort**: ~2 hours each.

---

### Investigate `codex exec --ephemeral` for plan reviews

**Status**: parked.

**Why parked**: `make review-plan-by-codex` invokes `codex exec` without
`--ephemeral`, so Codex persists session data to `~/.codex/`. For most
plan content (workflow / infrastructure / feature scoping) this isn't a
meaningful exposure. For plans containing PII, real user data, or secrets
it would be.

Adding `--ephemeral` isn't a one-line change — needs to confirm it
composes correctly with `--output-last-message` (the mechanic the
bidirectional loop depends on).

**Triggers to pick up**: first substantive plan whose content includes
sensitive material.

**Rough effort**: ~30 min (verify, document, edit Makefile).

---

### Investigate Codex doc-only-PR auto-review skip

**Status**: parked (carried over from Boxette's observation).

**Why parked**: Codex's GitHub auto-review may skip PRs whose diff is
entirely documentation. Boxette observed this on two consecutive
plan-only PRs (#7, #8). PR #1 of this skill is also doc-heavy.

**Triggers to pick up**: third consecutive plan-only PR gets skipped, OR
a code PR gets skipped.

**Rough effort**: ~30 min investigation.

---

### Per-file `--decisions` / skip / abort interactive flow

**Status**: parked.

**Why parked**: PR #1's collision policy is repo-wide
(`--overwrite-existing` is all-or-nothing consent). The merged plan's
original "asks per-file" wording is implementable but needs a
`--decisions` JSON file or an interactive prompt — both add UX surface
area beyond PR #1's scope.

**Triggers to pick up**: first user with a partial-overlay case (some
files theirs, some files generated) who can't use the all-or-nothing flag.

**Rough effort**: ~half a day.

---

## PR #4 follow-ups

### `bootstrap.py --enable-github-review={claude,both-docs}` for retroactive Tier-2 (imp-2)

**Status**: parked.

**Why parked**: A `--github-review=none` user who later wants to add bots
must currently re-run `bootstrap.py --apply` with ALL required args
(`--language`, `--project-name`, `--out`, `--github-owner`, `--github-repo`)
plus `--overwrite-existing`. Too clunky for user-facing docs. A single
`--enable-github-review` flag would write ONLY the github-review-conditional
files (`.github/workflows/claude-review.yml`, `docs/codex-github-review-setup.md`
overlay, PR template's reviewer checklist) with `--overwrite-existing`
semantics on those specific files.

**Triggers to pick up**: first `--github-review=none` user wants to add
bots later.

**Rough effort**: ~half a day.

### Codex/Claude reviewer alternation per iteration (imp-1)

**Status**: parked.

**Why parked**: PR #4's plan-review loop ran 6 Codex iterations + 1 Claude
iter (Claude direction returned only a summary — known `--permission-mode plan`
quirk). Could alternate reviewers to halve loop cost, but risks losing
complementary catches that each reviewer surfaces.

**Triggers to pick up**: subscription limits hit again on PR #5 or beyond,
AND idea-(a)/(b) prompt improvements don't reduce loop count enough.

**Rough effort**: ~1 day to design + measure on a real PR.

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

### `review-plan-fact-check-by-{claude,codex}` subagent target (imp-2)

**Status**: parked.

**Why parked**: separate from idea-(b) consistency check. A narrow subagent
that reads the plan + the current repo, and for every file path / test name /
line number / module reference in the plan, verifies it matches reality.
Catches the plan-vs-repo factual-mismatch class of findings (~25% of what
Codex finds) before Codex does.

**Triggers to pick up**: if iter-N reviews on upcoming PRs keep finding
plan-vs-repo factual mismatches.

**Rough effort**: ~half a day.

## PR #7 follow-ups

### Path-safety validation for `--mode=adopt` against sensitive target paths (imp-2)

**Status**: parked. **Source**: claude[bot] Tier-2 review on Plan PR #16 (finding #1).

**Why parked**: PR #7's `--mode=adopt` doesn't add path-safety validation
against sensitive target paths (those containing `secrets/`, `data/`,
customer content, real PII directories). The existing renderer-layer +
CLI-layer path-safety check guards against `..`/absolute-path escapes
but doesn't refuse to operate against paths that LOOK like production
data directories. The first version's blast radius is bounded by adopt
mode's per-file consent model (every recommendation is shown + decided
with the owner), but an extra refuse-by-default for sensitive paths
would be defense-in-depth.

**Triggers to pick up**:
- First user reports adoption-mode acting against a path containing
  `secrets/` or `data/`.
- A near-miss during a Tier-2 review of a future adoption-mode PR.

**Rough effort**: ~1 hour — add a path-pattern check in
`bootstrap_lib/cli.py` before adopt-mode dispatch (refuse paths matching
`secrets/`, `data/`, `customer_data/`, configurable via flag for
intentional opt-in). Tests in `tests/test_bootstrap_cli.py`.

---

### Update CLAUDE.md + shared/CLAUDE.md.tmpl: Codex GitHub bot IS configured (imp-2)

**Status**: parked. **Source**: discovered 2026-05-19 during PR #16 Tier-2 review verification.

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

### Filesystem-stress test for v1→v2 restore (imp-2)

**Status**: parked. **Source**: claude[bot] Tier-2 review on Plan PR #16 (finding #2).

**Why parked**: PR #7's manifest v2 introduces per-policy restore
semantics (`WRITE` removes created file, `OVERWRITE` writes
content_before_b64 back, `WRITE_NEW` removes `.new`, `APPEND_MERGE`
truncates to `pre_append_length`). The standard tests cover the happy
path + SHA-mismatch guard, but not filesystem-stress scenarios
(disk-full mid-restore, permission changes between manifest write and
restore, `EACCES` on `os.chmod`, `ENOSPC` on `write`, race with another
process). PR #1's restore had the same gap; PR #7 inherits + extends.

**Triggers to pick up**:
- First reported restore failure under disk-full or permission-change
  scenarios.
- A future PR rewrites restore internals (worth covering before
  shipping).

**Rough effort**: ~half a day. Add a fixture with monkey-patched
filesystem operations in `tests/test_manifest.py` covering: (i) ENOSPC
mid-restore, (ii) EACCES on chmod, (iii) target file modified between
manifest write and restore (SHA mismatch — already covered, but
exercise the cleanup path), (iv) partial restore (some files restored,
some failed — verify cleanup state).

---

## PR #6 follow-ups

### ✅ Fix `make review-plan-by-claude` + `review-plan-consistency-by-claude` + `review-commit-by-claude` plan-mode-exit-declined bug — DONE in PR #6 Step 13

**Status**: done.

**Summary**: All five Claude-direction review targets used `claude --print --permission-mode plan --add-dir ... --output-format text "..."`. The `--permission-mode plan` flag caused the subagent to enter plan mode, generate its findings, then politely decline ExitPlanMode (correctly per its own guidance: research task, not implementation). The harness then wrote `"The user declined the exit. The findings above stand as the deliverable for the consistency self-check"` to the output file INSTEAD of the actual findings. Surfaced during PR #6 iter-1.5 self-check; spread across all 5 affected targets confirmed during iter-2.

**Fix**: Removed `--permission-mode plan` from all 5 occurrences in `shared/Makefile.review.tmpl` + same 5 in `Makefile` (the skill-repo's dogfood). The prompts already say "Do NOT edit any files" (file-edit safety covered at the prompt layer); without plan mode, no ExitPlanMode call attempts, no spurious "declined" output. Verified by re-running `make review-plan-consistency-by-claude` against the converged PR #6 plan file — output is now the actual findings list, not the decline message.

**Triggers met**: Surfaced during PR #6 plan loop; user decision (2026-05-19) co-landed in PR #6 impl rather than as a separate small PR.

**Effort**: ~30 min including the verification run.

---

### Pin uv binary version in CI (imp-1)

**Status**: parked.

**Why parked**: Generated CI uses `astral-sh/setup-uv@v8.1.0` (action ref pinned — required because setup-uv v8 has no floating major tag). The uv BINARY version is NOT pinned — the action's default (latest stable uv) is what gets installed. `uv.lock` provides per-project reproducibility, so the binary version drift is OK for most cases.

**Triggers to pick up**:
- First time the action's default-latest uv binary breaks a smoke walk.
- User reports CI non-determinism from uv version drift.

**Rough effort**: ~30 min — add `version:` input to the `astral-sh/setup-uv@v8.1.0` invocations in both `languages/python/ci.yml.tmpl` (generated CI) and `.github/workflows/ci.yml` (skill repo CI) + docstring explaining the trade-off.

---

### uv migration tool (`bootstrap.py --migrate-from=pip --to=uv`)

**Status**: parked.

**Why parked**: PR #6 added uv support but does NOT convert existing pip projects to uv (adoption-mode respects the user's existing tooling). A migration tool would: read `requirements*.txt`, convert pin lines to `[dependency-groups].dev` in `pyproject.toml`, run initial `uv sync` to create `uv.lock`, optionally delete `requirements*.txt` after success.

**Triggers to pick up**:
- A user explicitly asks "I have a pip project; how do I switch to uv?"
- The PR #7 trial on `call-details/` surfaces this as a common adoption need.

**Rough effort**: ~1 day — design + impl + tests + docs.

---

### Adoption-mode UX redesign (analyze-then-decide-with-owner)

**Status**: parked. **Ships in PR #7 (hybrid: trial + adoption mode together) per user decision 2026-05-19.**

**Why parked**: PR #6 keeps the existing PR #1 collision-abort contract unchanged (`--apply` aborts on any collision unless `--overwrite-existing`). The real redesign is content-driven: a 4-phase `--mode=adopt` flag — (1) **Analyze** the target project per file (size, sections, markers), (2) **Recommend** a policy with reasoning shown to the user (`SKIP` / `OVERWRITE` / `WRITE-.new` / `APPEND-MERGE`), (3) **Decide with owner** (interactive prompt OR batch report with `--auto-accept-recommendations` for non-interactive use), (4) **Apply** per the agreed policies. **Not a hardcoded policy table** — different projects need different choices.

**Triggers to pick up**: PR #7 trial on `call-details/` is the empirical data source for the recommendation heuristics. PR #7 ships both the trial AND the redesign together.

**Rough effort**: ~2-3 days informed by trial data.

---

### Library-style scaffold (`--library` flag)

**Status**: parked.

**Why parked**: PR #6's greenfield uv mode ships in "non-package" mode (`[project]` table, no `[build-system]`) — correct for application starters, but doesn't support building a wheel. A `--library` flag would: add `src/<project_import_name>/__init__.py` package layout + `[build-system] uv_build` + `dependencies = []` stays + add `[project.scripts]` entry for installable CLIs.

**Triggers to pick up**: First user with a real library-publishing use case.

**Rough effort**: ~half a day — new scaffold files + tests + Architecture-decision doc edits.

---

### Real-project trial on `~/Desktop/Code/Boxette/call-details/` — PR #7

**Status**: parked (= scoped to PR #7).

**Why parked**: PR #7 is the **hybrid** real-project trial + adoption-mode redesign. The trial against `call-details/` uses `--dry-run` / `--diff` first to produce an empirical collision manifest (call-details has 8 collisions today: `CLAUDE.md`, `README.md`, `pyproject.toml`, `.python-version`, `uv.lock`, `.gitignore`, `src/`, `tests/` — and ~12 files that write cleanly). That manifest informs the adoption-mode recommendation heuristics. Trial finishes with a real `--apply --mode=adopt` using the new policies.

**Deliverables**: (i) trial plan in `docs/plans/`, (ii) `docs/trial-report-pr7.md` (one-time structured trial-experience write-up; NOT a typo for `LESSONS.md` — the two artifacts are intentionally distinct), (iii) the `--mode=adopt` implementation, (iv) any skill polish surfaced.

**Triggers to pick up**: PR #6 merges. (Already scheduled.)

**Rough effort**: ~3-4 days for the combined plan + impl loop.

---

### Tighten CLAUDE.md two-tier review wording from "or" to explicit same-AI / cross-AI split (imp-2)

**Status**: parked.

**Why parked**: CLAUDE.md's current "Tier-1 (after each focused commit, before push): `make review-commit-by-claude` or `make review-commit-by-codex`" presents both targets as equally valid options. The discipline (per LESSONS.md 2026-05-19 entry, surfaced via user push-back during PR #6 impl) is that Tier-1 uses the **same AI as the implementer** (Claude→Claude, Codex→Codex), and cross-AI review only fires at Tier-2 (claude[bot] + chatgpt-codex-connector). The "or" wording is too permissive and led to me using Codex for Tier-1 on Steps 2–3 before the user caught it.

**Triggers to pick up**:
- Next plan-review session opens (this is a fundamental-shift candidate per LESSONS.md's "Promotion to CLAUDE.md only for FUNDAMENTAL shifts" rule).
- Any other contributor hits the same "or" ambiguity.

**Rough effort**: ~30 min — one CLAUDE.md edit + same edit in `shared/CLAUDE.md.tmpl` + parametrized test in `tests/test_triage_byte_identity.py` to assert both files have the same updated wording. Likely needs a tiny plan PR since it changes the workflow contract.

## PR #5 follow-ups

### `sync-plan-to-ui` Makefile target (imp-1)

**Status**: parked.

**Why parked**: Claude Code's plan-mode UI reads from `~/.claude/plans/<file>.md`
which is separate from the in-repo `docs/plans/<file>.md`. As iterations
proceed in-repo, the UI version drifts. A `make sync-plan-to-ui PLAN_FILE=...
UI_NAME=...` target would `cp` the in-repo file over the UI file.

**Triggers to pick up**: if the drift causes another confusion incident
like the one in PR #5 plan loop (user opened the plan-mode UI and saw the
iter-1 version while the repo had iter-6).

**Rough effort**: ~15 min — a tiny `cp` target with safety check.

### Investigate Codex GitHub bot's ready-state auto-fire reliability (imp-1)

**Status**: parked.

**Why parked**: empirically, Codex Tier-2 review didn't auto-fire on
`gh pr ready` transition during Plan PR #9 + Impl PR #10. Both required
explicit `@codex review` comment to trigger. Codex DID auto-fire on Impl
PR #11. Pattern unclear — might be timing, might be the specific PR
content shape, might be GitHub-app config.

**Triggers to pick up**: third consecutive PR where Codex doesn't
auto-fire on ready-state. Then investigate the GitHub app's webhook
config + recent Codex GitHub-bot release notes.

**Workaround until investigated**: documented in `docs/usage.md` —
always comment `@codex review` after `gh pr ready` if Codex doesn't
auto-fire within ~5 min.

**Rough effort**: ~30 min investigation + ~15 min doc note if it turns
out to be a known limitation.

### Helper script to auto-append a reviewed impl-log row (imp-1)

**Status**: parked.

**Why parked**: per PR #5 plan, `## Implementation log` rows are
proposed by Tier-1 review and pasted by the driver into the plan file
(then a separate docs-only commit). PR #5's "Capture is semi-automatic"
design principle (closes Codex iter-5 #5) explicitly acknowledged the
manual paste step as a trade-off. A helper script (`make append-impl-log
PLAN_FILE=... ROW='...'` or one that parses the Tier-1 output) would
automate this.

**Trigger to pick up**: if driver-forgets-to-paste happens twice on any
post-PR-#5 implementation PR.

**Rough effort**: ~1 hour.

### ✅ "When adding a new Make target with overlapping semantics, audit + mirror the existing guards" (process lesson) — DONE in PR #5c

**Status**: shipped 2026-05-18 — captured as `LESSONS.md` entry #6.

**Source**: PR #5b Codex Tier-2 fold (`61f0101`). When I added
`review-commit-by-{codex,claude}` (semantically overlapping
`review-plan-by-{codex,claude}`), I missed the `test -f "$(PLAN_FILE)"`
guard that the plan-review targets already had. Codex caught it.

For generated projects: the lesson is project-local and doesn't ship in
the shared template (which starts empty). Generated projects accumulate
their own equivalent if/when they encounter the pattern.
