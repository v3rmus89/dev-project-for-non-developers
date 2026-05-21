"""Tests for bootstrap_lib.render.planned_paths (skill PR #8).

`planned_paths` must return exactly the path set `render_all` would write, so
the interactive intake's greenfield collision check sees the true file set.
"""

from __future__ import annotations

import pytest

from bootstrap_lib import render


def _context(language, github_review_mode="none", enable_smoke=False, package_manager=None):
    """A complete render context for `language` — every key the templates
    reference under Jinja's StrictUndefined."""
    return {
        "project_name": "test-proj",
        "language": language,
        "python_version": "3.12",
        "node_version": "24",
        "go_version": "1.26",
        "package_manager": package_manager,
        "enable_smoke": enable_smoke,
        "github_owner": "test-owner",
        "github_repo": "test-repo",
        "github_review_mode": github_review_mode,
    }


def test_planned_paths_filters_by_review_smoke():
    """claude-review.yml only for non-'none' review; the Codex setup doc only
    for both-docs; docs/SMOKE.md only when smoke is enabled."""
    none_mode = render.planned_paths("python", github_review_mode="none", enable_smoke=False)
    assert ".github/workflows/claude-review.yml" not in none_mode
    assert "docs/codex-github-review-setup.md" not in none_mode
    assert "docs/SMOKE.md" not in none_mode

    claude_mode = render.planned_paths("python", github_review_mode="claude")
    assert ".github/workflows/claude-review.yml" in claude_mode
    assert "docs/codex-github-review-setup.md" not in claude_mode

    both = render.planned_paths("python", github_review_mode="both-docs")
    assert ".github/workflows/claude-review.yml" in both
    assert "docs/codex-github-review-setup.md" in both

    smoke = render.planned_paths("python", enable_smoke=True)
    assert "docs/SMOKE.md" in smoke


def test_planned_paths_filters_by_package_manager():
    """Python package-manager filter: `.python-version` only for uv,
    `requirements-dev.txt` only for pip; `package_manager=None` normalizes to
    pip (matching `render_all`)."""
    uv = render.planned_paths("python", package_manager="uv")
    assert ".python-version" in uv
    assert "requirements-dev.txt" not in uv

    pip = render.planned_paths("python", package_manager="pip")
    assert ".python-version" not in pip
    assert "requirements-dev.txt" in pip

    none_pm = render.planned_paths("python", package_manager=None)
    assert none_pm == pip  # None → pip


def test_planned_paths_rejects_unsupported_language():
    with pytest.raises(ValueError, match="rust"):
        render.planned_paths("rust")


@pytest.mark.parametrize("language", ["python", "nodejs", "go"])
@pytest.mark.parametrize("github_review_mode", ["none", "claude", "both-docs"])
@pytest.mark.parametrize("enable_smoke", [False, True])
@pytest.mark.parametrize("package_manager", ["uv", "pip", None])
def test_planned_paths_equals_render_all_keys(
    language, github_review_mode, enable_smoke, package_manager
):
    """`planned_paths` must return exactly the keys `render_all` writes — this
    locks the helper to the renderer, so a filter added to one but not the
    other is caught. Covers Python `package_manager=None`, which `render_all`
    normalizes to pip via `_emit_python_in_pm_mode`."""
    ctx = _context(
        language,
        github_review_mode=github_review_mode,
        enable_smoke=enable_smoke,
        package_manager=package_manager,
    )
    rendered = set(render.render_all(ctx, language=language).keys())
    planned = render.planned_paths(
        language,
        github_review_mode=github_review_mode,
        enable_smoke=enable_smoke,
        package_manager=package_manager,
    )
    assert planned == rendered
