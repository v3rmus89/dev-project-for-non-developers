"""Unit tests for scripts/extract-codex-session-id.py.

The extractor reads a `codex exec --json` JSONL stream and prints the session
ID at `session_meta.payload.id` (V-13 confirmed field path) from the first
`session_meta` event. Contract (per the PR-1 Bucket F plan, Scope A):
  - JSONL WITH a session_meta event → prints the ID to stdout, exit 0
  - JSONL WITHOUT a session_meta event → non-zero exit, nothing on stdout

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
COMMITTED_FIXTURE = SKILL_ROOT / "tests" / "fixtures" / "codex-json-session.jsonl"
# The session_meta.payload.id pinned in the committed V-13 fixture.
FIXTURE_SESSION_ID = "00000000-0000-7000-8000-000000000001"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(EXTRACTOR), *args],
        capture_output=True,
        text=True,
    )


def test_extracts_session_id_from_committed_fixture():
    result = _run(str(COMMITTED_FIXTURE))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == FIXTURE_SESSION_ID


def test_jsonl_without_session_meta_exits_nonzero_and_prints_nothing(tmp_path):
    jsonl = tmp_path / "no-session-meta.jsonl"
    jsonl.write_text(
        '{"type":"turn_context","payload":{"cwd":"/x"}}\n'
        '{"type":"token_count","payload":{"info":null}}\n'
    )
    result = _run(str(jsonl))
    assert result.returncode != 0
    assert result.stdout == "", f"expected no stdout, got {result.stdout!r}"


def test_missing_file_exits_nonzero(tmp_path):
    result = _run(str(tmp_path / "does-not-exist.jsonl"))
    assert result.returncode != 0
    assert result.stdout == ""


def test_no_args_exits_nonzero():
    result = _run()
    assert result.returncode != 0
    assert result.stdout == ""


def test_skips_malformed_lines_before_session_meta(tmp_path):
    """A garbled line ahead of a well-formed session_meta must not abort the
    scan — the valid ID is still extracted."""
    jsonl = tmp_path / "mixed.jsonl"
    jsonl.write_text(
        "this is not json\n"
        "\n"
        '{"type":"session_meta","payload":{"id":"11111111-2222-7333-8444-555555555555"}}\n'
    )
    result = _run(str(jsonl))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "11111111-2222-7333-8444-555555555555"


def test_first_session_meta_wins(tmp_path):
    """If two session_meta events appear, the FIRST id is returned (the seed
    session), not a later one."""
    jsonl = tmp_path / "two-meta.jsonl"
    jsonl.write_text(
        '{"type":"session_meta","payload":{"id":"aaaaaaaa-0000-7000-8000-000000000001"}}\n'
        '{"type":"session_meta","payload":{"id":"bbbbbbbb-0000-7000-8000-000000000002"}}\n'
    )
    result = _run(str(jsonl))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "aaaaaaaa-0000-7000-8000-000000000001"


def test_session_meta_without_id_is_treated_as_missing(tmp_path):
    """A session_meta event whose payload lacks a string id is not a valid
    seed — fall through to non-zero exit, nothing on stdout."""
    jsonl = tmp_path / "meta-no-id.jsonl"
    jsonl.write_text(
        '{"type":"session_meta","payload":{"originator":"codex_exec"}}\n'
        '{"type":"session_meta","payload":{"id":null}}\n'
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
        '["session_meta"]\n'
        '{"type":"session_meta","payload":{"id":"22222222-0000-7000-8000-000000000003"}}\n'
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
