"""Full generated-project smoke walk.

Closes Codex iter-2 finding #4 (dry-run is filesystem-pure), iter-3 finding #2
(make install before make check), iter-11 finding #4 (dry-run printed file
list), iter-16 finding #4 (make run smoke-tested).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"

EXPECTED_PATHS_NONE_MODE = {
    "Makefile",
    "pyproject.toml",
    "requirements-dev.txt",
    "ruff.toml",
    "pytest.ini",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".editorconfig",
    ".github/workflows/ci.yml",
    ".github/pull_request_template.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "BACKLOG.md",
    "docs/plans/README.md",
    "scripts/run-with-clean-env.py",
    "tests/test_smoke.py",
    "src/main.py",
}


def test_smoke_python_generated(tmp_path):
    target = tmp_path / "smoke-test"
    assert not target.exists()

    # Step 1: dry-run, assert no writes
    dry = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--language",
            "python",
            "--project-name",
            "smoke-test",
            "--out",
            str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not target.exists(), "dry-run must not create --out"
    # Default mode is `none` — no claude-review.yml emitted
    assert ".github/workflows/claude-review.yml" not in dry.stdout
    for path in EXPECTED_PATHS_NONE_MODE:
        assert path in dry.stdout, f"dry-run missing expected path: {path}"

    # Step 2: --apply
    subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--project-name",
            "smoke-test",
            "--out",
            str(target),
        ],
        check=True,
    )
    assert target.is_dir()

    # Step 3: make install (creates per-project venv + installs deps)
    install = subprocess.run(["make", "install"], cwd=str(target), capture_output=True, text=True)
    assert install.returncode == 0, install.stderr

    # Step 4: make check
    check = subprocess.run(["make", "check"], cwd=str(target), capture_output=True, text=True)
    assert check.returncode == 0, check.stderr

    # Step 5: make run (Codex iter-16 finding #4)
    run = subprocess.run(
        ["make", "run"],
        cwd=str(target),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run.returncode == 0, run.stderr
    assert "smoke-test" in run.stdout
