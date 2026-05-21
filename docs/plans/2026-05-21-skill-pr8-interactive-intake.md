# Plan PR: interactive intake mode for the bootstrap skill

## Context

The repo is named `dev-project-for-non-developers`, but the only way to drive the
skill today is a wall of CLI flags:

```
./venv/bin/python bootstrap.py --apply --language python --package-manager uv \
  --github-review both-docs --github-owner v3rmus89 --github-repo my-project \
  --project-name my-project --out ../my-project
```

A non-coder cannot be expected to know that surface. Running `bootstrap.py` with
no flags today prints `missing required args: --language, --project-name, --out`
— a dead end for the skill's own target audience.

**PR #8 adds an interactive intake**: running `bootstrap.py` with no arguments on
a terminal (or with an explicit `--interactive` flag) starts a guided question
flow, echoes the resolved configuration, asks for confirmation, and only then
runs the existing pipeline. It is a thin **front-end** — it produces the same
argument set the CLI flags produce and re-feeds the existing parser, so every
existing validation, the dry-run default, and the restore manifest are untouched.

**Scope is GREENFIELD-only (iter-1 fold).** PR #8's intake guides the setup of a
*new* project. Adopting the workflow into an *existing* project stays flag-driven
via `--apply --mode=adopt`, which already has its own guided per-file
"analyze-then-decide-with-owner" UX. An intake front-end for adopt-mode is a
possible later PR.

*Greenfield* is defined precisely (iter-1.5 → iter-4 folds): a target folder that
**neither (a) contains any file the skill itself writes** for the chosen config
(`Makefile`, `CLAUDE.md`, the language manifest, `.github/…`, `src/main.py`, …)
**nor (b) contains any recognised project manifest in *any* supported language**
— `pyproject.toml`, `setup.py`, `uv.lock`, `requirements*.txt`, `package.json`,
`go.mod`. Check (b) is **language-agnostic** on purpose: choosing `nodejs` for a
folder that holds only a `pyproject.toml` must still be caught (that Python
manifest is absent from the nodejs planned-file set, so check (a) alone would
miss it — iter-4 fold). It is **not** "the folder is empty" — a folder that holds
only non-skill, non-manifest files (a business-goals note, a `data/` folder to
analyse, scratch notes) is still greenfield; the skill never writes or touches
those.

**Scope split (per user direction):** PR #8 asks for the language/tooling
**explicitly** (a numbered menu). The smarter "describe your project in plain
English and the skill suggests a stack" layer is **PR #9**, a separate plan.

**Python-version caveat (iter-1 fold):** the "a non-coder just runs
`bootstrap.py`" premise holds only when the invoked interpreter is Python 3.12+.
On a machine where `python3` is the macOS system 3.9, the 3.6-compatible shim
prints its version error and never reaches intake — a pre-existing constraint of
the skill, documented in `docs/usage.md` (which is why the invocation above and
the Phase-2 smoke-walk use `./venv/bin/python`), not introduced or solved here.

### Pre-coding: regression safety + outcome measurement

1. **Regression safety.** Auto-testable: intake unit tests that feed scripted
   stdin and assert the resolved argv; a `planned_paths` ≡ `render_all`-keys
   equivalence test across every shipped config; an end-to-end test that an
   interactive apply and the equivalent flag-driven apply produce byte-identical
   trees; TTY / EOF / Ctrl-C handling; the bare-`main([])` on a fake-TTY test;
   the cancel path (`main()` returns 0, target untouched, no restore manifest);
   `--interactive`-is-standalone rejection; required-empty-answer re-prompts;
   `test_shim_cli_help_consistency.py` continues to pass; the full existing CLI
   suite stays green unchanged (intake is purely additive). NOT auto-testable:
   whether the question wording reads clearly to a non-coder — covered by a
   manual greenfield intake smoke-walk in Phase 2.
2. **Outcome measurement.** No business metric applies — a developer-tool UX
   change with no telemetry. Success criterion: a non-coder can bootstrap a new
   project without reading the flag reference, validated by the Phase-2 manual
   intake walkthrough.

## Scope

### IN scope

| # | Change | Where |
|---|--------|-------|
| 1 | Add an `--interactive` boolean flag; extract `LANGUAGES`, `PACKAGE_MANAGERS`, `GITHUB_REVIEW_MODES`, `PROJECT_NAME_RE` into module constants in `_flags.py`; `cli.py` imports `PROJECT_NAME_RE` from there and its now-unused `import re` is removed (else ruff F401 fails `make check`) | `bootstrap_lib/_flags.py`, `bootstrap_lib/cli.py` |
| 2 | New `render.planned_paths(language, github_review_mode, enable_smoke, package_manager) -> set[str]` — the set of output paths the skill would write for a config, by applying the existing `_emit_in_mode` / `_emit_python_in_pm_mode` filters to the template-map keys **without rendering**. It normalizes Python `package_manager=None → "pip"` exactly as `render_all` does. A test locks `planned_paths(cfg) == set(render_all(context, language).keys())` for every shipped config — including Python `package_manager=None` (Bucket E) | `bootstrap_lib/render.py` |
| 3 | New `bootstrap_lib/intake.py` — the guided greenfield question flow: collects answers via `stdin.readline()`-based prompts, returns an argv list (or `None` on cancel; raises `IntakeAborted` on EOF) | `bootstrap_lib/intake.py` (new) |
| 4 | Trigger logic in `main()`: run intake when `--interactive` is passed OR when `bootstrap.py` is invoked with **zero** arguments AND `sys.stdin.isatty()`. `--interactive` is **standalone-only** — combined with any other flag → exit 2. `KeyboardInterrupt` during intake is caught → clean cancel | `bootstrap_lib/cli.py` |
| 5 | Intake question set (greenfield) — see Bucket B. The output-directory question is asked **last** (just before the greenfield check), carries a default (`../<project-name>`) — empty input accepts it — plus one line of guidance; the no-default required answers (`--github-owner`, `--github-repo`) are re-prompted on empty input | `bootstrap_lib/intake.py` |
| 6 | Confirm gate: after the questions + the greenfield check, print the resolved configuration in plain language, then ask **apply / cancel** | `bootstrap_lib/intake.py` |
| 7 | Intake builds an argv list and `main()` re-parses it through the **existing** `_build_parser()` — a backstop, not the primary validation | `bootstrap_lib/cli.py`, `bootstrap_lib/intake.py` |
| 8 | Append four `BACKLOG.md` entries (each with the repo's required *why parked* / *trigger* / *rough effort* fields — see Lessons) for the adopt-mode quality items observed while bootstrapping `call-details`; committed as a clearly-labelled "PR #7 adopt-mode-trial cleanup" commit, after a dedup check against existing `BACKLOG.md` entries (iter-5 fold, Codex 4) | `BACKLOG.md` |
| 9 | Tests — see Bucket E | `tests/test_intake.py` (new), `tests/test_render.py`, `tests/test_bootstrap_cli.py` |
| 10 | Docs: document the interactive mode (incl. intake's two-check greenfield definition) in a **new `docs/usage.md` section** + a one-line `README.md` pointer. Separately, fix the two *stale* `docs/usage.md` phrases — the adopt-mode "When NOT to use it" list and the uv-detection table's "empty-or-nonexistent dir" row — by **dropping the inaccurate "no files"/"empty dir" phrasing**; do NOT import intake's manifest-scan definition into those flag-driven sections, which use narrower notions of greenfield (iter-5 fold, Claude 2-B). `SKILL.md` is intentionally unchanged (see NOT-in-scope) | `docs/usage.md`, `README.md` |

### NOT in scope

- **Adopt-mode via intake.** PR #8's intake is greenfield-only. Adopting into an
  existing project stays `--apply --mode=adopt` (flag-driven; Python-only today).
  An intake front-end for adopt — and nodejs/go adoption — is a possible later PR.
- **A unified-diff "preview" step inside intake** — the plain-language confirm
  summary *is* the preview; `--apply` is reversible (a restore manifest). A raw
  diff is available via `bootstrap.py --diff …`.
- **Smart stack suggestion from a plain-English project description** — PR #9.
- **Any change to the render / apply / adopt / restore core** — intake only
  builds argv; `render.planned_paths` is a new *additive* read-only helper.
- **Re-architecting `_flags.py`** — item 1 only *adds* a flag and *extracts*
  existing inline literals into named constants in the same file.
- **Pre-seeding intake answers from partial CLI flags** — `--interactive` is
  standalone-only in PR #8.
- **A richer existing-project detector** beyond the planned-file collision check
  and the cross-language manifest scan (e.g. loose-source-layout heuristics) —
  a possible follow-up.
- **A TUI / curses interface** — prompts are plain line-by-line `stdin.readline()`
  reads, no full-screen UI.
- **`SKILL.md` changes** (iter-5 fold, Claude 2-C) — `SKILL.md` documents the
  *agent-facing* flag surface. Intake is human-TTY-only and never auto-triggers
  for an agent (non-TTY) invocation, so `SKILL.md` needs no interactive-mode
  entry. Deliberate no-change, recorded so it is a decision, not an omission.

## Subsystem breakdown

### Bucket A — `_flags.py`: the `--interactive` flag + shared constants

`_flags.py` stays Python-3.6-compatible (plain `add_argument`, `re` is stdlib).
Changes:

- Add module-level constants: `LANGUAGES`, `PACKAGE_MANAGERS`,
  `GITHUB_REVIEW_MODES`, `PROJECT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")`.
- `add_flags` uses those constants in its `choices=` arguments (same lists).
- Add `--interactive` (`store_true`).
- `cli.py` imports `PROJECT_NAME_RE` from `_flags.py` instead of defining it;
  **remove `cli.py`'s now-unused `import re`** — `re` is referenced only at the
  current `PROJECT_NAME_RE` definition (`cli.py:14`), so the import becomes dead
  and ruff F401 would fail `make check`.

`test_shim_cli_help_consistency.py` continues to pass unchanged.

### Bucket B — `bootstrap_lib/intake.py` + the greenfield check

A new Python-3.12 module, imported **lazily** by `cli.py` inside `main()`. Public
surface:

```python
class IntakeAborted(Exception):
    """Raised when stdin hits EOF mid-flow (Ctrl-D, or an exhausted pipe)."""

def run_intake(stdin=None, stdout=None) -> "list[str] | None":
    """Guided greenfield setup. Returns an argv list on confirm, None on the
    user choosing 'cancel'. Raises IntakeAborted on EOF. stdin/stdout default
    to None and are resolved to sys.stdin/sys.stdout *inside* the function."""
```

Prompts read via `stdin.readline()` (mirroring the existing adopt flow's
`_prompt_one_file`, `cli.py:354`) — **not** the builtin `input()`, which ignores
an injected stream and would defeat the scripted-stdin test strategy. An empty
`readline()` return is EOF → `raise IntakeAborted`.

Every **numbered-menu** prompt (language, package manager, GitHub review,
apply/cancel) re-displays and re-asks on any input that is not a valid in-range
choice — a non-coder typing `5`, an empty line, or the word `python` instead of
`1` must not crash (`IndexError`) or pass a silently-wrong value; the literal
value (e.g. `python`) is also accepted as a friendlier alternative to the number
(iter-5 fold, Claude 2-A).

A small internal helper re-prompts on empty input for the **required free-text
answers that have no default** (`--github-owner`, `--github-repo`) — a guided
non-coder flow must not collect a blank and only hit a raw parser
`missing required args` error later. The output-directory question is **not** in
this set: it has a default (`../<project-name>`), so empty input accepts the
default. Deeper syntax validation stays with the parser; only the empty case is
caught here.

Question order and the flag each produces:

| Question | Flag produced |
|---|---|
| Project name (validated against `_flags.PROJECT_NAME_RE`, re-asked on failure) | `--project-name` |
| Language — numbered menu `1) python  2) nodejs  3) go` (re-asked on invalid input) | `--language` |
| Package manager (only if python) — `1) uv (recommended)  2) pip` (re-asked on invalid input) | `--package-manager` |
| GitHub auto-review — `1) none  2) claude  3) both-docs` (re-asked on invalid input; one-line note: non-`none` needs a GitHub repo + a one-time token/secret — exact steps print after apply) | `--github-review` |
| GitHub owner + repo (only if review != none; each re-asked if empty) | `--github-owner`, `--github-repo` |
| Add a smoke-test doc skeleton? | `--enable-smoke` |
| **Output directory** (asked last — see below) — default `../<project-name>` shown, one line of guidance ("a path for the new project folder; it will be created"); empty input accepts the default | `--out` |

The output-directory question is asked **last** (iter-4 fold, Claude F): the
greenfield check runs immediately after it, so a collision re-ask lands the user
right back on the question they just answered, not four steps back. *(Greenfield
Go + review `none` accepts the flag-CLI's bare-module-name `go.mod` fallback —
same as today; noted, not changed.)*

**Greenfield check — runs after the output-directory question.** Once `--out` and
all file-affecting answers exist, intake runs **two** checks against `--out`:

1. **Planned-file collision** — `render.planned_paths(...)` gives the exact set
   of paths the skill would write for the chosen config; intake checks each with
   `path.exists()` (no `render_all`, no context dict, no `cli` import).
2. **Cross-language project-manifest scan** — intake checks `--out` for any
   recognised manifest, **regardless of the selected language**:
   `pyproject.toml`, `setup.py`, `uv.lock`, `requirements*.txt`, `package.json`,
   `go.mod`. This catches an existing project in *any* supported language even
   when check 1 misses it — e.g. choosing `nodejs` for a folder holding only a
   `pyproject.toml` (iter-4 fold, Codex 1). This scan **replaces** the iter-3
   Python-only `detect.detect_package_manager` check, which was language-blind in
   the wrong direction. Each name is matched as a **file** (`path.is_file()`,
   not `exists()` — a *directory* named `package.json` must not false-positive);
   `requirements*.txt` is a **glob filtered to files** (`detect._first_requirements_match`
   is a reusable model — iter-5 fold, Codex 1 / Claude 1-D).

**Neither tripped → greenfield**: the run proceeds even if the folder holds
non-skill, non-manifest files (a `business-goals.md`, a `data/` dir, notes) —
untouched.

**Either tripped → existing project**: intake explains the folder already holds
a project, and **the message is language-aware** (`--mode=adopt` is Python-only
per `cli.py:116`):
- **Python** target → point at adopt-mode (`bootstrap.py --apply --mode=adopt
  --language python …`).
- **nodejs / go** target → do **not** suggest `--mode=adopt` (it would
  argparse-reject); explain the folder already contains a project and note that
  nodejs/go adoption is a planned follow-up.
Then intake re-asks the `--out` question only and re-runs both checks.

**Accepted limitation:** a folder holding loose source under non-skill names with
no manifest at all is a rare edge intake treats as greenfield; the skill writes
alongside, overwriting nothing. A richer code-layout detector is a follow-up.

### Bucket C — confirm gate

After the questions and the greenfield check, `intake.py` prints a plain-language
summary — e.g. *"This will bootstrap a new **python** project named
**my-project** into `../my-project`, with **both-docs** GitHub review. Note:
GitHub review needs a GitHub repo and a one-time token/secret — the apply output
will print the exact steps. Any files already in that folder are left
untouched."* — then asks `1) apply  2) cancel`.

The summary uses the generic *"any files already in that folder are left
untouched"* — it does **not** enumerate specific stray filenames (iter-4 fold,
Claude A: enumeration would need an unspecified `listdir`-and-cap step; the
generic line carries the same reassurance without the spec gap).

- `apply` → `run_intake` returns the argv with `--apply` appended.
- `cancel` → `run_intake` returns `None` → `main()` exits 0, no work.

No separate "preview (diff)" option — the summary is the preview, `--apply` is
reversible, and a diff is available via `bootstrap.py --diff …`.

### Bucket D — trigger, EOF / Ctrl-C handling, and re-parse wiring in `cli.py`

```python
def main(argv):
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Standalone-only: any extra argv token alongside --interactive is rejected.
    # A raw token-count check is deliberate — any other flag adds >=1 token, and
    # this guard runs before mode resolution so --restore can never be re-routed.
    if args.interactive and len(argv) > 1:
        sys.stderr.write("--interactive must be used on its own "
                         "(no other flags) in this version\n")
        return 2
    if _should_run_intake(argv, args):
        from bootstrap_lib import intake          # lazy import — mirrors the
        # adopt lazy-import already in cli.py; lets intake.py import from
        # _flags.py / render.py without an at-import cycle.
        try:
            intake_argv = intake.run_intake()
        except intake.IntakeAborted:
            # Ctrl-D mid-flow → cancel on a TTY; fail loud on a non-TTY.
            if sys.stdin is not None and sys.stdin.isatty():
                return 0
            sys.stderr.write("interactive mode needs an interactive terminal "
                             "or piped answers\n")
            return 2
        except KeyboardInterrupt:                 # Ctrl-C → clean cancel,
            sys.stderr.write("\ncancelled\n")     # not a raw traceback
            return 0
        if intake_argv is None:                   # user chose 'cancel'
            return 0
        args = parser.parse_args(intake_argv)
    # ... unchanged from here ...
```

`_should_run_intake(argv, args)` → True when `args.interactive` is set, OR when
`argv` is empty AND `sys.stdin` is a TTY. **Every** `sys.stdin.isatty()` check —
the auto-trigger test here and the TTY-vs-non-TTY branch in the `IntakeAborted`
handler above — is guarded with `sys.stdin is not None`: a detached process can
have `sys.stdin is None`, which must fall through cleanly rather than raise
`AttributeError` (iter-5 fold, Claude 1-F).

**Exit-code contract:**

| Outcome | `run_intake` | `main()` |
|---|---|---|
| Flow completes + `apply` | returns `argv` | re-parse → run pipeline |
| `cancel` chosen | returns `None` | exit 0 |
| EOF on a **TTY** (Ctrl-D) | raises `IntakeAborted` | exit 0 (cancel) |
| EOF on a **non-TTY** (empty pipe) | raises `IntakeAborted` | exit 2 + message |
| `KeyboardInterrupt` (Ctrl-C) | propagates | caught → exit 0 + "cancelled" |

A bare non-TTY invocation keeps today's `missing required args` error. The
re-parse through `_build_parser()` is a backstop.

### Bucket E — tests

| Test | Assertion |
|---|---|
| `test_intake.py::test_intake_python_greenfield_maps_to_argv` | Scripted answers for a greenfield python+uv project produce the expected argv (ending `--apply`). |
| `test_intake.py::test_intake_nodejs_skips_package_manager_question` | nodejs/go → no package-manager question; no `--package-manager` in argv. |
| `test_intake.py::test_intake_both_docs_collects_owner_repo` | `both-docs` → `--github-review=both-docs --github-owner … --github-repo …`. |
| `test_intake.py::test_intake_reprompts_on_bad_project_name` | An invalid project name is re-asked; a valid follow-up is accepted. |
| `test_intake.py::test_intake_reprompts_on_empty_required_answer` | An empty `--github-owner` / `--github-repo` is re-asked, not passed through blank. |
| `test_intake.py::test_intake_reprompts_on_bad_menu_choice` | An out-of-range or non-numeric numbered-menu input (`5`, an empty line) is re-asked; a valid follow-up is accepted; the literal value (`python`) is also accepted. |
| `test_intake.py::test_intake_outdir_default_is_parent_project_name` | Accepting the default at the output-dir prompt yields `--out ../<project-name>`. |
| `test_intake.py::test_intake_cancel_returns_none` | Choosing `cancel` makes `run_intake` return `None`. |
| `test_intake.py::test_intake_eof_raises_intake_aborted` | An EOF mid-flow raises `IntakeAborted`, not a traceback. |
| `test_intake.py::test_intake_colliding_outdir_python_routes_to_adopt` | A Python run, `--out` with a `Makefile` → collision → adopt-mode pointer; re-asks `--out`. |
| `test_intake.py::test_intake_colliding_outdir_nodejs_no_adopt_pointer` | A nodejs run with a colliding `--out` → existing-project message **without** a `--mode=adopt` suggestion. |
| `test_intake.py::test_intake_cross_language_manifest_routes_to_existing` | A **nodejs** run, `--out` holding only a `pyproject.toml` → manifest scan trips → existing-project routing (proves the scan is language-agnostic). |
| `test_intake.py::test_intake_collision_on_review_gated_file` | `--out` with `docs/SMOKE.md` + smoke answered yes → collision detected (proves the check runs after the smoke question). |
| `test_intake.py::test_intake_outdir_with_noncode_files_is_greenfield` | `--out` with only `business-goals.md` + a `data/` dir → greenfield, no routing. |
| `test_render.py::test_planned_paths_filters_by_review_smoke` | `planned_paths` includes `claude-review.yml` only for non-`none` review, `codex-github-review-setup.md` only for `both-docs`, `docs/SMOKE.md` only when smoke enabled. |
| `test_render.py::test_planned_paths_filters_by_package_manager` | `planned_paths` includes `.python-version` only for uv, `requirements-dev.txt` only for pip. |
| `test_render.py::test_planned_paths_equals_render_all_keys` | Parameterised over all shipped languages × review modes × smoke on/off × Python package managers (uv, pip, **and `None`** → pip-normalized): `planned_paths(cfg) == set(render_all(context, language).keys())` — locks the helper to the renderer so a future filter added to one but not the other is caught (iter-4 fold Codex 2 / Claude D; iter-5 fold Codex 3 / Claude 1-E adds the `None` case). |
| `test_bootstrap_cli.py::test_interactive_apply_matches_flag_driven_apply` | End-to-end: a scripted interactive `apply` and the equivalent flag-driven apply produce byte-identical relative file trees. |
| `test_bootstrap_cli.py::test_interactive_apply_preserves_existing_nonskill_files` | `--out` pre-seeded with `business-goals.md` + `data/raw.txt`; a scripted interactive apply leaves their bytes unchanged and adds only planned skill files (the apply-level proof of the "existing files left untouched" promise — iter-5 fold, Codex 2). |
| `test_bootstrap_cli.py::test_intake_cancel_writes_nothing` | `main()` on a cancelled intake → returns 0, target dir absent/empty, no restore manifest. |
| `test_bootstrap_cli.py::test_bare_main_on_tty_enters_intake` | `main([])` with a fake-TTY stdin enters intake (no `missing required args`). |
| `test_bootstrap_cli.py::test_no_args_non_tty_keeps_missing_args_error` | Non-TTY stdin + empty argv → `main` returns 2 with the existing missing-args error. |
| `test_bootstrap_cli.py::test_interactive_flag_routes_through_intake` | `--interactive` with scripted stdin runs intake then the normal pipeline. |
| `test_bootstrap_cli.py::test_interactive_with_other_flag_exits_2` | `--interactive --apply` (or any pairing) → exit 2 before intake. |
| `test_bootstrap_cli.py::test_interactive_non_tty_empty_stdin_exits_2` | `--interactive` with an empty non-TTY stdin → exit 2, clean message. |
| `test_bootstrap_cli.py::test_interactive_keyboardinterrupt_exits_clean` | A `KeyboardInterrupt` during intake → `main` exits 0 with "cancelled", no traceback. |
| `test_shim_cli_help_consistency.py` | Continues to pass — `--interactive` flows through the single-source `_flags.py`. |
| All existing `test_bootstrap_cli.py` tests | Continue to pass unchanged — intake is additive. |

## Architecture decisions

- **Intake is a front-end, not a new mode.** It produces argv and re-feeds the
  existing parser. Building an `args` namespace directly would create a second,
  unvalidated path; rejected.
- **Greenfield-only for PR #8 (iter-1 fold).** Adopt-mode is already an
  interactive per-file flow and is Python-only. Greenfield-vs-existing is decided
  by *two* checks — a planned-file collision **and** a cross-language
  project-manifest scan — so an existing project in *any* supported language is
  excluded even when the user picks a different language, while a folder with
  just business notes or data is correctly greenfield. The existing-project
  message is language-aware (adopt-mode pointer for Python only). **(d)-class
  decision flagged for the human-approval gate** — accept greenfield-only, or
  expand PR #8 to also wrap adopt (larger).
- **Collision check uses a new read-only `render.planned_paths` helper**, run
  after all file-affecting questions; a test locks it equal to
  `render_all`'s output keys so the two cannot drift.
- **`run_intake` outcomes:** `argv` / `None` (cancel) / `IntakeAborted` on EOF;
  `main()` maps EOF to exit 0 on a TTY and exit 2 on a non-TTY, and catches
  `KeyboardInterrupt` as a clean cancel.
- **Prompts use `stdin.readline()`, not `input()`** — `input()` ignores an
  injected stream; `readline()` on the injected `stdin` is what makes the
  scripted-stdin tests work and mirrors the existing adopt prompt.
- **`intake.py` is a separate 3.12 module, lazily imported** by `cli.py`. Shared
  constants live in 3.6-safe `_flags.py`.
- **`--interactive` is standalone-only.** Combined with other flags → exit 2.
- **`stdin`/`stdout` default to `None`, resolved to `sys.*` inside `run_intake`.**
- **No-default required answers are re-prompted in intake** (empty
  `--github-owner`, `--github-repo`); `--out` carries a default instead.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Intake hangs on a prompt in a non-TTY context | Auto-trigger requires `isatty()`; explicit `--interactive` on an empty non-TTY hits EOF → `IntakeAborted` → exit 2. |
| EOF on a TTY (Ctrl-D) misclassified as a hard error | `main()` branches on `isatty()` — TTY EOF → 0, non-TTY EOF → 2. |
| Ctrl-C gives a non-coder a raw traceback | `main()` catches `KeyboardInterrupt` → exit 0 + "cancelled". |
| `--interactive` re-routes a load-bearing mode (`--restore`) into a Q&A | `--interactive` standalone-only → exit 2 if combined. |
| Collision check misses a review/smoke-gated file → raw collision error on apply | Check runs *after* all file-affecting answers, via `render.planned_paths`; `test_planned_paths_equals_render_all_keys` locks the helper to the renderer so it cannot silently drop a file. |
| Intake scaffolds over an existing project in another language | The greenfield check's manifest scan is language-agnostic — `pyproject.toml`/`package.json`/`go.mod`/`uv.lock`/`requirements*.txt`/`setup.py` in `--out` route to the existing-project path regardless of the chosen language. Test `test_intake_cross_language_manifest_routes_to_existing`. |
| Existing-project message suggests `--mode=adopt` for nodejs/go (Python-only) | Language-aware message: adopt pointer for Python only. |
| A non-coder types a bare `--out` → project written into the cwd (often the skill repo) | Output-dir question defaults to `../<project-name>` + one line of guidance. |
| `cli.py`'s `import re` becomes dead → ruff F401 | Bucket A removes it in the same change. |
| A folder with loose source but no manifest is treated as greenfield | Accepted, documented limitation; the skill overwrites nothing; richer detector is a follow-up. |
| GitHub-review hidden setup surprises the user | Intake's review question + confirm summary carry a one-line note; apply output prints exact steps. |
| New flag drifts shim vs cli help | `_flags.py` single-source + `test_shim_cli_help_consistency.py`. |

## Verification (acceptance criteria)

### Phase 1 — plan
- [ ] Plan converges (no importance-3 findings in the Codex + Claude reviews).
- [ ] Mandatory human-approval gate completed (incl. the greenfield-only
      (d)-decision and the no-preview confirm-gate decision).

### Phase 2 — implementation gates
1. Draft Implementation PR on branch `feat/skill-pr8-interactive-intake`.
2. Focused commits land in order, **tests co-located with the code they
   exercise**: (i) `_flags.py` flag + constants + `cli.py` `import re` removal;
   (ii) `render.planned_paths` + `test_render.py::test_planned_paths_*`;
   (iii-a) `intake.py` + `test_intake.py`; (iii-b) `cli.py` trigger/EOF/Ctrl-C
   wiring + the new `test_bootstrap_cli.py` cases; (iv) the four `BACKLOG.md`
   entries (a clearly-labelled PR-#7-adopt-mode-trial cleanup commit, after a
   dedup check against existing `BACKLOG.md` content); (v) docs. *(iii) is split
   into (iii-a)/(iii-b) — iter-4 fold,
   Claude C: `intake.py` is independently testable via `run_intake` with
   scripted stdin, so it does not need the cli wiring in the same commit.*
3. Per-commit Tier-1 review (same AI as implementer) — no importance-3 findings.
4. `make check` passes (full pytest + ruff).
5. New `test_intake.py` + `test_render.py::test_planned_paths_*` (incl. the
   `render_all`-keys equivalence test) pass; `test_shim_cli_help_consistency.py`
   passes; the interactive-vs-flag-driven equivalence test passes.
6. Every pre-existing `test_bootstrap_cli.py` test still passes unchanged.
7. **Manual greenfield intake smoke-walk**: run `./venv/bin/python bootstrap.py`
   (the venv interpreter — `python3` may be the macOS 3.9 and never reach intake)
   on a terminal, answer for a greenfield python project, confirm the summary
   reads clearly, choose `apply`, verify the result matches a known-good
   flag-driven run. Repeat once choosing `both-docs` (the GitHub-setup note
   appears) and once pointing `--out` at a folder holding a stray `Makefile`
   (the adopt-mode routing fires).
8. PR ready-for-review triggers the Tier-2 bots; findings triaged.

## Iteration log (this plan)

| Iter | Findings | Verdict |
|---|---|---|
| 1 (codex) | 3 imp-3 + 3 imp-2 | do not implement yet |
| 1 (claude) | 2 imp-3 + 4 imp-2 + 4 imp-1 | needs another iteration |
| 1-fold | All (a)-folded. **(d)-class decision**: intake scoped greenfield-only. |
| 1.5 (user direction) | "Greenfield" = collision, not folder emptiness | Folded |
| 1.5 consistency | 3 stale "non-empty" references | Fixed |
| 2 (codex) | 2 imp-3 + 3 imp-2 | do not implement yet |
| 2 (claude) | 2 imp-3 + 2 imp-2 + 1 imp-1 | needs another iteration |
| 2-fold | All (a)-folded. Collision check moved after all file-affecting questions via `render.planned_paths`; `run_intake` four outcomes; "preview" dropped; `stdin`/`stdout` default `None`. |
| 2.5 consistency | 1 "all four" wording imprecision | Fixed |
| 3 (codex) | 1 imp-3 + 3 imp-2 | do not implement yet |
| 3 (claude) | 1 imp-3 + 5 imp-2 + 2 imp-1 | needs another iteration |
| 3-fold | All (a)-folded. Package-manager-signal check added; language-aware existing-project message; required free-text re-prompts; output-dir default; `KeyboardInterrupt` caught; `import re` removal; tests co-located; equivalence + cancel-no-writes tests; `BACKLOG.md` made an explicit deliverable. |
| 3.5 consistency | 1 contradiction (`--out` default vs re-prompt-on-empty) | Fixed — `--out` has the default; only owner/repo re-prompt |
| 4 (codex) | 1 imp-3 + 4 imp-2 | do not implement yet |
| 4 (claude) | 0 imp-3 + 4 imp-2 + 2 imp-1 | ready after minor edits |
| 4-fold | All (a)-folded. The Python-only PM-signal check replaced by a **language-agnostic project-manifest scan** (catches an existing project in any language even when the user picks a different one — Codex's imp-3); `planned_paths ≡ render_all`-keys equivalence test added; `docs/usage.md` greenfield-definition update added to scope; smoke command corrected to `./venv/bin/python`; `BACKLOG.md` entries given the required field shape; confirm-summary "untouched files" line made generic (no enumeration); `input()` → `stdin.readline()`; commit (iii) split into (iii-a)/(iii-b); `RENDER_MAP`→actual map names; output-dir question moved last. |
| 5 (codex) | 0 imp-3 + 4 imp-2 | ready after minor edits |
| 5 (claude) | 0 imp-3 + 3 imp-2 + 4 imp-1 | ready after minor edits |
| 5-fold | **Loop converged — 0 imp-3 from both reviewers.** All imp-2/imp-1 (a)-folded: manifest scan specified as `is_file()` + glob-to-files (no directory false-positive); apply-level "existing non-skill files untouched" test added; `planned_paths` normalizes `None`→pip and the equivalence test covers the `None` case; numbered-menu prompts re-ask on invalid input; `docs/usage.md` item-10 split (intake's two-check definition documented only in the new interactive section; the stale adopt-mode / uv-detection "no files" phrasing is just dropped, not replaced with intake's definition); `SKILL.md` no-change recorded in NOT-in-scope; `sys.stdin is not None` guard added; commit (iv) relabelled a PR-#7-cleanup commit + dedup check; `cli.py:116`→`119-122` line-ref corrected. |
| 6 (tier-2, claude) | 0 imp-3 + 3 imp-2 + 1 imp-1 (PR-#20 review) | ready after minor edits — see iter-6 triage |
| 6 (tier-2, codex) | auto-skipped — PR #20 diff is entirely `.md` (the documented Codex doc-only-PR skip); the plan already received 5 Codex reviews in the loop | n/a |
| 6 triage | Claude Tier-2 PR-#20: 1 (a)-fold — the PR #20 *description* was corrected (the four adopt-mode `BACKLOG.md` cleanup entries are the implementation PR's deliverable per Scope item 8, not this plan PR; this plan PR's only `BACKLOG.md` change is the PR #9 entry). 3 (c)-rejects — see Evidence table. No plan-body change. |

## Evidence table — what was folded and where

| Source | Finding (one-line) | Triage | Where in plan |
|---|---|---|---|
| iter-1 / iter-2 / iter-3 findings | (see prior fold rows above) | **(a) fold** | Folded across Context, Scope, Buckets A-E, Architecture, Risks. |
| Codex 1 (iter-4) | greenfield check is language-blind — picking nodejs against a folder with only `pyproject.toml` is treated as greenfield | **(a) fold** | Greenfield check 2 replaced with a **cross-language project-manifest scan** (`pyproject.toml`/`setup.py`/`uv.lock`/`requirements*.txt`/`package.json`/`go.mod`, language-agnostic). Context, Bucket B, Architecture, Risks, test `test_intake_cross_language_manifest_routes_to_existing`. |
| Codex 2 / Claude D (iter-4) | `planned_paths` tests sample filters but never lock `planned_paths == render_all`-keys | **(a) fold** | New `test_render.py::test_planned_paths_equals_render_all_keys` parameterised over every shipped config. Scope 2, Bucket E, Risks. |
| Codex 3 (iter-4) | `docs/usage.md` still teaches "greenfield = no files in target" | **(a) fold** | Scope item 10 extended to update the stale `docs/usage.md` greenfield wording. |
| Codex 4 (iter-4) | manual smoke uses `python bootstrap.py` despite the 3.12 caveat | **(a) fold** | Phase-2 step 7 + the Context example use `./venv/bin/python bootstrap.py`. |
| Codex 5 (iter-4) | the four `BACKLOG.md` entries lack the repo's required field shape | **(a) fold** | Lessons section now gives each entry's *why parked* / *trigger* / *rough effort*. |
| Claude A (iter-4) | confirm-summary "existing files (`business-goals.md`) untouched" enumeration has no spec | **(a) fold** | Bucket C summary uses a generic "any files already in that folder are left untouched" — no per-file enumeration. |
| Claude B (iter-4) | NOT-in-scope says `input()` but `run_intake(stdin=…)` needs `stdin.readline()` | **(a) fold** | NOT-in-scope + Bucket B specify `stdin.readline()`-based prompts; `input()` removed. |
| Claude C (iter-4) | Phase-2 commit (iii) too large to be independently reviewable | **(a) fold** | Commit (iii) split into (iii-a) `intake.py`+tests / (iii-b) `cli.py` wiring+tests. |
| Claude E (iter-4) | Critical-files cites a non-existent `RENDER_MAP` | **(a) fold** | Replaced with `SHARED_TEMPLATE_MAP` + `LANGUAGE_TEMPLATE_MAPS`. |
| Claude F (iter-4) | output-dir question asked mid-flow but re-asked after the last question | **(a) fold** | Output-dir question moved to last, immediately before the greenfield check. Bucket B question table. |
| Codex 1 / Claude 1-D (iter-5) | manifest scan unspecified — `exists()` would false-positive on a directory named `package.json`; `requirements*.txt` is a glob | **(a) fold** | Bucket B: manifest names matched with `is_file()`; `requirements*.txt` is a glob filtered to files. |
| Codex 2 (iter-5) | "existing non-skill files untouched" promise has no apply-level test | **(a) fold** | New `test_interactive_apply_preserves_existing_nonskill_files` — asserts pre-seeded files' bytes unchanged after apply. |
| Codex 3 / Claude 1-E (iter-5) | `planned_paths` equivalence test omits Python `package_manager=None` (which `render_all` normalizes to pip) | **(a) fold** | `planned_paths` normalizes `None`→pip; equivalence test parameterised to include `None`. Scope 2, Bucket E. |
| Codex 4 (iter-5) | the four adopt-mode `BACKLOG.md` entries are scope-mixed into an intake PR | **(a) fold** | Committed as a clearly-labelled "PR #7 adopt-mode-trial cleanup" commit (iv), after a dedup check against `BACKLOG.md`. Scope 8, Phase 2 gate 2. |
| Claude 2-A (iter-5) | invalid numbered-menu input handling unspecified (crash / silently-wrong value) | **(a) fold** | Bucket B: every numbered-menu prompt re-asks on invalid input; the literal value is also accepted. Test `test_intake_reprompts_on_bad_menu_choice`. |
| Claude 2-B (iter-5) | item-10 docs rewording would import intake's broad greenfield definition into flag-driven adopt/uv sections that use narrower notions | **(a) fold** | Scope item 10 split — intake's definition only in the new interactive section; stale adopt/uv "no files" phrasing just dropped. |
| Claude 2-C (iter-5) | `SKILL.md` not considered | **(a) fold** | NOT-in-scope records `SKILL.md` unchanged — agent-facing flag surface; intake never auto-triggers for non-TTY agent invocations. |
| Claude 1-F (iter-5) | `sys.stdin` can be `None` in a detached process → `AttributeError` | **(a) fold** | Bucket D: `isatty()` guarded with `sys.stdin is not None`. Risks. |
| Claude 1-G (iter-5) | `cli.py:116` line-ref imprecise; test-stub robustness | **(a) fold** | Critical-files line-ref corrected to `cli.py:119-122`; test note. |
| Claude Tier-2 PR-#20 1 | Scope item 9 marks `test_intake.py` "(new)" but tests span existing files too | **(c) reject — premise wrong** | Scope item 9's "Where" column + Bucket E already attribute every test to `test_intake.py` (new) / `test_render.py` / `test_bootstrap_cli.py` via the `test_X.py::` row prefixes — no ambiguity. |
| Claude Tier-2 PR-#20 2 | PR #20 *description* read as if this plan PR files the 4 adopt-mode `BACKLOG.md` entries | **(a) fold** | PR #20 description corrected — those four are the implementation PR's deliverable (Scope item 8); this plan PR's only `BACKLOG.md` change is the PR #9 entry. No plan-body change. |
| Claude Tier-2 PR-#20 3 | Phase-2 step 7 `./venv/bin/python` assumes the venv exists | **(c) reject — moot** | Phase-2 gates are ordered: gate 4 (`make check`) runs before step 7 and requires the venv; `./venv/bin/python` is the repo-standard interpreter (CLAUDE.md). |
| Claude Tier-2 PR-#20 4 | greenfield-definition formatting ("neither/nor" vs "**not**") inconsistent | **(c) reject** | Two distinct sentences — the positive two-part definition, then the "not folder emptiness" clarification; not an inconsistency, no readability problem. |

## Implementation log (this PR)

| short-sha | what landed | deviations from plan, or 'none' | issues faced, or 'none' |
|---|---|---|---|
| b95a1a7 | (i) `--interactive` flag + `LANGUAGES`/`PACKAGE_MANAGERS`/`GITHUB_REVIEW_MODES`/`PROJECT_NAME_RE` constants extracted into `_flags.py`; `cli.py` imports `PROJECT_NAME_RE`, drops the now-dead `import re` | none (Bucket A) | none — Tier-1 clean |
| 18291d4 | (ii) `render.planned_paths()` helper + `tests/test_render.py` locking `planned_paths == set(render_all-keys)` across every language × review mode × smoke × pm (incl. `None`) | none (Bucket B / Scope item 2) | Tier-1 imp-2 (`planned_paths` doesn't validate `github_review_mode`) **rejected** — it deliberately mirrors `render_all`, which also doesn't validate; one imp-1 test tweak folded via `--amend` |
| 7c6c335 | (iii-a) `bootstrap_lib/intake.py` + `tests/test_intake.py` — guided greenfield flow: question sequence, two-check greenfield detection (planned-file collision + cross-language manifest scan), argv builder ending `--apply`, `IntakeAborted` on EOF; 16 tests | none (Buckets B/C) | Tier-1 imp-2 (no explicit in-loop cancel on the `--out` re-ask) **parked to BACKLOG**; 2 imp-1 (return type hint, directory-named-manifest false-positive test) folded via `--amend` |
| d5a10d6 | (iii-b) wired the intake trigger into `cli.main()` — `_should_run_intake` + standalone `--interactive` guard + EOF/Ctrl-C exit-code handling + re-parse backstop; 8 `test_bootstrap_cli.py` tests | none (Bucket D) | Tier-1 imp-2 (standalone-guard message dropped the plan's "in this version" tail — plan-impl drift) folded via `--amend` |
| 976a02b, 677e9a1 | (iv) the BACKLOG entries; (v) `docs/usage.md` interactive-mode section + stale-greenfield-wording fixes + `README.md` pointer | none (Scope items 8, 10) | N/A — trivial docs commits, per-commit Tier-1 skipped per CONTRIBUTING.md |

## Lessons surfaced (this PR)

The four adopt-mode quality items below were observed while bootstrapping
`call-details`. They are **Scope item 8** — appended to `BACKLOG.md` (commit iv)
with the repo's required *why parked* / *trigger* / *rough effort* fields:

| Backlog entry | Why parked | Trigger to pick up | Rough effort |
|---|---|---|---|
| Adopt-mode writes greenfield smoke placeholders (`src/main.py`, `tests/test_smoke.py`) into a project with real code | Surfaced during the `call-details` adopt trial; adopt-mode should not emit greenfield-only scaffold into an existing project | Next adopt-mode change, or a user reports stray `src/main.py` after an adopt run | ~1-2 h — gate the smoke/`src/main.py` emit on greenfield vs adopt |
| Adopt-mode's `Makefile` `run` target is hardcoded to `src/main.py` | The skill's `Makefile` assumes the greenfield layout; an adopted real project has a different entry point | Same as above, or a user reports `make run` broken after adopt | ~1 h — detect the real entry point, or leave `run` for the user to set |
| `make install-hooks` needs `pre-commit` but adopt-mode does not add it to the target's real dev-dependency group | The skill ships `.pre-commit-config.yaml` + the target but not the dep; surfaced on `call-details` | First adopt user runs `make install-hooks` and it fails | ~1 h — adopt-mode appends `pre-commit` to the detected dev-dependency group |
| `AGENTS.md` collided with the target's `.gitignore` | `call-details` ignored `AGENTS.md` as Codex-CLI residue; the skill's `AGENTS.md` is a tracked deliverable | An adopt user's `.gitignore` already lists `AGENTS.md` | ~30 min — adopt-mode detects + warns, or documents the conflict |

## Critical files to read before each iter's review

- `bootstrap.py` — the 3.6-compatible shim.
- `bootstrap_lib/_flags.py` — flag single-source (gains `--interactive` + the
  extracted constants).
- `bootstrap_lib/cli.py` — `main()`, `_build_parser()`, `_resolve_mode()`,
  `PROJECT_NAME_RE` (`cli.py:14`, moves out; `import re` then removed);
  `--mode=adopt` Python-only (the language check is `cli.py:119-122`); the adopt prompt `_prompt_one_file`
  (`cli.py:354`, the `stdin.readline()` pattern intake mirrors); adopt
  lazy-import (~`cli.py:610`).
- `bootstrap_lib/render.py` — `SHARED_TEMPLATE_MAP`, `LANGUAGE_TEMPLATE_MAPS`,
  `_emit_in_mode`, `_emit_python_in_pm_mode`, `render_all`; gains the read-only
  `planned_paths` helper.
- `bootstrap_lib/detect.py` — `has_collisions`; `detect_package_manager`
  (reference — the iter-3 PM-signal check it backed is superseded by the
  language-agnostic manifest scan).
- `tests/test_bootstrap_cli.py` — the in-process `run_cli` test pattern.
- `tests/test_shim_cli_help_consistency.py` — byte-equal help enforcement.
- `docs/usage.md` — interactive mode docs + the stale greenfield wording to fix.
