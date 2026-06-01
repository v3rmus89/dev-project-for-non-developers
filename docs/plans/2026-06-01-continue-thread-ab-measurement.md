# Continue-thread A/B SCREEN — does resume cache enough to be worth a full-rigor measurement? (Bucket F payoff) — SCREEN-ONLY SCOPE

**Author**: Claude (driver). **Date**: 2026-06-01. **Type**: substantive (external-CLI,
decision-bearing). **Scope: a cheap SCREEN** — it can soundly conclude *stay-fresh* or
*escalate to a full-rigor measurement*, but by construction it **NEVER flips** the default
(driver proposal after iter-3, confirmed by the user 2026-06-01) — see "Scope decision" below.

## Context

PR #33 (Bucket F) shipped the Codex continue-thread **mechanism** but left it **dormant**:
`THREAD_MODE ?= fresh` is the default ([Makefile:94](../../Makefile)), so every
`make review-plan-by-codex` starts a new Codex session. The hypothesis that drove Bucket F —
*resuming one Codex thread across a plan-review loop costs less than a fresh session per
iteration* — was deliberately left **unverified** (meta-plan PR-1 iter-1 F3: "MAY reduce —
HYPOTHESIS, not a known win"). The `~/.claude/plans/what-else-i-want-majestic-rain.md`
meta-plan (external) gates the `fresh -> continue` flip on a measured A/B. This PR runs a cheap
**screen** of that hypothesis: it can soundly conclude *stay-fresh* (no payoff even in the
best case) or *escalate to a full-rigor representative measurement* (payoff in the best case),
but it **cannot justify flipping the default** — that requires the full-rigor measurement
parked in BACKLOG.

**What already exists** (verified 2026-06-01 via code read):
- Seed/resume in `review-plan-by-codex`, each wrapped in `scripts/run-with-clean-env.py`
  (prefix scrub of `CLAUDE_CODE_*` / `CODEX_*` + `THREAD_*` / Make-internal vars): fresh =
  `codex exec -C "$(CURDIR)" --sandbox read-only --color never ...` (no `--json`)
  ([Makefile:214](../../Makefile)); continue-seed = `codex exec --json -C "$(CURDIR)"
  --sandbox read-only --color never ...` then `scripts/extract-codex-session-id.py` -> atomic
  `.tmp`+UUID+`mv` ([Makefile:206](../../Makefile)); continue-resume = `codex exec resume
  "$SESSION_ID" -c sandbox_mode=read-only ...` (NO `-C` / `--sandbox`; relies on `-c`)
  ([Makefile:191](../../Makefile)).
- The review prompt STRING embeds the plan **path** + **iteration** (not contents — contents
  enter when Codex reads the file) ([Makefile:186](../../Makefile)); seed and resume reuse it.
- Session-id extractor reads `thread.started.thread_id` from the `--json` stream
  ([scripts/extract-codex-session-id.py:45](../../scripts/extract-codex-session-id.py)).
- Stream cache metric = `turn.completed.usage.cached_input_tokens`
  ([tests/test_codex_jsonl_fixture.py:150](../../tests/test_codex_jsonl_fixture.py));
  `cached_input_tokens` is a SUBSET of `input_tokens`.
- Safety gate `scripts/verify-v13-5.py` already PASSED for the mechanism (untouched here).

**Files this PR creates** (planned outputs; a deterministic fact-check reports these "not
found" by design — expected): `scripts/ab_replay_lib.py`, `tests/test_ab_replay_lib.py`,
`scripts/ab-replay.py`, `docs/design-notes/2026-06-01-continue-thread-ab-result.md`.

## Scope decision: a cheap SCREEN, not a flip-justifying measurement (driver + user, post-iter-3)

iter-3 (Codex, on the lighter-directional rewrite) surfaced that the cheap test's design has two
structural limits that no amount of polish removes:
- **Best-case caching, not a real fold loop** (iter-3 FN1): reviewing the SAME plan 3x is the
  *friendliest possible* case for resume — identical context maximises cache hits. A real
  plan-review fold loop changes the plan between iterations, so it caches *less*. The same-plan
  test therefore over-states resume's payoff.
- **Order-confounded** (iter-3 FN3): whichever mode runs second hits a server-side prefix cache
  warmed by the first, biasing the cross-mode ratio.

So the cheap test's **sound** conclusions are only:
- *No payoff even in the best case* (`ratio > 0.90`) -> **stay-fresh** — a real loop caches less,
  so it cannot beat a best case that already shows nothing.
- *Payoff in the best case* (`ratio <= 0.90`, quality equivalent, not warmup-confounded) ->
  **escalate-to-full-rigor** — promising, but a best-case + N=3 + order-biased screen cannot
  justify a flip.
- *Confounded or degraded* -> **inconclusive** -> stay fresh + escalate.

This plan therefore runs a **SCREEN ONLY. There is no flip verdict.** A flip is satisfied only by
the full-rigor representative measurement parked in BACKLOG.

- **KEEPS the correctness the review hard-won**: the **uncached-input** metric, NOT raw token
  count (iter-1 FN1); **raw JSONL is never committed** (iter-2 FN2); **pinned read-only argv**
  (iter-3 FN2); a **pre-registered run order + per-call timestamps** (iter-3 FN3); a **manual
  quality equivalence table** (iter-3 FN5).
- **DROPS, for speed**: the separate gate-0 pre-probe (iter-2 FN3); the machine-checkable
  seeded-defect oracle + reproducible manufactured corpus (iter-1 FN2 / iter-2 FN5); the
  byte-identity prompt-contract test (iter-1 FN3 -> a documented close-mirror). Env-scrubbing is
  NOT dropped — the screen reuses `scripts/run-with-clean-env.py`, the wrapper the Makefile
  already uses (iter-2 FN4 -> reuse + operator preflight).
- **Full-rigor is the BACKLOG fallback**: if the screen shows a best-case payoff, escalate to it
  rather than forcing a flip on thin evidence.

## Three deviations from the meta-plan (documented)

1. **Real-plan replay, not historical per-iter replay** — per-iteration plan states don't
   survive (PR #10's plan has 3 commits; loop snapshots are ephemeral `/tmp`). We replay a
   real checked-in plan reviewed at iters 1/2/3 instead.
2. **Metric = uncached-input ratio**, not the meta-plan's raw-total-tokens `>=10% lower` gate
   (cond. 2, meta-plan line 528). Caching is a price discount: raw token COUNT can rise while
   cost falls, so raw-total is the wrong gate (iter-1 FN1). The meta-plan's own footnote (line
   558) already says compare cache-share + effective-uncached-input "not just raw totals"; this
   takes that to its conclusion (uncached-input primary; raw-total reported, not gated).
3. **Screen-only scope** (above) — a cheap disconfirm/escalate read, NOT the airtight automated
   measurement. **This PR never flips the default**; the meta-plan's flip gate is satisfied only
   by the full-rigor BACKLOG measurement.

## Goal / outcome

A directional **screen** disposition for the dormant `THREAD_MODE` bucket. The screen returns one
of: **stay-fresh** (no best-case payoff -> done, dormant bucket retired with data),
**escalate-to-full-rigor** (best-case payoff -> the full-rigor measurement is the next gate before
any flip), or **inconclusive** (confounded/unclear -> stay fresh, escalate). In every case
`THREAD_MODE` stays `fresh` at the end of this PR.

## Pre-coding declarations (per CONTRIBUTING.md)

- **Regression safety**: auto-testable for the only code entering `make check` — a tiny tested
  library (`ab_replay_lib.py`: uncached-input + ratio + cost-estimate math over fixtures, AND
  the safe-argv builders). The live runner + the measurement are operator-run, NOT in
  `make check` (like `verify-v13-5.py`).
- **Outcome measurement**: primary = **uncached-input ratio** =
  `sum(input-cached, continue) / sum(input-cached, fresh)`. **Pre-registered screen bars (no flip
  bar — the screen never flips):**
  - `ratio > 0.90` -> **stay-fresh** (no meaningful payoff even in best-case caching; a real
    fold loop caches less, so it will not beat this).
  - `ratio <= 0.90` AND quality equivalent AND not warmup-confounded -> **escalate-to-full-rigor**
    (promising in the best case; a best-case + N=3 + order-biased screen cannot justify a flip).
  - warmup-confounded (fresh's OWN calls 2/3 already substantially cached) OR quality not
    equivalent / unclear -> **inconclusive** -> stay fresh + escalate.
  Report cache-share per mode + a rough `est_cost` ratio (documented price ESTIMATE for codex
  0.130 / gpt-5.5 — labelled an estimate, not authoritative). Quality = **manual** equivalence
  read (table, below): the driver compares fresh vs continue findings on the same plan; any
  non-equivalence (continue going lazy on resume — "already reviewed, no new findings") forces
  stay-fresh / inconclusive.
- **Pre-registered run ORDER** (iter-3 FN3 — controls cross-mode prefix-cache contamination): run
  the **fresh block first** (3 new-session calls), THEN the **continue block** (seed + 2 resume).
  Rationale: fresh-first warms the server-side prefix cache, so continue (running second) gets
  *every* caching advantage. That biases the screen TOWARD continue looking cheap — so a
  **stay-fresh** verdict under this order is robust (continue had the advantage and still didn't
  win), and a continue-looks-cheap result is correctly treated as **escalate**, never flip.
  Record per-call UTC timestamps + per-call uncached input; if fresh's own calls 2/3 are already
  substantially cached, the cross-mode ratio is confounded -> **inconclusive**.

## Scope

### A. The small real A/B screen — `scripts/ab-replay.py` (operator-run, NOT in `make check`)

- **Subject**: ONE real, large, checked-in plan P (default
  `docs/plans/2026-05-31-skill-pr2-bucket-a-skill-wrapper.md`). Reviewing the SAME plan at
  iters 1/2/3 is the minimal best-case test of whether resume caches the plan+repo context — no
  manufactured corpus needed (and explicitly a best case, per the Scope decision).
- **Run order (pre-registered)**: fresh block (3 new-session calls, iters 1/2/3) FIRST, then the
  continue block (seed iter 1 + resume iters 2/3). Per-call UTC timestamps recorded.
- **Pinned safe argv** (iter-3 FN2 — built by pure functions in `ab_replay_lib.py`, unit-tested
  at V-1; all calls go through the same `scripts/run-with-clean-env.py` wrapper the Makefile uses):
  - **fresh / seed**: `scripts/run-with-clean-env.py -- codex exec --json -C <repo-abspath>
    --sandbox read-only --color never "<prompt>" < /dev/null` (stdout JSONL -> `/tmp`).
  - **resume**: `scripts/run-with-clean-env.py -- codex exec resume <tid> -c
    sandbox_mode=read-only --json "<prompt>" < /dev/null` (resume defaults to workspace-WRITE
    WITHOUT `-c sandbox_mode=read-only`; it does NOT take `-C` / `--sandbox` — memory
    `codex-json-resume-behavior` + [Makefile:191](../../Makefile)).
  - `--json` is added on ALL calls (the Makefile's non-continue fresh path omits it; the screen
    needs `turn.completed.usage`) — a documented close-mirror deviation.
  - `< /dev/null` on every call (codex `--json` hangs on open stdin — memory
    `codex-json-resume-behavior`).
- **Prompt**: built to **closely mirror** the Makefile `review-plan-by-codex` prompt
  ([Makefile:186](../../Makefile)); the exact prompt used is recorded in the result. (For a
  screen a documented close-mirror is acceptable; the full byte-identity test is the BACKLOG
  escalation.)
- **Raw JSONL -> `/tmp` only, NEVER committed** (iter-2 FN2). The result + design note carry
  only AGGREGATE + per-call uncached numbers + a qualitative quality note — no raw transcripts.
- **Simple cap**: abort if total wall-clock > 30 min or a single call runs away; ~6 calls on
  one plan is the bounded cost (~$10-20 est).
- **Env**: operator preflight (clean codex env) PLUS the script reuses
  `scripts/run-with-clean-env.py` for the prefix scrub (matches the Makefile exactly). Records
  `codex --version` + model in the result.

### B. Comparison + safe-argv builders — `scripts/ab_replay_lib.py` (tiny, unit-tested in `make check`)

- Parse `turn.completed.usage` from each mode's JSONL; per call
  `uncached_input = input_tokens - cached_input_tokens` (guard `info=None` / missing fields).
- Primary: `uncached_input_ratio = sum(uncached, continue) / sum(uncached, fresh)`. Report
  **per-call** uncached for BOTH modes (the warmup-confound detector), cache-share per mode, and a
  rough `est_cost` ratio (documented constants).
- A test pins that `cached_input_tokens` is a SUBSET of `input_tokens` and is never counted as
  a token-count "saving".
- **Safe-argv builders** live here too (pure functions: `build_fresh_argv(repo, prompt)`,
  `build_resume_argv(tid, prompt)`), so the pinned read-only argv is unit-testable WITHOUT
  running codex (V-1).

### C. Screen verdict + design note (NO flip — screen-only)

- **Always**: a short `docs/design-notes/2026-06-01-continue-thread-ab-result.md` recording the
  aggregate numbers + per-call uncached (warmup check) + the **manual quality equivalence table**
  + the verdict (NO raw JSONL).
- **stay-fresh** (`ratio > 0.90`): no default change; update BACKLOG `continue-thread-pr-followup`
  to "screened directionally; no best-case payoff; staying fresh".
- **escalate-to-full-rigor** (`ratio <= 0.90`, quality equivalent, not warmup-confounded): no
  default change (the screen cannot flip); update BACKLOG to "screen shows a best-case payoff;
  escalate to the full-rigor representative measurement before any flip", carrying the full-rigor
  spec (evolving corpus + seeded-defect oracle + cost model + byte-identity prompt test).
- **inconclusive** (warmup-confounded, or quality unclear): record it; stay fresh; BACKLOG ->
  escalate.
- **In ALL cases `THREAD_MODE` stays `fresh`.** The flip is out of scope for this PR.

### NOT in scope

- **No default flip** — the screen never flips `THREAD_MODE`; the flip requires the full-rigor
  BACKLOG measurement.
- No change to the seed/resume mechanism or the V-13.5 safety gate (`scripts/verify-v13-5.py`).
- No manufactured corpus, seeded-defect oracle, gate-0 pre-probe, or byte-identity prompt test
  (full-rigor BACKLOG escalation only).
- No multi-repo propagation.

## Verification

- **V-1 (library unit tests, in `make check`)** `tests/test_ab_replay_lib.py`:
  (i) uncached-input + ratio math; cached-is-not-a-saving; `info=None`/missing-field guards.
  (ii) **safe-argv builders** — fresh/seed argv carries `-C <repo>`, `--sandbox read-only`,
  `--json`, `--color never`, runs under `run-with-clean-env.py`, with stdin `/dev/null`, and
  rejects unexpected/unsafe flags; resume argv carries `-c sandbox_mode=read-only` + `--json` and
  does NOT carry workspace-write / `-C` / `--sandbox`. Mirrors the argv-capture pattern in
  `tests/test_makefile_review_targets.py`. Committed tiny fixtures; zero live calls.
- **V-2 (default unchanged — screen never flips)**: assert `THREAD_MODE` default is still `fresh`
  in BOTH [Makefile:94](../../Makefile) AND `shared/Makefile.review.tmpl`;
  `tests/test_selftest_overlap.py` stays green. (No flip branch exists in this PR.)
- **V-3 (live A/B screen, operator-run, NOT in `make check`)**: run `ab-replay.py` under a clean
  env in the pre-registered order; aggregate + per-call uncached numbers + the manual quality
  equivalence table populate the design note + Measured-result table; verdict per B/C.
- **V-4 (env preflight)**: Codex.app quit, `codex` logged in, network/quota OK, connected-MCP
  auth healthy or disabled (LESSONS 2026-05-30 — an expired MCP token aborts codex before first
  output).

## Implementation rollout (focused commits; Tier-1 fresh-Claude review each)

1. `scripts/ab_replay_lib.py` (metric math + safe-argv builders) + `tests/test_ab_replay_lib.py`
   (V-1). Pure functions first.
2. `scripts/ab-replay.py` (live runner: pre-registered order = 3 fresh then seed + 2 resume;
   JSONL -> `/tmp`; per-call UTC timestamps; prints aggregates + per-call uncached + records
   prompt/version/model; reuses `run-with-clean-env.py`).
3. Live run (V-3) under clean env; fill the manual quality equivalence table; write the design
   note + fill Measured-result.
4. Screen verdict -> design note + BACKLOG update (stay-fresh / escalate-to-full-rigor /
   inconclusive). **NO Makefile flip** (screen-only); V-2 asserts the default is unchanged.
   Approval gate before the verdict/design-note commit.

Plan-PR-then-impl-PR: this docs-only plan PR merges first; implementation branches
`feat/continue-thread-ab-measurement` off updated main.

## Risks

- **Prefix-cache ORDER confound (HIGH — iter-3 FN3)**: whichever mode runs second hits a cache
  warmed by the first. Mitigation: pre-registered fresh-first order biases TOWARD continue (so a
  stay-fresh verdict is robust); the uncached-input ratio nets each side's own cached tokens; and
  per-call uncached exposes warmup (fresh's own calls 2/3 already cached -> confounded ->
  inconclusive). A null/inverted/confounded ratio is a valid stay-fresh/inconclusive, never a flip.
- **Best-case caching (HIGH — iter-3 FN1, why this is a SCREEN)**: same-plan-3x is the friendliest
  case for resume; a real fold loop's plan changes between iters and caches less. The screen can
  disconfirm (no payoff even here) or motivate escalation (payoff here) — never confirm a flip.
- **Small sample (MED — screen trade-off)**: N=3 on ONE plan is a screen, not a robust estimate.
  Borderline -> "inconclusive -> stay fresh + escalate", never a forced flip.
- **Manual quality eyeball (MED — screen trade-off)**: subjective; the equivalence table makes it
  auditable (iter-3 FN5). Any non-equivalence -> stay-fresh / inconclusive.
- **Cost (LOW)**: ~6 calls on one plan, wall-clock-capped; ~$10-20 est.
- **Codex env contention (MED)**: clean-env preflight (V-4) + `run-with-clean-env.py` scrub;
  LESSONS 2026-05-30.

## Critical files / context

- [Makefile:94](../../Makefile) (`THREAD_MODE ?= fresh` — the screen asserts it STAYS `fresh`; no
  flip), [:186](../../Makefile) (prompt to mirror), [:206](../../Makefile) (seed argv),
  [:191](../../Makefile) (resume argv — `-c sandbox_mode=read-only`, no `-C`/`--sandbox`).
- [scripts/run-with-clean-env.py](../../scripts/run-with-clean-env.py) — the prefix-aware env
  scrubber the Makefile wraps every codex call in; the screen reuses it.
- `shared/Makefile.review.tmpl` — byte-identical mirror; V-2 asserts the default is unchanged in both.
- [scripts/extract-codex-session-id.py](../../scripts/extract-codex-session-id.py) — reused for the seed thread-id.
- `tests/fixtures/codex-json-stream.jsonl` + [tests/test_codex_jsonl_fixture.py:150](../../tests/test_codex_jsonl_fixture.py) — the `turn.completed.usage` schema the helper parses.
- `tests/test_makefile_review_targets.py` — the argv-capture shim pattern V-1's safe-argv test mirrors.
- `BACKLOG.md` `continue-thread-pr-followup` — parked entry; gets the screen result + (if escalate) the full-rigor-escalation spec.
- `~/.claude/plans/what-else-i-want-majestic-rain.md` (external) PR-1 cond. 2 — the meta-plan bar this refines (deviation 2) and defers the flip to (deviation 3).

## Iteration log (this PR)

| Iter | Reviewer | Date | Counts (3/2/1) | Verdict | Notes |
|---|---|---|---|---|---|
| 0.5 | Fact-check (deterministic + Codex interp) | 2026-06-01 | 0 / 2 / 0 | no imp-3 -- proceed | Deterministic `verify-plan-facts.py`: 12 verified (all real Makefile/script/test anchors + make targets); 8 "failed" = 6 files-this-PR-creates + 2 bare-basename drift; 5 not_verifiable = cli_flag_ref (deferred by design). Codex interp: no imp-3. Folded (a): bare-basename test refs -> path-explicit; added a "Files this PR creates" list. |
| 1 | Codex (cross-direction) | 2026-06-01 | 3 / 2 / 0 | do-not-implement | All 5 folded (a). **FN1 (imp-3)** raw total-token ratio doesn't measure cache payoff -> **uncached-input ratio**. **FN2 (imp-3)** vacuous quality guard -> seeded-defect corpus + inconclusive fallback. **FN3 (imp-3)** "prompt = f(contents,iter)" imprecise (path not contents) -> byte-identity contract. **FN4 (imp-2)** post-hoc gate-0 threshold -> pre-registered bars. **FN5 (imp-2)** files-list contradicted gate-0 early-exit -> 3 tiers. |
| 1.5 | Claude (consistency self-check, rounds a-d) | 2026-06-01 | doc-drift 4+3+5 | folded + driver-stop | Substantive invariants consistent EVERY round; residual was the falsifiable-enumeration trap (memory [[consistency-loop-process-gotchas]]). Rounds a(4)/b(3)/c(5)/d — all surface/enumeration drift, folded; DRIVER-STOP capped at 4 rounds per the anti-ritual rule. |
| 2 | Codex (cross-direction) | 2026-06-01 | 2 / 3 / 0 | do-not-implement | imp-3 3->2 (NEW + real). **FN1** ~$30 cap had no price constants + uncached-input silently refined meta-plan cond. 2. **FN2** live JSONL had no retention/sanitization policy (data-exposure). **FN3/4/5** gate-0 non-representative; env-scrub manual; oracle not machine-checkable. ALL real. Triage PAUSED for a user scope decision. |
| 2 (resolution) | Driver + user scope decision | 2026-06-01 | -- | rewrite to lighter scope | User chose **lighter-directional** (over full-rigor / pause). iter-2 resolved by scoping down: **FN1 metric-correctness KEPT** (uncached-input) + cost as a rough labelled estimate + documented as deviation 2; **FN2 data-exposure KEPT** simply (raw JSONL `/tmp`-only, never committed, aggregates-only in the design note); **FN3 gate-0 DROPPED** (the small A/B IS the measurement); **FN5 machine-oracle DROPPED** (manual quality eyeball); **FN4 env -> operator preflight**. Full-rigor automated harness PARKED to BACKLOG as the escalation. Plan rewritten to directional scope. |
| 3 | Codex (cross-direction, lighter rewrite) | 2026-06-01 | 3 / 2 / 0 | do-not-implement | Loop-reset for the scope-pivot rewrite; reviewed fresh. imp-3 3->2->3 (NOT converging by iteration). **FN1 (imp-3)** same-plan-3x replay is best-case caching, not a real fold loop -> the cheap test can SOUNDLY conclude stay-fresh or escalate-to-full-rigor, but CANNOT justify a flip (it becomes a SCREEN). **FN2 (imp-3)** runner doesn't pin safe argv (resume defaults to workspace-WRITE without `-c sandbox_mode=read-only`; fresh/seed need `-C <repo> --sandbox read-only`) -> safety gap. **FN3 (imp-3)** prefix-cache ORDER effects uncontrolled (whichever mode runs second hits a warm cache) -> biased ratio. **FN4 (imp-2)** flip-adoption docs miss generated surfaces (MOOT once FN1 removes the flip path). **FN5 (imp-2)** manual quality read not auditable -> needs an equivalence table. PROPOSED RESOLUTION: fold to a SCREEN-ONLY design (verdict in {stay-fresh, escalate, inconclusive}, NEVER flip) + pinned safe argv + pre-registered run order + quality equivalence table; DRIVER-STOP the Codex loop (3 rounds, non-converging, findings now real-and-foldable, residual validation is empirical + Tier-1 at impl). **USER DECISION 2026-06-01: run the cheap screen.** NEXT (fresh session -- this one loaded 2h+): **(1) fold this plan to SCREEN-ONLY** -- verdict in {stay-fresh, escalate-to-full-rigor, inconclusive}, NEVER flip; remove the flip path from Scope C + simplify V-2 to "assert default stays `fresh`"; FN4 becomes moot. **(2) Scope A: pin safe argv** -- fresh/seed = `codex exec --json -C <repo> --sandbox read-only --color never "<prompt>" < /dev/null`; resume = `codex exec resume <tid> -c sandbox_mode=read-only --json "<prompt>" < /dev/null` (resume defaults to workspace-WRITE without the `-c`); add a shim test (V-1) asserting cwd/read-only/stdin/rejected-flags, mirroring `tests/test_makefile_review_targets.py` thread shim. **(3) FN3: pre-register run ORDER + record per-call timestamps** (cross-mode cache contamination -> if the ratio depends on warmup, inconclusive). **(4) FN5: manual quality EQUIVALENCE table** in the design note (per fresh imp-3: did continue produce an equivalent? missing any -> stay/inconclusive). **(5) consistency check (cap 1 round) -> approval gate -> build** `scripts/ab_replay_lib.py`+test, `scripts/ab-replay.py` **-> live run** (~$10-20, clean codex env: quit Codex.app) **-> decide + design note + BACKLOG update.** All five iter-3 findings + the screen-only reframing are folded by this. |
| 3 (resolution) | Driver fold (fresh session) + user decision | 2026-06-01 | -- | folded to SCREEN-ONLY | All 5 iter-3 findings folded per the iter-3 NEXT spec. **FN1**: screen-only reframing — verdict in {stay-fresh, escalate-to-full-rigor, inconclusive}; the flip path removed from Scope C; the title, Scope decision, Goal, Pre-coding bars, V-2, rollout step 4, and Risks all rewritten to "never flips"; FN4 moot. **FN2**: pinned read-only argv (fresh/seed `-C <repo> --sandbox read-only --json --color never`; resume `-c sandbox_mode=read-only --json`, no `-C`/`--sandbox`), built by unit-tested pure functions (V-1), all wrapped in `scripts/run-with-clean-env.py` — the env-scrub wrapper the Makefile ALREADY uses (discovered this session via code read; folds iter-2 FN4 from manual-preflight to reuse). **FN3**: pre-registered run ORDER (fresh block first, then continue — biases toward continue so a stay-fresh verdict is robust) + per-call UTC timestamps + per-call uncached reported as a warmup-confound detector (inconclusive if fresh's own calls 2/3 are already cached). **FN5**: manual quality EQUIVALENCE table in the design note. **FN4** moot (no flip path). No Makefile flip ships in this PR. |

## Evidence table — what was folded and where

| Source | Finding | Importance | Resolution | Touched sections |
|---|---|---|---|---|
| Codex fact-check (iter 0.5) | Rollout steps named test files by bare basename | 2 | Folded (a): path-explicit (PR-2 precedent) | (superseded by the lighter rewrite) |
| Codex fact-check (iter 0.5) | 6 net-new files flagged "not found" by the verifier | 2 | Folded (a): explicit "Files this PR creates" list | Context |
| Codex iter-1 FN1 | Raw total-token ratio doesn't measure the cache payoff (cached is a subset; price discount) | 3 | **KEPT in lighter scope**: primary = uncached-input ratio | Deviation 2; Pre-coding; Scope B |
| Codex iter-1 FN2 | Quality guard vacuous without known defects | 3 | Rigor version used a seeded-defect oracle; **lighter scope replaces it with a manual quality eyeball** (FN5 below) | Scope decision; Scope A/C; Risks |
| Codex iter-1 FN3 | Prompt claim imprecise; harness could drift from the Makefile prompt | 3 | **Lighter**: documented close-mirror of the Makefile prompt + record the prompt used (byte-identity test parked to BACKLOG) | Context; Scope A |
| Codex iter-1 FN4 | Gate-0 threshold decided after seeing data | 2 | gate-0 DROPPED in lighter scope; the one pre-registered bar is the flip bar `<= 0.90` | Scope decision; Pre-coding |
| Codex iter-1 FN5 | Files-list contradicted gate-0 early-exit | 2 | Moot — gate-0 dropped; the files-list is now flat | Context |
| Codex iter-2 FN1 | ~$30 cap had no price constants; uncached-input silently refined meta-plan cond. 2 | 3 | Folded: cost is a rough LABELLED estimate + simple wall-clock cap; the metric deviation is documented (deviation 2) | Deviation 2; Pre-coding; Scope A |
| Codex iter-2 FN2 | Live JSONL had no retention/sanitization/gitignore policy (data-exposure) | 3 | Folded: raw JSONL `/tmp`-only, NEVER committed; aggregates-only in the design note | Scope A/C; NOT in scope |
| Codex iter-2 FN3 | Gate-0 decides stay-fresh from a non-representative probe | 2 | Folded by DROPPING gate-0 — the small A/B itself is the (representative) measurement | Scope decision; Scope A |
| Codex iter-2 FN4 | "Clean env" manual, not harness-enforced | 2 | Folded (iter-3): reuse `scripts/run-with-clean-env.py` (the Makefile's own wrapper) + operator preflight; full env-enforcement is the BACKLOG escalation | Scope A; V-4 |
| Codex iter-2 FN5 | Seeded-defect oracle not machine-checkable | 2 | Folded by DROPPING the automated oracle -> manual quality eyeball (lighter-scope trade-off, with stay-fresh-if-degraded default) | Scope decision; Pre-coding; Risks |
| Codex iter-3 FN1 | Same-plan-3x replay is best-case caching, not a real fold loop — can't justify a flip | 3 | Folded: SCREEN-ONLY — verdict in {stay-fresh, escalate-to-full-rigor, inconclusive}; flip path removed; a flip requires the full-rigor BACKLOG measurement | Title; Scope decision; Deviation 3; Goal; Pre-coding; Scope C; V-2; Rollout; Risks |
| Codex iter-3 FN2 | Runner didn't pin safe argv (resume defaults to workspace-WRITE) | 3 | Folded: pinned read-only argv via pure builders + a V-1 argv test (mirrors the thread shim); all calls wrapped in `scripts/run-with-clean-env.py` | Context; Scope A; Scope B; V-1; Critical files |
| Codex iter-3 FN3 | Prefix-cache ORDER effects uncontrolled -> biased ratio | 3 | Folded: pre-registered run order (fresh-first, conservative) + per-call UTC timestamps + per-call uncached warmup detector -> inconclusive if confounded | Pre-coding; Scope A/B; Risks |
| Codex iter-3 FN4 | Flip-adoption docs miss generated surfaces | 2 | Moot — folded by FN1 (no flip path ships in this PR; V-2 asserts the default is unchanged) | Scope C; V-2 |
| Codex iter-3 FN5 | Manual quality read not auditable | 2 | Folded: a manual quality EQUIVALENCE table in the design note (per finding: did continue reproduce it? missing any -> stay/inconclusive) | Pre-coding; Scope C; V-3; Risks |

## Measured result (filled at V-3)

Run 2026-06-01, codex-cli 0.130.0. Full detail + mechanism + quality table in
[docs/design-notes/2026-06-01-continue-thread-ab-result.md](../design-notes/2026-06-01-continue-thread-ab-result.md).

| Mode | total input | total cached_input | total uncached_input | cache share | total output | wall-clock (s) |
|---|---|---|---|---|---|---|
| fresh | 5,167,507 | 4,603,392 | 564,115 | 0.891 | 44,530 | 1,020.4 |
| continue | 11,602,178 | 10,651,008 | 951,170 | 0.918 | 60,399 | 684.5 |

**Per-call uncached input (warmup-confound check)**: fresh 1/2/3 = 200,835 / 124,712 / 238,568
(non-monotonic -> NOT a within-block cache-down -> not confounding); continue 1/2/3 = 186,476 /
359,033 / 405,661 (GROWS monotonically -- each resume re-sends the accumulating thread, the
structural reason continue costs more).

**Uncached-input ratio (continue/fresh)**: **1.686** (bar `> 0.90`). **est_cost ratio (rough,
placeholder prices)**: ~1.81 (illustrative only).

**Manual quality equivalence read**: both modes produced full FN-tagged reviews; continue did NOT
go lazy on resume (more output -- 60,399 vs 44,530 tokens). Quality roughly equivalent (moot for a
stay-fresh verdict, recorded to rule out an artifact):

| Fresh finding (one-line) | Continue reproduced an equivalent? | Notes |
|---|---|---|
| Source conflict: prompt says iter 1/2/3 but on-disk plan P is post-iter-4 (merged) | Yes -- all fresh + all continue calls flagged it | Property of replaying a merged plan, not a mode diff -> equivalent |
| Substantive plan-body imp-3-style findings | Yes -- continue resumes returned comparable multi-finding reviews | No "already reviewed, nothing new" laziness |

**Screen bars**: `ratio > 0.90` -> stay-fresh; `ratio <= 0.90` + quality equivalent + not
warmup-confounded -> escalate-to-full-rigor; confounded/unclear -> inconclusive. **The screen
never flips `THREAD_MODE`.**

**Verdict: STAY-FRESH.** Decisive (1.686 >> 0.90). Continue uses ~69% MORE uncached input (and
~81% more rough est-cost) than fresh -- resume re-sends the growing thread, and the higher cache
*share* (0.918 vs 0.891) does not offset a total input 2.25x fresh's. This is the best case for
continue (same plan x3) and it still lost, so **no full-rigor escalation** (the escalation was for
a promising-but-ambiguous `ratio <= 0.90`; this is an unambiguous disconfirmation). `THREAD_MODE`
default unchanged (`fresh`); `continue` stays opt-in. `uncached_input = input - cached_input`;
per-call detail + timestamps are in the `/tmp` JSONL (NOT committed).
