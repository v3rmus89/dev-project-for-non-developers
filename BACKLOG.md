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

### Retroactively add triage rule to Boxette's plan-review docs

**Status**: parked (PR #1 in-repo scope only; Boxette is a separate repo).

**Why parked**: the "Don't fold by default — triage" rule was developed
during this skill's plan-review loop (it cut iteration count from
diverging to converging in ~3 iters). Boxette (the source repo this skill
extracts patterns from) doesn't have it yet. Adding it would expand PR #1
across two repos.

**Triggers to pick up**: after PR #1 of this skill lands AND the next
substantive Boxette plan-review starts.

**Rough effort**: ~30 min — copy the rule verbatim into Boxette's
`CLAUDE.md`, `AGENTS.md`, `docs/plans/README.md`.

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
