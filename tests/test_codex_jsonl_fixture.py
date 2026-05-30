"""Validate the two committed codex JSONL fixtures.

TWO distinct schemas (the live gate falsified an earlier conflation of them):
  - codex-json-session.jsonl — the codex ROLLOUT FILE
    (~/.codex/sessions/<Y>/<M>/<D>/rollout-<ts>-<thread_id>.jsonl). Schema:
    session_meta / turn_context / event_msg / response_item. The V-13.5 read-only
    gate reads turn_context.payload.sandbox_policy.type from here.
      - session id: session_meta.payload.id (== the stream's thread_id)
      - cache tokens: event_msg -> payload.info.total_token_usage.cached_input_tokens
  - codex-json-stream.jsonl — the `codex exec --json` STDOUT STREAM. Schema:
    thread.started / turn.started / item.completed / turn.completed. The extractor
    + the V-13.5 thread-id gate read thread.started.thread_id from here.
      - resumable id: thread.started.thread_id
      - cache tokens: turn.completed.usage.cached_input_tokens (F4)

Also validates that both fixtures are sanitized: no home paths, no secrets-looking
keys, no long prompt bodies.

Note: real codex IDs are UUIDv7 (version nibble 7). The fixtures use synthetic
UUIDs that satisfy the same 8-4-4-4-12 hex pattern; Bucket F must not assume UUID v4.
"""

import json
import re
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "codex-json-session.jsonl"
STREAM_FIXTURE = Path(__file__).parent / "fixtures" / "codex-json-stream.jsonl"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

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


# ── codex-json-stream.jsonl: the --json STDOUT stream schema ──────────────────


def _load_stream_events():
    return [
        json.loads(line)
        for line in STREAM_FIXTURE.read_text().splitlines()
        if line.strip()
    ]


def test_stream_fixture_parses_as_valid_jsonl():
    events = _load_stream_events()
    assert len(events) >= 4, "Stream fixture must have at least 4 events"


def test_stream_thread_started_present_with_thread_id():
    """Pins the resumable-id field path for the STREAM: thread.started.thread_id
    (a top-level field, NOT session_meta.payload.id — that is the rollout file)."""
    events = _load_stream_events()
    started = [e for e in events if e.get("type") == "thread.started"]
    assert started, "No thread.started event in the stream fixture"
    thread_id = started[0].get("thread_id")
    assert isinstance(thread_id, str) and UUID_RE.match(thread_id), (
        "thread.started.thread_id must be an 8-4-4-4-12 UUID at the top level "
        "(this is the id `codex exec resume <SESSION_ID>` consumes)"
    )


def test_stream_turn_completed_has_cached_input_tokens():
    """Pins the STREAM cache metric (F4): turn.completed.usage.cached_input_tokens
    (NOT the rollout file's event_msg.payload.info... path)."""
    events = _load_stream_events()
    completed = [e for e in events if e.get("type") == "turn.completed"]
    assert completed, "No turn.completed event in the stream fixture"
    usage = completed[0].get("usage", {})
    assert "cached_input_tokens" in usage, (
        "turn.completed.usage.cached_input_tokens missing — this is the stream's "
        "cache-hit metric for the A/B replay gate"
    )


def test_stream_has_no_rollout_only_event_types():
    """Locks the schema distinction that the live gate forced: the --json STREAM
    must NOT contain session_meta / turn_context (those are rollout-FILE-only).
    Conflating the two is exactly the bug the 2026-05-30 correction fixed."""
    types = {e.get("type") for e in _load_stream_events()}
    for rollout_only in ("session_meta", "turn_context", "event_msg", "response_item"):
        assert rollout_only not in types, (
            f"'{rollout_only}' is a rollout-FILE event type; it must not appear in "
            "the --json STDOUT stream fixture"
        )


def test_stream_no_home_paths_or_secrets():
    raw = STREAM_FIXTURE.read_text()
    assert not HOME_PATH_RE.search(raw), "Stream fixture contains home paths — sanitize."
    assert not SECRET_KEY_RE.search(raw), "Stream fixture contains secret-looking keys."
