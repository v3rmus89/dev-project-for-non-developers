# Backlog — parked decisions and future work

Items here are explicit "we will do this someday" decisions, recorded so they
don't get lost between sessions. Each item lists **why it's parked**, **what
triggers picking it up**, and **rough effort**.

Newer items at the top.

---

## Follow-ups from the config-shadowing fix

Parked items from [docs/plans/2026-05-21-skill-config-shadowing-fix.md](docs/plans/2026-05-21-skill-config-shadowing-fix.md) (Bucket E).

### TOML section-merge for adoption-into-existing-`pyproject.toml` (imp-2)

**Status**: parked — adoption mode currently SKIPs an existing non-trivial
`pyproject.toml` (rule (g)/(h)) and emits the B2 advisory telling the owner to
merge the skill's `[tool.ruff]` / `[tool.pytest.ini_options]` tables by hand.
A section-merge would offer to add those tables automatically when they are
absent, with owner confirmation.

**Why parked**: the existing SKIP + advisory is a *safe, informed* outcome;
auto-injecting config is the very class of bug the config-shadowing fix
closed, so a merge feature needs its own careful design (idempotency, restore
semantics, owner consent).

**Trigger to pick up**: adoption mode gains an owner-confirmed config-merge
capability, or repeated user requests to auto-apply the skill's tool config.

**Rough effort**: ~half a day (plan + implementation).

### `tox.ini` / `setup.cfg` as additional pytest-config shadow sources (imp-1)

**Status**: parked — the B1 shadow scan covers `ruff.toml` / `.ruff.toml` /
`pytest.ini`. pytest also reads config from `tox.ini` (`[tool:pytest]`) and
`setup.cfg` (`[tool:pytest]`).

**Why parked**: `pytest.ini` is the common standalone case; `tox.ini` /
`setup.cfg` pytest config is rarer in new projects and lower-priority.

**Trigger to pick up**: a real adoption target is found keeping pytest config
in `tox.ini` / `setup.cfg`.

**Rough effort**: ~1 hour (extend the scan to parse those files for a
`[tool:pytest]` section + tests).

### Nested (non-top-level) standalone-config scan (imp-1)

**Status**: parked — the B1 shadow scan is **top-level only** (`target_root`,
not recursive). A monorepo with sub-directory `ruff.toml`s would not be scanned.

**Why parked**: the skill targets single small projects; a recursive scan also
risks surfacing sensitive nested path names and noisy partial shadows.

**Trigger to pick up**: a monorepo-shaped adoption target with sub-directory
`ruff.toml`s.

**Rough effort**: ~half a day (needs a privacy-aware recursive-scan design).

### Migrate the skill repo's own `ruff.toml` / `pytest.ini` into `pyproject.toml` (imp-1)

**Status**: parked — the config-shadowing fix moved the *generated* projects'
config into `pyproject.toml`, but the skill repo's own `ruff.toml` /
`pytest.ini` were left as-is.

**Why parked**: the skill repo is not a bootstrapped artifact; migrating its
lint config could surface new lint errors on the skill's own code mid-PR, which
should not ride along on an unrelated change.

**Trigger to pick up**: a maintenance window where surfacing/fixing any new
lint findings on the skill's own code is acceptable.

**Rough effort**: ~1 hour (mechanical migration + fix any new findings).

### Node / Go config-file shadowing (imp-2)

**Status**: parked — the skill ships `biome.json` (Node) and `.golangci.yml`
(Go). Biome also discovers `biome.jsonc`; `golangci-lint` also discovers
`.golangci.{yaml,toml,json}`. A target-owned alternate-extension config can
therefore shadow the skill's file — the same class of bug the Python
config-shadowing fix addressed. Surfaced by Codex Tier-2 on the plan PR.

**Why parked**: the config-shadowing fix was scoped to Python, where the bug
actually bit (call-details dogfooding). Node/Go adoption mode is itself parked
for a follow-up, so the shadow handling belongs with that work.

**Trigger to pick up**: adoption-mode shadow handling is extended beyond
Python, or a real Node/Go adoption target is found owning an alternate-extension
config.

**Rough effort**: ~half a day (alongside Node/Go adoption-mode work).

---

## Follow-ups from the interactive-intake work (skill PR #8)

### ✅ PR #9 — smart stack suggestion from a plain-English project description — DONE

**Status**: shipped — see
[docs/plans/2026-05-22-skill-pr9-smart-stack-suggestion.md](docs/plans/2026-05-22-skill-pr9-smart-stack-suggestion.md).
The interactive intake gained an optional "describe your project" step: a
deterministic keyword `stack_suggest` engine maps the description to a
*language* suggestion that pre-fills the language-menu default (the user still
confirms). Resolved decisions: deterministic signal scorer, not an LLM (keeps
the "pure offline CLI, no `.env`" invariant); language-only, not package
manager (a brief carries no uv-vs-pip signal); superpowers patterns referenced,
StackShare data used as CC0 inspiration, no code vendored.

### Non-interactive `--describe "..."` CLI flag (imp-1)

**Status**: parked — PR #9 (smart stack suggestion) shipped the suggestion as
an *interactive-intake* step only. A non-interactive `--describe "<brief>"`
flag would let a scripted / CI invocation get the same language suggestion
without the guided flow.

**Why parked**: PR #9's plan scoped this out deliberately — a `--describe`
flag is a larger surface (argv parsing, non-TTY semantics, how a suggestion
interacts with an explicit `--language`). The interactive step covers the
non-coder use case the skill is built for.

**Triggers to pick up**: a real need for scripted / non-interactive stack
suggestion (e.g. a wrapper tool or a CI bootstrap that wants the suggestion).

**Rough effort**: ~2-3 hours (a flag + argv wiring + tests; the
`stack_suggest` engine already exists).

---

### Interactive intake: explicit cancel option on the output-directory re-ask (imp-1)

**Status**: parked. **Source**: Tier-1 review during skill PR #8 implementation.

**Why parked**: `intake.run_intake`'s output-directory loop re-asks `--out`
whenever the chosen folder is an existing project; the only ways out are
picking a clean folder or pressing Ctrl-D / Ctrl-C (both handled cleanly,
exit 0). A user with only existing-project folders to offer has no
explicit in-loop "cancel" choice. Ctrl-C is a working, documented escape,
so this is UX polish, not a correctness gap.

**Triggers to pick up**: a user reports feeling stuck in the
output-directory re-ask, or the next change to the intake flow.

**Rough effort**: ~20 min — accept an explicit "cancel" word at the
output-directory prompt and return `None` (same as the confirm gate's
cancel).

---

## Follow-ups from the info-architecture refactor

### Mirror the gh-repo-create hint into adopt-mode's `_main_apply_adopt` success path (imp-2)

**Status**: parked. **Source**: scoped out of the info-architecture refactor PR (`refactor/tighten-info-architecture`, 2026-05-21).

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

### Adopt-mode skips the greenfield smoke placeholders for an existing project (imp-2)

**Status**: parked. **Source**: PR #7 adopt-mode trial against `call-details` (recorded during skill PR #8).

**Why parked**: an `--apply --mode=adopt` run emitted the greenfield smoke
placeholders `src/main.py` (`print("hello from <project>")`) and
`tests/test_smoke.py` (`assert True`) into `call-details`, which already
has real source under `src/boxette_calls/` and a real test suite. Adopt
mode should not scaffold greenfield-only placeholder code into a project
that already has code.

**Triggers to pick up**: the next adopt-mode change, or a user reports a
stray `src/main.py` / `tests/test_smoke.py` after an adopt run.

**Rough effort**: ~1-2h — gate the `src/main.py` + `tests/test_smoke.py`
emit on greenfield-vs-adopt in the adopt apply path.

---

### Adopt-mode's `Makefile` `run` target is hardcoded to `src/main.py` (imp-2)

**Status**: parked. **Source**: PR #7 adopt-mode trial against `call-details`.

**Why parked**: the skill's `Makefile` ships `run: uv run python src/main.py`
— correct for the greenfield smoke layout, wrong for an adopted real
project whose entry point is elsewhere (`call-details` uses a
`[project.scripts]` console script). After an adopt run, `make run` points
at a placeholder (or, once the placeholder is dropped per the entry above,
a missing file).

**Triggers to pick up**: the next adopt-mode change, or a user reports
`make run` broken after an adopt run.

**Rough effort**: ~1h — in adopt mode, detect the target's real entry
point (e.g. `[project.scripts]`) and retarget `run`, or leave `run` as a
documented TODO for the user to fill in.

---

### Adopt-mode does not add `pre-commit` to the target's dev dependencies (imp-2)

**Status**: parked. **Source**: PR #7 adopt-mode trial against `call-details`.

**Why parked**: adopt mode applies `.pre-commit-config.yaml` and the
`make install-hooks` target, but `make install-hooks` runs
`uv run pre-commit install` — and adopt mode (correctly) does not
overwrite the target's real `pyproject.toml`, so `pre-commit` is missing
from the target's dev-dependency group and `make install-hooks` fails.
(Distinct from the parked "Direct `--install-hooks` flag" entry under
"Skill follow-ups", which is about a skill-side bootstrap flag.)

**Triggers to pick up**: the first adopt user runs `make install-hooks`
and it fails on a missing `pre-commit`.

**Rough effort**: ~1h — adopt mode appends `pre-commit` to the detected
dev-dependency group (or prints a one-line "add pre-commit to your dev
deps" hint after applying `.pre-commit-config.yaml`).

---

### Adopt-mode: `AGENTS.md` can collide with the target's `.gitignore` (imp-1)

**Status**: parked. **Source**: PR #7 adopt-mode trial against `call-details`.

**Why parked**: `call-details`'s `.gitignore` listed `AGENTS.md` (it had
been ignored as Codex-CLI scratch residue). The skill's `AGENTS.md` is a
*tracked* reviewer-guidance deliverable, so an ignored `AGENTS.md` is
silently never committed and the GitHub review bots never read it. Adopt
mode writes the file but does not notice the gitignore conflict.

**Triggers to pick up**: an adopt user whose `.gitignore` already lists
`AGENTS.md` reports the review bots having no repo-specific guidance.

**Rough effort**: ~30 min — adopt mode detects an `AGENTS.md` entry in the
target's `.gitignore` and warns (or documents the conflict in the
adopt-mode docs).

---

### Annotate `--diff` headers with adopt-mode policy recommendations (imp-2)

**Status**: parked. **Source**: Tier-1 doc review on Bucket F docs commit (PR #17).

**Why parked**: Plan PR #16 Scope #8 + Bucket A row 8 specified that
plain `bootstrap.py --diff --language python` should run the analyzer
in read-only mode and annotate each unified-diff header with the
recommended policy (e.g. `--- a/CLAUDE.md (target: 96 lines)` /
`+++ b/CLAUDE.md (recommendation: WRITE_NEW)`). PR #7's impl path
focused on `--apply --mode=adopt` end-to-end; the `--diff` annotator
was not shipped. Plain `--diff` currently produces standard
`difflib.unified_diff` headers without policy annotations.

The Bucket F docs reference this caveat inline in the worked example;
the recommendation report (Step 2 of adopt-mode) shows the policy
per file, so the user-facing gap is only in the read-only-preview
workflow.

**Triggers to pick up**:
- A user requests inline policy annotations during `--diff` preview.
- Bucket E live trial surfaces the read-only-preview UX gap as a
  blocker to confident adopt-mode adoption.

**Rough effort**: ~2 hours — extend `_print_diff` in `bootstrap_lib/cli.py`
to call `adopt.analyze_target` when `args.language == "python"` (no
manifest, no writes), then inject policy strings into the `fromfile`/
`tofile` arg shape. Tests in `tests/test_bootstrap_cli.py` + new
fixture in `tests/test_mode_adopt_smoke.py` for the annotated diff
shape.

---

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

### Adoption-mode: align line-ending handling between gitignore normalization and append-merge (imp-1)

**Status**: parked. **Source**: Tier-1 review on `plan_adoption_entries` impl
commit (PR #17).

**Why parked**: `_normalize_gitignore_lines` (used by rule (d) membership
check in `recommend_policy`) decodes UTF-8 and uses `str.splitlines()`,
which handles `\r\n`/`\r`/`\v`/`\f` line endings. But
`compute_append_merge_bytes` (used to compute the post-apply bytes and
the apply-time write) operates in bytes and uses `bytes.split(b"\n")`,
which only splits on `\n` and leaves `\r` in each line.

For a CRLF-terminated target `.gitignore` (Windows-cloned repo, mixed
toolchain), rule (d)'s membership check matches `b"venv/"` (post-strip),
but the merge function's appended `raw_line` retains the `\r`, producing
a mixed `\r\n` + `\n` output on the next apply.

The PR #7 scope (call-details/ trial on macOS) uses LF-terminated
gitignore, so this doesn't fire. Real-but-deferrable.

**Triggers to pick up**:
- First user reports `.gitignore` mojibake or churn on a Windows-
  cloned repo using `--mode=adopt`.
- A test failure on a CI matrix that runs on Windows (not currently
  configured).

**Rough effort**: ~30 min — either (a) align both to bytes-split on
`\n` with `\r` stripped before processing, or (b) align both to
`str.splitlines()` after UTF-8 decode. Tests in `TestComputeAppendMergeBytes`
need one CRLF round-trip test added.

---

### Adoption-mode: route APPEND_MERGE restore through atomic_write for parity with OVERWRITE (imp-2)

**Status**: parked. **Source**: Tier-1 review on v2 restore matrix impl commit (PR #17).

**Why parked**: `_restore_v2_append_merge` uses
`open(path, "rb+").truncate(pre_append_length) + flush + fsync` to undo
APPEND_MERGE applies. `truncate(N)` is atomic-at-inode-level on POSIX
filesystems (the file length is old-or-new, never partial bytes), so
the safety contract holds. But v1 OVERWRITE restore routes through
`bio.atomic_write` (tmp + `os.replace`) per Codex iter-21 P1's
"no in-place truncation" discipline, and APPEND_MERGE diverges from
that pattern. Marginally weaker consistency story than "all restore
paths route through atomic_write."

The alternative (read `[:pre_append_length]` bytes + atomic_write)
costs one extra read per APPEND_MERGE entry — negligible at PR #7's
trial scale (1 collision file).

**Triggers to pick up**:
- First reported crash-during-restore bug that surfaces APPEND_MERGE
  truncation state inconsistency.
- A future audit of "all restore mutations route through atomic_write"
  catching this divergence.

**Rough effort**: ~30 min — replace truncate block with `data = full[:pre_append_length]; bio.atomic_write(target_path, data)`. Tests
already assert post-restore content equality, no test changes needed.

---

### Adoption-mode: orchestrator-level test for rule (a0) via subprocess git path (imp-1)

**Status**: parked. **Source**: Tier-1 review on `analyze_target` impl commit (PR #17).

**Why parked**: `TestRecommendPolicyRules.test_rule_a0_...` exercises rule
(a0) at the unit layer (feeds `ignored_by_git=".gitignore:..."` directly
into TargetMeta). `TestAnalyzeTarget.test_call_details_shaped_fixture` is
the only orchestrator-level integration test, and it doesn't `git init`
`tmp_path` — so `_check_ignored_by_git` returns `None` for every file,
and the (a0) path through the full subprocess pipeline is never exercised
end-to-end. The git plumbing IS exercised by
`TestComputeTargetMeta.test_ignored_by_git_for_missing_file`, so coverage
isn't zero — just split.

**Triggers to pick up**:
- A future regression where the subprocess error-handling in
  `_check_ignored_by_git` changes and breaks (a0)'s orchestrator path.
- During the live `--apply --mode=adopt` trial against call-details if
  AGENTS.md misfires.

**Rough effort**: ~15 min — add one test that does `_git_init(tmp_path)`,
writes `.gitignore` ignoring `Makefile`, then calls `analyze_target` with
`{"Makefile": b"..."}` and asserts SKIP/manual_review=True via the full
subprocess path.

---

### Adoption-mode: thread `target_content` from analyze_target to recommend_policy (imp-1)

**Status**: parked. **Source**: Tier-1 review on `analyze_target` impl commit (PR #17).

**Why parked**: `_compute_target_meta` reads each existing target file
once; `recommend_policy` re-reads the same file (for rules b/d/f/g that
need bytes). For PR #7's call-details collision set (4 files), that's
8 reads vs 4 — negligible. For a target with hundreds of colliding
files, the double-read could matter. The current docstring on
`recommend_policy` explains the design choice: TargetMeta is deliberately
content-free per Scope #11 privacy boundary — but a separate `bytes`
parameter wouldn't violate that.

**Triggers to pick up**:
- First user reports adopt-mode running noticeably slow against a large
  target (>100 colliding files).
- Performance benchmarks added to the CI run.

**Rough effort**: ~1 hour — add `target_content: bytes | None = None`
parameter to `recommend_policy`; `analyze_target` passes the buffer
from `_compute_target_meta`'s read (via a small refactor of
`_compute_target_meta` to optionally return content alongside meta).
Update all existing `recommend_policy` callers in tests.

---

### Adoption-mode rule (d): `.gitignore` order-aware merge for `!negation` patterns (imp-1)

**Status**: parked. **Source**: Tier-1 review on `recommend_policy` impl commit (PR #17).

**Why parked**: `_normalize_gitignore_lines` (`bootstrap_lib/adopt.py`)
uses a `set` for line-membership, which is correct for the common case
(skill adds new positive patterns missing from target's gitignore) and
order-blind by design. Gitignore semantics ARE order-dependent in one
edge case: `*.log` followed by `!important.log` differs from the reverse
order. The current APPEND_MERGE always appends to end, so if the skill
template ever includes `!negation` patterns that need to come AFTER
specific positive matches in the target, the merge would produce
semantically-different behavior than a hand-written ordering.

The call-details collision set used for PR #7's trial doesn't have
`!negation` patterns; the skill's own `.gitignore.tmpl` doesn't either.
Real-but-deferrable.

**Triggers to pick up**:
- First user reports APPEND_MERGE producing wrong gitignore semantics
  after running `--mode=adopt` on a project with negation patterns.
- The skill's `.gitignore.tmpl` ever adds a `!negation` pattern.

**Rough effort**: ~1 hour — extend `_normalize_gitignore_lines` to
return an ordered list with positional metadata; rewrite the APPEND_MERGE
contract to insert `!negation` lines in semantically-correct positions
rather than always-end-append. Manifest v2 `pre_append_length` would
need to become a more general "pre-merge state hash" for restore to work.

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

**Effort**: ~2 weeks across plan + impl, informed by call-details trial.

---

### Library-style scaffold (`--library` flag)

**Status**: parked.

**Why parked**: PR #6's greenfield uv mode ships in "non-package" mode (`[project]` table, no `[build-system]`) — correct for application starters, but doesn't support building a wheel. A `--library` flag would: add `src/<project_import_name>/__init__.py` package layout + `[build-system] uv_build` + `dependencies = []` stays + add `[project.scripts]` entry for installable CLIs.

**Triggers to pick up**: First user with a real library-publishing use case.

**Rough effort**: ~half a day — new scaffold files + tests + Architecture-decision doc edits.

---

### Real-project trial on `~/Desktop/Code/Boxette/call-details/` — PR #7

**Status**: in-progress (= the live trial portion of PR #7; engine + smoke fixtures shipped, live trial pending).

**Scope**: PR #7 is the **hybrid** real-project trial + adoption-mode redesign. The trial against `call-details/` is the empirical data source for the recommendation heuristics. The collision baseline was empirically verified during plan iter-1 fold via `bootstrap.py --dry-run --language python --project-name call-details --out ~/Desktop/Code/Boxette/call-details/`: **4 MODIFY collisions** (`.gitignore`, `.python-version`, `CLAUDE.md`, `pyproject.toml`) + **15 CREATE** (15 missing files the skill writes cleanly).

The pre-empirical "8 collisions" number from PR #6's plan was incorrect — it counted `README.md` + `uv.lock` (which exist in the target but aren't bootstrap writes) and `src/` + `tests/` (which are directories, not file collisions). Closes Codex iter-3 #5 baseline-correction fold.

**Deliverables**: (i) trial plan in `docs/plans/` ✅ shipped; (ii) `docs/trial-report-pr7.md` (one-time structured trial-experience write-up; NOT a typo for `LESSONS.md` — the two artifacts are intentionally distinct) — pending; (iii) the `--mode=adopt` implementation ✅ shipped (closes BACKLOG entry above); (iv) any skill polish surfaced — pending.

**Triggers to pick up**: engine done; smoke fixtures green; Bucket F docs landed; live trial is the next chunk (Phase D of plan Sequencing).

**Rough effort**: ~half a day for the live trial + trial-report.

---

### ✅ Tighten CLAUDE.md two-tier review wording from "or" to explicit same-AI / cross-AI split (imp-2) — DONE

**Status**: ✅ shipped 2026-05-21 — the info-architecture refactor PR (`refactor/tighten-info-architecture`) tightened the Tier-1 wording to "use the same AI as the implementer" in `CLAUDE.md` + `shared/CLAUDE.md.tmpl`'s Two-tier section, and replaced the bare `# or review-commit-by-codex` phrasing in `CONTRIBUTING.md` + `shared/CONTRIBUTING.md.tmpl` with the same-AI clarification.

**Why parked** (historical): CLAUDE.md's former "Tier-1 (after each focused commit, before push): `make review-commit-by-claude` or `make review-commit-by-codex`" presents both targets as equally valid options. The discipline (per LESSONS.md 2026-05-19 entry, surfaced via user push-back during PR #6 impl) is that Tier-1 uses the **same AI as the implementer** (Claude→Claude, Codex→Codex), and cross-AI review only fires at Tier-2 (claude[bot] + chatgpt-codex-connector). The "or" wording is too permissive and led to me using Codex for Tier-1 on Steps 2–3 before the user caught it.

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
