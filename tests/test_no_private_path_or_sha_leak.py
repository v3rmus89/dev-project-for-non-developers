"""Leak guard for the public repo: no real home paths or real commit SHAs in docs.

Added after three leak classes survived the pre-publication scrub (see LESSONS.md
2026-07-27). The scrub's own residual check reused the substitution table's tokens,
so it could not fail. This guard searches a DIFFERENT axis — the *shape* of the
leak rather than the names — which is what actually caught the residue.

`tests/test_codex_jsonl_fixture.py` already guards home paths, but only for the
codex JSONL fixture; the leaks landed in docs/ and plan files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent

# Real macOS/Linux home paths. `/Users/me`, `/Users/example`, `/Users/<name>` and
# `/Users/you` are documented placeholders and stay allowed.
PLACEHOLDER_USERS = {"me", "example", "you", "user", "<name>"}
HOME_PATH_RE = re.compile(r"/(?:Users|home)/([A-Za-z0-9_.<>-]+)")

# A bare 40-hex string is a real git SHA. Synthetic all-zero/all-same runs used as
# test fixtures are fine; anything else in prose is a real commit.
SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")

SCANNED_DIRS = ["docs", "."]


def _docs_and_root_markdown() -> list[Path]:
    seen: dict[Path, None] = {}
    for md in sorted((SKILL_ROOT / "docs").rglob("*.md")):
        seen[md] = None
    for md in sorted(SKILL_ROOT.glob("*.md")):
        seen[md] = None
    return list(seen)


@pytest.mark.parametrize("path", _docs_and_root_markdown(), ids=lambda p: p.name)
def test_no_real_home_paths_in_docs(path: Path):
    """`/Users/<real-name>/...` leaks the author's username and home topology."""
    offenders = [
        m.group(0)
        for m in HOME_PATH_RE.finditer(path.read_text())
        if m.group(1) not in PLACEHOLDER_USERS
    ]
    assert not offenders, (
        f"{path.relative_to(SKILL_ROOT)} contains real home path(s): {sorted(set(offenders))}. "
        f"Use `~/code/...` (parse_fact_roots expands the tilde, so Fact-roots "
        f"blocks stay machine-absolute) or a placeholder from {sorted(PLACEHOLDER_USERS)}."
    )


@pytest.mark.parametrize("path", _docs_and_root_markdown(), ids=lambda p: p.name)
def test_no_real_commit_shas_in_docs(path: Path):
    """A full 40-hex SHA in prose points at a commit in a private repo."""
    offenders = [s for s in SHA_RE.findall(path.read_text()) if len(set(s)) > 1]
    assert not offenders, (
        f"{path.relative_to(SKILL_ROOT)} contains real commit SHA(s): {sorted(set(offenders))}. "
        "Use a `<original-sha>`-style placeholder, or an abbreviated 7-char hash."
    )
