#!/usr/bin/env python3
"""Replace the SELFTEST-OVERLAP sentinel block in a target Makefile.

Extracts the block between SELFTEST-OVERLAP-BEGIN and SELFTEST-OVERLAP-END
from this skill repo's Makefile and replaces the same-sentinel block in the
target Makefile. Dry-run by default (prints a unified diff); use --apply to write.

Usage:
    scripts/migrate-selftest-block.py --target /path/to/Makefile [--apply]

Exit codes:
    0 — dry-run (already in sync) or --apply succeeded
    1 — one change would be made (dry-run only)
    2 — error (sentinel not found, found multiple times, or source read error)
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_MAKEFILE = _SKILL_ROOT / "Makefile"
_BEGIN = "# SELFTEST-OVERLAP-BEGIN:"
_END = "# SELFTEST-OVERLAP-END:"


def _extract_sentinel_block(lines: list[str], path: str) -> tuple[int, int]:
    """Return (begin_idx, end_idx) inclusive of the sentinel lines.

    Raises ValueError if sentinels are missing or appear more than once.
    """
    begins = [i for i, line in enumerate(lines) if line.startswith(_BEGIN)]
    ends = [i for i, line in enumerate(lines) if line.startswith(_END)]

    if len(begins) != 1:
        raise ValueError(f"{path}: expected 1 {_BEGIN!r} line, found {len(begins)}")
    if len(ends) != 1:
        raise ValueError(f"{path}: expected 1 {_END!r} line, found {len(ends)}")
    begin_idx, end_idx = begins[0], ends[0]
    if end_idx < begin_idx:
        raise ValueError(f"{path}: {_END!r} appears before {_BEGIN!r}")
    return begin_idx, end_idx


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace SELFTEST-OVERLAP block in a target Makefile."
    )
    parser.add_argument("--target", required=True, type=Path, help="Target Makefile path.")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    args = parser.parse_args()

    if not _SOURCE_MAKEFILE.is_file():
        print(f"ERROR: source Makefile not found: {_SOURCE_MAKEFILE}", file=sys.stderr)
        return 2

    if not args.target.is_file():
        print(f"ERROR: target not found: {args.target}", file=sys.stderr)
        return 2

    source_lines = _SOURCE_MAKEFILE.read_text().splitlines(keepends=True)
    target_lines = args.target.read_text().splitlines(keepends=True)

    try:
        s_begin, s_end = _extract_sentinel_block(source_lines, str(_SOURCE_MAKEFILE))
    except ValueError as exc:
        print(f"ERROR in source: {exc}", file=sys.stderr)
        return 2

    try:
        t_begin, t_end = _extract_sentinel_block(target_lines, str(args.target))
    except ValueError as exc:
        print(f"ERROR in target: {exc}", file=sys.stderr)
        return 2

    source_block = source_lines[s_begin : s_end + 1]
    target_block = target_lines[t_begin : t_end + 1]

    if source_block == target_block:
        print(f"{args.target}: already in sync")
        return 0

    updated_lines = target_lines[:t_begin] + source_block + target_lines[t_end + 1 :]

    diff = list(
        difflib.unified_diff(
            target_lines,
            updated_lines,
            fromfile=f"a/{args.target}",
            tofile=f"b/{args.target}",
        )
    )
    print(f"Source: {_SOURCE_MAKEFILE}")
    print(f"Target: {args.target}")
    print(f"Mode:   {'apply' if args.apply else 'dry-run'}")
    print()
    sys.stdout.writelines(diff)

    if args.apply:
        args.target.write_text("".join(updated_lines))
        print("\nApplied. Use `git diff` to review; `git checkout` to revert.")
        return 0
    else:
        print("\nRe-run with --apply to write. Use `git diff` to review; `git checkout` to revert.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
