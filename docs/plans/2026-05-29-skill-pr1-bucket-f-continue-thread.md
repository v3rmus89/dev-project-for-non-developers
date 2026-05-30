# PR-1: Bucket F — Continue-thread mode for Codex

## Why

`make review-plan-by-codex` starts a fresh Codex session on every call.
When a plan loop runs 5+ iterations, each iter pays the full context-window
cost from scratch (no prompt caching across sessions). Thread continuation
(`codex exec resume <SESSION_ID>`) lets subsequent iterations resume the
prior context, potentially lowering token cost via cache hits.

This is a **hypothesis** — the default stays `THREAD_MODE=fresh` until the
A/B replay gates in the Verification section pass (meta-plan PR-1).

## ⚠️ Implementation-findings plan correction (2026-05-30) — AUTHORITATIVE; supersedes the V-13 schema + resume-inheritance assumptions below

The first live `scripts/verify-v13-5.py` run (real codex-cli 0.130.0) **falsified two
foundational assumptions** this plan converged on. The 6 commits already on
`feat/skill-pr1-bucket-f-continue-thread` are built on the wrong schema/assumption and
must be re-implemented per the corrected spec here. Empirical facts (also in memory
`codex-json-resume-behavior`):

- **F1 — `--json` schema.** `codex exec --json` STDOUT emits `thread.started`{`thread_id`},
  `turn.started`, `item.completed`{`item`}, `turn.completed`{`usage.cached_input_tokens`}.
  There is **no `session_meta`/`turn_context` in the stream**. The resumable id is
  `thread.started.thread_id` (8-4-4-4-12 UUIDv7). The `session_meta`/`turn_context` schema
  this plan assumed — and the V-13 fixture `tests/fixtures/codex-json-session.jsonl` — is
  the codex **rollout-file** schema (`~/.codex/sessions/<Y>/<M>/<D>/rollout-<ts>-<thread_id>.jsonl`),
  where `session_meta.payload.id == thread_id` and `turn_context.payload.{sandbox_policy.type,cwd}`
  live. **V-13 confirmed the wrong artifact (the file, not the stream).**
- **F2 — `--json` hangs on stdin** unless invoked with `< /dev/null` ("Reading additional
  input from stdin…"); the positional PROMPT is still honoured with `< /dev/null`.
- **F3 (SAFETY) — `codex exec resume` does NOT inherit `-C`/`--sandbox`.** PR #10 iter-4 F2's
  "resume inherits them, don't re-pass" is **FALSE** for 0.130. Resume uses the caller's cwd and
  defaults to `sandbox_mode=workspace-write` — a resumed *review can write to the repo*, breaking
  the read-only contract the `fresh` path guarantees. Resume rejects `--sandbox`/`-C`, but
  `-c sandbox_mode=read-only` (config key `sandbox_mode`) **does** force read-only (verified: write blocked).
- **F4 — cache metric** is `turn.completed.usage.cached_input_tokens` (stream), not `event_msg…info…`.
  Cache hits confirmed real (3456 → 40064 on resume), so the token-saving premise holds.

### Corrected re-implementation spec (supersedes Scope A, Architecture "Session ID extraction" + "`-C`/`--sandbox` on resume", and Verification V-13.5)

1. **Extractor** (`scripts/extract-codex-session-id.py` + template): read `thread_id` from the
   first `thread.started` event (not `session_meta.payload.id`); keep the strict 8-4-4-4-12 UUID
   validation; replace the unit-test fixture with a real `--json` STREAM sample.
2. **Seed recipe** (continue, no THREAD_FILE): `codex exec --json … "PROMPT" < /dev/null` (add the
   stdin redirect). Atomic `.tmp`+`mv`, UUID-validate, JSONL delete / `KEEP_THREAD_JSONL`, failure
   cleanup all unchanged.
3. **Resume recipe** (THREAD_FILE exists): `codex exec resume $SESSION_ID -c sandbox_mode=read-only
   --output-last-message … "PROMPT" < /dev/null`. The `-c sandbox_mode=read-only` is **SAFETY-CRITICAL**
   (resume is workspace-write otherwise). Do NOT pass `--sandbox`/`-C`/`--color` (rejected). Add
   `< /dev/null` to the fresh + fallback `codex exec` calls too (defensive). Stale-session fallback unchanged.
4. **V-13.5 gate** (`scripts/verify-v13-5.py`): seed → extract `thread_id` from the stream →
   normal-path resume smoke. The critical gate is now **read-only ENFORCED on resume**: run the recipe's
   resume and assert a write is BLOCKED (probe file absent) AND the resumed rollout file's
   `turn_context.payload.sandbox_policy.type == "read-only"`. thread-id continuity = the resume stream
   re-emits `thread.started` with the same id. **DROP the "/tmp cwd-inheritance" gate** (no cwd inheritance;
   the recipe runs resume from the repo, so cwd=repo by construction). Keep preflight + 3 error classes;
   the `looks_like_env_failure` widening (OAuth/MCP) already landed (commit cc37d1c).
5. **A/B section**: cache metric at `turn.completed.usage.cached_input_tokens`; drop the `info: null` guard note.
6. **Risks**: add "resumed review runs workspace-write unless forced read-only" → mitigated by
   `-c sandbox_mode=read-only` + the V-13.5 read-only-enforced gate (merge blocker).

## Scope

| Row | What changes | How |
|-----|-------------|-----|
| A | `scripts/extract-codex-session-id.py` (new) | ⚠️ **Superseded by correction F1**: reads `thread.started.thread_id` (the resumable id in the `codex exec --json` STDOUT **stream** — 8-4-4-4-12 UUIDv7), NOT `session_meta.payload.id` (that is the rollout-FILE schema). Fails with non-zero exit if no `thread.started` event with a string `thread_id` is found. |
| B | `Makefile` (dogfood) | Add `THREAD_FILE` + `THREAD_JSONL_FILE` vars (KEY-derived). Extend `review-plan-by-codex` recipe with `THREAD_MODE` branch. Add `loop-reset` cleanup for `THREAD_FILE` + `THREAD_JSONL_FILE`. |
| C | `shared/Makefile.review.tmpl` | Mirror scope B changes (byte-identity contract). |
| D | `shared/scripts-extract-codex-session-id.py.tmpl` (new) | Mirror scope A (same content). |
| E | `bootstrap_lib/render.py` `SHARED_TEMPLATE_MAP` | Register `D`. |
| F | `bootstrap_lib/manifest.py` `EXECUTABLE_TARGETS` | Register the script as executable on bootstrap. |
| G | Tests | `tests/test_extract_codex_session_id.py` (unit tests for script A: JSONL-with-session-meta → prints ID to stdout; JSONL-without-session-meta → non-zero exit and prints nothing). `tests/test_selftest_overlap.py` extended: (a) add `scripts/extract-codex-session-id.py` ↔ `shared/scripts-extract-codex-session-id.py.tmpl` to `_SCRIPT_TEMPLATE_PAIRS` for byte-identity enforcement, (b) assert `scripts/extract-codex-session-id.py` is executable (`chmod +x` / `os.access(X_OK)`). `tests/test_makefile_review_targets.py` extended to cover new vars/targets. Test matrix in `tests/test_makefile_review_targets.py` using a codex argv-logging shim: (1) fresh — no `--json`, no `THREAD_FILE` written; (2) continue, no existing `THREAD_FILE` — runs `codex exec --json` (writes `THREAD_JSONL_FILE` via plain redirect), then extracts `THREAD_FILE` atomically via `.tmp` + strict-UUID validation (`8-4-4-4-12` hyphen positions; iter-7 FN3 — negative tests assert all-hyphen, no-hyphen, and wrong-length IDs are REJECTED and trigger the failure cleanup, never promoted to `THREAD_FILE`) + `mv`; extractor failure path — asserts no `THREAD_FILE`, `THREAD_FILE.tmp`, or `THREAD_JSONL_FILE` remains (all three cleaned up); also asserts `THREAD_JSONL_FILE` is deleted on the success path (FN4 fold) and retained when `KEEP_THREAD_JSONL=1` (only on success — failure path always removes it); (3) continue, `THREAD_FILE` exists — runs `codex exec resume $SESSION_ID`; (4a) `"no rollout found for thread id"` exact-match fallback — clears stale `THREAD_FILE` + `THREAD_JSONL_FILE`, runs a one-shot fresh `codex exec` (no `--json`), and asserts BOTH `THREAD_FILE` and `THREAD_JSONL_FILE` remain ABSENT afterward (re-seed happens on the next continue call, not this one — iter-6 FN3); (4b) unrelated resume failure — exits non-zero, does NOT clear thread state; (5) `loop-reset` — removes `THREAD_FILE` + `THREAD_JSONL_FILE`. |
| H | `scripts/run-with-clean-env.py` + `shared/scripts-run-with-clean-env.py.tmpl` | Add `THREAD_MODE`, `THREAD_FILE`, `THREAD_JSONL_FILE`, **`KEEP_THREAD_JSONL`** to `EXACT_DROP` (FN5 fold + FN3 iter-5 fold). Prevents leaked Make variables from reaching the Codex subprocess. Tests: the Makefile shim asserts Codex does not receive these in its environment, **AND** the 4 vars are added to `tests/test_env_scrubber.py` (the repo's existing direct `EXACT_DROP` test) so the scrubber's own exact-drop contract covers them — not just the one Makefile path (iter-7 FN4). |
| I | `BACKLOG.md` (sweep — not just one entry) | Update the V-13.5 description to the current gate (3-gate read-only-ENFORCED: thread-id continuity + write-BLOCKED + resumed-rollout `sandbox_policy.type == "read-only"`; cwd/`/tmp` probe DROPPED — correction item 4), **then sweep** for stale text the single-entry edit would miss: `grep -n -e 'V-13[.]5' -e 'sandbox-denial' -e 'sandbox_policy' BACKLOG.md` (multiple `-e` patterns — NOT `|` alternation: inside a markdown table the `|` must be escaped `\|`, which `grep -E` then treats as a *literal* pipe that matches nothing; iter-7 FN2 caught the broken escaped-pipe form) and fix every bullet that still enumerates the gate as "sandbox-denial" (notably the "UPDATED to 4-assertion gate" trigger bullet, which currently contradicts the corrected bullet above it). After the sweep, re-run the same `grep` and require it to show no `BACKLOG.md` line describing the 2nd gate as "sandbox-denial". Add to rollout commit 4 (docs-only change). |
| J | `scripts/verify-v13-5.py` (new, repo-internal) + `tests/test_verify_v13_5.py` (new) | iter-7 FN1: V-13.5 Part 2 promoted from a manual copy-paste block to a tested verifier script. Orchestrates the live gate (seed → normal-path resume smoke through the Make/clean-env path → read-only-enforcement probe (resume with `-c sandbox_mode=read-only`) → 3-gate + artifact assertions → cleanup, `KEEP_V13_5_JSONL=1` opt-out). Repo-internal — NOT bootstrapped (not in `SHARED_TEMPLATE_MAP`/`EXECUTABLE_TARGETS`); generated projects inherit the proven feature, not the proof harness. Unit tests cover the pure functions (JSONL parse, 3-gate read-only-enforced, normal-path artifacts, `make`-command construction incl. `PLAN_FILE=`) with fixtures; the live `codex`/`make` calls are the manual pre-merge run only. |

**NOT in scope (no code deliverable)**: default flip from `THREAD_MODE=fresh` → `continue`
(deferred to post-A/B-replay gates — see Verification). User-facing adoption docs for
`THREAD_MODE=continue` in generated projects (how/when to opt in, `make loop-reset`
troubleshooting) — deferred to the default-flip PR, since the feature is opt-in +
default-`fresh` until the A/B gates pass (iter-8 FN2). Tier-2 bot quality comparison
(secondary signal only).

(iter-7 FN1: V-13.5 Part 2 is no longer listed here — it moved IN scope as a code
deliverable, Scope row J above; see Verification.)

## Architecture decisions

### Session ID extraction
⚠️ **Superseded by correction F1 (live gate 2026-05-30).** The resumable id is
`thread.started.thread_id` in the `codex exec --json` **STDOUT stream** (a UUIDv7 —
a time-ordered UUID in standard `8-4-4-4-12` form, so the strict UUID-validation
regex below applies). The `session_meta.payload.id` field that V-13 (commit da776ee)
pinned is the codex **rollout-FILE** schema (`~/.codex/sessions/<Y>/<M>/<D>/rollout-<ts>-<thread_id>.jsonl`),
where `session_meta.payload.id == thread_id`; V-13 captured the file, not the stream.
The extraction script reads the JSONL stream line by line and prints `thread_id`
from the first `thread.started` event.

**Cache metric (F4)**: in the STREAM the cache figure is
`turn.completed.usage.cached_input_tokens` (there is no `info: null` first-event
quirk in the stream — that was the rollout-file `event_msg…info` path). The
extraction script does NOT touch token fields; this is a reminder for the A/B
replay implementation (post-PR-1).

### When `--json` is added to `codex exec`
`--json` causes all events to stream to stdout as JSONL (instead of the
terminal-friendly display). `--output-last-message` continues to write the
review text to the specified file; the JSONL stdout is captured separately.

On the FIRST call when `THREAD_MODE=continue` and no `THREAD_FILE` exists:
1. Gate extraction behind successful Codex exit (FN2 iter-4 fold):
   ```
   codex exec --json --output-last-message "$(PLAN_REVIEW_OUT_CODEX)" ... \
     < /dev/null > "$(THREAD_JSONL_FILE)" \   # < /dev/null: --json hangs on stdin otherwise (F2)
   && scripts/extract-codex-session-id.py "$(THREAD_JSONL_FILE)" > "$(THREAD_FILE).tmp" \
   && grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' "$(THREAD_FILE).tmp" \
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
2. Run `codex exec resume $SESSION_ID -c sandbox_mode=read-only --output-last-message ... < /dev/null`
   (`-c sandbox_mode=read-only` is **SAFETY-CRITICAL** — resume defaults to
   `workspace-write` and does NOT inherit the seed's `--sandbox`, F3; `--json` NOT
   needed for normal operation — session ID already known)
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

**V-13.5 exception**: the V-13.5 verifier script (`scripts/verify-v13-5.py`, see
Verification) uses `--json` ONLY in its inheritance-probe step (capturing the resumed
JSONL for the thread-id-continuity gate; the rollout file supplies the sandbox-policy gate); its normal-path resume smoke step uses the plain Make
resume path (no `--json`), matching normal operation. This is a one-time pre-merge
verification, not normal operation.

When `THREAD_MODE=fresh` (the default — unchanged): current behavior, no
`--json`, no session-ID tracking.

### `-C`/`--sandbox` on resume
⚠️ **Corrected by F3 (live gate 2026-05-30).** `codex exec resume` does **NOT**
inherit `-C`/`--sandbox`. It runs in the caller's cwd and defaults to
`sandbox_mode=workspace-write` — so a resumed *review could write the repo*,
breaking the read-only contract the `fresh` path guarantees. The
`--sandbox`/`-C`/`--color` flags remain CLI-rejected on `resume`
(`unexpected argument`), so they cannot be re-passed; instead the recipe forces
read-only via the general config override **`-c sandbox_mode=read-only`**
(config key `sandbox_mode`; verified: write blocked). V-13.5 proves read-only is
*enforced* on resume (a write is BLOCKED + the resumed rollout's
`turn_context.payload.sandbox_policy.type == "read-only"`) — NOT that inheritance holds.

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

### V-13.5 — thread-id continuity + read-only ENFORCED on resume (Part 1 automated shim test; Part 2 a unit-tested verifier script run live before merge; failure blocks PR merge)

> ⚠️ **Superseded by the correction (item 4, 2026-05-30).** The authoritative gate is now **3 checks**, not 4: (a) **thread-id continuity** — the resume `--json` stream re-emits `thread.started` with the same `thread_id`; (b) **read-only ENFORCED** — a write is BLOCKED (probe file absent) **and** the resumed rollout file's `turn_context.payload.sandbox_policy.type == "read-only"`. The **cwd-inheritance gate is DROPPED** (no cwd inheritance; the recipe runs resume from the repo, so cwd=repo by construction — the probe no longer runs from `/tmp`). The Part 1 shim test additionally asserts the resume argv carries `-c sandbox_mode=read-only`. The Part 2 prose below describes the OLD 4-gate `/tmp` design and reads `session_meta`/`turn_context` from the stream (the stream has neither); **`scripts/verify-v13-5.py` + `tests/test_verify_v13_5.py` are the source of truth.**

**Part 1 — Makefile resume branch (shim-based, part of automated test matrix)**:
The test matrix in Scope G item (3) uses a fake codex shim to assert that when
`THREAD_FILE` exists, the Makefile recipe calls `codex exec resume $SESSION_ID`
(not `codex exec`). This verifies the Makefile branching logic without a live API call.

**Part 2 — V-13.5 verifier script (`scripts/verify-v13-5.py`, repo-internal; run live before merge)**:
iter-7 FN1 fold. The earlier copy-paste block seeded through `make review-plan-by-codex`
but then probed inheritance by calling `codex exec resume --json` **directly**, bypassing
the Makefile resume branch + `run-with-clean-env.py` wrapper — so it never live-tested the
NORMAL resumed Make path it claims to gate (that path could fail to materialize output or
mishandle the cleaned env and still pass the old gate). Promoting the gate to a script lets
it **(a)** live-test the normal resume path AND **(b)** inspect inheritance, with the pure
assertion logic unit-tested so the gate stops re-drifting as prose (the recurring imp-3
across iters 1/4/5/6/7). The script is **repo-internal**: it verifies the skill's own
dogfood resume behaviour and is NOT bootstrapped to generated projects (they inherit the
proven feature, not the proof harness), so it is not in `SHARED_TEMPLATE_MAP` /
`EXECUTABLE_TARGETS`.

Run `python3 scripts/verify-v13-5.py` from the repo root before merging. It:
1. Computes `KEY`/paths and **derives the plan path** so it can pass `PLAN_FILE=` to every
   `make` call — both `loop-reset` and `review-plan-by-codex` REQUIRE `PLAN_FILE` (Makefile
   guards — both targets `test -n "$(PLAN_FILE)"`); omitting it fails the gate before it
   tests anything (iter-8 FN1), and a unit test covers the command construction. Runs
   `make loop-reset PLAN_FILE=<plan>`; asserts clean preconditions (no `THREAD_FILE` /
   `THREAD_JSONL_FILE` / `PROBE_FILE` / `RESUMED_JSONL`).
2. **Seeds** a continue session: `make review-plan-by-codex PLAN_FILE=<plan>
   THREAD_MODE=continue ITERATION=1` → asserts `THREAD_FILE` now holds a UUID (`SESSION_ID`),
   else "probe DID NOT RUN".
3. **Normal-path resume smoke (the actual gated path)**: `make review-plan-by-codex
   PLAN_FILE=<plan> THREAD_MODE=continue ITERATION=2` (THREAD_FILE exists → resume branch **through**
   `run-with-clean-env.py`, no `--json`). Asserts: exit 0; `PLAN_REVIEW_OUT_CODEX`
   materialized (non-empty); `THREAD_FILE` unchanged (same UUID); JSONL cleanup holds
   (`THREAD_JSONL_FILE` absent by default).
4. **Inheritance probe (4 gates)**: `cd /tmp && codex exec resume "$SESSION_ID"
   --skip-git-repo-check --json > RESUMED_JSONL` (the `/tmp` contrast condition;
   `--skip-git-repo-check` required — codex resume fails in non-git dirs), then asserts ALL
   FOUR from the resumed JSONL:
   - **a. UUID continuity** — `session_meta.payload.id == SESSION_ID` (resume, not restart).
   - **b. sandbox-policy-type inheritance** — first `turn_context.payload.sandbox_policy.type
     == "read-only"` (deterministic proof the sandbox was inherited, not inferred from model
     behaviour).
   - **c. file absence** — no file at `PROBE_FILE` (corroborates b).
   - **d. cwd inheritance** — first `turn_context.payload.cwd == realpath(repo root)`; a
     matching cwd when resuming from `/tmp` proves inheritance, not caller-cwd (FN1 iter-4 fold).
5. **Cleanup (iter-7 FN5)**: on a PASS, removes `RESUMED_JSONL` + `PROBE_FILE` (same
   data-exposure rationale as `THREAD_JSONL_FILE`); on a FAILURE it RETAINS them so the
   failed gate can be debugged; `KEEP_V13_5_JSONL=1` retains them regardless. (This
   success-only cleanup is the deliberate inverse of `KEEP_THREAD_JSONL`'s
   always-remove-on-failure rule — the verifier's artifacts are short-lived debugging aids
   for a one-time manual gate run, not persistent state, so retaining them on failure aids
   debugging without a standing leak.)
6. **Preflight + 3 error classes (iter-8 FN3)**: a preflight first checks the environment
   (codex auth/reachability). The script then exits non-zero with a CLEAR class —
   **`environment unavailable`** (auth / quota / network / local-codex error, e.g. the
   `Operation not permitted` an in-process app-server hit can raise), **`probe DID NOT RUN`**
   (a seed/resume command failed for a feature reason), or **`inheritance/normal-path FAILED`**
   (an assertion failed). ALL nonzero results stay merge-blocking; the class tells the driver
   whether to **rerun in a valid env** (environment) or **file a bug** (probe/feature).

**Unit tests** (`tests/test_verify_v13_5.py`): cover the script's **pure** functions — JSONL
parsing, the read-only-ENFORCED gate check (thread-id continuity + sandbox-policy +
write-blocked), the normal-path artifact check, and the `make`-command
construction (incl. `PLAN_FILE=`) — using fixtures (`codex-json-stream.jsonl` for the
thread-id gate + `codex-json-session.jsonl` (rollout) for the sandbox-policy gate, plus
PASS/FAIL resumed variants). The
live `codex` / `make` calls are exercised only by the manual pre-merge run, not by the unit
tests (no live API call in CI).

If the verifier exits non-zero: this PR must NOT merge, regardless of class. For
`environment unavailable`, rerun in a valid environment (the gate hasn't actually tested the
feature yet — do not treat it as a feature pass OR fail). For `probe DID NOT RUN` or
`inheritance/normal-path FAILED`, the `THREAD_MODE=continue` branch is unsafe — file a bug
and keep `THREAD_MODE=fresh` (the safe default) until fixed.

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
3. Cache-hit value `turn.completed.usage.cached_input_tokens > 0` in `continue` JSONL stream (F4; verified via direct `--json` capture).
4. Quality guard: no imp-3 findings `fresh` found that `continue` missed
   (adjudicate near-misses via Tier-2 cross-direction review).
Budget cap: 5 replay iter pairs, ~$30, 30 min wall-clock.

Until all 4 pass: `THREAD_MODE=fresh` is the default; `THREAD_MODE=continue`
is opt-in via env var.

## Risks

| Risk | Mitigation |
|------|-----------|
| `--json` breaks current review display | `--output-last-message` file is unchanged; `cat` at end still works. V-13.5 Part 2 checks inheritance, not display — display is verified by the `--output-last-message` path independently. |
| Resumed review runs `workspace-write` unless forced read-only (resume does NOT inherit `--sandbox`; F3) | Recipe passes `-c sandbox_mode=read-only` on every resume. The V-13.5 read-only-ENFORCED gate (write BLOCKED + resumed rollout `turn_context.payload.sandbox_policy.type == "read-only"`) blocks PR merge if it regresses. |
| THREAD_JSONL_FILE data exposure | Written during first-continue call then deleted after successful extraction (default). Stale JSONL doesn't persist across runs. `KEEP_THREAD_JSONL=1` retains it for debugging (success-path only; failure path always removes it). |
| V-13.5 Part 2 needs `--json` on resume but normal ops don't | The V-13.5 verifier script uses `--json` ONLY in its inheritance-probe step; its normal-path resume smoke step — and all normal resumed calls in `review-plan-by-codex` — do NOT use `--json`. |
| A/B cache metric read from the wrong field | Stream metric is `turn.completed.usage.cached_input_tokens` (F4); the rollout-file `event_msg…info.total_token_usage` path is a different artifact. A/B replay is post-PR-1; not in this PR's scope. |
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
| 4 | Extend selftest-overlap + makefile-review-targets tests (6-case matrix: 1/2/3/4a/4b/5 + clean-env leak test); add `THREAD_MODE`/`THREAD_FILE`/`THREAD_JSONL_FILE`/`KEEP_THREAD_JSONL` to `tests/test_env_scrubber.py` exact-drop assertions (iter-7 FN4); update + sweep BACKLOG.md V-13.5 references (Scope I — docs-only) | `tests/test_selftest_overlap.py`, `tests/test_makefile_review_targets.py`, `tests/test_env_scrubber.py`, `BACKLOG.md` |
| 5 | `scripts/verify-v13-5.py` (V-13.5 verifier — incl. iter-8 preflight + 3 error classes, FN3) + `tests/test_verify_v13_5.py` (unit tests for its pure functions — JSONL parse, 3-gate read-only-enforced, normal-path artifacts, `make`-command construction incl. `PLAN_FILE=`, iter-8 FN1) (iter-7 FN1 + iter-8 FN1/FN3) | `scripts/verify-v13-5.py`, `tests/test_verify_v13_5.py` |

Tier-1 review (same-AI fresh subagent) after each commit before push.
`make check` passes before the final commit merges. The **V-13.5 verifier**
(`python3 scripts/verify-v13-5.py`, commit 5) runs **live after commit 5** — i.e., after
the `run-with-clean-env.py` EXACT_DROP change (commit 3) AND after the verifier itself
exists — and before the PR is opened for Tier-2 review. It exercises the final execution
path (the normal `THREAD_MODE=continue` resume branch *through* `run-with-clean-env.py`,
plus the inheritance probe), not a partial state (iter-7 FN1).

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
| 7 | Codex | 2026-05-29 | 1 / 4 / 0 | do not implement yet | **Driver-decision point** (handoff): imp-3 stuck at 1, 5th iter on V-13.5 (a structural manual-prose-gate problem). Surfaced to user → chose **option A: script V-13.5**. FN1 (imp-3) (a) the V-13.5 probe bypassed the Make resume path it claimed to gate (direct `codex exec resume --json` vs the `run-with-clean-env.py`-wrapped Make branch; contradicted the rollout's "tests the final execution path" claim) → promoted Part 2 to a tested verifier `scripts/verify-v13-5.py` (repo-internal, Scope row J + commit 5): seeds → NORMAL-PATH resume smoke through the wrapper (exit 0 + output materialized + THREAD_FILE unchanged + JSONL cleanup) → `/tmp` `--json` inheritance probe (4 gates) → cleanup; pure assertion logic unit-tested; moved Part 2 OUT of NOT-in-scope. FN2 (imp-2) (a) the iter-6 BACKLOG sweep grep was broken — `'V-13\.5\|...'` escaped pipes are literals in ERE (verified: 0 matches) → `grep -n -e ... -e ... -e ...` (no pipes, table-safe). FN3 (imp-2) (a) loose UUID regex `[0-9a-f-]{36}` → strict `8-4-4-4-12` + negative tests (all-hyphen/no-hyphen/wrong-length rejected). FN4 (imp-2) (a) clean-env coverage only on the Makefile shim → also add the 4 vars to `tests/test_env_scrubber.py` (existing direct EXACT_DROP test). FN5 (imp-2) (a) manual probe left `/tmp/test-v13-5-resumed.jsonl` uncleaned → subsumed by FN1 (the verifier cleans RESUMED_JSONL + PROBE_FILE; `KEEP_V13_5_JSONL=1` opt-out). imp-3 trajectory 2→3→3→2→2→1→1. |
| 7.5 | Claude (consistency self-check; rounds a–c) | 2026-05-29 | doc-drift × 3→2→0 | folded + driver-exit | Round a: caught a regression *I* introduced in the iter-7 fold — the Lessons rewrite re-added the iter-enumeration ("iters 1,4,5,6,7" + "5 iters") that iter-6.5f had stripped as the drift-magnet (and it undercounted vs the Evidence table) → re-applied 6.5f's strip (the iter-7 "folds introduce defects" Lessons bullet, lived in real time). Round b: (a) "ULIDv7 UUID" (line 41) was self-contradictory — the FN3 strict-UUID regex surfaced the latent error → "UUIDv7"; (a) the verifier's `KEEP_V13_5_JSONL` cleanup semantics were unspecified → pinned (success-only cleanup; retain on failure for debugging; deliberate inverse of `KEEP_THREAD_JSONL`). Driver-exit: V-13.5 header "inheritance" gradient (already accepted iter-6.5d), and the 6.5f-log-quote-vs-current-Lessons mismatch (frozen historical narrative). Substantive invariants PASSED every round. Round c = final stamp on this row. Loop-ack stamped; ready for iter 8. |
| 8 | Codex | 2026-05-29 | 1 / 2 / 0 | do not implement yet → **LOOP COMPLETE (driver-exit)** | **Stop-and-implement point** (handoff's `~7-8` upper bound; user pre-approved implementation in the next session). imp-3 stuck at 1 for a 3rd iter, again V-13.5 — and like iters 6/7 it was a defect the PRIOR iter's V-13.5 rewrite introduced, confirming prose specs of runtime behaviour won't converge (this vindicates the iter-7 decision to script + unit-test it). All 3 folded (a) to correct the spec, then the review loop is EXITED by driver decision (not re-reviewed): FN1 (imp-3) the verifier's `make loop-reset` / `review-plan-by-codex` calls dropped `PLAN_FILE` (both targets require it; the iter-7 rewrite omitted it) → script derives the plan path + passes `PLAN_FILE=` to every make call + unit-tests command construction. FN2 (imp-2) no generated-project adoption doc for `THREAD_MODE=continue` → deferred to the default-flip PR. FN3 (imp-2) verifier conflated env failure with feature failure → preflight + 3 error classes (`environment unavailable` / `probe DID NOT RUN` / `inheritance/normal-path FAILED`), all merge-blocking with rerun-vs-file-bug guidance. imp-3 trajectory 2→3→3→2→2→1→1→1. Remaining V-13.5 spec-gaps are now caught by the script's unit tests at implementation, not more prose iters. |
| 8.5 | Claude (consistency self-check; rounds a–c) | 2026-05-29 | doc-drift × 5 | folded | Round a: 3 propagation gaps from the iter-8 folds in SUMMARIES — (a) Scope J + Critical files unit-test enum missed "command construction" → added; (a) rollout commit 5 missing iter-8 FN1 test + FN3 preflight/3-error-classes → updated; line-ref `:282`/`284` initially driver-exited. Round b: my round-a fix was incomplete AND backwards — the AUTHORITATIVE Verification unit-test paragraph still omitted "command construction" while the 3 summaries now had it (fold-introduced gap in the wrong direction) → added it to Verification; also de-brittled the loop-reset ref (dropped the line numbers, ending the `:282`/`284` disagreement). Round c = final stamp. Substantive invariants all PASSED (V-13.5 4-gate, KEEP_THREAD_JSONL/KEEP_V13_5_JSONL semantics, stale-fallback, EXACT_DROP, strict UUID regex, BACKLOG grep form, trajectory 2→3→3→2→2→1→1→1). Loop-ack stamped; **PLAN COMPLETE — ready for implementation**. |
| impl-findings | Live V-13.5 gate (real codex 0.130) | 2026-05-30 | — | **PLAN CORRECTED — re-implement** | The first live gate run FALSIFIED the V-13 schema + the PR #10 iter-4 "resume inherits `-C`/`--sandbox`" assumption. Real codex `--json` = `thread.started`/`thread_id` (the `session_meta` schema is the rollout FILE, which V-13 captured by mistake); `--json` hangs on stdin without `< /dev/null`; and **`codex exec resume` does NOT inherit the sandbox — it defaults to workspace-write (a resumed review could WRITE the repo)**, fixable only via `-c sandbox_mode=read-only`. The 6 commits on `feat/skill-pr1-bucket-f-continue-thread` are built on the wrong assumptions → re-implement per the "⚠️ Implementation-findings plan correction (2026-05-30)" section at the top. This vindicates scripting + live-running V-13.5 (iter-7/8): 8 prose review iters + 855 offline tests all inherited the wrong V-13 fixture; only the live gate caught it. |
| 9 | Codex (attempted → skipped) | 2026-05-30 | — | n/a | Cross-review of the CORRECTED plan. `make review-plan-by-codex … ITERATION=9`, timeout-guarded at 180s: codex was actively inspecting the repo (xhigh reasoning) but produced **zero findings** before the kill — documented large-repo slowness (memory `feedback-codex-timeout`), aggravated by Codex.app running concurrently. Per the driver instruction, skipped codex and ran a Claude consistency self-check instead (iter-9.5). The mandatory live V-13.5 gate still runs before PR (needs Codex.app quit). |
| 9.5 | Claude (consistency self-check) | 2026-05-30 | body↔correction × 9 | folded | Reconciled the plan body with the authoritative 2026-05-30 correction (the body still described the falsified design). Folds: Scope A + Architecture "Session ID extraction" (`session_meta.payload.id` → `thread.started.thread_id`, stream vs rollout-file); Architecture "`-C`/`--sandbox` on resume" rewritten (resume does NOT inherit; force `-c sandbox_mode=read-only`; **SAFETY**); seed snippet + resume step gained `< /dev/null` / `-c sandbox_mode=read-only`; V-13.5 header banner (3-gate read-only-ENFORCED; cwd gate DROPPED; probe from repo not `/tmp`); Risks rows (workspace-write risk + cache-metric field); A/B cache metric → `turn.completed.usage.cached_input_tokens`; Critical-files fixture split (stream vs rollout). **Left intact**: historical iter rows (1–8) + the Evidence table (a record of the past, not rewritten); the long V-13.5 Part 2 prose sits under a "superseded" banner — `scripts/verify-v13-5.py` + its unit tests are the source of truth. |

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
| Codex iter-6 FN5 | Scope I's single-entry update would miss stale "sandbox-denial" at BACKLOG:122 | 2 | Broadened Scope I to a `grep`-driven sweep of BACKLOG.md. **[sweep command itself fixed by iter-7 FN2 — the escaped-pipe form was broken]** | Scope I; Critical files |
| Codex iter-7 FN1 | V-13.5 probe called `codex exec resume --json` directly, bypassing the Make resume branch + clean-env wrapper it claims to gate — so the normal resume path was never live-tested (contradicted the rollout's "tests the final execution path" claim) | 3 | **Driver chose option A (script it).** Promoted V-13.5 Part 2 to a tested verifier `scripts/verify-v13-5.py` (repo-internal): seed → normal-path resume smoke *through* `run-with-clean-env.py` → `/tmp` `--json` inheritance probe (4 gates) → cleanup; pure assertion logic unit-tested. Moved Part 2 OUT of NOT-in-scope into Scope J + commit 5. Structurally ends the recurring V-13.5 imp-3 (code reviewed once + unit-tested, not re-litigated as prose). | NOT-in-scope; Scope row J (new); Verification V-13.5 (header + Part 2); Architecture V-13.5 exception; Implementation rollout (commit 5 + gate timing); Critical files; Lessons surfaced; Iteration log |
| Codex iter-7 FN2 | The iter-6 FN5 BACKLOG sweep grep `'V-13\.5\|sandbox-denial\|sandbox_policy'` is broken — escaped `\|` are *literal* pipes in ERE, so it matches nothing (verified: 0 hits, while the real stale text sits at BACKLOG:122) | 2 | Replaced with `grep -n -e 'V-13[.]5' -e 'sandbox-denial' -e 'sandbox_policy'` (multiple `-e`, no pipe chars — table-safe AND functional); require a post-edit re-run to show no stale wording. | Scope I (supersedes the iter-6 FN5 sweep command) |
| Codex iter-7 FN3 | UUID-validation regex `^[0-9a-f-]{36}$` too loose — accepts 36 hyphens or no-hyphen hex, so a malformed ID could be promoted to durable `THREAD_FILE` | 2 | Tightened to strict `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`; added negative tests (all-hyphen / no-hyphen / wrong-length → rejected → failure cleanup fires, never promoted). | Architecture first-continue snippet; Scope G case 2 |
| Codex iter-7 FN4 | Clean-env verification assigned only to the new Makefile shim; the repo's existing `tests/test_env_scrubber.py` (direct `EXACT_DROP` test) omits the 4 new vars, so the scrubber's own contract can drift | 2 | Add the 4 THREAD vars to `tests/test_env_scrubber.py` setup + stripped assertions; list it in Scope H, rollout commit 4, and Critical files. | Scope H; Implementation rollout commit 4; Critical files |
| Codex iter-7 FN5 | The manual V-13.5 probe wrote `/tmp/test-v13-5-resumed.jsonl` with no post-run cleanup — same data-exposure class as `THREAD_JSONL_FILE` | 2 | **Subsumed by FN1**: the verifier script removes `RESUMED_JSONL` + `PROBE_FILE` after asserting, with a `KEEP_V13_5_JSONL=1` debug opt-out. | Verification V-13.5 Part 2 (cleanup step) |
| Codex iter-8 FN1 | The iter-7 V-13.5 script rewrite dropped `PLAN_FILE` from the verifier's `make loop-reset` / `review-plan-by-codex` calls; both targets require it (Makefile guards) → the gate fails before testing anything | 3 | Script derives the plan path and passes `PLAN_FILE=<plan>` to every make call; unit-test the command construction. (3rd consecutive V-13.5 imp-3 introduced by the prior iter's rewrite — the pattern that justified scripting + unit-testing it.) | Verification V-13.5 steps 1-3; Scope J |
| Codex iter-8 FN2 | Feature ships into `shared/Makefile.review.tmpl` but the plan has no generated-project adoption doc for `THREAD_MODE=continue` | 2 | **Deferred** to the default-flip PR (feature is opt-in + default-`fresh` until the A/B gates pass); recorded in NOT-in-scope. | NOT-in-scope |
| Codex iter-8 FN3 | The live verifier (merge blocker) didn't separate environment failure from feature failure — Codex's own run hit `Operation not permitted` | 2 | Added a preflight + 3 error classes (`environment unavailable` / `probe DID NOT RUN` / `inheritance/normal-path FAILED`); all merge-blocking, with rerun-vs-file-bug guidance. | Verification V-13.5 step 6 + failure policy |

## Implementation log

| short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |
|-----------|---------------------|---------------------------------|------------------------|
| 09c6a77 | extract-codex-session-id.py + 9 subprocess unit tests: prints session_meta.payload.id from the first event; non-zero exit + empty stdout when absent | none (Tier-1 folded 2 polish tests: non-dict JSON line + directory-arg edge) | none |
| 1d8af64 | THREAD_MODE continue branch (fresh/seed/resume) for review-plan-by-codex; byte-identical Makefile+template; loop-reset clears thread state; review prompt hoisted to one shell var | none | Tier-1 caught a reintroduced imp-3 — the resume call copy-pasted `-C`/`--sandbox`/`--color`, which `codex exec resume` rejects (`unexpected argument`, LESSONS.md 2026-05-27 / PR #10 iter-4); dropped them (resume inherits). The fake-shim smoke could not surface it (real-CLI-only); commit 4 adds a shim assertion that resume argv excludes those flags |
| afbe58e | Register extract-codex-session-id in SHARED_TEMPLATE_MAP + EXECUTABLE_TARGETS (new byte-identical template); add THREAD_MODE/THREAD_FILE/THREAD_JSONL_FILE/KEEP_THREAD_JSONL to clean-env EXACT_DROP (both copies) | none | none (Tier-1 note carried to commit 4: also add the new template to test_shared_templates.py SHARED_TEMPLATES_TO_SCAN for scan-list symmetry) |
| 145ac7a | THREAD_MODE 6-case matrix (fresh/seed[+extract-fail+KEEP]/resume[asserts argv excludes -C/--sandbox/--color]/4a-stale/4b-unrelated/loop-reset) via env-driven codex shim; executable-bit + thread-machinery presence guards; +4 THREAD vars in env-scrubber test; +new template in SHARED_TEMPLATES_TO_SCAN; BACKLOG V-13.5 sweep + `.payload.` precision | none | Tier-1 (mutation-tested) flagged imp-2: case-4b `returncode!=0` passed via an incidental trailing-`cat` failure, not exit-code propagation — fixed by writing output on fail-other so only true `exit $$rc` yields non-zero (mutation-confirmed it now catches a swallowed exit); +imp-1 BACKLOG field-path `.payload.` |
| 87d555a | V-13.5 repo-internal live verifier (preflight + seed + normal-path resume smoke through clean-env + `/tmp` 4-gate inheritance probe; `PLAN_FILE=` on every make call; 3 merge-blocking error classes) + 32 pure-function unit tests over the V-13 fixture; NOT bootstrapped | none | Tier-1: no imp-3; folded imp-2 (tightened the env-vs-feature classifier from bare words → specific phrases — the plan under review itself contains "network"/"quota"; +3 false-positive-guard tests); rejected an imp-1 after premise-check (docstring already enumerates the funcs the reviewer thought were omitted) |
| cc37d1c | Broaden the V-13.5 env-classifier to catch OAuth / connected-MCP-auth token failures (`invalid_grant` / `tokenrefreshfailed` / `authrequired` / `www-authenticate`) + 2 unit tests vs the verbatim live-run failure | none | **LIVE GATE BLOCKED — environment, not feature.** The seed codex call aborted on an expired Meta-ads MCP OAuth token in the codex env (`TokenRefreshFailed`/`invalid_grant`, `mcp.facebook.com`); the THREAD_MODE feature behaved correctly (atomic cleanup, no corrupt state). The classifier mislabelled the env failure as "file a bug" → fixed to env-unavailable. **The gate must be RERUN after the broken MCP token is fixed/removed; PR stays unopened until it PASSES (THREAD_MODE=fresh remains the safe default meanwhile).** |
| _(re-implementation per the 2026-05-30 correction begins below — corrective commits on top; interactive rebase unavailable in this env)_ | | | |
| 408baad | Extractor + byte-identical template now read `thread.started.thread_id` from the `codex exec --json` STDOUT stream; new `codex-json-stream.jsonl` fixture; tests rewritten with a session_meta-rejection regression test and a stream-vs-rollout schema lock | none — implements correction F1 / Scope row A exactly | none — 861 suite tests green (4 skipped); 22 extractor+fixture tests and 8 thread-shim matrix tests pass; Tier-1 (fresh Claude subagent) confirmed `verify-v13-5.py` correctly retains the rollout-FILE schema (a different artifact, reworked in a later commit) — no imp-3/imp-2 |
| 11c8594 | resume recipe forces `-c sandbox_mode=read-only` + `< /dev/null` on every codex call (F2/F3); case-3 shim now asserts the override is present and `-c`-adjacent, still excludes --json/-C/--sandbox/--color | none — implements correction items 2/3 / Scope rows B+C exactly; byte-identical Makefile+template verified by render-and-diff | none — 35 review-target + 34 verifier-unit + 13 parity tests green; Tier-1 confirmed `< /dev/null` survives `os.execvpe` (fd preserved) and composes with `2>&1`/`$(...)`/`>file`. Open risk it flagged (imp-2, deferred to the NEXT commit per Scope J): `scripts/verify-v13-5.py` + its tests still encode the OLD 4-gate `/tmp` "resume inherits sandbox" model and don't pass `-c sandbox_mode=read-only` on the probe — reworked next, before the live gate/PR |
| b3849c4 | V-13.5 verifier reworked to the 3-gate read-only-ENFORCED model: `thread_id_of` reads the `--json` STREAM's thread.started.thread_id; `sandbox_type_of` reads the resumed ROLLOUT FILE's LAST turn_context; `resume_probe_command` forces `-c sandbox_mode=read-only` (unit-locked); cwd/`/tmp` gate DROPPED; probe runs from the repo; `/v13-5-probe.txt` gitignored. Resolves the imp-2 from 11c8594 (Scope row J) | none — implements correction item 4 / Scope row J exactly | Tier-1 (fresh Claude subagent, no imp-3): folded F-1 (imp-2, gitignore the repo-internal probe artifact), F-3 + F-2 (imp-1, docstring "first/last"→LAST; soften the "could not locate rollout" message since the resume succeeded). Reviewer mutation-tested the unit tests + verified robustness to BOTH codex rollout-file models (append-to-one-file last-wins + separate-file newest-mtime) against live `~/.codex/sessions`. 42 verifier unit tests + full `make check` (869 passed/4 skipped) green |
| _(live V-13.5 gate, post-b3849c4)_ | **PASS** (2026-05-30, real codex-cli 0.130): `python3 scripts/verify-v13-5.py` → EXIT_OK. Seed session `019e78c7-6516-7770-9dd2-eaf38cee1096` (THREAD_FILE + a fresh `~/.codex/sessions` rollout); resumed-rollout `turn_context.payload.sandbox_policy.type == "read-only"`; write probe BLOCKED (no `v13-5-probe.txt`); normal resume path materialised output. **Merge-blocker satisfied — the read-only-on-resume safety contract is proven, superseding the cc37d1c "gate blocked / PR stays unopened" state.** | n/a (gate run, not a commit) | Codex.app was running but did not interfere this run; the prior expired-Meta-ads-MCP-OAuth env-block did not recur. PR opened as-is per driver decision (also carries 4 non-PR-1 commits already on local main — PR-2 design note ×2, PR-3 script, side-item-3) |

## Lessons surfaced (this PR)

- **Manual prose verification gates for runtime behaviour accrue defects across iters — change their FORM, don't keep re-wording.**
  V-13.5 Part 2 generated fresh review findings repeatedly throughout this loop (see the
  Evidence table for the per-iter record) — each a different way a prose gate fell short of
  verifying runtime behaviour; at iter 7 it was found to test the wrong path entirely (a
  direct `--json` probe, not the Make resume path it claimed to gate). **Resolution
  (iter-7, driver-approved option A):** promoted V-13.5 to a tested verifier script
  (`scripts/verify-v13-5.py` + unit tests on its pure logic) — code is reviewed once and
  unit-tested, so it stops re-drifting as prose. **Rule (strong `LESSONS.md` candidate):**
  when a verification step is BOTH safety-critical AND covers runtime behaviour a prose
  block can't fully capture, script + unit-test it from the START rather than specifying it
  in prose. **Plan-loop signal:** if the SAME section keeps generating an imp-3 across
  several consecutive iters, the section is structurally wrong for prose — change its form
  and surface a driver decision rather than looping (what happened here → driver chose to
  script it).
- **Folds can introduce new defects — re-review the fold itself.** iter-7 FN2 (broken
  escaped-pipe grep) and FN5 (uncleaned RESUMED_JSONL) were both defects introduced by
  iter-6 folds. Echoes the over-defensive-folds lesson (`LESSONS.md` 2026-05-27): a fold is
  new code/text and deserves the same scrutiny as the original.

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
- `tests/fixtures/codex-json-stream.jsonl` (new) — real `codex exec --json` STDOUT **stream** sample (`thread.started.thread_id`, `turn.completed.usage.cached_input_tokens`); the extractor + the V-13.5 thread-id gate read this
- `tests/fixtures/codex-json-session.jsonl` — the codex **rollout-FILE** sample (`session_meta` + `turn_context.payload.sandbox_policy.type`); the V-13.5 read-only gate reads this (NOT the stream)
- `scripts/run-with-clean-env.py` + `shared/scripts-run-with-clean-env.py.tmpl` — add THREAD_MODE/FILE/JSONL_FILE/KEEP_THREAD_JSONL to EXACT_DROP
- `BACKLOG.md` — update V-13.5 description **and sweep stale `sandbox-denial`/4-gate text** (3-gate read-only-ENFORCED; see Scope I)
- `scripts/verify-v13-5.py` (new, repo-internal) — the V-13.5 verifier (iter-7 FN1); NOT bootstrapped (not in `SHARED_TEMPLATE_MAP`/`EXECUTABLE_TARGETS`)
- `tests/test_verify_v13_5.py` (new) — unit tests for the verifier's pure functions (JSONL parse, 3-gate read-only-enforced, normal-path artifacts, `make`-command construction incl. `PLAN_FILE=`) using fixtures; no live calls
- `tests/test_env_scrubber.py` — add `THREAD_MODE`/`THREAD_FILE`/`THREAD_JSONL_FILE`/`KEEP_THREAD_JSONL` to its `EXACT_DROP` assertions (iter-7 FN4)
