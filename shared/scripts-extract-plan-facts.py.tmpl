#!/usr/bin/env python3
"""Extract verifiable facts from active plan sections.

Reads a Markdown plan file and emits JSON containing:
- fact_roots: absolute paths declared in a ## Fact roots block (empty
  list if the block is absent — callers should then pass the repo root
  as the default root to verify-plan-facts.py).
- facts: list of typed fact items extracted from active sections only.

Active/historical detection (FN1 blacklist design): sections are active
by default; a section is treated as historical when its heading matches
one of the EXCLUDED_HEADINGS below.  The exclusion ends when the next
heading at the same or higher level appears.

Usage:
  scripts/extract-plan-facts.py <plan-file>
  scripts/extract-plan-facts.py <plan-file> | scripts/verify-plan-facts.py - <root-dir>

Exit codes:
  0 — JSON written to stdout
  1 — plan file not found or unreadable
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Headings (lower-cased, stripped) that mark the start of historical
# sections.  The exclusion extends until the next heading at the same
# or shallower level.
EXCLUDED_HEADINGS: frozenset[str] = frozenset(
    {
        "iteration log",
        "evidence table",
        "lessons surfaced",
        "loop outcome",
    }
)

# Known file extensions — used to distinguish file references from other
# backtick tokens.
FILE_EXTENSIONS: frozenset[str] = frozenset(
    {
        "py",
        "go",
        "ts",
        "tsx",
        "js",
        "md",
        "sh",
        "yml",
        "yaml",
        "json",
        "toml",
        "cfg",
        "tmpl",
        "txt",
        "lock",
        "mod",
    }
)


def _heading_level(line: str) -> int | None:
    """Return the heading level (1-6) or None if the line is not a heading."""
    m = re.match(r"^(#{1,6})\s", line)
    return len(m.group(1)) if m else None


def _heading_text(line: str) -> str:
    """Return the normalised heading text (lower-case, stripped)."""
    text = re.sub(r"^#{1,6}\s+", "", line).strip()
    text = re.sub(r"\s+#+\s*$", "", text).strip()
    return text.lower()


def extract_active_text(plan_text: str) -> str:
    """Strip lines that belong to historical (excluded) sections.

    Fenced code blocks (``` or ~~~) are opaque to heading detection: a
    Markdown heading shown *inside* a fence (e.g. an example
    ``## Evidence table``) is literal content, not a section boundary, and
    must not flip the extractor into historical-exclusion mode and silently
    drop the active facts that follow the fence.  The fence lines themselves
    stay in the active text — only their role as section headings is
    suppressed (mirrors parse_fact_roots's fence handling).
    """
    lines = plan_text.splitlines()
    active: list[str] = []
    excluded_depth: int | None = None
    in_fence = False

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            if excluded_depth is None:
                active.append(line)
            continue

        # Inside a fence, a "## ..." line is literal example content, not a
        # real section boundary — leave excluded_depth untouched.
        lvl = None if in_fence else _heading_level(line)
        if lvl is not None:
            # Exiting an excluded section when we see a heading at the same
            # or shallower (lower number) depth.
            if excluded_depth is not None and lvl <= excluded_depth:
                excluded_depth = None

            heading = _heading_text(line)
            # Check exact match or any prefix match from the excluded set.
            is_excluded = heading in EXCLUDED_HEADINGS or any(
                heading.startswith(e) for e in EXCLUDED_HEADINGS
            )
            if is_excluded:
                excluded_depth = lvl
                # Skip the heading line entirely so its text can't be
                # extracted as a fact.
                continue

        if excluded_depth is None:
            active.append(line)

    return "\n".join(active)


def parse_fact_roots(plan_text: str) -> list[str]:
    """Return absolute paths from a '## Fact roots' block, if present.

    Looks for a heading that starts with "fact roots" (case-insensitive)
    and collects list items that look like absolute paths.

    Privacy scoping: lines inside fenced code blocks (``` or ~~~) are
    ignored, so a Fact-roots example shown inside a code fence does NOT
    declare real read roots.  Callers should pass ACTIVE plan text
    (historical sections already stripped) so a Fact-roots block nested
    under an excluded section is not honoured either.
    """
    roots: list[str] = []
    in_block = False
    block_depth = 2
    in_fence = False

    for line in plan_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        lvl = _heading_level(line)
        if lvl is not None:
            heading = _heading_text(line)
            if in_block and lvl <= block_depth:
                break
            if heading.startswith("fact roots"):
                in_block = True
                block_depth = lvl
                continue
        if in_block:
            # Match "- /absolute/path" or "- `/absolute/path`"
            m = re.match(r"^\s*[-*]\s+`?(/[^\s`]+)`?", line)
            if m:
                roots.append(m.group(1))

    return roots


def _has_file_extension(name: str) -> bool:
    """True if the rightmost component after '.' is a known file extension."""
    parts = name.rsplit(".", 1)
    return len(parts) == 2 and parts[1].lower() in FILE_EXTENSIONS


def extract_facts(active_text: str) -> list[dict]:
    """Scan active_text for verifiable fact references.

    Extracts from:
    - Backtick-quoted tokens (primary source)
    - Bare path:N patterns in plain prose (secondary)

    Returns a de-duplicated list of fact dicts.  Each dict has at minimum:
      type, raw, and type-specific fields.
    """
    facts: list[dict] = []
    seen: set[tuple] = set()

    def _add(fact: dict, key: tuple) -> None:
        if key not in seen:
            seen.add(key)
            facts.append(fact)

    # ── Backtick-quoted tokens ─────────────────────────────────────────
    for m in re.finditer(r"`([^`\n]+)`", active_text):
        token = m.group(1).strip()

        # make <target> — before file check so "make loop-status" isn't
        # mistaken for a file path.
        mm = re.match(r"^make\s+([a-zA-Z_][a-zA-Z0-9_-]+)$", token)
        if mm:
            _add(
                {"type": "make_target_ref", "raw": token, "target": mm.group(1)},
                ("make_target_ref", mm.group(1)),
            )
            continue

        # path:N
        fm = re.match(r"^([\w./\-]+\.\w+):(\d+)$", token)
        if fm and _has_file_extension(fm.group(1)):
            _add(
                {
                    "type": "file_line_ref",
                    "raw": token,
                    "path": fm.group(1),
                    "line": int(fm.group(2)),
                },
                ("file_line_ref", fm.group(1), int(fm.group(2))),
            )
            continue

        # plain file path
        if (
            ("/" in token or _has_file_extension(token))
            and re.match(r"^[\w./\-]+$", token)
            and _has_file_extension(token.split("/")[-1])
        ):
            _add(
                {"type": "file_ref", "raw": token, "path": token},
                ("file_ref", token),
            )
            continue

        # symbol()
        sm = re.match(r"^([a-zA-Z_]\w+)\(\)$", token)
        if sm:
            _add(
                {"type": "symbol_ref", "raw": token, "symbol": sm.group(1)},
                ("symbol_ref", sm.group(1)),
            )
            continue

        # CLI flag (--flag or -f)
        if re.match(r"^-{1,2}[a-zA-Z][a-zA-Z0-9-]*$", token):
            _add(
                {"type": "cli_flag_ref", "raw": token, "flag": token},
                ("cli_flag_ref", token),
            )
            continue

    # ── Bare path:N in plain prose (outside backticks) ─────────────────
    # Strip backtick-quoted spans first to avoid double-counting.
    prose = re.sub(r"`[^`\n]+`", "", active_text)
    for m in re.finditer(r"(?<![/\w])([\w./\-]+\.\w+):(\d+)(?!\w)", prose):
        path, lineno = m.group(1), int(m.group(2))
        if _has_file_extension(path):
            _add(
                {"type": "file_line_ref", "raw": m.group(0), "path": path, "line": lineno},
                ("file_line_ref", path, lineno),
            )

    return facts


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print(
            "Usage: extract-plan-facts.py <plan-file>",
            file=sys.stderr,
        )
        return 1

    plan_path = Path(argv[0])
    if not plan_path.exists():
        print(f"plan file not found: {plan_path}", file=sys.stderr)
        return 1

    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read plan file: {exc}", file=sys.stderr)
        return 1

    active_text = extract_active_text(plan_text)
    # parse_fact_roots runs on ACTIVE text so a "## Fact roots" block nested
    # under a historical section cannot declare read roots (privacy scoping).
    fact_roots = parse_fact_roots(active_text)
    facts = extract_facts(active_text)

    result = {
        "plan_file": str(plan_path),
        "fact_roots": fact_roots,
        "facts": facts,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
