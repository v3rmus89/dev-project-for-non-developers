"""Full generated-project smoke walk for Python + uv mode.

Parallel to `test_smoke_python_generated.py` (pip mode); this test bootstraps a
generated project with `--package-manager=uv`, then verifies the uv-specific
contracts end-to-end:
- `make install` runs `uv sync` and creates `.venv/` + `uv.lock`
- `uv.lock` is not gitignored AND is commit-eligible (real-world reproducibility)
- `make install-hooks` arms the pre-commit framework via `uv run pre-commit`
- `make check` (lint + test) is green
- `make run` prints the project name
- uv-preflight subtest: hiding `uv` from PATH triggers the friendly error
  with `--package-manager=pip` escape-hatch mention on stderr
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

EXPECTED_PATHS_UV_MODE = {
    "Makefile",
    "pyproject.toml",
    # NOTE: requirements-dev.txt explicitly NOT here (uv mode skips it).
    ".gitignore",
    ".pre-commit-config.yaml",
    ".editorconfig",
    ".github/workflows/ci.yml",
    ".python-version",  # uv-mode only
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "BACKLOG.md",
    "LESSONS.md",
    "docs/plans/README.md",
    "scripts/run-with-clean-env.py",
    "tests/test_smoke.py",
    "src/main.py",
}


def _require_uv():
    """Skip locally if `uv` is absent; fail-hard when CI=true (mirrors PR #3 Go pattern)."""
    if shutil.which("uv") is None:
        msg = "uv not on PATH"
        if os.environ.get("CI") == "true":
            pytest.fail(msg + " (CI must install uv via astral-sh/setup-uv@v8.1.0)")
        pytest.skip(msg)


def test_smoke_python_uv_generated(tmp_path):
    """Full end-to-end smoke walk for python + uv mode."""
    _require_uv()
    target = tmp_path / "smoke-uv"
    assert not target.exists()

    # Step 1 — dry-run, assert no writes + expected file set rendered
    dry = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--language",
            "python",
            "--package-manager",
            "uv",
            "--project-name",
            "smoke-uv",
            "--out",
            str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not target.exists(), "dry-run must not create --out"
    # requirements-dev.txt MUST NOT appear (uv mode skips it):
    assert "requirements-dev.txt" not in dry.stdout
    # .python-version MUST appear (uv mode emits it):
    assert ".python-version" in dry.stdout
    # All expected paths present:
    for path in EXPECTED_PATHS_UV_MODE:
        assert path in dry.stdout, f"dry-run missing expected path: {path}"

    # Step 2 — --apply
    subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--package-manager",
            "uv",
            "--project-name",
            "smoke-uv",
            "--out",
            str(target),
        ],
        check=True,
    )
    assert target.is_dir()
    # uv-mode-specific file present:
    assert (target / ".python-version").exists()
    assert (target / ".python-version").read_text() == "3.12\n"
    # pip-mode-specific file absent:
    assert not (target / "requirements-dev.txt").exists()

    # Step 3 — git init (uv sync needs a git repo? no, but install-hooks does)
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(target), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(target), check=True)

    # Step 4 — make install (uv sync; creates .venv/ + uv.lock)
    install = subprocess.run(["make", "install"], cwd=str(target), capture_output=True, text=True)
    assert install.returncode == 0, (
        f"make install failed:\nSTDOUT:\n{install.stdout}\nSTDERR:\n{install.stderr}"
    )

    # Step 4a — uv.lock created (closes Codex iter-4 #1: reproducibility claim)
    uv_lock = target / "uv.lock"
    assert uv_lock.exists(), "make install (uv sync) did not create uv.lock"

    # Step 4b — .venv/ created by uv (not venv/ — that's pip's convention)
    assert (target / ".venv").is_dir(), "uv sync should create .venv/, not venv/"
    assert not (target / "venv").exists(), "uv mode must NOT create venv/ (pip convention)"

    # Step 4c — uv.lock not gitignored
    gitignore = (target / ".gitignore").read_text()
    # Any rule matching uv.lock would be a regression. Check the obvious patterns.
    for forbidden in ["uv.lock\n", "uv.lock ", "/uv.lock", "*.lock"]:
        assert forbidden not in gitignore, (
            f"uv.lock would be gitignored by pattern {forbidden!r} in .gitignore"
        )

    # Step 4d — uv.lock is commit-eligible (stage it and verify it lands in the index)
    subprocess.run(["git", "add", "uv.lock"], cwd=str(target), check=True)
    indexed = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(target),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "uv.lock" in indexed.stdout.splitlines(), (
        "uv.lock should be commit-eligible after git add"
    )

    # Step 5 — make install-hooks (pre-commit framework via `uv run pre-commit`)
    install_hooks = subprocess.run(
        ["make", "install-hooks"], cwd=str(target), capture_output=True, text=True
    )
    assert install_hooks.returncode == 0, install_hooks.stderr

    # Step 6 — make check (lint + test) green
    check = subprocess.run(["make", "check"], cwd=str(target), capture_output=True, text=True)
    assert check.returncode == 0, (
        f"make check failed:\nSTDOUT:\n{check.stdout}\nSTDERR:\n{check.stderr}"
    )

    # Step 7 — make run prints the project name
    run = subprocess.run(
        ["make", "run"], cwd=str(target), capture_output=True, text=True, timeout=30
    )
    assert run.returncode == 0, run.stderr
    assert "smoke-uv" in run.stdout


def test_smoke_python_uv_install_no_head_then_install_hooks(tmp_path):
    """Run `make install-hooks` BEFORE the initial commit (no-HEAD path),
    then commit the bootstrap output. Hooks must not crash on a clean tree.

    Mirrors the no-HEAD-safe subtest from `test_smoke_python_generated.py`
    (which exists for pip mode); the uv hook is also `git rev-parse --verify
    HEAD` safe via the pre-commit framework.
    """
    _require_uv()
    target = tmp_path / "no-head"
    subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--package-manager",
            "uv",
            "--project-name",
            "no-head",
            "--out",
            str(target),
        ],
        check=True,
    )
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(target), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(target), check=True)
    # Install before any commit exists
    subprocess.run(["make", "install"], cwd=str(target), check=True, capture_output=True)
    subprocess.run(["make", "install-hooks"], cwd=str(target), check=True, capture_output=True)
    # Now commit; the pre-commit hook must succeed on a clean tree.
    subprocess.run(["git", "add", "."], cwd=str(target), check=True)
    commit = subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    assert commit.returncode == 0, (
        f"first commit (no prior HEAD) failed:\nSTDOUT:\n{commit.stdout}\nSTDERR:\n{commit.stderr}"
    )


def test_uv_preflight_fires_with_friendly_error(tmp_path):
    """Closes Codex iter-4 #2: when `uv` is missing from PATH, generated
    `make install` must print a friendly error to stderr (not bare
    `command not found`) including the install one-liners + the
    `--package-manager=pip` escape-hatch mention.
    """
    # No _require_uv() here — this subtest verifies behaviour when uv is
    # *absent*. We strip uv from PATH using a sanitized PATH env var.
    target = tmp_path / "preflight"
    # Bootstrap requires uv to NOT be required (it's only used by make install,
    # not by bootstrap itself). Bootstrap should succeed even without uv.
    subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--package-manager",
            "uv",
            "--project-name",
            "preflight",
            "--out",
            str(target),
        ],
        check=True,
    )
    # Strip every PATH entry that contains a `uv` binary.
    original_path = os.environ.get("PATH", "")
    sanitized_entries = []
    for entry in original_path.split(os.pathsep):
        if entry and (Path(entry) / "uv").exists():
            continue  # drop this PATH entry
        sanitized_entries.append(entry)
    sanitized_path = os.pathsep.join(sanitized_entries)
    env = {**os.environ, "PATH": sanitized_path}
    # Sanity — `uv` is now NOT findable from this PATH
    found_after = shutil.which("uv", path=sanitized_path)
    if found_after is not None:
        pytest.skip(f"could not strip uv from PATH (still found at {found_after})")
    # Run `make install` with uv hidden
    install = subprocess.run(
        ["make", "install"], cwd=str(target), capture_output=True, text=True, env=env
    )
    # Must fail
    assert install.returncode != 0, "make install should fail when uv is absent"
    # Friendly error message goes to STDERR (closes Codex iter-6 #1: >&2 redirect)
    combined = install.stdout + install.stderr
    assert "uv not on PATH" in combined
    # Install hint present
    assert "brew install uv" in combined or "astral.sh/uv/install.sh" in combined
    # Escape-hatch mention present
    assert "--package-manager=pip" in combined
    # And the friendly message went to stderr specifically (not stdout)
    assert "uv not on PATH" in install.stderr, (
        "uv-preflight error must be on stderr (not stdout) so CI tools / IDEs pick it up correctly"
    )
