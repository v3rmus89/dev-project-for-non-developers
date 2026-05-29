#!/usr/bin/env python3
"""Propagate Tier-1 shared Markdown sections from this skill repo to downstream repos.

Tier-1 sections are byte-identical across all copies (no per-project render needed).
The canonical source is this skill repo's dogfood files. Target files are
git-tracked; git is the undo mechanism.

Usage:
    scripts/propagate-shared-rules.py [--apply] [--section HEADING] TARGET_FILE [TARGET_FILE ...]

    TARGET_FILE   Absolute or relative path to a Markdown file that contains the
                  managed section.

Options:
    --apply         Write changes (default: dry-run, print unified diff only).
    --section STR   Heading to propagate (default: "## Triaging review findings").
    --source FILE   Source file to read the canonical section from
                    (default: <skill-root>/CLAUDE.md).

Exit codes:
    0  — dry-run or all targets already in sync
    1  — one or more targets would be updated (dry-run) or were updated (--apply)
    2  — error (missing heading, ambiguous heading, file not found)
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SECTION = "## Triaging review findings"
DEFAULT_SOURCE = _SKILL_ROOT / "CLAUDE.md"

_NEXT_SECTION = "\n## "


def extract_heading_section(text: str, heading: str) -> str:
    """Return the body of a `## `-level Markdown section, stripped.

    Logic mirrors bootstrap_lib/section_extract.py — tests/test_triage_byte_identity.py
    imports that module; tests/test_propagate_shared_rules.py exercises this copy.
    Both must produce identical output for the same input (enforced by cross-check test).

    Raises ValueError if heading is not found or found more than once.
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


def _replace_section(text: str, heading: str, new_body: str) -> str:
    """Return text with the body of `heading` replaced by new_body.

    The heading line itself is preserved. new_body should be stripped;
    a surrounding blank line is added on each side.
    """
    count = text.count(heading)
    if count == 0:
        raise ValueError(f"Heading not found in target: {heading!r}")
    if count > 1:
        raise ValueError(f"Heading found {count} times in target (expected 1): {heading!r}")

    start_idx = text.index(heading)
    after_heading = text[start_idx + len(heading) :]

    next_section = "\n## "
    end_in_after = after_heading.find(next_section)
    if end_in_after == -1:
        # Section runs to end of file
        return text[: start_idx + len(heading)] + "\n\n" + new_body + "\n"
    else:
        suffix = after_heading[end_in_after:]
        return text[: start_idx + len(heading)] + "\n\n" + new_body + "\n" + suffix


def _propagate(source_body: str, target_path: Path, heading: str, apply: bool) -> bool:
    """Return True if a change was made or would be made.

    Raises ValueError on target file errors so main() can continue processing
    remaining targets and report all failures before exiting.
    """
    try:
        original = target_path.read_text()
    except FileNotFoundError:
        raise ValueError(f"target not found: {target_path}") from None

    try:
        current_body = extract_heading_section(original, heading)
    except ValueError as exc:
        raise ValueError(f"in {target_path}: {exc}") from exc

    if current_body == source_body:
        print(f"  {target_path}: already in sync")
        return False

    updated = _replace_section(original, heading, source_body)

    diff = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{target_path}",
            tofile=f"b/{target_path}",
        )
    )
    print(f"  {target_path}: {'applying' if apply else 'diff'}")
    sys.stdout.writelines(diff)

    if apply:
        target_path.write_text(updated)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Propagate Tier-1 shared sections to downstream Markdown files."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default: dry-run).",
    )
    parser.add_argument(
        "--section",
        default=DEFAULT_SECTION,
        help=f"Heading to propagate (default: {DEFAULT_SECTION!r}).",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Source file (default: {DEFAULT_SOURCE}).",
    )
    parser.add_argument(
        "targets",
        nargs="+",
        type=Path,
        metavar="TARGET_FILE",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"ERROR: source not found: {args.source}", file=sys.stderr)
        return 2

    try:
        source_body = extract_heading_section(args.source.read_text(), args.section)
    except ValueError as exc:
        print(f"ERROR in source {args.source}: {exc}", file=sys.stderr)
        return 2

    print(f"Section: {args.section!r}")
    print(f"Source:  {args.source}")
    print(f"Mode:    {'apply' if args.apply else 'dry-run'}")
    print()

    changed = False
    has_error = False
    for target in args.targets:
        try:
            changed |= _propagate(source_body, target, args.section, args.apply)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            has_error = True

    if has_error:
        return 2

    if changed and not args.apply:
        print()
        print(
            "Re-run with --apply to write changes. Use `git diff` to review; `git checkout` to revert."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
