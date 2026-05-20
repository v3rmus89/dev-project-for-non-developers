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
    recommend_policy,
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


def _meta(**overrides) -> TargetMeta:
    """Build a TargetMeta with sensible existing-file defaults; override as needed."""
    defaults = dict(
        exists=True,
        size=42,
        sha256="targetsha",
        line_count=5,
        heading_count=None,
        has_dependency_groups=False,
        python_version_pin=None,
        ignored_by_git=None,
    )
    defaults.update(overrides)
    return TargetMeta(**defaults)  # type: ignore[arg-type]


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class TestRecommendPolicyRules:
    """Scope #5 rules a0/a..h, one test per rule. Each asserts
    `manual_review_needed` explicitly per Bucket D contract."""

    # ─── Rule (a0): missing AND ignored_by_git → SKIP, manual_review=True ───
    def test_rule_a0_missing_and_ignored_returns_skip_manual_review(self, tmp_path: Path) -> None:
        meta = _meta(
            exists=False,
            size=0,
            sha256=None,
            line_count=None,
            ignored_by_git=".gitignore:1:AGENTS.md",
        )
        rec = recommend_policy("AGENTS.md", tmp_path / "AGENTS.md", b"skill content\n", meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True
        assert "gitignores" in rec.reason

    # ─── Rule (a): missing AND not ignored → WRITE/safe-create ───
    def test_rule_a_missing_and_not_ignored_returns_write(self, tmp_path: Path) -> None:
        meta = _meta(exists=False, size=0, sha256=None, line_count=None, ignored_by_git=None)
        rec = recommend_policy("new.txt", tmp_path / "new.txt", b"skill content\n", meta)
        assert rec.policy == "WRITE"
        assert rec.manual_review_needed is False

    # ─── Rule (b): empty / whitespace-only → OVERWRITE ───
    def test_rule_b_empty_file_returns_overwrite(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.txt"
        target.write_bytes(b"")
        meta = _meta(exists=True, size=0, sha256=_sha(b""), line_count=0)
        rec = recommend_policy("empty.txt", target, b"skill content\n", meta)
        assert rec.policy == "OVERWRITE"
        assert rec.manual_review_needed is False

    def test_rule_b_whitespace_only_returns_overwrite(self, tmp_path: Path) -> None:
        content = b"  \n\t\n  \n"
        target = tmp_path / "ws.txt"
        target.write_bytes(content)
        meta = _meta(exists=True, size=len(content), sha256=_sha(content), line_count=3)
        rec = recommend_policy("ws.txt", target, b"skill\n", meta)
        assert rec.policy == "OVERWRITE"
        assert rec.manual_review_needed is False

    # ─── Rule (c): byte-for-byte match → SKIP/no-op ───
    def test_rule_c_byte_identical_returns_skip(self, tmp_path: Path) -> None:
        content = b"identical content\n"
        target = tmp_path / "f.txt"
        target.write_bytes(content)
        meta = _meta(exists=True, size=len(content), sha256=_sha(content))
        rec = recommend_policy("f.txt", target, content, meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is False
        assert "byte-for-byte" in rec.reason

    # ─── Rule (d): .gitignore line-merge OR all-present-collapse ───
    def test_rule_d_gitignore_missing_patterns_returns_append_merge(self, tmp_path: Path) -> None:
        target_content = b"venv/\n*.pyc\n"
        skill_content = b"venv/\n*.pyc\n__pycache__/\n.env\n"
        target = tmp_path / ".gitignore"
        target.write_bytes(target_content)
        meta = _meta(exists=True, size=len(target_content), sha256=_sha(target_content))
        rec = recommend_policy(".gitignore", target, skill_content, meta)
        assert rec.policy == "APPEND_MERGE"
        assert rec.manual_review_needed is False
        # 2 patterns missing
        assert "2" in rec.reason

    def test_rule_d_gitignore_all_present_returns_skip(self, tmp_path: Path) -> None:
        target_content = b"venv/\n*.pyc\n__pycache__/\n.env\nextra_user_pattern/\n"
        skill_content = b"venv/\n*.pyc\n"  # both already in target
        target = tmp_path / ".gitignore"
        target.write_bytes(target_content)
        meta = _meta(exists=True, size=len(target_content), sha256=_sha(target_content))
        rec = recommend_policy(".gitignore", target, skill_content, meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is False
        assert "already present" in rec.reason

    def test_rule_d_gitignore_comments_and_blanks_ignored(self, tmp_path: Path) -> None:
        """Comments + blank lines aren't patterns; not counted toward missing set."""
        target_content = b"venv/\n*.pyc\n"
        skill_content = b"# skill header comment\n\nvenv/\n*.pyc\n"  # only comments+blanks "new"
        target = tmp_path / ".gitignore"
        target.write_bytes(target_content)
        meta = _meta(exists=True, size=len(target_content), sha256=_sha(target_content))
        rec = recommend_policy(".gitignore", target, skill_content, meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is False

    # ─── Rule (e): .python-version match-or-skip ───
    def test_rule_e_python_version_match_returns_skip(self, tmp_path: Path) -> None:
        """Same pin, BYTE-DIFFERENT contents (target has no trailing newline)
        so rule (c) doesn't fire first — exercises (e)'s match branch."""
        target_content = b"3.12"  # no trailing newline; pin still parses to "3.12"
        target = tmp_path / ".python-version"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            python_version_pin="3.12",
        )
        rec = recommend_policy(".python-version", target, b"3.12\n", meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is False
        assert "same Python version" in rec.reason

    def test_rule_e_python_version_mismatch_returns_skip_with_note(self, tmp_path: Path) -> None:
        target_content = b"3.10\n"
        target = tmp_path / ".python-version"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            python_version_pin="3.10",
        )
        rec = recommend_policy(".python-version", target, b"3.12\n", meta)
        assert rec.policy == "SKIP"
        # NOT (h)'s True — rule (e) explicitly handles mismatches as safe SKIP.
        assert rec.manual_review_needed is False
        assert "different Python version" in rec.reason

    # ─── Rule (f): domain markdown non-trivial → WRITE_NEW ───
    def test_rule_f_markdown_domain_long_file_returns_write_new(self, tmp_path: Path) -> None:
        """>20 lines trips non-trivial → WRITE_NEW with manual_review=True."""
        target_content = b"# Title\n" + b"line\n" * 25
        target = tmp_path / "CLAUDE.md"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            line_count=26,
            heading_count=1,
        )
        rec = recommend_policy("CLAUDE.md", target, b"# Skill template\n", meta)
        assert rec.policy == "WRITE_NEW"
        assert rec.manual_review_needed is True
        assert "domain content" in rec.reason

    def test_rule_f_markdown_domain_custom_heading_returns_write_new(self, tmp_path: Path) -> None:
        """≤20 lines but a heading not in skill → WRITE_NEW."""
        target_content = b"# Title\n\nshort doc\n\n## My Custom Section\n\nbody\n"
        skill_content = b"# Title\n\nshort doc\n"
        target = tmp_path / "AGENTS.md"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            line_count=7,
            heading_count=2,
        )
        rec = recommend_policy("AGENTS.md", target, skill_content, meta)
        assert rec.policy == "WRITE_NEW"
        assert rec.manual_review_needed is True

    def test_rule_f_markdown_domain_trivial_falls_through_to_h(self, tmp_path: Path) -> None:
        """Trivial CLAUDE.md (≤20 lines + same heading set) → falls through to (h)
        → SKIP/manual_review=True. (f) doesn't fire on trivial."""
        target_content = b"# Title\n\nshort body\n"
        skill_content = b"# Title\n\ndifferent body\n"  # same heading set
        target = tmp_path / "CLAUDE.md"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            line_count=3,
            heading_count=1,
        )
        rec = recommend_policy("CLAUDE.md", target, skill_content, meta)
        # Falls through to (h) — still SKIP/manual_review=True.
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True

    # ─── Rule (g): pyproject.toml non-trivial → SKIP/manual_review ───
    def test_rule_g_pyproject_dependency_groups_returns_skip(self, tmp_path: Path) -> None:
        target_content = b'[project]\nname = "x"\n\n[dependency-groups]\ndev = ["pytest"]\n'
        target = tmp_path / "pyproject.toml"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            has_dependency_groups=True,
            line_count=5,
        )
        rec = recommend_policy("pyproject.toml", target, b'[project]\nname = "y"\n', meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True

    def test_rule_g_pyproject_tool_table_returns_skip(self, tmp_path: Path) -> None:
        target_content = b'[project]\nname = "x"\n\n[tool.ruff]\nline-length = 100\n'
        target = tmp_path / "pyproject.toml"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            line_count=5,
        )
        rec = recommend_policy("pyproject.toml", target, b'[project]\nname = "y"\n', meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True

    def test_rule_g_pyproject_project_dependencies_returns_skip(self, tmp_path: Path) -> None:
        target_content = b'[project]\nname = "x"\ndependencies = ["requests"]\n'
        target = tmp_path / "pyproject.toml"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            line_count=3,
        )
        rec = recommend_policy("pyproject.toml", target, b'[project]\nname = "y"\n', meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True

    def test_rule_g_pyproject_trivial_falls_through_to_h(self, tmp_path: Path) -> None:
        """Trivial pyproject.toml (no deps/tool/dep-groups) → falls through to (h)."""
        target_content = b'[project]\nname = "x"\nversion = "1.0"\n'
        target = tmp_path / "pyproject.toml"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            line_count=3,
        )
        rec = recommend_policy("pyproject.toml", target, b"different\n", meta)
        # Falls through to (h) — still SKIP/manual_review=True (safe default).
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True

    # ─── Rule (h): DEFAULT for any existing non-empty unrecognized file ───
    def test_rule_h_default_unknown_existing_file_returns_skip_manual_review(
        self, tmp_path: Path
    ) -> None:
        """The core safety guarantee — Codex iter-1 #3: must never recommend WRITE
        on an existing file (WRITE's restore semantics delete the path, which
        would let `--restore` silently delete a pre-existing user file)."""
        target_content = b"some custom content here\n"
        target = tmp_path / "Makefile"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            line_count=1,
        )
        rec = recommend_policy("Makefile", target, b"different\n", meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True
        assert rec.policy != "WRITE", (
            "rule (h) must NEVER recommend WRITE on an existing file — "
            "WRITE's restore deletes the path (Bucket B row a)"
        )


class TestRecommendPolicyPrecedence:
    """Scope #5 says rules are evaluated in order; first match wins.
    Tests pin each precedence boundary that could regress if rules were reordered."""

    def test_a0_fires_before_a(self, tmp_path: Path) -> None:
        """Missing + ignored → (a0) SKIP/manual=True, NOT (a) WRITE/manual=False."""
        meta = _meta(
            exists=False,
            size=0,
            sha256=None,
            line_count=None,
            ignored_by_git=".gitignore:1:AGENTS.md",
        )
        rec = recommend_policy("AGENTS.md", tmp_path / "AGENTS.md", b"skill\n", meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True

    def test_a_fires_before_b_for_missing(self, tmp_path: Path) -> None:
        """Missing (size=0 metadata) → (a) WRITE, NOT (b) OVERWRITE.
        Rule (a) wins because (b) requires `exists=True`."""
        meta = _meta(exists=False, size=0, sha256=None, line_count=None)
        rec = recommend_policy("new.txt", tmp_path / "new.txt", b"skill\n", meta)
        assert rec.policy == "WRITE"
        assert rec.manual_review_needed is False

    def test_b_fires_before_c_for_empty_target(self, tmp_path: Path) -> None:
        """Empty target + matching skill — (b) OVERWRITE wins over (c) SKIP.
        (Both produce different outcomes; b's OVERWRITE is the load-bearing one
        because empty→empty is technically byte-equal but we still want a
        manifest entry so restore writes the empty back.)"""
        target = tmp_path / "empty.txt"
        target.write_bytes(b"")
        meta = _meta(exists=True, size=0, sha256=_sha(b""), line_count=0)
        # Skill content is also empty → SHA-equal. (c) would say SKIP; (b) wins.
        rec = recommend_policy("empty.txt", target, b"", meta)
        assert rec.policy == "OVERWRITE"
        assert rec.manual_review_needed is False

    def test_b_fires_before_f_for_empty_markdown_domain(self, tmp_path: Path) -> None:
        """Empty CLAUDE.md → (b) OVERWRITE wins over (f) WRITE_NEW.
        Empty domain file isn't "non-trivial" — no domain content to preserve."""
        target = tmp_path / "CLAUDE.md"
        target.write_bytes(b"")
        meta = _meta(exists=True, size=0, sha256=_sha(b""), line_count=0, heading_count=0)
        rec = recommend_policy("CLAUDE.md", target, b"# Skill\n", meta)
        assert rec.policy == "OVERWRITE"
        assert rec.manual_review_needed is False

    def test_c_fires_before_d_for_byte_identical_gitignore(self, tmp_path: Path) -> None:
        """Byte-identical .gitignore → (c) SKIP fires before (d) "all-present-SKIP".
        Both produce SKIP/manual_review=False, but (c) is the more general
        reason; pinning this avoids a future reorder collapsing both branches."""
        content = b"venv/\n*.pyc\n"
        target = tmp_path / ".gitignore"
        target.write_bytes(content)
        meta = _meta(exists=True, size=len(content), sha256=_sha(content))
        rec = recommend_policy(".gitignore", target, content, meta)
        assert rec.policy == "SKIP"
        assert "byte-for-byte" in rec.reason

    def test_c_fires_before_e_for_byte_identical_python_version(self, tmp_path: Path) -> None:
        """Byte-identical .python-version → (c) fires, NOT (e)."""
        content = b"3.12\n"
        target = tmp_path / ".python-version"
        target.write_bytes(content)
        meta = _meta(
            exists=True,
            size=len(content),
            sha256=_sha(content),
            python_version_pin="3.12",
        )
        rec = recommend_policy(".python-version", target, content, meta)
        assert rec.policy == "SKIP"
        assert "byte-for-byte" in rec.reason

    def test_e_fires_before_h_for_python_version_mismatch(self, tmp_path: Path) -> None:
        """Mismatched .python-version → (e) SKIP/manual=False, NOT (h) SKIP/manual=True.
        (e) explicitly handles mismatches as safe-SKIP without manual review;
        if reordered, (h) would incorrectly require manual review."""
        content = b"3.10\n"
        target = tmp_path / ".python-version"
        target.write_bytes(content)
        meta = _meta(
            exists=True,
            size=len(content),
            sha256=_sha(content),
            python_version_pin="3.10",
            line_count=1,
        )
        rec = recommend_policy(".python-version", target, b"3.12\n", meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is False  # (h) would be True

    def test_f_fires_before_h_for_nontrivial_domain_markdown(self, tmp_path: Path) -> None:
        """Non-trivial CLAUDE.md → (f) WRITE_NEW, NOT (h) SKIP.
        Both have manual_review=True, but (f)'s WRITE_NEW is the load-bearing
        outcome — it WRITES the .new file; (h) writes nothing."""
        target_content = b"# Title\n" + b"line\n" * 25
        target = tmp_path / "CLAUDE.md"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            line_count=26,
            heading_count=1,
        )
        rec = recommend_policy("CLAUDE.md", target, b"# Skill\n", meta)
        assert rec.policy == "WRITE_NEW"
        assert rec.manual_review_needed is True

    def test_g_fires_before_h_for_nontrivial_pyproject(self, tmp_path: Path) -> None:
        """Non-trivial pyproject.toml → (g) SKIP with explicit reason, NOT (h)."""
        target_content = b'[project]\nname = "x"\n\n[tool.ruff]\nline-length = 100\n'
        target = tmp_path / "pyproject.toml"
        target.write_bytes(target_content)
        meta = _meta(
            exists=True,
            size=len(target_content),
            sha256=_sha(target_content),
            line_count=5,
        )
        rec = recommend_policy("pyproject.toml", target, b"different\n", meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True
        # (g)'s reason mentions the actual signal; (h)'s reason wouldn't.
        assert "pyproject.toml" in rec.reason or "tool" in rec.reason
