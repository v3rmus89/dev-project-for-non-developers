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
    AdoptionCollisionError,
    AdoptionPlan,
    PlannedFileAnalysis,
    PolicyRecommendation,
    TargetMeta,
    _compute_target_meta,
    _is_dotclaude_class_pattern,
    analyze_target,
    compute_append_merge_bytes,
    format_recommendation_report,
    recommend_policy,
    scan_shadowing_configs,
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
        """Rule (a0)'s precondition: missing file + git ignores it. The result
        format is `<source>:<line>` only — the matching pattern is dropped to
        honour Scope #11's privacy boundary (patterns can be path-revealing)."""
        _git_init(tmp_path)
        (tmp_path / ".gitignore").write_text("AGENTS.md\n")
        meta = _compute_target_meta(tmp_path, "AGENTS.md")
        assert meta.exists is False
        assert meta.ignored_by_git is not None
        # `.gitignore:1` (source + line), NOT `.gitignore:1:AGENTS.md` (with pattern).
        assert meta.ignored_by_git == ".gitignore:1"
        # The pattern (AGENTS.md) must NOT be present in the captured reference.
        assert "AGENTS.md" not in meta.ignored_by_git

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

    # ─── Rule (a0): missing AND ignored_by_git ───
    # Not cleanly NEUTRALIZE-able (neutralize_eligible defaults False) → SKIP.
    def test_rule_a0_missing_and_ignored_returns_skip_manual_review(self, tmp_path: Path) -> None:
        meta = _meta(
            exists=False,
            size=0,
            sha256=None,
            line_count=None,
            ignored_by_git=".gitignore:1",
        )
        rec = recommend_policy("AGENTS.md", tmp_path / "AGENTS.md", b"skill content\n", meta)
        assert rec.policy == "SKIP"
        assert rec.manual_review_needed is True
        assert "gitignores" in rec.reason

    # Cleanly NEUTRALIZE-able ignore → NEUTRALIZE (the un-ignore block can fix it).
    def test_rule_a0_dotclaude_class_ignore_returns_neutralize(self, tmp_path: Path) -> None:
        meta = _meta(
            exists=False,
            size=0,
            sha256=None,
            line_count=None,
            ignored_by_git=".gitignore:50",
            neutralize_eligible=True,
        )
        rec = recommend_policy(
            ".claude/commands/dev-review.md",
            tmp_path / ".claude/commands/dev-review.md",
            b"# command\n",
            meta,
        )
        assert rec.policy == "NEUTRALIZE"
        assert rec.manual_review_needed is True  # ALWAYS needs consent (mutates .gitignore)
        assert "consent" in rec.reason

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
            ignored_by_git=".gitignore:1",
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


class TestAnalyzeTarget:
    """`analyze_target` orchestrator — walks planned_files, builds AdoptionPlan."""

    def test_empty_planned_files_returns_empty_plan(self, tmp_path: Path) -> None:
        plan = analyze_target(tmp_path, {})
        assert isinstance(plan, AdoptionPlan)
        assert plan.target_root == tmp_path
        assert plan.analyses == ()

    def test_target_root_passed_through(self, tmp_path: Path) -> None:
        plan = analyze_target(tmp_path, {"f.txt": b"skill\n"})
        assert plan.target_root == tmp_path

    def test_single_missing_file_gets_write_recommendation(self, tmp_path: Path) -> None:
        """No target file exists → rule (a) WRITE."""
        plan = analyze_target(tmp_path, {"new.txt": b"skill content\n"})
        assert len(plan.analyses) == 1
        analysis = plan.analyses[0]
        assert analysis.rel_path == "new.txt"
        assert analysis.target_meta.exists is False
        assert analysis.recommendation.policy == "WRITE"
        assert analysis.recommendation.manual_review_needed is False

    def test_single_byte_identical_file_gets_skip(self, tmp_path: Path) -> None:
        """Existing target == skill content → rule (c) SKIP."""
        content = b"matched\n"
        (tmp_path / "f.txt").write_bytes(content)
        plan = analyze_target(tmp_path, {"f.txt": content})
        assert len(plan.analyses) == 1
        analysis = plan.analyses[0]
        assert analysis.target_meta.exists is True
        assert analysis.recommendation.policy == "SKIP"
        assert "byte-for-byte" in analysis.recommendation.reason

    def test_multiple_files_each_gets_its_own_recommendation(self, tmp_path: Path) -> None:
        """Mixed plan: missing + empty + byte-identical + unknown-non-empty."""
        # (a) missing → WRITE
        # (b) empty existing → OVERWRITE
        # (c) byte-identical → SKIP
        # (h) unknown existing non-empty → SKIP/manual_review
        (tmp_path / "empty.txt").write_bytes(b"")
        (tmp_path / "matched.txt").write_bytes(b"same content\n")
        (tmp_path / "unknown.txt").write_bytes(b"some user content\n")
        planned = {
            "new.txt": b"new content\n",
            "empty.txt": b"fill me\n",
            "matched.txt": b"same content\n",
            "unknown.txt": b"different skill content\n",
        }
        plan = analyze_target(tmp_path, planned)
        assert len(plan.analyses) == 4

        by_path = {a.rel_path: a for a in plan.analyses}
        assert by_path["new.txt"].recommendation.policy == "WRITE"
        assert by_path["empty.txt"].recommendation.policy == "OVERWRITE"
        assert by_path["matched.txt"].recommendation.policy == "SKIP"
        assert "byte-for-byte" in by_path["matched.txt"].recommendation.reason
        assert by_path["unknown.txt"].recommendation.policy == "SKIP"
        assert by_path["unknown.txt"].recommendation.manual_review_needed is True

    def test_analyses_sorted_lexicographically(self, tmp_path: Path) -> None:
        """Stable ordering so user-facing report is deterministic across runs.

        Pass keys in non-sorted order; verify output is sorted regardless.
        """
        planned = {
            "z.txt": b"z\n",
            "a.txt": b"a\n",
            "m.txt": b"m\n",
        }
        plan = analyze_target(tmp_path, planned)
        rel_paths = [a.rel_path for a in plan.analyses]
        assert rel_paths == ["a.txt", "m.txt", "z.txt"]

    def test_downstream_app_shaped_fixture_exercises_full_rule_set(self, tmp_path: Path) -> None:
        """Synthetic fixture matching the downstream-app collision shape (4
        collisions: .gitignore + .python-version + CLAUDE.md + pyproject.toml).
        Verifies every Scope #5 rule fires once end-to-end via analyze_target."""
        # Target setup (4 collisions + 1 missing-create):
        (tmp_path / ".gitignore").write_bytes(b"venv/\n*.pyc\n")
        (tmp_path / ".python-version").write_bytes(b"3.10\n")  # mismatch with skill's 3.12
        # CLAUDE.md: >20 lines → non-trivial → rule (f) WRITE_NEW
        (tmp_path / "CLAUDE.md").write_bytes(b"# Project CLAUDE.md\n" + b"some line\n" * 30)
        # pyproject.toml: has [tool.*] → non-trivial → rule (g) SKIP
        (tmp_path / "pyproject.toml").write_bytes(
            b'[project]\nname = "x"\n\n[tool.ruff]\nline-length = 100\n'
        )

        planned = {
            ".gitignore": b"venv/\n*.pyc\n__pycache__/\n.env\n",  # 2 new patterns
            ".python-version": b"3.12\n",  # version mismatch
            "CLAUDE.md": b"# Skill template\nshort\n",  # short skill, long target
            "pyproject.toml": b'[project]\nname = "y"\n',  # trivial skill, non-trivial target
            "Makefile": b"all:\n\techo hi\n",  # MISSING — rule (a) WRITE
        }
        plan = analyze_target(tmp_path, planned)
        by_path = {a.rel_path: a for a in plan.analyses}

        # Rule (d) — APPEND_MERGE
        assert by_path[".gitignore"].recommendation.policy == "APPEND_MERGE"
        assert by_path[".gitignore"].recommendation.manual_review_needed is False

        # Rule (e) — SKIP with mismatch note
        assert by_path[".python-version"].recommendation.policy == "SKIP"
        assert by_path[".python-version"].recommendation.manual_review_needed is False
        assert "different Python version" in by_path[".python-version"].recommendation.reason

        # Rule (f) — WRITE_NEW (target has >20 lines)
        assert by_path["CLAUDE.md"].recommendation.policy == "WRITE_NEW"
        assert by_path["CLAUDE.md"].recommendation.manual_review_needed is True

        # Rule (g) — SKIP with manual_review (target has [tool.*])
        assert by_path["pyproject.toml"].recommendation.policy == "SKIP"
        assert by_path["pyproject.toml"].recommendation.manual_review_needed is True

        # Rule (a) — WRITE (missing file, not git-ignored — no .git in tmp_path)
        assert by_path["Makefile"].recommendation.policy == "WRITE"
        assert by_path["Makefile"].recommendation.manual_review_needed is False

    def test_target_meta_carries_per_file_shape(self, tmp_path: Path) -> None:
        """analyze_target attaches the right TargetMeta to each analysis."""
        (tmp_path / "exists.txt").write_bytes(b"hello\n")
        plan = analyze_target(tmp_path, {"exists.txt": b"different\n", "missing.txt": b"skill\n"})
        by_path = {a.rel_path: a for a in plan.analyses}
        assert by_path["exists.txt"].target_meta.exists is True
        assert by_path["exists.txt"].target_meta.size == len(b"hello\n")
        assert by_path["missing.txt"].target_meta.exists is False
        assert by_path["missing.txt"].target_meta.sha256 is None

    def test_does_not_write_to_target(self, tmp_path: Path) -> None:
        """Architecture decision: analyze phase reads files but writes NOTHING.

        Snapshot tmp_path contents before + after; verify no new files appeared.
        """
        (tmp_path / "existing.txt").write_bytes(b"untouched\n")
        before = sorted(p.name for p in tmp_path.iterdir())
        plan = analyze_target(tmp_path, {"existing.txt": b"skill\n", "missing.txt": b"skill\n"})
        after = sorted(p.name for p in tmp_path.iterdir())
        assert before == after, (
            "analyze_target wrote a file to target_root — violates pure-analyze contract"
        )
        # Sanity check that we DID analyze
        assert len(plan.analyses) == 2


class TestFormatRecommendationReport:
    """`format_recommendation_report` — user-facing rendering.

    Bucket D golden-output contract: assert STRUCTURE (key sections, counts,
    privacy-safe content), NOT byte-equality (so wording polish doesn't
    cascade-break tests).
    """

    def test_empty_plan_renders_short_message(self, tmp_path: Path) -> None:
        plan = AdoptionPlan(target_root=tmp_path, analyses=())
        report = format_recommendation_report(plan)
        assert "0 file(s) analyzed" in report
        assert str(tmp_path) in report
        assert "empty plan" in report
        assert report.endswith("\n")

    def test_report_includes_target_root(self, tmp_path: Path) -> None:
        plan = analyze_target(tmp_path, {"new.txt": b"skill\n"})
        report = format_recommendation_report(plan)
        assert str(tmp_path) in report

    def test_report_lists_every_rel_path(self, tmp_path: Path) -> None:
        (tmp_path / "exists.txt").write_bytes(b"hi\n")
        plan = analyze_target(
            tmp_path,
            {"new.txt": b"a\n", "exists.txt": b"b\n", ".gitignore": b"venv/\n"},
        )
        report = format_recommendation_report(plan)
        for rel in ("new.txt", "exists.txt", ".gitignore"):
            assert rel in report, f"{rel} missing from report"

    def test_report_shows_every_emitted_policy(self, tmp_path: Path) -> None:
        """Each policy name appears in the report wherever a file uses it."""
        (tmp_path / "empty.txt").write_bytes(b"")  # → OVERWRITE
        (tmp_path / "matched.txt").write_bytes(b"hi\n")  # → SKIP
        plan = analyze_target(
            tmp_path,
            {
                "new.txt": b"a\n",  # → WRITE
                "empty.txt": b"fill\n",
                "matched.txt": b"hi\n",
            },
        )
        report = format_recommendation_report(plan)
        assert "WRITE" in report
        assert "OVERWRITE" in report
        assert "SKIP" in report

    def test_report_groups_by_manual_review_needed(self, tmp_path: Path) -> None:
        """Files needing manual review are in their own section; auto-applies
        in another; both labeled with counts."""
        (tmp_path / "CLAUDE.md").write_bytes(
            b"# Title\n" + b"line\n" * 25
        )  # rule (f) → manual_review
        plan = analyze_target(
            tmp_path,
            {
                "new.txt": b"safe\n",  # auto (WRITE)
                "CLAUDE.md": b"# Skill\n",  # manual (WRITE_NEW)
            },
        )
        report = format_recommendation_report(plan)
        assert "automatic (1):" in report
        assert "manual review needed (1):" in report
        # CLAUDE.md belongs to the manual section; order check via index
        manual_idx = report.index("manual review needed")
        new_idx = report.index("new.txt")
        claude_idx = report.index("CLAUDE.md")
        # new.txt appears BEFORE the manual section
        assert new_idx < manual_idx
        # CLAUDE.md appears AFTER the manual section header
        assert claude_idx > manual_idx

    def test_report_shows_summary_with_policy_counts(self, tmp_path: Path) -> None:
        (tmp_path / "exists.txt").write_bytes(b"hi\n")
        plan = analyze_target(
            tmp_path,
            {"a.txt": b"a\n", "b.txt": b"b\n", "exists.txt": b"hi\n"},
        )
        report = format_recommendation_report(plan)
        assert "summary:" in report
        # Two WRITE (a.txt + b.txt missing) + one SKIP (exists.txt byte-identical)
        assert "WRITE=2" in report
        assert "SKIP=1" in report

    def test_report_summary_indicates_decisions_needed(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_bytes(b"# Title\n" + b"line\n" * 25)
        plan = analyze_target(tmp_path, {"new.txt": b"safe\n", "CLAUDE.md": b"# Skill\n"})
        report = format_recommendation_report(plan)
        assert "1 need your decision" in report

    def test_report_summary_all_automatic_when_no_manual_review(self, tmp_path: Path) -> None:
        plan = analyze_target(tmp_path, {"new.txt": b"safe\n"})
        report = format_recommendation_report(plan)
        assert "all automatic" in report
        assert "need your decision" not in report

    def test_report_shows_target_shape_for_existing_files(self, tmp_path: Path) -> None:
        """Target shape line includes line count + sha256 prefix for existing
        files (privacy-safe derived markers)."""
        content = b"hello\nworld\n"
        (tmp_path / "f.txt").write_bytes(content)
        plan = analyze_target(tmp_path, {"f.txt": b"different\n"})
        report = format_recommendation_report(plan)
        assert "2 lines" in report
        assert "sha256:" in report
        # First 8 chars of the sha256
        assert hashlib.sha256(content).hexdigest()[:8] in report

    def test_report_shows_missing_for_nonexistent_targets(self, tmp_path: Path) -> None:
        plan = analyze_target(tmp_path, {"missing.txt": b"skill\n"})
        report = format_recommendation_report(plan)
        assert "target: missing" in report

    def test_report_shows_python_version_pin(self, tmp_path: Path) -> None:
        """The pin appears for .python-version shape lines."""
        (tmp_path / ".python-version").write_bytes(b"3.10\n")
        plan = analyze_target(tmp_path, {".python-version": b"3.12\n"})
        report = format_recommendation_report(plan)
        assert "pin=3.10" in report

    def test_report_shows_dependency_groups_marker(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_bytes(
            b'[project]\nname = "x"\n\n[dependency-groups]\ndev = ["pytest"]\n'
        )
        plan = analyze_target(tmp_path, {"pyproject.toml": b'[project]\nname = "y"\n'})
        report = format_recommendation_report(plan)
        assert "[dependency-groups]" in report

    def test_report_includes_per_file_reason(self, tmp_path: Path) -> None:
        plan = analyze_target(tmp_path, {"new.txt": b"skill\n"})
        report = format_recommendation_report(plan)
        assert "reason: target file does not exist" in report

    # ─── Privacy boundary (Bucket B test row contract) ───
    def test_report_does_not_leak_raw_target_content(self, tmp_path: Path) -> None:
        """The user-facing report must contain NO raw target file content.

        Seed a target file with a unique marker string; verify the marker is
        absent from the rendered report. Only derived markers (counts/hashes/
        structural flags) should appear.
        """
        secret_marker = b"SUPER_SECRET_CUSTOMER_TOKEN_42_xyzZQ\n"
        (tmp_path / "CLAUDE.md").write_bytes(b"# Title\n" + secret_marker + b"line\n" * 30)
        (tmp_path / ".gitignore").write_bytes(secret_marker + b"venv/\n")
        (tmp_path / "pyproject.toml").write_bytes(
            b'[project]\nname = "x"\ndescription = "' + secret_marker.strip() + b'"\n'
        )
        plan = analyze_target(
            tmp_path,
            {
                "CLAUDE.md": b"# Skill\n",
                ".gitignore": b"venv/\n__pycache__/\n",
                "pyproject.toml": b'[project]\nname = "y"\n',
            },
        )
        report = format_recommendation_report(plan)

        # The marker bytes must not appear in the report (privacy boundary).
        marker_str = secret_marker.decode().strip()
        assert marker_str not in report, (
            f"raw target content leaked into report: {marker_str!r} found in output"
        )

    def test_report_does_not_leak_gitignore_user_patterns(self, tmp_path: Path) -> None:
        """The report counts missing patterns but does not enumerate user
        patterns from the target's .gitignore (privacy: user gitignore lines
        could be path-revealing — e.g. `secrets/client-name/`)."""
        user_secret_pattern = "secrets/client-acme-corp/"
        (tmp_path / ".gitignore").write_text(f"{user_secret_pattern}\nvenv/\n")
        plan = analyze_target(tmp_path, {".gitignore": b"venv/\n__pycache__/\n.env\n"})
        report = format_recommendation_report(plan)
        assert user_secret_pattern not in report, "user's .gitignore pattern leaked into report"

    def test_report_does_not_leak_gitignore_pattern_via_rule_a0(self, tmp_path: Path) -> None:
        """Rule (a0) privacy: when a planned-CREATE matches a target's
        `.gitignore` pattern, the report shows the file is ignored (so the
        user can decide SKIP-confirm vs WRITE_NEW) but MUST NOT include the
        matching pattern itself — patterns can be path-revealing
        (`secrets/client-acme/`, `*-customer-token-*`).

        Uses a pattern with a trailing `*` so the pattern's distinctive bytes
        don't appear in the matched filename — lets us assert pattern absence
        without false positives from the rel_path.
        """
        import re

        _git_init(tmp_path)
        secret_pattern = "totally-secret-prefix_LEAKMARKER_*"
        matched_path = "totally-secret-prefix_LEAKMARKER_xyz"
        (tmp_path / ".gitignore").write_text(f"{secret_pattern}\n")
        plan = analyze_target(tmp_path, {matched_path: b"skill content\n"})
        report = format_recommendation_report(plan)

        # Sanity: rule (a0) fired — file is in manual-review section.
        assert "manual review needed" in report
        # rel_path IS allowed (Scope #11 lists filenames as safe).
        assert matched_path in report

        # Pattern itself MUST NOT appear.
        assert secret_pattern not in report, (
            f"gitignore pattern leaked via rule (a0): {secret_pattern!r} found in report"
        )
        # No 3-field `.gitignore:N:<pattern>` references — only 2-field `.gitignore:N`.
        leaky_refs = re.findall(r"\.gitignore:\d+:[^\s)]+", report)
        assert not leaky_refs, (
            f"3-field gitignore reference (pattern-leaking) found in report: {leaky_refs}"
        )

    def test_report_ends_with_newline(self, tmp_path: Path) -> None:
        plan = analyze_target(tmp_path, {"f.txt": b"x\n"})
        report = format_recommendation_report(plan)
        assert report.endswith("\n")
        # Not double-newline at end
        assert not report.endswith("\n\n\n")

    def test_report_is_str_type(self, tmp_path: Path) -> None:
        plan = analyze_target(tmp_path, {"f.txt": b"x\n"})
        report = format_recommendation_report(plan)
        assert isinstance(report, str)


class TestComputeAppendMergeBytes:
    """`compute_append_merge_bytes` — the single source of truth for both
    rule (d) recommendation heuristic AND `_apply_adoption_writes` post-merge
    bytes. Tests pin the line-level idempotent contract."""

    def test_empty_target_appends_all_skill_lines(self) -> None:
        result = compute_append_merge_bytes(b"", b"venv/\n*.pyc\n")
        assert result == b"venv/\n*.pyc\n"

    def test_target_with_all_skill_lines_returns_target_unchanged(self) -> None:
        """Idempotent: if every skill line is already in target, no append."""
        target = b"venv/\n*.pyc\n__pycache__/\n"
        skill = b"venv/\n*.pyc\n"
        assert compute_append_merge_bytes(target, skill) == target

    def test_missing_skill_lines_appended(self) -> None:
        target = b"venv/\n"
        skill = b"venv/\n*.pyc\n.env\n"
        result = compute_append_merge_bytes(target, skill)
        assert result == b"venv/\n*.pyc\n.env\n"

    def test_skill_comments_not_appended(self) -> None:
        """Comments are not patterns; they're not part of the membership
        check AND not appended to target."""
        target = b"venv/\n"
        skill = b"# generated by skill bootstrap\n*.pyc\n"
        result = compute_append_merge_bytes(target, skill)
        # Comment dropped; pattern appended
        assert result == b"venv/\n*.pyc\n"

    def test_target_comments_preserved(self) -> None:
        """Comments in target are not touched by the append."""
        target = b"# my project gitignore\nvenv/\n"
        skill = b"*.pyc\n"
        result = compute_append_merge_bytes(target, skill)
        assert result == b"# my project gitignore\nvenv/\n*.pyc\n"

    def test_duplicate_skill_lines_appended_once(self) -> None:
        """If skill content has the same pattern twice, append only once."""
        target = b"venv/\n"
        skill = b"*.pyc\n*.pyc\n.env\n"
        result = compute_append_merge_bytes(target, skill)
        assert result == b"venv/\n*.pyc\n.env\n"

    def test_target_without_trailing_newline_gets_separator(self) -> None:
        """If target doesn't end in newline, add one before appending."""
        target = b"venv/"  # no trailing newline
        skill = b"*.pyc\n"
        result = compute_append_merge_bytes(target, skill)
        assert result == b"venv/\n*.pyc\n"

    def test_idempotent_twice_produces_same_result(self) -> None:
        target = b"venv/\n"
        skill = b"venv/\n*.pyc\n.env\n"
        once = compute_append_merge_bytes(target, skill)
        twice = compute_append_merge_bytes(once, skill)
        assert once == twice

    def test_empty_skill_returns_target_unchanged(self) -> None:
        target = b"venv/\n*.pyc\n"
        assert compute_append_merge_bytes(target, b"") == target

    def test_pure_comments_skill_returns_target_unchanged(self) -> None:
        """Skill with only comments + blank lines → no append (idempotent)."""
        target = b"venv/\n"
        skill = b"# header comment\n\n# another comment\n"
        assert compute_append_merge_bytes(target, skill) == target

    def test_byte_fidelity_no_utf8_roundtrip(self) -> None:
        """The function operates in bytes throughout — non-UTF-8 byte
        sequences in the patterns survive (no lossy decode)."""
        # Latin-1-ish bytes that aren't valid UTF-8
        target = b"\xff-pattern\n"
        skill = b"\xfe-pattern\n"
        result = compute_append_merge_bytes(target, skill)
        assert result == b"\xff-pattern\n\xfe-pattern\n"


def test_adoption_collision_error_is_exception() -> None:
    """`AdoptionCollisionError` is a real exception type — raisable + catchable."""
    with pytest.raises(AdoptionCollisionError, match="test message"):
        raise AdoptionCollisionError("test message")


# ──────────────────────────────────────────────────────────────────────
# B1 shadow scan + escalation + B1/B2 advisories (config-shadowing fix plan)
# ──────────────────────────────────────────────────────────────────────

_MINIMAL_PLANNED = {"pyproject.toml": b"[project]\nname = 'x'\n"}


class TestScanShadowingConfigs:
    """`scan_shadowing_configs` — top-level detection of target-owned
    standalone tool configs that would shadow pyproject.toml [tool.*]."""

    def test_empty_when_none_present(self, tmp_path: Path) -> None:
        assert scan_shadowing_configs(tmp_path) == ()

    @pytest.mark.parametrize("name", ["ruff.toml", ".ruff.toml", "pytest.ini"])
    def test_detects_each_standalone_config(self, tmp_path: Path, name: str) -> None:
        (tmp_path / name).write_text("x")
        assert scan_shadowing_configs(tmp_path) == (name,)

    def test_detects_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "ruff.toml").write_text("x")
        (tmp_path / "pytest.ini").write_text("x")
        assert set(scan_shadowing_configs(tmp_path)) == {"ruff.toml", "pytest.ini"}

    def test_top_level_only_not_recursive(self, tmp_path: Path) -> None:
        """Nested monorepo configs are out of scope (Bucket E BACKLOG)."""
        nested = tmp_path / "sub"
        nested.mkdir()
        (nested / "ruff.toml").write_text("x")
        assert scan_shadowing_configs(tmp_path) == ()

    def test_directory_named_like_config_is_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "ruff.toml").mkdir()
        assert scan_shadowing_configs(tmp_path) == ()


class TestShadowEscalation:
    """B1 escalation: a fresh-pyproject.toml WRITE over a target-owned
    standalone config is escalated to manual_review_needed=True."""

    @pytest.mark.parametrize("shadow", ["ruff.toml", ".ruff.toml", "pytest.ini"])
    def test_escalates_fresh_pyproject_write(self, tmp_path: Path, shadow: str) -> None:
        (tmp_path / shadow).write_text("x")
        plan = analyze_target(tmp_path, dict(_MINIMAL_PLANNED))
        pp = next(a for a in plan.analyses if a.rel_path == "pyproject.toml")
        assert pp.recommendation.policy == "WRITE"
        assert pp.recommendation.manual_review_needed is True
        assert shadow in pp.recommendation.reason
        assert plan.shadowing_configs == (shadow,)

    def test_no_escalation_without_shadow(self, tmp_path: Path) -> None:
        """No-shadow control: rule (a) WRITE with no standalone config stays
        manual_review_needed=False — the escalation must not over-fire."""
        plan = analyze_target(tmp_path, dict(_MINIMAL_PLANNED))
        pp = next(a for a in plan.analyses if a.rel_path == "pyproject.toml")
        assert pp.recommendation.policy == "WRITE"
        assert pp.recommendation.manual_review_needed is False
        assert plan.shadowing_configs == ()

    @pytest.mark.parametrize("shadow", ["ruff.toml", ".ruff.toml", "pytest.ini"])
    def test_escalates_empty_pyproject_overwrite(self, tmp_path: Path, shadow: str) -> None:
        """An empty/whitespace-only pyproject.toml routes through rule (b)
        OVERWRITE; with a shadow present it must ALSO escalate — otherwise
        `--non-interactive` would OVERWRITE pyproject.toml with the skill's
        [tool.*] tables and exit 0 with dead config."""
        (tmp_path / shadow).write_text("x")
        (tmp_path / "pyproject.toml").write_text("   \n")
        plan = analyze_target(tmp_path, dict(_MINIMAL_PLANNED))
        pp = next(a for a in plan.analyses if a.rel_path == "pyproject.toml")
        assert pp.recommendation.policy == "OVERWRITE"
        assert pp.recommendation.manual_review_needed is True
        assert shadow in pp.recommendation.reason

    @pytest.mark.parametrize("shadow", ["ruff.toml", ".ruff.toml", "pytest.ini"])
    def test_existing_pyproject_not_escalated_but_scanned(
        self, tmp_path: Path, shadow: str
    ) -> None:
        """Target owns a standalone config AND has a non-trivial pyproject.toml
        → pyproject routes through rule (g) SKIP (already mr=True); no
        escalation, but the scan result is still recorded on the plan."""
        (tmp_path / shadow).write_text("x")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "p"\n\n[tool.ruff]\nline-length = 88\n'
        )
        plan = analyze_target(tmp_path, dict(_MINIMAL_PLANNED))
        pp = next(a for a in plan.analyses if a.rel_path == "pyproject.toml")
        assert pp.recommendation.policy == "SKIP"
        assert pp.recommendation.manual_review_needed is True
        assert plan.shadowing_configs == (shadow,)


class TestShadowAdvisoryReport:
    """B1 advisory: format_recommendation_report always names a detected
    target-owned standalone config and the [tool.*] table it overrides."""

    def test_b1_advisory_names_ruff_toml(self, tmp_path: Path) -> None:
        (tmp_path / "ruff.toml").write_text("x")
        report = format_recommendation_report(analyze_target(tmp_path, dict(_MINIMAL_PLANNED)))
        assert "config-shadowing advisory" in report
        assert "ruff.toml" in report
        assert "[tool.ruff]" in report

    def test_b1_advisory_pytest_ini_names_pytest_table(self, tmp_path: Path) -> None:
        (tmp_path / "pytest.ini").write_text("x")
        report = format_recommendation_report(analyze_target(tmp_path, dict(_MINIMAL_PLANNED)))
        assert "pytest.ini" in report
        assert "[tool.pytest.ini_options]" in report

    def test_no_advisory_when_no_shadow(self, tmp_path: Path) -> None:
        report = format_recommendation_report(analyze_target(tmp_path, dict(_MINIMAL_PLANNED)))
        assert "config-shadowing advisory" not in report


class TestPyprojectSkipAdvisory:
    """B2 advisory: when the target's own pyproject.toml is SKIPped, the
    report explains the skill's [tool.*] config was not applied — with
    three wording branches keyed off the target file's parse state."""

    def test_rule_g_advisory_says_merge_via_diff(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "p"\n\n[tool.ruff]\nline-length = 88\n'
        )
        report = format_recommendation_report(analyze_target(tmp_path, dict(_MINIMAL_PLANNED)))
        assert "--diff" in report
        assert "copy ONLY" in report
        assert "[tool.pytest.ini_options]" in report

    def test_trivial_pyproject_advisory_says_may_add(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "p"\nversion = "0.1.0"\n')
        report = format_recommendation_report(analyze_target(tmp_path, dict(_MINIMAL_PLANNED)))
        assert "no tool" in report
        assert "may add" in report

    def test_malformed_pyproject_advisory_says_fix_first(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project\nnot valid toml")
        report = format_recommendation_report(analyze_target(tmp_path, dict(_MINIMAL_PLANNED)))
        assert "did not parse as valid TOML" in report

    def test_live_downstream_app_shape_surfaces_both_advisories(self, tmp_path: Path) -> None:
        """The exact live downstream-app shape: existing pyproject.toml with
        [tool.pytest.ini_options] PLUS a top-level pytest.ini that wins.
        B1 names pytest.ini; B2 gives rule-(g) merge guidance."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "p"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = other\n")
        report = format_recommendation_report(analyze_target(tmp_path, dict(_MINIMAL_PLANNED)))
        assert "config-shadowing advisory" in report
        assert "pytest.ini" in report
        assert "--diff" in report
        # B2 rule-(g) wording explicitly defers to the B1 shadow advisory
        # (plan H1 fold): copying tables into pyproject.toml is futile while
        # the standalone file wins.
        assert "overrides these tables" in report


# ─────────────────────────────────────────────────────────────────────────────
# PR-2 (Part 2A) — the `.claude/`-class ignore classifier (iter-1 FN5 / iter-3
# FN4). NEUTRALIZE must fire ONLY when the matched ignore pattern is one the
# managed un-ignore block can actually fix; a broad pattern (e.g. `*.md`) that
# merely happens to match stays a conservative SKIP (design-note AC4).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pattern, expected",
    [
        (".claude", True),
        (".claude/", True),
        (".claude/**", True),
        ("/.claude/", True),  # root-anchored — leading / stripped (iter-3 FN4)
        ("/.claude/**", True),
        (".claude/commands/", True),
        ("!.claude/", True),  # leading ! stripped (defensive)
        ("  .claude/  ", True),  # surrounding space stripped
        ("*.md", False),  # broad pattern the un-ignore block can't fix
        ("*.local", False),
        ("secrets/", False),
        ("claude/", False),  # missing leading dot
        (".claudette/", False),  # `.claude` prefix but not a `.claude/` path segment
    ],
)
def test_is_dotclaude_class_pattern(pattern, expected):
    assert _is_dotclaude_class_pattern(pattern) is expected


@pytest.mark.parametrize(
    "ignore_line, expect_neutralize",
    [
        (".claude/", True),
        ("/.claude/", True),
        (".claude/**", True),
        ("/.claude/**", True),
        (".claude", True),
        ("*.md", False),  # broad pattern that also matches → conservative SKIP
    ],
)
def test_rule_a0_end_to_end_dotclaude_class_vs_broad(tmp_path, ignore_line, expect_neutralize):
    """End-to-end through REAL `git check-ignore`: a planned, ignored
    `.claude/commands/dev-review.md` recommends NEUTRALIZE when the matching
    pattern is `.claude/`-class, else a conservative SKIP — both with
    manual_review_needed=True. Exercises the full classifier path
    (_compute_target_meta → _check_ignored_by_git → _is_dotclaude_class_pattern
    → recommend_policy), not just the in-memory boolean."""
    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text(ignore_line + "\n")
    rel = ".claude/commands/dev-review.md"
    meta = _compute_target_meta(tmp_path, rel)
    assert meta.exists is False
    assert meta.ignored_by_git is not None, f"{ignore_line!r} should ignore {rel}"
    assert meta.neutralize_eligible is expect_neutralize
    # privacy: the captured reference is source:line only — never the pattern
    assert ".claude" not in meta.ignored_by_git
    rec = recommend_policy(rel, tmp_path / rel, b"# command\n", meta)
    assert rec.manual_review_needed is True
    assert rec.policy == ("NEUTRALIZE" if expect_neutralize else "SKIP")


def test_rule_a0_negated_reinclude_is_write_not_neutralize(tmp_path):
    """Tier-2 codex P2 (PR #35): a target whose `.gitignore` already re-includes
    the command file via a `!`-negation (manual setup, OR an interrupted prior
    adopt that appended the un-ignore block but never wrote the file) is NOT
    ignored — `git check-ignore -v` reports rc 0 + the `!` pattern, but `-q`
    exits 1. The planned command must get a plain rule-(a) WRITE, never
    NEUTRALIZE (which would re-append the block / abort under --non-interactive)."""
    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text(
        ".claude/\n"
        "!.claude/\n"
        ".claude/*\n"
        "!.claude/commands/\n"
        ".claude/commands/*\n"
        "!.claude/commands/dev-review.md\n"
    )
    rel = ".claude/commands/dev-review.md"
    meta = _compute_target_meta(tmp_path, rel)
    assert meta.exists is False
    assert meta.ignored_by_git is None, "a `!`-re-included path must read as not-ignored"
    assert meta.neutralize_eligible is False
    rec = recommend_policy(rel, tmp_path / rel, b"# command\n", meta)
    assert rec.policy == "WRITE"
    assert rec.manual_review_needed is False


def test_rule_a0_exclude_sourced_is_skip_not_neutralize(tmp_path):
    """Tier-2 codex P2 finding A (PR #35): when `.claude/` is ignored via
    `.git/info/exclude` (NOT the target `.gitignore`) and no `.gitignore` exists,
    NEUTRALIZE would CREATE a `.gitignore` whose restore leaves a stray empty
    file. Require the ignore to be ROOT-`.gitignore`-sourced → else conservative
    SKIP, and nothing is created."""
    _git_init(tmp_path)
    exclude = tmp_path / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(".claude/\n")  # ignore via exclude; NO .gitignore in the worktree
    rel = ".claude/commands/dev-review.md"
    meta = _compute_target_meta(tmp_path, rel)
    assert meta.exists is False
    assert meta.ignored_by_git is not None  # it IS ignored (by exclude)
    assert meta.neutralize_eligible is False  # but NOT cleanly NEUTRALIZE-able
    rec = recommend_policy(rel, tmp_path / rel, b"# command\n", meta)
    assert rec.policy == "SKIP"
    assert rec.manual_review_needed is True
    assert not (tmp_path / ".gitignore").exists()  # analyze created nothing


def test_rule_a0_sentinel_already_present_is_skip_not_neutralize(tmp_path):
    """Tier-2 codex P2 finding B (PR #35): a `.gitignore` that already carries
    the NEUTRALIZE sentinel (a prior/partial block — here the functional `!`
    lines are absent so the command is still ignored by `.claude/`) is NOT
    cleanly NEUTRALIZE-able: apply would no-op on the sentinel (silent failure).
    Fall back to SKIP."""
    from bootstrap_lib.manifest import NEUTRALIZE_SENTINEL

    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text(f".claude/\n{NEUTRALIZE_SENTINEL}\n")
    rel = ".claude/commands/dev-review.md"
    meta = _compute_target_meta(tmp_path, rel)
    assert meta.ignored_by_git is not None  # still ignored by `.claude/`
    assert meta.neutralize_eligible is False  # sentinel present → not eligible
    rec = recommend_policy(rel, tmp_path / rel, b"# command\n", meta)
    assert rec.policy == "SKIP"


def test_rule_a0_block_then_reignore_is_skip_not_neutralize(tmp_path):
    """Tier-2 codex P2 finding D (PR #35): a `.gitignore` carrying the full
    un-ignore block AND a later rule re-ignoring the command → the later rule
    wins (so it's ignored), but the sentinel is present, so NEUTRALIZE (which
    would let restore delete the pre-existing block) is rejected → SKIP."""
    from bootstrap_lib.manifest import NEUTRALIZE_BLOCK_LINES

    _git_init(tmp_path)
    # The full managed block (INCLUDING its sentinel comment) THEN a later rule
    # re-ignoring the command — the later rule wins, so the command is ignored
    # again, but the sentinel comment is present in the file.
    block = "\n".join(NEUTRALIZE_BLOCK_LINES)
    (tmp_path / ".gitignore").write_text(
        ".claude/\n" + block + "\n.claude/commands/dev-review.md\n"
    )
    rel = ".claude/commands/dev-review.md"
    meta = _compute_target_meta(tmp_path, rel)
    assert meta.ignored_by_git is not None  # later positive rule wins → ignored
    assert meta.neutralize_eligible is False  # sentinel present → not eligible
    rec = recommend_policy(rel, tmp_path / rel, b"# command\n", meta)
    assert rec.policy == "SKIP"
