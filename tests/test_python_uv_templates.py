"""Per-template render-and-parse checks for languages/python/ in uv mode.

Parallel to tests/test_python_templates.py (which exercises pip mode);
contracts here lock in PR #6's uv-mode template branches per Bucket D.
"""

from __future__ import annotations

import re
import subprocess
import tomllib

import yaml

from bootstrap_lib import render

# Canonical pin list — shared with pip-mode tests so the two modes can't drift.
# When deps bump, both `requirements-dev.txt.tmpl` and `pyproject.toml.tmpl`'s
# `[dependency-groups].dev` must update in lockstep with this assertion.
DEV_DEP_PINS = ("ruff==0.15.12", "pytest>=8.0,<9", "pre-commit>=3.7,<5")


def _uv_context(**overrides):
    ctx = {
        "project_name": "test-proj",
        "project_import_name": "test_proj",
        "language": "python",
        "python_version": "3.12",
        "package_manager": "uv",
        "enable_smoke": False,
        "github_owner": "",
        "github_repo": "",
        "github_review_mode": "none",
    }
    ctx.update(overrides)
    return ctx


def _render(tmpl_name, context):
    env = render.build_env("python")
    return env.get_template(tmpl_name).render(**context)


# ──────────────────────────────────────────────────────────────────────
# Makefile (uv mode)
# ──────────────────────────────────────────────────────────────────────


def test_makefile_uv_renders_and_lists_targets(tmp_path):
    rendered = _render("Makefile.tmpl", _uv_context())
    mkf = tmp_path / "Makefile"
    mkf.write_text(rendered)
    result = subprocess.run(["make", "-f", str(mkf), "help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for target in ["help", "install", "install-hooks", "test", "lint", "format", "check", "run"]:
        assert target in result.stdout, f"target {target!r} missing from `make help`"
    # uv mode has NO `venv:` target (uv manages .venv/ itself). Match against the
    # target column specifically — substring check would false-positive on
    # description text like "creates .venv/". The help format is "  <target>  <desc>".
    target_column_pattern = re.compile(r"^\s*venv\s")
    assert not any(target_column_pattern.match(line) for line in result.stdout.splitlines()), (
        "uv mode must NOT expose a `venv` target"
    )


def test_makefile_uv_uses_uv_run_not_venv_bin(tmp_path):
    rendered = _render("Makefile.tmpl", _uv_context())
    # uv-mode substrings present
    assert "uv sync" in rendered
    assert "uv run pytest" in rendered
    assert "uv run ruff" in rendered
    assert "uv run python" in rendered
    # pip-mode substrings ABSENT — proves the branch isolation
    assert "./venv/bin/" not in rendered
    assert "pip install" not in rendered
    assert "-m venv venv" not in rendered  # `python3.12 -m venv venv`


def test_makefile_uv_install_has_preflight_guard_with_stderr_redirect():
    """Closes Codex iter-4 #2 + Tier-2 #6: install recipe must have the uv
    preflight guard AND redirect the error to stderr (`>&2`) so the
    smoke-test assertion that "stderr contains the install-hint" holds."""
    rendered = _render("Makefile.tmpl", _uv_context())
    assert "command -v uv >/dev/null 2>&1" in rendered
    assert "uv not on PATH" in rendered
    assert ">&2" in rendered  # the stderr redirect itself
    assert "--package-manager=pip" in rendered  # escape-hatch mention


def test_makefile_uv_install_hooks_uses_worktree_safe_guard():
    """install-hooks uses `git rev-parse --is-inside-work-tree` (worktree-safe),
    not `test -d .git` (fails in git worktrees per PR #3 iter-7 #1 lesson)."""
    rendered = _render("Makefile.tmpl", _uv_context())
    assert "git rev-parse --is-inside-work-tree" in rendered
    # In the uv branch, install-hooks runs `uv run pre-commit install`
    assert "uv run pre-commit install" in rendered


# ──────────────────────────────────────────────────────────────────────
# CI workflow (uv mode)
# ──────────────────────────────────────────────────────────────────────


def test_ci_yml_uv_parses_and_has_setup_uv():
    rendered = _render("ci.yml.tmpl", _uv_context())
    data = yaml.safe_load(rendered)
    steps = data["jobs"]["check"]["steps"]
    setup_uv = next((s for s in steps if "astral-sh/setup-uv" in s.get("uses", "")), None)
    assert setup_uv is not None, "setup-uv step missing"
    # Closes Codex iter-3 #1 + iter-5 #4: exact tag, NOT bare @v8
    assert setup_uv["uses"] == "astral-sh/setup-uv@v8.1.0"
    assert setup_uv["with"]["python-version"] == "3.12"


def test_ci_yml_uv_has_uv_version_diagnostic_step():
    rendered = _render("ci.yml.tmpl", _uv_context())
    data = yaml.safe_load(rendered)
    steps = data["jobs"]["check"]["steps"]
    diag = next((s for s in steps if s.get("run", "").strip() == "uv --version"), None)
    assert diag is not None, "`uv --version` diagnostic step missing"


def test_ci_yml_uv_has_uv_sync_locked_step():
    """Closes Codex iter-4 #1: CI runs `uv sync --locked` (npm-ci-style strict)
    so missing-from-git uv.lock fails CI loudly."""
    rendered = _render("ci.yml.tmpl", _uv_context())
    data = yaml.safe_load(rendered)
    steps = data["jobs"]["check"]["steps"]
    locked = next((s for s in steps if "uv sync --locked" in s.get("run", "")), None)
    assert locked is not None, "`uv sync --locked` step missing"


def test_ci_yml_uv_step_ordering():
    """Closes Codex iter-5 #2: parse workflow + assert exact ordering.
    Presence-only assertion would let an impl PR ship the steps in wrong order."""
    rendered = _render("ci.yml.tmpl", _uv_context())
    data = yaml.safe_load(rendered)
    steps = data["jobs"]["check"]["steps"]
    # Convert each step to a short identifier so order is greppable.
    identifiers = []
    for step in steps:
        if step.get("uses", "").startswith("actions/checkout"):
            identifiers.append("checkout")
        elif step.get("uses", "").startswith("astral-sh/setup-uv"):
            identifiers.append("setup-uv")
        elif step.get("run", "").strip() == "uv --version":
            identifiers.append("uv-version")
        elif "uv sync --locked" in step.get("run", ""):
            identifiers.append("uv-sync-locked")
        elif step.get("run", "").strip() == "make install":
            identifiers.append("make-install")
        elif step.get("run", "").strip() == "make check":
            identifiers.append("make-check")
    assert identifiers == [
        "checkout",
        "setup-uv",
        "uv-version",
        "uv-sync-locked",
        "make-install",
        "make-check",
    ], f"step order wrong: {identifiers}"
    # Closes Tier-1 F2: also assert no unknown steps were silently inserted.
    # Without this, an injected `pip install` step between `setup-uv` and
    # `make install` would be dropped by the if/elif chain and the test
    # would still pass with the expected identifiers list.
    assert len(steps) == 6, f"unexpected number of CI steps: {len(steps)}"


def test_ci_yml_uv_does_not_use_setup_python():
    """uv mode REPLACES setup-python (setup-uv sets up Python + uv in one step).
    Contrast with skill-repo's own CI which has both because the skill-repo runs
    multi-language smoke walks; generated projects use only setup-uv."""
    rendered = _render("ci.yml.tmpl", _uv_context())
    assert "actions/setup-python" not in rendered


# ──────────────────────────────────────────────────────────────────────
# pyproject.toml (uv mode — non-package shape)
# ──────────────────────────────────────────────────────────────────────


def test_pyproject_uv_parses_and_has_dependency_groups():
    rendered = _render("pyproject.toml.tmpl", _uv_context())
    data = tomllib.loads(rendered)
    assert data["project"]["name"] == "test-proj"
    assert data["project"]["dependencies"] == []
    assert "dependency-groups" in data
    assert "dev" in data["dependency-groups"]


def test_pyproject_uv_dev_deps_match_canonical_pins():
    """Both modes pin the same dev deps. Test parametrised against
    DEV_DEP_PINS (module-level constant) so a drift in either mode's
    template fails this test."""
    rendered = _render("pyproject.toml.tmpl", _uv_context())
    data = tomllib.loads(rendered)
    dev_deps = data["dependency-groups"]["dev"]
    for expected_pin in DEV_DEP_PINS:
        assert expected_pin in dev_deps, f"missing pin: {expected_pin}"


def test_pyproject_uv_has_no_build_system_table():
    """Closes Codex iter-1 #1: greenfield uv mode is 'non-package' mode.
    No [build-system] table → uv doesn't try to build the project as a wheel.
    The current `src/main.py` scaffold is an application starter, not a library."""
    rendered = _render("pyproject.toml.tmpl", _uv_context())
    data = tomllib.loads(rendered)
    assert "build-system" not in data, "uv mode must NOT have [build-system] (non-package)"
    assert "[build-system]" not in rendered  # belt + suspenders


def test_pyproject_uv_has_no_setuptools_section():
    """uv mode also drops [tool.setuptools] sections (relevant only for the
    pip+setuptools build path)."""
    rendered = _render("pyproject.toml.tmpl", _uv_context())
    assert "[tool.setuptools]" not in rendered


# ──────────────────────────────────────────────────────────────────────
# .python-version (uv mode — emitted only in uv mode)
# ──────────────────────────────────────────────────────────────────────


def test_python_version_uv_emitted_and_content():
    """`.python-version` is emitted in uv mode with content `{{python_version}}\\n`."""
    rendered = _render(".python-version.tmpl", _uv_context())
    assert rendered == "3.12\n"


def test_python_version_in_render_all_output_for_uv():
    """End-to-end: render_all puts `.python-version` in the uv-mode output."""
    output = render.render_all(_uv_context(), language="python")
    assert ".python-version" in output
    assert output[".python-version"] == b"3.12\n"


# ──────────────────────────────────────────────────────────────────────
# .pre-commit-config.yaml (uv mode — two branches)
# ──────────────────────────────────────────────────────────────────────


def test_pre_commit_config_uv_parses_and_pytest_entry_uses_uv_run():
    """Closes Codex iter-1 #3: .pre-commit-config.yaml is always emitted in
    both modes; only the pytest entry: line + lockstep-comment differ."""
    rendered = _render(".pre-commit-config.yaml.tmpl", _uv_context())
    data = yaml.safe_load(rendered)
    # ruff hook still present (shared across modes)
    repos = data["repos"]
    ruff_repo = next((r for r in repos if "ruff-pre-commit" in r["repo"]), None)
    assert ruff_repo is not None, "ruff-pre-commit repo missing"
    # pytest local hook entry uses `uv run` in uv mode
    local_repo = next((r for r in repos if r["repo"] == "local"), None)
    assert local_repo is not None, "local hooks repo missing"
    pytest_hook = next((h for h in local_repo["hooks"] if h["id"] == "pytest-pre-push"), None)
    assert pytest_hook is not None
    assert pytest_hook["entry"] == "uv run python -m pytest"


def test_pre_commit_config_uv_lockstep_comment_references_pyproject():
    """Closes Codex iter-4 #3: in uv mode, the rev-pin lockstep comment must
    reference `[dependency-groups].dev` (in pyproject.toml), NOT requirements-dev.txt
    (which doesn't exist in uv mode — that would be a dangling reference)."""
    rendered = _render(".pre-commit-config.yaml.tmpl", _uv_context())
    assert "[dependency-groups].dev" in rendered
    # And explicitly NOT the pip-mode wording:
    assert "requirements-dev.txt" not in rendered


# ──────────────────────────────────────────────────────────────────────
# render_all integration (uv context) — negative coverage
# ──────────────────────────────────────────────────────────────────────


def test_render_all_uv_omits_requirements_dev():
    """In uv mode, requirements-dev.txt is NOT in the planned files."""
    output = render.render_all(_uv_context(), language="python")
    assert "requirements-dev.txt" not in output


def test_render_all_uv_includes_pre_commit_config():
    """In uv mode, .pre-commit-config.yaml IS still emitted (only branched, not skipped)."""
    output = render.render_all(_uv_context(), language="python")
    assert ".pre-commit-config.yaml" in output
    # And its content is the uv-branch variant:
    assert b"uv run python -m pytest" in output[".pre-commit-config.yaml"]


def test_render_all_uv_strict_undefined_passes_with_full_context():
    """Sanity: uv-mode render_all under StrictUndefined doesn't crash on any
    template (paranoia regression for the `|default("pip")` filter convention)."""
    # Should not raise; also confirm we got a non-empty output dict.
    output = render.render_all(_uv_context(), language="python")
    assert output, "render_all returned empty dict"
