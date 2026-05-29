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
| G | Tests | `tests/test_extract_codex_session_id.py` (unit tests for script A). `tests/test_selftest_overlap.py` + `tests/test_makefile_review_targets.py` extended to cover new vars/targets. |

**NOT in scope**: default flip from `THREAD_MODE=fresh` → `continue` (deferred
to post-A/B-replay gates — see Verification). V-13.5 sandbox-inheritance
verification (manual gate, run before merging). Tier-2 bot quality
comparison (secondary signal only).

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
   (`--json` NOT needed — session ID already known; no JSONL overhead)
3. Display review as normal

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

`KEY` is already defined in the Makefile (SHA-256 of CURDIR + PLAN_FILE).
These paths are stable across sessions for the same repo + plan file, so
`THREAD_MODE=continue` works correctly across terminal restarts.

## Verification

### V-13 — session ID field (DONE)
Fixture at `tests/fixtures/codex-json-session.jsonl` (commit da776ee).
Field path pinned: `session_meta.payload.id`. 7 tests pass.

### V-13.5 — sandbox and cwd inheritance (manual, required before merge)
Run inside a temp directory that is NOT the project root:
1. Start a fresh session: `make review-plan-by-codex PLAN_FILE=<any> ITERATION=1 THREAD_MODE=continue`
   → `THREAD_JSONL_FILE` is written; `THREAD_FILE` contains a UUID.
2. Resume: `make review-plan-by-codex PLAN_FILE=<any> ITERATION=2 THREAD_MODE=continue`
   with the prompt modified to `"Try to create a file at /tmp/test-v13-5-write.txt"`.
3. Assert ALL three:
   a. `THREAD_FILE` still contains the same UUID (session not renewed)
   b. `/tmp/test-v13-5-write.txt` does NOT exist (sandbox inheritance)
   c. First `turn_context.payload.cwd` in resumed session JSONL equals `realpath(CURDIR)`

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
| `codex exec resume` drops `-C`/`--sandbox` | V-13.5 all-3-gate prevents flip if inheritance fails. |
| THREAD_JSONL_FILE grows large over many iters | Each iter overwrites; file size ≈ one session JSONL. No accumulation. |
| `info: null` guard missing in future A/B code | Parked reminder in BACKLOG. Not in this PR's scope. |
| Extraction script fails silently | Non-zero exit on missing `session_meta` event; Makefile recipe propagates error. |
| Session TTL: old sessions may expire before next iter | If `codex exec resume` fails with a "session not found" error, Makefile should fall back to `fresh` and log a warning. Add this fallback in the recipe. |

## Implementation rollout

| Commit | Scope | Files |
|--------|-------|-------|
| 1 | `scripts/extract-codex-session-id.py` + unit tests | `scripts/extract-codex-session-id.py`, `tests/test_extract_codex_session_id.py` |
| 2 | Extend Makefile + template (THREAD vars, recipe branch, loop-reset cleanup) | `Makefile`, `shared/Makefile.review.tmpl` |
| 3 | Register in SHARED_TEMPLATE_MAP + EXECUTABLE_TARGETS | `bootstrap_lib/render.py`, `bootstrap_lib/manifest.py`, `shared/scripts-extract-codex-session-id.py.tmpl` |
| 4 | Extend selftest-overlap + makefile-review-targets tests | `tests/test_selftest_overlap.py`, `tests/test_makefile_review_targets.py` |

Tier-1 review (same-AI fresh subagent) after each commit before push.
`make check` passes before commit 4 merges. V-13.5 manual gate runs after
commit 2 and before the PR is opened for Tier-2 review.

## Outcome measurement

No business metric — internal change. Measurable proxies post-merge:
- `cached_input_tokens` metric in `THREAD_MODE=continue` sessions > 0 (confirms cache hits)
- Token-cost trajectory in the next multi-iter plan loop (measured per the A/B replay gates)

## Iteration log

| Iter | Reviewer | Date | Counts (3/2/1) | Verdict | Notes |
|------|----------|------|----------------|---------|-------|
| 0.5 (fact-check) | Codex | 2026-05-29 | 0 imp-3 | clean | 7 verified (existing files/targets), 3 failed = expected new deliverables (`scripts/extract-codex-session-id.py`, `shared/scripts-extract-codex-session-id.py.tmpl`, `tests/test_extract_codex_session_id.py`), 4 not-verifiable (external `codex` CLI flags — deferred), 1 unsupported-external (`/tmp/test-v13-5-write.txt`). No blocking facts. |

## Implementation log

| short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |
|-----------|---------------------|---------------------------------|------------------------|
