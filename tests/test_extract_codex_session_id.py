"""Unit tests for scripts/extract-codex-session-id.py.

The extractor reads a `codex exec --json` JSONL STREAM and prints the resumable
id at `thread.started.thread_id` (verified live 2026-05-30) from the first
`thread.started` event. Contract (per the PR-1 Bucket F plan, Scope A, as
corrected 2026-05-30):
  - JSONL WITH a thread.started event → prints the thread_id to stdout, exit 0
  - JSONL WITHOUT a thread.started event → non-zero exit, nothing on stdout

NOTE: the fixture is `codex-json-stream.jsonl` (the --json STDOUT *stream*), NOT
`codex-json-session.jsonl` (the rollout FILE — session_meta/turn_context schema).
The earlier extractor keyed on session_meta.payload.id, which is the rollout
file's field, not the stream's — the live gate falsified that.

Subprocess-based (like test_env_scrubber.py): the script has a hyphenated
filename and ships as an executable CLI, so we exercise the real exit-code /
stdout contract rather than importing the module.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
EXTRACTOR = SKILL_ROOT / "scripts" / "extract-codex-session-id.py"
COMMITTED_FIXTURE = SKILL_ROOT / "tests" / "fixtures" / "codex-json-stream.jsonl"
# The thread.started.thread_id pinned in the committed --json stream fixture.
FIXTURE_SESSION_ID = "00000000-0000-7000-8000-000000000001"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(EXTRACTOR), *args],
        capture_output=True,
        text=True,
    )


def test_extracts_thread_id_from_committed_stream_fixture():
    result = _run(str(COMMITTED_FIXTURE))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == FIXTURE_SESSION_ID


def test_jsonl_without_thread_started_exits_nonzero_and_prints_nothing(tmp_path):
    jsonl = tmp_path / "no-thread-started.jsonl"
    jsonl.write_text(
        '{"type":"turn.started"}\n'
        '{"type":"turn.completed","usage":{"cached_input_tokens":0}}\n'
    )
    result = _run(str(jsonl))
    assert result.returncode != 0
    assert result.stdout == "", f"expected no stdout, got {result.stdout!r}"


def test_rollout_session_meta_is_not_accepted(tmp_path):
    """A rollout-FILE line (session_meta.payload.id) must NOT be mistaken for the
    stream's thread.started.thread_id — locks the schema fix that the live gate
    forced (the old extractor would have returned this id)."""
    jsonl = tmp_path / "rollout-shaped.jsonl"
    jsonl.write_text(
        '{"type":"session_meta","payload":{"id":"00000000-0000-7000-8000-000000000abc"}}\n'
        '{"type":"turn_context","payload":{"cwd":"/x","sandbox_policy":{"type":"read-only"}}}\n'
    )
    result = _run(str(jsonl))
    assert result.returncode != 0
    assert result.stdout == ""


def test_missing_file_exits_nonzero(tmp_path):
    result = _run(str(tmp_path / "does-not-exist.jsonl"))
    assert result.returncode != 0
    assert result.stdout == ""


def test_no_args_exits_nonzero():
    result = _run()
    assert result.returncode != 0
    assert result.stdout == ""


def test_skips_malformed_lines_before_thread_started(tmp_path):
    """A garbled line ahead of a well-formed thread.started must not abort the
    scan — the valid thread_id is still extracted."""
    jsonl = tmp_path / "mixed.jsonl"
    jsonl.write_text(
        "this is not json\n"
        "\n"
        '{"type":"thread.started","thread_id":"11111111-2222-7333-8444-555555555555"}\n'
    )
    result = _run(str(jsonl))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "11111111-2222-7333-8444-555555555555"


def test_first_thread_started_wins(tmp_path):
    """If two thread.started events appear, the FIRST thread_id is returned (the
    seed thread), not a later one."""
    jsonl = tmp_path / "two-started.jsonl"
    jsonl.write_text(
        '{"type":"thread.started","thread_id":"aaaaaaaa-0000-7000-8000-000000000001"}\n'
        '{"type":"thread.started","thread_id":"bbbbbbbb-0000-7000-8000-000000000002"}\n'
    )
    result = _run(str(jsonl))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "aaaaaaaa-0000-7000-8000-000000000001"


def test_thread_started_without_thread_id_is_treated_as_missing(tmp_path):
    """A thread.started event whose body lacks a string thread_id is not a valid
    seed — fall through to non-zero exit, nothing on stdout."""
    jsonl = tmp_path / "started-no-id.jsonl"
    jsonl.write_text(
        '{"type":"thread.started"}\n'
        '{"type":"thread.started","thread_id":null}\n'
    )
    result = _run(str(jsonl))
    assert result.returncode != 0
    assert result.stdout == ""


def test_non_dict_json_line_is_skipped(tmp_path):
    """A well-formed-but-non-object JSON line (e.g. a bare array) must be
    skipped, not crash the scan — locks the `isinstance(event, dict)` guard
    so a future refactor that drops it fails loudly."""
    jsonl = tmp_path / "non-dict-line.jsonl"
    jsonl.write_text(
        '["thread.started"]\n'
        '{"type":"thread.started","thread_id":"22222222-0000-7000-8000-000000000003"}\n'
    )
    result = _run(str(jsonl))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "22222222-0000-7000-8000-000000000003"


def test_directory_argument_exits_nonzero(tmp_path):
    """A directory path passes Path.exists() but read_text() raises
    IsADirectoryError (an OSError) — the read guard must turn that into a
    clean non-zero exit with empty stdout, not a traceback."""
    result = _run(str(tmp_path))
    assert result.returncode != 0
    assert result.stdout == ""
