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
    permitted"). The gate has NOT actually tested the feature — RERUN in a
    valid environment. Do not treat as a feature pass OR fail.
  - probe DID NOT RUN (exit 3): a seed/resume command failed for a feature
    reason (e.g. the seed never produced THREAD_FILE). FILE A BUG and keep
    THREAD_MODE=fresh (the safe default) until fixed.
  - inheritance/normal-path FAILED (exit 4): an assertion failed — the
    resumed session did not inherit the session id / read-only sandbox /
    cwd, or the normal resume path did not materialise output. The
    THREAD_MODE=continue branch is unsafe — FILE A BUG and keep
    THREAD_MODE=fresh until fixed.

What it does (live, ~3 real codex calls):
  0. Preflight — confirm codex is reachable + authenticated.
  1. `make loop-reset PLAN_FILE=<plan>` → assert clean preconditions.
  2. Seed: `make review-plan-by-codex PLAN_FILE=<plan> THREAD_MODE=continue
     ITERATION=1` → assert THREAD_FILE now holds a session id.
  3. Normal-path resume smoke (THE gated path): `make review-plan-by-codex
     ... THREAD_MODE=continue ITERATION=2` (resume branch THROUGH
     run-with-clean-env.py, no --json). Assert exit 0 + output materialised
     + THREAD_FILE unchanged + JSONL cleaned up.
  4. Inheritance probe (4 gates): from /tmp, `codex exec resume <id>
     --skip-git-repo-check --json` and assert (a) session-id continuity,
     (b) turn_context.payload.sandbox_policy.type == "read-only",
     (c) the probe file was NOT written, (d) cwd inherited (== repo root,
     NOT /tmp).
  5. Cleanup: on PASS, remove the probe/JSONL artifacts; on FAILURE retain
     them for debugging; KEEP_V13_5_JSONL=1 retains regardless (the
     deliberate inverse of KEEP_THREAD_JSONL's always-remove-on-failure).

The PURE functions below (make_command, compute_key, parse_jsonl,
check_four_gates, normal_path_artifacts_ok, looks_like_env_failure) are
unit-tested in tests/test_verify_v13_5.py with fixtures — no live calls in CI.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
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


def parse_jsonl(text: str) -> list[dict]:
    """Parse a codex `--json` stream into a list of dict events; skip blank or
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


def session_id_of(events: list[dict]) -> str | None:
    """First session_meta.payload.id (a string), else None."""
    for e in events:
        if e.get("type") == "session_meta" and isinstance(e.get("payload"), dict):
            sid = e["payload"].get("id")
            if isinstance(sid, str) and sid:
                return sid
    return None


def first_turn_context_payload(events: list[dict]) -> dict | None:
    """Payload of the first turn_context event, else None."""
    for e in events:
        if e.get("type") == "turn_context" and isinstance(e.get("payload"), dict):
            return e["payload"]
    return None


def check_four_gates(
    events: list[dict],
    expected_session_id: str,
    expected_cwd: str,
    probe_file_exists: bool,
) -> tuple[bool, dict[str, tuple[bool, str]]]:
    """The V-13.5 4-gate check on a RESUMED-session JSONL event list.

    `probe_file_exists` is supplied by the caller so this stays pure (the
    filesystem check lives in the orchestrator). Returns
    (passed, {gate: (ok, detail)}).
    """
    results: dict[str, tuple[bool, str]] = {}

    sid = session_id_of(events)
    results["a_uuid_continuity"] = (
        sid == expected_session_id,
        f"session_meta.payload.id={sid!r} (expected {expected_session_id!r})",
    )

    tc = first_turn_context_payload(events) or {}
    sandbox_type = (tc.get("sandbox_policy") or {}).get("type")
    results["b_sandbox_read_only"] = (
        sandbox_type == "read-only",
        f"turn_context.payload.sandbox_policy.type={sandbox_type!r} (expected 'read-only')",
    )

    results["c_probe_file_absent"] = (
        not probe_file_exists,
        f"probe file present={probe_file_exists} (expected absent)",
    )

    cwd = tc.get("cwd")
    results["d_cwd_inheritance"] = (
        cwd == expected_cwd,
        f"turn_context.payload.cwd={cwd!r} (expected {expected_cwd!r}, NOT the /tmp caller cwd)",
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
    (auth/quota/network/local-codex) rather than a feature failure."""
    low = text.lower()
    return any(sig in low for sig in _ENV_SIGNATURES)


# ─── live orchestration (the manual pre-merge run; not exercised in CI) ─────


def _run(cmd: list[str], cwd: Path | str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


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
    probe_file = Path("/tmp/v13-5-probe.txt")
    resumed_jsonl = Path("/tmp/v13-5-resumed.jsonl")
    out_seed = Path("/tmp/v13-5-out-seed.md")
    out_resume = Path("/tmp/v13-5-out-resume.md")
    expected_cwd = os.path.realpath(str(REPO_ROOT))
    keep = os.environ.get("KEEP_V13_5_JSONL", "") == "1"

    def cleanup_on_success() -> None:
        if keep:
            return
        for p in (resumed_jsonl, probe_file, out_seed, out_resume):
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
            "/tmp/v13-5-preflight.txt",
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

    # 4. Inheritance probe from /tmp (the cwd-contrast condition). Direct
    #    `codex exec resume --json` through the clean-env wrapper so CODEX_*
    #    config can't perturb the inheritance check. --skip-git-repo-check is
    #    required because /tmp is not a git repo. resume does NOT take
    #    -C/--sandbox (it inherits them; passing them is CLI-rejected).
    probe_file.unlink(missing_ok=True)
    probe_prompt = (
        f"Use a shell command to create the file {probe_file} containing the text "
        "v13-5-probe, then tell me whether the write succeeded."
    )
    probe = _run(
        [
            "scripts/run-with-clean-env.py",
            "--",
            "codex",
            "exec",
            "resume",
            session_id,
            "--skip-git-repo-check",
            "--json",
            probe_prompt,
        ],
        cwd="/tmp",
    )
    resumed_jsonl.write_text(probe.stdout)
    if probe.returncode != 0:
        combined = probe.stderr + probe.stdout
        if looks_like_env_failure(combined):
            return _fail(
                EXIT_ENV,
                "FAIL CLASS: environment unavailable (inheritance probe failed on an env error).",
                "-> RERUN in a valid environment. Artifacts retained.\n" + combined[-1000:],
            )
        return _fail(
            EXIT_PROBE,
            "probe DID NOT RUN: `codex exec resume --json` from /tmp failed.",
            "-> FILE A BUG. Artifacts retained.\n" + combined[-1000:],
        )

    events = parse_jsonl(resumed_jsonl.read_text())
    passed, gates = check_four_gates(events, session_id, expected_cwd, probe_file.exists())
    if not passed:
        sys.stderr.write("\n[V-13.5] inheritance/normal-path FAILED (4-gate inheritance probe):\n")
        _print_gate_results(gates)
        sys.stderr.write(
            "-> FILE A BUG; the resume branch does NOT inherit the seed's session. "
            "Keep THREAD_MODE=fresh until fixed. Artifacts retained for debugging.\n"
        )
        return EXIT_FAIL

    cleanup_on_success()
    sys.stdout.write(
        "\n[V-13.5] PASS — codex exec resume inherits the session id + read-only "
        "sandbox + cwd, and the normal resume path materialises output.\n"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
