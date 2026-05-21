"""Per-template render-and-parse checks for languages/go/."""

from __future__ import annotations

import subprocess

import jinja2
import pytest
import yaml

from bootstrap_lib import render


def _context(**overrides):
    ctx = {
        "project_name": "test-go",
        "language": "go",
        "python_version": "3.12",
        "node_version": "24",
        "go_version": "1.26",
        "enable_smoke": False,
        "github_owner": "",
        "github_repo": "",
        "github_review_mode": "none",
    }
    ctx.update(overrides)
    return ctx


def _render(tmpl_name, context):
    env = render.build_env("go")
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


def test_makefile_uses_project_local_bin():
    """Codex iter-3 #1: tools must be installed/invoked via ./bin/, not bare names."""
    rendered = _render("Makefile.tmpl", _context())
    # Tool install uses GOBIN
    assert 'GOBIN="$(CURDIR)/bin"' in rendered
    # Lint + format use ./bin/ prefix
    assert "./bin/gofumpt" in rendered
    assert "./bin/golangci-lint" in rendered


def test_makefile_pins_tool_versions_no_latest():
    """Closes Codex iter-1 #5 + iter-2 #6 + iter-4 #5: no @latest in install commands."""
    rendered = _render("Makefile.tmpl", _context())
    assert "@latest" not in rendered, "tool installs must be pinned, not @latest"
    # Pinned versions are present
    assert "GOFUMPT_VERSION" in rendered
    assert "GOLANGCI_LINT_VERSION" in rendered


def test_makefile_uses_v2_golangci_lint_module_path():
    """Codex iter-2 #1: v2 install path requires `/v2/` segment."""
    rendered = _render("Makefile.tmpl", _context())
    assert "github.com/golangci/golangci-lint/v2/cmd/golangci-lint" in rendered


def test_makefile_install_hooks_has_git_guard():
    """Codex iter-4 #4 + iter-7 + iter-7-followup: install-hooks must guard on
    git-repo presence first via `git rev-parse --is-inside-work-tree` (so git
    worktrees with `.git` file are detected — `test -d .git` would skip them).
    AND uses `git rev-parse --git-path hooks/...` for the existing-hooks warning
    so that in a worktree we check the COMMON repo's hooks/ (where Git actually
    resolves default hooks from per the docs for `--git-path`), not the
    worktree-specific `.git/worktrees/<name>/hooks/` which Git does not consult
    for defaults."""
    rendered = _render("Makefile.tmpl", _context())
    assert "git rev-parse --is-inside-work-tree" in rendered
    assert "git rev-parse --git-path hooks/pre-commit" in rendered
    assert "git rev-parse --git-path hooks/pre-push" in rendered


def test_go_mod_uses_github_path_when_coords_set():
    rendered = _render(
        "go.mod.tmpl",
        _context(github_owner="example", github_repo="my-go-proj"),
    )
    assert rendered.startswith("module github.com/example/my-go-proj\n")
    assert "go 1.26" in rendered


def test_go_mod_falls_back_to_project_name_when_coords_missing():
    rendered = _render("go.mod.tmpl", _context(project_name="standalone"))
    assert rendered.startswith("module standalone\n")
    assert "go 1.26" in rendered


def test_golangci_yml_parses_as_v2():
    """Closes Codex iter-2 #2: v2 config schema; gofmt/formatters NOT in linters list."""
    rendered = _render(".golangci.yml.tmpl", _context())
    data = yaml.safe_load(rendered)
    assert data["version"] == 2 or data["version"] == "2"
    # Expected v2 linters (no `gofmt` — formatters moved to a separate block in v2)
    enabled = data["linters"]["enable"]
    for linter in ["govet", "staticcheck", "errcheck"]:
        assert linter in enabled, f"missing {linter} in golangci-lint v2 linters"
    # No `gofmt` in the linters list (moved to formatters in v2)
    assert "gofmt" not in enabled
    assert "gofumpt" not in enabled


def test_gitignore_has_expected_lines():
    rendered = _render(".gitignore.tmpl", _context())
    for line in ["*.test", "*.out", "bin/", "*.exe"]:
        assert line in rendered, f"missing {line!r} in .gitignore"


def test_ci_yml_pins_go_26_and_cache_false():
    """Closes Codex iter-1 #3 (Go 1.26 pin) + iter-4 #2 (cache: false for no-go.sum)."""
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
    assert "actions/setup-go" in step_names[1]
    assert "make install" in step_names[2]
    assert "make check" in step_names[3]
    # Go version pinned to 1.26
    setup_go = next(s for s in steps if "setup-go" in s.get("uses", ""))
    assert setup_go["with"]["go-version"] == "1.26"
    # cache: false (no go.sum in stdlib-only smoke)
    assert setup_go["with"]["cache"] is False


def test_hooks_pre_commit_robust_format_check():
    """Closes Codex iter-1 #2: gofumpt -l doesn't exit non-zero on dirty; shell pattern needed."""
    rendered = _render("hooks-pre-commit.tmpl", _context())
    # The robust pattern: capture output, exit 1 if non-empty
    assert "./bin/gofumpt -l" in rendered
    assert 'if [ -n "$out" ]' in rendered
    assert "exit 1" in rendered


def test_hooks_pre_commit_no_head_safe():
    """Closes Codex iter-1 #3: lint must work on greenfield (no HEAD)."""
    rendered = _render("hooks-pre-commit.tmpl", _context())
    assert "git rev-parse --verify HEAD" in rendered


def test_hooks_pre_push_runs_go_test():
    rendered = _render("hooks-pre-push.tmpl", _context())
    assert "go test ./..." in rendered


def test_main_go_compiles_and_prints_project_name():
    rendered = _render("main.go.tmpl", _context(project_name="hello-go"))
    assert "package main" in rendered
    assert "hello-go" in rendered
    assert "fmt.Println" in rendered


def test_main_test_go_uses_testing_package():
    rendered = _render("main_test.go.tmpl", _context())
    assert "package main" in rendered
    assert 'import "testing"' in rendered
    assert "func Test" in rendered


def test_strict_undefined_catches_missing_go_version():
    """StrictUndefined fires when context is incomplete."""
    env = render.build_env("go")
    bad_ctx = {
        "language": "go",
        "python_version": "3.12",
        "node_version": "24",
        # missing go_version
        "enable_smoke": False,
        "github_owner": "",
        "github_repo": "",
        "github_review_mode": "none",
    }
    with pytest.raises(jinja2.exceptions.UndefinedError):
        env.get_template("ci.yml.tmpl").render(**bad_ctx)
