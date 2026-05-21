# Skill bugfix — config-shadowing: consolidate ruff/pytest config into `pyproject.toml`

## Context

Dogfooding `--mode=adopt` into the real `call-details` project surfaced a
silent, damaging bug.

The skill ships ruff's configuration as a **standalone file**
(`languages/python/ruff.toml.tmpl`) and pytest's as a standalone
`languages/python/pytest.ini.tmpl`. Most existing Python projects —
`call-details` included — keep that configuration **inside `pyproject.toml`**
(`[tool.ruff]`, `[tool.pytest.ini_options]`).

When adoption mode analyzed `call-details`, it looked for a file literally
named `ruff.toml`, found none, and classified it under rule **(a)** —
"missing AND not ignored → `WRITE`, `manual_review_needed=False`". So the skill
**silently wrote a `ruff.toml`** with no owner prompt.

ruff's precedence rule: *when both `ruff.toml` and `pyproject.toml` exist in a
directory, `ruff.toml` wins and `[tool.ruff]` in `pyproject.toml` is ignored
entirely* — ruff does not merge them. pytest behaves the same way
(`pytest.ini` overrides `[tool.pytest.ini_options]`).

Result in `call-details`: the project's deliberate, hand-tuned ruff config
(its `ignore = ["RUF001","RUF002","RUF003"]` ambiguous-unicode exemption, with
an explicit "this project handles RU/UZ text everywhere" comment) went dead.
~107 false-positive errors lit up and `make lint` turned red. **A secondary
defect** (referred to below as the "`known-first-party` defect"): the skill's
`ruff.toml` set `known-first-party = ["call_details"]` — a package that does
not exist (the project's real packages are `boxette_calls` / `boxette_chats`);
the value was derived mechanically from the repo folder name.

### Why the analyzer missed it

The per-file heuristic in `bootstrap_lib/adopt.py::recommend_policy` decides by
**path collision** — "does a file at this exact path exist?" A new file at an
unoccupied path looks 100% safe to `WRITE`. The analyzer never asks "does
writing this file change the behavior of a tool whose config currently lives in
a *different* file?"

The irony: rule **(g)** already detects `[tool.*]` in the target's
`pyproject.toml` and carefully **SKIPs** `pyproject.toml` so it is not
overwritten — and then rule (a) writes `ruff.toml`, which nullifies exactly the
`[tool.ruff]` block rule (g) just protected. The two rules work against each
other.

### Root cause vs. patch

The root cause is the **config layout**, not the analyzer. The skill always
ships a `pyproject.toml` anyway, so a separate `ruff.toml` is a *second* config
file that buys nothing for this skill's audience (single small projects — a
standalone `ruff.toml` only earns its keep in monorepos, where ruff supports
nested per-directory configs). Consolidating ruff + pytest config **into
`pyproject.toml`** (the dominant post-PEP-518/621 convention) removes the
standalone files the *skill* ships.

That alone does not make shadowing impossible: the **target project** may own
its own standalone `ruff.toml` / `.ruff.toml` / `pytest.ini`, and after this
change the analyzer no longer walks those paths at all (it only inspects
*planned* files). Two distinct shadow shapes survive:

- target owns a standalone config **and has no `pyproject.toml`** — adoption
  writes a fresh skill `pyproject.toml` whose `[tool.*]` is shadowed by the
  target's standalone file;
- target owns a standalone config **and already has a `pyproject.toml`** with
  `[tool.*]` — the standalone file shadows the target's *own* `[tool.*]`
  (the exact live `call-details` shape: `[tool.pytest.ini_options]` in
  `pyproject.toml` plus a top-level `pytest.ini` that wins).

So the fix has **two halves**:

1. **Greenfield + the files the skill ships** — consolidate into `pyproject.toml`;
   delete the standalone templates (this plan, Bucket A).
2. **Adoption + files the *target* owns** — a top-level shadow scan that
   **always** names any target-owned `ruff.toml` / `.ruff.toml` / `pytest.ini`
   in the report and states it overrides the matching `[tool.*]` table —
   regardless of whether a `pyproject.toml` exists. When adoption would *write*
   a fresh `pyproject.toml` over such a shadow, it additionally **escalates
   that write to a manual-review decision** so the `--non-interactive` CI path
   fails loud instead of going green with dead config (this plan, Bucket B).
   The skill never modifies or deletes a target-owned file.

### Pre-coding statements

**Regression safety.**
- *Auto-testable:* the rendered `pyproject.toml` content (`[tool.ruff]` /
  `[tool.pytest.ini_options]` sections present, correct values); `planned_paths`
  no longer lists `ruff.toml` / `pytest.ini`; the Python generated-project smoke
  tests (`make check` green in a bootstrapped project — exercises ruff + pytest
  reading config from `pyproject.toml`); the adoption-mode smoke tests.
- *New coverage:* (a) adoption into a target with an existing `pyproject.toml`
  containing `[tool.ruff]` does not produce a shadowing file; (b) the shadow
  scan detects and the report names a target-owned `ruff.toml` / `.ruff.toml` /
  `pytest.ini` — unit-level escalation + report tests are **parameterized over
  all three filenames**, in both the "no `pyproject.toml`" and "existing
  `pyproject.toml`" target shapes; (c) the load-bearing escalation — a target
  that owns a standalone config and has **no** `pyproject.toml`, run under
  `--auto-accept-recommendations --non-interactive`, **must exit 2** (not 0),
  because the `pyproject.toml` write is escalated to `manual_review_needed=True`.
- *Not auto-testable:* nothing material — the change is mechanical and fully
  covered by render + smoke + adopt-engine tests.

**Outcome measurement.** No business metric applies — internal bugfix. The
success signal is dogfooding: re-running `--mode=adopt` into a project that
keeps ruff/pytest config in `pyproject.toml` no longer creates a shadowing file,
and a project that owns a **top-level `ruff.toml` / `.ruff.toml` / `pytest.ini`**
gets that file named in the report (and, when a fresh `pyproject.toml` would be
written over it, a manual-review stop so CI fails loud). Coverage is scoped to
those three top-level filenames — `tox.ini` / `setup.cfg` / nested configs are
explicitly out of scope (Bucket E). Verified by the adoption-mode smoke tests.

## Scope

### IN scope

| # | Item |
|---|---|
| 1 | Move `ruff.toml.tmpl` content into `pyproject.toml.tmpl` as `[tool.ruff]` / `[tool.ruff.lint]` / `[tool.ruff.format]` tables. Drop the unused `[lint.isort] known-first-party` key (AD-3). |
| 2 | Move `pytest.ini.tmpl` content into `pyproject.toml.tmpl` as a `[tool.pytest.ini_options]` table. |
| 3 | Delete `languages/python/ruff.toml.tmpl` and `languages/python/pytest.ini.tmpl`; remove their two keys from `PYTHON_TEMPLATE_MAP` in `render.py`; remove the now-dead `project_import_name` key from `cli.py::_build_context`. |
| 4 | Add a top-level **shadow scan** for adoption mode: detect target-owned `ruff.toml` / `.ruff.toml` / `pytest.ini`; **always** name detected files in the report with their override relationship; when a fresh `pyproject.toml` would be written over a shadow, **escalate that write to `manual_review_needed=True`** (Bucket B, B1). Also add the B2 three-way `pyproject.toml`-SKIPped advisory — rule (g) / parseable-trivial / malformed-TOML branches (Bucket B, B2). |
| 5 | Update the test files that reference `ruff.toml` / `pytest.ini` — including naming explicit replacement fixture files so displaced rule-(b)/(c) coverage is preserved (Bucket C). |
| 6 | Add tests: `[tool.ruff]` + `[tool.pytest.ini_options]` present in rendered `pyproject.toml`; `ruff.toml` / `pytest.ini` absent from `planned_paths`; shadow-scan escalation + advisory parameterized over all three filenames and both target shapes; the non-interactive exit-2 escalation; the adoption no-shadow contract (Bucket C). |
| 7 | Update docs whose planned-file counts or recommendation-report / CI-contract examples change (`docs/usage.md`); add the advisory + escalation behavior to the usage example (Bucket D). |
| 8 | Add `BACKLOG.md` entries (each with an explicit trigger) for the parked items: TOML section-merge, `tox.ini`/`setup.cfg` shadow sources, nested (non-top-level) config scan, skill-repo own-config migration, Node/Go config-file shadowing (Bucket E). |

### NOT in scope

| Item | Why / where it goes |
|---|---|
| TOML **section-merge** for adoption-into-existing-`pyproject.toml` (auto-add `[tool.ruff]` when absent, with owner confirmation) | Deferred — `BACKLOG.md` entry created by Scope #8. The existing rules + the B1 escalation + the B2 advisory give a safe, *informed*, fail-loud outcome (AD-2); section-merge is an enhancement, not a correctness requirement. |
| `tox.ini` / `setup.cfg` as pytest-config shadow sources | Lower-priority than `pytest.ini`; rarer. `BACKLOG.md` entry (Scope #8). The Context, Outcome, and Verification wording is scoped to the three top-level filenames so nothing overclaims. |
| **Nested** (non-top-level) standalone configs (monorepo sub-directory `ruff.toml`s) | The scan is **top-level (`target_root`) only** (AD-1). Recursive scanning risks surfacing sensitive nested path names and noisy partial shadows. `BACKLOG.md` entry (Scope #8). |
| Migrating the **skill repo's own** `ruff.toml` / `pytest.ini` to its `pyproject.toml` | Separate concern — the skill repo is not a bootstrapped artifact; changing its lint config could surface new lint errors on the skill's own code mid-PR. `BACKLOG.md` entry (Scope #8); flagged in the approval summary. |
| Node / Go config-file shadowing | The skill ships `biome.json` (Node) and `.golangci.yml` (Go). Biome also discovers `biome.jsonc`; `golangci-lint` also discovers `.golangci.{yaml,toml,json}` — so a target-owned *alternate-extension* config **can** shadow the skill's file. This PR scopes the shadow fix to Python (where the bug actually bit); Node/Go shadow handling is parked — `BACKLOG.md` entry (Scope #8). |
| Removing the stale `pytest.ini` from the live `call-details` repo | Work in the `call-details` repo, not the skill (AD-5). Listed under "Post-PR human follow-up", not Verification — the implementation session must not edit `call-details`. |

## Subsystem breakdown

### Bucket A — Consolidate greenfield config into `pyproject.toml`

`pyproject.toml.tmpl` currently branches on `pm` (`uv` vs `pip`) for the
dependency section only. The ruff + pytest tables are package-manager-agnostic
and are added **unconditionally** (outside the `{% if pm %}` branch).

Source content to migrate (semantics-preserving):

`ruff.toml.tmpl` → `pyproject.toml`:
- top-level `line-length`, `target-version`, `extend-exclude` → `[tool.ruff]`
- `[lint]` (`select`, `ignore`) → `[tool.ruff.lint]`
- `[format]` (`quote-style`, `indent-style`) → `[tool.ruff.format]`
- `[lint.isort]` (`known-first-party`) → **dropped** (see AD-3)

`pytest.ini.tmpl` `[pytest]` → `[tool.pytest.ini_options]`:
- `testpaths = tests` → `testpaths = ["tests"]` (TOML list)
- `python_files = test_*.py` → `python_files = ["test_*.py"]` (TOML list)
- `addopts = --strict-config --strict-markers` → `addopts = "--strict-config --strict-markers"` (TOML string)

The `target-version` template expression (`py{{python_version | replace('.','')}}`)
carries over unchanged.

`make lint` runs `ruff check .` / `ruff format --check .` and `make test` runs
`pytest -v` — all auto-discover config — so **no `Makefile.tmpl` change** is
needed. The pre-commit `ruff` / `ruff-format` hooks (`args: [--fix]`, no
`--config`) also auto-discover — **no `.pre-commit-config.yaml.tmpl` change**.

### Bucket B — Adoption-mode: shadow scan with escalation + advisory

Two changes. Both are read-only with respect to target-owned files — the skill
never modifies or deletes a target-owned `ruff.toml` / `pytest.ini`.

**B1 — top-level shadow scan: always-name + conditional escalation.** When
`--mode=adopt` runs for `--language=python`, scan **`target_root` only (not
recursively)** for owner-owned standalone config files the skill no longer
ships but which would override the skill's `pyproject.toml` tool tables:
- `ruff.toml`, `.ruff.toml` → shadow `[tool.ruff]`
- `pytest.ini` → shadows `[tool.pytest.ini_options]`

The scan runs **in every case**, and its result drives two things:

1. *Always — report advisory.* `format_recommendation_report` emits an
   advisory block that **names every detected file** and states plainly that
   it overrides the matching `[tool.*]` table — *whichever* `pyproject.toml`
   that table lives in (the skill's freshly-written one, or the target's own).
   This is emitted whether or not the target already has a `pyproject.toml`;
   it is the load-bearing surfacing of the live `call-details` shape (existing
   `[tool.pytest.ini_options]` + a `pytest.ini` that wins).
2. *Conditional — manual-review escalation.* If adoption would **WRITE a fresh
   `pyproject.toml`** (rule (a) — target has none) and the scan found a
   shadowing file, the `pyproject.toml` recommendation is **escalated to
   `manual_review_needed=True`** with a `reason` string explicitly naming the
   shadowing file(s). Interactive adoption then prompts the owner;
   `--non-interactive` exits 2 (the existing CI contract). If the target
   **already has a `pyproject.toml`** (rule (g) / (h) SKIP), no escalation is
   needed — that recommendation is already `manual_review_needed=True` — but
   the always-on report advisory above still names the shadowing file(s).

The escalated `pyproject.toml` recommendation **keeps `policy=WRITE`** (it does
not switch to SKIP or WRITE_NEW). Rationale: a project genuinely needs a
`pyproject.toml`, and SKIP would leave it without one — breaking the skill's
`Makefile` / render contract; `WRITE_NEW` (a `.new` sidecar) for a foundational
*missing* file is clunky. The escalation's value is the forced prompt plus an
explicit, file-naming `reason` shown in both the report advisory and the
prompt; the interactive blank-Enter default (accept `WRITE`) is acceptable
because the owner has by then seen the named warning twice, and the harm is
"the skill's tool config is not yet effective", not data loss. CI
(`--non-interactive`) still hard-fails via exit 2. *(Alternative considered:
escalate to SKIP/WRITE_NEW — rejected for the reasons above.)*

This uses **no new `Policy` enum value and no manifest-format change** — only
the existing `manual_review_needed` flag on the `pyproject.toml`
`PolicyRecommendation` is flipped. Implementation: `analyze_target` runs the
scan **once** (e.g. via a `scan_shadowing_configs(target_root)` helper in
`adopt.py`) and stores the result as a new explicit field on `AdoptionPlan`
(e.g. `shadowing_configs: tuple[str, ...]`). Both the escalation post-step and
`format_recommendation_report` consume that single stored snapshot — never
rescanning — so the escalation decision and the report advisory cannot drift
apart.

**B2 — `pyproject.toml`-SKIPped advisory.** When the target's own
`pyproject.toml` is SKIPped, the report notes that the skill's `[tool.ruff]` /
`[tool.pytest.ini_options]` were **not** applied. The wording has three
branches, because rule (h) is the catch-all default and covers more than a
"trivial" file:
- **rule (g)** — the target `pyproject.toml` already carries `[tool.*]` /
  `[project].dependencies` / `[dependency-groups]`: instruct the owner to
  inspect the **rendered** skill output via `--diff` (not the raw Jinja
  templates) and, if they want the skill's curated rules, **copy only** the
  `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]`, and
  `[tool.pytest.ini_options]` tables into their `pyproject.toml` — never
  replacing `[project]` or dependency sections, and merging rather than
  clobbering project-specific config (e.g. `call-details`' RU/UZ ruff
  ignores). The wording must **not** assert that the owner's `pyproject.toml`
  config is what is live — if the B1 scan found a standalone shadow file, that
  file wins instead; the rule-(g) wording explicitly defers to the B1 shadow
  advisory on the question of which config is actually effective.
- **rule (h), parseable + trivial** — the `pyproject.toml` parses cleanly but
  has no `[tool.*]` / deps: tell the owner they may add the skill's
  `[tool.ruff]` / `[tool.pytest.ini_options]` sections from the template.
- **rule (h), malformed / unparseable TOML** — `_is_nontrivial_pyproject`
  returns `False` for malformed TOML, so a malformed `pyproject.toml` also
  falls to rule (h): the advisory must tell the owner to **inspect and fix the
  malformed `pyproject.toml` first**, not to add sections to a broken file.
  Distinguishing parseable-trivial from malformed needs a `tomllib` parse in
  the advisory code (cheap — mirrors `_is_nontrivial_pyproject`'s parse).

No change to `recommend_policy`'s rules is required — the existing rules route
`pyproject.toml` correctly; B1's escalation is a post-step, and B2 is report
wording.

### Bucket C — Tests

`tests/test_mode_adopt_smoke.py` — the largest update surface. The all-safe
fixture currently uses `ruff.toml` (byte-identical → rule (c) SKIP) and
`pytest.ini` (empty → rule (b) OVERWRITE) as the *only* files exercising those
two rules end-to-end. They must be replaced with other planned files so the
rule-(b)/(c) coverage and the SKIP/OVERWRITE restore-matrix coverage are not
lost:
- rule (c) byte-identical SKIP → seed `.pre-commit-config.yaml` byte-identical
  to the rendered template.
- rule (b) empty OVERWRITE → seed an empty `.editorconfig`.

New B1 coverage:
- *unit-level* (adopt-engine test module) — the `scan_shadowing_configs`
  helper, the `analyze_target` escalation post-step, and the report advisory
  rendering, **parameterized over `ruff.toml` / `.ruff.toml` / `pytest.ini`**
  and over both target shapes: "no `pyproject.toml`" (escalation fires) and
  "existing `pyproject.toml`" (no escalation, advisory still names the file).
  The existing-`pyproject.toml` + `pytest.ini` case (the live `call-details`
  shape) is an explicit fixture asserting the report names `pytest.ini` as
  overriding `[tool.pytest.ini_options]`. A **no-shadow control** — rule-(a)
  WRITE `pyproject.toml` with no standalone config present → not escalated,
  `manual_review_needed=False` — guards the escalation against over-firing.
- *end-to-end* (`test_mode_adopt_smoke.py`) — one CLI smoke: target owns a
  standalone config + no `pyproject.toml`, run with
  `--auto-accept-recommendations --non-interactive` → **exit 2**. The existing
  non-trivial-`pyproject.toml` smoke fixture (`TestCallDetailsShapedFixture`,
  which seeds `pyproject.toml` with `[tool.ruff]`, rule (g) SKIP) additionally
  asserts the B2 rule-(g) advisory fires — note this fixture exercises the
  rule-(g) path, *not* the full live `call-details` shadow shape (existing
  `[tool.pytest.ini_options]` + a top-level `pytest.ini`), which is covered by
  the dedicated unit-level fixture above and the Verification smoke bullet.

`tests/test_python_templates.py` (pip-mode direct templates) — drop `ruff.toml`
/ `pytest.ini` references; add `[tool.ruff]` / `[tool.pytest.ini_options]`
assertions on the rendered `pyproject.toml`. `tests/test_python_uv_templates.py`
(uv-mode direct templates) — add the same `[tool.ruff]` /
`[tool.pytest.ini_options]` assertions: the new tables sit outside the `pm`
branch, so both package-manager modes must be covered.
`test_smoke_python_generated.py`, `test_smoke_python_uv_generated.py` — drop
`ruff.toml` / `pytest.ini` from expected path sets. A malformed-`pyproject.toml`
B2 advisory test lives in the adopt-engine test module.

### Bucket D — Docs

Bucket D targets **docs whose planned-file counts or recommendation-report /
CI-contract examples change** when two planned files disappear and the B1
escalation is added — primarily `docs/usage.md` (its adoption
recommendation-report example, file-count figures, and the
`--non-interactive` CI-contract description, which now has a new
manual-review-required trigger). Historical records
(`docs/trial-report-pr7.md`) stay as written — they are a point-in-time log;
this plan's Context section is the authoritative record of the bug, so no
erratum is added. `CLAUDE.md`'s "Key implementation invariants" does not
mention either file — no change there.

### Bucket E — BACKLOG entries for parked items

Add `BACKLOG.md` entries, each with an explicit trigger, for the four parked
items (per the repo's triage discipline — parked findings must be recorded,
not just mentioned):
- **TOML section-merge** for adoption-into-existing-`pyproject.toml` — trigger:
  when adoption mode gains the ability to merge owner-confirmed config sections.
- **`tox.ini` / `setup.cfg`** as additional pytest-config shadow sources —
  trigger: a real adoption target is found to keep pytest config there.
- **Nested (non-top-level) config scan** — trigger: a monorepo-shaped adoption
  target with sub-directory `ruff.toml`s.
- **Skill-repo own-config migration** (`ruff.toml`/`pytest.ini` →
  `pyproject.toml`) — trigger: a maintenance window where surfacing new lint
  errors on the skill's own code is acceptable.
- **Node / Go config-file shadowing** — the skill ships `biome.json` /
  `.golangci.yml`; Biome also reads `biome.jsonc` and `golangci-lint` also
  reads `.golangci.{yaml,toml,json}`, so a target-owned alternate-extension
  config can shadow the skill's. Trigger: extending adoption-mode shadow
  handling beyond Python, or a real Node/Go adoption target found to own an
  alternate-extension config.

## Architecture decisions

- **AD-1 — config lives in `pyproject.toml` for the files the skill ships; the
  target-owned-config residual is handled by a top-level shadow scan that
  always surfaces and conditionally escalates.** The standalone `ruff.toml` /
  `pytest.ini` templates are removed. A *target-owned* standalone config can
  still shadow a `pyproject.toml` — the skill's freshly-written one, or the
  target's own. The Bucket B B1 scan (top-level only — nested configs are out
  of scope, BACKLOG'd) **always** names detected files in the report, and
  **escalates** the `pyproject.toml` write to `manual_review_needed=True`
  whenever it would write a fresh one over a shadow, so automated
  (`--non-interactive`) adoption fails loud instead of going green with dead
  config.
- **AD-2 — adoption into an existing `pyproject.toml` SKIPs; the skill does
  not inject tool config.** Trade-off: a target that has a `pyproject.toml`
  without `[tool.ruff]` does not auto-receive the skill's curated ruff rules.
  This is deliberate — adoption mode's contract is *safety and
  non-interference*, and silently injecting config is the very class of bug
  this plan fixes. The B2 advisory tells the owner how to opt in by hand. The
  auto-add-when-absent enhancement (section-merge) is BACKLOG'd (Bucket E).
- **AD-3 — drop the `known-first-party` key entirely.** It was derived
  mechanically as `project_name.replace("-","_")`. It is wrong for adoption
  into a project whose real package differs from the repo name
  (`call-details` → guessed `call_details`, real `boxette_chats`), **and** it
  is already a dead no-op for greenfield: the skill scaffolds `src/main.py` (a
  script), not a package named after the project, so nothing matches
  `known-first-party` until the user creates a package they would name
  themselves. ruff's isort works without the key (it auto-detects first-party
  from project layout). Removing it eliminates the `known-first-party` defect
  (the "secondary defect" of the Context section) everywhere, with no BACKLOG
  park needed. The `project_import_name` context key in `cli.py::_build_context`
  becomes dead and is removed in the same change. *(Alternative considered:
  keep the key and park the adoption wrong-guess to BACKLOG — rejected because
  the key is unused even in greenfield, so keeping it ships misleading dead
  config.)*
- **AD-4 — pytest `[pytest]` → `[tool.pytest.ini_options]` TOML form.**
  `testpaths` / `python_files` become TOML lists; `addopts` a TOML string.
  pytest's `--strict-config` (kept in `addopts`) fails loud on a malformed
  `ini_options` table — so a bad migration cannot pass silently.
- **AD-5 — the live `call-details` cleanup is out of scope for this skill PR.**
  `call-details` still contains a stale `pytest.ini` from the original buggy
  adoption. Removing it is work in the `call-details` repo. The skill PR's
  acceptance is about the *skill*; it is not gated on the state of one
  downstream repo, and the implementation session must not edit `call-details`.
  Tracked under "Post-PR human follow-up" and surfaced at the approval gate.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| TOML type errors in the migrated pytest options | `--strict-config` in `addopts` + the generated-project smoke tests run real `pytest` → a bad table fails CI loud. |
| B1 escalation could over-fire (escalate `pyproject.toml` when no real shadow) | Escalation only triggers when the `pyproject.toml` recommendation is rule (a) WRITE *and* a top-level `ruff.toml`/`.ruff.toml`/`pytest.ini` exists; the rule (g)/(h) SKIP path is already mr=True and unaffected. Covered by the exit-2 and no-false-escalation fixtures. |
| Interactive blank-Enter still WRITEs a shadowed `pyproject.toml` | Accepted + documented (Bucket B B1 rationale): the owner sees the file-naming warning in both the report advisory and the escalated prompt `reason`; harm is "config not yet effective", not data loss; CI still hard-fails via exit 2. |
| `test_mode_adopt_smoke.py` rewrite silently weakens the rule-(b)/(c) / restore-matrix coverage | Bucket C names explicit replacement planned files (`.pre-commit-config.yaml`, `.editorconfig`) for each displaced rule; Tier-1 review verifies assertions were re-pointed, not deleted. |
| Shadow scan misses a config location (`tox.ini`, `setup.cfg`, nested configs) | Explicitly scoped out (NOT-in-scope) with BACKLOG entries (Bucket E); Context/Outcome/Verification wording is scoped to the three top-level filenames so nothing overclaims. |
| ruff version-pin lockstep (pre-commit `rev` ↔ pyproject `ruff==` pin) | Unchanged by this PR — the pin's location does not move. Noted so reviewers do not re-flag it. |
| Skill repo's own `ruff.toml` now inconsistent with what the skill ships | Out of scope (NOT-in-scope table); BACKLOG entry (Bucket E); surfaced in the approval summary. |

## Verification

- `make check` green in the skill repo.
- Bootstrap a fresh Python project (uv and pip modes) → `make check` green in
  the generated project, with ruff + pytest reading config from `pyproject.toml`.
- Adoption smoke: `--mode=adopt` into a fixture with an existing
  `pyproject.toml` containing `[tool.ruff]` → the target's `pyproject.toml` is
  SKIPped (untouched), B2 rule-(g) advisory shown.
- Adoption smoke: `--mode=adopt` into a fixture with an existing
  `pyproject.toml` (with `[tool.pytest.ini_options]`) **plus** a top-level
  `pytest.ini` → the report names `pytest.ini` as overriding
  `[tool.pytest.ini_options]` (the live `call-details` shape).
- Adoption smoke: `--mode=adopt` into a fixture that owns a top-level
  standalone `ruff.toml` / `.ruff.toml` / `pytest.ini` and has **no**
  `pyproject.toml`, run with `--auto-accept-recommendations --non-interactive`
  → **exit 2** (the B1 escalation guard); the advisory names the shadowing file.
- The skill *surfaces* the call-details-class issue (advisory + escalation);
  Verification does **not** edit any downstream repo.

## Post-PR human follow-up

Not a gate on this skill PR (AD-5), surfaced at the approval gate: the live
`call-details` repo still contains a stale `pytest.ini` written by the original
buggy adoption. The user should remove it in the `call-details` repo and
confirm that repo's `make lint` goes green.

## Iteration log (this plan)

| Iter | Reviewer | imp-3 | imp-2 | imp-1 | Notes |
|---|---|---|---|---|---|
| 1 | Codex | 2 | 3 | 1 | F2 folded (target-owned shadow scan); F3 folded (drop `known-first-party`); F4 folded (advisory = merge-not-replace); F5 folded (explicit replacement fixtures); F6 folded (Bucket D scope). F1 imp-3 framing rejected — call-details cleanup is a separate-repo task (AD-5) + Verification note. |
| 1.5 | Claude (consistency) | 0 | — | — | 0 contradictions; 5 internal drifts all folded (C1–C5). |
| 2 | Codex | 1 | 4 | 0 | All 5 folded: G1 imp-3 (B1 → manual-review escalation, not log-only); G2 (B2 three-way wording incl. malformed pyproject); G3 (top-level-only scan boundary); G4 (Bucket E owns the BACKLOG updates); G5 (call-details action moved out of Verification). |
| 2.5 | Claude (consistency) | 0 | — | — | 0 contradictions; 1 minor drift folded (C6 — B1/B2 advisory attribution). |
| 3 | Codex | 1 | 3 | 0 | All 4 folded: H1 imp-3 (B1 scan always surfaces detected files even when a `pyproject.toml` exists; B2 rule-(g) no longer asserts unconditional precedence); H2 (escalated rec keeps `policy=WRITE` — justified); H3 (tests parameterized over all 3 filenames); H4 (Context/Outcome/Verification scoped to the 3 top-level filenames). |
| 3.5 | Claude (consistency) | 0 | — | — | 0 contradictions; 3 minor drifts folded (C7 — B2 missing a Scope row; C8 — stale "no `ruff.toml` written" in Verification; C9 — Risks named a no-false-escalation fixture absent from Bucket C). |
| 4 | Codex | 0 | 3 | 1 | **0 imp-3 — convergence pass.** All 4 folded: I1 (one scan result stored on `AdoptionPlan` — single snapshot for escalation + report, no drift); I2 (B2 rule-(g) → inspect via `--diff`, copy only the `[tool.ruff*]`/`[tool.pytest.ini_options]` tables); I3 (clarified the e2e fixture is the rule-(g) `[tool.ruff]` shape, not the full live shadow shape); I4 (uv direct-template test named). |
| 4.5 | Claude (consistency) | 0 | — | — | 0 contradictions; 1 cosmetic label folded (C10 — Critical-files line aligned with the I3 reframing). **Loop converged.** |
| T2 | claude[bot] + Codex (PR #22) | 0 | 3 | 1 | claude[bot]: 0 imp-3, "ready for implementation". Codex: 1 P2. J1 folded (Codex P2 — Node/Go config-file shadowing is a real surface, claim corrected + parked). J2–J4 rejected (already-covered / implementation-review / stylistic). |

## Evidence table — what was folded and where

| Finding | Reviewer/iter | Decision | Where |
|---|---|---|---|
| F1 — no remediation for already-shadowed call-details | Codex/1 | (c) reject imp-3 framing + (d) surface to human | AD-5; Post-PR human follow-up; NOT-in-scope row. Skill PR not gated on a downstream repo's state. |
| F2 — analyzer still misses target-owned standalone configs | Codex/1 | (a) fold | Context (two-halves); Scope #4/#6; Bucket B (B1); AD-1; Risks; Verification; Critical files. (Strengthened by G1/H1.) |
| F3 — AD-3 overclaimed `project_import_name` solved | Codex/1 | (a) fold | AD-3 rewritten — drop `known-first-party` + `project_import_name` key entirely; Scope #1/#3; Bucket A; Bucket D. |
| F4 — advisory too vague / unsafe copy-paste | Codex/1 | (a) fold | Bucket B (B2) — advisory wording = compare-and-merge, owner config wins; Bucket C asserts it. |
| F5 — test migration can weaken restore coverage | Codex/1 | (a) fold | Bucket C names `.pre-commit-config.yaml` (rule c) + `.editorconfig` (rule b) replacements; Risks. |
| F6 — docs scope imprecise | Codex/1 | (a) fold | Bucket D reworded to "docs whose counts/examples change"; trial report stays historical. |
| C1 — orphaned "Bug B" label | consistency/1.5 | (a) fold | AD-3 — replaced "Bug B" with "the `known-first-party` defect (the 'secondary defect' of the Context section)". |
| C2 — B2 trigger set vs wording (rule (h) has no owner config) | consistency/1.5 | (a) fold | Bucket B (B2) — wording adapts per SKIP reason (further refined to three-way by G2). |
| C3 — `.ruff.toml` missing from Verification bullet 4 | consistency/1.5 | (a) fold | Verification — added `.ruff.toml` to the shadow-scan fixture list. |
| C4 — advisory test location disagreed (smoke vs adopt-engine module) | consistency/1.5 | (a) fold | Pre-coding + Bucket C — reconciled: unit tests in the adopt-engine module, end-to-end in `test_mode_adopt_smoke.py`. |
| C5 — Scope #6 missing bucket tag | consistency/1.5 | (a) fold | Scope #6 — tagged "(Bucket C)". |
| G1 — B1 log-only advisory lets `--non-interactive` adoption go green with shadowed config | Codex/2 | (a) fold | Context (half 2); Scope #4/#6; Bucket B (B1) — escalate `pyproject.toml` write to `manual_review_needed=True`; AD-1; Risks; Verification; Pre-coding new-coverage (c). |
| G2 — rule (h) covers malformed/unclassified, not only "trivial" | Codex/2 | (a) fold | Bucket B (B2) — three-way wording incl. malformed-`pyproject.toml` branch; Bucket C malformed advisory test. |
| G3 — shadow-scan scope (top-level vs recursive) underspecified | Codex/2 | (a) fold | Bucket B (B1) — "top-level (`target_root`) only"; NOT-in-scope nested-config row; Bucket E BACKLOG entry. |
| G4 — deferred items say BACKLOG but plan doesn't own the update | Codex/2 | (a) fold | New Scope #8 + Bucket E — `BACKLOG.md` entries with explicit triggers for all four parked items. |
| G5 — Verification contains an out-of-scope `call-details` mutation | Codex/2 | (a) fold | Verification — mutation removed; new "Post-PR human follow-up" section; AD-5; NOT-in-scope row. |
| C6 — B1 claimed the SKIP-case advisory that B2 owns | consistency/2.5 | (a) fold | Bucket B (B1) — already-has-`pyproject.toml` bullet defers the SKIP-case advisory to B2 (refined by H1: B1 still emits its own always-on shadow advisory). |
| H1 — existing-`pyproject.toml` + standalone shadow not surfaced; B2 rule-(g) "takes precedence" false | Codex/3 | (a) fold | Context (half 2 — two shadow shapes); Bucket B (B1 always-name; B2 rule-(g) defers to B1); Scope #4/#6; Bucket C (existing-pyproject + `pytest.ini` fixture); AD-1; Verification; Outcome. |
| H2 — B1 flips only `manual_review_needed`; interactive default still WRITEs shadowed config | Codex/3 | (a) fold | Bucket B (B1) — `policy=WRITE` retained, rationale + alternative documented; Risks row; Bucket C asserts `reason` names the file. |
| H3 — tests don't cover all three shadow filenames | Codex/3 | (a) fold | Pre-coding new-coverage (b); Scope #6; Bucket C — unit tests parameterized over `ruff.toml`/`.ruff.toml`/`pytest.ini`. |
| H4 — outcome overclaims "standalone config" while `tox.ini`/`setup.cfg` deferred | Codex/3 | (a) fold | Outcome measurement + Context + Verification scoped to the three top-level filenames; NOT-in-scope rationale; Risks. |
| C7 — B2 implementation had no Scope-table row | consistency/3.5 | (a) fold | Scope #4 — extended to enumerate the B2 three-way advisory (Bucket B, B2). |
| C8 — stale "no `ruff.toml` written" in Verification | consistency/3.5 | (a) fold | Verification — rephrased to "the target's `pyproject.toml` is SKIPped (untouched)". |
| C9 — Risks named a no-false-escalation fixture absent from Bucket C | consistency/3.5 | (a) fold | Bucket C — added the no-shadow control fixture (rule-(a) WRITE, no standalone config → not escalated). |
| I1 — B1 scan result has no owner in the data model (advisory/escalation drift risk) | Codex/4 | (a) fold | Bucket B (B1) — `analyze_target` scans once, stores `shadowing_configs` on `AdoptionPlan`; escalation + report share the snapshot. |
| I2 — B2 manual-merge guidance underspecified (raw Jinja, no diff path) | Codex/4 | (a) fold | Bucket B (B2 rule-(g)) — inspect via `--diff` (rendered, not template), copy only the tool tables, never `[project]`/deps. |
| I3 — "call-details-shaped fixture" label overclaims the live shadow shape | Codex/4 | (a) fold | Bucket C — relabelled the e2e fixture as the non-trivial-`pyproject.toml` rule-(g) fixture; full live shadow shape covered by the dedicated unit fixture + Verification bullet. |
| I4 — uv direct-template test not named in Bucket C | Codex/4 | (a) fold | Bucket C — `tests/test_python_uv_templates.py` named; `[tool.ruff]`/`[tool.pytest.ini_options]` asserted for both pm modes. |
| C10 — Critical-files fixture label not aligned with the I3 reframing | consistency/4.5 | (a) fold | Critical files — relabelled to "non-trivial-`pyproject.toml` rule-(g) fixture (`TestCallDetailsShapedFixture`)". |
| J1 — "no shadowing risk" for Node/Go is false (`golangci-lint` reads `.golangci.{yaml,toml,json}`; Biome reads `biome.jsonc`) | Codex Tier-2/PR #22 | (a) fold | NOT-in-scope row corrected (Node/Go shadowing is real, parked not "nothing to change"); Scope #8 + Bucket E — 5th BACKLOG entry. |
| J2 — verify TOML section-name semantics (`[lint]` → `[tool.ruff.lint]`) | claude[bot] Tier-2/PR #22 | (c) reject | Already covered — the generated-project smoke test runs real ruff/pytest against the rendered `pyproject.toml`; section-name equivalence is documented ruff behavior, not a risk. |
| J3 — `policy=WRITE` display vs manual-review prompt UX | claude[bot] Tier-2/PR #22 | (c) reject | Implementation-review territory — the plan already specifies an explicit file-naming `reason`, and `format_recommendation_report` segregates `mr=True` files under a "manual review needed" heading. |
| J4 — Scope-table parallel structure | claude[bot] Tier-2/PR #22 | (c) reject | Stylistic. |

## Implementation log (this PR)

| Commit | Summary | Tier-1 |
|---|---|---|

## Lessons surfaced (this PR)

| Lesson | Source | Triage |
|---|---|---|

## Critical files to read before each iter's review

- `bootstrap_lib/render.py` — `PYTHON_TEMPLATE_MAP`, `planned_paths`, `render_all`
- `bootstrap_lib/adopt.py` — `recommend_policy` rules (a)/(g)/(h), `_is_nontrivial_pyproject`, `analyze_target`, `format_recommendation_report`
- `bootstrap_lib/cli.py` — `_build_context` (`project_import_name`), the adoption flow + `--non-interactive` contract + the interactive prompt default
- `languages/python/pyproject.toml.tmpl`, `ruff.toml.tmpl`, `pytest.ini.tmpl`, `Makefile.tmpl`, `.pre-commit-config.yaml.tmpl`
- `tests/test_mode_adopt_smoke.py` — all-safe + non-trivial-`pyproject.toml` rule-(g) fixture (`TestCallDetailsShapedFixture`)
- `docs/usage.md` — adoption recommendation-report example + `--non-interactive` CI contract
- This plan's Context section (the call-details dogfooding report)
