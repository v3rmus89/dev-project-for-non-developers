"""Canonical check order: help → version → jinja2 → cli.

Per Codex iter-16: --install-hooks was removed, so the order is now
help → version → jinja2 → cli (4 branches, not 6).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


def _make_hermetic_venv(tmp_path, *, install_jinja2=False):
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


def test_help_works_without_jinja2(tmp_path):
    py = _make_hermetic_venv(tmp_path, install_jinja2=False)
    result = subprocess.run(
        [str(py), str(BOOTSTRAP_PY), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--language" in result.stdout
    assert "--apply" in result.stdout


def test_missing_jinja2_exits_2_with_hint(tmp_path):
    py = _make_hermetic_venv(tmp_path, install_jinja2=False)
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
    assert "jinja2" in result.stderr
    assert "make install" in result.stderr


def test_wrong_python_version_exits_2(tmp_path):
    """Skipped when python3.9 is unavailable. The shim must be 3.6-compatible
    so this test should run cleanly under 3.9 if present."""
    py39 = None
    for cand in ("python3.9", "python3.10", "python3.11"):
        result = subprocess.run(["which", cand], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            py39 = result.stdout.strip()
            break
    if py39 is None:
        import pytest

        pytest.skip("no pre-3.12 python on PATH")
    result = subprocess.run(
        [
            py39,
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
    assert "Python 3.12" in result.stderr


def test_happy_path_with_jinja2(tmp_path):
    py = _make_hermetic_venv(tmp_path, install_jinja2=True)
    target = tmp_path / "out"
    result = subprocess.run(
        [
            str(py),
            str(BOOTSTRAP_PY),
            "--language",
            "python",
            "--project-name",
            "happy",
            "--out",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "dry-run:" in result.stdout
