"""Adoption-mode analyze + recommend engine for `--mode=adopt`.

Per the merged Plan PR #7 (`docs/plans/2026-05-19-skill-pr7-hybrid-trial-adoption-mode.md`),
this module ships the per-file analyze-then-decide-with-owner UX:

    1. analyze_target(target_root, planned_files) -> AdoptionPlan
    2. recommend_policy(rel_path, target_path, skill_content, target_meta)
       -> PolicyRecommendation
    3. format_recommendation_report(plan) -> str  (user-facing report)

The decide phase lives in `bootstrap_lib/cli.py` (`_interactive_decide`); the
apply phase lives in `manifest.plan_adoption_entries` +
`cli._apply_adoption_writes`. This module is the analyze + recommend layer.

All data classes are NamedTuple via class-syntax per PR #6 Claude iter-2 #2
lesson (functional NamedTuple stores annotations as strings; class-syntax does
not — matters for `Literal[...]` types).
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Literal, NamedTuple

Policy = Literal["WRITE", "SKIP", "OVERWRITE", "WRITE_NEW", "APPEND_MERGE"]
Confidence = Literal["high", "medium", "low"]

# Files we treat as markdown for heading-count purposes.
_MARKDOWN_EXTS = frozenset({".md", ".markdown"})

# Regex for a markdown heading line (start of line, 1-6 '#', then space or EOL).
_MD_HEADING_RE = re.compile(rb"^#{1,6}(?:\s|$)", re.MULTILINE)


class TargetMeta(NamedTuple):
    """Derived metadata about a target file.

    Per Scope #11 privacy boundary: NO raw target content fields. Only
    derived markers (line count, heading count, structural flags, hashes).
    The user-facing recommendation report MUST NOT contain raw target text.
    """

    exists: bool
    size: int
    sha256: str | None  # None when file doesn't exist
    line_count: int | None  # None when not a text file or doesn't exist
    heading_count: int | None  # markdown only; count of '^#' lines
    has_dependency_groups: bool  # pyproject.toml; True if [dependency-groups]
    python_version_pin: str | None  # .python-version's pinned version, or None
    ignored_by_git: str | None  # `git check-ignore -v` match line; None if not ignored


class PolicyRecommendation(NamedTuple):
    """A per-file recommendation produced by `recommend_policy`.

    Per Scope #6 single-matrix consent contract:
      - `manual_review_needed=False`: `--auto-accept-recommendations` auto-applies
        without a prompt; under `--non-interactive`, still auto-applies.
      - `manual_review_needed=True`: always needs an interactive prompt; under
        `--non-interactive` becomes exit-2.
    """

    policy: Policy
    reason: str
    confidence: Confidence
    manual_review_needed: bool


class PlannedFileAnalysis(NamedTuple):
    """The analyze-phase product for a single planned file.

    Pairs the per-file `TargetMeta` with the `PolicyRecommendation` derived from
    Scope #5 rules. AdoptionPlan is a sequence of these.
    """

    rel_path: str
    target_meta: TargetMeta
    recommendation: PolicyRecommendation


class AdoptionPlan(NamedTuple):
    """The full analyze-phase product across all planned files.

    Consumed by `format_recommendation_report` (user-facing report) and by
    `manifest.plan_adoption_entries` (apply-phase wiring).
    """

    target_root: Path
    analyses: tuple[PlannedFileAnalysis, ...]


def _check_ignored_by_git(target_root: Path, rel_path: str) -> str | None:
    """Run `git check-ignore -v -- <rel_path>` in target_root.

    Returns the matching `.gitignore` line (e.g. `.gitignore:48:AGENTS.md`) if
    the path is ignored, else None. Returns None for non-git directories or
    any subprocess failure (defensive: missing git, permissions, etc.).

    Per plan rule (a0): a planned CREATE that is ignored by git → recommended
    SKIP with manual_review_needed=True (silent SKIP loses planned file, silent
    WRITE writes invisible-to-git file — owner MUST decide).
    """
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-v", "--", rel_path],
            cwd=str(target_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        # git not installed, target_root not a directory, etc.
        return None
    # Exit 0 = ignored; output is "<source>:<line>:<pattern>\t<path>".
    # Exit 1 = not ignored. Exit 128 = not a git repo.
    if result.returncode == 0 and result.stdout:
        # Return just the "source:line:pattern" part for stable evidence.
        first_line = result.stdout.splitlines()[0]
        return first_line.split("\t", 1)[0] if "\t" in first_line else first_line
    return None


def _python_version_pin(content_bytes: bytes) -> str | None:
    """Extract the Python version pin from `.python-version` contents.

    The file convention is a single trimmed version string like `3.12` or
    `3.12.7`. Returns None for empty/whitespace-only files.
    """
    text = content_bytes.decode("utf-8", errors="replace").strip()
    return text if text else None


def _has_dependency_groups_table(content_bytes: bytes) -> bool:
    """Return True if `pyproject.toml` content has a `[dependency-groups]` table.

    Used by rule (g): non-trivial pyproject.toml (with deps, tool config, or
    dependency-groups) → SKIP with manual_review_needed=True.

    Defensive: malformed TOML returns False (callers fall through to rule (h)
    SKIP with manual_review_needed=True anyway, which is the safe default).
    """
    try:
        data = tomllib.loads(content_bytes.decode("utf-8", errors="replace"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return False
    return "dependency-groups" in data and isinstance(data["dependency-groups"], dict)


def _compute_target_meta(target_root: Path, rel_path: str) -> TargetMeta:
    """Inspect a single target file and produce its TargetMeta.

    All fields are derived — NO raw target content is stored (per Scope #11
    privacy boundary). Hashes, counts, structural flags only.

    `ignored_by_git` is populated only when the file doesn't exist (the rule
    (a0) precondition is "planned CREATE that is ignored"). For existing files
    the value is None — rule (a0) doesn't apply.
    """
    full_path = target_root / rel_path
    exists = full_path.is_file()

    if not exists:
        return TargetMeta(
            exists=False,
            size=0,
            sha256=None,
            line_count=None,
            heading_count=None,
            has_dependency_groups=False,
            python_version_pin=None,
            ignored_by_git=_check_ignored_by_git(target_root, rel_path),
        )

    content = full_path.read_bytes()
    size = len(content)
    sha256 = hashlib.sha256(content).hexdigest()

    # Line count: count of newlines + 1 if last line has content
    # (handles both newline-terminated and not-terminated files).
    if size == 0:
        line_count: int | None = 0
    else:
        line_count = content.count(b"\n") + (0 if content.endswith(b"\n") else 1)

    ext = full_path.suffix.lower()
    is_markdown = ext in _MARKDOWN_EXTS
    heading_count: int | None = len(_MD_HEADING_RE.findall(content)) if is_markdown else None

    has_dependency_groups = False
    python_version_pin: str | None = None
    if full_path.name == "pyproject.toml":
        has_dependency_groups = _has_dependency_groups_table(content)
    elif full_path.name == ".python-version":
        python_version_pin = _python_version_pin(content)

    return TargetMeta(
        exists=True,
        size=size,
        sha256=sha256,
        line_count=line_count,
        heading_count=heading_count,
        has_dependency_groups=has_dependency_groups,
        python_version_pin=python_version_pin,
        ignored_by_git=None,  # only populated for missing files; existing files don't apply rule (a0)
    )


__all__ = [
    "AdoptionPlan",
    "Confidence",
    "PlannedFileAnalysis",
    "Policy",
    "PolicyRecommendation",
    "TargetMeta",
    "_compute_target_meta",  # exported for tests
]
