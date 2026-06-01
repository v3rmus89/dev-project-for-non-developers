# PR-2 (Bucket A): in-plan-mode review-wrapper

## Context

PR-2 implements **Bucket A** from the meta-plan
(`~/.claude/plans/what-else-i-want-majestic-rain.md`, "PR-2: Bucket A —
third priority") and its merged design pre-work
([docs/design-notes/2026-05-29-bucket-a-architecture.md](../design-notes/2026-05-29-bucket-a-architecture.md)).
Bucket A was deferred out of PR #10 after 6 cross-review iters failed to plateau
on three adopt-engine architectural blockers; the design note resolves all
three (options considered + rejected + acceptance criteria), and the focused
cross-direction Codex review on the note (2026-05-29) is complete. This plan
turns that design into a buildable PR; iters 1-2 of the cross-review loop folded
ten findings that materially reshaped it (see Iteration log + Evidence table).

**What PR-2 ships** (two layers):
1. A **`make review` dispatcher** (the shared, deterministically-testable core):
   `make review MODE={plan,commit} ACTOR={claude,codex} [PLAN_FILE=… ITERATION=…]`
   resolves to the *correct* review target — **cross-direction** for plan review
   (Claude-authored → Codex; Codex-authored → Claude) and **same-AI** for commit
   review — and invokes it. This is what makes the 6-branch behavior testable in
   `make check`.
2. A Claude Code **slash command** `/dev-review` (a new artifact at
   `.claude/commands/dev-review.md`) — Claude's *front-end* to the dispatcher.
   `ACTOR` is the review **subject**, determined **mode-asymmetrically** (iter-3
   FN1): for `/dev-review commit` the implementer IS the Claude session, so it
   passes `ACTOR=claude` directly (same-AI Tier-1, correct by construction); for
   `/dev-review plan` the plan's **author** may be Claude or Codex, so the command
   `AskUserQuestion`s ("who authored this plan?", Claude the default option) rather
   than silently defaulting — a silent default could mis-route a Codex-authored
   plan to the wrong reviewer. It does **not** rely on an `export REVIEWER=…`
   persisting — each Claude Bash tool call is a fresh shell, so an export there
   wouldn't reach a later `make` call (iter-2 FN4). It lets a Claude implementer
   launch the right review from **inside plan mode** without the exit-plan-mode /
   return cycle.

PR-2 also extends **Python** adopt-mode so the command file can be installed into
an existing Python repo whose `.gitignore` blanket-ignores `.claude/` (Node/Go
adopt-mode is rejected by `_resolve_mode`, so there is no Node/Go-adopt-`.claude/`
path — see the NOT-in-scope Node/Go row, iter-3 FN2).

**Codex side (iter-1 FN3 — platform reality):** a `.claude/commands/*.md` slash
command is a **Claude Code** feature; **Codex cannot invoke it** (`codex --help`
exposes `exec`/`review`/`plugin`, no `.claude/commands` resolution). So Codex
does **not** get a slash command — when Codex is the implementer it calls the
*same* `make review ACTOR=codex MODE=…` dispatcher **directly** (guided by
AGENTS.md). `REVIEWER` survives only as a **terminal** convenience for
hand-run `make review` (a shell `export REVIEWER=codex` persists within that
shell, unlike a Claude tool-call export). Both AIs reach the same dispatch
truth; only Claude needs the slash-command front-end (only Claude has the
plan-mode exit/return friction).

**What PR-2 is NOT:** it is *workflow ergonomics*, NOT a deduplication fix. The
command is a 7th shared surface (V-21 byte-identity acknowledges this); it does
**not** solve cross-project rule propagation — that was PR-3
(`scripts/propagate-shared-rules.py`, shipped in PR #33). The `THREAD_MODE`
continue-default flip is unrelated and out of scope.

**Naming decision (iter-1 FN6 — folded; overridable at the approval gate):** the
command is named **`dev-review`** (`/dev-review`, `.claude/commands/dev-review.md`).
The merged design note loosely named it `dev-project-setup`, but that **collides**
with the existing bootstrap skill (root `SKILL.md` = `# dev-project-setup`) and
Claude Code's registry resolution precedence between a same-named skill and slash
command is unverified. `dev-review` is collision-free, more descriptive (it IS a
review wrapper, not a bootstrap surrogate — reinforced by FN3 narrowing it to a
review front-end), and matches PR #10's original name. Surfaced for override; if
`dev-project-setup` is still wanted, it is a mechanical find-replace + a live
coexistence smoke.

### Pre-coding declarations (CONTRIBUTING "Pre-coding")

- **Regression safety — auto-testable.** Deterministic tests gate every
  behavior: the 4 `ACTOR×MODE` dispatcher resolutions + the unset→`NEEDS-ASK`
  signal (via the dispatcher's resolve mode — no live AI); V-21 render-overlap
  byte-identity for the command file; `git check-ignore` clears the dogfood
  command (committable); the dispatcher's byte-identity
  (Makefile ↔ `shared/Makefile.review.tmpl`); dispatch-convention presence
  asserts; the command-body assertion of the `plan`/`commit` invocation forms;
  NEUTRALIZE `recommend_policy` rules (incl. `.claude/`-class vs broad-pattern);
  NEUTRALIZE consent under normal / `--auto-accept-recommendations` /
  `--non-interactive`; `sort_key` apply/restore ordering + legacy-v2 compat; the
  `.gitignore`-touched-by-both (APPEND_MERGE + NEUTRALIZE) apply→restore
  byte-identical round-trip + the interrupted-apply + user-edited-block cases.
  All run under `make check`. One step is **manual**: a live smoke invoking
  `/dev-review` (both `plan` and `commit`) from a real Claude session (the
  markdown command is executed by a live agent — not unit-runnable). Called out
  in Verification.
- **Outcome measurement — internal change, no business metric.** PR-2 is
  developer-workflow tooling. Internal proxy: a Claude implementer launches the
  correct cross-direction plan review (or same-AI commit review) from inside
  plan mode in **one command**, **zero** plan-mode exit/return cycles, never
  offered a wrong-direction or both-directions choice; a Codex implementer
  reaches the same dispatch via `make review` directly.

## Scope

### IN scope

| # | Item | Surfaces |
|---|------|----------|
| S1 | `make review MODE=… ACTOR=… [PLAN_FILE=… ITERATION=…]` dispatcher + a `REVIEW_RESOLVE` mode that prints the target it would run (deterministic test hook, no live AI) | `Makefile` + `shared/Makefile.review.tmpl` (inside the `SELFTEST-OVERLAP-BEGIN/END` block — byte-identical) |
| S2 | Dispatcher tests: 4 `ACTOR×MODE` **resolve-mode** resolutions + unset→`NEEDS-ASK`; **+ 4 normal-mode invocation tests** (faked CLI, assert the sub-target runs + `PLAN_FILE`/`ITERATION` passthrough — iter-4 FN2); `make help` lists `review` (iter-3 FN5); selftest-overlap byte-identity covers the new lines | `tests/test_makefile_review_targets.py`; `tests/test_selftest_overlap.py`; the per-language target-list render tests (e.g. `tests/test_nodejs_templates.py`) asserting `make help` contents |
| S3 | `/dev-review` dogfood command + verbatim template + render registration + **the skill-repo `.gitignore` un-ignore exception for the dogfood command** (iter-2 FN1) | `.claude/commands/dev-review.md` (new); `shared/claude-commands-dev-review.md.tmpl` (new); `bootstrap_lib/render.py` `SHARED_TEMPLATE_MAP` (`render.py:9`); this repo's `.gitignore` |
| S4 | V-21 byte-identity (rendered template == dogfood command) | `tests/test_selftest_overlap.py` (new `test_overlap_dev_review_command`) |
| S5 | Dispatch convention in docs: Claude invokes `/dev-review …` (which passes `ACTOR=claude` directly); Codex runs `make review ACTOR=codex …` directly (NO slash command); `REVIEWER` = terminal convenience only | `CLAUDE.md`, `shared/CLAUDE.md.tmpl`; `AGENTS.md`, `shared/AGENTS.md.tmpl` |
| S6 | Presence asserts for the dispatch convention (per-surface, different wording) | `tests/test_dogfood_doc_sanity.py` (new parametrized test) |
| S7 | 6-branch acceptance = the 4 `ACTOR×MODE` dispatcher resolutions (S2) + 2 command-body assertions (Other×plan → asks author then emits the chosen form; Other×commit → emits `ACTOR=claude` directly, no ask — iter-3 FN1) asserting the exact `make review MODE=plan/commit ACTOR=… [PLAN_FILE=…]` forms and never offering both cross-AI options; the dispatcher's `unset→NEEDS-ASK` (S2) is the routing trigger, not a branch | `tests/test_makefile_review_targets.py` + `tests/test_dogfood_doc_sanity.py` (command-body assertion) |
| S8 | NEUTRALIZE policy: new `Policy` literal + `recommend_policy` trigger (`.claude/`-class ignore only) + `manual_review_needed=True` | `bootstrap_lib/adopt.py` `Policy` (`adopt.py:29`), `_check_ignored_by_git` (`adopt.py:144`, add a privacy-safe `.claude/`-class classifier), `TargetMeta` (`adopt.py:58`), `recommend_policy` rule-a0 site (`adopt.py:419`) |
| S9 | `sort_key` dependency ordering on v2 manifest entries | `bootstrap_lib/manifest.py` v2 builders (`manifest.py:168-253`), `plan_adoption_entries` (`manifest.py:256`), `_restore_v2` (`manifest.py:581`) |
| S10 | NEUTRALIZE entry builder + apply (sentinel block) + **sentinel-based** restore handler + two-entry expansion | `bootstrap_lib/manifest.py` (new `_build_v2_neutralize_entry`, `_restore_v2_neutralize`, `_V2_RESTORE_HANDLERS` at `manifest.py:573`); report/decide path in `bootstrap_lib/cli.py` |
| S11 | adopt-mode tests: NEUTRALIZE rules + consent + sort_key + both-mutations round-trip + interrupted-apply + user-edited-block | `tests/test_adopt_engine.py`, `tests/test_manifest.py`, `tests/test_interactive_decide.py`, `tests/test_mode_adopt_smoke.py` |
| S12 | Docs: `/dev-review` invocation syntax (plan + commit) + manual smoke recipe; **update `docs/usage.md`'s normative tables — the adopt-mode rule table (add a NEUTRALIZE row) + the v2 restore matrix (add NEUTRALIZE sentinel-removal) — + a doc-sanity assertion** (iter-4 FN5) | `docs/usage.md`; `tests/test_dogfood_doc_sanity.py` |

### NOT in scope

| Item | Why | Where it lives |
|------|-----|----------------|
| A Codex-native slash command | Codex can't invoke `.claude/commands` (FN3); it uses `make review` directly | — |
| `THREAD_MODE=fresh→continue` default flip | Separate future PR gated on A/B-replay gates | BACKLOG `continue-thread-pr-followup` |
| Cross-project rule propagation | PR-3 shipped it (`scripts/propagate-shared-rules.py`, PR #33) | — |
| A `depends_on` DAG for manifest ordering | `sort_key` suffices for the single NEUTRALIZE→WRITE dependency (design note open-Q2) | deferred |
| Node/Go adopt-mode `.claude/` handling | The command ships via `SHARED_TEMPLATE_MAP` (renders for all langs), but adopt-mode (NEUTRALIZE) is Python-only — `cli.py` `_resolve_mode` **rejects** `--mode=adopt` for Node/Go, so there is no Node/Go-adopt-`.claude/` path to break. Greenfield Node/Go is safe (their `.gitignore.tmpl` has no `.claude/`). The only residual gap — plain `--apply --overwrite-existing` into an *existing* Node/Go repo already ignoring `.claude/` — is a **pre-existing** plain-apply limitation, not introduced by PR-2 (iter-3 FN2) | parked → BACKLOG when Node/Go adopt-mode is built |
| Live-AI assertion inside `make check` | non-deterministic; the resolve mode + content assertions cover it deterministically instead | manual smoke only |
| Renaming/migrating root `SKILL.md` | distinct artifact; no change needed | — |

## Subsystem breakdown

PR-2 splits into **Part 1 (the wrapper — dispatcher + slash command + docs)** and
**Part 2 (adopt-mode delivery — NEUTRALIZE + sort_key)**. The skill's own
`languages/*/.gitignore.tmpl` contains **no** `.claude/` pattern (verified —
`languages/python/.gitignore.tmpl` ignores only `.bootstrap-tmp/`), so a
greenfield-bootstrapped or `.claude/`-not-ignored target receives the command
file through the normal render/write path with **no** NEUTRALIZE needed. Part 2
is required ONLY for adopt-into-a-repo-that-already-ignores-`.claude/`.

**Dogfood caveat (iter-2 FN1):** the skill repo *itself* ignores `.claude/`
(`.gitignore:50` = `.claude/`, to keep local session state out of git), so the
**dogfood** `.claude/commands/dev-review.md` is git-ignored here and not
committable as-is (`git check-ignore` confirms it). Part 1 therefore appends the
same 6-line un-ignore block (S3) to *this repo's own* `.gitignore` — a one-time
edit that **dogfoods exactly what Part-2 NEUTRALIZE automates** for adopt
targets (only `.claude/commands/dev-review.md` is un-ignored; the rest of
`.claude/`, e.g. `settings.local.json`, stays ignored). With that exception in
Part 1, Part 1 is independently shippable and Part 2 is a cleanly separable
second stage (see the Part-2-splits-to-PR-2b contingency, per the CONTRIBUTING
architectural-blocker-split advisory).

### Part 1 — the review-wrapper

**1A. The `make review` dispatcher (S1, S2) — the shared tested core.** A new
`review` target in the `SELFTEST-OVERLAP-BEGIN/END` block of `Makefile` (mirrored
byte-identically in `shared/Makefile.review.tmpl`, so generated projects inherit
it; the existing `test_overlap_makefile_review_section` enforces parity). The
target is declared `.PHONY` and carries a `##` help description (iter-3 FN5), so it
appears in `make help` as the user-facing entry point.

- Inputs: `MODE` ∈ {plan, commit}, `ACTOR` ∈ {claude, codex, unset}, plus pass-through
  `PLAN_FILE` / `ITERATION` for plan mode. **`ACTOR` precedence:** an explicit
  `ACTOR=` on the command line (what the slash command passes) wins; else
  `ACTOR ?= $(REVIEWER)` (the terminal convenience — a shell `export REVIEWER`
  persists within that shell); else unset → `NEEDS-ASK`.
- Resolution table (the single source of dispatch truth):

  | `ACTOR` / `MODE` | resolves to |
  |---|---|
  | claude / plan | `review-plan-by-codex PLAN_FILE=$(PLAN_FILE) ITERATION=$(ITERATION)` (cross) |
  | codex / plan | `review-plan-by-claude PLAN_FILE=$(PLAN_FILE) ITERATION=$(ITERATION)` (cross) |
  | claude / commit | `review-commit-by-claude` (same-AI) |
  | codex / commit | `review-commit-by-codex` (same-AI) |
  | `ACTOR` unset / other (any `MODE`) | print `NEEDS-ASK`, exit 2 — **normal mode**; in resolve mode it prints `NEEDS-ASK` and exits 0 (the `/dev-review` command must `AskUserQuestion` for the actor first) |

- **Resolve mode (deterministic test hook):** when `REVIEW_RESOLVE=1`, the target
  prints **only** the resolved target name — or `NEEDS-ASK` for the unset/other
  case — and exits **0** **without invoking** `codex`/`claude`, so every branch
  (including unset) is cleanly assertable. This is what `make check` tests — no
  live AI, no mocking. Normal invocation (no `REVIEW_RESOLVE`) runs the resolved
  sub-target and exits 2 on the unset/other case (the table row above is
  normal-mode behavior).
- `tests/test_makefile_review_targets.py`: assert
  `make review MODE=plan ACTOR=claude REVIEW_RESOLVE=1` → `review-plan-by-codex`,
  the other 3 mappings, and bare `ACTOR=` → `NEEDS-ASK`.
- **Normal-mode invocation tests (iter-4 FN2):** the resolve-mode tests prove the
  *decision*; a separate set with a faked `codex`/`claude` on `PATH` runs
  `make review` in NORMAL mode for all 4 `ACTOR×MODE` paths and asserts the right
  sub-target actually executed AND plan mode passed `PLAN_FILE`/`ITERATION` through
  — catching a broken recursive `$(MAKE)` call or dropped passthrough that
  resolve-mode alone would miss.
- *Rejected alternative:* a `scripts/review-dispatch.py` the command + tests both
  call. It adds a new shared-script surface (template + byte-identity +
  `EXECUTABLE_TARGETS` + render-map). The dispatch is inherently a make concern;
  the resolve mode gives equal determinism with less surface.

**1B. The `/dev-review` slash command (S3, S4) — Claude's front-end.**
- New dogfood `.claude/commands/dev-review.md`: YAML frontmatter
  (`name: dev-review`; one-line `description`; `allowed-tools:` MUST include
  `Bash` (to run `make review`) and `AskUserQuestion` (the ambiguous-actor
  fallback — PR #10 iter-2 F7)).
- **Argument contract (iter-2 FN3 + iter-3 FN1):** `/dev-review plan [PLAN_FILE]
  [ITERATION]` and `/dev-review commit`. The body parses the mode token, then:
  - `commit` → `make review MODE=commit ACTOR=claude` — the Claude session IS the
    implementer, so `ACTOR=claude` is correct by construction (same-AI Tier-1); no
    question.
  - `plan` → the author may differ from the session, so it `AskUserQuestion`s "who
    authored this plan?" (Claude the default option), then runs
    `make review MODE=plan ACTOR=<answer> PLAN_FILE=<arg-or-active-plan> ITERATION=<arg-or-1>`.
    (No positional actor token — the author is set by the question. If `PLAN_FILE`
    is omitted it uses the active plan-mode file or asks.)
  - It MUST NEVER offer both cross-AI plan-review options at once (PR #10 iter-4 F5).
- **Skill-repo `.gitignore` exception (iter-2 FN1):** append the 6-line un-ignore
  block (same as 2C's) to *this repo's* `.gitignore` so the dogfood command is
  git-trackable; verify `git check-ignore .claude/commands/dev-review.md` returns
  no match. (Dogfoods Part-2 NEUTRALIZE — see Subsystem breakdown.)
- New verbatim template `shared/claude-commands-dev-review.md.tmpl`,
  **byte-identical** to the dogfood — it contains **no Jinja directives**, so it
  renders to itself (it references project-agnostic `make` targets;
  `PLAN_FILE`/`ITERATION` are runtime args, not render vars). It is still loaded
  *through* the Jinja env like every overlap template. Registered in
  `SHARED_TEMPLATE_MAP` (`render.py:9`) as
  `".claude/commands/dev-review.md": "claude-commands-dev-review.md.tmpl"`. NOT in
  `EXECUTABLE_TARGETS` (markdown, mode 0644).
- V-21 (S4): `test_overlap_dev_review_command` in `tests/test_selftest_overlap.py`,
  modeled on the existing `test_overlap_*` functions — render the template (loaded
  by Jinja via its bare name, as the other overlap tests do) with
  `SKILL_REPO_CONTEXT`, `_assert_byte_equal` against the new dogfood file. Verbatim
  ⇒ `render == source == dogfood`.

**1C. Dispatch convention in docs (S5, S6).** No runtime API detects the calling
AI (design note sub-design 3), so the convention is documented per surface:
- `CLAUDE.md` + `shared/CLAUDE.md.tmpl`: a short instruction — in plan mode,
  Claude invokes `/dev-review plan` (or `commit`) to run the right review;
  `commit` dispatches `ACTOR=claude` directly (the session implements), `plan`
  asks the author. No `REVIEWER` export needed — an export in one Bash tool call
  would not reach a later `make` call.
- `AGENTS.md` + `shared/AGENTS.md.tmpl`: the Codex mirror — Codex **cannot**
  invoke a Claude slash command, so it runs `make review ACTOR=codex MODE=…`
  (or the explicit `review-plan-by-claude` / `review-commit-by-codex` target)
  **directly**, passing `ACTOR=codex` **inline on the same invocation** — a
  separate `export REVIEWER=codex` is unreliable (Codex tool calls are also fresh
  shells; iter-4 FN3), so `REVIEWER` stays a human-terminal-only convenience.
  AGENTS.md currently has no approval-gate paragraph (BACKLOG `iter-3 F5`); this
  is a *new* short section.
- Not byte-identical across surfaces (Claude vs Codex wording differs) → pinned
  by per-surface **presence** asserts in `tests/test_dogfood_doc_sanity.py`
  (modeled on `test_cross_session_recovery_instruction_present`).

**1D. 6-branch acceptance (S7).** The design note requires all 6 branches to have
an automated test (`docs/design-notes/2026-05-29-bucket-a-architecture.md:197-210`).
The 6 branches = 3 actors (Claude / Codex / Other) × 2 modes (plan / commit).
Coverage, all deterministic + in `make check`:
- **4 branches** (Claude/Codex × plan/commit) → the dispatcher resolve-mode tests (S2).
- **2 branches** (Other × plan/commit) → command-body content assertions on
  `.claude/commands/dev-review.md` (iter-3 FN1 — mode-asymmetric subject): for
  **plan** review the command `AskUserQuestion`s the **author** then emits the
  chosen-direction `make review MODE=plan ACTOR=<answer> …` form; for **commit**
  review the implementer is the Claude session by construction, so it emits
  `make review MODE=commit ACTOR=claude` directly (no ask — this refines the design
  note's Other×commit "ask" row). It never lists both cross-AI options together.
  The dispatcher's mode-agnostic `unset→NEEDS-ASK` (one S2 test) is the *routing
  trigger* — supporting plumbing, not a 7th branch.

This replaces iter-1's rejected pure-markdown-only assertion: the dispatch
*decision* is now proven by executing the dispatcher, not by grepping prose.

### Part 2 — adopt-mode delivery (NEUTRALIZE + sort_key)

**2A. NEUTRALIZE policy + trigger + consent (S8).** Extend `Policy` (`adopt.py:29`)
to `Literal["WRITE","SKIP","OVERWRITE","WRITE_NEW","APPEND_MERGE","NEUTRALIZE"]`.

- **Trigger (iter-1 FN5 — `.claude/`-class only):** at the rule-a0 site
  (`adopt.py:419`), a planned `.claude/commands/dev-review.md` that is ignored
  returns `NEUTRALIZE` **only when the matched ignore pattern is `.claude/`-class**
  (the block we append can actually un-ignore it). If the path is ignored by a
  *broad* rule the block won't fix (e.g. `*.md`), keep the conservative rule-a0
  `SKIP`+`manual_review` (preserves design-note AC4). Privacy-safe detection:
  `_check_ignored_by_git` (`adopt.py:144`) already drops the pattern from the
  surfaced report; extend it to ALSO return a derived boolean
  `ignored_by_dotclaude_pattern` (precise check: the matched pattern, `!`/space
  **and an optional leading `/`** stripped — root-anchored `/.claude/` and
  `/.claude/**` are normal gitignore forms (iter-3 FN4) — then equals `.claude`,
  `.claude/`, `.claude/**`, or starts with `.claude/`). The boolean is non-path-revealing (`.claude` is not sensitive),
  stored on `TargetMeta` (`adopt.py:58`) — the raw pattern is never surfaced.
- **Consent (iter-1 FN4 — `manual_review_needed=True`):** NEUTRALIZE mutates the
  owner's `.gitignore` AND overrides a `.claude/` ignore they set deliberately, so
  it ALWAYS needs explicit consent. Under `--auto-accept-recommendations` it still
  prompts; under `--non-interactive` it exits 2. The recommendation report shows
  the **exact 6-line block** that would be appended (no raw target content — the
  block is skill-authored, privacy-safe).

**2B. `sort_key` ordering (S9).** Add an integer `sort_key` to every v2 entry
builder (`manifest.py:168-253`). `plan_adoption_entries` (`manifest.py:256`) sorts
entries by `(sort_key, path)` ascending before returning; `_restore_v2`
(`manifest.py:581`) sorts by `sort_key` **descending** before iterating (restore
reverses apply). Backward-compat: legacy v2 manifests lack `sort_key` → read via
`entry.get("sort_key", 0)` everywhere; a regression test loads a no-`sort_key`
manifest and restores unchanged.

- **Tiers (iter-1 FN1 — corrected ordering):**
  - **0** — all normal mutations, **including APPEND_MERGE on `.gitignore`** (the
    skill-pattern merge). Default for every existing builder.
  - **1** — the NEUTRALIZE `.gitignore` entry. It MUST apply *after* the
    APPEND_MERGE so (a) its sentinel block is the last thing in the file (cleanly
    sentinel-removable on restore) and (b) the APPEND_MERGE's before/after SHAs —
    computed at plan time against the on-disk **original** — stay valid (APPEND_MERGE
    applies first, against that original).
  - **2** — the dependent command-file `WRITE` (`.claude/commands/dev-review.md`),
    after `.gitignore` is fully set up so the file lands git-visible.
- **Why this is correct without virtual-SHA-chaining (iter-2 FN2):** NEUTRALIZE
  carries **no whole-file SHA guard** (its integrity check is the sentinel block —
  see 2C), so the two same-`target_path` entries do NOT need chained SHAs. Apply
  ascending `0→1→2`: APPEND_MERGE (→ `original+patterns`) → NEUTRALIZE appends its
  block (→ `…+block`) → command WRITE. Restore descending `2→1→0`: delete command
  file → NEUTRALIZE **sentinel-removes** its block (→ `original+patterns`,
  independent of any SHA) → APPEND_MERGE sees `original+patterns` (== its stored
  `sha256_after_target_path`) and truncates to `pre_append_length = len(original)`
  → **byte-identical `original`**. APPEND_MERGE keeps its existing SHA guard
  unchanged and valid precisely because NEUTRALIZE restored first.

**2C. NEUTRALIZE entry builder + apply + sentinel-based restore (S10).**
- `_build_v2_neutralize_entry(target_root)` → `policy="NEUTRALIZE"`,
  `target_path=".gitignore"`, `sort_key=1`, recording the **sentinel marker + the
  expected 6-line block text** (for the restore integrity check — NOT a whole-file
  SHA).
- Apply appends the **6-line** block (design note Option B — the
  `!.claude/commands/` intermediate line is required or git can't descend into
  `commands/`):
  ```
  # dev-project-setup: un-ignore the managed /dev-review command below
  !.claude/
  .claude/*
  !.claude/commands/
  .claude/commands/*
  !.claude/commands/dev-review.md
  ```
  Idempotent: appends only if the sentinel comment is absent.
- `_restore_v2_neutralize` (in `_V2_RESTORE_HANDLERS`, `manifest.py:573`) is
  **sentinel-based, not whole-file-SHA** (iter-2 FN2 — resolving the prior
  contradiction): locate the sentinel comment, verify the slice **starting at**
  it matches the recorded `NEUTRALIZE_BLOCK_LINES` (the sentinel comment + 5
  pattern lines = **6 lines total**, iter-4 FN4), then remove exactly those 6
  lines — a 7th line after the block is never consumed (tested). Guard cases:
  - sentinel **absent** → no-op skip (apply was interrupted before NEUTRALIZE, or
    the user already removed it) — benign.
  - block **modified** (lines don't match) → SKIP-with-warning, never clobber the
    user's edit.
  - block **intact** → remove exactly those 6 lines (order-independent vs any
    other append on `.gitignore`).
  *Rejected alternative (Codex's iter-1/2 suggestion):* virtual-SHA-chaining of
  same-path entries. Heavier; the sentinel guard achieves correct,
  user-edit-safe restore with no chaining.

**2D. NEUTRALIZE → two-entry expansion (S10).** A single NEUTRALIZE
*recommendation* on the command file expands, in `plan_adoption_entries`, into
**two** manifest entries: (i) the `.gitignore` NEUTRALIZE entry (`sort_key=1`),
(ii) a `WRITE` for `.claude/commands/dev-review.md` (`sort_key=2`). The
gitignore-neutralize entry is **deduped** (one even if several `.claude/` files
were planned). The report/decide layer shows ONE owner-facing decision
(NEUTRALIZE for the command file) with `manual_review_needed=True`; accepting it
authorizes both entries. The command `WRITE` (entry ii) reuses the normal
`plan_adoption_entries` WRITE parent-directory tracking (`manifest.py:300-306`): if
`.claude/` and/or `.claude/commands/` did not pre-exist, they are added to
`created_directories`, so `_restore_v2`'s reverse-depth empty-dir removal
(`manifest.py:632`) cleans them up — restore returns the target to its true
pre-apply state (no orphan `.claude/` dirs); a pre-existing `.claude/` is NOT
added, so restore leaves it (iter-3 FN3).

**Decide-phase action matrix (iter-4 FN1).** NEUTRALIZE is a new manual-review
policy, so the interactive decide phase must be policy-aware. `cli.py`'s
`_allowed_actions_for` (`cli.py:265`) currently offers `[n]ew`/`[o]verwrite` for
every manual-review file, and the action→policy map (`cli.py:371`) routes them to
`WRITE_NEW`/`OVERWRITE` — both UNSAFE for a NEUTRALIZE target (`n` would create an
ignored `.claude/….new`; `o` assumes the file already exists). For a NEUTRALIZE
recommendation, offer ONLY `[r]ecommended`/`[s]kip`/`[d]iff`/`[?]help`/`[q]uit`;
`n`/`o`/`a` are neither offered nor accepted. Tested in
`tests/test_interactive_decide.py`.

**2E. adopt tests (S11).**
- `tests/test_adopt_engine.py`: NEUTRALIZE for a `.claude/`-class-ignored planned
  command file; rule-a0 SKIP+manual_review for a *broad-pattern* (`*.md`) ignored
  `.claude/commands/dev-review.md` (FN5 / AC4); SKIP+manual_review for a non-`.claude/`
  ignored path (unchanged a0). Parametrize the classifier over `.claude/`,
  `/.claude/`, `.claude/**`, `/.claude/**` (→ NEUTRALIZE) and `*.md` (→ SKIP) (iter-3 FN4).
- `tests/test_interactive_decide.py`: NEUTRALIZE prompts under
  `--auto-accept-recommendations`; exits 2 under `--non-interactive` (FN4); and
  `n`/`o`/`a` are neither offered nor accepted for a NEUTRALIZE target — only
  recommended/skip/diff/help/quit (iter-4 FN1).
- `tests/test_manifest.py`: `sort_key` ascending apply / descending restore;
  legacy-v2 (no `sort_key`) restores unchanged; the NEUTRALIZE builder; the
  two-entry expansion ordering; **interrupted-apply** (block appended but command
  WRITE never ran → restore still byte-identical); **user-edited block** (→
  SKIP-with-warning, no clobber); **created-dir cleanup** — no pre-existing
  `.claude/` → restore removes `.claude/commands/` then `.claude/`; pre-existing
  `.claude/` → restore leaves it (iter-3 FN3).
- `tests/test_mode_adopt_smoke.py`: fixture with an existing `.gitignore`
  containing `.claude/` **and** patterns the skill merges. After
  `--apply --mode=adopt` (consent given): `.gitignore` carries both the skill
  patterns (APPEND_MERGE) and the sentinel unignore block,
  `git check-ignore .claude/commands/dev-review.md` returns no match, the command
  file lands. After `--restore`: `.gitignore` **byte-identical** to pre-apply, the
  command file removed (the FN1 round-trip).

## Architecture decisions

| ID | Decision | Main alternative (rejected) | Why |
|----|----------|-----------------------------|-----|
| D1 | Command named **`dev-review`** at `.claude/commands/dev-review.md` | design note's `dev-project-setup`; PR #10's `.claude/skills/dev-review/SKILL.md` | `dev-project-setup` collides with the bootstrap skill name (registry precedence unverified — iter-1 FN6); `dev-review` is collision-free + descriptive. Slash-command (not skill-dir) is the current Claude Code convention. Overridable at approval. |
| D2 | A **`make review` dispatcher** is the single source of dispatch truth; both the slash command and Codex call it | dispatch logic embedded in the markdown only | iter-1 FN2: the 6-branch behavior must be *automatically* tested; markdown isn't runnable in `make check`. The resolve mode proves all branches deterministically. |
| D3 | Slash command is **Claude-only**; Codex calls `make review` directly via AGENTS.md | a Codex-invocable wrapper / assume Codex reads `.claude/commands` | iter-1 FN3: Codex can't invoke Claude slash commands (`codex --help`). Only Claude has plan-mode exit/return friction; the shared dispatcher gives Codex the same dispatch without a false premise. |
| D4 | `ACTOR` = the mode-specific review **subject** (plan author / commit implementer). `commit` → `ACTOR=claude` (the session implements, by construction); `plan` → the command `AskUserQuestion`s the author (Claude default) — never a silent default. `REVIEWER` is a terminal-only convenience | a silent `ACTOR=claude` default for both modes / rely on `export REVIEWER` persisting across Claude tool calls | iter-3 FN1: a silent default could mis-route a Codex-authored plan. iter-2 FN4: a per-Bash-call `export` does NOT reach later `make`; passing `ACTOR` directly is the only reliable handoff. |
| D5 | Command template is **verbatim** (byte-identical dogfood↔template) via `SHARED_TEMPLATE_MAP` | Jinja-templated per project | Project-agnostic `make` targets; no render vars. Keeps V-21 a simple byte check; avoids a placeholder-truthiness trap (LESSONS.md 2026-05-18). |
| D6 | NEUTRALIZE triggers ONLY on a **`.claude/`-class ignore** (privacy-safe derived boolean), `manual_review_needed=True` | path-under-`.claude/`-plus-any-ignore | iter-1 FN5: a broad `*.md` ignore wouldn't be fixed by the `.claude/` block → must stay conservative SKIP (AC4). iter-1 FN4: mutating the owner's `.gitignore` needs explicit consent. The classifier strips an optional leading `/` so root-anchored `/.claude/` forms match (iter-3 FN4). |
| D7 | NEUTRALIZE restore = **sentinel-block removal with no whole-file SHA guard**; ordering tiers APPEND_MERGE(0) → NEUTRALIZE(1) → command WRITE(2) | virtual-SHA-chaining of same-path entries | iter-1 FN1 + iter-2 FN2: `.gitignore` is mutated by both; a sentinel-only NEUTRALIZE guard + correct ordering make restore byte-identical AND user-edit-safe without chaining (APPEND_MERGE's own SHA guard stays valid because NEUTRALIZE restores first). |
| D8 | One NEUTRALIZE recommendation → **two manifest entries** (gitignore `sort_key=1` + command WRITE `sort_key=2`), gitignore entry deduped; the command WRITE reuses normal parent-dir tracking | one entry mutating two files | One entry mutating two files breaks the per-file manifest/restore contract (design note sub-design 2 Option A). Reusing WRITE dir-tracking lets restore clean created `.claude/` dirs (iter-3 FN3). |
| D9 | `sort_key` integer, default 0; tiers as in D7 | full `depends_on` DAG | Single dependency chain; a DAG is unjustified (design note open-Q2). |
| D10 | Ship Part 1 first (incl. the dogfood `.gitignore` exception); Part 2 separable to PR-2b if the adopt engine destabilizes | one monolithic PR | Greenfield works without NEUTRALIZE; adopt-engine change is the class that ran PR #10 to non-plateau. Honors the architectural-blocker-split advisory. |

## Risks + mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Dispatcher resolves the wrong target / normal-mode invocation broken | imp-3 | 4 resolve-mode tests pin every `ACTOR×MODE` decision + 4 normal-mode faked-CLI tests prove the actual invocation + passthrough (iter-4 FN2); the targets are pinned by `test_makefile_review_targets.py`. |
| NEUTRALIZE target offered unsafe decide actions (`n`/`o`/`a`) | imp-3 | 2D: policy-aware `_allowed_actions_for` — NEUTRALIZE offers only recommended/skip/diff/help/quit; `test_interactive_decide.py` asserts `n`/`o`/`a` rejected (iter-4 FN1). |
| Dogfood command is git-ignored in the skill repo → uncommittable / V-21 reads an untracked file | imp-3 | S3 adds the `.gitignore` un-ignore exception in Part 1 (commit 2); Verification asserts `git check-ignore` returns no match. |
| Dispatcher in Makefile drifts from `shared/Makefile.review.tmpl` | imp-2 | It lives in the `SELFTEST-OVERLAP` block; `test_overlap_makefile_review_section` enforces byte-identity. |
| Wrong-direction review (e.g. a Codex-authored plan reviewed by Codex) | imp-3 | D4: `plan` asks the author (no silent default), `commit` uses the session implementer; the 6-branch command-body assertion pins the exact `make review` forms for both. |
| Dispatch instruction lands in dogfood but not the template (or vice versa) | imp-2 | Per-surface presence asserts cover BOTH dogfood and rendered template. |
| NEUTRALIZE + APPEND_MERGE both touch `.gitignore`; restore leaves residue / clobbers a user edit | imp-3 | D7 sentinel restore (no whole-file SHA) + tier ordering; 2E asserts byte-identical round-trip, interrupted-apply, and user-edited-block → SKIP. |
| NEUTRALIZE silently overrides the owner's deliberate `.claude/` ignore | imp-3 | D6 `manual_review_needed=True`; `--non-interactive` exits 2; report shows the exact block. |
| NEUTRALIZE fires on a broad-pattern ignore the block can't fix → command stays ignored | imp-2 | D6 `.claude/`-class-only trigger; 2E broad-pattern test asserts SKIP. |
| Shared command renders for Node/Go but NEUTRALIZE is Python-only | imp-2 | Node/Go adopt-mode is rejected upstream (`_resolve_mode`); greenfield Node/Go is safe; the residual plain-apply-overwrite-into-existing-`.claude/`-ignoring-repo gap is pre-existing + parked (iter-3 FN2). |
| Restore leaves orphan `.claude/` dirs it created | imp-3 | 2D: the command WRITE reuses normal parent-dir tracking; `_restore_v2` removes empty created dirs; 2E asserts removal when not pre-existing (iter-3 FN3). |
| `sort_key` breaks restore of pre-existing v2 manifests | imp-3 | `entry.get("sort_key", 0)` default; legacy-v2 regression test. |
| `/dev-review` markdown can't be unit-tested for live behavior → dead wrapper | imp-2 | Dispatch decision tested via resolve mode + the command-body form assertion; manual live smoke (both modes) is a required pre-merge gate. |

## Verification

**Automated (all under `make check`):**
1. **Dispatcher** — 4 resolve-mode `ACTOR×MODE` resolutions + unset→`NEEDS-ASK`; **4 normal-mode invocation tests** (faked CLI, sub-target runs + `PLAN_FILE`/`ITERATION` passthrough — iter-4 FN2); `review` is `.PHONY` + appears in `make help` (iter-3 FN5).
2. **V-21** — rendered command template == dogfood `.claude/commands/dev-review.md`.
3. **Dogfood committable** — `git check-ignore .claude/commands/dev-review.md` returns no match after the Part-1 `.gitignore` exception.
4. **Dispatcher byte-identity** — `test_overlap_makefile_review_section` green with the new `review` target in both surfaces.
5. **Dispatch convention presence** — Claude (`/dev-review`; `commit`→direct `ACTOR=claude`, `plan`→asks author) in `CLAUDE.md` + template; Codex (`make review ACTOR=codex`) in `AGENTS.md` + template.
6. **6-branch** — the 4 dispatcher resolutions (item 1; that same item-1 test set also pins the `unset→NEEDS-ASK` routing trigger — plumbing, not a 5th resolution) + the 2 command-body assertions (Other×plan → asks author then emits the chosen form; Other×commit → emits `ACTOR=claude` directly, no ask — iter-3 FN1), never both cross-AI options.
7. **NEUTRALIZE rules** — NEUTRALIZE for a `.claude/`-class-ignored command file (incl. root-anchored `/.claude/` + `/.claude/**`, iter-3 FN4); SKIP+manual_review for a broad-pattern (`*.md`) ignore and for non-`.claude/` ignores (AC4).
8. **NEUTRALIZE consent** — prompts under `--auto-accept-recommendations`; exit 2 under `--non-interactive`; report shows the 6-line block.
9. **sort_key + restore** — ascending apply / descending restore; legacy-v2 (no `sort_key`) restores unchanged; interrupted-apply + user-edited-block cases.
10. **NEUTRALIZE round-trip** — adopt smoke with a `.claude/`-ignoring `.gitignore` (+ skill patterns): after apply both present and the command file git-visible; after restore `.gitignore` byte-identical, the command removed, and created `.claude/`/`.claude/commands/` dirs removed when not pre-existing (iter-3 FN3).
11. Full `make check` green. Run `make format` before every commit (no pre-commit hook here — LESSONS.md 2026-05-30).

**Manual (cannot be in `make check`):**
12. **Live smoke (both modes)** — from a real Claude session: invoke
    `/dev-review plan <PLAN_FILE>` in plan mode, confirm it runs
    `make review MODE=plan ACTOR=claude …` → `review-plan-by-codex` with no
    exit-plan-mode cycle; invoke `/dev-review commit`, confirm
    `→ review-commit-by-claude`; and an ambiguous-author invocation → confirm the
    `AskUserQuestion` fallback. (Codex side is the deterministic
    `make review ACTOR=codex` path — no slash command to smoke.) `make status`
    Health checks confirm `claude`+`codex`.

**Stop rule (docs/plans/README.md):** large/cross-cutting ⇒ ~3 cross-review
iters; stop when no importance-3 remains and 1/2 findings are folded or
explicitly accepted. Consistency self-check at N.5 after each fold.

## Implementation rollout

One implementation PR referencing this plan; Part 1 lands before Part 2.

| Commit | Lands | Tests added |
|--------|-------|-------------|
| 1 | Part 1A: `make review` dispatcher + resolve mode (Makefile + `shared/Makefile.review.tmpl`) | dispatcher resolutions (S2) |
| 2 | Part 1B: `/dev-review` dogfood + verbatim template + `SHARED_TEMPLATE_MAP` + the skill-repo `.gitignore` un-ignore exception | V-21 overlap (S4) + `git check-ignore` assertion (S3) |
| 3 | Part 1C/1D: dispatch convention in CLAUDE.md + AGENTS.md + templates; command-body 6-branch + invocation-form assertion | presence asserts (S6) + the S7 command-body assertion (the 4 dispatcher resolutions already landed in commit 1) |
| 4 | Part 2A: NEUTRALIZE `Policy` + `.claude/`-class classifier on `_check_ignored_by_git`/`TargetMeta` + `recommend_policy` trigger + `manual_review_needed=True` | recommend rules + consent (S11) |
| 5 | Part 2B: `sort_key` on builders + plan ascending / restore descending + legacy-v2 compat | sort ordering + legacy compat |
| 6 | Part 2C/2D: NEUTRALIZE builder + apply + sentinel restore + two-entry expansion | builder/sentinel-restore (incl. interrupted/user-edit) /expansion units |
| 7 | Part 2E: adopt round-trip smoke | round-trip smoke (S11) |
| 8 | Docs: `/dev-review` usage in `docs/usage.md` (Part 1) + the NEUTRALIZE-adopt + round-trip manual smoke recipe (Part 2) + impl-log rows | — |

**Part-2 split contingency (D10):** if commit 4 surfaces an adopt-engine contract
problem the design note didn't anticipate that would take >1 iter of architecture
rework, STOP, land Part 1 (commits 1-3 + the Part-1 half of commit 8 — the
`/dev-review` usage doc) as PR-2, and re-file Part 2 (commits 4-7 + the Part-2 half
of commit 8 — the NEUTRALIZE/round-trip smoke recipe) as PR-2b with the surfaced
blocker as its starting requirement. Part 1 is self-contained: the dogfood
`.gitignore` exception (commit 2) lets the command land in the skill repo without
any NEUTRALIZE machinery. Tier-1 (fresh Claude subagent) reviews every commit
before push; Tier-2 bots review the PR.

## Iteration log (this plan)

| Iter | Reviewer | Date | Counts (3/2/1) | Verdict | Notes |
|------|----------|------|----------------|---------|-------|
| 0.5 | Fact-check (deterministic + Codex interp) | 2026-05-31 | 0 / 1 / 0 | no imp-3 — proceed | Deterministic `verify-plan-facts.py`: **35/35 existing-code anchors verified clean** (`adopt.py:29/144/419`, `manifest.py:14/256/573/581`, `render.py:9`, all make targets + files in range). 6 "failed" = files PR-2 *creates* (5) + the superseded PR #10 `.claude/skills/dev-review/SKILL.md` (1) — not drift. 1 `not_verifiable` = `--restore` (verifier defers CLI-flag semantics by design). Codex: no imp-3; one imp-2 hygiene (V-21 bare basename) → folded path-explicit. |
| 1 | Codex (cross-direction) | 2026-05-31 | 4 / 2 / 0 | do-not-implement | All 6 folded (a) after four-questions triage. **FN1** (imp-3) NEUTRALIZE+APPEND_MERGE broke `.gitignore` restore — corrected `sort_key` tiers APPEND_MERGE(0)→NEUTRALIZE(1)→WRITE(2) + sentinel restore (simpler than Codex's virtual-SHA-chaining). **FN2** (imp-3) 6-branch gate was text-parsing only — added the tested `make review` dispatcher + resolve mode. **FN3** (imp-3) Codex can't invoke a Claude slash command — narrowed slash command to Claude; Codex uses `make review` directly. **FN4** (imp-3) NEUTRALIZE consent unspecified — `manual_review_needed=True`. **FN5** (imp-2) trigger over-fired on broad ignores — `.claude/`-class-only. **FN6** (imp-2) name collision — renamed to `/dev-review`. |
| 1.5 | Claude (consistency self-check; rounds a–b) | 2026-05-31 | doc-drift 6 → 4 | folded + driver-exit | Substantive invariants confirmed consistent BOTH rounds. Round a (6): resolve-vs-normal exit code; manifest `:573`/`:581`; verbatim-vs-Jinja; commit-3 label; + an *incomplete* 6-branch reconciliation. Round b (4; run after round-a edits to refresh the loop marker) caught round-a's 6-branch note **over-claimed** — reframed: 6 branches = 4 dispatcher resolutions + 2 command-body Other-asserts, the mode-agnostic `unset→NEEDS-ASK` is the routing trigger not a branch; + `ACTOR`-unset referent; + commit-8 docs split; + `render.py:9` precision. Driver-exit (body clean). |
| 2 | Codex (cross-direction) | 2026-05-31 | 2 / 2 / 0 | do-not-implement | imp-3 4→2 (downward). All 4 folded (a). **FN1** (imp-3) the **dogfood** command is git-ignored in *this* repo (`.gitignore:50` = `.claude/`; `git check-ignore` confirmed) → Part 1 adds the un-ignore exception to the skill repo's own `.gitignore` (dogfoods Part-2 NEUTRALIZE); Verification asserts it (Subsystem caveat, 1B, S3, rollout 2, D10, Risks). **FN2** (imp-3) my 2C had a contradiction — claimed "no virtual-SHA-chaining" yet "same SHA-mismatch guard as other handlers"; resolved: NEUTRALIZE restore is **sentinel-based with NO whole-file SHA guard** (APPEND_MERGE's SHA stays valid because NEUTRALIZE restores first) + interrupted/user-edit tests (2B/2C/2E/D7). **FN3** (imp-2) `/dev-review` arg contract undefined → defined `plan [PLAN_FILE] [ITERATION]` / `commit` + form assertions + both-mode smoke (1B/1D/S7/S12/Verification 6/12). **FN4** (imp-2) `export REVIEWER` doesn't persist across Claude tool calls → command passes `ACTOR=claude` directly; REVIEWER is terminal-only (Context/1A/1C/S5/D4). |
| 2.5 | Claude (consistency self-check) | 2026-05-31 | doc-drift × 4 | folded + driver-exit | Substantive invariants confirmed consistent (exit codes, 6-line block, `0→1→2`/`2→1→0` ordering, sentinel restore + APPEND_MERGE-SHA-stays-valid, all `adopt.py`/`manifest.py`/`render.py`/`.gitignore` anchors). 4 surface drifts folded: (1) D7 rejected-alt listed "byte-length truncation" which 2C never rejects → trimmed to virtual-SHA-chaining; (2) 1B "explicit actor token" had no slot in the `plan [PLAN_FILE] [ITERATION]` contract → clarified the override is always via `AskUserQuestion` (no positional actor token); (3) 1B merged "who authored/implemented" → split mode-specific (plan→author, commit→implementer) to match S7/1D; (4) Verification-6 parenthetical could read `NEEDS-ASK` as a 5th resolution → clarified it's plumbing. Driver-exit (1 round; body clean). |
| 3 | Codex (cross-direction) | 2026-05-31 | 3 / 2 / 0 | do-not-implement | imp-3 2→3 (wobble — non-plateau zone; all findings real, not re-litigation). All 5 folded (a); FN1 was the recurring one, now nailed. **FN1** (imp-3) ACTOR conflated session-AI with the review subject → made it **mode-asymmetric**: `commit`→`ACTOR=claude` (session implements, by construction), `plan`→ask the author (no silent default that could mis-route a Codex-authored plan); refines design-note Other×commit (Context/1B/1C/1D/D4/Risks). **FN2** (imp-3) shared command renders for all langs but NEUTRALIZE is Python-only → clarified Node/Go adopt is rejected by `_resolve_mode` (no path to break), greenfield safe, residual plain-apply gap pre-existing + parked (Context/NOT-in-scope/Risks). **FN3** (imp-3) restore didn't clean created `.claude/` dirs → command WRITE reuses normal parent-dir tracking (2D/2E/D8/Risks/Verification 10). **FN4** (imp-2) classifier missed root-anchored `/.claude/` → strip optional leading `/` (2A/2E/D6/Verification 7). **FN5** (imp-2) `review` not in `.PHONY`/help → declared `.PHONY` + `##` help + target-list tests (1A/S2/Verification 1). |
| 3.5 | Claude (consistency self-check) | 2026-05-31 | doc-drift × 3 (1 substantive) | folded + driver-exit | All substantive invariants confirmed consistent (exit codes, 6-line block, sort_key tiers + reverse restore, sentinel-not-SHA + APPEND_MERGE-SHA-valid, `/`-stripping classifier, two-entry+dir-tracking, all anchors, REVIEWER terminal-only). **Substantive (1):** the iter-3 FN1 fold updated 1B/1D/D4/Risks to "commit → ACTOR=claude, no ask" but **missed S7 + Verification 6** (still "Other×commit → asks implementer") → reconciled both to the mode-asymmetry. Cosmetic (2): Verification-5 clarified (direct for commit, asks for plan); 1A Inputs `ACTOR ∈ {claude, codex, unset}`. Driver-exit. |
| 4 | Codex (cross-direction) | 2026-05-31 | 2 / 3 / 0 | do-not-implement → **DRIVER-STOP** | imp-3 trajectory **4→2→3→2 — NOT plateauing** (PR #10's non-plateau pattern; findings genuine, not re-litigation). **2 imp-3 FOLDED** (real integration/test gaps): **FN1** NEUTRALIZE needs a policy-aware decide-phase action matrix (`cli.py:265`/`:371`) — offer only recommended/skip/diff/help/quit, never the unsafe `n`/`o`/`a` (2D/2E/S10/Risks/Verification). **FN2** resolve-mode tests prove the decision but not normal invocation → added 4 faked-CLI normal-mode tests asserting the sub-target runs + `PLAN_FILE`/`ITERATION` passthrough (1A/S2/Verification 1/Risks). **3 imp-2 FOLDED at the approval gate** (before commit): FN3 (AGENTS.md tells Codex to pass `ACTOR=codex` **inline**, not `export REVIEWER` — same fresh-shell trap; 1C), FN4 (sentinel block off-by-one — `NEUTRALIZE_BLOCK_LINES` = comment + 5 patterns = 6 lines; no-over-consume test; 2C), FN5 (docs/usage.md normative adopt-rule + v2-restore tables get a NEUTRALIZE row + a doc-sanity assert; S12). **DRIVER-STOP** (per CONTRIBUTING "do not iterate as a ritual" + the meta-plan anti-bloat lesson + the PR #10 precedent where the driver stopped a non-plateauing loop): all imp-3 across iters 1-4 are folded; the loop's residual findings are increasingly implementation/Tier-1 territory; the 3 captured imp-2 + final cross-ref tidying land as the first implementation commits, caught by the two-tier discipline. |

**Loop outcome (driver-stop after iter 4).** 4 Codex cross-reviews + a fact-check
pre-pass + 4 Claude consistency self-checks. imp-3 trajectory **2(fc=0)→4→2→3→2**;
the loop never reached 0 imp-3 and is not plateauing — the PR #10 pattern the
meta-plan explicitly warns about. **All imp-3 findings (iters 1-4) are folded.**
The 3 iter-4 imp-2 (FN3/FN4/FN5) were folded at the approval gate before commit. The genuine plan-level architecture (dispatcher,
Claude-only slash command, mode-asymmetric `ACTOR`, NEUTRALIZE policy + consent +
`.claude/`-class trigger, sentinel restore + tier ordering, two-entry expansion +
dir-tracking) is settled; the remaining residue is implementation/Tier-1
territory. Per CONTRIBUTING's stop rule + the PR #10 driver-stop precedent, the
loop is stopped here for the human-approval gate.

## Evidence table — what was folded and where

| Source | Finding | Importance | Resolution | Touched sections |
|--------|---------|------------|------------|------------------|
| Fact-check iter 0.5 (Codex interp) | V-21 named the template by bare basename — ambiguous vs full `shared/` path | 2 | Made 1B path-explicit | Subsystem 1B/S4 |
| Codex iter-1 FN1 | NEUTRALIZE + APPEND_MERGE both mutate `.gitignore`; APPEND_MERGE's original-based SHA breaks restore when NEUTRALIZE applied first | 3 | Corrected `sort_key` tiers (0/1/2) so APPEND_MERGE applies first (SHA valid) and NEUTRALIZE's sentinel block is last | 2B, 2C, 2D, D7, D9 |
| Codex iter-1 FN2 | 6-branch gate downgraded to static markdown parsing; design note requires an automated invocation test | 3 | Added the `make review` dispatcher + `REVIEW_RESOLVE` mode; 4 resolutions tested deterministically | 1A, 1D, S1/S2/S7, D2 |
| Codex iter-1 FN3 | Plan assumed Codex invokes a Claude `.claude/commands` slash command; no such mechanism | 3 | Slash command Claude-only; Codex calls `make review ACTOR=codex` directly via AGENTS.md | Context, 1C, S5, D3, NOT-in-scope |
| Codex iter-1 FN4 | NEUTRALIZE consent (`manual_review_needed`) unspecified | 3 | `manual_review_needed=True`; report shows the 6-line block; auto-accept/non-interactive tests | 2A, 2E, D6, S8/S11 |
| Codex iter-1 FN5 | Path-based trigger over-fires on a broad-pattern ignore (e.g. `*.md`) | 2 | Trigger restricted to `.claude/`-class via a privacy-safe derived boolean; broad → SKIP (AC4) | 2A, 2E, D6, S8 |
| Codex iter-1 FN6 | `/dev-project-setup` collides with the bootstrap skill name | 2 | Renamed the command to `/dev-review`; surfaced for override at approval | Context, D1, all path refs |
| Codex iter-2 FN1 | The **dogfood** `.claude/commands/dev-review.md` is git-ignored in THIS repo (`.gitignore:50`) → not committable; Part 1 not shippable as written | 3 | Part 1 appends the un-ignore block to the skill repo's own `.gitignore` (dogfoods Part-2 NEUTRALIZE); `git check-ignore` verified | Subsystem caveat, 1B, S3, rollout 2, D10, Risks, Verification 3 |
| Codex iter-2 FN2 | 2C contradiction: "no virtual-SHA-chaining" but "same SHA-mismatch guard as other handlers" — APPEND_MERGE-before-NEUTRALIZE makes a NEUTRALIZE after-SHA un-matchable | 3 | NEUTRALIZE restore is **sentinel-based, no whole-file SHA**; APPEND_MERGE's SHA guard stays valid because NEUTRALIZE restores first; + interrupted-apply + user-edited-block tests | 2B, 2C, 2E, D7, Risks, Verification 9 |
| Codex iter-2 FN3 | `/dev-review` argument contract (plan vs commit, PLAN_FILE, ITERATION) undefined | 2 | Defined `/dev-review plan [PLAN_FILE] [ITERATION]` and `commit`; command-body asserts the exact `make review` forms; both-mode manual smoke | 1B, 1D, S7, S12, Verification 6/12, rollout 3 |
| Codex iter-2 FN4 | `export REVIEWER=claude` in one Bash tool call doesn't persist to later calls/`make` — handoff fragile | 2 | The Claude command passes `ACTOR=claude` directly; `REVIEWER` is a terminal-only convenience | Context, 1A, 1C, S5, D4, Verification 5/12 |
| Codex iter-3 FN1 | ACTOR conflated "current Claude session" with the plan author / commit implementer → a silent `ACTOR=claude` default could mis-route a Codex-authored plan | 3 | Made ACTOR a **mode-asymmetric subject**: `commit`→claude (session implements), `plan`→ask the author (Claude default). Refines design-note Other×commit | Context, 1B, 1C, 1D, D4, S7, Risks, Verification 6/12 |
| Codex iter-3 FN2 | Command renders for all langs (`SHARED_TEMPLATE_MAP`) but NEUTRALIZE is Python-only → Node/Go could write an invisible command | 3 | Clarified: Node/Go adopt is rejected by `_resolve_mode` (no path); greenfield safe; the residual plain-apply-overwrite gap is pre-existing + parked | Context, NOT-in-scope, Risks |
| Codex iter-3 FN3 | Restore didn't prove cleanup of `.claude/`/`.claude/commands/` dirs the command WRITE creates → orphan dirs | 3 | Command WRITE reuses `plan_adoption_entries` parent-dir tracking; `_restore_v2` removes empty created dirs; created-vs-pre-existing tests | 2D, 2E, D8, Risks, Verification 10 |
| Codex iter-3 FN4 | `.claude/`-class classifier missed root-anchored `/.claude/`, `/.claude/**` | 2 | Strip an optional leading `/` before classification; parametrized tests | 2A, 2E, D6, Verification 7 |
| Codex iter-3 FN5 | New `review` dispatcher not pinned for `.PHONY` / `make help` discoverability | 2 | Declared `.PHONY` + `##` help; per-language target-list tests assert `make help` lists it | 1A, S2, Verification 1 |

## Implementation log (this PR)

| short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |
|-----------|----------------------|---------------------------------|-------------------------|
| _(populated during implementation; Tier-1 proposes each row)_ | | | |

## Lessons surfaced (this PR)

_(reviewer-proposed lessons triaged later → real ones to LESSONS.md)_

## Critical files to read before each iter's review

- [docs/design-notes/2026-05-29-bucket-a-architecture.md](../design-notes/2026-05-29-bucket-a-architecture.md) — the 3 sub-designs (options + rejected + acceptance criteria). NOTE: this plan refines it where its premises missed — Codex can't invoke a Claude slash command (FN3), NEUTRALIZE must be `.claude/`-class-only for AC4 (FN5), the dogfood command needs a skill-repo `.gitignore` exception (iter-2 FN1), NEUTRALIZE restore is sentinel-based not SHA (iter-2 FN2), and the command is renamed `dev-review` (FN6).
- `bootstrap_lib/adopt.py` — `Policy` (`:29`), `TargetMeta` (`:58`), `recommend_policy` rule-a0 (`:419`), `_check_ignored_by_git` (`:144`, drops the pattern for privacy — extended with a derived `.claude/`-class boolean).
- `bootstrap_lib/manifest.py` — v2 entry builders (`:168-253`), `plan_adoption_entries` (`:256`), `_V2_RESTORE_HANDLERS` dict (`:573`) registered just before `_restore_v2` (`:581`); APPEND_MERGE restore SHA-gate at `:558-565`; `EXECUTABLE_TARGETS` (`:14`).
- `bootstrap_lib/render.py` — `SHARED_TEMPLATE_MAP` (`:9`, dict spans `:9-27`).
- `Makefile` + `shared/Makefile.review.tmpl` — the `SELFTEST-OVERLAP-BEGIN/END` block (`Makefile:78-461`) where the `review` dispatcher lands; existing `review-plan-by-*` / `review-commit-by-*` targets it dispatches to.
- `.gitignore` (`:50` = `.claude/`) — the dogfood ignore the Part-1 exception un-ignores.
- `tests/test_selftest_overlap.py` — `_assert_byte_equal` (V-21) + `test_overlap_makefile_review_section` (dispatcher byte-identity).
- `tests/test_makefile_review_targets.py` — where the dispatcher resolve-mode tests land.
- `tests/test_dogfood_doc_sanity.py` — the presence-assertion pattern S6/S7 follow.
- `CLAUDE.md` / `AGENTS.md` (+ `shared/*.tmpl`) — dispatch-convention insertion points; AGENTS.md has no approval-gate paragraph.
- `~/.claude/plans/what-else-i-want-majestic-rain.md` — meta-plan PR-2 section + the 6-branch verification gate.
