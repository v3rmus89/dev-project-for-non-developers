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

from pathlib import Path
from typing import Literal, NamedTuple

Policy = Literal["WRITE", "SKIP", "OVERWRITE", "WRITE_NEW", "APPEND_MERGE"]
Confidence = Literal["high", "medium", "low"]


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


__all__ = [
    "AdoptionPlan",
    "Confidence",
    "PlannedFileAnalysis",
    "Policy",
    "PolicyRecommendation",
    "TargetMeta",
]
