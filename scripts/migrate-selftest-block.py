#!/usr/bin/env python3
"""Re-sync the review machinery of a downstream Makefile from this skill repo.

Two things travel together (a migrated block without its data files would
reference prompt files the downstream does not have):

1. The SELFTEST-OVERLAP sentinel block: extracted from this skill repo's
   Makefile (between SELFTEST-OVERLAP-BEGIN and SELFTEST-OVERLAP-END) and
   swapped into the same-sentinel block of the target Makefile.
2. The block's runtime data + helper: every `prompts/*.txt` review prompt and
   `scripts/render-review-prompt.py` (the substitution helper the recipes
   exec), copied into the target project (the target Makefile's directory).
   The helper lands executable (0755).

Dry-run by default: prints the block diff plus the files that would be
copied; use --apply to write.

Usage:
    scripts/migrate-selftest-block.py --target /path/to/Makefile [--apply]

Exit codes:
    0 — dry-run (already in sync) or --apply succeeded
    1 — changes would be made (dry-run only)
    2 — error (sentinel not found, found multiple times, or read error)
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_MAKEFILE = _SKILL_ROOT / "Makefile"
_BEGIN = "# SELFTEST-OVERLAP-BEGIN:"
_END = "# SELFTEST-OVERLAP-END:"

# The substitution helper the migrated recipes exec; must land 0755.
_HELPER_REL = "scripts/render-review-prompt.py"


def _files_to_carry() -> list[str]:
    """Repo-relative paths of the prompt files + helper the block depends on."""
    prompt_rels = sorted(
        p.relative_to(_SKILL_ROOT).as_posix() for p in (_SKILL_ROOT / "prompts").glob("*.txt")
    )
    return [*prompt_rels, _HELPER_REL]


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
        description="Re-sync SELFTEST-OVERLAP block + prompts/ + helper into a target project."
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
    block_differs = source_block != target_block

    # Prompt files + helper: compare bytes against the target project (the
    # target Makefile's directory) to decide what needs copying.
    project_root = args.target.resolve().parent
    copies: list[tuple[str, str]] = []  # (rel_path, "new" | "changed")
    for rel in _files_to_carry():
        src = _SKILL_ROOT / rel
        if not src.is_file():
            print(f"ERROR: source file missing: {src}", file=sys.stderr)
            return 2
        dst = project_root / rel
        if not dst.exists():
            copies.append((rel, "new"))
        elif dst.read_bytes() != src.read_bytes():
            copies.append((rel, "changed"))

    if not block_differs and not copies:
        print(f"{args.target}: already in sync (block + prompt files + helper)")
        return 0

    print(f"Source: {_SOURCE_MAKEFILE}")
    print(f"Target: {args.target}")
    print(f"Mode:   {'apply' if args.apply else 'dry-run'}")
    print()

    if block_differs:
        updated_lines = target_lines[:t_begin] + source_block + target_lines[t_end + 1 :]
        diff = list(
            difflib.unified_diff(
                target_lines,
                updated_lines,
                fromfile=f"a/{args.target}",
                tofile=f"b/{args.target}",
            )
        )
        sys.stdout.writelines(diff)
        print()
    else:
        updated_lines = target_lines
        print("(sentinel block already in sync)")

    if copies:
        print(f"Files to copy into {project_root}:")
        for rel, status in copies:
            print(f"  {rel} ({status})")
    else:
        print("(prompt files + helper already in sync)")

    if args.apply:
        if block_differs:
            args.target.write_text("".join(updated_lines))
        for rel, _status in copies:
            src = _SKILL_ROOT / rel
            dst = project_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)  # copies mode bits too
            if rel == _HELPER_REL:
                dst.chmod(0o755)  # belt-and-braces: recipes exec this directly
        print("\nApplied. Use `git diff` to review; `git checkout` to revert.")
        return 0
    else:
        print("\nRe-run with --apply to write. Use `git diff` to review; `git checkout` to revert.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
