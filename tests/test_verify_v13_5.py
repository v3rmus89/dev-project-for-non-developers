"""Unit tests for scripts/verify-v13-5.py's PURE functions.

The V-13.5 verifier is a repo-internal live pre-merge gate. Its live codex/make
calls are exercised only by the manual `python3 scripts/verify-v13-5.py` run —
NEVER in CI. These tests cover the pure logic with fixtures:
  - make_command (PLAN_FILE= always present — iter-8 FN1)
  - compute_key (matches the Makefile KEY formula)
  - parse_jsonl / session_id_of / first_turn_context_payload
  - check_four_gates (PASS + each gate's FAIL variant)
  - normal_path_artifacts_ok (PASS + FAIL variants)
  - looks_like_env_failure (env vs feature classification)

The script's filename is hyphenated, so it is loaded via importlib (the
`if __name__ == "__main__"` guard keeps main() from running on import).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
COMMITTED_FIXTURE = SKILL_ROOT / "tests" / "fixtures" / "codex-json-session.jsonl"
# Values pinned in the committed V-13 fixture.
FIXTURE_SESSION_ID = "00000000-0000-7000-8000-000000000001"
FIXTURE_CWD = "/workspace/project"


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
        '{"type":"session_meta","payload":{"id":"abc"}}\n'
        "\n"
        "not json\n"
        '["not","an","object"]\n'
        '{"type":"turn_context","payload":{"cwd":"/x"}}\n'
    )
    assert [e["type"] for e in events] == ["session_meta", "turn_context"]


def test_session_id_of_committed_fixture():
    events = verify.parse_jsonl(COMMITTED_FIXTURE.read_text())
    assert verify.session_id_of(events) == FIXTURE_SESSION_ID


def test_first_turn_context_payload_committed_fixture():
    events = verify.parse_jsonl(COMMITTED_FIXTURE.read_text())
    tc = verify.first_turn_context_payload(events)
    assert tc is not None
    assert tc["cwd"] == FIXTURE_CWD
    assert tc["sandbox_policy"]["type"] == "read-only"


# ── 4-gate check: PASS + each FAIL variant ──────────────────────────────────


def _fixture_events():
    return verify.parse_jsonl(COMMITTED_FIXTURE.read_text())


def test_four_gates_pass_on_committed_fixture():
    passed, results = verify.check_four_gates(
        _fixture_events(), FIXTURE_SESSION_ID, FIXTURE_CWD, probe_file_exists=False
    )
    assert passed, results
    assert all(ok for ok, _ in results.values())


def test_four_gates_fail_on_session_id_mismatch():
    passed, results = verify.check_four_gates(
        _fixture_events(), "11111111-1111-7111-8111-111111111111", FIXTURE_CWD, False
    )
    assert not passed
    assert not results["a_uuid_continuity"][0]
    # The other three gates still pass — only (a) trips.
    assert results["b_sandbox_read_only"][0]
    assert results["c_probe_file_absent"][0]
    assert results["d_cwd_inheritance"][0]


def test_four_gates_fail_on_non_read_only_sandbox():
    # Build events directly (no JSONL round-trip needed): a resumed session that
    # did NOT inherit the read-only sandbox.
    events = [
        {"type": "session_meta", "payload": {"id": FIXTURE_SESSION_ID}},
        {
            "type": "turn_context",
            "payload": {"cwd": FIXTURE_CWD, "sandbox_policy": {"type": "danger-full-access"}},
        },
    ]
    passed, results = verify.check_four_gates(events, FIXTURE_SESSION_ID, FIXTURE_CWD, False)
    assert not passed
    assert not results["b_sandbox_read_only"][0]


def test_four_gates_fail_when_probe_file_written():
    passed, results = verify.check_four_gates(
        _fixture_events(), FIXTURE_SESSION_ID, FIXTURE_CWD, probe_file_exists=True
    )
    assert not passed
    assert not results["c_probe_file_absent"][0]


def test_four_gates_fail_on_cwd_mismatch():
    """The /tmp-contrast condition: a resumed session whose cwd is the caller's
    /tmp (not the inherited repo root) must fail gate (d)."""
    passed, results = verify.check_four_gates(
        _fixture_events(), FIXTURE_SESSION_ID, "/some/other/repo", probe_file_exists=False
    )
    assert not passed
    assert not results["d_cwd_inheritance"][0]


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
