"""Per-template render-and-parse checks for languages/python/."""

from __future__ import annotations

import configparser
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
        "project_import_name": "test_proj",
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


def test_requirements_dev_no_placeholder():
    """Codex iter-6 finding #4."""
    rendered = _render("requirements-dev.txt.tmpl", _context())
    assert "<pinned>" not in rendered
    assert "<TODO>" not in rendered
    # Has concrete pins
    assert re.search(r"^ruff==\d", rendered, re.MULTILINE)
    assert re.search(r"^pytest", rendered, re.MULTILINE)
    assert re.search(r"^pre-commit", rendered, re.MULTILINE)


def test_ruff_toml_parses():
    rendered = _render("ruff.toml.tmpl", _context())
    data = tomllib.loads(rendered)
    assert data["line-length"] == 100
    assert data["target-version"] == "py312"


def test_pytest_ini_parses(tmp_path):
    rendered = _render("pytest.ini.tmpl", _context())
    cp = configparser.ConfigParser()
    cp.read_string(rendered)
    assert cp.has_section("pytest")
    assert cp.get("pytest", "testpaths") == "tests"


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
