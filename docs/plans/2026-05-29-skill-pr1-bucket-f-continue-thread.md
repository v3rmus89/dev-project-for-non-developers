# PR-1: Bucket F — Continue-thread mode for Codex

## Why

`make review-plan-by-codex` starts a fresh Codex session on every call.
When a plan loop runs 5+ iterations, each iter pays the full context-window
cost from scratch (no prompt caching across sessions). Thread continuation
(`codex exec resume <SESSION_ID>`) lets subsequent iterations resume the
prior context, potentially lowering token cost via cache hits.

This is a **hypothesis** — the default stays `THREAD_MODE=fresh` until the
A/B replay gates in the Verification section pass (meta-plan PR-1).

## Scope

| Row | What changes | How |
|-----|-------------|-----|
| A | `scripts/extract-codex-session-id.py` (new) | Reads JSONL from `codex exec --json`, extracts `session_meta.payload.id` (V-13 confirmed field path). Fails with non-zero exit if no `session_meta` event found. |
| B | `Makefile` (dogfood) | Add `THREAD_FILE` + `THREAD_JSONL_FILE` vars (KEY-derived). Extend `review-plan-by-codex` recipe with `THREAD_MODE` branch. Add `loop-reset` cleanup for `THREAD_FILE` + `THREAD_JSONL_FILE`. |
| C | `shared/Makefile.review.tmpl` | Mirror scope B changes (byte-identity contract). |
| D | `shared/scripts-extract-codex-session-id.py.tmpl` (new) | Mirror scope A (same content). |
| E | `bootstrap_lib/render.py` `SHARED_TEMPLATE_MAP` | Register `D`. |
| F | `bootstrap_lib/manifest.py` `EXECUTABLE_TARGETS` | Register the script as executable on bootstrap. |
| G | Tests | `tests/test_extract_codex_session_id.py` (unit tests for script A). `tests/test_selftest_overlap.py` + `tests/test_makefile_review_targets.py` extended to cover new vars/targets. Test matrix in `tests/test_makefile_review_targets.py` using a codex argv-logging shim: (1) fresh — no `--json`, no `THREAD_FILE` written; (2) continue, no existing `THREAD_FILE` — runs `codex exec --json`, writes `THREAD_FILE` + `THREAD_JSONL_FILE`; (3) continue, `THREAD_FILE` exists — runs `codex exec resume $SESSION_ID`; (4) "session not found" fallback — clears stale `THREAD_FILE` + `THREAD_JSONL_FILE`, starts fresh; (5) `loop-reset` — removes `THREAD_FILE` + `THREAD_JSONL_FILE`. |

**NOT in scope (no code deliverable)**: default flip from `THREAD_MODE=fresh` → `continue`
(deferred to post-A/B-replay gates — see Verification). V-13.5 Part 2 live
sandbox-inheritance probe (manual operator step, no code shipped — run before merging;
Part 1 is automated via the Scope G test matrix). Tier-2 bot quality comparison
(secondary signal only).

## Architecture decisions

### Session ID extraction
**V-13 confirmed (2026-05-29, commit da776ee)**: session ID lives at
`session_meta.payload.id` in the `--json` event stream (ULIDv7 UUID, NOT
a top-level `session_id` field). The extraction script reads JSONL line by
line and prints the ID from the first `session_meta` event.

**Guard required**: the first `token_count` event has `info: null`. Any
future code reading `cached_input_tokens` must guard `if info is not None`.
The extraction script does NOT touch token fields — this guard is a
reminder for the A/B replay implementation (post-PR-1).

### When `--json` is added to `codex exec`
`--json` causes all events to stream to stdout as JSONL (instead of the
terminal-friendly display). `--output-last-message` continues to write the
review text to the specified file; the JSONL stdout is captured separately.

On the FIRST call when `THREAD_MODE=continue` and no `THREAD_FILE` exists:
1. Run `codex exec --json --output-last-message ... > $(THREAD_JSONL_FILE)`
2. Run `scripts/extract-codex-session-id.py $(THREAD_JSONL_FILE) > $(THREAD_FILE)`
3. Display review: `cat $(PLAN_REVIEW_OUT_CODEX)` (unchanged)

On SUBSEQUENT calls when `THREAD_FILE` exists:
1. Read `SESSION_ID = $(cat $(THREAD_FILE))`
2. Run `codex exec resume $SESSION_ID --output-last-message ...`
   (`--json` NOT needed for normal operation — session ID already known)
3. Display review as normal

**V-13.5 exception**: when running the V-13.5 inheritance verification, the
resume call explicitly uses `--json` to capture the resumed JSONL for
assertion (see Verification). This is a one-time verification step, not
normal operation.

When `THREAD_MODE=fresh` (the default — unchanged): current behavior, no
`--json`, no session-ID tracking.

### `-C`/`--sandbox` on resume
V-13.5 verifies that `codex exec resume` inherits `-C` and `--sandbox`
from the original session. Per iter-4 F2, passing these flags defensively
on `resume` is **CLI-rejected** (`unexpected argument`). Do NOT re-pass them.
V-13.5 is the proof that inheritance holds.

### Key/path derivation
`THREAD_FILE = /tmp/plan-review-$(KEY).thread`
`THREAD_JSONL_FILE = /tmp/plan-review-$(KEY).session.jsonl`

`KEY` is already defined in the Makefile as `sha256(realpath(CURDIR) + ":" + realpath(PLAN_FILE))[:12]`.
These paths are stable across sessions for the same repo + plan file, so
`THREAD_MODE=continue` works correctly across terminal restarts.

## Verification

### V-13 — session ID field (DONE)
Fixture at `tests/fixtures/codex-json-session.jsonl` (commit da776ee).
Field path pinned: `session_meta.payload.id`. 7 tests pass.

### V-13.5 — sandbox and cwd inheritance (mixed gate: Part 1 automated, Part 2 manual, required before merge)

**Part 1 — Makefile resume branch (shim-based, part of automated test matrix)**:
The test matrix in Scope G item (3) uses a fake codex shim to assert that when
`THREAD_FILE` exists, the Makefile recipe calls `codex exec resume $SESSION_ID`
(not `codex exec`). This verifies the Makefile branching logic without a live API call.

**Part 2 — Live inheritance probe (session UUID continuity, sandbox, cwd)**:
Run FROM the repo root using the actual codex CLI:
1. Start a fresh session to seed `THREAD_FILE`:
   ```
   make -C /abs/path/to/repo review-plan-by-codex \
     PLAN_FILE=docs/plans/<any>.md ITERATION=1 THREAD_MODE=continue
   ```
   → `THREAD_JSONL_FILE` is written; `THREAD_FILE` contains a UUID (`SESSION_ID`).
2. Probe inheritance directly using `codex exec resume --json`:
   ```
   # KEY derivation matches Makefile (sha256 of realpath(CURDIR):realpath(PLAN_FILE))[:12]
   KEY=$(python3 -c "import hashlib,os; \
     k=os.path.realpath('.')+':'+os.path.realpath('docs/plans/<plan>.md'); \
     print(hashlib.sha256(k.encode()).hexdigest()[:12])")
   SESSION_ID=$(cat /tmp/plan-review-$KEY.thread)
   codex exec resume "$SESSION_ID" --json \
     "Attempt to create a file at /tmp/test-v13-5-write.txt. Report what happened." \
     > /tmp/test-v13-5-resumed.jsonl
   ```
3. Assert ALL three from the resumed JSONL:
   a. `session_meta.payload.id` in `/tmp/test-v13-5-resumed.jsonl` equals `SESSION_ID`
      (session not renewed; same UUID proves continuation)
   b. `/tmp/test-v13-5-write.txt` does NOT exist after the resumed session
      (sandbox inheritance — read-only mode enforced)
   c. First `turn_context.payload.cwd` in resumed JSONL equals `realpath(CURDIR)`
      from the ORIGINAL session (cwd inherited)

If any assertion fails: the default flip is blocked; file a bug and keep `THREAD_MODE=fresh`.

### A/B replay gates (required before default flip; POST-PR-1)
Per meta-plan PR-1 Verification: pick a real folded plan + its committed
iter outputs (e.g. PR #10). Archive the exact prompt for each iter. Replay
twice against the archived plan-state-at-iter-N: once `THREAD_MODE=fresh`,
once `THREAD_MODE=continue`. Conditions:
1. `continue` total tokens ≥10% lower than `fresh`.
2. Per-iter wall-clock in `continue` not regressing >20%.
3. Cache-hit value `cached_input_tokens > 0` in `continue` JSONL.
4. Quality guard: no imp-3 findings `fresh` found that `continue` missed
   (adjudicate near-misses via Tier-2 cross-direction review).
Budget cap: 5 replay iter pairs, ~$30, 30 min wall-clock.

Until all 4 pass: `THREAD_MODE=fresh` is the default; `THREAD_MODE=continue`
is opt-in via env var.

## Critical files

- `scripts/extract-codex-session-id.py` (new)
- `shared/scripts-extract-codex-session-id.py.tmpl` (new)
- `Makefile` — lines 87–92 (KEY/path block), 104–141 (review-plan-by-codex), 284 (loop-reset)
- `shared/Makefile.review.tmpl` — mirror of above
- `bootstrap_lib/render.py` — `SHARED_TEMPLATE_MAP`
- `bootstrap_lib/manifest.py` — `EXECUTABLE_TARGETS`
- `tests/test_extract_codex_session_id.py` (new)
- `tests/test_selftest_overlap.py` — extend parity check for new vars
- `tests/test_makefile_review_targets.py` — extend for new targets/vars
- `tests/fixtures/codex-json-session.jsonl` — already committed (V-13)

## Risks

| Risk | Mitigation |
|------|-----------|
| `--json` breaks current review display | `--output-last-message` file is unchanged; `cat` at end still works. V-13.5 verifies end-to-end display. |
| `codex exec resume` drops `-C`/`--sandbox` | V-13.5 Part 2 all-3-gate prevents flip if inheritance fails. |
| THREAD_JSONL_FILE grows large | First-continue call writes it once; subsequent resumed calls don't capture JSONL. No accumulation across iters. |
| V-13.5 Part 2 needs `--json` on resume but normal ops don't | V-13.5 is a one-time manual gate; it explicitly passes `--json` to the `codex exec resume` probe command. Normal resumed calls in `review-plan-by-codex` do NOT use `--json`. |
| `info: null` guard missing in future A/B code | Parked reminder in BACKLOG. Not in this PR's scope. |
| Extraction script fails silently | Non-zero exit on missing `session_meta` event; Makefile recipe propagates error. |
| Session TTL: old sessions may expire before next iter | If `codex exec resume` fails with a "session not found" error, Makefile should fall back to `fresh` and log a warning. Add this fallback in the recipe. |

## Rollback

- **Escape hatch**: `THREAD_MODE=fresh` always bypasses thread continuation. No rebuild needed.
- **Stale session recovery**: if `codex exec resume` returns a "session not found" error, the
  Makefile recipe clears `THREAD_FILE` + `THREAD_JSONL_FILE`, logs a warning, and falls back
  to a fresh `codex exec` call for that iteration. The fallback does NOT silently swallow errors
  from other failure modes.
- **Full cleanup**: `make loop-reset PLAN_FILE=...` removes `THREAD_FILE` + `THREAD_JSONL_FILE`
  in addition to the existing hash/consistency/snapshot cleanup.
- **Default flip**: any flip from `THREAD_MODE=fresh` → `continue` as default is a SEPARATE PR
  after the A/B replay gates pass. This PR never changes the default.

## Implementation rollout

| Commit | Scope | Files |
|--------|-------|-------|
| 1 | `scripts/extract-codex-session-id.py` + unit tests | `scripts/extract-codex-session-id.py`, `tests/test_extract_codex_session_id.py` |
| 2 | Extend Makefile + template (THREAD vars, recipe branch, loop-reset cleanup) | `Makefile`, `shared/Makefile.review.tmpl` |
| 3 | Register in SHARED_TEMPLATE_MAP + EXECUTABLE_TARGETS | `bootstrap_lib/render.py`, `bootstrap_lib/manifest.py`, `shared/scripts-extract-codex-session-id.py.tmpl` |
| 4 | Extend selftest-overlap + makefile-review-targets tests | `tests/test_selftest_overlap.py`, `tests/test_makefile_review_targets.py` |

Tier-1 review (same-AI fresh subagent) after each commit before push.
`make check` passes before commit 4 merges. V-13.5 Part 2 manual gate runs after
commit 2 and before the PR is opened for Tier-2 review.

## Outcome measurement

No business metric — internal change. Measurable proxies post-merge:
- `cached_input_tokens` metric in `THREAD_MODE=continue` sessions > 0 (confirms cache hits)
- Token-cost trajectory in the next multi-iter plan loop (measured per the A/B replay gates)

## Iteration log

| Iter | Reviewer | Date | Counts (3/2/1) | Verdict | Notes |
|------|----------|------|----------------|---------|-------|
| 0.5 (fact-check) | Codex | 2026-05-29 | 0 imp-3 | clean | 7 verified (existing files/targets), 3 failed = expected new deliverables (`scripts/extract-codex-session-id.py`, `shared/scripts-extract-codex-session-id.py.tmpl`, `tests/test_extract_codex_session_id.py`), 4 not-verifiable (external `codex` CLI flags — deferred), 1 unsupported-external (`/tmp/test-v13-5-write.txt`). No blocking facts. |
| 1 | Codex | 2026-05-29 | 2 / 2 / 0 | do not implement yet | All 4 folded as (a). FN1 (imp-3) V-13.5 can't prove resume inheritance without resumed JSONL and only checked file absence vs the BACKLOG's all-3-gate → added V-13.5 Part 1 (shim test matrix) + Part 2 (live probe with `--json` on resume); Architecture section now has V-13.5 exception carve-out. FN2 (imp-3) V-13.5 command not executable as written (temp-dir + hard-coded prompt) → replaced with `make -C /abs/path` for Makefile test + direct `codex exec resume --json` for inheritance probe. FN3 (imp-2) test matrix too vague → explicit 5-case matrix added to Scope G. FN4 (imp-2) no rollback section → added Rollback section (escape hatch, stale recovery, loop-reset, default-flip isolation). |
| 1.5 | Claude (consistency self-check) | 2026-05-29 | doc-drift × 5 | folded | D1 V-13.5 header "manual" contradicts Part 1 "automated" → header updated to "mixed-mode gate"; NOT-in-scope updated to "Part 2 manual". D2 stale-session fallback scope mismatch (THREAD_FILE only vs THREAD_FILE + THREAD_JSONL_FILE) → Scope G item (4) updated to match Rollback. D3 `print-thread-file` target referenced but never declared → replaced with inline KEY derivation in Part 2 probe command. D4 Risks row 3 "each iter overwrites" contradicted "first-continue call only" → fixed to "First-continue call writes it once". D5 Scope G item (2) omitted THREAD_JSONL_FILE → added to item (2). |
| 1.5b | Claude (consistency self-check, round 2) | 2026-05-29 | doc-drift × 4 | folded | D1 KEY derivation in Architecture missing `realpath()` + colon + `[:12]` → updated to precise formula. D2 "NOT in scope" contradicted "required before merge" for V-13.5 Part 2 → reworded to "no code deliverable" + "manual operator step". D3 V-13.5 Part 2 sub-header "Live sandbox inheritance probe" understated scope (only 2 of 3 gates named) → renamed to "Live inheritance probe (session UUID continuity, sandbox, cwd)". D4 Rollout "V-13.5 manual gate" ambiguous about which Part → added "Part 2". |
| 1.5c | Claude (consistency self-check, round 3) | 2026-05-29 | 0 drifts | stable | No internal contradictions found. Loop-ack run; HASH_FILE stamped. Proceeding to iter 2. |

## Implementation log

| short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |
|-----------|---------------------|---------------------------------|------------------------|
