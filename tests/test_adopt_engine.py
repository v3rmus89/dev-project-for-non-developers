"""Unit tests for `bootstrap_lib/adopt.py`.

Step 1 (scaffold): verify the data classes' shape — class-syntax NamedTuple
preserves Literal[...] types instead of stringifying them, which matters for
introspection and later type-narrowing in `recommend_policy`. This test pins
that contract.

Subsequent steps will add rule-by-rule `recommend_policy` tests + analyze_target
tests + format_recommendation_report golden-output tests per Bucket D row.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_type_hints

import pytest

from bootstrap_lib.adopt import (
    AdoptionPlan,
    PlannedFileAnalysis,
    PolicyRecommendation,
    TargetMeta,
)


class TestDataClassShape:
    """The NamedTuple class-syntax contract — Literal[...] survives intact."""

    def test_target_meta_fields_present(self) -> None:
        meta = TargetMeta(
            exists=False,
            size=0,
            sha256=None,
            line_count=None,
            heading_count=None,
            has_dependency_groups=False,
            python_version_pin=None,
            ignored_by_git=None,
        )
        assert meta.exists is False
        assert meta.sha256 is None
        assert meta.ignored_by_git is None

    def test_policy_recommendation_literal_type_preserved(self) -> None:
        """Class-syntax NamedTuple keeps `Literal[...]` as a real type object,
        not a string (the iter-2 lesson from PR #6)."""
        hints = get_type_hints(PolicyRecommendation)
        # If we'd used functional NamedTuple, this would be a string "Policy".
        # Class-syntax gives us the resolved Literal[...] type.
        assert hints["policy"].__origin__ is not None or hasattr(hints["policy"], "__args__")

    def test_policy_recommendation_accepts_each_policy_string(self) -> None:
        # All 5 policy strings should be constructable (no runtime enforcement,
        # but the type-checker would catch invalid ones).
        for policy in ("WRITE", "SKIP", "OVERWRITE", "WRITE_NEW", "APPEND_MERGE"):
            rec = PolicyRecommendation(
                policy=policy,  # type: ignore[arg-type]
                reason="test",
                confidence="high",
                manual_review_needed=False,
            )
            assert rec.policy == policy

    def test_planned_file_analysis_composes_meta_and_recommendation(self) -> None:
        meta = TargetMeta(
            exists=True,
            size=42,
            sha256="abc",
            line_count=3,
            heading_count=0,
            has_dependency_groups=False,
            python_version_pin=None,
            ignored_by_git=None,
        )
        rec = PolicyRecommendation(
            policy="SKIP",
            reason="byte-identical",
            confidence="high",
            manual_review_needed=False,
        )
        analysis = PlannedFileAnalysis(rel_path="CLAUDE.md", target_meta=meta, recommendation=rec)
        assert analysis.rel_path == "CLAUDE.md"
        assert analysis.target_meta.size == 42
        assert analysis.recommendation.policy == "SKIP"

    def test_adoption_plan_holds_tuple_of_analyses(self) -> None:
        plan = AdoptionPlan(target_root=Path("/tmp/x"), analyses=())
        assert plan.target_root == Path("/tmp/x")
        assert plan.analyses == ()

    def test_namedtuples_are_immutable(self) -> None:
        """NamedTuple immutability is part of the contract — recommendations
        cannot be mutated after `_interactive_decide` returns."""
        rec = PolicyRecommendation(
            policy="SKIP", reason="x", confidence="low", manual_review_needed=False
        )
        with pytest.raises(AttributeError):
            rec.policy = "WRITE"  # type: ignore[misc]
