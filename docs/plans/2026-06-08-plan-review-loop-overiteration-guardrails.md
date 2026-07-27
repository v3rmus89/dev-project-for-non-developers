# Plan — Plan-review-loop over-iteration guardrails

- **Date:** 2026-06-08 (drafted); iter-1 folds applied 2026-06-08.
- **Status:** Plan converged at iter-2 (0 imp-3); human-approval gate passed at C1. iter-1
  (3 imp-3 + 1 imp-2), iter-1.5 (consistency), and iter-2 (3 imp-2) all folded; C4 split to a
  follow-up plan. **Implementation COMPLETE** — C1 (58711ed), C2 (975a6f1), C3 (a69eccf) all
  landed green (make check 977 → 979 pass) with clean Tier-1 reviews (0 imp-3, 0 imp-2). Pending
  the PR.
- **Author:** Claude.
- **Origin:** Post-mortem of the `downstream-app` plan
  `docs/plans/2026-06-08-doc-layout-post-2b-improvements.md`, whose review loop ran **19 Codex
  iterations** (+ ~16 self-checks) in one day without converging. Target band is 3–5.

## Regression safety + outcome measurement (pre-coding)

- **Regression safety — auto-testable.** All changes are prose in rule docs / prompt templates
  kept byte-identical by `tests/test_dogfood_doc_sanity.py` and `tests/test_shared_templates.py`
  plus `scripts/propagate-shared-rules.py`. New assertions verify (a) the calibration sentence is
  present in both rendered plan-review prompts, and (b) those prompts contain **no** backticks or
  `$(` and no literal double-quotes (extending the Tier-1-only no-backtick guard — see iter-1 FN1).
  `make check` (lint + full suite) is the gate.
- **Outcome measurement — internal process change, no business metric.** Success is a *leading
  behavioural* signal, not a shipped feature: the next cross-surface plan whose loop runs under
  these rules shows (a) integer iterations ≤ 5, and (b) a downward imp-3 trajectory (not the flat
  ~2/round seen here). This is a soft, lagging metric (low confidence on attribution); recorded
  here so we revisit it, not as an acceptance gate.

## Background — what the 19-iteration loop actually did

The post-2b plan's review log records imp-3 (blocker) counts per Codex round:

`[3, 2, 2, 2, 3, 3, 1, 3, 2, 2, 2, 2, 1, 2, 1, 2, 3, 2, 2]` — **40 blockers across 19 rounds**,
hovering at ~2 with no trend toward zero (iter-17 spiked back to 3). The loop was terminated by
human decision at iter-19 while the round was *still* producing imp-3 findings; the formal stop
condition ("no importance-3 remain") was never recorded as met.

Classifying every imp-3 finding by what it was really about (classification is a judgment call;
the proportions are robust):

| Bucket | What the findings were about | ~count | Correct verification tool |
|---|---|---|---|
| **1. Design / scope** | chat counts in figures (iter-1 F1), one combined chart vs two (iter-1 F2), deploy is resynthesis not render-only (iter-5 F2), existing version floor (iter-5 F3), calls-period also needs re-render (iter-8 F3), no standalone chat-daily Doc (iter-16 F1) | ~6 | ✅ cross-review — converged by ~iter 5 |
| **2. CLI / API signature mismatches** | `--no-digest` absent (iter-4, iter-9), `doctor` makes no API calls (iter-13), `claude-cli` needs `--model` (iter-16), `generate()` keyword-only / `.parsed` (iter-18, iter-19), `period_source_coverage` positional args (iter-2, iter-19) | ~9 | ❌ C2 (CLI lives in the script, verified by running) + `--help`/source pre-pass. *Caveat (iter-1 FN2): the current fact-check verifies paths/symbols but marks CLI flags `not_verifiable` and does not check API signatures — that verifier upgrade is parked, see Not-in-scope.* |
| **3. Deploy/rollback bash correctness** | trap pause-vs-resume (iter-7), `set -e` kills shell (iter-9/10), `awk` wrong field (iter-11), DB-restore ordering (iter-11), `&& echo \|\| echo` defeats `set -e` (iter-18), clean-tree regex (iter-17), git-revert range (iter-3), WAL-safe backup (iter-8)… | ~21 | ❌ a real `.sh` + `shellcheck` + `--dry-run` + Tier-1 |

Separately — *not* part of the 40 Codex imp-3 above — ~6 of the Claude self-check findings were
purely *"review-log rows out of order"*: process noise the loop generated about its own bookkeeping.
(The three imp-3 buckets are approximate, "~", and their example lists are illustrative, not
exhaustive — they account for most of the 40, not all.)

**Root cause:** the plan embedded a ~200-line executable deploy+rollback runbook, and the loop
tried to make it line-perfect through static cross-AI review. Buckets 2+3 (~30 of 40 blockers)
are executable-artifact correctness — the class static review converges on slowly, because the
reviewer cannot run anything (1–2 bugs found per pass) and every fold *adds* surface (a trap, a
grep, a gate) that regenerates findings next round.

**Three process gaps amplified it (all verified):**
1. `downstream-app` is on a **pre-PR-30 skill snapshot** (rule files last synced 2026-05-25). It has
   **no fact-check pre-pass** (which catches the path/symbol claims of Bucket 2 in one batch — though
   not CLI-flag existence; see iter-1 FN2) and **no architectural-split rule**. Only the older
   plateau rule was present.
2. The plateau rule did not fire — it requires findings to be *"increasingly narrow edge cases,"*
   but each finding here looked like a fresh genuine blocker.
3. The reviewer prompt defines importance only as *"3 = blocker, 2 = improvement, 1 = polish"* with
   **no calibration**. The calibration ("imp-3 = the PR doesn't work without it") lives in
   `CONTRIBUTING.md`, which the reviewer (Codex) never reads — so the reviewer was never told what
   "blocker" means in this project, inviting over-escalation. (Nearly every logged finding was
   folded — exactly one was parked, iter-19 F3, and none rejected; the park/reject triage was
   effectively unused.)

## Scope

| Item | Surface | Change |
|---|---|---|
| **C1** | plan-review prompt (`shared/Makefile.review.tmpl` codex+claude blocks; root `Makefile`); `AGENTS.md` reviewer-protocol pointer | Bake imp-3 **calibration** into the prompt with a *narrowed* carve-out (iter-1 FN2): illustrative shell/CLI/runbook **syntax shown only to explain intent** (quoting, exit codes, awk/grep fields) is at most imp-2 — but a CLI flag / command / API signature the design **genuinely relies on** stays imp-3 if wrong or unverified. Prompt text is shell-safe: no backticks, no `$(`, no literal double-quotes (iter-1 FN1). |
| **C2** | `CONTRIBUTING.md` (+ `shared/CONTRIBUTING.md.tmpl`); pointer in `docs/plans/README.md` (+ tmpl) | New rule: **executable runbooks stay out of the plan body.** Plans describe deploy/rollback at *intent* fidelity (sequence, scope, ordering, failure modes to verify). Line-level scripts live in `scripts/…` and are verified by `shellcheck` (or a documented equivalent in the repo's toolchain) / `--dry-run` / `--help` + Tier-1, not the plan loop. Boundary: ordering/scope/which-failure-to-check = plan; syntax/flags/quoting/signatures = script. |
| **C3** | `CONTRIBUTING.md` plateau rule (+ tmpl); `docs/plans/README.md` "Stopping the loop" (+ tmpl) | **Extend the circuit-breaker** with a second trigger: even when findings are *not* narrow edge cases, if imp-3 keeps regenerating past ~iter 5 clustered in **one artifact/theme** (deploy runbook; CLI/API signatures), that is an *artifact-class mismatch*, not convergence — stop folding, switch to execution-based verification, or escalate to the human-approval gate. |

**NOT in this plan:**
- **C4 — port to `downstream-app`: split to a separate follow-up plan** (was in this plan; carved out
  at iter-1 FN3). As of 2026-06-08, `downstream-app` had an actively-changing dirty tree from the in-progress post-2b
  implementation (15+ modified files across `src/acme_*/` + tests, still progressing); porting
  into a mid-flight tree would tangle two workstreams. This snapshot is point-in-time, not a durable
  fact — the "6 files" first recorded here was already stale by iter-2 (FN2) and used ambiguous bare
  filenames (FN1); the follow-up plan must recheck the exact dirty set (repo-relative paths) at start. The follow-up runs **once downstream-app is clean AND
  C1–C3 have merged**; it re-propagates the fact-check pre-pass templates + updated rule docs via
  `bootstrap.py` / `scripts/propagate-shared-rules.py`, with a clean-tree precondition, its own
  branch, and git-revert rollback.
- **Teaching the fact-check pre-pass to verify CLI flags + API signatures** — *parked to BACKLOG*
  (iter-1 FN2). Empirically (this plan's own pre-pass run) the verifier marks CLI flags
  `not_verifiable` and does not introspect function signatures. Mechanically checking them (import
  the CLI, read argparse; introspect signatures) — plus disambiguating bare filenames and excluding
  `venv`/vendored dirs (iter-2 FN1: a bare `models.py` matched `venv/.../pip/_vendor/requests/models.py`
  under the declared root) — is the real enabler for catching Bucket-2 findings in one batch. Trigger: the next plan whose loop burns >2 iterations on CLI/API-existence findings.
  Until then Bucket-2 is handled by C2 + a manual `--help`/source pre-pass, and relied-upon CLI/API
  deps stay imp-3 (C1 carve-out).
- **Commit-review (Tier-1) prompt calibration** (`Makefile` lines ~284/293/317/324). Tier-1 reviews
  *actual code*, where bash/CLI correctness is legitimately in scope — the C1 carve-out must NOT
  apply there. Possible separate follow-up for the general "imp-3 = doesn't work" half only.
- Auto-enforcement of the circuit-breaker (it stays a human-judgment signal at the approval gate,
  consistent with the existing "advisory, not a cap" framing).

## Design

### C1 — imp-3 calibration in the plan-review prompt

The canonical source is the template `shared/Makefile.review.tmpl` (codex plan-review block
~line 134, claude block ~line 201). The skill repo's own `Makefile` carries a *rendered* copy of
this template inside its `SELFTEST-OVERLAP-BEGIN/END: shared/Makefile.review.tmpl` region (Makefile
~lines 78–511); an existing selftest re-renders the template for this repo's context and fails if
the region drifts — so the edit propagates by re-syncing that region, **not** by hand-editing two
independent copies.

**The prompt is a double-quoted shell argument** (`@PROMPT="Review the plan file…"`), so the inserted
text MUST be shell-safe: no backticks and no `$(` (they trigger command substitution) and no literal
double-quotes (they terminate the arg) — use single quotes for any inner quoting, matching the
existing prompt's style (iter-1 FN1; the template header at `shared/Makefile.review.tmpl:1` documents
this constraint). In **both** plan-review prompt blocks, immediately **after** the sentence
`Return findings ordered by importance (3 = blocker, 2 = improvement, 1 = polish).`, insert (verbatim,
already shell-safe — note the single quotes):

> Calibrate importance strictly. A 3 (blocker) means the implemented PR would fail make check or its
> smoke walk without this change — a real defect in the plan's design, data flow, scope, or
> sequencing. It is NOT 'would be more correct', NOT a style preference, and NOT the exact syntax of
> an illustrative shell/CLI/runbook snippet shown only to explain intent (quoting, exit-code
> handling, awk or grep field numbers) — that syntax is verified at implementation by running it, so
> raise it at most as importance-2. BUT a dependency the plan genuinely relies on for feasibility — a
> CLI flag, command, or function/API signature that must exist for the design to work — stays
> importance-3 when it is wrong or unverified, because the design fails without it; do not down-rank a
> feasibility dependency to importance-2 just because it resembles 'syntax'. When unsure whether a
> finding blocks, ask: can the PR ship with a green make check and a passing smoke walk without it? If
> yes, it is at most importance-2.

This injects the existing `CONTRIBUTING.md` calibration (line ~200) at the **source** (the reviewer)
rather than relying on the driver to down-triage afterward. Rationale: the reviewer never reads
`CONTRIBUTING.md`; calibrating the prompt reduces false imp-3 *emission*, which is upstream of the
over-folding ratchet. The narrowed carve-out (iter-1 FN2) is the crux: it stops over-escalation of
*illustrative* syntax without giving a free pass to *relied-upon* CLI/API dependencies, which remain
real blockers (e.g. the post-2b `--no-digest` findings were feasibility blockers, not noise).

`AGENTS.md` line ~92 (reviewer-side "importance score: 1/2/3" protocol) gains a one-line pointer to
the same calibration for consistency.

### C2 — executable runbooks out of the plan body

New short subsection in `CONTRIBUTING.md` (near the plateau rule), proposed text:

> **Keep executable runbooks out of the plan.** A plan describes deploy/rollback at *intent*
> fidelity: the sequence of steps, what is in scope, ordering constraints that matter for safety
> (e.g. "restore the DB backup *before* re-rendering"), and which failure modes the operator must
> verify. It does **not** embed line-level executable scripts — bash with traps / `set -euo
> pipefail`, `awk`/`grep` output parsing, DB backup/restore, or internal-API heredocs. Executable
> artifacts belong in a real file (`scripts/deploy/<task>.sh`) and are verified by *execution* —
> `shellcheck` (or a documented equivalent; add it to `make doctor` when shell deploy scripts are
> introduced), a `--dry-run`, and `--help` / source checks for every CLI flag and API signature —
> then reviewed as code (Tier-1). Static cross-review converges on design but not on executable
> correctness; trying to make a runbook line-perfect in the plan body regenerates importance-3
> findings every iteration (the post-2b doc-layout loop: 19 iterations, ~30 of 40 blockers were
> CLI/bash mechanics). **Boundary:** ordering / scope / which-failure-to-check → plan; syntax /
> flags / quoting / exact signatures → script.

(This C2 text lives in a Markdown doc, not a shell prompt — backticks are correct here.)
`docs/plans/README.md` gets a one-line cross-reference under "Stopping the loop".

### C3 — circuit-breaker second trigger

Extend the existing plateau rule in `CONTRIBUTING.md` (line ~202) — append, not replace. (The
"architectural-blocker split" rule that the inserted text cross-references as "below" already exists
in `CONTRIBUTING.md` at ~204; C3 sits just above it, so "below" resolves in-context.) Inserted text:

> **Second trigger — same-class regeneration.** Even when findings are *not* narrow edge cases: if
> importance-3 findings keep appearing past ~iteration 5 but cluster in **one artifact or theme**
> (e.g. the deploy runbook, or CLI/API signatures), that is not convergence — it is the wrong
> verification tool for that artifact. Stop folding; extract the artifact and verify by execution
> (`shellcheck` / `--dry-run` / `--help` / the fact-check pre-pass), or escalate to the
> human-approval gate. Signals: findings concentrate in one section; findings are about
> syntax / flags / exit-codes / signatures rather than design. (Distinct from the architectural-
> blocker split below, which is about *design* holes; this is about *artifact-class* mismatch.)

`docs/plans/README.md` "Stopping the loop" gains a matching bullet: stop and switch tools if imp-3
keeps regenerating in one executable artifact.

## Fact roots

For the fact-check pre-pass. Declared roots **replace** the default repo root, so both this repo
(for the C1–C3 templates/scripts/tests in the Files table) and the `downstream-app` repo — needed only
so the Background post-mortem's reference to `docs/plans/2026-06-08-doc-layout-post-2b-improvements.md`
(which lives in downstream-app) resolves instead of reading as an external miss — are declared. Paths
are absolute + machine-specific — local fact-check tooling metadata, not portable plan logic:

- /Users/sandeep/Desktop/Code/dev-project-for-non-developers
- /Users/sandeep/Desktop/Code/Acme/downstream-app

## Files / surfaces

| Surface | Canonical | Template mirror | Enforced by |
|---|---|---|---|
| Plan-review prompt (C1) | `shared/Makefile.review.tmpl` (codex ~134 / claude ~201) | root `Makefile` SELFTEST-OVERLAP region (~78–511), synced by existing selftest | new render-and-assert (calibration present; no backticks/`$(`/`"`) + existing selftest |
| Runbook rule (C2) | `CONTRIBUTING.md` | `shared/CONTRIBUTING.md.tmpl` | `test_shared_templates.py` + `test_dogfood_doc_sanity.py` |
| Circuit-breaker (C3) | `CONTRIBUTING.md`, `docs/plans/README.md` | `shared/CONTRIBUTING.md.tmpl`, `shared/docs-plans-README.md.tmpl` | `test_shared_templates.py` + `test_dogfood_doc_sanity.py` |
| Reviewer protocol pointer (C1) | `AGENTS.md` ~92 | `shared/AGENTS.md.tmpl` | `test_dogfood_doc_sanity.py` |

## Phasing

Single phase (C1–C3, this repo). C1 → C2 → C3 as focused commits (one logical change each), each
with `make check` green + Tier-1 commit review. Update each root doc **and** its `.tmpl` together
(dogfood tests fail otherwise); run `scripts/propagate-shared-rules.py` where applicable; re-sync the
Makefile SELFTEST-OVERLAP region for C1. (The downstream-app port is a separate follow-up plan — see
Not-in-scope.)

## Tests

- **C1:** a render-and-assert test (mirroring the existing `test_dogfood_doc_sanity.py` pattern that
  renders `shared/*.tmpl` via `bootstrap_lib.render` and asserts content) confirming both rendered
  plan-review prompt blocks contain the calibration text. **Plus a shell-safety assertion** (iter-1
  FN1): both rendered plan-review prompts contain no backtick, no `$(`, and no literal double-quote —
  extending `test_tier1_prompt_has_no_backticks_in_rendered_recipe` (which currently guards only the
  Tier-1 commit-review recipe) to the plan-review recipes. The existing Makefile `SELFTEST-OVERLAP`
  selftest already enforces that the root Makefile matches the rendered template.
- **C2/C3:** `test_shared_templates.py` / `test_dogfood_doc_sanity.py` extended to cover the new
  subsection + plateau-rule extension across canonical + `.tmpl` copies.
- **Full suite:** `make check` green before each commit.
- **Manual (non-auto):** read the rendered prompt once (the generated prompt string, or a
  `make review-plan-by-codex` dry inspection) to confirm the calibration reads correctly to a reviewer.

## Iteration log (this plan)

| Iter | Reviewer | Date | Findings (3/2/1) | Verdict |
|------|----------|------|------------------|---------|
| 0.5 | Codex fact-check (deterministic) | 2026-06-08 | 23 verified / 2 benign / 4 not-verifiable (point-in-time on the draft; counts shift as the plan is folded — re-run for current, iter-2 FN1) | clean — no real factual drift (the 2 "failed" are `.sh`/`.tmpl` prose fragments) |
| 1 | Codex | 2026-06-08 | 3/1/0 | do-not-implement → folded (FN1, FN2-narrow, FN4); FN2-enhancement parked; FN3 → C4 split to follow-up |
| 1.5 | Claude self-check | 2026-06-08 | 0/3/0 | folded — 3 internal-drift nits: "Two"→"Three" process gaps; Fact-roots justification → Background citation (not out-of-scope C4); FN3 "gate" ambiguity disambiguated. (Self-check then ran 5 passes total before converging — capped per C3 once it hit cosmetic/self-inflicted drift; a live instance of this plan's own thesis.) |
| 2 | Codex | 2026-06-08 | 0/3/0 | **converged — 0 imp-3** → 3 imp-2 folded (FN1 bare-filename/venv + stale counts; FN2 stale dirty-tree snapshot; FN3 shellcheck not in doctor). Stop rule met; no ritual iter-3. |

## Evidence table — what was folded and where

(Cross-review findings, one row each. Consistency self-check drift-folds — e.g. the three iter-1.5
nits — are mechanical doc-drift and are summarized in the Iteration log's iter-1.5 row, not given
separate rows here.)

| Iter | Finding | Imp | Disposition | Where |
|------|---------|-----|-------------|-------|
| 1 | **FN1** — C1 prompt text used backticks around `make check` → shell command substitution when the double-quoted prompt is built; the no-backtick guard test covers only Tier-1, not plan-review prompts | 3 | **(a) fold** | Design C1 prompt rewritten shell-safe (single quotes, no backticks/`$(`/`"`); Tests C1 + Regression-safety add the plan-review shell-safety assertion; Scope C1 notes the constraint |
| 1 | **FN2** — C1 carve-out too broad: routed CLI/API findings to the fact-check pre-pass, but the verifier marks CLI flags `not_verifiable` and ignores API signatures → would hide real feasibility blockers | 3 | **(a) fold** (narrow) + **(b) park** | Carve-out narrowed in Scope/Design C1 (relied-upon CLI/API deps stay imp-3); Background bucket-2 + gap-1 softened; verifier upgrade parked to BACKLOG (trigger noted in Not-in-scope) |
| 1 | **FN3** — C4 port into `downstream-app` lacked clean-tree/branch/rollback gates; the repo is mid-implementation (dirty tree from post-2b — 6 files when first checked, 15+ by iter-2) | 3 | **(d) surface → split** | C4 removed from this plan; carved into a follow-up (Not-in-scope) with clean-tree precondition + revert rollback. User confirmed the split during iter-1 triage (formal approval gate still pending). |
| 1 | **FN4** — plan violated the README section order (Implementation log before Iteration log; no Evidence table / Lessons) → `make status` tailed the wrong section | 2 | **(a) fold** | Restructured: Iteration log → Evidence table → Implementation log → Lessons surfaced |
| 2 | **FN1** — iter-0.5 fact-check not reproducible; bare `models.py` mis-verified against a `venv` pip-vendored file | 2 | **(a) fold** | C4 bullet + Evidence use dated/repo-relative refs; iter-0.5 row marked point-in-time; parked verifier item broadened to bare-filename / venv-exclusion |
| 2 | **FN2** — "6 dirty files" downstream-app snapshot already stale (15+ by iter-2, still moving) | 2 | **(a) fold** | C4 bullet → dated snapshot + "recheck in follow-up"; Evidence FN3 row updated |
| 2 | **FN3** — C2 mandates `shellcheck`, which is absent from `make doctor` and not installed in this env | 2 | **(a) fold** | Scope + Design C2 softened to "shellcheck or a documented equivalent; add to doctor when shell scripts are introduced" |

## Implementation log (this PR)

**CODE_ROLLBACK_BASE** (commit before first C1 change): `f1bdeeb`

| Item | Commit | Date | Summary | check | Tier-1 |
|------|--------|------|---------|-------|--------|
| (plan) | f1bdeeb | 2026-06-08 | Track plan (converged iter-2). | n/a | n/a |
| C1 | 58711ed | 2026-06-08 | imp-3 calibration in both plan-review prompts; Makefile SELFTEST-OVERLAP re-synced; AGENTS.md+tmpl pointer; plan-review prompt shell-safety test | ✓ 975 pass | Claude: 0 imp-3; 1 imp-2 (F1 — test missing the literal-double-quote check) folded in amend |
| C2 | 975a6f1 | 2026-06-08 | "Keep executable runbooks out of the plan" rule in CONTRIBUTING.md (+ post-2b example) + generic `.tmpl` mirror (example stripped); one-line cross-ref under README "Stopping the loop" (+ byte-identical `.tmpl`); 2 presence tests + README delete-on-both-sides guard | ✓ 977 pass | Claude: 0 imp-3, 0 imp-2 (2 imp-1 noted — intentional dogfood/tmpl divergence — no change) |
| C3 | a69eccf | 2026-06-09 | "Second trigger — same-class regeneration" inserted between the plateau rule and the architectural-blocker split in CONTRIBUTING.md + identical `.tmpl`; matching "Same-class regeneration is not convergence" stop signal under README "Stopping the loop" (+ byte-identical `.tmpl`); 2 presence tests + README delete-on-both-sides guard | ✓ 979 pass | Claude: 0 imp-3, 0 imp-2 (1 imp-1 — unused `enable_smoke` test kwarg, matches repo `_context()` convention — no change) |

## Lessons surfaced (this PR)

- **A plan that proposes prompt-string text must keep that text shell-safe** (no backticks, no
  `$(`, no literal double-quotes) — it will be embedded in a double-quoted Makefile arg. The existing
  no-backtick regression test covered only Tier-1 prompts; plan-review prompts were an unguarded gap
  (iter-1 FN1). *(Append to `LESSONS.md` Active when this plan is implemented.)*
- **When a rule routes findings to a verifier as a safety net, confirm the verifier actually checks
  that class.** The C1 draft sent CLI/API findings to the fact-check pre-pass, which marks CLI flags
  `not_verifiable` — the net had a hole (iter-1 FN2). Verify the tool's real coverage before relying
  on it in a rule.
- **When a rule names a verification tool, make sure that tool is in the repo's documented toolchain**
  (`make doctor`), or the rule recreates the tool-mismatch it exists to prevent — `shellcheck` was
  mandated by C2 but is not installed here nor in `doctor` (iter-2 FN3).
- **A fact-check fact-root that contains a `venv`/vendored tree will mis-match bare filenames** — a
  bare `models.py` "verified" against a pip-vendored copy (iter-2 FN1). Qualify external references
  with repo-relative paths; the verifier needs venv exclusion (parked).
- **The consistency self-check can itself over-iterate.** It ran 5 passes here (3→4→3→3→2 nits),
  several self-inflicted by folds — a live instance of this plan's own thesis. The C3 circuit-breaker
  should arguably cover the consistency self-check explicitly (cap passes / accept cosmetic drift).
  *Candidate follow-up — flagged to the human at the gate, not yet folded into C3 scope.*
