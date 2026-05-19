"""Generated `make install-hooks` test (Subsystem F).

Closes Codex iter-16 finding #1 + iter-17 finding #2: hook script must
reference the TARGET project's venv/bin/python, NOT the skill repo's
venv/bin/python (proves the hook is scoped to the target).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


def test_generated_install_hooks_uses_target_venv(tmp_path):
    target = tmp_path / "proj"

    # 1. Bootstrap into the tempdir.
    # Explicit --package-manager=pip so PR #6's default shift to uv doesn't
    # break this test (the test asserts pip-mode artifacts: ./venv/bin/python
    # in the hook). uv-mode equivalent lives in test_smoke_python_uv_generated.py.
    result = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--package-manager",
            "pip",
            "--project-name",
            "hooks-test",
            "--out",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    # 2. Initialize as git repo so install-hooks won't bail
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    # configure local git so commits work if needed later
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(target), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(target), check=True)

    # 3. make install + make install-hooks
    install = subprocess.run(["make", "install"], cwd=str(target), capture_output=True, text=True)
    assert install.returncode == 0, install.stderr

    install_hooks = subprocess.run(
        ["make", "install-hooks"], cwd=str(target), capture_output=True, text=True
    )
    assert install_hooks.returncode == 0, install_hooks.stderr

    # 4. Assertions
    pre_commit_hook = target / ".git" / "hooks" / "pre-commit"
    assert pre_commit_hook.exists(), "pre-commit hook not registered"
    hook_text = pre_commit_hook.read_text()

    # (b) Ownership: target project's venv must appear SOMEWHERE in the hook
    target_venv_py = (target / "venv" / "bin" / "python").resolve()
    assert str(target_venv_py) in hook_text or "venv/bin/python" in hook_text, (
        f"target venv not referenced in hook:\n{hook_text}"
    )

    # (c) Negative ownership: skill repo's venv must NOT appear
    skill_venv_py = (SKILL_ROOT / "venv" / "bin" / "python").resolve()
    assert str(skill_venv_py) not in hook_text, (
        f"skill repo venv leaked into target's hook:\n{hook_text}"
    )
