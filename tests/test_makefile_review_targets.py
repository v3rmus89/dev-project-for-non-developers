"""Test the generated project's review-plan-by-codex / review-plan-by-claude
targets with shim CLIs.

Closes:
- Codex iter-1 finding #1 (review targets are alive in generated projects)
- Codex iter-7 finding #2 (Claude direction also tested)
- Codex iter-9 finding #1 (stale-PWD robustness via $(CURDIR))
- Codex iter-15 finding #2 (codex shim must materialise the output file)
"""

from __future__ import annotations

import json
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


# ── PR #4: Tier-1 + consistency target tests ─────────────────────────────


def _hermetic_git_setup(target):
    """Init git in target and create a single fixture commit."""
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", "add", "."],
        cwd=str(target),
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=test",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=str(target),
        check=True,
    )


def _shim_dir_capturing_argv(tmp_path, codex_exit=0, claude_exit=0):
    """Shim CLIs that capture argv to a file + exit with controlled status."""
    shim_dir = tmp_path / "shims-argv"
    shim_dir.mkdir()
    argv_log = tmp_path / "argv-log.json"

    codex = shim_dir / "codex"
    codex.write_text(
        textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import json, sys
        argv = sys.argv[1:]
        if "--version" in argv:
            print("codex-cli 0.130.0")
            sys.exit(0)
        # Find --output-last-message and write canned content
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
                f.write("CANNED CODEX OUTPUT\\n")
        # Append argv to log file (multiple invocations possible)
        try:
            with open({str(argv_log)!r}) as f:
                existing = json.load(f)
        except FileNotFoundError:
            existing = []
        existing.append({{"cli": "codex", "argv": argv}})
        with open({str(argv_log)!r}, "w") as f:
            json.dump(existing, f)
        sys.exit({codex_exit})
        """)
    )
    codex.chmod(0o755)

    claude = shim_dir / "claude"
    claude.write_text(
        textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import json, sys
        argv = sys.argv[1:]
        if "--version" in argv:
            print("2.1.139 (Claude Code)")
            sys.exit(0)
        print("CANNED CLAUDE OUTPUT")
        try:
            with open({str(argv_log)!r}) as f:
                existing = json.load(f)
        except FileNotFoundError:
            existing = []
        existing.append({{"cli": "claude", "argv": argv}})
        with open({str(argv_log)!r}, "w") as f:
            json.dump(existing, f)
        sys.exit({claude_exit})
        """)
    )
    claude.chmod(0o755)
    return shim_dir, argv_log


def test_review_commit_by_codex_materialises_sha_keyed_output(tmp_path):
    """PR #4 Bucket E #1: SHA-keyed output path; matches `git rev-parse --short HEAD`
    from the test fixture (not a fixed 7-char assumption)."""
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    shim_dir, _ = _shim_dir_capturing_argv(tmp_path)

    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(target),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out_file = tmp_path / f"out-commit-{sha}.md"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-commit-by-codex",
            f"REVIEW_COMMIT_OUT_CODEX={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    assert out_file.exists()
    assert "CANNED CODEX OUTPUT" in out_file.read_text()


def test_review_commit_by_claude_materialises_sha_keyed_output(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    shim_dir, _ = _shim_dir_capturing_argv(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out_file = tmp_path / "out-commit-claude.md"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-commit-by-claude",
            f"REVIEW_COMMIT_OUT_CLAUDE={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    assert out_file.exists()
    assert "CANNED CLAUDE OUTPUT" in out_file.read_text()


def test_review_commit_argv_contains_literal_git_commands_not_output(tmp_path):
    """PR #4 iter-3 #1 regression test: the prompt passed to codex must
    contain literal 'git show HEAD' / 'git log -1 --stat HEAD' strings, NOT
    the output of executing those commands. Locks down the backtick /
    `$()` shell-substitution class."""
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-commit-by-codex",
            f"REVIEW_COMMIT_OUT_CODEX={tmp_path}/log-test.md",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    log_data = json.loads(argv_log.read_text())
    # The codex argv list should contain a prompt arg with literal command strings
    codex_argv = [entry["argv"] for entry in log_data if entry["cli"] == "codex"]
    assert codex_argv, "codex shim was never invoked"
    prompt = " ".join(codex_argv[-1])  # join argv for substring check
    # Literal strings (single-quoted in prompt, not backticks)
    assert "'git show HEAD'" in prompt, (
        "literal 'git show HEAD' missing — possible shell-substitution regression"
    )
    assert "'git log -1 --stat HEAD'" in prompt, "literal 'git log -1 --stat HEAD' missing"


def test_review_commit_by_codex_skips_in_non_git_dir(tmp_path):
    """PR #4 iter-4 #1: non-git dir must exit 0 WITHOUT invoking the CLI."""
    target = _bootstrap_fixture(tmp_path)
    # NO git init
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    result = subprocess.run(
        ["make", "-C", str(target), "review-commit-by-codex"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "skipping: not a git repo" in result.stdout
    # argv log file should not exist (CLI never invoked)
    assert not argv_log.exists(), "shim was invoked despite skip"


def test_review_commit_by_codex_skips_in_no_commit_repo(tmp_path):
    """PR #4 iter-4 #1: git repo with no commits must exit 0 WITHOUT invoking
    the CLI (would otherwise call `git show HEAD` and fail confusingly)."""
    target = _bootstrap_fixture(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    # NO commit
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    result = subprocess.run(
        ["make", "-C", str(target), "review-commit-by-codex"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "no commits yet" in result.stdout
    assert not argv_log.exists(), "shim was invoked despite no-commits skip"


def test_review_commit_by_codex_propagates_cli_failure(tmp_path):
    """PR #4 iter-5 #1: `; cat` regression test. CLI shim exits 42; the make
    target must also exit nonzero (NOT swallowed by `cat` succeeding on
    pre-existing output file)."""
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    shim_dir, _ = _shim_dir_capturing_argv(tmp_path, codex_exit=42)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    # Pre-create a stale output file (would mask failure if `; cat` was used)
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(target),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    stale = tmp_path / f"stale-{sha}.md"
    stale.write_text("STALE PRE-EXISTING OUTPUT")

    result = subprocess.run(
        ["make", "-C", str(target), "review-commit-by-codex", f"REVIEW_COMMIT_OUT_CODEX={stale}"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "make target swallowed CLI failure — `;` vs `&&` regression. "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )


def test_review_plan_consistency_by_claude_writes_iter_keyed_output(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="consistency_smoke")
    shim_dir, _ = _shim_dir_capturing_argv(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out_file = tmp_path / "consistency-iter-2.md"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-consistency-by-claude",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=2",
            f"PLAN_CONSISTENCY_OUT={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_file.exists()
    assert "CANNED CLAUDE OUTPUT" in out_file.read_text()
