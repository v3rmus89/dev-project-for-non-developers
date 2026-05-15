# Backlog — parked decisions and future work

Items here are explicit "we will do this someday" decisions, recorded so they
don't get lost between sessions. Each item lists **why it's parked**, **what
triggers picking it up**, and **rough effort**.

Newer items at the top.

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

### Add Node-TS language support (`languages/nodejs/`)

**Status**: parked for PR #2.

**Why parked**: PR #1 is Python only. PR #2 will add Node-TS (Biome +
vitest) once PR #1's templates + bootstrap engine + safety primitives
ship.

**Triggers to pick up**: PR #1 merged.

**Rough effort**: ~1 day per the merged plan in
`docs/plans/2026-05-15-skill-pr1-minimal-python-bootstrap.md`'s "What we
are NOT doing" + the master plan in the Boxette repo.

---

### Add Go language support (`languages/go/`)

**Status**: parked for PR #3.

**Triggers to pick up**: PR #2 merged.

**Rough effort**: ~1 day.

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
