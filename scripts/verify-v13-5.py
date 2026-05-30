#!/usr/bin/env python3
"""V-13.5 — live pre-merge gate for Bucket F (Codex thread-continuation).

REPO-INTERNAL proof harness. This script verifies the skill's OWN dogfood
`THREAD_MODE=continue` behaviour; it is deliberately NOT bootstrapped to
generated projects (not in SHARED_TEMPLATE_MAP / EXECUTABLE_TARGETS) — they
inherit the proven feature, not the harness.

Run it from the repo root before opening the PR:

    python3 scripts/verify-v13-5.py [PLAN_FILE]

It is a MERGE BLOCKER: any non-zero exit means do NOT merge. The non-zero
exit CLASS tells you what to do:

  - environment unavailable (exit 2): codex auth / quota / network / a local
    codex error (e.g. an in-process app-server hitting "Operation not
    permitted", or a connected-MCP-server OAuth token expiring). The gate has
    NOT actually tested the feature — RERUN in a valid environment. Do not
    treat as a feature pass OR fail.
  - probe DID NOT RUN (exit 3): a seed/resume command failed for a feature
    reason (e.g. the seed never produced THREAD_FILE). FILE A BUG and keep
    THREAD_MODE=fresh (the safe default) until fixed.
  - inheritance/normal-path FAILED (exit 4): an assertion failed — the resume
    branch did not materialise output, or read-only was NOT enforced on resume
    (a write succeeded, or the resumed rollout's sandbox_policy.type was not
    "read-only"), or thread-id continuity broke. The THREAD_MODE=continue
    branch is unsafe — FILE A BUG and keep THREAD_MODE=fresh until fixed.

What it does (live, ~3 real codex calls):
  0. Preflight — confirm codex is reachable + authenticated.
  1. `make loop-reset PLAN_FILE=<plan>` → assert clean preconditions.
  2. Seed: `make review-plan-by-codex PLAN_FILE=<plan> THREAD_MODE=continue
     ITERATION=1` → assert THREAD_FILE now holds a session id (thread_id).
  3. Normal-path resume smoke (THE gated path): `make review-plan-by-codex
     ... THREAD_MODE=continue ITERATION=2` (resume branch THROUGH
     run-with-clean-env.py, no --json). Assert exit 0 + output materialised
     + THREAD_FILE unchanged + JSONL cleaned up.
  4. Read-only-ENFORCED probe (3 gates): resume the seed thread with
     `-c sandbox_mode=read-only --json` (mirroring the recipe's resume flags)
     and a WRITE-attempting prompt, run FROM THE REPO. Assert
     (a) thread-id continuity — the resume stream re-emits thread.started with
         the same thread_id;
     (b) read-only enforced — the resumed ROLLOUT FILE's
         turn_context.payload.sandbox_policy.type == "read-only";
     (c) the write was BLOCKED — the probe file was NOT created.
     The OLD 4th gate (cwd inheritance, probe from /tmp) is DROPPED: the recipe
     runs resume from the repo, so cwd=repo by construction (correction 2026-05-30).
  5. Cleanup: on PASS, remove the probe/JSONL artifacts; on FAILURE retain
     them for debugging; KEEP_V13_5_JSONL=1 retains regardless (the deliberate
     inverse of KEEP_THREAD_JSONL's always-remove-on-failure).

Schema note (verified live, codex 0.130, 2026-05-30): the `codex exec --json`
STDOUT *stream* keys continuity on `thread.started.thread_id` and has NO
turn_context. `sandbox_policy.type` lives only in the codex ROLLOUT FILE
(~/.codex/sessions/<Y>/<M>/<D>/rollout-<ts>-<thread_id>.jsonl) — so gate (b)
reads the rollout file, not the stream. `codex exec resume` does NOT inherit
`-C`/`--sandbox` (it defaults to workspace-write); read-only is forced via the
general config override `-c sandbox_mode=read-only`.

The PURE functions below (make_command, resume_probe_command, compute_key,
parse_jsonl, thread_id_of, sandbox_type_of, check_gates, normal_path_artifacts_ok,
looks_like_env_failure) are unit-tested in tests/test_verify_v13_5.py with
fixtures — no live calls in CI.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN = "docs/plans/2026-05-29-skill-pr1-bucket-f-continue-thread.md"

# Exit classes. Every non-zero value is merge-blocking; the value distinguishes
# "rerun in a valid env" (ENV) from "file a bug" (PROBE / FAIL).
EXIT_OK = 0
EXIT_ENV = 2
EXIT_PROBE = 3
EXIT_FAIL = 4

# Substrings (lower-cased) that mark a codex failure as an ENVIRONMENT problem
# rather than a feature failure (iter-8 FN3 — distinguish so the driver reruns
# instead of filing a spurious bug). Deliberately SPECIFIC phrases, not bare
# words: the seed/resume calls cat a review of the plan (which itself contains
# words like "network"/"quota" in its own error-class prose), so bare
# "connection"/"network"/"401" would false-positive a real feature failure into
# "rerun". 401/403 are covered by the "unauthorized"/"forbidden" phrasings.
_ENV_SIGNATURES = (
    "operation not permitted",
    "not logged in",
    "unauthorized",
    "forbidden",
    "rate limit",
    "network error",
    "network is unreachable",
    "timed out",
    "connection refused",
    "connection reset",
    "could not connect",
    "econnrefused",
    "authentication failed",
    # OAuth / connected-MCP-server auth failures (surfaced by the first live
    # run: an expired Meta-ads MCP token aborted codex before it seeded a
    # thread). These are specific machine-error tokens, not prose, so they stay
    # env-class without re-introducing bare-word false positives.
    "invalid_grant",
    "tokenrefreshfailed",
    "authrequired",
    "www-authenticate",
    "www_authenticate",
)


# ─── pure helpers (unit-tested; no I/O, no live calls) ──────────────────────


def compute_key(repo_root: str, plan_file: str) -> str:
    """Mirror the Makefile KEY formula EXACTLY so we locate the same
    THREAD_FILE the recipe writes:
        sha256(realpath(CURDIR) + ':' + realpath(PLAN_FILE))[:12]
    """
    k = os.path.realpath(repo_root) + ":" + os.path.realpath(plan_file)
    return hashlib.sha256(k.encode()).hexdigest()[:12]


def make_command(target: str, plan_file: str, **make_vars: str) -> list[str]:
    """Build a `make <target> PLAN_FILE=<plan> [VAR=value ...]` argv.

    PLAN_FILE is ALWAYS included: both `loop-reset` and `review-plan-by-codex`
    guard on `test -n "$(PLAN_FILE)"`, so an omitted PLAN_FILE fails the make
    call before it tests anything (iter-8 FN1 — the prior prose verifier
    dropped it). This is the single source of make-invocation construction so
    the unit test can lock the PLAN_FILE= invariant.
    """
    cmd = ["make", target, f"PLAN_FILE={plan_file}"]
    for key, value in make_vars.items():
        cmd.append(f"{key}={value}")
    return cmd


def subprocess_env(base_env: Mapping[str, str]) -> dict[str, str]:
    """Environment for the verifier's make/codex subprocesses — a copy of the
    operator's env with KEEP_THREAD_JSONL stripped.

    If KEEP_THREAD_JSONL=1 is exported in the operator's shell, the seed
    `make review-plan-by-codex` recipe inherits it and RETAINS THREAD_JSONL_FILE:
    its `[ "$KEEP_THREAD_JSONL" = 1 ] || rm` test reads the shell env directly, and
    run-with-clean-env.py's EXACT_DROP only scrubs the codex subprocess, not this
    recipe-level shell test. The retained JSONL then trips the step-3 `jsonl_absent`
    gate and SPURIOUSLY fails V-13.5. The verifier always wants the recipe's default
    (delete-after-extract) behaviour; its own artifact retention is the separate
    KEEP_V13_5_JSONL knob (read by this script, not by the recipe). (Tier-2 codex P2.)
    """
    env = dict(base_env)
    env.pop("KEEP_THREAD_JSONL", None)
    return env


def resume_probe_command(repo_root: str, session_id: str, probe_file: str) -> list[str]:
    """Build the read-only-ENFORCED resume-probe argv (the SAFETY core of V-13.5).

    Mirrors the recipe's resume invocation: `-c sandbox_mode=read-only` (resume
    defaults to workspace-write and does NOT inherit --sandbox; F3) and NO
    --sandbox/-C/--color (resume CLI-rejects those). `--json` captures the stream
    for the thread-id-continuity gate. The prompt asks codex to WRITE probe_file
    so the gate can assert read-only blocked it.

    Single source of construction so the unit test can lock the `-c
    sandbox_mode=read-only` flag — a regression dropping it would let the probe
    resume in workspace-write and silently pass the write-blocked gate (the exact
    failure mode the live gate exists to catch).
    """
    return [
        f"{repo_root}/scripts/run-with-clean-env.py",
        "--",
        "codex",
        "exec",
        "resume",
        session_id,
        "-c",
        "sandbox_mode=read-only",
        "--json",
        (
            f"Use a shell command to create the file {probe_file} containing the "
            "text v13-5-probe, then tell me whether the write succeeded."
        ),
    ]


def parse_jsonl(text: str) -> list[dict]:
    """Parse a codex JSONL stream/file into a list of dict events; skip blank or
    non-JSON / non-object lines."""
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def thread_id_of(events: list[dict]) -> str | None:
    """First thread.started.thread_id (a string) from a `codex exec --json`
    STREAM, else None. This is the resumable id — NOT session_meta.payload.id
    (that is the rollout-FILE field; the stream has no session_meta)."""
    for e in events:
        if e.get("type") == "thread.started":
            tid = e.get("thread_id")
            if isinstance(tid, str) and tid:
                return tid
    return None


def sandbox_type_of(rollout_events: list[dict]) -> str | None:
    """The LAST turn_context.payload.sandbox_policy.type from a codex ROLLOUT
    FILE, else None.

    Reads the rollout FILE (not the --json stream — the stream has no
    turn_context). LAST (not first) so the RESUMED turn's sandbox is checked: if
    a regression resumed in workspace-write, it shows up in the most recent
    turn_context even when the seed turn was read-only.
    """
    result = None
    for e in rollout_events:
        if e.get("type") == "turn_context" and isinstance(e.get("payload"), dict):
            sp = e["payload"].get("sandbox_policy")
            if isinstance(sp, dict) and "type" in sp:
                result = sp.get("type")
    return result


def check_gates(
    stream_events: list[dict],
    rollout_events: list[dict],
    expected_session_id: str,
    probe_file_exists: bool,
) -> tuple[bool, dict[str, tuple[bool, str]]]:
    """The V-13.5 read-only-ENFORCED gate — 3 checks (correction item 4):

    a. thread-id continuity — the resume STREAM re-emits thread.started with the
       same thread_id (resume, not restart).
    b. read-only enforced — the resumed ROLLOUT FILE's LAST
       turn_context.payload.sandbox_policy.type == "read-only" (deterministic
       proof read-only was applied, not inferred from model behaviour).
    c. write blocked — the probe file was NOT created (corroborates b: read-only
       actually prevented the write).

    The OLD cwd-inheritance gate is DROPPED: the recipe runs resume from the
    repo, so cwd=repo by construction. `probe_file_exists` is supplied by the
    caller so this stays pure. Returns (passed, {gate: (ok, detail)}).
    """
    results: dict[str, tuple[bool, str]] = {}

    tid = thread_id_of(stream_events)
    results["a_thread_id_continuity"] = (
        tid == expected_session_id,
        f"thread.started.thread_id={tid!r} (expected {expected_session_id!r})",
    )

    sandbox_type = sandbox_type_of(rollout_events)
    results["b_sandbox_read_only"] = (
        sandbox_type == "read-only",
        f"resumed rollout turn_context.payload.sandbox_policy.type={sandbox_type!r} "
        "(expected 'read-only')",
    )

    results["c_write_blocked"] = (
        not probe_file_exists,
        f"probe file present={probe_file_exists} "
        "(expected absent — read-only must block the write)",
    )

    passed = all(ok for ok, _ in results.values())
    return passed, results


def normal_path_artifacts_ok(
    exit_code: int,
    out_text: str,
    session_before: str,
    session_after: str,
    jsonl_exists: bool,
) -> tuple[bool, dict[str, tuple[bool, str]]]:
    """Step-3 normal-path resume smoke check (pure; caller supplies observed
    values). Asserts exit 0 + non-empty output + unchanged session id + the
    JSONL was cleaned up (default behaviour, no --json on resume)."""
    checks: dict[str, tuple[bool, str]] = {
        "exit_zero": (exit_code == 0, f"exit_code={exit_code}"),
        "output_materialized": (bool(out_text.strip()), f"output_length={len(out_text)}"),
        "thread_unchanged": (
            bool(session_after) and session_before == session_after,
            f"before={session_before!r} after={session_after!r}",
        ),
        "jsonl_absent": (not jsonl_exists, f"jsonl_present={jsonl_exists}"),
    }
    passed = all(ok for ok, _ in checks.values())
    return passed, checks


def looks_like_env_failure(text: str) -> bool:
    """True if the combined stdout/stderr smells like an environment problem
    (auth/quota/network/local-codex/connected-MCP-OAuth) rather than a feature
    failure."""
    low = text.lower()
    return any(sig in low for sig in _ENV_SIGNATURES)


# ─── live orchestration (the manual pre-merge run; not exercised in CI) ─────


def _run(cmd: list[str], cwd: Path | str | None = None) -> subprocess.CompletedProcess:
    # stdin=DEVNULL: `codex exec --json` hangs reading stdin otherwise (F2); the
    # positional prompt is still honoured. Harmless for the non-json make calls.
    # env: strip KEEP_THREAD_JSONL so an exported value can't leak into the seed
    # recipe and spuriously fail the step-3 jsonl_absent gate (Tier-2 codex P2).
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else str(REPO_ROOT),
        env=subprocess_env(os.environ),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )


def _find_resumed_rollout(session_id: str) -> Path | None:
    """Locate the codex rollout FILE for a thread id: the most-recently-modified
    ~/.codex/sessions/**/rollout-*-<session_id>.jsonl (a resume re-uses the same
    thread_id, so the newest matching file holds the resumed turn)."""
    sessions = Path.home() / ".codex" / "sessions"
    if not sessions.is_dir():
        return None
    matches = sorted(
        sessions.rglob(f"rollout-*-{session_id}.jsonl"),
        key=lambda p: p.stat().st_mtime,
    )
    return matches[-1] if matches else None


def _print_gate_results(results: dict[str, tuple[bool, str]]) -> None:
    for name, (ok, detail) in results.items():
        sys.stderr.write(f"    [{'PASS' if ok else 'FAIL'}] {name}: {detail}\n")


def _fail(exit_code: int, headline: str, detail: str = "") -> int:
    sys.stderr.write(f"\n[V-13.5] {headline}\n")
    if detail:
        sys.stderr.write(detail.rstrip() + "\n")
    return exit_code


def main(argv: list[str]) -> int:
    plan_file = argv[0] if argv else DEFAULT_PLAN
    plan_path = REPO_ROOT / plan_file
    if not plan_path.exists():
        return _fail(
            EXIT_FAIL,
            f"inheritance/normal-path FAILED: plan file not found: {plan_file}",
            "Pass the active plan path as argv[1], or run from the repo root.",
        )

    key = compute_key(str(REPO_ROOT), str(plan_path))
    thread_file = Path(f"/tmp/plan-review-{key}.thread")
    thread_jsonl = Path(f"/tmp/plan-review-{key}.session.jsonl")
    # The probe writes INSIDE the repo workspace: under read-only the write is
    # blocked (absent → PASS); under a workspace-write regression it succeeds
    # (present → FAIL), which is exactly the safety hole we are gating against.
    probe_file = REPO_ROOT / "v13-5-probe.txt"
    resumed_jsonl = Path("/tmp/v13-5-resumed.jsonl")
    out_seed = Path("/tmp/v13-5-out-seed.md")
    out_resume = Path("/tmp/v13-5-out-resume.md")
    preflight_out = Path("/tmp/v13-5-preflight.txt")
    keep = os.environ.get("KEEP_V13_5_JSONL", "") == "1"

    def cleanup_on_success() -> None:
        if keep:
            return
        for p in (resumed_jsonl, probe_file, out_seed, out_resume, preflight_out):
            p.unlink(missing_ok=True)

    # 0. Preflight — is the environment actually usable?
    preflight = _run(
        [
            "scripts/run-with-clean-env.py",
            "--",
            "codex",
            "exec",
            "-C",
            str(REPO_ROOT),
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--output-last-message",
            str(preflight_out),
            "Reply with the single word: ok",
        ]
    )
    if preflight.returncode != 0:
        return _fail(
            EXIT_ENV,
            "FAIL CLASS: environment unavailable (codex preflight failed).",
            "-> RERUN in a valid environment; this is NOT a feature pass/fail.\n"
            + (preflight.stderr or preflight.stdout)[-1000:],
        )

    # 1. Clean slate.
    _run(make_command("loop-reset", str(plan_path)))
    for p in (probe_file, resumed_jsonl, out_seed, out_resume):
        p.unlink(missing_ok=True)
    if thread_file.exists() or thread_jsonl.exists():
        return _fail(
            EXIT_PROBE,
            "probe DID NOT RUN: loop-reset left thread state behind.",
            f"-> FILE A BUG. {thread_file} or {thread_jsonl} still present after loop-reset.",
        )

    # 2. Seed a continue session.
    seed = _run(
        make_command(
            "review-plan-by-codex",
            str(plan_path),
            THREAD_MODE="continue",
            ITERATION="1",
            PLAN_REVIEW_OUT_CODEX=str(out_seed),
        )
    )
    if seed.returncode != 0:
        combined = seed.stderr + seed.stdout
        if looks_like_env_failure(combined):
            return _fail(
                EXIT_ENV,
                "FAIL CLASS: environment unavailable (seed call failed on an env error).",
                "-> RERUN in a valid environment.\n" + combined[-1000:],
            )
        return _fail(
            EXIT_PROBE,
            "probe DID NOT RUN: the seed `review-plan-by-codex` call failed.",
            "-> FILE A BUG.\n" + combined[-1000:],
        )
    if not thread_file.exists():
        return _fail(
            EXIT_PROBE,
            "probe DID NOT RUN: seed did not create THREAD_FILE.",
            f"-> FILE A BUG. Expected {thread_file} to hold a session id.",
        )
    session_id = thread_file.read_text().strip()

    # 3. Normal-path resume smoke — the ACTUAL gated path (resume branch through
    #    run-with-clean-env.py, no --json).
    resume = _run(
        make_command(
            "review-plan-by-codex",
            str(plan_path),
            THREAD_MODE="continue",
            ITERATION="2",
            PLAN_REVIEW_OUT_CODEX=str(out_resume),
        )
    )
    if resume.returncode != 0 and looks_like_env_failure(resume.stderr + resume.stdout):
        return _fail(
            EXIT_ENV,
            "FAIL CLASS: environment unavailable (resume call failed on an env error).",
            "-> RERUN in a valid environment.\n" + (resume.stderr + resume.stdout)[-1000:],
        )
    session_after = thread_file.read_text().strip() if thread_file.exists() else ""
    out_text = out_resume.read_text() if out_resume.exists() else ""
    ok, checks = normal_path_artifacts_ok(
        resume.returncode, out_text, session_id, session_after, thread_jsonl.exists()
    )
    if not ok:
        sys.stderr.write("\n[V-13.5] inheritance/normal-path FAILED (normal-path resume smoke):\n")
        _print_gate_results(checks)
        sys.stderr.write("-> FILE A BUG; keep THREAD_MODE=fresh until fixed. Artifacts retained.\n")
        return EXIT_FAIL

    # 4. Read-only-ENFORCED probe: resume with `-c sandbox_mode=read-only --json`
    #    + a write-attempting prompt, FROM THE REPO. resume does NOT take
    #    -C/--sandbox (CLI-rejected); read-only is forced via the `-c` override.
    probe_file.unlink(missing_ok=True)
    probe = _run(
        resume_probe_command(str(REPO_ROOT), session_id, str(probe_file)),
        cwd=REPO_ROOT,
    )
    resumed_jsonl.write_text(probe.stdout)
    if probe.returncode != 0:
        combined = probe.stderr + probe.stdout
        if looks_like_env_failure(combined):
            return _fail(
                EXIT_ENV,
                "FAIL CLASS: environment unavailable (read-only probe failed on an env error).",
                "-> RERUN in a valid environment. Artifacts retained.\n" + combined[-1000:],
            )
        return _fail(
            EXIT_PROBE,
            "probe DID NOT RUN: `codex exec resume -c sandbox_mode=read-only --json` failed.",
            "-> FILE A BUG. Artifacts retained.\n" + combined[-1000:],
        )

    stream_events = parse_jsonl(resumed_jsonl.read_text())
    rollout_path = _find_resumed_rollout(session_id)
    if rollout_path is None:
        return _fail(
            EXIT_FAIL,
            "inheritance/normal-path FAILED: could not locate the resumed rollout file.",
            f"-> Looked for rollout-*-{session_id}.jsonl under ~/.codex/sessions "
            "(needed for the sandbox_policy gate). The resume itself SUCCEEDED (exit 0), "
            "so this is more likely a harness/sessions-path mismatch (e.g. a non-default "
            "CODEX_HOME) than a resume-branch regression — check the rollout location "
            "before filing a bug. Artifacts retained.",
        )
    rollout_events = parse_jsonl(rollout_path.read_text())
    passed, gates = check_gates(stream_events, rollout_events, session_id, probe_file.exists())
    if not passed:
        sys.stderr.write("\n[V-13.5] inheritance/normal-path FAILED (read-only-ENFORCED probe):\n")
        _print_gate_results(gates)
        sys.stderr.write(
            f"    (resumed rollout file: {rollout_path})\n"
            "-> FILE A BUG; the resume branch is NOT read-only-enforced. "
            "Keep THREAD_MODE=fresh until fixed. Artifacts retained for debugging.\n"
        )
        return EXIT_FAIL

    cleanup_on_success()
    sys.stdout.write(
        "\n[V-13.5] PASS — codex exec resume continues the same thread id, enforces "
        "read-only (write blocked + resumed rollout sandbox_policy.type == 'read-only'), "
        "and the normal resume path materialises output.\n"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
