"""Full generated-project smoke walk for Node-TS language.

Mirrors `test_smoke_python_generated.py`. Skipped when `node` is not on
PATH locally; FAILS HARD in CI (when `CI=true` env var is set) so missing
Node setup can't silently hide the gate.

Closes Codex iter-2 #3 + Claude iter-4 #6 (deterministic hook-fired assertion).
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

EXPECTED_PATHS_NONE_MODE = {
    "Makefile",
    "package.json",
    "tsconfig.json",
    "biome.json",
    "vitest.config.ts",
    ".gitignore",
    ".github/workflows/ci.yml",
    ".github/pull_request_template.md",
    ".husky/pre-commit",
    ".husky/pre-push",
    ".editorconfig",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "BACKLOG.md",
    "LESSONS.md",
    "docs/plans/README.md",
    "scripts/run-with-clean-env.py",
    "tests/test_smoke.test.ts",
    "src/main.ts",
}


def _require_node():
    """In CI, fail hard if node is missing. Locally, skip cleanly."""
    if shutil.which("node") is None:
        if os.environ.get("CI") == "true":
            pytest.fail("node is not on PATH but CI=true — CI must have actions/setup-node")
        pytest.skip("node not on PATH (local dev environment)")


def test_smoke_nodejs_generated(tmp_path):
    _require_node()

    target = tmp_path / "smoke-test"
    assert not target.exists()

    # Step 1: dry-run, assert filesystem-pure
    dry = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--language",
            "nodejs",
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
    for path in EXPECTED_PATHS_NONE_MODE:
        assert path in dry.stdout, f"dry-run missing expected path: {path}"

    # Step 2: --apply
    subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "nodejs",
            "--project-name",
            "smoke-test",
            "--out",
            str(target),
        ],
        check=True,
    )
    assert target.is_dir()

    # Step 3: git init + user config (required BEFORE install-hooks because
    # install-hooks has a `test -d .git` guard; closes Codex iter-3 #2)
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(target), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(target), check=True)
    # Initial commit so subsequent commits in step 8 have HEAD to diff against
    subprocess.run(["git", "add", "."], cwd=str(target), check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial bootstrap", "--no-verify"],
        cwd=str(target),
        check=True,
        capture_output=True,
    )

    # Step 4: make install (npm install)
    install = subprocess.run(
        ["make", "install"],
        cwd=str(target),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert install.returncode == 0, install.stderr

    # Step 5: make install-hooks (defensive re-arm — npm install's prepare
    # script already did the work, but the explicit re-arm should be idempotent)
    install_hooks = subprocess.run(
        ["make", "install-hooks"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    assert install_hooks.returncode == 0, install_hooks.stderr

    # Step 6: make check (biome + tsc --noEmit + vitest)
    check = subprocess.run(
        ["make", "check"],
        cwd=str(target),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert check.returncode == 0, check.stderr

    # Step 7: make run (prints "hello from smoke-test")
    run = subprocess.run(
        ["make", "run"],
        cwd=str(target),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr
    assert "smoke-test" in run.stdout

    # Step 8: commit-fires-hook deterministic assertion (closes Claude iter-4 #6)
    # Write a TS file with single quotes — Biome's formatter (configured for
    # double quotes) rewrites to double quotes. This is a SAFE fix (not an
    # unsafe rewrite like `var`→`const`), so lint-staged applies it.
    fresh = target / "src" / "test-hook.ts"
    fresh.write_text("const greeting = 'hello';\nconsole.log(greeting);\n")
    subprocess.run(["git", "add", str(fresh)], cwd=str(target), check=True)
    commit = subprocess.run(
        ["git", "commit", "-m", "test hook"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    assert commit.returncode == 0, commit.stderr

    # Verify the hook actually ran: Biome's formatter rewrites 'hello' to "hello"
    show = subprocess.run(
        ["git", "show", "HEAD:src/test-hook.ts"],
        cwd=str(target),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "'hello'" not in show.stdout, (
        f"pre-commit hook did not normalise quotes — Biome lint-staged didn't "
        f"run. Hook is not armed. Committed content:\n{show.stdout}"
    )
    assert '"hello"' in show.stdout, (
        f"expected Biome to rewrite 'hello' → \"hello\". Committed content:\n{show.stdout}"
    )
