"""Heading-delimited section extraction for Markdown files.

Provides extract_heading_section() — a shared primitive used by both
tests/test_triage_byte_identity.py (for byte-identity enforcement) and
scripts/propagate-shared-rules.py (for section propagation).
Having a single copy prevents the two callers from drifting.
"""

from __future__ import annotations


def extract_heading_section(text: str, heading: str) -> str:
    """Return the body of a `## `-level Markdown section, stripped.

    Args:
        text:    Full file content.
        heading: Exact heading text, e.g. "## Triaging review findings".

    Returns:
        The text between the `heading` LINE and the next `## ` heading line,
        stripped of leading/trailing whitespace.

    Raises:
        ValueError: heading not found, or found more than once.

    Matches only real Markdown heading LINES (a line whose stripped content
    equals `heading`), NOT prose that merely mentions the heading text inline
    (e.g. "see ## Triaging review findings below"). A substring match
    (`text.count`) would over-count such a mention and spuriously raise.
    """
    lines = text.split("\n")
    matches = [i for i, ln in enumerate(lines) if ln.strip() == heading]
    if not matches:
        raise ValueError(f"Heading not found: {heading!r}")
    if len(matches) > 1:
        raise ValueError(f"Heading found {len(matches)} times (expected 1): {heading!r}")

    body = []
    for line in lines[matches[0] + 1 :]:
        if line.startswith("## "):  # next level-2 heading line ends the section
            break
        body.append(line)
    return "\n".join(body).strip()
