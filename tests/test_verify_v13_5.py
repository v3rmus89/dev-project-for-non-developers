"""Unit tests for scripts/verify-v13-5.py's PURE functions.

The V-13.5 verifier is a repo-internal live pre-merge gate. Its live codex/make
calls are exercised only by the manual `python3 scripts/verify-v13-5.py` run —
NEVER in CI. These tests cover the pure logic with fixtures:
  - make_command (PLAN_FILE= always present — iter-8 FN1)
  - resume_probe_command (the SAFETY core: `-c sandbox_mode=read-only` present,
    --sandbox/-C/--color/--skip-git-repo-check absent)
  - compute_key (matches the Makefile KEY formula)
  - parse_jsonl / thread_id_of (stream) / sandbox_type_of (rollout file)
  - check_gates (read-only-ENFORCED, 3 gates: PASS + each FAIL variant; the OLD
    cwd-inheritance gate is dropped)
  - normal_path_artifacts_ok (PASS + FAIL variants)
  - looks_like_env_failure (env vs feature classification)

TWO fixtures, two schemas (the live gate falsified an earlier conflation):
  - codex-json-stream.jsonl  — the `codex exec --json` STDOUT stream
    (thread.started.thread_id); used by thread_id_of / gate (a).
  - codex-json-session.jsonl — the codex rollout FILE
    (turn_context.payload.sandbox_policy.type); used by sandbox_type_of / gate (b).

The script's filename is hyphenated, so it is loaded via importlib (the
`if __name__ == "__main__"` guard keeps main() from running on import).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
STREAM_FIXTURE = SKILL_ROOT / "tests" / "fixtures" / "codex-json-stream.jsonl"
ROLLOUT_FIXTURE = SKILL_ROOT / "tests" / "fixtures" / "codex-json-session.jsonl"
# thread.started.thread_id in the stream fixture == session_meta.payload.id in the
# rollout fixture (codex re-uses the same id on resume — that's the continuity).
FIXTURE_SESSION_ID = "00000000-0000-7000-8000-000000000001"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_v13_5", SKILL_ROOT / "scripts" / "verify-v13-5.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


verify = _load_verifier()


# ── make_command: PLAN_FILE= must always be present (iter-8 FN1) ────────────


@pytest.mark.parametrize(
    "target,make_vars",
    [
        ("loop-reset", {}),
        ("review-plan-by-codex", {"THREAD_MODE": "continue", "ITERATION": "1"}),
        (
            "review-plan-by-codex",
            {"THREAD_MODE": "continue", "ITERATION": "2", "PLAN_REVIEW_OUT_CODEX": "/tmp/o.md"},
        ),
    ],
)
def test_make_command_always_includes_plan_file(target, make_vars):
    cmd = verify.make_command(target, "docs/plans/x.md", **make_vars)
    assert cmd[0] == "make"
    assert cmd[1] == target
    assert "PLAN_FILE=docs/plans/x.md" in cmd, (
        f"PLAN_FILE= missing for {target} — both make targets guard on it (iter-8 FN1)"
    )
    for key, value in make_vars.items():
        assert f"{key}={value}" in cmd, f"{key}={value} missing from constructed command"


def test_make_command_plan_file_immediately_after_target():
    """PLAN_FILE should be the first var (stable, readable invocations)."""
    cmd = verify.make_command("review-plan-by-codex", "p.md", THREAD_MODE="continue")
    assert cmd[:3] == ["make", "review-plan-by-codex", "PLAN_FILE=p.md"]


# ── resume_probe_command: the SAFETY core (must force read-only) ────────────


def test_resume_probe_command_forces_read_only():
    """The probe MUST carry `-c sandbox_mode=read-only`, adjacency-checked. Dropping
    it would let the probe resume in workspace-write and silently pass gate (c) —
    the exact failure the live gate exists to catch (F3)."""
    cmd = verify.resume_probe_command("/repo", "SID-123", "/repo/v13-5-probe.txt")
    assert "resume" in cmd
    assert "SID-123" in cmd
    assert "-c" in cmd and "sandbox_mode=read-only" in cmd
    assert cmd[cmd.index("-c") + 1] == "sandbox_mode=read-only", (
        "`-c` must be immediately followed by `sandbox_mode=read-only`"
    )
    assert "--json" in cmd, "probe needs --json to capture the stream for the thread-id gate"


def test_resume_probe_command_omits_resume_rejected_flags():
    """`codex exec resume` CLI-rejects --sandbox/-C/--color, and from the repo we do
    NOT pass --skip-git-repo-check (that was the OLD /tmp probe)."""
    cmd = verify.resume_probe_command("/repo", "SID-123", "/repo/v13-5-probe.txt")
    for rejected in ("--sandbox", "-C", "--color", "--skip-git-repo-check"):
        assert rejected not in cmd, f"resume probe must NOT pass {rejected}"


def test_resume_probe_command_prompt_targets_the_probe_file():
    cmd = verify.resume_probe_command("/repo", "SID-123", "/repo/v13-5-probe.txt")
    assert any("/repo/v13-5-probe.txt" in part for part in cmd), (
        "the write-probe prompt must reference the probe file path"
    )
    assert cmd[:2] == ["/repo/scripts/run-with-clean-env.py", "--"], (
        "probe must run through the clean-env wrapper"
    )


# ── compute_key matches the Makefile KEY formula ────────────────────────────


def test_compute_key_matches_sha256_formula(tmp_path):
    import hashlib

    repo = tmp_path / "repo"
    repo.mkdir()
    plan = repo / "plan.md"
    plan.write_text("x")
    expected = hashlib.sha256(
        (os.path.realpath(str(repo)) + ":" + os.path.realpath(str(plan))).encode()
    ).hexdigest()[:12]
    assert verify.compute_key(str(repo), str(plan)) == expected
    assert len(verify.compute_key(str(repo), str(plan))) == 12


# ── JSONL parsing ───────────────────────────────────────────────────────────


def test_parse_jsonl_skips_blank_and_garbled_lines():
    events = verify.parse_jsonl(
        '{"type":"thread.started","thread_id":"abc"}\n'
        "\n"
        "not json\n"
        '["not","an","object"]\n'
        '{"type":"turn.completed","usage":{"cached_input_tokens":0}}\n'
    )
    assert [e["type"] for e in events] == ["thread.started", "turn.completed"]


# ── thread_id_of: reads the STREAM (thread.started.thread_id) ────────────────


def test_thread_id_of_committed_stream_fixture():
    events = verify.parse_jsonl(STREAM_FIXTURE.read_text())
    assert verify.thread_id_of(events) == FIXTURE_SESSION_ID


def test_thread_id_of_first_wins_and_ignores_non_string():
    events = [
        {"type": "thread.started"},  # no thread_id → skip
        {"type": "thread.started", "thread_id": None},  # non-string → skip
        {"type": "thread.started", "thread_id": "real-id-1"},
        {"type": "thread.started", "thread_id": "real-id-2"},
    ]
    assert verify.thread_id_of(events) == "real-id-1"


def test_thread_id_of_returns_none_when_absent():
    events = [{"type": "turn.completed", "usage": {}}]
    assert verify.thread_id_of(events) is None


def test_thread_id_of_ignores_rollout_session_meta():
    """session_meta is the rollout-file field; thread_id_of must NOT read it."""
    events = [{"type": "session_meta", "payload": {"id": "rollout-id"}}]
    assert verify.thread_id_of(events) is None


# ── sandbox_type_of: reads the ROLLOUT FILE (turn_context.sandbox_policy) ────


def test_sandbox_type_of_committed_rollout_fixture():
    events = verify.parse_jsonl(ROLLOUT_FIXTURE.read_text())
    assert verify.sandbox_type_of(events) == "read-only"


def test_sandbox_type_of_returns_last_turn_context():
    """LAST turn_context wins — so a resumed turn that flipped to workspace-write is
    caught even when the seed turn was read-only."""
    events = [
        {"type": "turn_context", "payload": {"sandbox_policy": {"type": "read-only"}}},
        {"type": "turn_context", "payload": {"sandbox_policy": {"type": "workspace-write"}}},
    ]
    assert verify.sandbox_type_of(events) == "workspace-write"


def test_sandbox_type_of_returns_none_when_absent():
    events = [{"type": "thread.started", "thread_id": "x"}]
    assert verify.sandbox_type_of(events) is None


# ── check_gates: read-only-ENFORCED, 3 gates (PASS + each FAIL variant) ──────


def _pass_inputs():
    stream = verify.parse_jsonl(STREAM_FIXTURE.read_text())
    rollout = verify.parse_jsonl(ROLLOUT_FIXTURE.read_text())
    return stream, rollout


def test_gates_pass_on_committed_fixtures():
    stream, rollout = _pass_inputs()
    passed, results = verify.check_gates(
        stream, rollout, FIXTURE_SESSION_ID, probe_file_exists=False
    )
    assert passed, results
    assert set(results) == {"a_thread_id_continuity", "b_sandbox_read_only", "c_write_blocked"}, (
        "exactly 3 gates — the OLD cwd-inheritance gate must be dropped"
    )


def test_gates_fail_on_thread_id_mismatch():
    stream, rollout = _pass_inputs()
    passed, results = verify.check_gates(
        stream, rollout, "11111111-1111-7111-8111-111111111111", probe_file_exists=False
    )
    assert not passed
    assert not results["a_thread_id_continuity"][0]
    assert results["b_sandbox_read_only"][0]
    assert results["c_write_blocked"][0]


def test_gates_fail_on_non_read_only_sandbox():
    """A resumed session that ran workspace-write (the F3 hole) must trip gate (b)."""
    stream, _ = _pass_inputs()
    rollout = [
        {"type": "turn_context", "payload": {"sandbox_policy": {"type": "workspace-write"}}},
    ]
    passed, results = verify.check_gates(
        stream, rollout, FIXTURE_SESSION_ID, probe_file_exists=False
    )
    assert not passed
    assert not results["b_sandbox_read_only"][0]


def test_gates_fail_when_probe_file_written():
    """If the probe write succeeded, read-only was NOT enforced — gate (c) trips."""
    stream, rollout = _pass_inputs()
    passed, results = verify.check_gates(
        stream, rollout, FIXTURE_SESSION_ID, probe_file_exists=True
    )
    assert not passed
    assert not results["c_write_blocked"][0]


def test_gates_no_cwd_gate_present():
    """Regression-lock: the dropped cwd-inheritance gate must not reappear."""
    stream, rollout = _pass_inputs()
    _, results = verify.check_gates(stream, rollout, FIXTURE_SESSION_ID, probe_file_exists=False)
    assert not any("cwd" in name for name in results), "cwd gate was dropped (correction item 4)"


# ── normal-path resume smoke check ──────────────────────────────────────────


def test_normal_path_artifacts_ok_pass():
    passed, checks = verify.normal_path_artifacts_ok(
        exit_code=0,
        out_text="CANNED RESUME REVIEW\n",
        session_before=FIXTURE_SESSION_ID,
        session_after=FIXTURE_SESSION_ID,
        jsonl_exists=False,
    )
    assert passed, checks


@pytest.mark.parametrize(
    "kwargs,failing_key",
    [
        (
            dict(
                exit_code=1, out_text="x", session_before="a", session_after="a", jsonl_exists=False
            ),
            "exit_zero",
        ),
        (
            dict(
                exit_code=0,
                out_text="   ",
                session_before="a",
                session_after="a",
                jsonl_exists=False,
            ),
            "output_materialized",
        ),
        (
            dict(
                exit_code=0, out_text="x", session_before="a", session_after="b", jsonl_exists=False
            ),
            "thread_unchanged",
        ),
        (
            dict(
                exit_code=0, out_text="x", session_before="", session_after="", jsonl_exists=False
            ),
            "thread_unchanged",
        ),
        (
            dict(
                exit_code=0, out_text="x", session_before="a", session_after="a", jsonl_exists=True
            ),
            "jsonl_absent",
        ),
    ],
)
def test_normal_path_artifacts_fail_variants(kwargs, failing_key):
    passed, checks = verify.normal_path_artifacts_ok(**kwargs)
    assert not passed
    assert not checks[failing_key][0], f"expected {failing_key} to fail"


# ── env-vs-feature failure classification ───────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "Error: Operation not permitted (os error 1)",
        "not logged in — run `codex login`",
        "HTTP 401 Unauthorized",
        "rate limit exceeded",
        "connection refused",
        "request timed out",
        # Connected-MCP-server OAuth failures, observed verbatim on the first
        # live gate run (an expired Meta-ads MCP token aborted codex):
        'AuthRequired(AuthRequiredError { www_authenticate_header: "Bearer ..." })',
        'Auth(TokenRefreshFailed("...invalid_grant: The provided authorization grant ... '
        'is invalid, expired, revoked..."))',
    ],
)
def test_looks_like_env_failure_true(text):
    assert verify.looks_like_env_failure(text)


@pytest.mark.parametrize(
    "text",
    [
        "AssertionError: THREAD_FILE not created",
        "no rollout found for thread id deadbeef",
        "make: *** [review-plan-by-codex] Error 1",
        "",
        # False-positive guards (Tier-1 commit-5 FN1): a real feature failure
        # whose captured output cats review prose containing bare words like
        # "network"/"connection"/"quota"/"403" must NOT be misclassified as an
        # environment problem — the signatures are specific phrases, not bare
        # words (the plan under review literally contains these words).
        "the review discusses the network layer and connection pooling at length",
        "imp-2: the plan's error-class prose lists auth / quota / network failures",
        "AssertionError: expected HTTP 403 in the response body",
    ],
)
def test_looks_like_env_failure_false(text):
    assert not verify.looks_like_env_failure(text)
