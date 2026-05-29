"""Heading-delimited section extraction for Markdown files.

Provides extract_heading_section() — a shared primitive used by both
tests/test_triage_byte_identity.py (for byte-identity enforcement) and
scripts/propagate-shared-rules.py (for section propagation).
Having a single copy prevents the two callers from drifting.
"""

from __future__ import annotations

_NEXT_SECTION = "\n## "


def extract_heading_section(text: str, heading: str) -> str:
    """Return the body of a `## `-level Markdown section, stripped.

    Args:
        text:    Full file content.
        heading: Exact heading text, e.g. "## Triaging review findings".

    Returns:
        The text between `heading` and the next `## ` heading, stripped
        of leading/trailing whitespace.

    Raises:
        ValueError: heading not found, or found more than once.
    """
    count = text.count(heading)
    if count == 0:
        raise ValueError(f"Heading not found: {heading!r}")
    if count > 1:
        raise ValueError(f"Heading found {count} times (expected 1): {heading!r}")

    start = text.index(heading) + len(heading)
    rest = text[start:]
    end_idx = rest.find(_NEXT_SECTION)
    block = rest if end_idx == -1 else rest[:end_idx]
    return block.strip()
