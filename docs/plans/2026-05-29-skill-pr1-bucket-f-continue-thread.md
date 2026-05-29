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
| G | Tests | `tests/test_extract_codex_session_id.py` (unit tests for script A: JSONL-with-session-meta → prints ID to stdout; JSONL-without-session-meta → non-zero exit and prints nothing). `tests/test_selftest_overlap.py` extended: (a) add `scripts/extract-codex-session-id.py` ↔ `shared/scripts-extract-codex-session-id.py.tmpl` to `_SCRIPT_TEMPLATE_PAIRS` for byte-identity enforcement, (b) assert `scripts/extract-codex-session-id.py` is executable (`chmod +x` / `os.access(X_OK)`). `tests/test_makefile_review_targets.py` extended to cover new vars/targets. Test matrix in `tests/test_makefile_review_targets.py` using a codex argv-logging shim: (1) fresh — no `--json`, no `THREAD_FILE` written; (2) continue, no existing `THREAD_FILE` — runs `codex exec --json` (writes `THREAD_JSONL_FILE` via plain redirect), then extracts `THREAD_FILE` atomically via `.tmp` + UUID validation + `mv`; extractor failure path — asserts no `THREAD_FILE`, `THREAD_FILE.tmp`, or `THREAD_JSONL_FILE` remains (all three cleaned up); also asserts `THREAD_JSONL_FILE` is deleted on the success path (FN4 fold) and retained when `KEEP_THREAD_JSONL=1` (only on success — failure path always removes it); (3) continue, `THREAD_FILE` exists — runs `codex exec resume $SESSION_ID`; (4a) `"no rollout found for thread id"` exact-match fallback — clears stale `THREAD_FILE` + `THREAD_JSONL_FILE`, starts fresh; (4b) unrelated resume failure — exits non-zero, does NOT clear thread state; (5) `loop-reset` — removes `THREAD_FILE` + `THREAD_JSONL_FILE`. |
| H | `scripts/run-with-clean-env.py` + `shared/scripts-run-with-clean-env.py.tmpl` | Add `THREAD_MODE`, `THREAD_FILE`, `THREAD_JSONL_FILE` to `EXACT_DROP` (FN5 fold). Prevents leaked Make variables from reaching the Codex subprocess. Test: shim asserts Codex does not receive these in its environment. |

**NOT in scope (no code deliverable)**: default flip from `THREAD_MODE=fresh` → `continue`
(deferred to post-A/B-replay gates — see Verification). V-13.5 Part 2 live
inheritance probe (UUID continuity + sandbox-policy-type inheritance + file absence + cwd;
manual operator step — failure blocks PR merge; run before merging;
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
1. Gate extraction behind successful Codex exit (FN2 iter-4 fold):
   ```
   codex exec --json --output-last-message "$(PLAN_REVIEW_OUT_CODEX)" ... \
     > "$(THREAD_JSONL_FILE)" \
   && scripts/extract-codex-session-id.py "$(THREAD_JSONL_FILE)" > "$(THREAD_FILE).tmp" \
   && grep -qE '^[0-9a-f-]{36}$' "$(THREAD_FILE).tmp" \
   && mv "$(THREAD_FILE).tmp" "$(THREAD_FILE)" \
   || { rm -f "$(THREAD_FILE).tmp" "$(THREAD_FILE)" "$(THREAD_JSONL_FILE)"; \
        echo "ERROR: codex exec or session ID extraction failed"; exit 1; }
   ```
   On failure: no `THREAD_FILE`, `THREAD_FILE.tmp`, or `THREAD_JSONL_FILE` remains.
2. Delete THREAD_JSONL_FILE after successful extraction (FN4 iter-4 fold — review
   content in JSONL is a data exposure risk; session ID is now safely in THREAD_FILE):
   ```
   rm -f "$(THREAD_JSONL_FILE)"
   ```
   If debugging is needed: set `KEEP_THREAD_JSONL=1` to skip this deletion
   **on successful extraction only**. The failure-path cleanup (step 1 above)
   always removes `THREAD_JSONL_FILE` regardless of `KEEP_THREAD_JSONL`.
3. Display review: `cat $(PLAN_REVIEW_OUT_CODEX)` (unchanged)

On SUBSEQUENT calls when `THREAD_FILE` exists:
1. Read `SESSION_ID = $(cat $(THREAD_FILE))`
2. Run `codex exec resume $SESSION_ID --output-last-message ...`
   (`--json` NOT needed for normal operation — session ID already known)
3. On resume failure: capture stderr; log a warning; if it contains the pinned
   string `"no rollout found for thread id"` (verified 2026-05-29 by running
   `codex exec resume 00000000-0000-0000-0000-000000000000 --ephemeral NOOP`,
   which emits `Error: thread/resume: thread/resume failed: no rollout found for
   thread id 00000000-0000-0000-0000-000000000000 (code -32600)`), clear
   `THREAD_FILE` + `THREAD_JSONL_FILE` and fall back to a fresh `codex exec`
   call. Any OTHER non-zero exit propagates unchanged — do NOT swallow
   auth/network/quota errors.
4. Display review as normal

**V-13.5 exception**: when running the V-13.5 inheritance verification, the
resume call explicitly uses `--json` to capture the resumed JSONL for
assertion (see Verification). This is a one-time verification step, not
normal operation.

When `THREAD_MODE=fresh` (the default — unchanged): current behavior, no
`--json`, no session-ID tracking.

### `-C`/`--sandbox` on resume
V-13.5 verifies that `codex exec resume` inherits `-C` and `--sandbox`
from the original session. Per PR #10 iter-4 F2 (verified empirically),
passing these flags defensively on `resume` is **CLI-rejected**
(`unexpected argument`). Do NOT re-pass them. V-13.5 is the proof that
inheritance holds.

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

### V-13.5 — session UUID continuity, sandbox-policy-type inheritance, file absence, and cwd (mixed gate: Part 1 automated, Part 2 manual, failure blocks PR merge)

**Part 1 — Makefile resume branch (shim-based, part of automated test matrix)**:
The test matrix in Scope G item (3) uses a fake codex shim to assert that when
`THREAD_FILE` exists, the Makefile recipe calls `codex exec resume $SESSION_ID`
(not `codex exec`). This verifies the Makefile branching logic without a live API call.

**Part 2 — Live inheritance probe (session UUID continuity, sandbox-policy-type inheritance, file absence, cwd)**:
Run FROM the repo root using the actual codex CLI:
1. Preconditions and cleanup (FN3 fold):
   ```
   PLAN=docs/plans/2026-05-29-skill-pr1-bucket-f-continue-thread.md
   # Compute KEY for THREAD_FILE path
   KEY=$(python3 -c "import hashlib,os; \
     k=os.path.realpath('.')+':'+os.path.realpath('$PLAN'); \
     print(hashlib.sha256(k.encode()).hexdigest()[:12])")
   # Clear any stale thread state from previous runs
   make -C /abs/path/to/repo loop-reset PLAN_FILE="$PLAN"
   # Assert both files absent and probe file absent
   test ! -e /tmp/plan-review-$KEY.thread || { echo "ERROR: THREAD_FILE not cleaned up"; exit 1; }
   test ! -e /tmp/plan-review-$KEY.session.jsonl || { echo "ERROR: THREAD_JSONL_FILE not cleaned up"; exit 1; }
   test ! -e /tmp/test-v13-5-write.txt || { echo "ERROR: clean up /tmp/test-v13-5-write.txt first"; exit 1; }
   ```
2. Seed a fresh session:
   ```
   make -C /abs/path/to/repo review-plan-by-codex \
     PLAN_FILE="$PLAN" ITERATION=1 THREAD_MODE=continue
   ```
   → `THREAD_FILE` contains a UUID (`SESSION_ID`); `THREAD_JSONL_FILE` is written
   then deleted by default (set `KEEP_THREAD_JSONL=1` to retain it for debugging).
3. Probe inheritance from a DIFFERENT directory (FN1 iter-4 fold — contrast condition):
   Running resume from a different cwd is the only way to distinguish "resume
   inherited the original cwd" from "resume used the caller's current cwd".
   ```
   SESSION_ID=$(cat /tmp/plan-review-$KEY.thread)
   echo "Probing session: $SESSION_ID"
   # Run resume from /tmp — NOT the repo root
   cd /tmp && codex exec resume "$SESSION_ID" --json \
     "Attempt to create a file at /tmp/test-v13-5-write.txt. Report what happened." \
     > /tmp/test-v13-5-resumed.jsonl
   # Return to repo root for subsequent assertions
   cd -
   ```
4. Assert ALL FOUR from the resumed JSONL:
   a. `session_meta.payload.id` in `/tmp/test-v13-5-resumed.jsonl` equals `SESSION_ID`
      (session not renewed — UUID continuity proves resume, not restart)
   b. First `turn_context.payload.sandbox_policy.type` in resumed JSONL equals `"read-only"`
      (deterministic proof that sandbox setting was inherited — not inferred from model behavior)
      AND `/tmp/test-v13-5-write.txt` does NOT exist (file absence corroborates)
   c. (redundant corroboration) No file at `/tmp/test-v13-5-write.txt` after the resumed session
   d. First `turn_context.payload.cwd` in resumed JSONL equals `realpath(CURDIR)`
      from the ORIGINAL session (cwd inherited)

If any assertion fails: this PR must NOT merge. The `THREAD_MODE=continue` branch is unsafe
(not merely unsuitable as default) until V-13.5 passes. File a bug and keep `THREAD_MODE=fresh`
(the safe default) until fixed.

### A/B replay gates (required before default flip; POST-PR-1)
Per meta-plan PR-1 Verification: pick a real folded plan + its committed
iter outputs (e.g. PR #10). Archive the exact prompt for each iter. Replay
twice against the archived plan-state-at-iter-N: once `THREAD_MODE=fresh`,
once `THREAD_MODE=continue`.

**JSONL capture note (FN4 fold)**: the normal resumed calls in `review-plan-by-codex`
do NOT use `--json`. For the A/B replay, the measurement bypasses the Make target
and uses direct `codex exec/resume --json` CLI commands to capture JSONL from
all iterations including resumed ones. The Make target is for day-to-day use;
the A/B harness is a separate measurement script.

Conditions:
1. `continue` total tokens ≥10% lower than `fresh`.
2. Per-iter wall-clock in `continue` not regressing >20%.
3. Cache-hit value `cached_input_tokens > 0` in `continue` JSONL (verified via direct `--json` capture).
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
- `tests/test_selftest_overlap.py` — extend parity check for new Makefile vars + add `scripts/extract-codex-session-id.py` ↔ template to `_SCRIPT_TEMPLATE_PAIRS` + assert executable bit
- `tests/test_makefile_review_targets.py` — extend for new targets/vars
- `tests/fixtures/codex-json-session.jsonl` — already committed (V-13)
- `scripts/run-with-clean-env.py` + `shared/scripts-run-with-clean-env.py.tmpl` — add THREAD vars to EXACT_DROP

## Risks

| Risk | Mitigation |
|------|-----------|
| `--json` breaks current review display | `--output-last-message` file is unchanged; `cat` at end still works. V-13.5 verifies end-to-end display. |
| `codex exec resume` drops `-C`/`--sandbox` | V-13.5 Part 2 all-4-gate failure blocks PR merge (continue branch is unsafe). |
| THREAD_JSONL_FILE data exposure | Written during first-continue call then deleted after successful extraction (default). Stale JSONL doesn't persist across runs. `KEEP_THREAD_JSONL=1` retains it for debugging (success-path only; failure path always removes it). |
| V-13.5 Part 2 needs `--json` on resume but normal ops don't | V-13.5 is a one-time manual gate; it explicitly passes `--json` to the `codex exec resume` probe command. Normal resumed calls in `review-plan-by-codex` do NOT use `--json`. |
| `info: null` guard missing in future A/B code | Parked reminder in BACKLOG. Not in this PR's scope. |
| Makefile recipe leaves corrupt state on extraction failure | On failure: removes `THREAD_FILE.tmp` + `THREAD_FILE` + `THREAD_JSONL_FILE` (all three). Test case 2 in `test_makefile_review_targets.py` asserts none of the three remain on extractor failure. |
| Session TTL: fallback swallows unrelated failures | Recipe captures stderr and falls back ONLY when stderr contains `"no rollout found for thread id"` (pinned by live probe 2026-05-29). All other non-zero exits propagate unchanged. Two tests: positive fallback + unrelated-failure must NOT clear thread state. |
| A/B replay has no JSONL capture path for resumed iters | A/B replay bypasses the Makefile and uses direct `codex exec/resume --json` CLI commands (not the Make target). The Make target is for normal operation; the A/B measurement tool is a separate script. |

## Rollback

- **Escape hatch**: `THREAD_MODE=fresh` always bypasses thread continuation. No rebuild needed.
- **Stale session recovery**: if `codex exec resume` stderr contains `"no rollout found for
  thread id"` (pinned string), the Makefile recipe clears `THREAD_FILE` + `THREAD_JSONL_FILE`,
  logs a warning, and falls back to a fresh `codex exec` call. The fallback does NOT silently
  swallow errors from other failure modes.
- **Full cleanup**: `make loop-reset PLAN_FILE=...` removes `THREAD_FILE` + `THREAD_JSONL_FILE`
  in addition to the existing hash/consistency/snapshot cleanup.
- **Default flip**: any flip from `THREAD_MODE=fresh` → `continue` as default is a SEPARATE PR
  after the A/B replay gates pass. This PR never changes the default.

## Implementation rollout

| Commit | Scope | Files |
|--------|-------|-------|
| 1 | `scripts/extract-codex-session-id.py` + unit tests (no-session-meta → non-zero exit; reads JSONL, prints session ID) | `scripts/extract-codex-session-id.py`, `tests/test_extract_codex_session_id.py` |
| 2 | Extend Makefile + template (THREAD vars, atomic recipe branch, `&&`-gated extraction, THREAD_JSONL_FILE deletion + `KEEP_THREAD_JSONL=1` opt-out, stale-session exact-match fallback, loop-reset cleanup) | `Makefile`, `shared/Makefile.review.tmpl` |
| 3 | Register in SHARED_TEMPLATE_MAP + EXECUTABLE_TARGETS; add THREAD vars to clean-env EXACT_DROP | `bootstrap_lib/render.py`, `bootstrap_lib/manifest.py`, `shared/scripts-extract-codex-session-id.py.tmpl`, `scripts/run-with-clean-env.py`, `shared/scripts-run-with-clean-env.py.tmpl` |
| 4 | Extend selftest-overlap + makefile-review-targets tests (6-case matrix: 1/2/3/4a/4b/5 — cases 4a+4b split from orig. 4 — + clean-env leak test) | `tests/test_selftest_overlap.py`, `tests/test_makefile_review_targets.py` |

Tier-1 review (same-AI fresh subagent) after each commit before push.
`make check` passes before commit 4 merges. V-13.5 Part 2 manual gate runs after
commit 3 (after `run-with-clean-env.py` EXACT_DROP change — FN3 iter-4 fold) and
before the PR is opened for Tier-2 review. The gate tests the final execution path
(including the clean-env wrapper), not a partial state.

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
| 1.5d (re-stamp) | Claude | 2026-05-29 | — | re-stamp | Plan changed after 1.5c ack (1.5c log entry added). Re-ran consistency to re-stamp CONS_FILE. Loop-ack stamped again. |
| 2 | Codex | 2026-05-29 | 3 / 2 / 1 | do not implement yet | All 6 folded as (a). FN1 (imp-3) iter-1 fold REPLACED sandbox-denial with UUID continuity instead of adding it → V-13.5 now asserts all 4: UUID continuity + sandbox-denial event + file absence + cwd. FN2 (imp-3) THREAD_FILE written via direct shell redirect — corrupt on failure → atomic write (.tmp + validate UUID + mv; on failure remove tmp+final). FN3 (imp-3) stale-session fallback underspecified (resume || fresh swallows unrelated failures) → fallback matches ONLY pinned exact CLI error string (pre-impl fixture step); other non-zero exits propagate. Added test 4b (unrelated failure must not clear state). FN4 (imp-2) A/B replay needs --json on resumed calls but Make target doesn't use it → A/B replay bypasses Make target, uses direct `codex exec/resume --json`; note added to A/B gates. FN5 (imp-2) THREAD_MODE/FILE/JSONL_FILE not in clean-env EXACT_DROP → added to Scope H + Critical files + commit 3. FN6 (imp-1) V-13.5 probe placeholder inconsistency + missing pre-check → PLAN variable defined once, precondition assertion added. |
| 2.5 | Claude (consistency self-check) | 2026-05-29 | doc-drift × 4 (folded) + 1 (rejected) | stable | D1 "iter-4 F2" unanchored → added "(PR #10 iter-4 F2)". D2 commit-4 "5-case matrix + 4b" vs Scope G 6 cases → updated to "6-case matrix (1/2/3/4a/4b/5)". D3 NOT-in-scope still said "sandbox-inheritance probe" after Part 2 sub-header rename → updated to enumerate all 4 gates. D4 Architecture omitted warning on fallback but Rollback mentioned it → "logs a warning" added to Architecture. D5 iter-1.5b log entry 3-element vs current 4-element sub-header → (c) rejected as historical record (iter-2 FN1 added the 4th element after the 1.5b entry was written). Also in this round: pinned exact CLI error string for FN3 by running `codex exec resume NONEXISTENT-UUID` — result `"no rollout found for thread id"` added to Architecture + Risks. |
| 2.5b | Claude (consistency self-check, round 2) | 2026-05-29 | doc-drift × 4 | folded | D1 V-13.5 main header still said "sandbox and cwd inheritance" (2 elements) after Part 2 enumerated 4 → header updated to "session UUID continuity, sandbox-denial, file absence, and cwd inheritance". D2 commit-1 attributed atomic write + UUID validation (commit-2 work) → stripped from commit-1 description. D3 Scope G misplaced "no THREAD_FILE remains" assertion in script unit tests instead of Makefile-recipe tests → moved to test_makefile_review_targets.py description. D4 Risks row 6 said "Extraction script" but Makefile recipe owns THREAD_FILE writes → updated to "Makefile recipe". |
| 2.5c | Claude (consistency self-check, round 3) | 2026-05-29 | doc-drift × 1 | folded | D1 Risk row 6 said "Test case 2" asserts extractor failure, but Scope G case (2) only showed success path → case (2) description extended to also enumerate the extractor-failure sub-case explicitly. Plan internally consistent on all other cross-section checks (V-13.5 four-gate, KEY derivation, stale-session string, commit/scope mapping, --json carve-outs all matched). |
| 2.5d | Claude (consistency self-check, round 4) | 2026-05-29 | doc-drift × 1 | folded | D1 Scope G item (2) said "atomically" for THREAD_JSONL_FILE but Architecture shows plain redirect → case (2) reworded to "writes THREAD_JSONL_FILE via plain redirect, then extracts THREAD_FILE atomically". |
| 2.5e | Claude (consistency self-check, round 5) | 2026-05-29 | 0 drifts | stable | 2.5d fold left the plan consistent. Loop-ack stamped. Proceeding to iter 3. |
| 3 | Codex | 2026-05-29 | 3 / 2 / 0 | do not implement yet | FN1 (imp-3) (a) V-13.5 failure said "blocks default flip" but correct: failure must block PR merge entirely (continue branch unsafe if sandbox not inherited). FN2 (imp-3) (a) assertion b "no function_call emitted" proves model behavior not sandbox → replaced with `turn_context.payload.sandbox_policy.type == "read-only"` (deterministic). FN3 (imp-3) (a) probe step 1 doesn't clear stale thread state first → added `make loop-reset` + assert-absent pre-steps. FN4 (imp-2) (c) THREAD_JSONL_FILE atomic write unnecessary — plain redirect sufficient because THREAD_FILE is the state invariant; if extraction fails, THREAD_FILE is cleaned up; next run overwrites JSONL. FN5 (imp-2) (a) new script not in `test_selftest_overlap.py` `_SCRIPT_TEMPLATE_PAIRS` → added to Scope G. |
| 3.5 | Claude (consistency self-check) | 2026-05-29 | doc-drift × 3 + 1 borderline | folded | D1 Risks row 2 said "prevents flip" but iter-3 FN1 escalated to "blocks merge" → updated. D2 Rollback used generic "session not found" instead of pinned string → updated to `"no rollout found for thread id"`. D3 Critical files `test_selftest_overlap.py` description omitted `_SCRIPT_TEMPLATE_PAIRS` + executable-bit check → added. D4 (borderline, a) header/NOT-in-scope said "sandbox-denial" but assertion checks `sandbox_policy.type` → both updated to "sandbox-policy-type inheritance". |
| 3.5b | Claude (consistency self-check, round 2) | 2026-05-29 | doc-drift × 1 | folded | D1 Part 2 sub-header still said "sandbox policy" after 3.5 D4 rename → added "sandbox-policy-type". |
| 3.5c | Claude (consistency self-check, round 3) | 2026-05-29 | doc-drift × 2 | folded | D1 Scope G case (4a) used colloquial "session not found" → updated to pinned `"no rollout found for thread id"`. D2 NOT-in-scope said "sandbox-policy-type check" but header says "inheritance" → updated. |
| 3.5d | Claude (consistency self-check, round 4) | 2026-05-29 | doc-drift × 3 | folded | D1 Missing 3.5b log entry (was placed before 3.5) → reordered + added. D2 Part 2 sub-header lacked "inheritance" qualifier → added. D3 Asymmetric cleanup note: THREAD_JSONL_FILE not removed on extraction failure → added explanatory note (intentional; harmless; overwritten on next call). |
| 4 | Codex | 2026-05-29 | 2 / 2 / 1 | do not implement yet | FN1 (imp-3) (a) V-13.5 probe runs from same cwd as seed → cwd assertion trivially passes; contrast requires running resume from /tmp. FN2 (imp-3) (a) first-continue path doesn't gate extraction on codex exit → `&&` chain + clean all three artifacts on failure. FN3 (imp-2) (a) V-13.5 live gate scheduled after commit 2 but commit 3 changes execution path → gate moved to after commit 3. FN4 (imp-2) (a) THREAD_JSONL_FILE retained in /tmp exposes review content → delete after successful extraction (KEEP_THREAD_JSONL=1 opt-out). FN5 (imp-1) (a) iter log had 3.5b before 3.5 → reordered. |
| 4.5 | Claude (consistency self-check) | 2026-05-29 | doc-drift × 6 + 1 process-obs | folded | All 6 from iter-4 FN4 fold not propagated. D1/D3 Scope G case (2) test missing THREAD_JSONL_FILE absence + JSONL-deletion assertions → added. D2 Risks row 6 omitted THREAD_JSONL_FILE from failure cleanup → updated to "all three". D4 KEEP_THREAD_JSONL semantics ambiguous (applies success-only; failure always removes) → clarified. D5 Risks row 3 stale (JSONL no longer persists by default) → rewritten as "data exposure" row. D6 Rollout commit 2 missing JSONL deletion + KEEP_THREAD_JSONL opt-out → added. D7 (process-obs, c) no 3.5e stable row in iter log — accepted as historical gap. |
| 4.5b | Claude (consistency self-check, round 2) | 2026-05-29 | doc-drift × 2 | folded | D1 Iter log had 4.5 before 4 → reordered. D2 V-13.5 failure action said THREAD_MODE=undefined → standardized to THREAD_MODE=fresh. |

## Implementation log

| short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |
|-----------|---------------------|---------------------------------|------------------------|
