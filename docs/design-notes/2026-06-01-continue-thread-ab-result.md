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

### Per-call uncached input (warmup-confound check, iter-3 FN3)

| call | fresh | continue |
|---|---|---|
| iter 1 (seed) | 200,835 | 186,476 |
| iter 2 | 124,712 | 359,033 |
| iter 3 | 238,568 | 405,661 |

- **Continue GROWS monotonically** (186k → 359k → 406k): each resume re-sends the
  accumulating thread history, so per-turn uncached input rises. This is the
  structural reason continue costs more — a higher cache *share* (0.918 vs 0.891)
  does not offset a total input that is 2.25x fresh's.
- **Fresh is non-monotonic** (201k → 125k → 239k) — NOT a progressive
  within-block cache-down, so the cross-mode comparison is not warmup-confounded
  in a way that would undermine the verdict. (And even if it were, fresh-first
  biased toward continue, and continue still lost decisively.)

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

- N=3 on ONE plan; a screen, not a robust estimate. But the result is directional
  and far from the bar (1.69 vs 0.90), and the mechanism (monotone input growth on
  resume) is structural, not noise.
- Prompt is a close ASCII mirror of the Makefile review prompt (Makefile:186), not
  byte-identical (byte-identity test parked to BACKLOG).
- est_cost uses placeholder prices — illustrative only; the verdict does not depend
  on it.
