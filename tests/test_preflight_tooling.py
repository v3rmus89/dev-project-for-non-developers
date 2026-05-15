"""Shim-only tests for make preflight-review-tooling.

Codex iter-2 finding #3: `make check` must NOT consume Claude/Codex
subscription quota. Real-CLI invocation is a manual step.

Four layers:
(a) missing CLI: PATH omits codex/claude → exit 2 with "CLI not found"
(b) flag-smoke failure: shim CLI exits non-zero → exit 2 with "flag smoke failed"
(c) version-drift advisory: shim succeeds but reports a non-baseline version
    → exit 0 with WARN
(d) shim success path: shim succeeds + baseline version → exit 0 + no WARN
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


def _bootstrap_fixture(tmp_path):
    target = tmp_path / "proj"
    result = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--project-name",
            "preflight-fixture",
            "--out",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return target


def _shim_script(version_string, exit_code=0):
    """Generate a shim script that reports a fixed --version and otherwise
    succeeds. exit_code controls the non-version branch."""
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env python3
        import sys
        argv = sys.argv[1:]
        if "--version" in argv:
            print({version_string!r})
            sys.exit(0)
        out = None
        i = 0
        while i < len(argv):
            if argv[i] == "--output-last-message":
                out = argv[i + 1]
                i += 2
                continue
            i += 1
        if out:
            with open(out, "w") as f:
                f.write("ok\\n")
        sys.exit({exit_code})
        """
    )


def _path_with_shims(tmp_path, name, content):
    shim_dir = tmp_path / f"shims-{name}"
    shim_dir.mkdir()
    # Both codex and claude shims need to exist for preflight to find them
    for tool in ("codex", "claude"):
        f = shim_dir / tool
        f.write_text(content)
        f.chmod(0o755)
    return shim_dir


def _run_preflight(target, env):
    return subprocess.run(
        ["make", "-C", str(target), "preflight-review-tooling"],
        env=env,
        capture_output=True,
        text=True,
    )


def test_a_missing_cli_exits_nonzero(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    env = os.environ.copy()
    # Restrict PATH to /usr/bin:/bin — claude/codex won't be there
    env["PATH"] = "/usr/bin:/bin"
    result = _run_preflight(target, env)
    assert result.returncode != 0
    assert "not found" in result.stdout + result.stderr


def test_b_flag_smoke_failure_exits_nonzero(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    shim_dir = _path_with_shims(tmp_path, "fail", _shim_script("0.130.0", exit_code=1))
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:/usr/bin:/bin"
    result = _run_preflight(target, env)
    assert result.returncode != 0
    assert "flag smoke failed" in result.stdout + result.stderr


def test_c_version_drift_emits_warn_but_passes(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    shim_dir = _path_with_shims(tmp_path, "drift", _shim_script("9.99.0", exit_code=0))
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:/usr/bin:/bin"
    result = _run_preflight(target, env)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "WARN" in combined
    assert "tested baseline" in combined


def test_d_shim_success_path(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    # Need TWO version strings — codex 0.130.x and claude 2.1.139
    shim_dir = tmp_path / "shims-success"
    shim_dir.mkdir()
    (shim_dir / "codex").write_text(_shim_script("codex-cli 0.130.0", 0))
    (shim_dir / "codex").chmod(0o755)
    (shim_dir / "claude").write_text(_shim_script("2.1.139 (Claude Code)", 0))
    (shim_dir / "claude").chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:/usr/bin:/bin"
    result = _run_preflight(target, env)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "WARN" not in combined
    assert "preflight ok" in combined
