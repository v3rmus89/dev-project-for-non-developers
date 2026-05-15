"""Shim --help and full-CLI --help must produce byte-equal output (modulo
prog-name).

Closes Codex iter-16 finding #2: hand-mirrored argparse in two places would
silently drift; bootstrap_lib/_flags.py is the single source of truth.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


def _venv_python(tmp_path, *, with_jinja2: bool):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / "bin" / "python"
    if with_jinja2:
        subprocess.run(
            [str(py), "-m", "pip", "install", "jinja2"],
            check=True,
            capture_output=True,
        )
    return py


def test_shim_help_matches_full_cli_help(tmp_path):
    py_no_jinja = _venv_python(tmp_path / "no_jinja", with_jinja2=False)
    py_with_jinja = _venv_python(tmp_path / "with_jinja", with_jinja2=True)

    out_shim = subprocess.run(
        [str(py_no_jinja), str(BOOTSTRAP_PY), "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    out_full = subprocess.run(
        [str(py_with_jinja), str(BOOTSTRAP_PY), "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    # Both invocations come through the same prog name (bootstrap.py) so the
    # outputs should be byte-equal. If they ever differ, drift is real.
    assert out_shim == out_full
