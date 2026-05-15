"""SIGTERM mid-apply test with deterministic sentinel sync.

Closes Codex iter-5 finding #2 (polling for a transient `.bootstrap-tmp`
artifact was racy) and iter-2 finding #2 (byte-identical rollback).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


def test_sigterm_mid_apply_leaves_no_tmp_artifacts(tmp_path):
    target = tmp_path / "proj"
    sentinel = tmp_path / "sentinel.touch"

    env = os.environ.copy()
    env["DEV_PROJECT_SETUP_PAUSE_AFTER_FIRST_WRITE"] = str(sentinel)
    env["TMPDIR"] = str(tmp_path)

    proc = subprocess.Popen(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--project-name",
            "sigterm-test",
            "--out",
            str(target),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for the sentinel file to appear (deterministic)
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if sentinel.exists():
            break
        time.sleep(0.05)
    else:
        proc.kill()
        out, err = proc.communicate(timeout=5)
        raise AssertionError(f"sentinel never touched. stdout={out}, stderr={err}")

    # The first file should be on disk (the apply paused AFTER its first
    # successful os.rename).
    # No .bootstrap-tmp residue at this point.
    leftover = list(target.rglob("*.bootstrap-tmp"))
    assert leftover == [], leftover

    # SIGTERM the process
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=10)

    # After SIGTERM cleanup, no .bootstrap-tmp files left
    leftover_after = list(target.rglob("*.bootstrap-tmp"))
    assert leftover_after == [], leftover_after
