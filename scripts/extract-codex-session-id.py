#!/usr/bin/env python3
"""Extract the Codex session (thread) ID from a `codex exec --json` JSONL stream.

Reads the JSONL stream `codex exec --json` writes to stdout and prints the
resumable id found at `thread.started.thread_id` (verified live against
codex-cli 0.130.0, 2026-05-30) from the FIRST `thread.started` event. That id is
the argument `codex exec resume <SESSION_ID>` needs to continue the thread.

Schema note: the `--json` STDOUT *stream* keys the resumable id on a top-level
`thread.started.thread_id`. The `session_meta.payload.id` field is the codex
*rollout FILE* schema (`~/.codex/sessions/<Y>/<M>/<D>/rollout-<ts>-<thread_id>.jsonl`),
where `session_meta.payload.id == thread_id`. This script reads the STREAM, so it
keys on `thread.started`, NOT `session_meta` (an earlier version read the wrong
artifact — see the 2026-05-30 plan correction).

Lines that are blank or not valid JSON are skipped, so a partial/garbled
stream that still contains a well-formed `thread.started` event yields the id.

Usage:
    scripts/extract-codex-session-id.py <jsonl-file>

Exit codes:
    0 — session id written to stdout
    1 — file not found / unreadable, OR no `thread.started` event with a
        string `thread_id` was found (nothing written to stdout)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def extract_session_id(jsonl_text: str) -> str | None:
    """Return `thread_id` from the first `thread.started` event, else None."""
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "thread.started":
            continue
        thread_id = event.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            return thread_id
    return None


def main(argv: list[str]) -> int:
    if not argv:
        sys.stderr.write("Usage: extract-codex-session-id.py <jsonl-file>\n")
        return 1

    jsonl_path = Path(argv[0])
    if not jsonl_path.exists():
        sys.stderr.write(f"jsonl file not found: {jsonl_path}\n")
        return 1

    try:
        jsonl_text = jsonl_path.read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"cannot read jsonl file: {exc}\n")
        return 1

    session_id = extract_session_id(jsonl_text)
    if session_id is None:
        sys.stderr.write("no thread.started event with a string thread_id found\n")
        return 1

    print(session_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
