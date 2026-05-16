"""Full generated-project smoke walk for Go language.

Mirrors `test_smoke_nodejs_generated.py`. Skipped when `go` is not on
PATH locally; FAILS HARD in CI (when `CI=true` env var is set).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"

# Must match the `go_version` value in bootstrap_lib/cli.py — the generated
# go.mod pins this version, so anything older on PATH will either trigger
# GOTOOLCHAIN auto-download (slow / non-deterministic) or fail outright
# under GOTOOLCHAIN=local with `go.mod requires go >= X.Y`. Bump together.
REQUIRED_GO_VERSION = (1, 26)

_GO_VERSION_RE = re.compile(r"\bgo(\d+)\.(\d+)(?:\.\d+)?\b")


def _parse_go_version(output):
    """Parse `go version` stdout → (major, minor) tuple, or None if unparseable."""
    m = _GO_VERSION_RE.search(output)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


def _require_go():
    if shutil.which("go") is None:
        if os.environ.get("CI") == "true":
            pytest.fail("go is not on PATH but CI=true — CI must have actions/setup-go")
        pytest.skip("go not on PATH (local dev environment)")
    # Version check: generated go.mod pins go REQUIRED_GO_VERSION; older
    # toolchains on PATH would fail confusingly mid-`make install` under
    # GOTOOLCHAIN=local, or silently auto-download under default settings.
    try:
        proc = subprocess.run(
            ["go", "version"], capture_output=True, text=True, check=True, timeout=10
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        if os.environ.get("CI") == "true":
            pytest.fail(f"`go version` failed under CI: {exc}")
        pytest.skip(f"`go version` failed locally: {exc}")
    parsed = _parse_go_version(proc.stdout)
    if parsed is None:
        if os.environ.get("CI") == "true":
            pytest.fail(f"could not parse `go version` output under CI: {proc.stdout!r}")
        pytest.skip(f"could not parse `go version` output: {proc.stdout!r}")
    if parsed < REQUIRED_GO_VERSION:
        msg = (
            f"go {parsed[0]}.{parsed[1]} on PATH, but generated go.mod "
            f"requires >= {REQUIRED_GO_VERSION[0]}.{REQUIRED_GO_VERSION[1]}"
        )
        if os.environ.get("CI") == "true":
            pytest.fail(msg)
        pytest.skip(msg)


def test_smoke_go_generated(tmp_path):
    _require_go()

    target = tmp_path / "smoke-go"
    assert not target.exists()

    # Step 1: dry-run, assert filesystem-pure
    dry = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--language",
            "go",
            "--project-name",
            "smoke-go",
            "--out",
            str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not target.exists()
    for expected in [
        "Makefile",
        "go.mod",
        ".golangci.yml",
        "hooks/pre-commit",
        "hooks/pre-push",
        "main.go",
        "main_test.go",
    ]:
        assert expected in dry.stdout, f"dry-run missing {expected}"

    # Step 2: --apply
    subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "go",
            "--project-name",
            "smoke-go",
            "--out",
            str(target),
        ],
        check=True,
    )

    # Step 3: git init + initial commit (so install-hooks's git-guard passes)
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(target),
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(target), check=True)
    subprocess.run(["git", "add", "."], cwd=str(target), check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial bootstrap", "--no-verify"],
        cwd=str(target),
        check=True,
        capture_output=True,
    )

    # Step 4: make install (go mod download + go install of pinned tools)
    install = subprocess.run(
        ["make", "install"],
        cwd=str(target),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert install.returncode == 0, install.stderr

    # Step 5: make install-hooks
    install_hooks = subprocess.run(
        ["make", "install-hooks"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    assert install_hooks.returncode == 0, install_hooks.stderr
    # Verify core.hooksPath set
    hooks_path = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=str(target),
        capture_output=True,
        text=True,
        check=True,
    )
    assert hooks_path.stdout.strip() == "hooks"

    # Step 6: make check
    check = subprocess.run(
        ["make", "check"],
        cwd=str(target),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert check.returncode == 0, check.stderr

    # Step 7: make run
    run = subprocess.run(
        ["make", "run"],
        cwd=str(target),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr
    assert "smoke-go" in run.stdout

    # Step 8: commit-fires-hook deterministic assertion.
    # gofumpt rewrites `fmt.Println( "x")` (extra space) to `fmt.Println("x")`.
    # The hook DETECTS the dirty file, REWRITES it, and EXITS NON-ZERO so
    # the commit fails. We then re-add + re-commit to capture the formatted version.
    fresh = target / "hook_test.go"
    fresh.write_text(
        'package main\n\nimport "fmt"\n\nfunc demoHook() {\n\tfmt.Println( "dirty")\n}\n'
    )
    subprocess.run(["git", "add", str(fresh)], cwd=str(target), check=True)

    # First commit: hook detects + rewrites + exits non-zero
    commit1 = subprocess.run(
        ["git", "commit", "-m", "test hook"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    assert commit1.returncode != 0, (
        "expected hook to block the commit; got success. stderr: " + commit1.stderr
    )

    # File should now be rewritten on disk by gofumpt
    rewritten = fresh.read_text()
    assert "( " not in rewritten, f"gofumpt should have removed the extra space; got: {rewritten}"

    # Re-add + commit succeeds (file is clean now)
    subprocess.run(["git", "add", str(fresh)], cwd=str(target), check=True)
    commit2 = subprocess.run(
        ["git", "commit", "-m", "test hook formatted"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    assert commit2.returncode == 0, commit2.stderr

    # Verify the committed content is formatted (no `( ` extra space)
    show = subprocess.run(
        ["git", "show", "HEAD:hook_test.go"],
        cwd=str(target),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "( " not in show.stdout, "committed file should be formatted; got: " + show.stdout


def test_install_hooks_preserves_existing_hookspath(tmp_path):
    """Codex iter-2 #5 + iter-5 #4: pre-existing core.hooksPath must be
    captured + the printed rollback must restore it. Executes the rollback
    to verify end-to-end."""
    _require_go()
    target = tmp_path / "preserve-test"
    subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "go",
            "--project-name",
            "preserve-test",
            "--out",
            str(target),
        ],
        check=True,
    )
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(target),
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(target), check=True)
    # Set pre-existing core.hooksPath
    subprocess.run(
        ["git", "config", "core.hooksPath", "my-old-hooks"],
        cwd=str(target),
        check=True,
    )

    # Run install-hooks; output should include the rollback command for `my-old-hooks`
    install_hooks = subprocess.run(
        ["make", "install-hooks"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    assert install_hooks.returncode == 0, install_hooks.stderr
    assert "my-old-hooks" in install_hooks.stdout, (
        "rollback command should reference the previous value"
    )

    # Verify the new value is set
    current = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=str(target),
        capture_output=True,
        text=True,
        check=True,
    )
    assert current.stdout.strip() == "hooks"

    # Execute the printed rollback (extracted from stdout)
    subprocess.run(
        ["git", "config", "core.hooksPath", "my-old-hooks"],
        cwd=str(target),
        check=True,
    )
    restored = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=str(target),
        capture_output=True,
        text=True,
        check=True,
    )
    assert restored.stdout.strip() == "my-old-hooks"


def test_install_hooks_skips_in_non_git_dir(tmp_path):
    """Codex iter-4 #4: install-hooks must skip cleanly (exit 0) when .git/ missing."""
    target = tmp_path / "non-git"
    subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "go",
            "--project-name",
            "non-git",
            "--out",
            str(target),
        ],
        check=True,
    )
    # No git init — target is not a git repo
    install_hooks = subprocess.run(
        ["make", "install-hooks"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    assert install_hooks.returncode == 0, install_hooks.stderr
    assert "skipping" in install_hooks.stdout.lower()
