"""Validate the sanitized codex --json JSONL fixture.

Pins two field paths found by inspecting real codex exec --json output (2026-05-29):
  - session ID: session_meta.payload.id (UUID / ULIDv7) — NOT a top-level session_id
  - cache tokens: event_msg -> payload.info.total_token_usage.cached_input_tokens

Also validates that the fixture is sanitized: no home paths, no secrets-looking keys,
no long prompt bodies.

Note: real codex IDs are ULIDv7 format (version nibble 7). The fixture uses a synthetic
UUID that satisfies the same 8-4-4-4-12 hex pattern; Bucket F must not assume UUID v4.
"""

import json
import re
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "codex-json-session.jsonl"

HOME_PATH_RE = re.compile(r"/Users/|/home/")
SECRET_KEY_RE = re.compile(
    r'"(api_key|secret|password|token|auth|credential|private_key)"\s*:',
    re.IGNORECASE,
)


def _load_events():
    events = []
    for line in FIXTURE.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def test_fixture_parses_as_valid_jsonl():
    events = _load_events()
    assert len(events) >= 4, "Fixture must have at least 4 events"


def test_no_home_paths():
    raw = FIXTURE.read_text()
    assert not HOME_PATH_RE.search(raw), (
        "Fixture contains home paths (/Users/ or /home/). Sanitize before committing."
    )


def test_no_secrets_looking_keys():
    raw = FIXTURE.read_text()
    assert not SECRET_KEY_RE.search(raw), (
        "Fixture contains secret-looking keys (api_key, password, token…)."
    )


def test_session_meta_event_present_with_id_field():
    """Pins the ACTUAL session-ID field path: session_meta.payload.id (not top-level session_id)."""
    events = _load_events()
    meta_events = [e for e in events if e.get("type") == "session_meta"]
    assert meta_events, "No session_meta event in fixture"
    meta = meta_events[0]
    payload = meta.get("payload", {})
    assert "id" in payload, (
        "session_meta.payload.id missing — the session ID used by "
        "`codex exec resume <SESSION_ID>` is at payload.id, not a top-level field"
    )
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        payload["id"],
    ), "session_meta.payload.id must be a UUID"


def test_cached_input_tokens_field_present():
    """Pins the token-cache field path: event_msg -> payload.info.total_token_usage.cached_input_tokens."""
    events = _load_events()
    token_events = [
        e
        for e in events
        if e.get("type") == "event_msg"
        and e.get("payload", {}).get("type") == "token_count"
        and e.get("payload", {}).get("info") is not None
    ]
    assert token_events, "No event_msg/token_count event with non-null info in fixture"
    usage = token_events[0]["payload"]["info"]["total_token_usage"]
    assert "cached_input_tokens" in usage, (
        "cached_input_tokens missing from total_token_usage — "
        "field name must be verified against real codex output"
    )


def test_all_required_event_types_present():
    events = _load_events()
    types = {e.get("type") for e in events}
    for required in ("session_meta", "turn_context", "event_msg", "response_item"):
        assert required in types, f"Event type '{required}' missing from fixture"


def test_no_long_prompt_bodies():
    """Prompt/reasoning bodies in the fixture must be short (sanitization check)."""
    events = _load_events()
    for e in events:
        payload = e.get("payload", {})
        content = payload.get("content", [])
        if isinstance(content, list):
            for block in content:
                text = block.get("text", "") if isinstance(block, dict) else ""
                assert len(text) < 500, (
                    f"Fixture contains a long content block ({len(text)} chars). "
                    "Strip prompt bodies before committing."
                )
        msg = payload.get("message", "")
        assert len(msg) < 500, f"Fixture contains a long message field ({len(msg)} chars)."
