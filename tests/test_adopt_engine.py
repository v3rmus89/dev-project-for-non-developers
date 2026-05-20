"""Unit tests for `bootstrap_lib/adopt.py`.

Step 1 (scaffold): verify the data classes' shape — class-syntax NamedTuple
preserves Literal[...] types instead of stringifying them, which matters for
introspection and later type-narrowing in `recommend_policy`. This test pins
that contract.

Subsequent steps will add rule-by-rule `recommend_policy` tests + analyze_target
tests + format_recommendation_report golden-output tests per Bucket D row.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import get_type_hints

import pytest

from bootstrap_lib.adopt import (
    AdoptionPlan,
    PlannedFileAnalysis,
    PolicyRecommendation,
    TargetMeta,
    _compute_target_meta,
)


def _git_init(path: Path) -> None:
    """Initialize a minimal git repo for ignored_by_git tests."""
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "init",
        ],
        cwd=str(path),
        check=True,
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


class TestComputeTargetMeta:
    """`_compute_target_meta` — file inspection layer producing TargetMeta."""

    def test_missing_file_returns_exists_false(self, tmp_path: Path) -> None:
        meta = _compute_target_meta(tmp_path, "nonexistent.txt")
        assert meta.exists is False
        assert meta.size == 0
        assert meta.sha256 is None
        assert meta.line_count is None

    def test_existing_file_sha256_matches_content(self, tmp_path: Path) -> None:
        content = b"hello world\n"
        (tmp_path / "f.txt").write_bytes(content)
        meta = _compute_target_meta(tmp_path, "f.txt")
        assert meta.exists is True
        assert meta.size == len(content)
        assert meta.sha256 == hashlib.sha256(content).hexdigest()

    def test_empty_file_line_count_zero(self, tmp_path: Path) -> None:
        (tmp_path / "empty.txt").write_bytes(b"")
        meta = _compute_target_meta(tmp_path, "empty.txt")
        assert meta.size == 0
        assert meta.line_count == 0

    def test_unterminated_last_line_counted(self, tmp_path: Path) -> None:
        # 3 lines: two newline-terminated + one without trailing newline.
        (tmp_path / "f.txt").write_bytes(b"a\nb\nc")
        meta = _compute_target_meta(tmp_path, "f.txt")
        assert meta.line_count == 3

    def test_markdown_heading_count(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_bytes(
            b"# Title\n\nsome text\n\n## Section\n\n### Subsection\nnot a heading: #foo\n"
        )
        meta = _compute_target_meta(tmp_path, "doc.md")
        assert meta.heading_count == 3

    def test_non_markdown_heading_count_none(self, tmp_path: Path) -> None:
        (tmp_path / "f.txt").write_bytes(b"# Not markdown\n")
        meta = _compute_target_meta(tmp_path, "f.txt")
        assert meta.heading_count is None

    def test_pyproject_dependency_groups_detected(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_bytes(
            b'[project]\nname = "x"\n\n[dependency-groups]\ndev = ["pytest"]\n'
        )
        meta = _compute_target_meta(tmp_path, "pyproject.toml")
        assert meta.has_dependency_groups is True

    def test_pyproject_without_dependency_groups(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_bytes(b'[project]\nname = "x"\n')
        meta = _compute_target_meta(tmp_path, "pyproject.toml")
        assert meta.has_dependency_groups is False

    def test_pyproject_malformed_toml_returns_false(self, tmp_path: Path) -> None:
        # Defensive: malformed TOML must not crash; returns False so rule (h)
        # SKIP/manual_review_needed=True kicks in (the safe default).
        (tmp_path / "pyproject.toml").write_bytes(b"[project\nname = broken\n")
        meta = _compute_target_meta(tmp_path, "pyproject.toml")
        assert meta.has_dependency_groups is False

    def test_python_version_pin_extracted(self, tmp_path: Path) -> None:
        (tmp_path / ".python-version").write_bytes(b"3.12\n")
        meta = _compute_target_meta(tmp_path, ".python-version")
        assert meta.python_version_pin == "3.12"

    def test_python_version_pin_whitespace_only_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / ".python-version").write_bytes(b"   \n")
        meta = _compute_target_meta(tmp_path, ".python-version")
        assert meta.python_version_pin is None

    def test_ignored_by_git_for_missing_file(self, tmp_path: Path) -> None:
        """Rule (a0)'s precondition: missing file + git ignores it."""
        _git_init(tmp_path)
        (tmp_path / ".gitignore").write_text("AGENTS.md\n")
        meta = _compute_target_meta(tmp_path, "AGENTS.md")
        assert meta.exists is False
        assert meta.ignored_by_git is not None
        assert "AGENTS.md" in meta.ignored_by_git

    def test_not_ignored_when_no_gitignore_match(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        (tmp_path / ".gitignore").write_text("unrelated.txt\n")
        meta = _compute_target_meta(tmp_path, "AGENTS.md")
        assert meta.ignored_by_git is None

    def test_ignored_by_git_none_for_existing_file(self, tmp_path: Path) -> None:
        """ignored_by_git is only meaningful for planned CREATEs (missing files).
        For existing files the field is None — rule (a0) doesn't apply."""
        _git_init(tmp_path)
        (tmp_path / ".gitignore").write_text("AGENTS.md\n")
        (tmp_path / "AGENTS.md").write_text("contents\n")
        meta = _compute_target_meta(tmp_path, "AGENTS.md")
        assert meta.exists is True
        assert meta.ignored_by_git is None

    def test_ignored_by_git_none_outside_git_repo(self, tmp_path: Path) -> None:
        """Defensive: non-git directories return None (not a crash)."""
        meta = _compute_target_meta(tmp_path, "AGENTS.md")
        assert meta.ignored_by_git is None
