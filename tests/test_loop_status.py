"""Tests for Bucket D verdict-footer parsing (V-6/7/8).

V-6: well-formed json-verdict footer  → parse returns expected dict
V-7: malformed JSON in footer block   → returns {"status": "malformed"}
V-8: no footer block at all           → returns {"status": "footer-missing"}

NOTE: _parse_footer is defined locally here as a contract test.
Commit 3 moves it into scripts/loop-status.py and updates these tests
to import from there.
"""

from __future__ import annotations

import json
import re


def _parse_footer(text: str) -> dict:
    """Extract and parse the last ```json code fence in *text*.

    Returns the parsed dict on success.
    Returns {"status": "footer-missing"} if no ```json fence is found.
    Returns {"status": "malformed"} if the fence exists but JSON is invalid.
    """
    fences = list(re.finditer(r"```json\s*\n(.*?)```", text, re.DOTALL))
    if not fences:
        return {"status": "footer-missing"}
    raw = fences[-1].group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "malformed"}


# ── V-6: well-formed footer ──────────────────────────────────────────────────


def test_v6_well_formed_footer():
    """V-6: a valid json-verdict fence is parsed into the expected dict."""
    review_text = """\
## Findings

**F1 (importance 3):** something is wrong.

**F2 (importance 1):** minor polish item.

```json
{
  "verdict": "needs-iter",
  "severity_counts": {"3": 1, "2": 0, "1": 1},
  "key": "abc123456789",
  "findings": [
    {
      "id": "F1",
      "importance": 3,
      "section_or_line": "## Implementation",
      "title": "something is wrong",
      "fingerprint": "implementation:something-is-wrong"
    },
    {
      "id": "F2",
      "importance": 1,
      "section_or_line": "## Scope",
      "title": "minor polish item",
      "fingerprint": "scope:minor-polish-item"
    }
  ]
}
```
"""
    result = _parse_footer(review_text)
    assert result["verdict"] == "needs-iter"
    assert result["severity_counts"]["3"] == 1
    assert result["severity_counts"]["1"] == 1
    assert result["key"] == "abc123456789"
    assert len(result["findings"]) == 2
    assert result["findings"][0]["id"] == "F1"
    assert result["findings"][0]["fingerprint"] == "implementation:something-is-wrong"


def test_v6_converged_verdict():
    """V-6 variant: converged verdict parses correctly."""
    review_text = """\
No important findings.

```json
{"verdict": "converged", "severity_counts": {"3": 0, "2": 0, "1": 0}, "key": "xyz987", "findings": []}
```
"""
    result = _parse_footer(review_text)
    assert result["verdict"] == "converged"
    assert result["findings"] == []


def test_v6_last_fence_wins():
    """V-6 variant: when multiple ```json fences exist, the last one is the verdict."""
    review_text = """\
Here is an example JSON snippet in the prose:

```json
{"example": "this is not the verdict"}
```

Now the actual verdict footer:

```json
{"verdict": "converged", "severity_counts": {"3": 0, "2": 1, "1": 0}, "key": "aaa111", "findings": []}
```
"""
    result = _parse_footer(review_text)
    assert result["verdict"] == "converged"
    assert result.get("example") is None


# ── V-7: malformed JSON ──────────────────────────────────────────────────────


def test_v7_malformed_json_returns_malformed():
    """V-7: a ```json fence with invalid JSON → {"status": "malformed"}."""
    review_text = """\
Some prose findings.

```json
{this is not valid json
  "verdict": "needs-iter",
}
```
"""
    result = _parse_footer(review_text)
    assert result == {"status": "malformed"}


def test_v7_truncated_json():
    """V-7 variant: truncated JSON object → {"status": "malformed"}."""
    review_text = '```json\n{"verdict": "needs-iter", "findings": [\n```\n'
    result = _parse_footer(review_text)
    assert result == {"status": "malformed"}


# ── V-8: missing footer ──────────────────────────────────────────────────────


def test_v8_no_footer_returns_footer_missing():
    """V-8: review text with no ```json fence → {"status": "footer-missing"}."""
    review_text = """\
## Findings

**F1 (importance 2):** something could be improved.

Overall: needs another iteration.
"""
    result = _parse_footer(review_text)
    assert result == {"status": "footer-missing"}


def test_v8_only_non_json_fences():
    """V-8 variant: ```python or plain ``` fences don't count as the footer."""
    review_text = """\
Here is some code:

```python
x = 1
```

And a plain fence:

```
not json
```
"""
    result = _parse_footer(review_text)
    assert result == {"status": "footer-missing"}


def test_v8_empty_string():
    """V-8 variant: empty input → {"status": "footer-missing"}."""
    assert _parse_footer("") == {"status": "footer-missing"}
