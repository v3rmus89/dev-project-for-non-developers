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
import contextlib
import difflib
import os
import sys
import tempfile
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

# Stdlib-only import (bootstrap_lib/__init__.py is empty; paths pulls no
# third-party deps) -- the same containment check render/adopt use, so the
# migration cannot write through a symlinked prompts/ or helper path to
# somewhere outside the target project.
from bootstrap_lib.paths import PathSafetyError, validate_target_path  # noqa: E402

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


def _atomic_copy(src: Path, dst: Path, mode: int) -> None:
    """Write src's bytes to dst via a same-directory temp file + os.replace.

    os.replace never follows an existing dst symlink (it replaces the link
    itself), so combined with the containment validation above a write can
    never land outside the target project; it is also crash-atomic.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(dst.parent), prefix=dst.name + ".")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(src.read_bytes())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, dst)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


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

    # Prompt files + helper: compare against the target project (the target
    # Makefile's directory) to decide what needs copying. Every derived
    # destination is containment-validated FIRST -- a symlinked prompts/ dir
    # or helper file pointing outside the project would otherwise let --apply
    # overwrite an unrelated path (dry-run reads through it too).
    project_root = args.target.resolve().parent
    copies: list[tuple[str, str]] = []  # (rel_path, "new" | "changed" | "mode")
    for rel in _files_to_carry():
        src = _SKILL_ROOT / rel
        if not src.is_file():
            print(f"ERROR: source file missing: {src}", file=sys.stderr)
            return 2
        try:
            dst = validate_target_path(project_root, rel)
        except PathSafetyError as exc:
            print(f"ERROR: refusing {rel}: {exc}", file=sys.stderr)
            return 2
        if not dst.exists():
            copies.append((rel, "new"))
        elif dst.read_bytes() != src.read_bytes():
            copies.append((rel, "changed"))
        elif rel == _HELPER_REL and not os.access(dst, os.X_OK):
            # Byte-identical helper without its exec bit still breaks every
            # rewired recipe (permission denied) -- mode drift IS drift.
            copies.append((rel, "mode"))

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
        for rel, status in copies:
            src = _SKILL_ROOT / rel
            dst = validate_target_path(project_root, rel)  # re-check at write time
            if status == "mode":
                dst.chmod(0o755)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            _atomic_copy(src, dst, 0o755 if rel == _HELPER_REL else 0o644)
        print("\nApplied. Use `git diff` to review; `git checkout` to revert.")
        return 0
    else:
        print("\nRe-run with --apply to write. Use `git diff` to review; `git checkout` to revert.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
