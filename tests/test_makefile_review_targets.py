"""Test the generated project's review-plan-by-codex / review-plan-by-claude
targets with shim CLIs.

Closes:
- Codex iter-1 finding #1 (review targets are alive in generated projects)
- Codex iter-7 finding #2 (Claude direction also tested)
- Codex iter-9 finding #1 (stale-PWD robustness via $(CURDIR))
- Codex iter-15 finding #2 (codex shim must materialise the output file)
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
            "fixture",
            "--out",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return target


def _shim_dir_with_codex_and_claude(tmp_path):
    """Build a directory of shim CLIs that succeed cleanly."""
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir()
    # codex shim: parses --output-last-message <path>; writes canned text there
    codex = shim_dir / "codex"
    codex.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import sys
            argv = sys.argv[1:]
            if "--version" in argv:
                print("codex-cli 0.130.0")
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
                    f.write("CANNED CODEX REVIEW OUTPUT\\n")
            print("ok")  # to satisfy preflight's smoke
            """
        )
    )
    codex.chmod(0o755)

    # claude shim: prints canned text to stdout (target uses shell redirect)
    claude = shim_dir / "claude"
    claude.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import sys
            argv = sys.argv[1:]
            if "--version" in argv:
                print("2.1.139 (Claude Code)")
                sys.exit(0)
            print("CANNED CLAUDE REVIEW OUTPUT")
            """
        )
    )
    claude.chmod(0o755)
    return shim_dir


def _make_plan_file(target, slug="_smoke_plan"):
    plan_dir = target / "docs" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / f"{slug}.md"
    plan_file.write_text("# smoke plan\nbody\n")
    return plan_file


def test_make_help_lists_review_targets(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    result = subprocess.run(["make", "help"], cwd=str(target), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for tgt in ["review-plan-by-codex", "review-plan-by-claude", "preflight-review-tooling"]:
        assert tgt in result.stdout, f"{tgt} missing from `make help`"


def test_review_plan_by_codex_materialises_output_file(tmp_path):
    """Codex iter-15 finding #2."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target)
    shim_dir = _shim_dir_with_codex_and_claude(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out_file = tmp_path / "out-codex.md"
    env["PLAN_REVIEW_OUT_CODEX"] = str(out_file)

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1",
            f"PLAN_REVIEW_OUT_CODEX={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_file.exists()
    assert "CANNED CODEX REVIEW OUTPUT" in out_file.read_text()


def test_review_plan_by_claude_materialises_output_file(tmp_path):
    """Codex iter-7 finding #2."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target)
    shim_dir = _shim_dir_with_codex_and_claude(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out_file = tmp_path / "out-claude.md"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-claude",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1",
            f"PLAN_REVIEW_OUT_CLAUDE={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_file.exists()
    assert "CANNED CLAUDE REVIEW OUTPUT" in out_file.read_text()


def test_stale_pwd_does_not_corrupt_curdir(tmp_path):
    """Codex iter-9 finding #1: invoke from a different cwd with a
    deliberately stale PWD env var; review target must still resolve to the
    fixture path."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target)
    shim_dir = _shim_dir_with_codex_and_claude(tmp_path)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    env["PWD"] = str(elsewhere)  # stale!

    out_file = tmp_path / "out.md"
    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1",
            f"PLAN_REVIEW_OUT_CODEX={out_file}",
        ],
        env=env,
        cwd=str(elsewhere),  # different cwd than the project
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # If $(CURDIR) was actually $(PWD), the shim would have been invoked
    # against `elsewhere` and never produced the output file. Materialisation
    # of out_file proves $(CURDIR) resolved correctly.
    assert out_file.exists()
