"""Per-template render-and-parse checks for languages/python/."""

from __future__ import annotations

import re
import subprocess
import tomllib

import jinja2
import pytest
import yaml

from bootstrap_lib import render


def _context(**overrides):
    ctx = {
        "project_name": "test-proj",
        "language": "python",
        "python_version": "3.12",
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


def test_makefile_renders_parses_lists_targets(tmp_path):
    rendered = _render("Makefile.tmpl", _context())
    mkf = tmp_path / "Makefile"
    mkf.write_text(rendered)
    # make -n is dry-parse; we use BSD make on macOS so just sanity-check
    # the help target lists what we expect.
    result = subprocess.run(["make", "-f", str(mkf), "help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for target in [
        "help",
        "install",
        "install-hooks",
        "test",
        "lint",
        "format",
        "check",
        "run",
        "review-plan-by-codex",
        "review-plan-by-claude",
        "review-commit-by-codex",
        "review-commit-by-claude",
        "review-plan-consistency-by-claude",
        "preflight-review-tooling",
    ]:
        assert target in result.stdout, f"{target!r} missing from `make help`"
    # the `make review` dispatcher (PR-2) is listed as its OWN target, distinct
    # from review-plan-by-* / review-commit-by-* (a bare `"review" in stdout`
    # would pass trivially on those substrings — match the first token instead).
    help_targets = [line.strip().split()[0] for line in result.stdout.splitlines() if line.strip()]
    assert "review" in help_targets, f"`review` dispatcher missing from `make help`: {help_targets}"
    # restart was removed per Codex iter-19 finding #3
    assert "restart" not in result.stdout


def test_makefile_install_does_not_call_pre_commit():
    """Codex iter-8 finding #3: generated `make install` must NOT run
    pre-commit install. That belongs to `make install-hooks`."""
    rendered = _render("Makefile.tmpl", _context())
    # Find the install target body
    lines = rendered.splitlines()
    in_install = False
    install_body = []
    for line in lines:
        if line.startswith("install:"):
            in_install = True
            continue
        if in_install:
            if line and not line.startswith(("\t", " ", "#")):
                break
            install_body.append(line)
    install_text = "\n".join(install_body)
    assert "pre-commit install" not in install_text


def test_makefile_install_hooks_has_git_guard():
    rendered = _render("Makefile.tmpl", _context())
    assert "test -d .git" in rendered
    assert "pre-commit install" in rendered


def test_pre_commit_config_yaml_parses():
    rendered = _render(".pre-commit-config.yaml.tmpl", _context())
    data = yaml.safe_load(rendered)
    assert isinstance(data, dict)
    assert "repos" in data
    repo_urls = [r.get("repo") for r in data["repos"]]
    assert any("ruff-pre-commit" in url for url in repo_urls)


def test_pyproject_toml_parses():
    rendered = _render("pyproject.toml.tmpl", _context())
    data = tomllib.loads(rendered)
    assert data["project"]["name"] == "test-proj"


def test_pyproject_has_ruff_config():
    """ruff config lives in [tool.ruff] (consolidated from the former
    standalone ruff.toml — see the config-shadowing fix plan)."""
    rendered = _render("pyproject.toml.tmpl", _context())
    data = tomllib.loads(rendered)
    ruff = data["tool"]["ruff"]
    assert ruff["line-length"] == 100
    assert ruff["target-version"] == "py312"
    assert "I" in ruff["lint"]["select"]
    assert ruff["format"]["quote-style"] == "double"
    # known-first-party was dropped (AD-3) — no isort table.
    assert "isort" not in ruff["lint"]


def test_pyproject_has_pytest_config():
    """pytest config lives in [tool.pytest.ini_options] (consolidated from
    the former standalone pytest.ini)."""
    rendered = _render("pyproject.toml.tmpl", _context())
    data = tomllib.loads(rendered)
    ini = data["tool"]["pytest"]["ini_options"]
    assert ini["testpaths"] == ["tests"]
    assert "--strict-config" in ini["addopts"]


def test_requirements_dev_no_placeholder():
    """Codex iter-6 finding #4."""
    rendered = _render("requirements-dev.txt.tmpl", _context())
    assert "<pinned>" not in rendered
    assert "<TODO>" not in rendered
    # Has concrete pins
    assert re.search(r"^ruff==\d", rendered, re.MULTILINE)
    assert re.search(r"^pytest", rendered, re.MULTILINE)
    assert re.search(r"^pre-commit", rendered, re.MULTILINE)


def test_gitignore_has_expected_lines():
    rendered = _render(".gitignore.tmpl", _context())
    for line in ["venv/", "__pycache__/", ".pytest_cache/"]:
        assert line in rendered


def test_ci_yml_parses_and_has_install_then_check():
    """Codex iter-4 finding #2: step ordering is checkout → setup-python →
    make install → make check."""
    rendered = _render("ci.yml.tmpl", _context())
    data = yaml.safe_load(rendered)
    steps = data["jobs"]["check"]["steps"]
    step_names = []
    for s in steps:
        if "uses" in s:
            step_names.append(s["uses"].split("@")[0])
        elif "name" in s:
            step_names.append(s["name"])
    assert "actions/checkout" in step_names[0]
    assert "actions/setup-python" in step_names[1]
    assert "make install" in step_names[2]
    assert "make check" in step_names[3]


def test_ci_yml_pins_python_version_to_312():
    """Codex iter-19 finding #4: hardcoded python_version='3.12'."""
    rendered = _render("ci.yml.tmpl", _context())
    data = yaml.safe_load(rendered)
    setup_py_step = next(
        s for s in data["jobs"]["check"]["steps"] if "setup-python" in s.get("uses", "")
    )
    assert setup_py_step["with"]["python-version"] == "3.12"


def test_test_smoke_py_compiles():
    rendered = _render("tests-test_smoke.py.tmpl", _context())
    compile(rendered, "<rendered-test_smoke.py>", "exec")


def test_main_py_compiles_and_prints_project_name():
    rendered = _render("src-main.py.tmpl", _context(project_name="my-proj"))
    compile(rendered, "<rendered-main.py>", "exec")
    assert "my-proj" in rendered


def test_strict_undefined_catches_missing_var():
    """Codex iter-11 finding #1: StrictUndefined catches unsubstituted vars."""
    env = render.build_env("python")
    # Render with a context missing `project_name`
    bad_ctx = {
        "language": "python",
        "python_version": "3.12",
        "enable_smoke": False,
        "github_owner": "",
        "github_repo": "",
        "github_review_mode": "none",
    }
    with pytest.raises(jinja2.exceptions.UndefinedError):
        env.get_template("src-main.py.tmpl").render(**bad_ctx)


# ──────────────────────────────────────────────────────────────────────
# _emit_python_in_pm_mode — package-manager-aware filtering (PR #6)
# ──────────────────────────────────────────────────────────────────────


def test_emit_python_in_pm_mode_uv_skips_requirements_dev():
    """In uv mode, requirements-dev.txt is NOT emitted (deps live in pyproject)."""
    assert render._emit_python_in_pm_mode("requirements-dev.txt", "uv") is False


def test_emit_python_in_pm_mode_pip_emits_requirements_dev():
    """In pip mode, requirements-dev.txt IS emitted (legacy pip flow)."""
    assert render._emit_python_in_pm_mode("requirements-dev.txt", "pip") is True


def test_emit_python_in_pm_mode_uv_emits_python_version():
    """In uv mode, .python-version IS emitted (uv reads it for `uv python install`)."""
    assert render._emit_python_in_pm_mode(".python-version", "uv") is True


def test_emit_python_in_pm_mode_pip_skips_python_version():
    """In pip mode, .python-version is NOT emitted (pip doesn't use it; would just be noise)."""
    assert render._emit_python_in_pm_mode(".python-version", "pip") is False


def test_emit_python_in_pm_mode_pre_commit_config_always_emitted():
    """`.pre-commit-config.yaml` is always emitted (closes Codex iter-1 #3 — scope
    contradiction; framework stays in both modes, only the pytest entry differs)."""
    assert render._emit_python_in_pm_mode(".pre-commit-config.yaml", "uv") is True
    assert render._emit_python_in_pm_mode(".pre-commit-config.yaml", "pip") is True


def test_emit_python_in_pm_mode_unrelated_files_always_emitted():
    """Files outside the pm-aware set are emitted regardless of mode."""
    for rel_out in [
        "Makefile",
        "pyproject.toml",
        ".gitignore",
        ".github/workflows/ci.yml",
        "tests/test_smoke.py",
        "src/main.py",
    ]:
        assert render._emit_python_in_pm_mode(rel_out, "uv") is True, rel_out
        assert render._emit_python_in_pm_mode(rel_out, "pip") is True, rel_out


def test_emit_python_in_pm_mode_none_normalizes_to_pip():
    """`package_manager=None` (non-aware caller) must normalize to pip-mode behaviour.

    Closes Codex Tier-2 #6: without the `pm = package_manager or "pip"`
    normalization, neither `None == "uv"` nor `None == "pip"` would match,
    so both `requirements-dev.txt` AND `.python-version` would render —
    contradicting the shared-templates `|default("pip")` safety net.
    """
    # Same behaviour as pip mode:
    assert render._emit_python_in_pm_mode("requirements-dev.txt", None) is True  # rendered (pip)
    assert render._emit_python_in_pm_mode(".python-version", None) is False  # skipped (pip)
    assert render._emit_python_in_pm_mode(".pre-commit-config.yaml", None) is True
    assert render._emit_python_in_pm_mode("Makefile", None) is True


def test_render_all_filters_python_by_package_manager_uv(tmp_path):
    """render_all with package_manager="uv": requirements-dev.txt NOT in output.

    `.python-version` not in output either because the template doesn't
    exist yet (added in PR #6 Step 5). Once Step 5 lands, an integration
    test asserts `.python-version` IS in output for uv mode. For now,
    Step 4's contract is verified by the helper unit tests above.
    """
    ctx = _context(package_manager="uv")
    output = render.render_all(ctx, language="python")
    assert "requirements-dev.txt" not in output


def test_render_all_filters_python_by_package_manager_pip(tmp_path):
    """render_all with package_manager="pip": requirements-dev.txt IS in output,
    .python-version NOT in output, .pre-commit-config pytest entry is pip-form.

    The full plan assertion set (Bucket D test row): asserts pip-mode renders
    `requirements-dev.txt` AND `.pre-commit-config.yaml`'s pytest entry
    contains `./venv/bin/python -m pytest` AND `.python-version` is NOT
    rendered. Closes Tier-1 F1 + F2 (missing assertions from the plan).
    """
    ctx = _context(package_manager="pip")
    output = render.render_all(ctx, language="python")
    assert "requirements-dev.txt" in output
    assert ".python-version" not in output  # closes Tier-1 F2 (pip-mode skip)
    # closes Tier-1 F1 — pre-commit-config pytest entry is pip-form (./venv/bin/python).
    # The .pre-commit-config.yaml.tmpl is single-branch today (pip default); when Step
    # 6 lands the two-branch form, this assertion guards against accidental flip.
    assert b"./venv/bin/python -m pytest" in output[".pre-commit-config.yaml"]


def test_render_all_missing_package_manager_key_renders_pip_mode(tmp_path):
    """render_all without `package_manager` in context normalizes to pip-mode.

    Closes Codex Tier-2 #6 end-to-end: existing tests + non-aware callers
    that omit `"package_manager"` from their context dict get pip-mode
    output (the pre-PR-#6 default), not a half-uv / half-pip mix.

    NOTE: Full coverage of the shared-templates `|default("pip")` filter
    (assertion (a): "no UndefinedError raised") lands after PR #6 Step 7
    (Bucket C shared template branches). Step 4's check here covers the
    render-layer normalization only.
    """
    # _context() omits package_manager by default — exactly the scenario.
    ctx = _context()
    assert "package_manager" not in ctx
    output = render.render_all(ctx, language="python")
    # pip-mode behaviour: requirements-dev.txt rendered.
    assert "requirements-dev.txt" in output
    assert ".python-version" not in output  # closes Tier-1 F2 (pip-mode skip)
    # closes Tier-1 F1 — pre-commit-config pytest entry is pip-form.
    assert b"./venv/bin/python -m pytest" in output[".pre-commit-config.yaml"]
