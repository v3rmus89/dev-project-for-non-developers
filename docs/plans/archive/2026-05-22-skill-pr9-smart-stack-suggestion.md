# Plan PR: PR #9 — smart stack suggestion from a plain-English project description

## Context

PR #8 (merged) shipped the **interactive intake**: running `bootstrap.py` with no
flags starts a guided question flow. PR #8 asks for the stack **explicitly** — a
numbered menu for language, then (for Python) package manager.

A non-coder, though, does not necessarily know "Python vs Node vs Go". PR #8's
own plan deliberately split out the smarter layer: **PR #9 lets the user
describe the project in plain English, and the skill *suggests* a language** —
then pre-fills that suggestion as the language-menu default. The user still
sees the menu and still confirms; the suggestion never auto-applies.

This plan is informed by a research pass (2026-05-22) over `obra/superpowers`
and a survey of other NL-brief → stack tools — see **External sources** below.
Findings that shaped the design:

- **No vendor-able open-source library exists** for "NL brief → stack
  suggestion" as inspectable code. The space is closed SaaS tools + agent-
  instruction skills. So PR #9 builds its own small deterministic module.
- **`obra/superpowers` ships only agent-instruction markdown**, no runnable
  code — a *pattern* source. Reusable patterns: ask one question at a time,
  prefer multiple-choice; **lead with the recommended option and explain why**;
  suggestion ≠ decision (keep an explicit approval gate).
- **StackShare "Awesome Stacks"** (CC0-1.0) is a license-clean *inspiration*
  source for the web / front-end / back-end signal groupings. It does **not**
  have a CLI/tooling category, so the Go signal set is the skill's own product
  judgment, not source-backed (see External sources + AD-5).

### External sources (evidence trail)

| Source | URL | License | Accessed | How it is used |
|---|---|---|---|---|
| `obra/superpowers` (`main`) | https://github.com/obra/superpowers — `skills/brainstorming/SKILL.md`, `skills/writing-plans/SKILL.md` | MIT | 2026-05-22 | *Patterns only* — paraphrased into intake copy (AD-5); no code/prose copied. |
| StackShare "Awesome Stacks" | https://github.com/stackshareio/awesome-stacks | CC0-1.0 | 2026-05-22 | **Broad inspiration** for the **nodejs** (Front-end / Full-stack categories) and **python** (Back-end category) signal groupings. The README's categories are Front-end / Full stack / Back-end / Mobile — there is **no** CLI/tooling category, so it does **not** back the **go** signal set. CC0 prose; access date is the pin. |
| Go's well-known niche (CLI tooling, systems programming, concurrency) | — (general knowledge) | n/a | — | The **go** signal set is **repo-local product judgment** — Go's commonly-understood strengths — not transcribed from any one source. Flagged explicitly so it is a documented decision, not an unsourced claim. |

### Pre-coding statements

**Regression safety.**
- *Auto-testable:* `suggest_stack()` is a pure function — unit-tested against the
  fixed **Brief acceptance matrix v1** (below), which is part of *this plan* and
  reviewed here, before any code. Intake tests feed scripted stdin and assert
  the resolved argv; one CLI-level `_FakeStdin` test drives the full `main([])`
  path with a non-empty brief.
- *Existing tests — honest impact:* PR #9 inserts a new prompt into
  `run_intake`, so **every scripted-stdin fixture that drives the intake must
  gain a blank "brief" answer** after the project-name answer — in
  `tests/test_intake.py` and `tests/test_bootstrap_cli.py`. The *expected argv /
  assertions* are unchanged; only the *input answer streams* shift by one line.
  A dedicated test asserts that skipping the brief yields argv byte-identical to
  the equivalent PR #8 flow — proving PR #9 is purely additive.
- *Not auto-testable:* suggestion quality on phrasing **outside** the matrix.
  Mitigated by AD-2's graceful fallback (a missed brief → plain menu).

**Outcome measurement.** User-facing feature, but the skill is a pure offline
CLI with **no telemetry** — there is no event to capture an acceptance-rate
metric. Stated explicitly so it is a considered decision, not an omission.
Success signal: (a) the Brief acceptance matrix v1 passes in CI, and
(b) dogfooding. No business metric applies.

## Brief acceptance matrix v1

This matrix is the **objective success criterion** (folded per Codex iter-2 #1 —
without it the implementer would define both the rules and the tests, making
the only success measure self-referential). It is fixed *here, in the plan*.
`tests/test_stack_suggest.py` parameterizes exactly these rows; the signal sets
in Bucket A must satisfy every row. Each row is derivable from the Bucket A
rules — the "matched signals" column names the Bucket A signal(s) that fire.

| # | Brief | Expected | Matched signals (from Bucket A) |
|---|---|---|---|
| 1 | "A script to scrape competitor prices into a spreadsheet" | `python` | `scrape` (strong) + `script`, `spreadsheet` (weak) |
| 2 | "An automation that emails me a daily sales report" | `python` | `automation`, `report` (weak ×2 → eligible) |
| 3 | "A REST API for my mobile app's backend" | `python` | `rest api` (strong) + `api`, `backend` (weak) |
| 4 | "A machine learning model to predict customer churn" | `python` | `machine learning` (strong) |
| 5 | "A data pipeline that loads orders into a warehouse" | `python` | `data pipeline` (strong) + `data` (weak) |
| 6 | "A landing page for my bakery" | `nodejs` | `landing page` (strong) |
| 7 | "A React dashboard showing live orders" | `nodejs` | `react` (strong) + `dashboard` (weak) |
| 8 | "A website where customers book appointments" | `nodejs` | `website` (strong) |
| 9 | "A single page web app for tracking tasks" | `nodejs` | `single page`, `web app` (strong ×2) |
| 10 | "A command line tool to rename files in bulk" | `go` | `command line tool`, `command line` (strong) + `tool` (weak) |
| 11 | "A high performance microservice for image resizing" | `go` | `high performance`, `microservice` (strong) |
| 12 | "A small daemon that watches a folder and syncs files" | `go` | `daemon` (strong) |
| 13 | "A customer dashboard" | `None` | only `dashboard` (1 weak, 0 strong) — below the eligibility floor |
| 14 | "A tool for tracking shipments" | `None` | only `tool` (1 weak, 0 strong) — below the eligibility floor |
| 15 | "A machine learning model with a React interface" | `None` | `machine learning` (python strong) **vs** `react` (nodejs strong) — both eligible, tied max score → no unique winner |
| 16 | "Something to help my business grow" | `None` | no signal matches |
| 17 | "A rapid prototype of an idea" | `None` | no-false-hit guard — `rapid` must NOT match the `api` signal; nothing else matches |
| 18 | "A machine learning dashboard in the browser" | `python` | `machine learning` (python strong → score 3) **outranks** `dashboard` + `browser` (nodejs, 2 weak → score 2) — strong-outranks-multiple-weak |

Rows 13-14 exercise the eligibility floor; row 15 the tie-among-eligible
branch; row 16 the zero-match branch; row 17 the no-false-hit guard; row 18
the strong-outranks-multiple-weak score weighting (Bucket A step 3). Rows
9-11 exercise multi-word phrase matching. Signals are written **hyphen-free**
(Bucket A step 1) so a hyphenated brief ("single-page", "command-line")
normalises to match. The matrix may be *extended* in implementation (more
rows), never *weakened* (no row removed or changed without a plan amendment).

## Scope

### IN scope

| # | Item |
|---|---|
| 1 | New module `bootstrap_lib/stack_suggest.py` — `suggest_stack(brief: str) -> StackSuggestion | None`: a deterministic phrase-matching **signal scorer** mapping a plain-English brief to a **language** suggestion + a one-line rationale. Returns `None` on low confidence (Bucket A). |
| 2 | Rules table — per-language signal sets, each split into **strong** and **weak** signals (words *and* phrases), satisfying the Brief acceptance matrix v1. Keyed on `_flags.LANGUAGES` (single source of truth for the language list — an import-time assertion + a test pin the key set); sources per the External-sources table (Bucket A). |
| 3 | Intake wiring — a new optional **"describe your project"** free-text question after the project-name step; a confident suggestion pre-fills the **language** menu *default* and the menu prompt (rendered by the caller) leads with the recommendation + rationale; skip or low-confidence → the language menu behaves exactly as PR #8 (Bucket B). |
| 4 | `_ask_menu` gains an optional `default` parameter affecting **input only** — blank Enter returns `default`; no `default` → current required-choice behaviour, byte-identical to PR #8; raises fail-loud on `default not in choices`. `_ask_menu` does **not** render rows or markers — the caller owns the prompt string (Bucket B; AD-6). |
| 5 | Tests — `stack_suggest` unit tests driven by the Brief acceptance matrix v1 + a `_flags.LANGUAGES` key-consistency test; intake tests for the brief/skip/override/low-confidence paths + a canary-brief privacy test + a visible-marker test + an `_ask_menu` test (both branches + the fail-loud guard); a CLI-level `_FakeStdin` test of the full `main([])` brief path; the blank-brief fixture shift in `test_intake.py` + `test_bootstrap_cli.py` (re-prompt / EOF fixtures verified per-case); the skip-brief ⇒ PR-#8-identical-argv regression test (Bucket C). |
| 6 | Docs + BACKLOG — `docs/usage.md` + `README.md` updated for the describe-your-project step; **mark** the "PR #9" `BACKLOG.md` entry `✅ DONE` (repo convention) and **add** a `--describe`-flag entry with a trigger (Bucket D). |

### NOT in scope

| Item | Why / where it goes |
|---|---|
| An LLM call for the suggestion | AD-1 — rejected: breaks the "pure CLI, no `.env`, offline" invariant and is not CI-testable. Deterministic signal scorer instead. |
| A non-interactive `--describe "..."` CLI flag | PR #9 is an *intake-flow* enhancement only. A `--describe` flag is a larger surface — a `BACKLOG.md` entry is **added by Bucket D**, with a trigger. |
| Suggesting the **package manager** from the brief | A plain-English brief carries no uv-vs-pip signal. The suggestion is **language-only**; the Python package-manager menu is untouched (PR #8 — uv labelled "(recommended)"). |
| Refactoring `_ask_menu` into a structured menu renderer | AD-6 picks the minimal contract — `_ask_menu` handles blank-default *input* only; callers keep owning prompt rendering. A renderer refactor is out of scope. |
| Suggesting `github-review`, smoke-doc, output-dir, or Node/Go sub-options | Not "stack" decisions / out of the `language`-only decision space. |
| Adopt-mode (`--mode=adopt`) intake | PR #8's intake is greenfield-only; PR #9 inherits that boundary. |

## Subsystem breakdown

### Bucket A — the suggestion engine (`bootstrap_lib/stack_suggest.py`)

A new module, importable by `intake.py`. 3.12 syntax (never loaded by the
3.6-compatible shim).

- `StackSuggestion` — a class-syntax `NamedTuple`: `language: str`,
  `rationale: str`. (No `package_manager` — the suggestion is language-only.)
- `suggest_stack(brief: str) -> StackSuggestion | None`:
  1. **Normalise** the brief: lowercase; replace every run of non-alphanumeric
     characters (**including hyphens** — hyphens are punctuation here) with a
     single space; wrap in single spaces → `norm`. Because hyphens are
     stripped, the signal sets are written **hyphen-free** (`"single page"`,
     `"command line tool"`) and a hyphenated brief (`"single-page"`)
     normalises to match. Signals list the exact word forms that matter (e.g.
     both `"website"` and `"websites"`) — there is no stemming, so the engine
     stays fully deterministic.
  2. **Match** each signal against `norm` as a *space-bounded substring*
     (`f" {signal} " in norm`) — works for unigrams (`"api"`) and phrases
     (`"machine learning"`), and space-bounding prevents false hits inside
     longer words (`"api"` ∉ `"rapid"` — matrix row 17).
  3. **Score** each language: `n_strong` = distinct **strong** signals matched,
     `n_weak` = distinct **weak** signals matched,
     **`score = 3 * n_strong + n_weak`** — a strong signal is weighted so that
     one strong match outranks two weak matches (Codex iter-3 #1: equal
     weighting let two weak Node signals beat one strong Python signal).
  4. **Eligibility (the confidence floor — Codex iter-2 #4):** a language is
     *eligible* only if `n_strong >= 1` **or** `n_weak >= 2`. A single broad
     (weak) signal is **not** enough — that is matrix rows 13-14.
  5. **Pick:** among *eligible* languages, the one with the unique-maximum
     `score` wins. No eligible language, or a tie for the max `score` among
     eligible languages → `return None` (low confidence — AD-2 fallback).
  6. **Rationale:** a short, fixed, human-readable string **per language** —
     for Python: `"data, automation, and API projects are Python's usual
     home"` — never an echo of the user's words (deterministic +
     privacy-clean). The same string is reused verbatim in Bucket B's
     confident line.
- Rules table — module-level constants, per language a `strong` and a `weak`
  `frozenset`. The signal table **and** the rationale table are keyed on the
  language strings, and those keys must be exactly `set(_flags.LANGUAGES)` —
  `_flags.py` stays the single source of truth for the language list (Codex
  iter-3 #3). A module-level assertion (`set(SIGNALS) == set(RATIONALES) ==
  set(_flags.LANGUAGES)`) fails loud at import on drift; a Bucket C test pins
  it too. All signals are hyphen-free (step 1). The sets below are the
  **baseline**: they satisfy every Brief acceptance matrix v1 row. They may be
  *extended* in implementation **only when the extension is exercised by an
  accompanying new matrix row** (Tier-2 #2 — an untested signal is not
  allowed; the matrix stays the complete coverage gate), and never reduced
  below matrix coverage. Sourcing per the External-sources table.
  - python — strong: `"scrape"`, `"scraper"`, `"scraping"`,
    `"machine learning"`, `"data pipeline"`, `"rest api"`, `"etl"`; weak:
    `"data"`, `"script"`, `"api"`, `"backend"`, `"automation"`, `"ai"`,
    `"bot"`, `"report"`, `"spreadsheet"`.
  - nodejs — strong: `"website"`, `"websites"`, `"web site"`, `"web app"`,
    `"react"`, `"single page"`, `"landing page"`, `"frontend"`,
    `"front end"`; weak: `"ui"`, `"dashboard"`, `"browser"`.
  - go — strong: `"command line tool"`, `"command line"`, `"microservice"`,
    `"daemon"`, `"high performance"`; weak: `"cli"`, `"tool"`, `"systems"`,
    `"concurrent"`.
- No I/O, no network, no new dependency — a pure function over a string.

### Bucket B — intake wiring (`bootstrap_lib/intake.py`)

- New step, **after** `_ask_project_name`, **before** the language menu: an
  optional free-text question — *"Describe your project in a sentence or two —
  or press Enter to skip:"*. Blank → skip (`suggestion = None`).
- On a non-blank brief: call `stack_suggest.suggest_stack(brief)`.
  - Confident suggestion → print one "lead with the recommendation" line that
    embeds `suggestion.rationale` verbatim, in the form *"Based on that, I'd
    suggest **<language>**: <rationale>. You can still pick anything below."* —
    e.g. *"Based on that, I'd suggest **python**: data, automation, and API
    projects are Python's usual home. You can still pick anything below."*
  - `None` → print a neutral line (*"I couldn't infer a language from that —
    pick below."*) and proceed with no pre-fill.
- The **caller** (intake's language-menu block) renders the menu prompt
  string. When a suggestion exists it appends a `← recommended` marker to the
  matching row and a `[default: <lang>]` hint, then calls
  `_ask_menu(prompt, choices, default=suggestion.language)`. With no
  suggestion it renders the PR #8 prompt verbatim and calls `_ask_menu` with
  no `default`.
- `_ask_menu` itself (AD-6): `default: str | None = None`. When `default` is
  set and the user enters a blank line, return `default`; otherwise behave as
  PR #8 (re-prompt on invalid/empty). When `default` is set it **must** be one
  of `choices` — `_ask_menu` raises (fail-loud) on `default not in choices`,
  so a `stack_suggest` ↔ `_flags.LANGUAGES` drift surfaces at the call site,
  not silently downstream (Codex iter-3 #3). `_ask_menu` does **not** parse or
  render rows. The no-`default` branch is byte-identical to PR #8.
- The Python package-manager menu and everything downstream (github-review,
  smoke, output-dir, greenfield check, confirm gate, argv assembly) is
  **untouched** — the suggestion only changes the language menu's default +
  the caller-rendered prompt text.

### Bucket C — tests

- `tests/test_stack_suggest.py` (new): the **Brief acceptance matrix v1**
  parameterized one-row-per-test; plus targeted unit tests — multi-word-signal
  briefs, the no-false-hit (`"api"`/`"rapid"`) case, the eligibility floor
  (one weak signal → `None`; one strong → suggestion), the
  strong-outranks-multiple-weak weighting (row 18), tie → `None`, rationale
  presence; and the **key-consistency test** —
  `set(SIGNALS) == set(RATIONALES) == set(_flags.LANGUAGES)` (Codex iter-3 #3).
- `tests/test_intake.py` (extend): the brief-confident path (pre-fill, blank
  Enter accepts → argv has the suggested language); the brief-skip path; the
  **override** path (suggestion made, user types a different language number →
  that wins); the low-confidence path; a **canary-brief privacy test** (a
  unique sensitive token absent from captured stdout **and** the returned
  argv, while the fixed rationale appears); a **visible-marker test** — for a
  confident suggestion, captured stdout contains the `← recommended` row
  marker **and** the `[default: <lang>]` hint; for the skip / low-confidence
  paths it contains **neither** (Codex iter-3 #5); a dedicated `_ask_menu`
  test covering **both** branches (`default` set → blank accepts it; no
  `default` → required choice, byte-identical to PR #8) **plus** the
  fail-loud `default not in choices` guard.
- `tests/test_bootstrap_cli.py` (extend): one CLI-level `_FakeStdin` test of
  the full `main([])` path — project name → non-empty brief → blank language
  answer (accepting the suggested default) → remaining answers → assert the
  apply succeeds and the generated tree is the suggested language (Codex
  iter-2 #5).
- **Fixture shift (Codex iter-3 #4 — not a mechanical one-liner):** every
  scripted-stdin fixture in `test_intake.py` + `test_bootstrap_cli.py` that
  drives `run_intake` gains a blank brief answer **immediately after the
  *accepted* project-name answer** — which, for an invalid-project-name
  re-prompt fixture, is the *last* answer of the re-prompt sequence, not the
  first. EOF-mid-flow fixtures must be reviewed per-case: an EOF that today
  lands on the language prompt must be re-pointed so it still lands there
  (now one answer later) — the test must keep exercising the *same* EOF
  point, not just stay long enough to pass. Expected-argv assertions are
  unchanged; a shared helper inserts the blank-brief line but each re-prompt
  / EOF fixture is verified individually.
- **Regression lock:** skipping the brief produces argv byte-identical to the
  equivalent PR #8 flow.

### Bucket D — docs + BACKLOG

- `docs/usage.md`'s interactive-setup section gains a short paragraph on the
  describe-your-project step (optional; pre-fills the language menu, never
  auto-applies; skipping is fine). `README.md`'s "New project?" pointer gets a
  clause. No flag docs change — PR #9 adds no flag.
- `BACKLOG.md` (Codex iter-3 #2 + Tier-2 #1): **mark** the "PR #9 — smart
  stack suggestion" entry `✅ … — DONE in PR #<impl>` — following the repo's
  existing BACKLOG convention (shipped items stay, marked `✅ DONE`, e.g. the
  PR #2 / PR #5c entries) rather than being deleted. A `✅ DONE` entry no
  longer reads as parked, so `make status` / recovery docs are correct. **Add**
  a new BACKLOG entry for the parked non-interactive `--describe` flag, with an
  explicit trigger.

## Architecture decisions

- **AD-1 — deterministic signal scorer, not an LLM call.** An LLM would handle
  arbitrary phrasing better, but it breaks the skill's hard invariants: the
  bootstrap is a *pure offline CLI with no `.env`* (project `CLAUDE.md`), and a
  non-deterministic call is not CI-testable. The decision space is small
  (3 languages). The scorer's weakness — brittle phrasing — is made *graceful*
  by AD-2: a missed brief falls back to the plain menu. `suggest_stack` is kept
  behind a single function signature so a future PR could swap in an optional,
  key-gated LLM path without touching `intake.py`. *(Alternative — LLM —
  rejected for the invariant break + untestability.)*
- **AD-2 — suggestion ≠ decision; graceful fallback.** The suggestion only
  sets the language-menu *default*. The user always sees the full menu and
  always confirms at the existing confirm gate. A `None` or skipped brief
  produces no pre-fill — behaviour identical to PR #8. The engine's failure
  mode is a no-op, not a wrong outcome. The strong/weak confidence floor
  (Bucket A step 4) keeps a single broad word from producing a thin
  recommendation a non-coder might over-trust.
- **AD-3 — the suggestion is language-only.** A plain-English brief carries a
  parseable signal for *language* but not for the uv-vs-pip choice. The
  package-manager menu is left exactly as PR #8.
- **AD-4 — intake-only; no new CLI flag.** A non-interactive `--describe` flag
  is BACKLOG'd.
- **AD-5 — pattern reuse, CC0 inspiration, no code vendoring.** superpowers'
  brainstorming *patterns* are paraphrased into PR #9's intake copy — not
  copied (MIT; a courtesy credit is in External sources). StackShare "Awesome
  Stacks" (CC0) is *broad inspiration* for the web/back-end signal groupings —
  not transcribed verbatim and not a per-signal source. The **go** signal set
  is explicitly repo-local product judgment (External sources row 3). No code
  is vendored from any source.
- **AD-6 — `_ask_menu` keeps its minimal contract.** `_ask_menu` receives a
  caller-rendered prompt string; PR #9 adds only blank-default *input*
  handling (`default` param). It does **not** gain row-rendering or
  marker-drawing — those stay with the caller (which already hand-writes menu
  prompts). Rejected alternative: refactor `_ask_menu` into a structured menu
  renderer — larger blast radius, and it would invalidate the "everything
  downstream untouched" guarantee for the other menus.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Signal sets misfire on phrasing outside the matrix (wrong default) | AD-2 — the suggestion is only a menu default; the user sees + overrides it; the confirm gate is unchanged. The confidence floor (strong/weak) suppresses thin one-word guesses. |
| The matrix is too small to be a real quality gate | The matrix is fixed in the plan (reviewed here) and may be *extended* in implementation, never weakened. It is the calibration target for the signal sets. |
| Phrase signals silently never match (hyphens, multi-word) | Bucket A step 1 strips hyphens and the signal sets are hyphen-free; step 2 space-bounds the match; matrix rows 9-11 + the no-false-hit row 17 lock the behaviour. |
| Inserting a prompt breaks scripted-stdin fixtures | Bucket C explicitly shifts every `run_intake` fixture in `test_intake.py` + `test_bootstrap_cli.py`; the skip-brief regression test pins byte-identical argv to PR #8. |
| `_ask_menu`'s new `default` param changes behaviour for no-`default` callers | `default` defaults to `None`; the `None` branch is byte-identical to PR #8, pinned by the two-branch `_ask_menu` test (AD-6). |
| Brief free-text could contain something sensitive the skill echoes | Rationale strings are *fixed per language*; the brief is never echoed. The canary-brief test asserts the brief is absent from stdout + argv. |
| A weak-signal pile-up outranks a genuine strong signal | Bucket A step 3 weights strong signals (`score = 3·n_strong + n_weak`); matrix row 18 locks "one strong outranks two weak". |
| The pre-filled default is invisible to the user (feature works but hides) | Bucket C's visible-marker test asserts the `← recommended` marker + `[default]` hint appear in stdout for a confident suggestion and are absent for skip / low-confidence. |
| `stack_suggest`'s language keys drift from `_flags.LANGUAGES` | Import-time assertion in `stack_suggest.py` + a Bucket C key-consistency test + `_ask_menu`'s fail-loud `default not in choices` guard. |

## Verification

- `make check` green in the skill repo.
- `tests/test_stack_suggest.py` — every Brief acceptance matrix v1 row passes,
  plus the multi-word / no-false-hit / eligibility-floor / strong-weighting
  (row 18) / key-consistency cases.
- The existing `tests/test_intake.py` assertions pass with the blank-brief
  fixture shift (re-prompt / EOF fixtures verified per-case); the skip-brief
  test proves byte-identical argv to PR #8; the canary-brief test confirms no
  echo; the visible-marker test confirms the recommendation marker + default
  hint render for a confident suggestion and not otherwise; the CLI-level
  `_FakeStdin` test proves the full `main([])` brief path applies the
  suggested language.
- Manual: run `bootstrap.py` (no flags) on a TTY, type a brief, confirm the
  recommendation + rationale appear and the language-menu default is
  pre-filled; repeat with a nonsense brief → graceful no-pre-fill.

## Iteration log (this plan)

| Iter | Reviewer | imp-3 | imp-2 | imp-1 | Notes |
|---|---|---|---|---|---|
| 1 | Codex | 2 | 3 | 0 | All 5 folded: F1 (regression-safety claim corrected); F2 (phrase-aware space-bounded matching); F3 (suggestion narrowed to language-only); F4 (canary-brief privacy test); F5 (External-sources table). |
| 1.5 | Claude (consistency) | 0 | — | — | 0 contradictions; 3 drifts folded (C1 "decision tree"→"signal scorer"; C2 `_ask_menu` two-branch test; C3 rationale example unified). |
| 2 | Codex | 2 | 3 | 0 | All 5 folded: G1 imp-3 (fixed "Brief acceptance matrix v1" added to the plan — success criterion is no longer self-referential); G2 imp-3 (AD-6 — `_ask_menu` minimal contract, caller owns rendering); G3 (StackShare evidence corrected — no CLI category; go signals = repo-local judgment); G4 (strong/weak confidence floor); G5 (CLI-level `_FakeStdin` brief test). |
| 2.5 | Claude (consistency) | 0 | — | — | 2 contradictions + 2 drifts folded (C4 hyphenated signals can't match a hyphen-stripped `norm` → signal sets made hyphen-free; C5 row-15 rebuilt as a real tie-among-eligible case; C6 rationale string genuinely unified Bucket A↔B; C7 matrix rows ↔ Bucket A signal sets made mutually derivable). |
| 3 | Codex | 0 | 5 | 0 | **0 imp-3 — convergence pass.** All 5 folded: H1 (strong signals now *weighted* `3·n_strong + n_weak` — one strong outranks two weak; matrix row 18); H2 (Bucket D removes the shipped "PR #9" BACKLOG entry + adds a `--describe` entry); H3 (`stack_suggest` keyed on `_flags.LANGUAGES` — import assertion + key-consistency test + `_ask_menu` fail-loud guard); H4 (fixture-shift wording made per-case-precise for re-prompt / EOF fixtures); H5 (visible-marker stdout test). |
| 3.5 | Claude (consistency) | 0 | — | — | 0 contradictions; 2 stale evidence-table cells folded (G1 "17"→"18" matrix rows; G4 eligibility-floor formula refreshed to the H1-final `n_weak>=2` form). **Loop converged.** |
| T2 | claude[bot] + Codex (PR #24) | 0 | 2 | 2 | claude[bot]: 0 imp-3, "ready after minor edits". Codex: 👍 (no suggestions). J1 folded (BACKLOG: mark `✅ DONE` per repo convention, not "remove"); J2 folded (extended signals require an accompanying matrix row). J3–J4 rejected (row-17 guard is intentional; Go-set "repo-local judgment" framing is the honest one). |

## Evidence table — what was folded and where

| Finding | Reviewer/iter | Decision | Where |
|---|---|---|---|
| F1 — "tests run unchanged" false; a new prompt shifts every scripted-stdin fixture | Codex/1 | (a) fold | Pre-coding regression-safety; Scope #5; Bucket C; Risks; Verification; Critical files. |
| F2 — unigram tokeniser cannot match multi-word phrase signals | Codex/1 | (a) fold | Bucket A step 1-2 — space-bounded substring matching; Bucket C; Risks; Verification. |
| F3 — `package_manager` claimed inferred but hard-coded | Codex/1 | (a) fold | Suggestion narrowed to language-only; Scope; Bucket A/B; AD-3; NOT-in-scope. |
| F4 — privacy/no-echo unverified | Codex/1 | (a) fold | Bucket C canary-brief test; Risks; Verification. |
| F5 — external-source reuse not reproducible | Codex/1 | (a) fold | External-sources table; AD-5; Context. |
| C1 — "decision tree" vs the score-and-max mechanism | consistency/1.5 | (a) fold | Scope #1, NOT-in-scope, AD-1 — "signal scorer". |
| C2 — Risks claimed an `_ask_menu` test absent from Bucket C | consistency/1.5 | (a) fold | Bucket C — `_ask_menu` two-branch test. |
| C3 — rationale example differed between Bucket A and B | consistency/1.5 | (a) fold | Bucket B — example embeds `suggestion.rationale`. |
| G1 — suggestion-quality gate self-referential (rules + tests both written in impl) | Codex/2 | (a) fold | New "Brief acceptance matrix v1" section (18 fixed rows after the H1 row-18 addition); Pre-coding; Scope #2/#5; Bucket A/C; Risks; Verification. |
| G2 — `_ask_menu` assigned row-rendering it cannot own | Codex/2 | (a) fold | AD-6 (minimal contract — caller renders, `_ask_menu` handles blank-default input only); Scope #4; Bucket B; NOT-in-scope; Bucket C. |
| G3 — StackShare evidence overreaches (no CLI category) | Codex/2 | (a) fold | External-sources table rewritten (StackShare = web/back-end inspiration only; go signals = repo-local judgment, row 3); Context; AD-5; Bucket A. |
| G4 — confidence rule too permissive (one broad signal suggests) | Codex/2 | (a) fold | Bucket A step 3-5 — strong/weak split + eligibility floor (`n_strong>=1` or `n_weak>=2` — formula finalised by the H1 weighted-score fold); matrix rows 13-14; AD-2; Risks. |
| G5 — non-empty-brief CLI path left manual | Codex/2 | (a) fold | Bucket C — CLI-level `_FakeStdin` `main([])` brief test; Scope #5; Verification. |
| C4 — hyphenated signals can never match a hyphen-stripped `norm` | consistency/2.5 | (a) fold | Bucket A step 1 strips hyphens + signal sets rewritten hyphen-free; matrix "matched signals" column hyphen-free. |
| C5 — matrix row 15's "tie" mechanism never fires (both ineligible) | consistency/2.5 | (a) fold | Row 15 rebuilt as "machine learning" vs "react" — two strong signals, a genuine tie-among-eligible → `None`. |
| C6 — rationale example still differed between Bucket A and Bucket B | consistency/2.5 | (a) fold | One canonical Python rationale string fixed in Bucket A step 6, reused verbatim in Bucket B's confident line. |
| C7 — matrix rows cited signals absent from Bucket A's sets | consistency/2.5 | (a) fold | Matrix "matched signals" column + Bucket A baseline sets reconciled — every row is now derivable from the listed signals. |
| H1 — strong/weak signals scored equally (two weak outrank one strong) | Codex/3 | (a) fold | Bucket A step 3 — `score = 3·n_strong + n_weak`; eligibility restated `n_strong>=1 OR n_weak>=2`; matrix row 18; Risks. |
| H2 — plan doesn't clean up the shipped "PR #9" BACKLOG entry | Codex/3 | (a) fold | Bucket D — remove the parked PR #9 entry, add a `--describe`-flag entry; Scope #6; NOT-in-scope `--describe` row. |
| H3 — `stack_suggest` is a second language source of truth, ungated | Codex/3 | (a) fold | Bucket A — tables keyed on `_flags.LANGUAGES` + import assertion; Bucket B — `_ask_menu` fail-loud `default not in choices`; Bucket C key-consistency test; Scope #2/#4. |
| H4 — fixture-shift wording too broad for re-prompt / EOF fixtures | Codex/3 | (a) fold | Bucket C — blank brief inserted after the *accepted* project-name answer; re-prompt / EOF fixtures verified per-case. |
| H5 — the visible default/recommendation marker isn't auto-tested | Codex/3 | (a) fold | Bucket C — visible-marker stdout test (marker + `[default]` hint present for a confident suggestion, absent for skip / low-confidence); Verification; Risks. |
| J1 — Bucket D said "remove" the PR #9 BACKLOG entry; repo convention is to mark `✅ DONE` | claude[bot] Tier-2/PR #24 | (a) fold | Bucket D + Scope #6 — "remove" → "mark `✅ DONE in PR #<impl>`" per the repo's existing BACKLOG convention. |
| J2 — signal-set extensions could be untested (matrix is fixed) | claude[bot] Tier-2/PR #24 | (a) fold | Bucket A rules table — an extension is allowed only with an accompanying new matrix row; the matrix stays the complete coverage gate. |
| J3 — matrix row 17 (`rapid`/`api`) seems redundant with space-bounded matching | claude[bot] Tier-2/PR #24 | (c) reject | Row 17 is a deliberate regression guard for the space-bounding contract (added per Codex iter-1 #2) — "the algorithm already handles it" is exactly what a regression test pins. |
| J4 — Go signal set cites "general knowledge" not documented sources | claude[bot] Tier-2/PR #24 | (c) reject | The plan already *honestly* frames the Go set as repo-local product judgment (Codex iter-3 #3); blog-post citations would not make it less a judgment call — the explicit flag is the more honest documentation. |

## Implementation log (this PR)

| Commit | Summary | Tier-1 |
|---|---|---|
| 0da1273 | Bucket A — `stack_suggest.py` deterministic signal scorer (`suggest_stack`, `StackSuggestion`) + `test_stack_suggest.py` (18-row matrix v1 + targeted unit tests); 31 tests pass | 0 imp-3; 1 imp-2 folded (tie-reset branch now covered) + 1 imp-1 folded (rationale test tightened); 2 imp-1 accepted as-is (duplicate-of-matrix test; `assert`-vs-`python -O` — both no-change-needed per Tier-1) |
| 82974aa | Bucket B+C — optional plain-English brief wired into `intake.py`; `_ask_menu` gains a blank-accepts-`default` param; `_language_menu_prompt` renders the marker; intake/CLI tests + the scripted-stdin fixture shift | 0 imp-3; 2 imp-2 folded (default hint → plan-consistent `[default:]` brackets; added a `_language_menu_prompt(None)` byte-identity test); 1 imp-1 accepted as-is (brief wording paraphrase — within AD-5 latitude). NOTE: this commit's message says "713 passed" — stale by one; the imp-2 fold amend added a test, real count is 714 (see Bucket D's `make check`). |
| 3d315eb | Bucket D — docs (`docs/usage.md` describe-step paragraph + `README.md` clause) + `BACKLOG.md` (PR #9 marked `✅ DONE`, new `--describe`-flag entry); 714 `make check` tests pass | 0 imp-3; 2 imp-1 accepted-and-noted: (a) `82974aa`'s "713" is stale vs the real 714 — not force-pushed for a cosmetic message fix; (b) the BACKLOG done-heading is a bare `— DONE` (the impl PR number is unknowable pre-merge; bare `— DONE` has repo precedent) |

## Lessons surfaced (this PR)

| Lesson | Source | Triage |
|---|---|---|

## Critical files to read before each iter's review

- `bootstrap_lib/intake.py` — the PR #8 question flow + `_ask_menu` that PR #9 extends
- `bootstrap_lib/_flags.py` — `LANGUAGES` constant (the language-list source of truth `stack_suggest` keys on)
- `BACKLOG.md` — the "PR #9 — smart stack suggestion" parked entry Bucket D removes
- `bootstrap_lib/cli.py` — how intake argv re-feeds the parser; `--interactive`
- `tests/test_intake.py` + `tests/test_bootstrap_cli.py` — the scripted-stdin
  fixtures PR #9 must shift; `_FakeStdin` is the CLI-level test harness
- `docs/plans/2026-05-21-skill-pr8-interactive-intake.md` — the merged intake plan
- This plan's Context + External sources + Brief acceptance matrix v1
