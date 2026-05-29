"""Env-scrubber tests for scripts/run-with-clean-env.py.

Asserts prefix scrubbing for CLAUDE_CODE_* and CODEX_* env vars.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRUBBER = SKILL_ROOT / "scripts" / "run-with-clean-env.py"


def _env_with_prefix_vars():
    env = os.environ.copy()
    env["CLAUDE_CODE_SESSION_ID"] = "should-be-stripped"
    env["CLAUDE_CODE_TOKEN"] = "secret"
    env["CODEX_API_KEY"] = "stripped"
    env["CODEX_USER_ID"] = "stripped"
    env["UNRELATED_VAR"] = "kept"
    env["MAKEFLAGS"] = "should-also-be-dropped"
    env["PLAN_FILE"] = "docs/plans/x.md"
    env["REVIEW_COMMIT_SHA"] = "abc1234"
    env["REVIEW_COMMIT_OUT_CODEX"] = "/tmp/x-codex.md"
    env["REVIEW_COMMIT_OUT_CLAUDE"] = "/tmp/x-claude.md"
    env["PLAN_CONSISTENCY_OUT"] = "/tmp/x-consistency.md"
    # Bucket F thread-continuation Make vars (iter-7 FN4): must not leak into
    # the Codex subprocess env.
    env["THREAD_MODE"] = "continue"
    env["THREAD_FILE"] = "/tmp/plan-review-x.thread"
    env["THREAD_JSONL_FILE"] = "/tmp/plan-review-x.session.jsonl"
    env["KEEP_THREAD_JSONL"] = "1"
    return env


def test_strips_claude_code_and_codex_prefixes(tmp_path):
    # Use a Python child that dumps its env so we can assert
    dump_script = tmp_path / "dump.py"
    dump_script.write_text(
        "import json, os, sys\njson.dump({k: v for k, v in os.environ.items()}, sys.stdout)\n"
    )
    result = subprocess.run(
        [str(SCRUBBER), "--", sys.executable, str(dump_script)],
        env=_env_with_prefix_vars(),
        capture_output=True,
        text=True,
        check=True,
    )
    child_env = json.loads(result.stdout)
    for stripped in [
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_TOKEN",
        "CODEX_API_KEY",
        "CODEX_USER_ID",
        "MAKEFLAGS",
        "PLAN_FILE",
        "REVIEW_COMMIT_SHA",
        "REVIEW_COMMIT_OUT_CODEX",
        "REVIEW_COMMIT_OUT_CLAUDE",
        "PLAN_CONSISTENCY_OUT",
        "THREAD_MODE",
        "THREAD_FILE",
        "THREAD_JSONL_FILE",
        "KEEP_THREAD_JSONL",
    ]:
        assert stripped not in child_env, f"{stripped} survived scrubbing"
    assert child_env.get("UNRELATED_VAR") == "kept"


def test_keep_flags_preserve_prefix_vars(tmp_path):
    dump_script = tmp_path / "dump.py"
    dump_script.write_text(
        "import json, os, sys\njson.dump({k: v for k, v in os.environ.items()}, sys.stdout)\n"
    )
    result = subprocess.run(
        [
            str(SCRUBBER),
            "--keep-claude-code",
            "--keep-codex",
            "--",
            sys.executable,
            str(dump_script),
        ],
        env=_env_with_prefix_vars(),
        capture_output=True,
        text=True,
        check=True,
    )
    child_env = json.loads(result.stdout)
    assert child_env.get("CLAUDE_CODE_SESSION_ID") == "should-be-stripped"
    assert child_env.get("CODEX_API_KEY") == "stripped"
    # But Make-internal exact-match drops still apply
    assert "MAKEFLAGS" not in child_env


def test_missing_separator_exits_2():
    result = subprocess.run(
        [str(SCRUBBER), "echo", "no-separator"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "'--'" in result.stderr or "separator" in result.stderr


def test_no_command_after_separator_exits_2():
    result = subprocess.run([str(SCRUBBER), "--"], capture_output=True, text=True)
    assert result.returncode == 2
