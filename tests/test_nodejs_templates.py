"""Per-template render-and-parse checks for languages/nodejs/."""

from __future__ import annotations

import json
import subprocess

import jinja2
import pytest
import yaml

from bootstrap_lib import render


def _context(**overrides):
    ctx = {
        "project_name": "test-node",
        "project_import_name": "test_node",
        "language": "nodejs",
        "python_version": "3.12",
        "node_version": "24",
        "enable_smoke": False,
        "github_owner": "",
        "github_repo": "",
        "github_review_mode": "none",
    }
    ctx.update(overrides)
    return ctx


def _render(tmpl_name, context):
    env = render.build_env("nodejs")
    return env.get_template(tmpl_name).render(**context)


def test_makefile_renders_and_lists_targets(tmp_path):
    rendered = _render("Makefile.tmpl", _context())
    mkf = tmp_path / "Makefile"
    mkf.write_text(rendered)
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


def test_package_json_parses_as_json():
    rendered = _render("package.json.tmpl", _context(project_name="my-app"))
    data = json.loads(rendered)
    assert data["name"] == "my-app"
    assert data["type"] == "module"
    # Required scripts present
    for script in ["start", "test", "lint", "format", "typecheck", "prepare"]:
        assert script in data["scripts"], f"missing script: {script}"
    # Required devDeps present
    for dep in ["@biomejs/biome", "typescript", "vitest", "tsx", "husky", "lint-staged"]:
        assert dep in data["devDependencies"], f"missing devDep: {dep}"
    # No <pinned> placeholders (Codex iter-6 of PR #1 discipline)
    assert "<pinned>" not in rendered
    assert "<TODO>" not in rendered


def test_tsconfig_json_parses_as_strict_json():
    """Strict JSON, no comments — closes Codex iter-2 #3 / Claude iter-4 (tsconfig
    is JSONC in the wild; we ship strict for parseability)."""
    rendered = _render("tsconfig.json.tmpl", _context())
    data = json.loads(rendered)  # would raise on comments
    assert data["compilerOptions"]["strict"] is True
    assert data["compilerOptions"]["target"] == "ES2023"
    assert data["compilerOptions"]["module"] == "NodeNext"


def test_biome_json_parses_as_strict_json():
    rendered = _render("biome.json.tmpl", _context())
    data = json.loads(rendered)
    assert data["formatter"]["enabled"] is True
    assert data["linter"]["enabled"] is True


def test_vitest_config_has_key_directives():
    """Codex iter-4 #4 / Claude iter-4: don't try to TS-compile in Python.
    String-presence check on key directives instead. Full TS compile is
    exercised by test_smoke_nodejs_generated.py's `make check` step."""
    rendered = _render("vitest.config.ts.tmpl", _context())
    assert "defineConfig" in rendered
    assert "test:" in rendered or "test :" in rendered
    assert "globals" in rendered
    assert "node" in rendered  # environment: "node"


def test_gitignore_has_expected_lines():
    rendered = _render(".gitignore.tmpl", _context())
    for line in ["node_modules/", "dist/", ".husky/_/"]:
        assert line in rendered, f"missing {line!r} in .gitignore"
    # NOT ignored:
    assert "package-lock.json" not in rendered or "!package-lock.json" in rendered, (
        "package-lock.json must be committable"
    )


def test_ci_yml_parses_and_pins_node_24():
    """Closes Codex iter-2 #1: was 20 in earlier draft."""
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
    assert "actions/setup-node" in step_names[1]
    assert "npm ci" in step_names[2]
    assert "make check" in step_names[3]
    # Node version pinned to 24
    setup_node = next(s for s in steps if "setup-node" in s.get("uses", ""))
    assert setup_node["with"]["node-version"] == "24"


def test_husky_pre_commit_runs_lint_staged():
    rendered = _render(".husky-pre-commit.tmpl", _context())
    assert "lint-staged" in rendered


def test_husky_pre_push_runs_npm_test():
    rendered = _render(".husky-pre-push.tmpl", _context())
    assert "npm test" in rendered


def test_main_ts_compiles_syntactically_via_tsconfig_directives():
    """Just a string-presence check — full compile happens in the smoke test."""
    rendered = _render("src-main.ts.tmpl", _context(project_name="hello-world"))
    assert "hello-world" in rendered
    assert "console.log" in rendered


def test_test_smoke_ts_uses_vitest_imports():
    rendered = _render("tests-test_smoke.test.ts.tmpl", _context())
    assert "vitest" in rendered
    assert "test(" in rendered or "test (" in rendered


def test_strict_undefined_catches_missing_var():
    """StrictUndefined fires when context is incomplete."""
    env = render.build_env("nodejs")
    bad_ctx = {
        "language": "nodejs",
        "python_version": "3.12",
        # missing node_version
        "enable_smoke": False,
        "github_owner": "",
        "github_repo": "",
        "github_review_mode": "none",
    }
    with pytest.raises(jinja2.exceptions.UndefinedError):
        env.get_template("ci.yml.tmpl").render(**bad_ctx)
