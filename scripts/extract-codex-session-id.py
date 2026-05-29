#!/usr/bin/env python3
"""Extract the Codex session ID from a `codex exec --json` JSONL stream.

Reads the JSONL file produced by `codex exec --json` and prints the session
ID found at `session_meta.payload.id` (V-13 confirmed field path, 2026-05-29 —
NOT a top-level `session_id`) from the FIRST `session_meta` event. That ID is
the argument `codex exec resume <SESSION_ID>` needs to continue the thread.

Lines that are blank or not valid JSON are skipped, so a partial/garbled
stream that still contains a well-formed `session_meta` event yields the ID.

Usage:
    scripts/extract-codex-session-id.py <jsonl-file>

Exit codes:
    0 — session ID written to stdout
    1 — file not found / unreadable, OR no `session_meta` event with a
        string `payload.id` was found (nothing written to stdout)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def extract_session_id(jsonl_text: str) -> str | None:
    """Return `payload.id` from the first `session_meta` event, else None."""
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "session_meta":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        session_id = payload.get("id")
        if isinstance(session_id, str) and session_id:
            return session_id
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
        sys.stderr.write("no session_meta event with a string payload.id found\n")
        return 1

    print(session_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
