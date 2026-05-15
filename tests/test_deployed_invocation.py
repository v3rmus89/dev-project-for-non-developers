"""Deployment / invocation contract — hermetic temp-venv tests.

Closes Codex iter-10 finding #1: missing-dep test must not depend on
whatever jinja2 happens to be in the parent test env or in system python3.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


def _hermetic_venv(tmp_path, *, install_jinja2=False):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / "bin" / "python"
    if install_jinja2:
        subprocess.run(
            [str(py), "-m", "pip", "install", "jinja2"],
            check=True,
            capture_output=True,
        )
    return py


def test_happy_path_from_other_cwd(tmp_path):
    py = _hermetic_venv(tmp_path, install_jinja2=True)
    target = tmp_path / "elsewhere"
    other_cwd = tmp_path / "elsewhere-cwd"
    other_cwd.mkdir()
    result = subprocess.run(
        [
            str(py),
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--project-name",
            "happy",
            "--out",
            str(target),
        ],
        cwd=str(other_cwd),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (target / "Makefile").exists()


def test_hermetic_missing_jinja2_exits_2(tmp_path):
    py = _hermetic_venv(tmp_path, install_jinja2=False)
    result = subprocess.run(
        [
            str(py),
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "missing dep" in result.stderr
    assert "make install" in result.stderr


def test_restore_hint_command_is_runnable(tmp_path):
    """Codex iter-7 finding #1 + iter-8 finding #1: rollback hint must work
    from any cwd, using sys.executable + absolute bootstrap.py path."""
    py = _hermetic_venv(tmp_path, install_jinja2=True)
    target = tmp_path / "proj"
    result = subprocess.run(
        [
            str(py),
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--project-name",
            "rollback",
            "--out",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # Pull out the restore command
    restore_line = [line for line in result.stdout.splitlines() if line.startswith("to rollback:")]
    assert restore_line
    cmd_str = restore_line[0].split(":", 1)[1].strip()
    # Run from a totally unrelated cwd
    far_away = tmp_path / "far-away"
    far_away.mkdir()
    result2 = subprocess.run(cmd_str, shell=True, cwd=str(far_away), capture_output=True, text=True)
    assert result2.returncode == 0, result2.stderr
