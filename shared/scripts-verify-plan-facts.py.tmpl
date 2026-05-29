#!/usr/bin/env python3
"""Deterministic verifier for facts extracted by extract-plan-facts.py.

Reads the JSON produced by extract-plan-facts.py (from stdin or a file),
verifies each fact against the declared fact roots without mutating any
state, and emits a structured verification JSON to stdout.

Verification rules (all read-only):
  file_ref        — path exists under a declared root
  file_line_ref   — path exists AND file has >= N lines
  symbol_ref      — grep recursively for a function/method definition
  make_target_ref — grep Makefile in the root for the target
  cli_flag_ref    — not_verifiable (argparse semantics require importing
                    the CLI under test; deferred to a future enhancement)

Fact-root resolution:
  - The plan may declare explicit absolute roots in a ## Fact roots block;
    these are passed through the facts JSON under "fact_roots".
  - The caller passes a DEFAULT_ROOT (the current repo) as the second
    argument.  If fact_roots is empty the default root is used.
  - A relative path fact is searched under each declared root in order.
  - Containment is enforced by resolving the candidate (collapsing ``..``
    and symlinks): an absolute path OR a relative path that climbs out via
    ``..`` and lands outside every declared root is classified as
    unsupported_external — never verified.

Usage:
  scripts/extract-plan-facts.py plan.md | scripts/verify-plan-facts.py - /repo/root
  scripts/verify-plan-facts.py facts.json /repo/root

Exit codes:
  0 — JSON written to stdout (regardless of failed findings)
  1 — argument/input error
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    except OSError:
        return -1


def _within(path: Path, root: Path) -> bool:
    """True if *path* resolves to a location inside *root* (already resolved).

    ``resolve()`` collapses ``..`` and symlinks, so neither can smuggle a read
    outside the declared root.  This is the SINGLE containment predicate shared
    by every read site (``_escapes_all_roots``, ``_find_file``, ``_grep_symbol``,
    ``_grep_make_target``) so the guarantee cannot drift between them.
    """
    return path.resolve().is_relative_to(root)


_SYMBOL_EXTENSIONS = (".py", ".go", ".ts", ".tsx", ".js")


def _grep_symbol(roots: list[Path], symbol: str) -> bool:
    """Return True if a function/method definition for *symbol* exists under
    any of the given roots.  Uses plain-text search (no subprocess) for the
    most common patterns:
      Python:  def <symbol>(
      Go:      func <symbol>(
      TypeScript/JS: function <symbol>(
    """
    # Build literal search strings for each language convention.
    needles = [
        f"def {symbol}(",
        f"func {symbol}(",
        f"function {symbol}(",
    ]
    for root in roots:
        for src_file in root.rglob("*"):
            if src_file.suffix not in _SYMBOL_EXTENSIONS or not _within(src_file, root):
                continue
            try:
                text = src_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(needle in text for needle in needles):
                return True
    return False


def _grep_make_target(root: Path, target: str) -> bool:
    """Return True if *target* appears as a Makefile target in root/Makefile."""
    makefile = root / "Makefile"
    if not makefile.exists() or not _within(makefile, root):
        return False
    try:
        text = makefile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    # Target line: starts at column 0, name, colon (optionally followed by deps)
    pattern = re.compile(r"^" + re.escape(target) + r"\s*:", re.MULTILINE)
    return bool(pattern.search(text))


def _resolve_roots(fact_roots_from_json: list[str], default_root: Path) -> list[Path]:
    """Return the list of root directories to search (all resolved)."""
    if fact_roots_from_json:
        return [Path(r).resolve() for r in fact_roots_from_json]
    return [default_root.resolve()]


def _escapes_all_roots(path_str: str, roots: list[Path]) -> bool:
    """True if *path_str* resolves outside EVERY declared root.

    Handles both absolute paths and relative paths that climb out via
    ``..``.  ``resolve()`` collapses ``..`` segments AND symlinks, so
    neither can smuggle a read outside the declared roots.  *roots* are
    already resolved by ``_resolve_roots``.
    """
    p = Path(path_str)
    if p.is_absolute():
        return not any(_within(p, root) for root in roots)
    return all(not _within(root / p, root) for root in roots)


def _find_file(rel_path: str, roots: list[Path]) -> Path | None:
    """Find the first existing file matching rel_path under any root.

    For relative paths that contain a directory separator, try the
    exact path under each root.  For bare filenames (no ``/``), also
    fall back to a recursive glob so that shorthand references like
    ``adopt.py`` resolve to ``bootstrap_lib/adopt.py``.

    Containment guard: a candidate is only returned if its resolved path
    stays under the root it was found in, so a ``../`` climb-out cannot
    be reported as found even if the escaped file happens to exist.
    """
    for root in roots:
        candidate = root / rel_path
        if candidate.exists() and _within(candidate, root):
            return candidate
    # Bare filename fallback: search recursively under each root.  Apply the
    # SAME containment guard as the exact-path branch so a buried symlink
    # pointing outside the root cannot be returned (skip non-contained matches
    # rather than only inspecting the first).
    if "/" not in rel_path:
        for root in roots:
            for match in sorted(root.rglob(rel_path)):
                if _within(match, root):
                    return match
    return None


def verify(facts_data: dict, default_root: Path) -> dict:
    """Verify all facts and return the structured result."""
    roots = _resolve_roots(facts_data.get("fact_roots", []), default_root)
    facts = facts_data.get("facts", [])

    verified: list[dict] = []
    failed: list[dict] = []
    unsupported_external: list[dict] = []
    not_verifiable: list[dict] = []

    for fact in facts:
        ftype = fact.get("type")

        if ftype == "file_ref":
            path_str = fact["path"]
            if _escapes_all_roots(path_str, roots):
                unsupported_external.append(
                    {
                        "fact": fact,
                        "detail": f"path resolves outside declared fact roots: {path_str}",
                    }
                )
                continue
            found = _find_file(path_str, roots)
            if found:
                verified.append({"fact": fact, "detail": f"exists: {found}"})
            else:
                failed.append({"fact": fact, "detail": f"file not found under roots: {path_str}"})

        elif ftype == "file_line_ref":
            path_str = fact["path"]
            lineno = fact["line"]
            if _escapes_all_roots(path_str, roots):
                unsupported_external.append(
                    {
                        "fact": fact,
                        "detail": f"path resolves outside declared fact roots: {path_str}",
                    }
                )
                continue
            found = _find_file(path_str, roots)
            if not found:
                failed.append({"fact": fact, "detail": f"file not found under roots: {path_str}"})
            else:
                n_lines = _count_lines(found)
                if n_lines < lineno:
                    failed.append(
                        {
                            "fact": fact,
                            "detail": (f"line {lineno} out of range: {found} has {n_lines} lines"),
                        }
                    )
                else:
                    verified.append(
                        {
                            "fact": fact,
                            "detail": (f"line {lineno} in range ({n_lines} total): {found}"),
                        }
                    )

        elif ftype == "symbol_ref":
            symbol = fact["symbol"]
            if _grep_symbol(roots, symbol):
                verified.append({"fact": fact, "detail": f"definition found for: {symbol}"})
            else:
                failed.append(
                    {
                        "fact": fact,
                        "detail": (
                            f"no definition found for symbol: {symbol} "
                            "(searched py/go/ts/js under declared roots)"
                        ),
                    }
                )

        elif ftype == "make_target_ref":
            target = fact["target"]
            found_in_any = any(_grep_make_target(root, target) for root in roots)
            if found_in_any:
                verified.append({"fact": fact, "detail": f"Makefile target exists: {target}"})
            else:
                failed.append(
                    {
                        "fact": fact,
                        "detail": (
                            f"Makefile target not found: {target} "
                            "(checked Makefile in each declared root)"
                        ),
                    }
                )

        elif ftype == "cli_flag_ref":
            not_verifiable.append(
                {
                    "fact": fact,
                    "detail": (
                        "cli_flag_ref: argparse semantic validation requires "
                        "importing the CLI under test — deferred"
                    ),
                }
            )

        else:
            not_verifiable.append({"fact": fact, "detail": f"unknown fact type: {ftype!r}"})

    return {
        "verified": verified,
        "failed": failed,
        "unsupported_external": unsupported_external,
        "not_verifiable": not_verifiable,
        "summary": {
            "verified": len(verified),
            "failed": len(failed),
            "unsupported_external": len(unsupported_external),
            "not_verifiable": len(not_verifiable),
        },
    }


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) < 2:
        print(
            "Usage: verify-plan-facts.py <facts-json-or--> <default-root>",
            file=sys.stderr,
        )
        return 1

    facts_src, default_root_str = argv[0], argv[1]
    default_root = Path(default_root_str).resolve()

    try:
        raw = sys.stdin.read() if facts_src == "-" else Path(facts_src).read_text(encoding="utf-8")
        facts_data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read/parse facts JSON: {exc}", file=sys.stderr)
        return 1

    result = verify(facts_data, default_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
