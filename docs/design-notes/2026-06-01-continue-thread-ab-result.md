# Continue-thread A/B SCREEN — result + verdict (2026-06-01)

**Verdict: STAY-FRESH.** `THREAD_MODE` stays `fresh` (unchanged). The continue
(resume-one-thread) hypothesis is **disconfirmed** directionally: continue used
**1.69x MORE** uncached input than fresh — the opposite of the hoped-for discount.
No escalation to a full-rigor measurement is warranted (the screen showed no
best-case payoff to chase; it showed a structural penalty).

This is the screen-only measurement specified in
[docs/plans/2026-06-01-continue-thread-ab-measurement.md](../plans/2026-06-01-continue-thread-ab-measurement.md).
By design the screen can only conclude *stay-fresh* / *escalate-to-full-rigor* /
*inconclusive* — it never flips the default.

## Setup (operator-run, NOT in `make check`)

- **Runner**: `scripts/ab-replay.py --execute` (metric + argv logic in the
  unit-tested `scripts/ab_replay_lib.py`).
- **Subject plan P**: `docs/plans/2026-05-31-skill-pr2-bucket-a-skill-wrapper.md`,
  reviewed at iterations 1/2/3.
- **codex**: codex-cli 0.130.0. **Run date**: 2026-06-01.
- **Pre-registered run order**: FRESH block (3 new sessions) first, then CONTINUE
  (seed iter 1 + resume iters 2/3 on one thread, tid
  `019e8479-9e39-7d40-8cd8-daf3b7ebf232`). Fresh-first warms the server prefix
  cache *for continue*, biasing TOWARD continue looking cheap — so a stay-fresh
  verdict is robust (it survived the bias).
- **Metric**: uncached-input ratio = `sum(input - cached, continue) /
  sum(input - cached, fresh)`. Primary, price-independent. Pre-registered bar:
  `> 0.90` → stay-fresh.
- **Raw JSONL**: written to a `/tmp` dir only, NOT committed (only the aggregates
  below leave `/tmp`).

## Aggregate result

| Mode | total input | total cached_input | total uncached_input | cache share | total output | wall-clock (s) |
|---|---|---|---|---|---|---|
| fresh | 5,167,507 | 4,603,392 | 564,115 | 0.891 | 44,530 | 1,020.4 |
| continue | 11,602,178 | 10,651,008 | 951,170 | 0.918 | 60,399 | 684.5 |

- **Uncached-input ratio (continue / fresh) = 1.686** (bar `> 0.90` → **stay-fresh**).
- **est_cost ratio (continue / fresh) ≈ 1.81** — ROUGH, PLACEHOLDER prices
  (`ab_replay_lib.PLACEHOLDER_PRICES_USD_PER_MTOK`); illustrative only, NOT
  authoritative. The verdict rests on the price-independent uncached ratio, not
  this number.

### Per-call detail (input / cached / uncached / shell commands)

| call | input | cached | uncached | cache% | shell cmds |
|---|---|---|---|---|---|
| fresh iter 1 | 1,716,099 | 1,515,264 | 200,835 | 88.3% | 48 |
| fresh iter 2 | 1,415,848 | 1,291,136 | 124,712 | 91.2% | 46 |
| fresh iter 3 | 2,035,560 | 1,796,992 | 238,568 | 88.3% | 62 |
| continue seed (1) | 3,009,004 | 2,822,528 | 186,476 | 93.8% | 66 |
| continue resume 2 | 4,096,761 | 3,737,728 | 359,033 | 91.2% | **15** |
| continue resume 3 | 4,496,413 | 4,090,752 | 405,661 | 91.0% | **4** |

**This table is the heart of the result — and it shows continue behaving exactly
as designed, yet still losing:**

- **Continue used context efficiently** — its per-resume shell-command count
  COLLAPSES (66 → 15 → 4). The resumes re-inspect the repo far less because they
  already hold it in context. So continue is NOT being used naively; it is doing
  the right thing.
- **Continue loses anyway because it CARRIES the growing transcript as input every
  turn** (3.0M → 4.1M → 4.5M): every prior command's output + reasoning + messages
  is re-fed each resume. Even at ~91% cache, the 9% uncached tail of a 4.5M-token
  transcript (406k) exceeds the entire uncached cost of a lean 2M-token fresh
  review — and the *cached* volume continue pays for (10.6M) is 2.3x fresh's
  (cached tokens are discounted, not free). Fresh is the inverse: re-inspect every
  time (~50 commands) but stay lean (~1.4–2M) and discard.
- For PLAN REVIEW — small marginal new work per iteration, large stable context —
  "re-read but stay lean" beats "read once but carry the whole transcript forever."
- **Warmup-confound check** (iter-3 FN3): fresh's uncached is non-monotonic
  (201k → 125k → 239k) — not a progressive within-block cache-down — so the
  cross-mode comparison is not warmup-confounded in a way that undermines the
  verdict. (And fresh-first biased toward continue anyway, and continue still lost.)

## Manual quality equivalence read

Both modes produced full, substantive FN-tagged reviews; continue did **not** go
lazy on resume (it produced MORE output — 60,399 vs 44,530 tokens — and longer
agent messages). Quality is roughly equivalent, so the cost penalty is real work,
not degradation. (For a `stay-fresh` verdict quality is moot per the decision
logic — we are not adopting — but it is recorded to rule out a quality artifact.)

| Salient fresh finding | Continue reproduced an equivalent? | Notes |
|---|---|---|
| Source conflict: prompt says "iteration 1/2/3" but the on-disk plan P is post-iteration-4 (merged) | **Yes** — both fresh (all 3) and continue (seed + resumes) independently flagged it | A property of replaying a *merged* plan, not a mode difference; both noticed → equivalent |
| Substantive imp-3-style findings on the plan body (e.g. NEUTRALIZE trigger staleness in fresh iter 2) | **Yes** — continue resumes returned comparable multi-finding reviews (3–5 agent messages, ~4.4–5.6k chars each) | No "already reviewed, nothing new" laziness on resume |

## Why continue lost (mechanism)

`codex exec resume` continues ONE thread, so every resumed turn re-sends the
growing conversation (all prior review turns) as input. Prompt caching discounts
the *price* of the repeated prefix (continue's cache share is even higher than
fresh's), but the **uncached remainder still grows each turn**, and the absolute
input balloons (2.25x fresh). Fresh sessions each start lean and independent, and
— because the 3 fresh calls share the same plan+repo prefix — they ALSO get heavy
server-side prefix-cache hits (0.891 share) without paying the thread-accumulation
tax. Net: fresh is cheaper in uncached input, decisively.

This is the *best case* for continue (identical plan replayed 3x maximises cache
hits) and continue still lost — so a real fold loop, where the plan changes
between iterations and caches even less, would not reverse the result.

## Disposition

- `THREAD_MODE` default stays **`fresh`** (no Makefile change; the screen never
  flips). `THREAD_MODE=continue` remains available as an opt-in for anyone who
  wants single-thread continuity for non-cost reasons.
- **No full-rigor escalation.** The full-rigor measurement was the BACKLOG
  fallback for a *promising-but-ambiguous* (`ratio ≤ 0.90`) screen. This screen is
  an unambiguous disconfirmation, so there is nothing to escalate. Re-open only if
  the resume *mechanism* changes (e.g. codex adds a history-compacting resume that
  doesn't re-send the full thread).
- `BACKLOG.md` `continue-thread-pr-followup` updated with this result.

## Caveats (screen-scope, honest)

- **Large agentic non-determinism; N=1 per cell -> the precise 1.69x is NOISY.**
  `fresh-iter1` and `continue-seed-iter1` are the *identical* operation (a fresh
  review of P at iter 1), yet cost **1.72M vs 3.01M input** (the seed happened to
  run 66 shell commands vs fresh's 48). With one sample per cell, treat the
  magnitude as "continue is directionally more expensive," NOT as a precise 1.69x.
  What is NOT noise: the resume transcript-carry growth (3.0M -> 4.1M -> 4.5M) is
  monotonic and structural — even a lean seed could not close a 2.25x total-input
  gap over a 3-turn loop. The DECISION (don't flip the default) is robust; the
  exact ratio is soft.
- **We tested the AS-BUILT mechanism (same prompt for seed AND resume).** PR #33
  reuses the Makefile review prompt verbatim on resume (Makefile:186). A *smarter*
  continue design would send a lean "here is what changed for iter N" delta prompt
  to exploit the cached context and avoid re-feeding the full transcript. This
  screen does NOT rule that out — it rules out flipping the default to the
  mechanism as it exists today. The delta-prompt / history-compacting redesign is
  the BACKLOG escalation, not a refutation of this result.
- N=3 on ONE plan; a screen, not a robust estimate (see the non-determinism point).
- Prompt is a close ASCII mirror of the Makefile review prompt (Makefile:186), not
  byte-identical (byte-identity test parked to BACKLOG).
- est_cost uses placeholder prices — illustrative only; the verdict does not depend
  on it.
