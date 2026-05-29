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
| G | Tests | `tests/test_extract_codex_session_id.py` (unit tests for script A: JSONL-with-session-meta → prints ID to stdout; JSONL-without-session-meta → non-zero exit and prints nothing). `tests/test_selftest_overlap.py` extended: (a) add `scripts/extract-codex-session-id.py` ↔ `shared/scripts-extract-codex-session-id.py.tmpl` to `_SCRIPT_TEMPLATE_PAIRS` for byte-identity enforcement, (b) assert `scripts/extract-codex-session-id.py` is executable (`chmod +x` / `os.access(X_OK)`). `tests/test_makefile_review_targets.py` extended to cover new vars/targets. Test matrix in `tests/test_makefile_review_targets.py` using a codex argv-logging shim: (1) fresh — no `--json`, no `THREAD_FILE` written; (2) continue, no existing `THREAD_FILE` — runs `codex exec --json` (writes `THREAD_JSONL_FILE` via plain redirect), then extracts `THREAD_FILE` atomically via `.tmp` + UUID validation + `mv`; extractor failure path — asserts no `THREAD_FILE`, `THREAD_FILE.tmp`, or `THREAD_JSONL_FILE` remains (all three cleaned up); also asserts `THREAD_JSONL_FILE` is deleted on the success path (FN4 fold) and retained when `KEEP_THREAD_JSONL=1` (only on success — failure path always removes it); (3) continue, `THREAD_FILE` exists — runs `codex exec resume $SESSION_ID`; (4a) `"no rollout found for thread id"` exact-match fallback — clears stale `THREAD_FILE` + `THREAD_JSONL_FILE`, runs a one-shot fresh `codex exec` (no `--json`), and asserts BOTH `THREAD_FILE` and `THREAD_JSONL_FILE` remain ABSENT afterward (re-seed happens on the next continue call, not this one — iter-6 FN3); (4b) unrelated resume failure — exits non-zero, does NOT clear thread state; (5) `loop-reset` — removes `THREAD_FILE` + `THREAD_JSONL_FILE`. |
| H | `scripts/run-with-clean-env.py` + `shared/scripts-run-with-clean-env.py.tmpl` | Add `THREAD_MODE`, `THREAD_FILE`, `THREAD_JSONL_FILE`, **`KEEP_THREAD_JSONL`** to `EXACT_DROP` (FN5 fold + FN3 iter-5 fold). Prevents leaked Make variables from reaching the Codex subprocess. Test: shim asserts Codex does not receive these in its environment. |
| I | `BACKLOG.md` (sweep — not just one entry) | Update the V-13.5 description to the current gate (`turn_context.payload.sandbox_policy.type == "read-only"` + `--skip-git-repo-check` on the `/tmp` probe), **then sweep** for stale text the single-entry edit would miss: `grep -nE 'V-13\.5\|sandbox-denial\|sandbox_policy' BACKLOG.md` and fix every bullet that still enumerates the gate as "sandbox-denial" (notably the "UPDATED to 4-assertion gate" trigger bullet, which currently contradicts the corrected bullet above it). After the sweep, no `BACKLOG.md` line should describe the 2nd gate as "sandbox-denial". Add to rollout commit 4 (docs-only change). |

**NOT in scope (no code deliverable)**: default flip from `THREAD_MODE=fresh` → `continue`
(deferred to post-A/B-replay gates — see Verification). V-13.5 Part 2 live
inheritance probe (UUID continuity + sandbox-policy-type inheritance + file absence + cwd;
manual operator step — failure blocks PR merge; run before merging;
Part 1 is automated via Scope G test-matrix case (3)). Tier-2 bot quality comparison
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
   content in JSONL is a data exposure risk; session ID is now safely in THREAD_FILE),
   **unless `KEEP_THREAD_JSONL=1`** (iter-6 FN2 fold — the deletion is conditional on
   `KEEP_THREAD_JSONL`, not unconditional):
   ```
   [ "$${KEEP_THREAD_JSONL:-}" = "1" ] || rm -f "$(THREAD_JSONL_FILE)"
   ```
   `KEEP_THREAD_JSONL=1` retains the JSONL for debugging **on successful extraction
   only**. The failure-path cleanup (step 1 above) always removes `THREAD_JSONL_FILE`
   regardless of `KEEP_THREAD_JSONL`.
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
   `THREAD_FILE` + `THREAD_JSONL_FILE` and fall back to a **one-shot fresh
   `codex exec`** for THIS call (iter-6 FN3 fold): no `--json`, no re-seed —
   `THREAD_FILE` and `THREAD_JSONL_FILE` stay absent after the fallback. The fallback does NOT capture a
   replacement session ID; instead the **next** `THREAD_MODE=continue` call sees no
   `THREAD_FILE`, re-enters the first-continue path, and re-seeds a new session
   (self-healing within one extra non-continuing call — chosen over re-seeding inline
   to avoid duplicating the atomic-write + extraction + cleanup logic in two places).
   Any OTHER non-zero exit propagates unchanged — do NOT swallow
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
Run the single self-contained block below **from the repo root** using the actual
codex CLI (iter-6 FN1 fold — the previous version interleaved `/abs/path/to/repo`,
`<KEY>`, and `<realpath-of-repo>` placeholders that defeated "copy-pasteable"; this
version computes every path itself and distinguishes "probe DID NOT RUN" from
"inheritance FAILED"). What each gate proves:
- **a. UUID continuity** — `session_meta.payload.id` in the resumed JSONL equals the
  seed `SESSION_ID` (resume, not restart).
- **b. sandbox-policy-type inheritance** — first `turn_context.payload.sandbox_policy.type`
  equals `"read-only"` (deterministic proof the sandbox setting was inherited, not
  inferred from model behaviour).
- **c. file absence** — no file at `/tmp/test-v13-5-write.txt` (corroborates b).
- **d. cwd inheritance** — first `turn_context.payload.cwd` equals the ORIGINAL
  session's `realpath(CURDIR)`. The probe runs resume from `/tmp` (the contrast
  condition — FN1 iter-4 fold), so a matching cwd proves inheritance, not caller-cwd.

```bash
set -euo pipefail
REPO="$(git rev-parse --show-toplevel)"            # repo root — computed, no placeholder
PLAN="docs/plans/2026-05-29-skill-pr1-bucket-f-continue-thread.md"
KEY=$(python3 -c "import hashlib,os; \
  k=os.path.realpath('$REPO')+':'+os.path.realpath('$REPO/$PLAN'); \
  print(hashlib.sha256(k.encode()).hexdigest()[:12])")
THREAD_FILE="/tmp/plan-review-$KEY.thread"
JSONL_FILE="/tmp/plan-review-$KEY.session.jsonl"
PROBE_FILE="/tmp/test-v13-5-write.txt"
RESUMED_JSONL="/tmp/test-v13-5-resumed.jsonl"

# (1) Clear stale state; assert clean preconditions
make -C "$REPO" loop-reset PLAN_FILE="$PLAN"
test ! -e "$THREAD_FILE" || { echo "ERROR: THREAD_FILE not cleaned up"; exit 1; }
test ! -e "$JSONL_FILE"  || { echo "ERROR: THREAD_JSONL_FILE not cleaned up"; exit 1; }
test ! -e "$PROBE_FILE"  || { echo "ERROR: clean up $PROBE_FILE first"; exit 1; }
rm -f "$RESUMED_JSONL"

# (2) Seed a fresh continue session (writes THREAD_FILE; JSONL deleted by default)
make -C "$REPO" review-plan-by-codex PLAN_FILE="$PLAN" ITERATION=1 THREAD_MODE=continue
test -s "$THREAD_FILE" || { echo "ERROR: seed wrote no THREAD_FILE — probe DID NOT RUN"; exit 1; }
SESSION_ID="$(cat "$THREAD_FILE")"
echo "Probing session: $SESSION_ID"

# (3) Probe inheritance from a DIFFERENT cwd (/tmp) — the contrast condition.
#     --skip-git-repo-check required (codex exec resume fails in non-git dirs).
( cd /tmp && codex exec resume "$SESSION_ID" --skip-git-repo-check --json \
    "Attempt to create a file at $PROBE_FILE. Report what happened." \
    > "$RESUMED_JSONL" ) \
  || { echo "ERROR: resume failed — probe DID NOT RUN (distinct from inheritance FAILED)"; exit 1; }
test -s "$RESUMED_JSONL" || { echo "ERROR: no resumed JSONL captured — probe DID NOT RUN"; exit 1; }

# (4) Assert ALL FOUR (Python reads paths from the environment — no placeholders)
REPO_CWD="$(cd "$REPO" && pwd -P)" \
SESSION_ID="$SESSION_ID" RESUMED_JSONL="$RESUMED_JSONL" PROBE_FILE="$PROBE_FILE" \
python3 - <<'PY'
import json, os, sys
events       = [json.loads(l) for l in open(os.environ["RESUMED_JSONL"]) if l.strip()]
session_meta = next(e for e in events if e.get("type") == "session_meta")
turn_ctx     = next(e for e in events if e.get("type") == "turn_context")
results = {
  "uuid_continuity":   session_meta["payload"]["id"] == os.environ["SESSION_ID"],
  "sandbox_read_only": turn_ctx["payload"]["sandbox_policy"]["type"] == "read-only",
  "cwd_inherited":     turn_ctx["payload"]["cwd"] == os.environ["REPO_CWD"],
  "file_absent":       not os.path.exists(os.environ["PROBE_FILE"]),
}
for k, v in results.items():
    print(f"{'PASS' if v else 'FAIL'}: {k}")
if not all(results.values()):
    sys.exit(1)
print("ALL FOUR PASS")
PY
```
If any assertion fails (non-zero exit): this PR must NOT merge. The `THREAD_MODE=continue`
branch is unsafe until V-13.5 passes. File a bug and keep `THREAD_MODE=fresh` (the safe
default) until fixed.

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

## Risks

| Risk | Mitigation |
|------|-----------|
| `--json` breaks current review display | `--output-last-message` file is unchanged; `cat` at end still works. V-13.5 Part 2 checks inheritance, not display — display is verified by the `--output-last-message` path independently. |
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
  logs a warning, and falls back to a **one-shot fresh `codex exec`** for that call
  (THREAD_FILE + THREAD_JSONL_FILE stay absent; the next `THREAD_MODE=continue` call re-seeds — self-healing).
  The fallback does NOT silently swallow errors from other failure modes.
- **Full cleanup**: `make loop-reset PLAN_FILE=...` removes `THREAD_FILE` + `THREAD_JSONL_FILE`
  in addition to the existing hash/consistency/snapshot cleanup.
- **Default flip**: any flip from `THREAD_MODE=fresh` → `continue` as default is a SEPARATE PR
  after the A/B replay gates pass. This PR never changes the default.

## Implementation rollout

| Commit | Scope | Files |
|--------|-------|-------|
| 1 | `scripts/extract-codex-session-id.py` + unit tests (no-session-meta → non-zero exit; reads JSONL, prints session ID) | `scripts/extract-codex-session-id.py`, `tests/test_extract_codex_session_id.py` |
| 2 | Extend Makefile + template (THREAD vars, atomic recipe branch, `&&`-gated extraction, THREAD_JSONL_FILE deletion + `KEEP_THREAD_JSONL=1` opt-out, stale-session exact-match fallback, loop-reset cleanup) | `Makefile`, `shared/Makefile.review.tmpl` |
| 3 | Register in SHARED_TEMPLATE_MAP + EXECUTABLE_TARGETS; add THREAD_MODE/FILE/JSONL_FILE + KEEP_THREAD_JSONL to clean-env EXACT_DROP | `bootstrap_lib/render.py`, `bootstrap_lib/manifest.py`, `shared/scripts-extract-codex-session-id.py.tmpl`, `scripts/run-with-clean-env.py`, `shared/scripts-run-with-clean-env.py.tmpl` |
| 4 | Extend selftest-overlap + makefile-review-targets tests (6-case matrix: 1/2/3/4a/4b/5 + clean-env leak test); update + sweep BACKLOG.md V-13.5 references (Scope I — docs-only) | `tests/test_selftest_overlap.py`, `tests/test_makefile_review_targets.py`, `BACKLOG.md` |

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
| 4.5c | Claude (consistency self-check, round 3) | 2026-05-29 | doc-drift × 2 | folded | D1 Log had 4.5 before 4 again → reordered. D2 V-13.5 failure THREAD_MODE=undefined → THREAD_MODE=fresh. (Recurring log-ordering defect, same class as 3.5d/4.5b; fixed in this round.) |
| 5 | Codex | 2026-05-29 | 2 / 2 / 0 | do not implement yet | FN1 (imp-3) (a) /tmp probe fails without --skip-git-repo-check (verified) → added to probe command. FN2 (imp-3) (a) 4-gate assertion is prose-only → added copy-pasteable Python script. FN3 (imp-2) (a) KEEP_THREAD_JSONL not in EXACT_DROP → added to Scope H (Scope I/BACKLOG handled separately by FN4). FN4 (imp-2) (a) BACKLOG V-13.5 description stale (sandbox-denial) → updated to sandbox_policy.type check + /tmp flag. |
| 5.5 | Claude (consistency self-check) | 2026-05-29 | doc-drift × 4 | folded | D1 Scope I said "commit 4" but commit 4 file list omitted BACKLOG.md → added. D2 Critical files omitted BACKLOG.md → added. D3 Critical files shorthand "THREAD vars" missed KEEP_THREAD_JSONL → enumerated all 4. D4 Risks row 1 attributed display-verification to V-13.5 but V-13.5 only checks inheritance → corrected. |
| 5.5b | Claude (consistency self-check, round 2) | 2026-05-29 | doc-drift × 3 (log-narrative only) | folded + driver-exit | Substantive plan body confirmed consistent by reviewer. D1 (a) 4.5c note referenced non-existent "4.5d" → reworded. D3 (a) iter-5 FN3 note said "Scope H + Scope I" but FN3 only touched Scope H → corrected. D2 (c, accepted) no explicit "0 drifts stable" plateau row for the 3.5/4.5 series — accepted as historical bookkeeping gap (same disposition as iter-4.5 D7). Driver-exit the consistency loop here: remaining items are log-narrative, plan body is clean. Loop-ack stamped; ready for iter 6. |
| 6 | Codex | 2026-05-29 | 1 / 4 / 0 | do not implement yet | All 5 folded (a) after four-questions triage. FN1 (imp-3) V-13.5 "copy-pasteable" gate still held `/abs/path/to/repo` + `<KEY>` + `<realpath-of-repo>` placeholders → rewrote Part 2 as ONE self-contained block (shell computes `REPO`/`KEY`/`SESSION_ID`/`REPO_CWD`, Python reads `os.environ`), now distinguishes "probe DID NOT RUN" from "inheritance FAILED"; kept as a manual gate (NOT a code deliverable, so NOT-in-scope unchanged). FN2 (imp-2) Architecture's unconditional `rm -f THREAD_JSONL_FILE` fence contradicted the `KEEP_THREAD_JSONL=1` prose → made the fence conditional. FN3 (imp-2) stale-session fallback didn't define re-seed → specified one-shot fresh (no re-seed; self-heals on the next continue call); Scope G (4a) asserts THREAD_FILE stays absent. FN4 (imp-2) plan violated README §6/§8/§9 structure (no Evidence table, no Lessons surfaced, Critical files mid-doc) — confirmed 12/12 sibling plans conform → added Evidence table (one row per finding, iters 1-6) + Lessons surfaced; moved Critical files to last. FN5 (imp-2) Scope I single-entry update missed stale "sandbox-denial" at BACKLOG:122 → broadened to a `grep`-driven sweep. imp-3 trajectory 2→3→3→2→2→**1**. |
| 6.5 | Claude (consistency self-check) | 2026-05-29 | doc-drift × 4 | folded | D1 Lessons surfaced called iter-4 FN1 "executability" but it was proof-validity (wrong cwd) → reworded. D2 Architecture step 2 "shown previously" dangled after the unconditional `rm -f` was replaced in the same fold → made self-contained. D3 iter-4.5c recurrence class cited "3.5b/3.5" (neither was log-ordering) → corrected to "3.5d/4.5b". D4 rollout commit-3 "THREAD vars" shorthand vs Scope H's 4-var enumeration → enumerated. |
| 6.5b | Claude (consistency self-check, round 2) | 2026-05-29 | doc-drift × 1 (+1 non-issue) | folded | D1 rollout commit-4 said "update BACKLOG.md V-13.5 description" but FN5 broadened Scope I to update+sweep → commit-4 updated to "update + sweep". Non-issue (reviewer-confirmed no fix): 5.5b D1's "4.5d" note is a correct historical record. All substantive invariants PASSED. |
| 6.5c | Claude (consistency self-check, round 3) | 2026-05-29 | doc-drift × 3 | folded | D1 Lessons surfaced precise count ("3 exec + 1 proof") undercounted (omitted iter-5 FN1 `--skip-git-repo-check`) → removed the tally, deferred to Evidence table. D2 Scope G 4a asserted only THREAD_FILE absent vs Architecture clearing both → assert BOTH THREAD_FILE + THREAD_JSONL_FILE absent. D3 NOT-in-scope "Part 1 automated via the Scope G test matrix" overstated → pinned to "case (3)". |
| 6.5d | Claude (consistency self-check, round 4) | 2026-05-29 | doc-drift × 5 (all soft) | folded | Reviewer verdict: "largely internally consistent, no substantive contradictions." D1 (a) Lessons iter-enumeration re-flagged (iters 2/3 also touched V-13.5) → removed the iter list. D2–D5 (driver-exit): UUID-vs-session-UUID wording; cwd-vs-cwd-inheritance header/detail gradient (surfaces internally consistent); historical pinned-string-command narrative (output string unchanged); commit-4-vs-V-13.5 sequencing (commit-4 is docs/tests-only, execution-path claim holds). Substantive invariants PASSED. NOTE: D1's iter-list removal was a half-measure — the defect-type enumeration still competed with the Evidence table; 6.5e/6.5f below land the full strip. |
| 6.5e | Claude (consistency self-check, round 5) | 2026-05-29 | doc-drift × 3 | folded | Caught that the Lessons "enumeration vs Evidence table" magnet still wasn't dead: "one proof-validity fix" undercounted (Evidence table has 2 — iter-3 FN2 + iter-4 FN1); the executability list omitted iter-3 FN3 (stale-state precondition). (minor) Scope G 4a asserted both-absent but Architecture/Rollback only said THREAD_FILE. |
| 6.5f | Claude (consistency self-check, round 6) | 2026-05-29 | 0 substantive (driver-exit) | folded + driver-exit | Landed the definitive durable fix the checker recommended: stripped ALL iter/type/count enumeration from Lessons surfaced (now "multiple executability and proof-validity fixes — see Evidence table"), so it can no longer drift against the Evidence table on future V-13.5 folds. Aligned Architecture step 3 + Rollback to state both THREAD_FILE + THREAD_JSONL_FILE stay absent post-fallback (matches Scope G 4a). 6-round consistency cycle (6.5/b/c/d/e/f): every round confirmed the substantive invariants (V-13.5 4-gate, KEEP/stale/fallback/EXACT_DROP/counts); all drift was narrative/precision (the recurring item was the Lessons magnet, now neutralized). Driver-exit (5.5b precedent). Loop-ack stamped; ready for iter 7. |

## Evidence table — what was folded and where

| Source | Finding | Importance | Resolution | Touched sections |
|---|---|---|---|---|
| Codex iter-1 FN1 | V-13.5 only checked file absence; can't prove resume inheritance without the resumed JSONL | 3 | Added V-13.5 Part 1 (shim test matrix) + Part 2 (live probe with `--json` on resume); Architecture got the V-13.5 `--json`-exception carve-out. **[progressively refined by iter-2 FN1, iter-3 FN1/FN2, iter-4 FN1, iter-5 FN1/FN2, iter-6 FN1]** | Verification V-13.5; Architecture (`--json` exception) |
| Codex iter-1 FN2 | V-13.5 command not executable as written (temp-dir + hard-coded prompt) | 3 | Replaced with `make -C <abs>` for the Makefile test + direct `codex exec resume --json` probe. **[SUPERSEDED by iter-6 FN1 — the remaining placeholders were finally removed and the block made self-contained]** | Verification V-13.5 Part 2 |
| Codex iter-1 FN3 | Test matrix too vague | 2 | Explicit case matrix added to Scope G (later grew to 6 cases). | Scope G |
| Codex iter-1 FN4 | No rollback section | 2 | Added Rollback (escape hatch, stale recovery, loop-reset, default-flip isolation). | Rollback (new) |
| Codex iter-2 FN1 | iter-1 fold REPLACED sandbox-denial with UUID continuity instead of adding it | 3 | V-13.5 made to assert all 4 gates (UUID + sandbox event + file absence + cwd). **[2nd gate later changed sandbox-denial→`sandbox_policy.type` by iter-3 FN2]** | Verification V-13.5; headers; NOT-in-scope |
| Codex iter-2 FN2 | THREAD_FILE written via direct redirect — corrupt on failure | 3 | Atomic write: `.tmp` + UUID-regex validate + `mv`; on failure remove `.tmp`+final (+JSONL). | Architecture first-continue; Scope G case 2; Risks |
| Codex iter-2 FN3 | Stale-session fallback underspecified (`resume \|\| fresh` swallows unrelated failures) | 3 | Fallback fires ONLY on the pinned exact CLI string; all other non-zero exits propagate. Added test 4b. **[fallback re-seed behaviour later specified by iter-6 FN3]** | Architecture subsequent-call; Scope G 4a/4b; Risks |
| Codex iter-2 FN4 | A/B replay needs `--json` on resumed calls but the Make target doesn't use it | 2 | A/B replay bypasses the Make target; uses direct `codex exec/resume --json`. | A/B replay gates; Risks |
| Codex iter-2 FN5 | THREAD_MODE/FILE/JSONL_FILE not in clean-env EXACT_DROP | 2 | Added to Scope H + Critical files + rollout commit 3. | Scope H; Critical files; rollout commit 3 |
| Codex iter-2 FN6 | V-13.5 probe placeholder inconsistency + missing pre-check | 1 | `PLAN` var defined once; precondition assertion added. **[fully resolved by iter-6 FN1's self-contained block]** | Verification V-13.5 Part 2 |
| Codex iter-3 FN1 | V-13.5 failure said "blocks default flip" but should block PR merge entirely | 3 | Corrected: failure blocks PR merge (continue branch unsafe if sandbox not inherited). | Verification V-13.5; Risks |
| Codex iter-3 FN2 | Assertion "no function_call emitted" proves model behaviour, not the sandbox setting | 3 | Replaced with deterministic `turn_context.payload.sandbox_policy.type == "read-only"`. | Verification V-13.5; headers; NOT-in-scope; Risks |
| Codex iter-3 FN3 | Probe step 1 doesn't clear stale thread state first | 3 | Added `make loop-reset` + assert-absent pre-steps to Part 2. | Verification V-13.5 Part 2 |
| Codex iter-3 FN4 | Claimed THREAD_JSONL_FILE needs an atomic write | 2 | **Rejected (c)** — plain redirect is sufficient; THREAD_FILE is the state invariant. **[Note: iter-4 FN4 later changed JSONL handling for a different reason — data exposure, not corruption]** | (no plan change; rejection documented) |
| Codex iter-3 FN5 | New script not in `test_selftest_overlap.py` `_SCRIPT_TEMPLATE_PAIRS` | 2 | Added the script↔template pair to Scope G. | Scope G; Critical files |
| Codex iter-4 FN1 | V-13.5 probe ran from the same cwd as the seed → cwd assertion trivially passes | 3 | Probe runs `codex exec resume` from `/tmp` (contrast condition) so cwd-match proves inheritance. | Verification V-13.5 Part 2 |
| Codex iter-4 FN2 | First-continue path doesn't gate extraction on the codex exit code | 3 | `&&`-chained extraction; cleans all three artifacts on any failure. | Architecture first-continue; Scope G case 2; Risks |
| Codex iter-4 FN3 | V-13.5 live gate scheduled after commit 2, but commit 3 changes the execution path | 2 | Moved the gate to after commit 3 (tests the final clean-env path). | Implementation rollout |
| Codex iter-4 FN4 | THREAD_JSONL_FILE retained in `/tmp` exposes review content | 2 | Delete JSONL after successful extraction; `KEEP_THREAD_JSONL=1` opt-out. **[supersedes iter-3 FN4's "keep plain redirect, no deletion" — JSONL is now deleted for data-exposure reasons]** | Architecture step 2; Scope G case 2; Risks; rollout commit 2 |
| Codex iter-4 FN5 | Iteration log had 3.5b before 3.5 | 1 | Reordered. | Iteration log |
| Codex iter-5 FN1 | `/tmp` probe fails without `--skip-git-repo-check` (verified) | 3 | Added `--skip-git-repo-check` to the probe command. | Verification V-13.5 Part 2 |
| Codex iter-5 FN2 | 4-gate assertion was prose-only (too easy to skip incorrectly) | 3 | Added a copy-pasteable Python assertion script. **[SUPERSEDED by iter-6 FN1 — the script's `<KEY>`/`<realpath-of-repo>` placeholders were removed; it now reads `os.environ`]** | Verification V-13.5 Part 2 |
| Codex iter-5 FN3 | `KEEP_THREAD_JSONL` not in EXACT_DROP | 2 | Added `KEEP_THREAD_JSONL` to Scope H. | Scope H; Critical files |
| Codex iter-5 FN4 | BACKLOG V-13.5 description stale (said "sandbox-denial") | 2 | Updated the description to `sandbox_policy.type` + `/tmp` flag. **[extended to a full BACKLOG sweep by iter-6 FN5]** | Scope I; Critical files |
| Codex iter-6 FN1 | V-13.5 "copy-pasteable" block still held `/abs/path/to/repo` + `<KEY>` + `<realpath-of-repo>` placeholders | 3 | Rewrote Part 2 as one self-contained block (shell computes `REPO`/`KEY`/`SESSION_ID`/`REPO_CWD`; Python reads `os.environ`); distinguishes "probe DID NOT RUN" from "inheritance FAILED". Kept a manual gate — NOT a code deliverable. | Verification V-13.5 Part 2; Iteration log; Evidence table |
| Codex iter-6 FN2 | Architecture's unconditional `rm -f THREAD_JSONL_FILE` fence contradicted the `KEEP_THREAD_JSONL=1` prose | 2 | Made the fence conditional: `[ "$${KEEP_THREAD_JSONL:-}" = "1" ] \|\| rm -f`. | Architecture step 2 |
| Codex iter-6 FN3 | Stale-session fallback didn't define whether it re-seeds a new THREAD_FILE | 2 | Specified one-shot fresh (no re-seed; THREAD_FILE stays absent; next continue call self-heals). Scope G 4a asserts absence. | Architecture subsequent-call; Scope G 4a; Rollback |
| Codex iter-6 FN4 | Plan lacked Evidence table + Lessons surfaced; Critical files not last (README §6/§8/§9) | 2 | Added this Evidence table + Lessons surfaced; moved Critical files to the end. | Iteration log; Evidence table (new); Lessons surfaced (new); Critical files (moved last) |
| Codex iter-6 FN5 | Scope I's single-entry update would miss stale "sandbox-denial" at BACKLOG:122 | 2 | Broadened Scope I to a `grep`-driven sweep of BACKLOG.md. | Scope I; Critical files |

## Implementation log

| short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |
|-----------|---------------------|---------------------------------|------------------------|

## Lessons surfaced (this PR)

- **Manual copy-paste verification gates accrue defects across iters.**
  V-13.5 Part 2 needed multiple executability and proof-validity fixes across the loop
  (see the Evidence table for the per-iter detail) — each a different way the manual gate
  fell short. For a *safety-critical* gate (this one blocks
  PR merge), a prose / copy-paste block is hard to get right in one pass. **Rule
  candidate**: when a verification step is BOTH safety-critical AND repeatedly flagged
  for executability or proof-validity, prefer promoting it to an actual tested script
  over iterating on a manual block. Deferred here (would expand this PR's scope + change
  the NOT-in-scope line); flagged for the driver as the decision point if iter-7 surfaces
  yet another V-13.5 gate defect. Candidate for `LESSONS.md`.

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
- `scripts/run-with-clean-env.py` + `shared/scripts-run-with-clean-env.py.tmpl` — add THREAD_MODE/FILE/JSONL_FILE/KEEP_THREAD_JSONL to EXACT_DROP
- `BACKLOG.md` — update V-13.5 description **and sweep stale `sandbox-denial` text** (`sandbox_policy.type` check + `--skip-git-repo-check`; see Scope I)
