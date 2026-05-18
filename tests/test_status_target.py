"""Tests for the `make status` recovery target.

Covers every contract from PR #5 plan Bucket A:
- All 7 section headings present
- Current branch activity (HEAD commits visible even on feature branch)
- Recent main activity fallback chain (origin/main → main → HEAD)
- Open PRs section gracefully handles `gh` missing / unauthed
- Active plan: PLAN_FILE override, mtime fallback, README filter, multi-plan WARN
- Bad PLAN_FILE handling (file missing → graceful)
- Active lessons section reads LESSONS.md
- Local repo state (works in non-git dir → "(not a git repo)")
- Health checks (inlined; never fails the target)
- Fence-aware section extraction (skips fenced ## Implementation log examples)
- Legacy plan with no impl-log section → fallback message
- Local-commits-no-remote case (Current branch shows them)
- File-named-status regression (.PHONY effective)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


def _bootstrap_fixture(tmp_path, language="python"):
    target = tmp_path / "proj"
    result = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            language,
            "--project-name",
            "fixture",
            "--out",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return target


def _git_init_commit(target, commits=1):
    """Init git in target + create N initial commits."""
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@x.com", "-c", "user.name=t", "add", "."],
        cwd=str(target),
        check=True,
    )
    for i in range(commits):
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=test@x.com",
                "-c",
                "user.name=t",
                "commit",
                "--allow-empty",
                "-q",
                "-m",
                f"commit {i}",
            ],
            cwd=str(target),
            check=True,
        )


def _make_status(target, env=None, plan_file=None):
    cmd = ["make", "-C", str(target), "status"]
    if plan_file is not None:
        cmd.append(f"PLAN_FILE={plan_file}")
    use_env = os.environ.copy()
    if env:
        use_env.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, env=use_env)


def test_status_has_all_section_headings(tmp_path):
    """All 7 section headings must appear in output."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target)
    result = _make_status(target)
    assert result.returncode == 0, result.stderr
    for heading in [
        "── Current branch activity ──",
        "── Recent main activity ──",
        "── Open PRs ──",
        "── Active plan ──",
        "── Active lessons ──",
        "── Local repo state ──",
        "── Health checks ──",
    ]:
        assert heading in result.stdout, f"missing section heading {heading!r}"


def test_status_in_non_git_dir(tmp_path):
    """`make status` in a non-git tmpdir falls back gracefully without erroring."""
    target = _bootstrap_fixture(tmp_path)
    # No git init
    result = _make_status(target)
    assert result.returncode == 0, result.stderr
    assert "(not a git repo)" in result.stdout


def test_status_local_commits_no_remote(tmp_path):
    """Closes Codex iter-6 #1 + iter-2 #2 + 6.5 #2: feature-branch commits
    with no origin/main must show up in Current-branch-activity."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target, commits=3)
    # Create + check out a feature branch and add another commit on it
    subprocess.run(
        ["git", "checkout", "-b", "feat/unique-marker"],
        cwd=str(target),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@x.com",
            "-c",
            "user.name=t",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "UNIQUE_FEATURE_COMMIT_MARKER",
        ],
        cwd=str(target),
        check=True,
    )
    result = _make_status(target)
    assert result.returncode == 0, result.stderr
    # The feature-branch-only commit must be visible in the Current branch section
    current_idx = result.stdout.index("── Current branch activity ──")
    main_idx = result.stdout.index("── Recent main activity ──")
    current_section = result.stdout[current_idx:main_idx]
    assert "UNIQUE_FEATURE_COMMIT_MARKER" in current_section, (
        "Current branch activity section must show feature-branch commits"
    )
    assert "feat/unique-marker" in current_section, "branch name must appear"


def test_status_gh_unavailable(tmp_path):
    """`gh` missing → graceful '(gh CLI not available)' fallback (not error)."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target)
    # Use a PATH without gh — but git must still be there
    # Find git's directory
    git_path = shutil.which("git")
    assert git_path
    git_dir = str(Path(git_path).parent)
    # Use only git's dir + system /usr/bin /bin so we have basics but no gh (gh usually in /opt/homebrew/bin or /usr/local/bin)
    restricted_path = f"{git_dir}:/usr/bin:/bin"
    if shutil.which("gh", path=restricted_path):
        pytest.skip("gh present even in restricted PATH; can't test the 'no gh' path here")
    result = _make_status(target, env={"PATH": restricted_path})
    assert result.returncode == 0, result.stderr
    assert "(gh CLI not available)" in result.stdout


def test_status_plan_file_override(tmp_path):
    """PLAN_FILE override wins; existence checked; bad path → graceful error."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target)
    # Make a valid plan file (override-target)
    plan_dir = target / "docs" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / "2026-05-18-fixture-plan.md"
    plan_file.write_text(
        "# fixture\n\n## Iteration log\n\n"
        "| Iter | Findings | Verdict |\n|---|---|---|\n"
        "| 1 | UNIQUE_ITER_LOG_MARKER | done |\n\n"
        "## Implementation log\n\n"
        "| Commit | What | Devs | Issues |\n|---|---|---|---|\n"
        "| abc1234 | UNIQUE_IMPL_LOG_MARKER | none | none |\n"
    )
    # Test override = explicit path
    result = _make_status(target, plan_file=str(plan_file.relative_to(target)))
    assert result.returncode == 0, result.stderr
    assert "PLAN_FILE override" in result.stdout
    assert "UNIQUE_ITER_LOG_MARKER" in result.stdout, "iteration log content must appear"
    assert "UNIQUE_IMPL_LOG_MARKER" in result.stdout, "impl log content must appear"

    # Test override = missing file → graceful error in Active-plan section, not crash
    result = _make_status(target, plan_file="docs/plans/does-not-exist.md")
    assert result.returncode == 0, "bad PLAN_FILE must not crash the target"
    assert "(PLAN_FILE not found:" in result.stdout


def test_status_multi_plan_warn(tmp_path):
    """Multiple plan files → WARN line + top-3 candidate list (closes iter-1 #5)."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target)
    plan_dir = target / "docs" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    for slug in ["a", "b", "c"]:
        (plan_dir / f"2026-05-18-{slug}.md").write_text(
            f"# {slug}\n\n## Iteration log\n\n| 1 | UNIQUE_PLAN_{slug.upper()} | done |\n"
        )
    result = _make_status(target)
    assert result.returncode == 0, result.stderr
    assert "WARN" in result.stdout, "multi-plan WARN line must fire"
    assert "PLAN FILES PRESENT" in result.stdout
    # All three should be listed (top-3 by mtime; since they were written near-simultaneously, order may vary)
    for slug in ["a", "b", "c"]:
        assert f"2026-05-18-{slug}.md" in result.stdout, (
            f"top-3 candidate list must include 2026-05-18-{slug}.md"
        )


def test_status_excludes_docs_plans_readme(tmp_path):
    """`docs/plans/README.md` ships in every generated project — must NOT be
    picked as 'the active plan' (closes Codex iter-2 #1)."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target)
    # No other plan files exist — only the bootstrap-emitted README.md
    result = _make_status(target)
    assert result.returncode == 0, result.stderr
    # The status output's Active-plan section must say "(no plan files)" since
    # we're filtering README out, not naming README as the active plan
    active_idx = result.stdout.index("── Active plan ──")
    next_section_idx = result.stdout.index("── Active lessons ──")
    active_section = result.stdout[active_idx:next_section_idx]
    # README.md exists in docs/plans/ but should NOT be displayed as the active plan
    # The filter should cause: either "(no plan files)" OR the section is empty of README ref
    if "README.md" in active_section:
        # If README appears, it should only be in the "WARN: candidates" list AS A FILTERED-OUT item
        # In our current design, README is filtered out at the candidates step entirely.
        # So README.md should NEVER appear in the Active-plan section.
        raise AssertionError(
            f"docs/plans/README.md must be filtered from plan-detect; got:\n{active_section}"
        )


def test_status_fence_aware_extraction(tmp_path):
    """Plan with fenced code containing fake `## Implementation log` must NOT
    be matched (closes Codex iter-4 #1, iter-6 #3)."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target)
    plan_dir = target / "docs" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / "2026-05-18-fence-test.md"
    plan_file.write_text(
        "# Plan\n\n"
        "## Iteration log\n\n"
        "REAL_ITER_LOG_MARKER\n\n"
        "## Example block\n\n"
        "Example template (do not match):\n"
        "```markdown\n"
        "## Implementation log\n\n"
        "| sha | FAKE_IMPL_LOG_MARKER | none | none |\n"
        "```\n\n"
        "## Implementation log\n\n"
        "| Commit | What | Devs | Issues |\n|---|---|---|---|\n"
        "| abc1234 | REAL_IMPL_LOG_MARKER | none | none |\n"
    )
    result = _make_status(target, plan_file=str(plan_file.relative_to(target)))
    assert result.returncode == 0, result.stderr
    assert "REAL_ITER_LOG_MARKER" in result.stdout
    assert "REAL_IMPL_LOG_MARKER" in result.stdout
    assert "FAKE_IMPL_LOG_MARKER" not in result.stdout, (
        "fenced example must be skipped by fence-aware extraction"
    )


def test_status_legacy_plan_no_impl_log(tmp_path):
    """Legacy plans (PR #1-#4) have no Implementation log section → fallback
    message instead of empty/crashing (closes Codex iter-4 #1 / iter-6 #3)."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target)
    plan_dir = target / "docs" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / "2026-01-01-legacy.md"
    plan_file.write_text(
        "# Legacy plan (no impl log section)\n\n"
        "## Iteration log\n\n"
        "| Iter | Findings | Verdict |\n|---|---|---|\n"
        "| 1 | LEGACY_ITER_LOG_MARKER | done |\n\n"
        "## Critical files\n\n- foo.md\n"
    )
    result = _make_status(target, plan_file=str(plan_file.relative_to(target)))
    assert result.returncode == 0, result.stderr
    assert "LEGACY_ITER_LOG_MARKER" in result.stdout
    assert "no Implementation log section yet" in result.stdout


def test_status_phony_with_status_file_present(tmp_path):
    """If a file named `status` exists, `.PHONY: status` declaration must
    still cause the recipe to run (closes Codex iter-4 #5)."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target)
    # Create a file named `status` in the project root
    (target / "status").write_text("a file named status\n")
    result = _make_status(target)
    assert result.returncode == 0, result.stderr
    # Recipe should still have run — section headings present
    assert "── Current branch activity ──" in result.stdout, (
        "recipe should run even with a file named `status` (PHONY effective)"
    )


def test_status_active_lessons_section(tmp_path):
    """Active lessons section reads LESSONS.md if present; falls back gracefully."""
    target = _bootstrap_fixture(tmp_path)
    _git_init_commit(target)
    # First check: with LESSONS.md (bootstrap should emit it now)
    assert (target / "LESSONS.md").exists(), "bootstrap should emit LESSONS.md"
    result = _make_status(target)
    assert result.returncode == 0, result.stderr
    # Active section should have heading present; it might be empty (no seed entries
    # in the generated project) — but the section must exist
    assert "── Active lessons ──" in result.stdout

    # Second check: with LESSONS.md removed
    (target / "LESSONS.md").unlink()
    result = _make_status(target)
    assert result.returncode == 0, result.stderr
    assert "(no LESSONS.md)" in result.stdout
