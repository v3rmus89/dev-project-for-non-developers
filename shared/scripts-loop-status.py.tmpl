#!/usr/bin/env python3
"""Loop-status classifier for the plan-review loop.

Reads plan-review iter output files from a review dir (default /tmp),
filters by the KEY field in the json verdict footer, and classifies the
loop state.

Usage:
  scripts/loop-status.py <KEY> [<review-dir>] [<plan-stem>]
  make loop-status PLAN_FILE=docs/plans/<file>.md

Output: STATUS: <classification> followed by a one-line rationale.

Exit codes:
  0  — any non-error status (needs-iter, converged, converged-with-polish,
       oscillating, stuck, regressed, no-iters)
  1  — malformed: last iter footer is missing or invalid JSON; or
       malformed-latest: with a <plan-stem>, the newest review for this plan
       is malformed (it would otherwise be skipped and read as no-iters)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _parse_footer(text: str) -> dict:
    """Extract and parse the last ```json code fence in *text*.

    Returns the parsed dict on success.
    Returns {"status": "footer-missing"} if no ```json fence is found.
    Returns {"status": "malformed"} if the fence exists but the content
    is invalid JSON or not a JSON object.
    """
    fences = list(re.finditer(r"```json\s*\n(.*?)```", text, re.DOTALL))
    if not fences:
        return {"status": "footer-missing"}
    raw = fences[-1].group(1)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "malformed"}
    if not isinstance(parsed, dict):
        return {"status": "malformed"}
    return parsed


def _iter_sort_key(path: Path) -> tuple[int, str]:
    """Order plan-review files by numeric iteration, then filename.

    Filenames are plan-review-<stem>-by-<actor>-iter-<N>.md.  A plain lexical
    sort puts iter-10/iter-11 before iter-2, so the "last" footer could be
    iter-9 once a loop reaches double-digit iterations — exactly the long-loop
    case loop-status exists to guard.  Parse N and sort on it; fall back to -1
    for any name that does not match (it sorts first, never masking a real iter).
    """
    m = re.search(r"-iter-(\d+)\.md$", path.name)
    return (int(m.group(1)) if m else -1, path.name)


def _load_iters(key: str, review_dir: Path) -> list[dict]:
    """Load plan-review iter files filtered by KEY.

    Globs plan-review-*-by-*-iter-*.md in review_dir.  Skips files
    whose footer is missing, malformed, or whose key field does not
    match *key*.  Returns footers in numeric-iteration order.
    """
    pattern = "plan-review-*-by-*-iter-*.md"
    files = sorted(review_dir.glob(pattern), key=_iter_sort_key)
    iters = []
    for path in files:
        try:
            text = path.read_text()
        except OSError:
            continue
        footer = _parse_footer(text)
        if footer.get("status") in ("footer-missing", "malformed"):
            continue
        if footer.get("key") != key:
            continue
        iters.append(footer)
    return iters


def _latest_file_for_stem(stem: str, review_dir: Path) -> Path | None:
    """Return the numerically-highest plan-review iter file for *stem*, or None.

    _load_iters drops files whose footer does not parse, so a malformed newest
    review is invisible when filtering by key.  The filename embeds the plan stem
    (plan-review-<stem>-by-<actor>-iter-<N>.md), so the latest review for a given
    plan can still be located by name — used to surface a malformed-latest status.
    """
    files = sorted(review_dir.glob(f"plan-review-{stem}-by-*-iter-*.md"), key=_iter_sort_key)
    return files[-1] if files else None


def classify(iters: list[dict]) -> tuple[str, str]:
    """Classify the review loop state from a sequence of parsed footers.

    Returns (status, rationale).  Status is one of:
      needs-iter, converged, converged-with-polish,
      oscillating, stuck, regressed, malformed, no-iters
    """
    if not iters:
        return "no-iters", "no plan-review iter files found for this key"

    last = iters[-1]
    if last.get("status") in ("footer-missing", "malformed"):
        return "malformed", f"last iter has status={last.get('status')}"

    counts = last.get("severity_counts", {})
    try:
        total = sum(int(v) for v in counts.values())
        c3 = int(counts.get("3", 0))
    except (TypeError, ValueError):
        total, c3 = 0, 0

    verdict = last.get("verdict", "")

    if verdict == "converged" and total == 0:
        return "converged", "reviewer called converged with no remaining findings"
    if c3 == 0 and total > 0:
        return (
            "converged-with-polish",
            f"no imp-3 findings remain (verdict={verdict}); fold or park remaining {total}",
        )

    for f in last.get("findings", []):
        if not f.get("fingerprint"):
            return "malformed", "finding missing required fingerprint field"

    def _fps(footer: dict) -> set[str]:
        return {
            f.get("fingerprint", "") for f in footer.get("findings", []) if f.get("fingerprint")
        }

    if len(iters) >= 2:
        curr_fps = _fps(last)
        prev_fps = _fps(iters[-2])

        if curr_fps and curr_fps == prev_fps:
            fps_str = ", ".join(sorted(curr_fps))
            return "stuck", f"same fingerprints as previous iter: {fps_str}"

        if len(iters) >= 3:
            ante_fps = _fps(iters[-3])
            reappeared = {fp for fp in curr_fps if fp in ante_fps and fp not in prev_fps}
            if reappeared:
                fps_str = ", ".join(sorted(reappeared))
                return "oscillating", f"fingerprints reappeared from iter N-2: {fps_str}"

        try:
            prev_c3 = int(iters[-2].get("severity_counts", {}).get("3", 0))
        except (TypeError, ValueError):
            prev_c3 = 0

        if c3 > prev_c3:
            return "regressed", f"imp-3 count grew from {prev_c3} to {c3}"

    return "needs-iter", f"imp-3={c3}, verdict={verdict}"


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("Usage: loop-status.py <KEY> [<review-dir>] [<plan-stem>]", file=sys.stderr)
        print(
            "  Usually invoked via: make loop-status PLAN_FILE=docs/plans/<file>.md",
            file=sys.stderr,
        )
        return 1

    key = argv[0]
    review_dir = Path(argv[1]) if len(argv) > 1 else Path("/tmp")
    stem = argv[2] if len(argv) > 2 else None

    iters = _load_iters(key, review_dir)
    status, rationale = classify(iters)

    # Surface a malformed LATEST review for THIS plan that _load_iters dropped.
    # _load_iters skips files whose footer is missing/malformed, so a malformed
    # newest review collapses to "no-iters".  With the plan stem we can still find
    # that file by name and report it distinctly instead of a misleading no-iters.
    if stem and status == "no-iters":
        latest = _latest_file_for_stem(stem, review_dir)
        if latest is not None:
            try:
                footer = _parse_footer(latest.read_text())
            except OSError:
                footer = {"status": "footer-missing"}
            if footer.get("status") in ("footer-missing", "malformed"):
                status = "malformed-latest"
                rationale = f"latest review for this plan is malformed: {latest.name}"

    print(f"STATUS: {status}")
    print(f"  {rationale}")

    if status in ("malformed", "malformed-latest"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
