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
    ".gitignore",
    ".pre-commit-config.yaml",
    ".editorconfig",
    ".github/workflows/ci.yml",
    ".github/pull_request_template.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "BACKLOG.md",
    "LESSONS.md",
    "docs/plans/README.md",
    "scripts/run-with-clean-env.py",
    "scripts/loop-status.py",
    "tests/test_smoke.py",
    "src/main.py",
}


def test_smoke_python_generated(tmp_path):
    target = tmp_path / "smoke-test"
    assert not target.exists()

    # Step 1: dry-run, assert no writes.
    # Explicit --package-manager=pip so PR #6's default shift to uv doesn't
    # change this test's expected file set (uv mode skips requirements-dev.txt
    # and adds .python-version). uv-mode smoke walk lives in
    # test_smoke_python_uv_generated.py (added in a later PR #6 step).
    dry = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--language",
            "python",
            "--package-manager",
            "pip",
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

    # Step 2: --apply (same explicit --package-manager=pip)
    subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--package-manager",
            "pip",
            "--project-name",
            "smoke-test",
            "--out",
            str(target),
        ],
        check=True,
    )
    assert target.is_dir()

    # PR #5a post-apply assertion: LESSONS.md is emitted with the expected
    # schema headings. Closes Tier-1 P1 — Plan Bucket F asked for this in
    # the smoke tests' post-apply blocks specifically (not just dry-run).
    lessons_path = target / "LESSONS.md"
    assert lessons_path.exists(), "LESSONS.md must be written by --apply"
    lessons_text = lessons_path.read_text()
    assert lessons_text.startswith("# Lessons"), "LESSONS.md must start with top heading"
    assert "## Active" in lessons_text, "LESSONS.md must have Active section"
    assert "## Archived" in lessons_text, "LESSONS.md must have Archived section"

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

    # V-2.2: scripts/loop-status.py is rendered, executable, and exits 0 with
    # "STATUS: no-iters" when no plan-review files exist for the given KEY.
    import os

    loop_status = target / "scripts" / "loop-status.py"
    assert loop_status.exists(), "scripts/loop-status.py must be rendered by --apply"
    assert os.access(loop_status, os.X_OK), "scripts/loop-status.py must be executable"
    ls_result = subprocess.run(
        [str(loop_status), "dummykey000000", str(target)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert ls_result.returncode == 0, f"loop-status with no files must exit 0: {ls_result.stderr}"
    assert "STATUS: no-iters" in ls_result.stdout, (
        f"expected 'STATUS: no-iters' when no review files present; got: {ls_result.stdout!r}"
    )
