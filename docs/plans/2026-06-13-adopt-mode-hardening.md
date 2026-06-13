# Adopt-mode hardening (validated by the Telegram-bot port)

## Context

`--mode=adopt` (`bootstrap_lib/cli.py:_main_apply_adopt`, dispatched from
`main()` ~862) is the skill's path for bringing its machinery into a project
that **already has its own config** — as opposed to greenfield `--apply`, which
writes into an empty/clean directory. Adopt runs a per-file analyze →
recommend → owner-consent → apply pipeline (`bootstrap_lib/adopt.py` is the
analyze+recommend engine; `recommend_policy` applies rules a0/a..h in order).

This plan hardens adopt mode in the skill, using the **live Boxette Telegram
bot** (`~/Desktop/Code/Boxette/Telegram bot`) as a real-project acceptance
test. The bot is an ideal target: it adopted an **early (PR #1-era, 2026-05-15)
version of the skill** and is now badly stale — its `Makefile` still has the
old Codex-only `review` / `review-plan` targets (pre `-by-codex`/`-by-claude`
split), and its `AGENTS.md`/`CLAUDE.md` carry **none** of the current skill
markers (triage rule, two-tier review, loop machinery). It is pip/venv-based
(not uv), under git on `main` (reversible), and holds **real secrets**
(`.env`, `boxette.db`, `data/`).

### Ground-truth evidence (read-only analyze against the live bot)

Running `adopt.analyze_target` against the bot (python, pip, github-review=none;
analyze writes nothing) produces this exact outcome over 23 planned files:

| Policy | Files | Assessment |
|---|---|---|
| WRITE | `src/main.py`, `tests/test_smoke.py` | **BUG — greenfield-only placeholders into a real project** (Bucket A) |
| WRITE | `scripts/{loop-status,extract-plan-facts,verify-plan-facts,extract-codex-session-id,propagate-shared-rules,run-with-clean-env}.py` | **BUG — orphaned: their Makefile targets are SKIPped** (Bucket B) |
| WRITE | `.editorconfig`, `LESSONS.md` | correct (genuinely new) |
| APPEND_MERGE | `.gitignore` | correct |
| NEUTRALIZE (manual) | `.claude/commands/dev-review.md` | correct — bot gitignores `.claude/`; verify-only |
| WRITE_NEW (manual) | `AGENTS.md`, `BACKLOG.md`, `CLAUDE.md`, `CONTRIBUTING.md` | correct (preserve domain content as `.new`) |
| SKIP (manual) | `Makefile`, `pyproject.toml`, `.pre-commit-config.yaml`, `requirements-dev.txt`, `.github/pull_request_template.md`, `.github/workflows/ci.yml`, `docs/plans/README.md` | safe |

`shadowing_configs` is empty — the bot keeps ruff/pytest config inside
`pyproject.toml` (no `ruff.toml`/`pytest.ini`), so the rule-(g) SKIP is the only
config-merge surface and the existing SKIP+advisory is the safe outcome.

### The three real gaps the bot exposes

1. **Greenfield-only placeholders land in a real project.** `src/main.py`
   (`print("hello from …")`) and `tests/test_smoke.py` (`assert True`) are
   render-map entries (`bootstrap_lib/render.py:38-39`) emitted unconditionally.
   Adopt classifies them rule-(a) WRITE because the bot has neither (its package
   is `bot/`, its tests are real). A stray hello-world module + a trivial
   always-pass test get written into production code.

2. **The plan-review machinery is delivered incoherently.** The entire
   plan-review automation (the dispatcher + `loop-status` / `review-plan-by-codex`
   / `review-plan-by-claude` / consistency targets) lives **inline inside the
   single generated `Makefile`** via `{% include 'Makefile.review.tmpl' %}`
   (`languages/python/Makefile.tmpl:75`). Adopt SKIPs an existing `Makefile`
   (rule h), so **none** of those targets land — yet the six `scripts/*.py` the
   targets call **do** land (rule a). The owner gets six scripts nothing invokes.
   This is the heart of "bring the machinery in": today it brings in half of it.

3. **The adopt success path omits all post-apply guidance.**
   `_main_apply_adopt`'s success block (`cli.py:744-748`) prints only the
   mutated-entry count + restore hint. The v1 `--apply` success path
   (`cli.py:901-1008`) additionally prints next-steps, the `gh repo create`
   hint (when `--github-review != none`), the `CLAUDE_CODE_OAUTH_TOKEN` secret
   step, and the both-docs Codex hint. Adopt users see none of it. (This is the
   parked BACKLOG item "Mirror the gh-repo-create hint into adopt-mode's `_main_apply_adopt`";
   its trigger — "the next PR that touches `_main_apply_adopt`'s success block" —
   fires here.)

### Pre-coding declarations (CONTRIBUTING.md)

- **Regression safety**: auto-testable. Every bucket gets a synthetic
  bot-shaped fixture test (existing Makefile + non-trivial pyproject + domain
  Markdown docs + `.gitignore` ignoring `.claude/` + existing source package + tests)
  plus the existing `make check` suite (baseline 1005 passed / 4 skipped) stays
  green. Final acceptance is a three-step gate (no adopt "dry-run" CLI mode
  exists — `cli.py:110` rejects `--mode=adopt` without `--apply`, and a
  "piped-SKIP" run still auto-applies every non-manual rule-(a) WRITE): (1)
  read-only preview via an `adopt.analyze_target` + `format_recommendation_report`
  harness (writes nothing — the same call used to gather this plan's evidence);
  (2) real `--apply --mode=adopt` against a **`cp -R` throwaway copy** of the
  bot, driven by a **scripted stdin** that accepts each recommendation (the bot
  has ~12 manual-review files, so an unscripted run would hang — iter-2 FN3) —
  writes are safe on a copy — and inspect the result; (3) only after 1-2 are
  clean, the live bot, gated per R-SAFETY (live is driven interactively, per
  file — not the scripted accept used on the copy).
- **Outcome measurement**: no business metric — internal tooling change. The
  user-facing outcome is "adopt mode produces coherent, non-harmful output on a
  real existing project," verified by the bot acceptance test, not a metric.

## Scope

### IN scope

| # | Item | Bucket |
|---|---|---|
| 1 | Suppress greenfield-only placeholders (`src/main.py`, `tests/test_smoke.py`) in **Python** adopt mode (folds the parked BACKLOG item "Adopt-mode skips the greenfield smoke placeholders for an existing project") — adopt is Python-only (`cli.py` rejects `--mode=adopt --language nodejs\|go`); the shared constant lists the Node/Go stub names too so suppression is already correct when their adopt ships, but no behavior changes for them now | A |
| 2 | Deliver the plan-review machinery to an existing-Makefile project coherently — factor it into a standalone `Makefile.review` include in adopt mode + emit a post-apply `include` hint | B |
| 3 | Give `_main_apply_adopt` post-apply guidance parity with the v1 path via a single shared helper (folds the parked gh-repo-create mirror item) | C |
| 4 | Verify (not fix) the NEUTRALIZE `.claude/` un-ignore path on the bot acceptance test (verification-only — covered in Verification step 3, no Bucket change) | Verify |

### NOT in scope (parked — see BACKLOG triggers)

| Item | Why parked / why it doesn't fire on the bot |
|---|---|
| **Re-adopt / upgrade detection** (the bot adopted an old skill version; adopt has no notion of "already adopted me, here's the delta") | Large new feature (track prior adoption manifest, diff against it). Deepest finding — recorded as a **new BACKLOG cluster + candidate future plan**, not built here. |
| Path-safety refuse-by-default for sensitive target paths (`.env`, `data/`, `*.db`) | **Does not fire**: no planned file targets those paths; blast radius on the bot's secrets is already zero. Existing BACKLOG item; defense-in-depth only. |
| TOML section-merge into an existing `pyproject.toml` | SKIP+advisory is the safe outcome; `shadowing_configs` empty on the bot. Existing BACKLOG item. |
| `tox.ini`/`setup.cfg`/nested standalone-config shadow scan | Bot has none. Existing BACKLOG items. |
| Node/Go config-file shadowing | Python-only pass. Existing BACKLOG item. |
| CRLF ↔ append-merge line-ending parity | macOS LF target; does not fire. Existing BACKLOG item. |
| `pre-commit` into target dev-deps / uv-vs-pip `install-hooks` | **Does not fire**: bot already has `pre-commit` in `requirements-dev.txt`; its Makefile is SKIPped so the skill's `install-hooks` never lands. Existing BACKLOG item. |
| Refine the rule-(g) pyproject SKIP advisory wording | Cosmetic; the SKIP is correct. Park unless the loop/human elevates it. |
| Retarget the adopt-rendered `Makefile` `run:` target away from the suppressed `src/main.py` (the no-Makefile subcase) | Existing BACKLOG item ("adopt run hardcoded to src/main.py"). **The bot does not exercise it** — the bot owns a Makefile, so its `run:` is SKIPped, not written. Only fires when adopting into a project with source but no Makefile. De-claimed in Bucket A/B; left as a known residual (iter-1 FN3). |
| A read-only adopt-policy preview CLI mode (`--mode=adopt` without `--apply`, or annotated `--diff`) | Folds with the existing BACKLOG "annotate `--diff` headers with adopt policy" item. The `analyze_target` harness covers this plan's verification need with zero new CLI surface; a real preview command is a separate UX enhancement (iter-1 FN1). |

## Subsystem breakdown

### Bucket A — suppress greenfield-only placeholders in adopt mode

**Problem.** `render_all` emits per-language entrypoint+smoke stubs
unconditionally: python `src/main.py` + `tests/test_smoke.py`; nodejs
`src/main.ts` + `tests/test_smoke.test.ts`; go `main.go` + `main_test.go`
(`render.py` template maps). In adopt mode these are never wanted — adopt is by
definition into a project that already has source and tests.

**Change.** Define a per-language `GREENFIELD_ONLY_PLACEHOLDERS` set (the
entrypoint + smoke-test stubs) and filter them out of the planned-files set
**in the adopt path only** (greenfield keeps them). Cleanest seam: filter in
`_main_apply_adopt` after `render`/context build and before `analyze_target`,
or expose an `adopt=True` flag to a render-layer filter helper — decided at
implementation; the contract is "adopt-mode planned files never include the
greenfield stubs." This closes the parked BACKLOG item "Adopt-mode skips the
greenfield smoke placeholders for an existing project" (PR #7 follow-up).

**Decision AD1** — *unconditional* suppression in adopt mode, not conditional
on whether the target already has source. Alternative: only suppress when the
target has existing source/tests. Rejected: an existing project that happens to
lack `src/main.py` still does not want a hello-world stub from an adopt run; the
conditional adds detection complexity for no real benefit.

**Reachability + a coupled residual (iter-1 FN3/FN4).** Adopt is Python-only
today, so only the Python stubs are reachable; the constant lists the Node/Go
names for free correctness when their adopt ships. Suppressing `src/main.py`
*couples* to the base Makefile's `run: … src/main.py` recipe: in the **bot's
case the Makefile is SKIPped** (the bot owns one), so its `run:` is never
written and there is no breakage. The only place the coupling bites is adopting
into a project with source but **no** Makefile (base Makefile is rule-(a) WRITE,
inlining a `run:` that now points at the suppressed stub). That `run:`-retarget
is **parked** (existing BACKLOG item; not exercised by the bot) — this PR does
not claim to fix it (see Bucket B's de-claimed coherence note).

**Verification.** Fixture: adopt against a dir with an existing source package →
assert no `src/main.py` / `tests/test_smoke.py` in the plan. Bot acceptance:
those two rows disappear from the analyze output.

### Bucket B — coherent delivery of the plan-review machinery

**Problem.** The machinery's Makefile targets are inlined into the single
`Makefile` via a render-time Jinja `include`; an existing Makefile is SKIPped,
so the targets never arrive while the scripts they call do. The skill already
factors the machinery as a self-contained fragment
(`shared/Makefile.review.tmpl` — a macro + a sentinel-delimited
`SELFTEST-OVERLAP` block), which is exactly an includable unit.

**Change (recommended — AD2).** In **adopt mode**, when the target owns a
`Makefile` (rule-(h) SKIP — the bot's case), deliver the machinery as a
standalone `Makefile.review`:
- Add a standalone-rendered `Makefile.review` to the adopt planned-files; it
  classifies rule-(a) WRITE (the bot lacks it). Emit it **only when the base
  `Makefile` is SKIPped**. When the target has NO Makefile (base Makefile is
  rule-(a) WRITE), keep today's behavior — the written Makefile already inlines
  the review block via `{% include 'Makefile.review.tmpl' %}` — and DROP the
  redundant standalone copy. This is a post-analyze conditional keyed on the
  base Makefile's recommendation, which avoids the "render the base Makefile
  without its include" complication entirely.
- **Sequencing contract (iter-2 FN1).** `manifest.plan_adoption_entries` raises
  `ValueError` for any analysis whose `rel_path` is absent from `planned_files`
  (`manifest.py:383`), and conversely only writes paths present in the analyses
  tuple. So the drop must remove `Makefile.review` from **both** the final
  `planned_files` dict **and** the `AdoptionPlan.analyses` tuple, atomically,
  **before** the report / prompt / manifest build. Two-phase shape: (1)
  provisionally render `Makefile.review` into `planned_files` and run
  `analyze_target`; (2) if the base `Makefile` is rule-(a) WRITE, prune the
  entry from both structures (keep otherwise). A partial fold that touched only
  one structure would either raise at manifest time or silently omit the file
  from the report/manifest.
- Emit a post-apply hint (Bucket C's guidance helper) **only in the SKIP
  subcase**: *"add `include Makefile.review` to your Makefile, and remove your
  stale `review` and `review-plan` targets — the fragment's `review` dispatcher
  (which name-collides with yours) and `review-plan-by-{codex,claude}` replace
  them."* (Only the bare `review:` truly name-collides; `review-plan` is
  superseded — see R-B1.)

This fixes the subcase the bot exercises (target owns a Makefile): the six
scripts now have a home — the standalone `Makefile.review` the owner includes.
The no-Makefile subcase is **unchanged** (its Makefile already inlines the
machinery) except for the parked `run:`-target residual noted in Bucket A; this
PR does **not** claim coherence there.

**Alternatives considered.**
- *Warn-only* (B-alt-1): emit nothing extra; just warn that the scripts are
  unwired and point at docs. Lower risk, but leaves adopt mode delivering
  orphaned scripts — fails the hand-off's "bring the machinery in" intent.
- *APPEND_MERGE into the target Makefile* (B-alt-2): **rejected** — Makefiles
  are tab- and target-sensitive; line-level merge is unsafe (target-name
  collisions, recipe corruption).
- *Suppress the scripts when the Makefile is SKIPped* (B-alt-3): conservative
  but throws away the skill's core value in adopt mode.

**Risk R-B1 (target-name collision + superseded targets on `include`).**
`shared/Makefile.review.tmpl` is the full plan-review machinery — a bare
**`review:`** dispatcher (line 79), the cross-direction
`review-plan-by-{codex,claude}` + `review-commit-by-{codex,claude}` +
`review-plan-consistency-by-claude` targets, the `loop-{status,ack,reset}` +
`status` helpers, and the `review-plan-fact-check-by-*` pre-pass. Exactly one
name-**collides** with the live bot Makefile: the bare `review:` (bot line 102
vs fragment line 79) — two recipes make GNU Make warn *"overriding recipe for
target 'review'"* and silently keep the last. The bot's older `review-plan:`
does **not** name-collide (the fragment's are `-by-*`-suffixed) but is
**superseded** by them; `review-uncommitted:` is the bot's own quick-review,
orthogonal. Variables are safe (`PLAN_FILE ?=` / `ITERATION ?=` are
conditional-assign). Mitigation: (1) the include hint names the stale targets to
remove — `review` (the true collision) and `review-plan` (superseded) — leaving
`review-uncommitted` to the owner; (2) implementation computes the **actual
overlapping target names** (fragment targets ∩ the target Makefile's targets)
and passes them as `colliding_targets` into the guidance helper, which lists
them in the hint — so the advice is correct for **any** existing Makefile, not
hard-coded to the bot's `review` (iter-2 FN2: the fragment also defines
`status` / `loop-*` / `preflight-review-tooling` / the review+fact-check
targets, any of which a different target could already own); (3) the bot
acceptance test verifies the **post-removal** state (`make -n review` resolves
to the new dispatcher with no override warning). This is the upgrade-merge problem in miniature — the
natural seam to the parked re-adopt/upgrade work.

**Risk R-B2 (standalone render parity).** The standalone `Makefile.review` must
render to bytes equivalent to today's inline include. Implementation step:
confirm the fragment renders standalone via the same Jinja env + context, and
extend/keep `tests/test_selftest_overlap.py`-style coverage so the standalone
and inline forms cannot drift.

**Verification.** Fixture A (target owns a Makefile): adopt → assert base
Makefile SKIP, `Makefile.review` WRITE, the six scripts WRITE, the `include`
hint printed (listing the colliding targets to remove). Fixture B (target has
source but no Makefile): adopt → assert base Makefile WRITE (inline include
intact) and **no** standalone `Makefile.review` emitted (dropped post-analyze).
Bot acceptance: Fixture-A shape; after adding `include Makefile.review` and
removing the old `review` / `review-plan` targets, `make -n review` resolves to
the new dispatcher with no override warning.

### Bucket C — adopt success-path guidance parity

**Problem.** `_main_apply_adopt`'s success block omits the next-steps /
gh-repo-create / token-secret guidance the v1 path prints.

**Change (AD3).** Extract the v1 post-apply guidance (`cli.py:901-1008`) into a
single `_print_post_apply_guidance(args, target_root, *, adopt: bool,
makefile_review_emitted: bool = False, colliding_targets: tuple[str, ...] = ())`
helper and call it from both the v1 success path and `_main_apply_adopt`. The
explicit `makefile_review_emitted` flag is required because the helper cannot
otherwise tell an emitted `Makefile.review` from a pre-existing or dropped one
(iter-1 FN6); `colliding_targets` carries the computed fragment-vs-target
overlap so the hint lists the real names rather than a hard-coded set (iter-2
FN2). Both are values the caller already computed when deciding to emit. Adapt
for adopt mode:
- Gate the greenfield "`cd … && make install`" next-step on `adopt` (an adopt
  target already has its own install flow; the skill must not imply it created
  one). Keep the `gh repo create` hint, the `CLAUDE_CODE_OAUTH_TOKEN` step, and
  the both-docs Codex hint when `--github-review != none`.
- Print the Bucket B `include Makefile.review` hint **iff**
  `makefile_review_emitted` is true; when `colliding_targets` is non-empty, name
  those exact targets as the ones to remove (falling back to "`review` /
  `review-plan`" only when the overlap set is empty/unknown).

This folds the parked BACKLOG item "Mirror the gh-repo-create hint into
adopt-mode's `_main_apply_adopt`" (its stated trigger fires here).

**Verification.** Fixture: `--apply --mode=adopt --github-review both-docs`
against a fixture → assert the helper's lines appear in adopt output, with the
`include Makefile.review` hint present when `makefile_review_emitted=True` and
absent when `False`. A second fixture whose existing Makefile defines a
**non-`review`** colliding target (e.g. `status:`) → assert the hint names
`status` (not a hard-coded `review`), proving `colliding_targets` drives the
output (iter-2 FN2). The v1 path's existing assertions still pass (no regression
from the extraction).

## Architecture decisions

- **AD1** — Adopt suppresses greenfield-only placeholders unconditionally (not
  conditioned on existing-source detection). Simpler; no real loss.
- **AD2** — The plan-review machinery is delivered to a target that owns a
  Makefile as a standalone `Makefile.review` include fragment + an `include`
  hint, **not** by merging into the target Makefile. The fragment is already
  self-contained and restore is a file delete; the cost is that the owner must
  add one `include` line and remove the superseded `review`/`review-plan`
  targets the fragment's `review` dispatcher collides with (R-B1). Rejected
  alternative — APPEND_MERGE into the Makefile — is unsafe (tab/target
  sensitivity).
- **AD3** — Post-apply guidance is one shared helper called from both success
  paths, eliminating the drift that created the parked mirror item.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| R-B1: bare `review:` name-collision (fragment dispatcher vs the bot's `review:`) + stale `review-plan` superseded | Include hint names the stale targets to remove (`review` collides; `review-plan` superseded); impl adds a target-name overlap check; bot acceptance verifies post-removal `make -n review`. Full detail in Bucket B R-B1. |
| R-B2: standalone vs inline `Makefile.review` drift | Render via the same env/context; keep a selftest-overlap-style guard across both forms. |
| R-2: adopt-fixture test churn (planned-file set changes) | Mechanical fixture updates; the set change is small and asserted. |
| R-3: restore correctness for the new `Makefile.review` WRITE | It is a rule-(a) WRITE; restore deletes it. Assert restore round-trip in the e2e test. |
| R-SAFETY: the bot is **live/production** (a launchd job runs it) and carries untracked state (`test_api.py`) | Never run unhardened adopt against the live tree. Gate: read-only `analyze_target` preview → `--apply` on a `cp -R` copy (scripted-accept stdin) → only then the live bot, on a dedicated branch, applied **interactively per file**. Live rollback = the adopt **restore manifest** (primary — it removes the new untracked files adopt writes; `git` alone won't) **plus** `git restore` for tracked-file edits; record the pre-existing untracked `test_api.py` first so it is not mistaken for adopt output. No push/PR to the bot without explicit intent (paid review bots). |

## Verification

1. **Unit / engine tests** — extend `tests/test_adopt_engine.py`,
   `tests/test_adopt_apply_e2e.py`, `tests/test_mode_adopt_smoke.py`,
   `tests/test_bootstrap_cli.py` with the bucket fixtures above.
2. **`make check`** — full CI-equivalent stays green (baseline 1005 passed / 4
   skipped).
3. **Bot acceptance (read-only preview, then scripted copy apply)** — first the
   `adopt.analyze_target` + `format_recommendation_report` harness against the
   bot (writes nothing — the primary check) → confirm the policy table: no
   `src/main.py` / `tests/test_smoke.py`; `Makefile.review` WRITE; the six
   scripts WRITE; `.new` for the four domain docs; NEUTRALIZE for `.claude/`.
   Then exercise the real writes with `--apply --mode=adopt --language python`
   against a **`cp -R` throwaway copy**, driven by a **scripted stdin** that
   accepts each recommendation: the bot has ~12 manual-review files (4
   WRITE_NEW + 1 NEUTRALIZE + 7 SKIP-confirm), so `--auto-accept-recommendations`
   alone — which only auto-applies the mr=False writes — would still prompt and
   hang (iter-2 FN3). (No read-only adopt `--apply` and no
   "accept-all-including-manual" flag exist today; adding the latter is a noted
   future enhancement. The copy + scripted stdin is what makes the smoke
   repeatable and safe.) Inspect the on-disk result + the include hint naming
   `review`.
4. **Bot acceptance (live, gated)** — only after 1-3 pass: record the bot's
   pre-existing untracked files (`test_api.py`); apply on a dedicated branch
   **interactively, per file** (deliberate decisions — NOT the scripted
   accept-all used on the copy); confirm `make -n review` resolves the new
   dispatcher after the `include` + old-target removal. Rollback = the adopt
   **restore manifest** (removes the new untracked files) + `git restore` for
   any tracked edits — git alone does not clean adopt's new untracked output.

## Iteration log (this plan)

| Iter | Reviewer | Date | Findings (3/2/1) | Verdict |
|------|----------|------|------------------|---------|
| 0.5 | Fact-check (deterministic + Codex interpretation) | 2026-06-13 | n/a (28 ✓ / 8 benign / 3 n.v.) | **clean** — 28/28 load-bearing facts verified (incl. `languages/python/Makefile.tmpl:75` include line, all `bootstrap_lib/*` + `tests/*` + `shared/*` refs). All 8 `failed` are benign and explained: 6 are **generated-output paths** (`src/main.py`, `tests/test_smoke.py`, + nodejs/go equivalents) the verifier can't tell from repo files — Codex confirmed each maps to a real template in `render.py` (lines 38-39/52-53/64-65), so the references are accurate; `setup.cfg` is a negative ref (a shadow-config class the bot lacks); `.md` was extractor noise (reworded to "Markdown"). 3 `not_verifiable` are cli-flag/target-suffix tokens (documented). **No `## Fact roots` block for the bot**: its path contains a space (`Telegram bot`) which the `(/[^\s\`]+)` fact-roots regex cannot capture, and the bot facts were instead verified live via a read-only `analyze_target` run (see Context). |
| 1 | Codex | 2026-06-13 | 1/5/0 | needs-iter → **all 6 addressed**. Codex verified premises empirically (ran `bootstrap.py --dry-run --mode adopt` → exit 2; read the bot's `git status`). FN1 (imp-3, no read-only adopt gate / piped-SKIP still writes) folded (a). FN2/FN4/FN5/FN6 (imp-2) folded (a). FN3 (imp-2, suppressed-stub breaks `run:` in the no-Makefile subcase) folded as de-claim (a) + run-target retarget parked (b). 0 imp-3 remain after the folds. See Evidence table. |
| 1.5 | Claude self-check (3 passes; findings 4→3→2, converging) | 2026-06-13 | 0 imp-3 (9 doc-drifts, all fixed) | **Pass 1** — 4 fold-drifts fixed: missing iter-1 row (added); Critical-files said the run-target item was "folded" while everywhere else parks it (reworded); `cli.py` guidance range cited 898 vs 901 (unified to 901-1008); gh-repo BACKLOG title quoted two ways (aligned). **Pass 2** — 3 more, one substantive: R-B1's enumeration of the `Makefile.review` target set was incomplete (omitted `review-plan-by-*`) and overstated the collision set — corrected to "only the bare `review:` name-collides; `review-plan` is superseded; `review-uncommitted` orthogonal" across R-B1 / hint / Risks; Scope item 4 retagged verification-only. **Pass 3** (re-stamp before iter 2) — 2 more: Bucket A now credits the parked BACKLOG greenfield-placeholder item it folds (paralleling Bucket C); iter-0.5 findings column changed `0/8/0`→`n/a` (the 8 was the fact-check `failed` count, not imp-2 findings). **Cap reached (3 passes; shrinking, all self-inflicted fold-wording).** Structural facts cross-check clean (23-file count, six-scripts list, helper signature, line anchors, baseline 1005/4). **0 imp-3 after the iter-1 folds; user opted to run a confirming iter 2 (below).** |
| 2 | Codex | 2026-06-13 | 0/3/0 | **converged** — 0 imp-3; 3 imp-2 all folded (a). FN1: the post-analyze drop of `Makefile.review` must prune **both** `planned_files` and `AdoptionPlan.analyses` (verified `manifest.py:383` raises `ValueError` otherwise) → Bucket B sequencing contract. FN2: R-B1 promised a generic overlap check but the helper carried only a `bool` → added structured `colliding_targets` + a non-`review` collision fixture. FN3: copy/live acceptance had no defined decision input (verified `--auto-accept-recommendations` auto-applies only mr=False files; the bot has ~12 mr=True) → copy = read-only analyze harness + scripted-stdin apply, live = interactive per-file. **Stop: 0 imp-3, all imp-2 folded; no consistency pass-4 (cap; folds are localized precision additions, manually cross-checked).** |

## Evidence table — what was folded and where

| Finding | Decision (a/b/c/d) | Where |
|---|---|---|
| iter-1 FN1 (imp-3): no read-only adopt mode for the copy gate; "piped-SKIP" still auto-writes rule-(a) entries | **(a) fold** | Pre-coding declarations; Verification step 3; R-SAFETY. Gate rewritten to read-only `analyze_target` harness → `--apply` on a `cp -R` copy. Real CLI preview mode parked (NOT-in-scope). |
| iter-1 FN2 (imp-2): `Makefile.review` bare `review:` collides with the target's `review:` | **(a) fold** | Bucket B Change + R-B1; AD2; Risks R-B1; Verification. Include hint names targets to remove; overlap check added; post-removal acceptance. |
| iter-1 FN3 (imp-2): suppressing `src/main.py` leaves a broken `run:` in the no-Makefile subcase | **(a) fold as de-claim + (b) park** | Bucket A (reachability/residual note); Bucket B (de-claimed "coherent in both sub-cases"); NOT-in-scope (run-target retarget, BACKLOG). Bot does not exercise it. |
| iter-1 FN4 (imp-2): Node/Go placeholder scope contradicts Python-only adopt | **(a) fold** | Scope item 1; Bucket A AD1 reachability note. Narrowed to Python; constant documents Node/Go names with no behavior change. |
| iter-1 FN5 (imp-2): live rollback assumes a clean reversible worktree (bot has untracked `test_api.py`) | **(a) fold** | R-SAFETY; Risks R-SAFETY row; Verification step 4. Rollback = restore manifest + `git restore`; record untracked state first. |
| iter-1 FN6 (imp-2): guidance helper signature can't tell an emitted `Makefile.review` from pre-existing | **(a) fold** | Bucket C Change + Verification. Helper gains `makefile_review_emitted: bool`; both cases tested. |
| iter-2 FN1 (imp-2): post-analyze drop of `Makefile.review` must prune both `planned_files` + `analyses` | **(a) fold** | Bucket B sequencing contract (cites the `manifest.py:383` `ValueError`). Two-phase: render+analyze, then prune both structures if base Makefile is WRITE. |
| iter-2 FN2 (imp-2): generic overlap hint needs structured data, not a `bool` | **(a) fold** | Bucket C helper gains `colliding_targets: tuple[str,...]`; R-B1 mitigation (2) computes the real overlap; non-`review` (`status:`) collision fixture added to Bucket C Verification. |
| iter-2 FN3 (imp-2): copy/live acceptance has no defined decision input (bot has ~12 manual-review files) | **(a) fold** | Pre-coding step 2; Verification steps 3-4; R-SAFETY. Copy = analyze harness + scripted-stdin apply; live = interactive per-file. Verified `--auto-accept-recommendations` only auto-applies mr=False. |

## Implementation log (this PR)

| Commit | Date | Summary | check | Tier-1 |
|--------|------|---------|-------|--------|
| c936920 | 2026-06-13 | Bucket A — suppress greenfield-only placeholders (`src/main.py`, `tests/test_smoke.py`) in adopt: `render.GREENFIELD_ONLY_PLACEHOLDERS` (per-language; node/go listed) + a filter in `_main_apply_adopt` before `analyze_target`. Greenfield `--apply` unchanged. | 1008/4 | same-AI self-review, clean |
| 7841564 | 2026-06-13 | Bucket C — extract `_print_post_apply_guidance(args, target_root, *, adopt, makefile_review_emitted=False, colliding_targets=())`, called from BOTH v1 + adopt paths (AD3); gate `cd … && make install` on adopt; dormant include-hint branch. v1 output byte-identical. | 1015/4 | same-AI self-review, clean; v1 regression tests green |
| 88b6ba0 | 2026-06-13 | Bucket B — standalone `Makefile.review` WRITE when the target owns a Makefile; two-phase prune of BOTH `planned_files` + `analyses` when the base Makefile is not SKIPped (iter-2 FN1); computed `colliding_targets` (iter-2 FN2); `render.render_makefile_review` + R-B2 selftest-overlap parity guard. | 1023/4 | same-AI self-review, clean |
| 0b9e6ac | 2026-06-13 | Tier-2 folds — codex P2: a 2nd prune pass after `_interactive_decide` so an owner who [o]verwrites their SKIPped Makefile doesn't get a redundant `Makefile.review` + duplicate-target hint ([n]ew keeps it); claude #1: shared `_drop_planned_file` helper makes both prune sites desync-proof; claude #2: path-validate the injected `Makefile.review`. +2 tests. | 1025/4 | Tier-2 claude+codex bots |

**Tier-2 review (PR #48).** CI + claude[bot] + codex all ran on `6231936`.
claude[bot]: approve-with-fixes — 2 imp-2, both folded `(a)`: path-validate the
injected `Makefile.review` (its suggested sync-assertion #1 referenced a
non-existent field `analysis.policy`, so addressed instead by the shared
`_drop_planned_file` helper — sync by construction). codex: 1 P2, folded `(a)` —
a real interactive-path bug: an owner who [o]verwrites the SKIPped Makefile makes
the skill's inline-include Makefile the active one, so the standalone
`Makefile.review` + its include hint were redundant/harmful; fixed by re-deciding
on the FINAL Makefile action (commit `0b9e6ac`) with `[o]`/`[n]` regression tests.

**Bot acceptance (gated).** Step 1 (read-only `analyze_target` harness) — clean:
22 planned files (23 pre-hardening − 2 suppressed placeholders + 1 `Makefile.review`);
policy table matches the Context ground truth exactly; `colliding_targets == ('review',)`.
Step 2 (`cp -R` throwaway copy, scripted-stdin apply + restore) — clean: 16 mutating
entries; include hint named `review`; originals (`Makefile`/`pyproject.toml`/`CLAUDE.md`)
untouched; `.gitignore` carried the NEUTRALIZE block + the command became git-visible;
restore reversed everything (2 restored / 14 removed) with `.gitignore` byte-identical.
Step 3 (live bot) — **skipped by decision**: step 2's `cp -R` copy was byte-identical to
the live bot (same files + `.git`), so it already validated adopt against the bot's exact
content + full restore; re-running on the production tree (launchd job live) adds ~zero
signal. The marginal-only check (`make -n review` after the manual `include` + target
removal) is an owner step, not something adopt performs.

## Lessons surfaced (this PR)

- **Tier-1 (self-review)**: none — no new mistake-class, no approach-changing push-back.
- **Tier-2 (codex P2)**: new mistake-class → `LESSONS.md` 2026-06-13 — *a gate keyed on
  the analyze-phase recommendation can be invalidated by the interactive decide phase*
  (the owner can `[o]verwrite` a SKIPped Makefile). Folded `(a)` in commit `0b9e6ac`.
- **Tier-2 (claude #1)**: its suggested sync-assertion cited a non-existent field
  (`analysis.policy`) — caught before folding (the 2026-05-17 "verify the reviewer's
  suggested fix" lesson holding); addressed via the shared `_drop_planned_file` helper.
- One design observation parked (BACKLOG "Follow-ups from adopt-mode hardening (PR #48)"),
  not a lesson: adopt's `make install-hooks` next-step can name a target absent in the
  owns-a-Makefile subcase (the skill's `Makefile`, which defines it, is SKIPped) —
  plan-faithful (the plan gates only `make install`), so left as a follow-up.

## Critical files to read before each iter's review

- `bootstrap_lib/adopt.py` — `recommend_policy` (rules a0/a..h), `analyze_target`,
  `_compute_target_meta`, `compute_append_merge_bytes`, `_normalize_gitignore_lines`.
- `bootstrap_lib/cli.py` — `_main_apply_adopt` (~643), `_apply_adoption_writes`
  (~534, esp. NEUTRALIZE/APPEND_MERGE/WRITE_NEW), `_interactive_decide` (~425),
  the v1 success/gh-repo-create guidance block (`cli.py:901-1008`).
- `bootstrap_lib/render.py` — `SHARED_TEMPLATE_MAP` / `PYTHON_TEMPLATE_MAP`,
  `render_all`, `planned_paths`, `_emit_python_in_pm_mode`.
- `languages/python/Makefile.tmpl` (the `{% include 'Makefile.review.tmpl' %}`
  at line 75) + `shared/Makefile.review.tmpl` (the fragment) +
  `tests/test_selftest_overlap.py` (the drift guard).
- `BACKLOG.md` — the parked items this plan **folds** (gh-repo-create mirror;
  PR #7 greenfield-placeholder item) vs the ones it **leaves parked** (the
  adopt `run:`-target retarget; config-shadowing cluster; sensitive-path
  safety; CRLF parity; re-adopt/upgrade detection).
- Bot acceptance target: `~/Desktop/Code/Boxette/Telegram bot` (pyproject.toml,
  Makefile, .gitignore, requirements-dev.txt).
