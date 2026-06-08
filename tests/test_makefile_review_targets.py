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

import pytest

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
    # the `make review` dispatcher (PR-2, iter-3 FN5) is listed as its OWN target
    # (first token == "review"), distinct from the review-plan-by-* substrings.
    help_targets = [line.strip().split()[0] for line in result.stdout.splitlines() if line.strip()]
    assert "review" in help_targets, f"`review` dispatcher missing from `make help`: {help_targets}"


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


def test_review_commit_by_claude_propagates_cli_failure(tmp_path):
    """PR #4 Tier-1 review #3: failure-preservation must hold for claude target too."""
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    shim_dir, _ = _shim_dir_capturing_argv(tmp_path, claude_exit=42)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(target),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    stale = tmp_path / f"stale-claude-{sha}.md"
    stale.write_text("STALE PRE-EXISTING OUTPUT")

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-commit-by-claude",
            f"REVIEW_COMMIT_OUT_CLAUDE={stale}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "review-commit-by-claude swallowed CLI failure — `;` vs `&&` regression"
    )


def test_review_plan_consistency_by_claude_propagates_cli_failure(tmp_path):
    """PR #4 Tier-1 review #3: failure-preservation must hold for consistency target too."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="consistency_fail")
    shim_dir, _ = _shim_dir_capturing_argv(tmp_path, claude_exit=42)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    stale = tmp_path / "stale-consistency.md"
    stale.write_text("STALE PRE-EXISTING OUTPUT")

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-consistency-by-claude",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1",
            f"PLAN_CONSISTENCY_OUT={stale}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "review-plan-consistency-by-claude swallowed CLI failure — `;` vs `&&` regression"
    )


def test_review_commit_warns_on_dirty_worktree(tmp_path):
    """PR #4 Tier-1 review #4: dirty-worktree WARN must fire AND CLI must still invoke."""
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    # Make the worktree dirty (unstaged change to an existing tracked file)
    mkf = target / "Makefile"
    mkf.write_text(mkf.read_text() + "\n# dirty-marker\n")

    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out_file = tmp_path / "out-dirty.md"

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
    assert result.returncode == 0, result.stderr
    assert "WARN: worktree has uncommitted changes" in result.stderr, (
        "dirty-worktree WARN missing from stderr"
    )
    # The CLI must still have been invoked (not blocked)
    assert argv_log.exists(), "shim was not invoked despite WARN-not-block contract"


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


# ── PR #5b: PLAN_FILE runtime passthrough tests ─────────────────────────────


def test_review_commit_by_codex_with_plan_file_includes_plan_in_prompt(tmp_path):
    """PR #5b: when PLAN_FILE=docs/plans/x.md is passed at Make runtime, the
    rendered prompt must contain the plan path. Locks down the Make→prompt
    passthrough (closes the deferred iter-5 P2 + iter-6 #2)."""
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    # Plan file must exist — the Tier-1 recipe guards on `test -f`
    plan = target / "docs" / "plans" / "UNIQUE_PLAN_PATH.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("# plan body\n")
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-commit-by-codex",
            "PLAN_FILE=docs/plans/UNIQUE_PLAN_PATH.md",
            f"REVIEW_COMMIT_OUT_CODEX={tmp_path}/out.md",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    log = json.loads(argv_log.read_text())
    codex_argv = [e["argv"] for e in log if e["cli"] == "codex" if e["argv"] != ["--version"]]
    # find the actual exec invocation (excludes version check)
    exec_argv = [a for a in codex_argv if "exec" in a]
    assert exec_argv, "codex exec never invoked"
    prompt = " ".join(exec_argv[-1])
    assert "UNIQUE_PLAN_PATH.md" in prompt, (
        "PLAN_FILE runtime value must appear in rendered prompt;"
        " Make-level $(PLAN_FILE) passthrough broken"
    )
    assert "Check this commit against" in prompt, (
        "with-plan-binding prompt phrase must fire when PLAN_FILE set"
    )
    assert "No plan binding" not in prompt, (
        "unbound prompt phrase must NOT appear when PLAN_FILE set"
    )


def test_review_commit_by_codex_without_plan_file_uses_unbound_prompt(tmp_path):
    """PR #5b: without PLAN_FILE, the unbound prompt fires (`No plan binding`)."""
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
            f"REVIEW_COMMIT_OUT_CODEX={tmp_path}/out.md",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    log = json.loads(argv_log.read_text())
    codex_argv = [e["argv"] for e in log if e["cli"] == "codex"]
    exec_argv = [a for a in codex_argv if "exec" in a]
    prompt = " ".join(exec_argv[-1])
    assert "No plan binding" in prompt, "unbound prompt phrase must fire when PLAN_FILE empty"
    assert "Check this commit against" not in prompt, (
        "with-plan-binding phrase must NOT fire when PLAN_FILE empty"
    )


def test_review_commit_by_claude_plan_file_passthrough(tmp_path):
    """PR #5b: same PLAN_FILE binding contract for the claude target."""
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    plan = target / "docs" / "plans" / "CLAUDE_TEST_PLAN.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("# plan\n")
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    # With PLAN_FILE
    subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-commit-by-claude",
            "PLAN_FILE=docs/plans/CLAUDE_TEST_PLAN.md",
            f"REVIEW_COMMIT_OUT_CLAUDE={tmp_path}/out-with.md",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    log = json.loads(argv_log.read_text())
    claude_argv = [e["argv"] for e in log if e["cli"] == "claude" and e["argv"] != ["--version"]]
    assert claude_argv, "claude was never invoked"
    prompt = " ".join(claude_argv[-1])
    assert "CLAUDE_TEST_PLAN.md" in prompt
    assert "Check this commit against" in prompt
    assert "No plan binding" not in prompt


def test_review_commit_rejects_missing_plan_file(tmp_path):
    """Closes Tier-2 P1 (Codex on PR #11): if PLAN_FILE is set but the file
    doesn't exist, the target must fail before invoking the CLI — otherwise
    Tier-1 reviewers get told to check drift against a nonexistent plan."""
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    for which_target in ["review-commit-by-codex", "review-commit-by-claude"]:
        result = subprocess.run(
            [
                "make",
                "-C",
                str(target),
                which_target,
                "PLAN_FILE=docs/plans/THIS_DOES_NOT_EXIST.md",
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"{which_target} with missing PLAN_FILE must fail; got success"
        )
        assert "PLAN_FILE not found" in result.stdout, (
            f"{which_target} must print 'PLAN_FILE not found' on bad path"
        )
    # And the shim must never have been invoked for either target
    assert not argv_log.exists(), (
        "shim was invoked despite PLAN_FILE existence check failure — guard ineffective"
    )


def test_review_commit_by_claude_without_plan_file_uses_unbound_prompt(tmp_path):
    """Closes Tier-1 F1: claude target's without-plan branch needs argv-level
    coverage too (codex was tested; claude was not — asymmetric)."""
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
            "review-commit-by-claude",
            f"REVIEW_COMMIT_OUT_CLAUDE={tmp_path}/out.md",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    log = json.loads(argv_log.read_text())
    claude_argv = [e["argv"] for e in log if e["cli"] == "claude" and e["argv"] != ["--version"]]
    assert claude_argv, "claude was never invoked"
    prompt = " ".join(claude_argv[-1])
    assert "No plan binding" in prompt, (
        "unbound prompt phrase must fire when PLAN_FILE empty for claude target"
    )
    assert "Check this commit against" not in prompt, (
        "with-plan-binding phrase must NOT fire when PLAN_FILE empty"
    )


def test_tier1_prompt_has_no_backticks_in_rendered_recipe(tmp_path):
    """PR #5 Tier-2 regression test: the rendered Tier-1 prompt (both branches)
    must not contain backticks or `$(` — they'd trigger shell command
    substitution when passed as a double-quoted shell arg."""
    target = _bootstrap_fixture(tmp_path)
    makefile_text = (target / "Makefile").read_text()
    # Locate review-commit-by-codex recipe block
    rec_start = makefile_text.index("review-commit-by-codex:")
    rec_end = makefile_text.index("preflight-review-tooling:")
    rec_block = makefile_text[rec_start:rec_end]
    # Extract everything inside the quoted prompts (after "Review commit ...)
    p_starts = []
    cursor = 0
    while True:
        try:
            idx = rec_block.index('"Review commit', cursor)
            p_starts.append(idx)
            cursor = idx + 10
        except ValueError:
            break
    # Both codex + claude targets have 2 prompts each (with-plan + unbound) = 4 total
    assert len(p_starts) == 4, (
        f"expected exactly 4 quoted prompts in recipe block (2 targets x 2 branches); "
        f"got {len(p_starts)}"
    )
    for ps in p_starts:
        line_end = rec_block.index("\n", ps)
        prompt = rec_block[ps + 1 : line_end].rstrip('"').rstrip(" \\").rstrip('"')
        # Exception: the WITH-plan branch DOES contain $(PLAN_FILE) — that's
        # intentional, Make expands it at runtime. But it should NOT contain
        # any OTHER $( or backticks.
        # Strip the literal $(PLAN_FILE) first to check the rest is clean.
        check = prompt.replace("$(PLAN_FILE)", "<PLAN>")
        assert "`" not in check, f"Tier-1 prompt contains backtick: {check[:200]}"
        assert "$(" not in check, f"Tier-1 prompt contains shell-substitution `$(`: {check[:200]}"


def test_plan_review_prompt_has_calibration_and_is_shell_safe(tmp_path):
    """C1 regression: the plan-review prompts (codex + claude) must (a) carry the
    imp-3 calibration sentence, and (b) be shell-safe — no backticks, no `$(`
    beyond the legit make vars, and no literal double-quote — since each is passed
    as a double-quoted shell arg.
    Extends the Tier-1-only no-backtick guard above to the plan-review prompts;
    that coverage gap is what let the calibration's own backticks slip into the
    plan at iter-1 (FN1)."""
    target = _bootstrap_fixture(tmp_path)
    makefile_text = (target / "Makefile").read_text()
    needle = '"Review the plan file at'
    starts = [i for i in range(len(makefile_text)) if makefile_text.startswith(needle, i)]
    assert len(starts) == 2, (
        f"expected exactly 2 plan-review prompts (codex + claude); got {len(starts)}"
    )
    for s in starts:
        line_end = makefile_text.index("\n", s)
        prompt = makefile_text[s + 1 : line_end]
        assert "Calibrate importance strictly" in prompt, (
            "plan-review prompt is missing the imp-3 calibration sentence"
        )
        # The prompt is one double-quoted shell arg, so the ONLY double-quote on the
        # line is the closing delimiter; an inner one would terminate the arg early.
        # (Codex ends the prompt with `"; \`, Claude with `" \` — both have exactly
        # one `"`.) This is the third shell-safety guarantee from the plan's Tests C1.
        assert prompt.count('"') == 1, (
            f"plan-review prompt contains a literal double-quote: {prompt[:200]}"
        )
        # Make expands $(PLAN_FILE)/$(ITERATION)/$(KEY) before the shell sees them;
        # anything else with $( or a backtick would be shell command substitution.
        check = (
            prompt.replace("$(PLAN_FILE)", "<P>")
            .replace("$(ITERATION)", "<I>")
            .replace("$(KEY)", "<K>")
        )
        assert "`" not in check, f"plan-review prompt contains a backtick: {check[:200]}"
        assert "$(" not in check, (
            f"plan-review prompt contains shell-substitution `$(`: {check[:200]}"
        )


def test_step9_mandate_appears_in_contributing(tmp_path):
    """PR #5b Bucket B: CONTRIBUTING.md step 9 must explicitly mandate
    appending the Tier-1-suggested impl-log row + docs-only commit pattern.
    Test BOTH the rendered fixture AND the skill-repo dogfood (closes Tier-1
    F5 — dogfood file is hand-maintained against the template; drift could
    silently land if only the template is tested)."""
    target = _bootstrap_fixture(tmp_path)
    rendered = (target / "CONTRIBUTING.md").read_text()
    dogfood = (SKILL_ROOT / "CONTRIBUTING.md").read_text()
    # Search by content (not step number) so renumbering in dogfood doesn't
    # break the test
    for surface_name, contributing in [("rendered", rendered), ("dogfood", dogfood)]:
        assert "MANDATED" in contributing, (
            f"{surface_name} CONTRIBUTING.md must contain MANDATED keyword for impl-log append"
        )
        assert "append" in contributing.lower() and "implementation log" in contributing.lower(), (
            f"{surface_name} CONTRIBUTING.md must reference appending to Implementation log"
        )
        assert "docs-only commit" in contributing.lower(), (
            f"{surface_name} CONTRIBUTING.md must specify the separate-docs-only-commit pattern"
        )
        assert "PLAN_FILE" in contributing, (
            f"{surface_name} CONTRIBUTING.md must show PLAN_FILE= invocation"
        )


def test_plan_file_structural_convention_documented(tmp_path):
    """PR #5b Bucket B: the new plan-file structural convention (sections 1-9
    order) must appear in shared/docs-plans-README.md.tmpl + dogfood mirror."""
    target = _bootstrap_fixture(tmp_path)
    readme = (target / "docs" / "plans" / "README.md").read_text()
    assert "## Plan-file structural convention" in readme, (
        "docs/plans/README.md must document the section convention"
    )
    # Must reference both the new sections by canonical name
    assert "Implementation log" in readme
    assert "Lessons surfaced" in readme
    assert "Iteration log" in readme
    # Must mention `make status` extraction reliance
    assert "make status" in readme.lower()


# ── PR-0: review-plan-fact-check targets ─────────────────────────────


def test_make_help_lists_fact_check_targets(tmp_path):
    """review-plan-fact-check-by-{codex,claude} must appear in `make help`."""
    target = _bootstrap_fixture(tmp_path)
    result = subprocess.run(["make", "help"], cwd=str(target), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for tgt in ["review-plan-fact-check-by-codex", "review-plan-fact-check-by-claude"]:
        assert tgt in result.stdout, f"{tgt} missing from `make help`"


def test_review_plan_fact_check_by_codex_materialises_output(tmp_path):
    """review-plan-fact-check-by-codex must materialise the output file."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="fact_check_smoke")
    shim_dir = _shim_dir_with_codex_and_claude(tmp_path)
    out_file = tmp_path / "fact-check-codex.md"

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-fact-check-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            f"PLAN_FACT_CHECK_OUT_CODEX={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    assert out_file.exists(), "output file not materialised"
    assert "CANNED CODEX REVIEW OUTPUT" in out_file.read_text()


def test_review_plan_fact_check_by_claude_materialises_output(tmp_path):
    """review-plan-fact-check-by-claude must materialise the output file."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="fact_check_smoke_claude")
    shim_dir = _shim_dir_with_codex_and_claude(tmp_path)
    out_file = tmp_path / "fact-check-claude.md"

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-fact-check-by-claude",
            f"PLAN_FILE={plan.relative_to(target)}",
            f"PLAN_FACT_CHECK_OUT_CLAUDE={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    assert out_file.exists(), "output file not materialised"
    assert "CANNED CLAUDE REVIEW OUTPUT" in out_file.read_text()


def test_review_plan_fact_check_fails_without_plan_file(tmp_path):
    """review-plan-fact-check-by-{codex,claude} must fail if PLAN_FILE is unset."""
    target = _bootstrap_fixture(tmp_path)
    shim_dir = _shim_dir_with_codex_and_claude(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    for tgt in ["review-plan-fact-check-by-codex", "review-plan-fact-check-by-claude"]:
        result = subprocess.run(
            ["make", "-C", str(target), tgt],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, f"{tgt} must fail when PLAN_FILE is unset"
        assert "Usage:" in result.stdout, f"{tgt} must print Usage: when PLAN_FILE unset"


def test_review_plan_fact_check_by_codex_propagates_cli_failure(tmp_path):
    """CLI failure must not be swallowed by the fact-check target."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="fact_check_fail")
    shim_dir, _ = _shim_dir_capturing_argv(tmp_path, codex_exit=42)
    out_file = tmp_path / "fact-check-fail.md"
    out_file.write_text("STALE")
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-fact-check-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            f"PLAN_FACT_CHECK_OUT_CODEX={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "review-plan-fact-check-by-codex must propagate CLI failure"


# ── PR-1 Bucket F: THREAD_MODE continue-thread matrix ────────────────────────
# Six cases (plan Scope G): (1) fresh, (2) first-continue seed [+ extraction
# failure + KEEP_THREAD_JSONL sub-cases], (3) resume, (4a) stale-session
# fallback on the pinned string, (4b) unrelated-failure preserves state,
# (5) loop-reset. Driven by a controllable codex shim (env-configured).

# thread.started.thread_id the seed shim emits — a valid 8-4-4-4-12 UUID.
_SEED_SESSION_ID = "00000000-0000-7000-8000-000000000abc"

# A controllable codex shim. Behaviour is entirely env-driven so one static
# script covers every case; uses print() throughout to avoid newline escaping.
_THREAD_CODEX_SHIM = '''#!/usr/bin/env python3
"""Controllable codex shim for THREAD_MODE tests (env-driven).

SHIM_ARGV_LOG          JSON file; each call appends its argv list
SHIM_RESUME_BEHAVIOR   success | fail-pinned | fail-other  (resume calls)
SHIM_EMIT_THREAD_STARTED 1 | 0  (seed --json calls: emit a thread.started line)
"""
import json
import os
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

logf = os.environ.get("SHIM_ARGV_LOG")
if logf:
    try:
        with open(logf) as fh:
            existing = json.load(fh)
    except FileNotFoundError:
        existing = []
    existing.append(argv)
    with open(logf, "w") as fh:
        json.dump(existing, fh)

if "resume" in argv:
    mode = os.environ.get("SHIM_RESUME_BEHAVIOR", "success")
    if mode == "fail-pinned":
        print(
            "Error: thread/resume: thread/resume failed: no rollout found for "
            "thread id deadbeef (code -32600)",
            file=sys.stderr,
        )
        sys.exit(1)
    if mode == "fail-other":
        # Write the output file even on this failure so that a hypothetical
        # "swallow the error" regression would let the recipe's trailing `cat`
        # SUCCEED (exit 0). That isolates the exit-code-propagation signal: the
        # only way `make` exits non-zero is the recipe's own `exit $$rc`, not an
        # incidental missing-output `cat` failure (Tier-1 imp-2 fix).
        if out:
            with open(out, "w") as fh:
                print("CANNED RESUME REVIEW (unrelated failure)", file=fh)
        print("Error: unrelated network/quota failure", file=sys.stderr)
        sys.exit(7)
    if out:
        with open(out, "w") as fh:
            print("CANNED RESUME REVIEW", file=fh)
    print("resumed ok")
    sys.exit(0)

if "--json" in argv:
    if out:
        with open(out, "w") as fh:
            print("CANNED SEED REVIEW", file=fh)
    if os.environ.get("SHIM_EMIT_THREAD_STARTED", "1") == "1":
        print('{"type":"thread.started","thread_id":"00000000-0000-7000-8000-000000000abc"}')
    else:
        print('{"type":"turn.started"}')
    sys.exit(0)

if out:
    with open(out, "w") as fh:
        print("CANNED FRESH REVIEW", file=fh)
print("fresh ok")
sys.exit(0)
'''


def _thread_shim_dir(tmp_path):
    shim_dir = tmp_path / "thread-shims"
    shim_dir.mkdir()
    codex = shim_dir / "codex"
    codex.write_text(_THREAD_CODEX_SHIM)
    codex.chmod(0o755)
    return shim_dir


def _run_review_codex(
    target,
    plan,
    shim_dir,
    *,
    thread_mode,
    argv_log,
    out_file,
    thread_file,
    jsonl_file,
    extra_env=None,
):
    """Run `make review-plan-by-codex` against the fixture with the thread shim,
    overriding THREAD_FILE / THREAD_JSONL_FILE / output to tmp paths so the
    test never collides with the KEY-derived /tmp defaults."""
    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    env["SHIM_ARGV_LOG"] = str(argv_log)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1",
            f"THREAD_MODE={thread_mode}",
            f"PLAN_REVIEW_OUT_CODEX={out_file}",
            f"THREAD_FILE={thread_file}",
            f"THREAD_JSONL_FILE={jsonl_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )


def _exec_calls(argv_log):
    """All codex argv lists that include 'exec' (skips bare --version probes)."""
    data = json.loads(argv_log.read_text())
    return [a for a in data if "exec" in a]


def test_thread_mode_fresh_uses_no_json_and_writes_no_thread_file(tmp_path):
    """Case 1: THREAD_MODE=fresh (default) — plain codex exec, no --json, no
    session tracking. The thread machinery must stay completely dormant."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="thread_fresh")
    shim_dir = _thread_shim_dir(tmp_path)
    argv_log = tmp_path / "argv.json"
    tf, tj, out = tmp_path / "x.thread", tmp_path / "x.jsonl", tmp_path / "out.md"

    r = _run_review_codex(
        target,
        plan,
        shim_dir,
        thread_mode="fresh",
        argv_log=argv_log,
        out_file=out,
        thread_file=tf,
        jsonl_file=tj,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    calls = _exec_calls(argv_log)
    assert calls, "codex exec never invoked"
    assert "--json" not in calls[-1], "fresh path must not pass --json"
    assert "resume" not in calls[-1], "fresh path must not resume"
    assert not tf.exists(), "fresh path must not write THREAD_FILE"
    assert not tj.exists()


def test_thread_mode_continue_seeds_thread_file_and_deletes_jsonl(tmp_path):
    """Case 2: continue + no THREAD_FILE — seeds via codex exec --json, extracts
    the session id into THREAD_FILE, and deletes THREAD_JSONL_FILE on success."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="thread_seed")
    shim_dir = _thread_shim_dir(tmp_path)
    argv_log = tmp_path / "argv.json"
    tf, tj, out = tmp_path / "x.thread", tmp_path / "x.jsonl", tmp_path / "out.md"

    r = _run_review_codex(
        target,
        plan,
        shim_dir,
        thread_mode="continue",
        argv_log=argv_log,
        out_file=out,
        thread_file=tf,
        jsonl_file=tj,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    calls = _exec_calls(argv_log)
    assert "--json" in calls[-1], "seed path must pass --json"
    assert tf.exists(), "seed must write THREAD_FILE"
    assert tf.read_text().strip() == _SEED_SESSION_ID
    assert not tj.exists(), "THREAD_JSONL_FILE must be deleted after extraction"


def test_thread_mode_continue_extraction_failure_cleans_all_artifacts(tmp_path):
    """Case 2 (extractor-failure sub-case): seed JSONL has no thread.started →
    extraction fails → recipe exits non-zero and removes THREAD_FILE,
    THREAD_FILE.tmp, AND THREAD_JSONL_FILE (no corrupt state left behind)."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="thread_seedfail")
    shim_dir = _thread_shim_dir(tmp_path)
    argv_log = tmp_path / "argv.json"
    tf, tj, out = tmp_path / "x.thread", tmp_path / "x.jsonl", tmp_path / "out.md"

    r = _run_review_codex(
        target,
        plan,
        shim_dir,
        thread_mode="continue",
        argv_log=argv_log,
        out_file=out,
        thread_file=tf,
        jsonl_file=tj,
        extra_env={"SHIM_EMIT_THREAD_STARTED": "0"},
    )
    assert r.returncode != 0, "extraction failure must propagate non-zero"
    assert not tf.exists(), "THREAD_FILE must not exist after extraction failure"
    assert not Path(str(tf) + ".tmp").exists(), "THREAD_FILE.tmp must be cleaned"
    assert not tj.exists(), "THREAD_JSONL_FILE must be cleaned on failure"


def test_thread_mode_continue_keep_jsonl_retains_it_on_success(tmp_path):
    """Case 2 (KEEP sub-case): KEEP_THREAD_JSONL=1 retains the JSONL on a
    successful seed (debug opt-out)."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="thread_keep")
    shim_dir = _thread_shim_dir(tmp_path)
    argv_log = tmp_path / "argv.json"
    tf, tj, out = tmp_path / "x.thread", tmp_path / "x.jsonl", tmp_path / "out.md"

    r = _run_review_codex(
        target,
        plan,
        shim_dir,
        thread_mode="continue",
        argv_log=argv_log,
        out_file=out,
        thread_file=tf,
        jsonl_file=tj,
        extra_env={"KEEP_THREAD_JSONL": "1"},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert tf.read_text().strip() == _SEED_SESSION_ID
    assert tj.exists(), "KEEP_THREAD_JSONL=1 must retain THREAD_JSONL_FILE"


def test_thread_mode_continue_resume_uses_resume_subcommand(tmp_path):
    """Case 3: continue + existing THREAD_FILE — runs codex exec resume
    $SESSION_ID, NOT a fresh exec. The resume argv MUST carry `-c
    sandbox_mode=read-only` (SAFETY/F3 — resume defaults to workspace-write and
    does NOT inherit the seed's sandbox; live gate 2026-05-30) and MUST NOT carry
    --json or -C/--sandbox/--color (the resume subcommand rejects those —
    LESSONS.md 2026-05-27 / 2026-05-30 / PR #10 iter-4)."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="thread_resume")
    shim_dir = _thread_shim_dir(tmp_path)
    argv_log = tmp_path / "argv.json"
    tf, tj, out = tmp_path / "x.thread", tmp_path / "x.jsonl", tmp_path / "out.md"
    tf.write_text("11111111-2222-7333-8444-555555555555")

    r = _run_review_codex(
        target,
        plan,
        shim_dir,
        thread_mode="continue",
        argv_log=argv_log,
        out_file=out,
        thread_file=tf,
        jsonl_file=tj,
        extra_env={"SHIM_RESUME_BEHAVIOR": "success"},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    resume_calls = [a for a in _exec_calls(argv_log) if "resume" in a]
    assert resume_calls, "resume subcommand never invoked"
    ra = resume_calls[-1]
    assert "11111111-2222-7333-8444-555555555555" in ra, "resume must pass the session id"
    assert "--json" not in ra, "resume must not pass --json"
    # SAFETY (F3): resume does NOT inherit the seed's sandbox — it defaults to
    # workspace-write — so the recipe MUST force read-only via the general config
    # override `-c sandbox_mode=read-only`. Assert it's present AND that `-c` is
    # immediately followed by the value (so a split/reordered pair can't slip by).
    assert "-c" in ra and "sandbox_mode=read-only" in ra, (
        "resume MUST pass `-c sandbox_mode=read-only` — without it a resumed review "
        "runs workspace-write and could write the repo (F3, live gate 2026-05-30)"
    )
    assert ra[ra.index("-c") + 1] == "sandbox_mode=read-only", (
        "`-c` must be immediately followed by `sandbox_mode=read-only`"
    )
    for rejected in ("-C", "--sandbox", "--color"):
        assert rejected not in ra, (
            f"resume must NOT pass {rejected} — codex exec resume rejects it "
            "(unexpected argument). The seed's sandbox is NOT inherited; read-only "
            "is forced via `-c sandbox_mode=read-only` instead."
        )
    assert tf.read_text().strip() == "11111111-2222-7333-8444-555555555555", (
        "THREAD_FILE must be unchanged on a successful resume"
    )


def test_thread_mode_continue_stale_session_falls_back_to_fresh(tmp_path):
    """Case 4a: resume fails with the pinned 'no rollout found for thread id'
    string → clear THREAD_FILE + THREAD_JSONL_FILE and run a one-shot fresh
    codex exec (no --json). Both files stay absent (self-heals next call)."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="thread_stale")
    shim_dir = _thread_shim_dir(tmp_path)
    argv_log = tmp_path / "argv.json"
    tf, tj, out = tmp_path / "x.thread", tmp_path / "x.jsonl", tmp_path / "out.md"
    tf.write_text("11111111-2222-7333-8444-555555555555")
    tj.write_text("stale jsonl")

    r = _run_review_codex(
        target,
        plan,
        shim_dir,
        thread_mode="continue",
        argv_log=argv_log,
        out_file=out,
        thread_file=tf,
        jsonl_file=tj,
        extra_env={"SHIM_RESUME_BEHAVIOR": "fail-pinned"},
    )
    assert r.returncode == 0, "fallback fresh exec should succeed → exit 0\n" + r.stderr + r.stdout
    assert not tf.exists(), "stale THREAD_FILE must be cleared"
    assert not tj.exists(), "stale THREAD_JSONL_FILE must be cleared"
    calls = _exec_calls(argv_log)
    assert any("resume" in a for a in calls), "resume must have been attempted"
    fallback = [a for a in calls if "resume" not in a]
    assert fallback, "a fresh codex exec must run as the fallback"
    assert "--json" not in fallback[-1], "fallback fresh exec must not pass --json"


def test_thread_mode_continue_unrelated_failure_preserves_state(tmp_path):
    """Case 4b: resume fails with an UNRELATED error (not the pinned string) →
    the recipe exits non-zero and does NOT clear thread state (no swallowing of
    auth/network/quota errors)."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="thread_other")
    shim_dir = _thread_shim_dir(tmp_path)
    argv_log = tmp_path / "argv.json"
    tf, tj, out = tmp_path / "x.thread", tmp_path / "x.jsonl", tmp_path / "out.md"
    tf.write_text("11111111-2222-7333-8444-555555555555")

    r = _run_review_codex(
        target,
        plan,
        shim_dir,
        thread_mode="continue",
        argv_log=argv_log,
        out_file=out,
        thread_file=tf,
        jsonl_file=tj,
        extra_env={"SHIM_RESUME_BEHAVIOR": "fail-other"},
    )
    assert r.returncode != 0, "unrelated resume failure must propagate non-zero"
    assert tf.exists(), "thread state must NOT be cleared on an unrelated failure"
    assert tf.read_text().strip() == "11111111-2222-7333-8444-555555555555"


def test_loop_reset_removes_thread_state(tmp_path):
    """Case 5: loop-reset removes THREAD_FILE + THREAD_JSONL_FILE alongside the
    hash/consistency/snapshot artifacts."""
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="thread_loopreset")
    tf, tj = tmp_path / "x.thread", tmp_path / "x.jsonl"
    tf.write_text("11111111-2222-7333-8444-555555555555")
    tj.write_text("jsonl")

    r = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "loop-reset",
            f"PLAN_FILE={plan.relative_to(target)}",
            f"THREAD_FILE={tf}",
            f"THREAD_JSONL_FILE={tj}",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert not tf.exists(), "loop-reset must remove THREAD_FILE"
    assert not tj.exists(), "loop-reset must remove THREAD_JSONL_FILE"


# ─────────────────────────────────────────────────────────────────────────────
# PR-2 (Bucket A) — the `make review` dispatcher (S1/S2).
#
#   make review MODE={plan,commit} ACTOR={claude,codex} [PLAN_FILE=… ITERATION=…]
#
# resolves to the CORRECT review target — cross-direction for plan review
# (claude→codex, codex→claude), same-AI for commit review — and invokes it.
# REVIEW_RESOLVE=1 is a deterministic test hook: it prints the resolved target
# (or NEEDS-ASK) and exits 0 WITHOUT invoking any CLI. The resolutions are the 4
# of the design note's 6 acceptance branches; the other 2 (Other x plan/commit)
# are command-body assertions on .claude/commands/dev-review.md (test_dev_review_*).
# ─────────────────────────────────────────────────────────────────────────────

# (MODE, ACTOR, resolved-target). Plan review is cross-direction; commit is same-AI.
_DISPATCH_RESOLUTIONS = [
    ("plan", "claude", "review-plan-by-codex"),
    ("plan", "codex", "review-plan-by-claude"),
    ("commit", "claude", "review-commit-by-claude"),
    ("commit", "codex", "review-commit-by-codex"),
]
_ALL_REVIEW_TARGETS = {t for _, _, t in _DISPATCH_RESOLUTIONS}


def _run_review(target, args, extra_env=None):
    """Invoke `make -C target review …`. Always scrubs REVIEWER/ACTOR from the
    inherited env so a developer's `export REVIEWER=codex` cannot leak into the
    unset-actor assertions (the dispatcher reads $(REVIEWER) as the fallback)."""
    env = os.environ.copy()
    env.pop("REVIEWER", None)
    env.pop("ACTOR", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["make", "-C", str(target), "review", *args],
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("mode,actor,expected", _DISPATCH_RESOLUTIONS)
def test_review_resolve_mode_maps_actor_x_mode(tmp_path, mode, actor, expected):
    """The 4 ACTOR x MODE resolutions (4 of the 6 acceptance branches), proven
    deterministically via REVIEW_RESOLVE=1 — no live AI, no shims."""
    target = _bootstrap_fixture(tmp_path)
    result = _run_review(target, [f"MODE={mode}", f"ACTOR={actor}", "REVIEW_RESOLVE=1"])
    assert result.returncode == 0, result.stderr + result.stdout
    resolved_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert expected in resolved_lines, f"expected {expected!r} in {resolved_lines!r}"
    # never mis-resolves to a different review target (e.g. wrong cross-direction)
    for other in _ALL_REVIEW_TARGETS - {expected}:
        assert other not in resolved_lines, (
            f"unexpected {other!r} also resolved: {resolved_lines!r}"
        )


def test_review_resolve_mode_unset_actor_prints_needs_ask_exit_0(tmp_path):
    """Unset ACTOR (and no REVIEWER) → NEEDS-ASK. In RESOLVE mode it exits 0 so
    every branch (including unset) is cleanly assertable; it is the routing
    trigger that makes /dev-review AskUserQuestion for the actor."""
    target = _bootstrap_fixture(tmp_path)
    result = _run_review(target, ["MODE=plan", "REVIEW_RESOLVE=1"])
    assert result.returncode == 0, result.stderr + result.stdout
    resolved_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert "NEEDS-ASK" in resolved_lines, resolved_lines
    for t in _ALL_REVIEW_TARGETS:
        assert t not in resolved_lines, f"unset must not resolve to a target: {resolved_lines!r}"


def test_review_normal_mode_unset_actor_exits_2(tmp_path):
    """NORMAL mode (no REVIEW_RESOLVE) for unset ACTOR prints NEEDS-ASK and
    exits 2 — the exit-code asymmetry vs resolve mode (which exits 0)."""
    target = _bootstrap_fixture(tmp_path)
    result = _run_review(target, ["MODE=plan"])
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "NEEDS-ASK" in result.stdout


def test_review_reviewer_env_is_actor_fallback(tmp_path):
    """REVIEWER is the terminal convenience: a shell `export REVIEWER=codex`
    (env var → make var) supplies ACTOR when ACTOR= is not passed. Resolve mode
    proves the fallback without needing a persistent export across tool calls."""
    target = _bootstrap_fixture(tmp_path)
    result = _run_review(target, ["MODE=plan", "REVIEW_RESOLVE=1"], extra_env={"REVIEWER": "codex"})
    assert result.returncode == 0, result.stderr + result.stdout
    resolved_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    # ACTOR=codex via REVIEWER → cross-direction → review-plan-by-claude
    assert "review-plan-by-claude" in resolved_lines, resolved_lines


def test_review_explicit_actor_overrides_reviewer_env(tmp_path):
    """An explicit ACTOR= on the command line wins over $(REVIEWER) (precedence)."""
    target = _bootstrap_fixture(tmp_path)
    result = _run_review(
        target,
        ["MODE=plan", "ACTOR=claude", "REVIEW_RESOLVE=1"],
        extra_env={"REVIEWER": "codex"},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    resolved_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    # ACTOR=claude wins → cross-direction → review-plan-by-codex (NOT -by-claude)
    assert "review-plan-by-codex" in resolved_lines, resolved_lines
    assert "review-plan-by-claude" not in resolved_lines, resolved_lines


# ── Normal-mode invocation tests (iter-4 FN2) — resolve mode proves the
#    DECISION; these prove the dispatcher actually INVOKES the sub-target (a
#    broken recursive $(MAKE) or dropped PLAN_FILE/ITERATION passthrough would
#    slip past resolve-mode-only tests). Faked codex/claude on PATH.


def test_review_normal_mode_plan_claude_invokes_codex_with_passthrough(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="dispatch_plan_codex")
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    out_file = tmp_path / "out-plan-codex.md"
    result = _run_review(
        target,
        [
            "MODE=plan",
            "ACTOR=claude",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=7",
            f"PLAN_REVIEW_OUT_CODEX={out_file}",
        ],
        extra_env={"PATH": f"{shim_dir}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    log = json.loads(argv_log.read_text())
    clis = [entry["cli"] for entry in log]
    # cross-direction: a Claude-authored plan is reviewed by codex (review-plan-by-codex)
    assert "codex" in clis and "claude" not in clis, clis
    # PLAN_FILE + ITERATION passthrough is visible in the codex prompt
    prompt = " ".join(log[-1]["argv"])
    assert "iteration 7" in prompt, prompt
    assert "docs/plans/dispatch_plan_codex.md" in prompt, prompt


def test_review_normal_mode_plan_codex_invokes_claude_with_passthrough(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    plan = _make_plan_file(target, slug="dispatch_plan_claude")
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    out_file = tmp_path / "out-plan-claude.md"
    result = _run_review(
        target,
        [
            "MODE=plan",
            "ACTOR=codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=7",
            f"PLAN_REVIEW_OUT_CLAUDE={out_file}",
        ],
        extra_env={"PATH": f"{shim_dir}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    log = json.loads(argv_log.read_text())
    clis = [entry["cli"] for entry in log]
    # cross-direction: a Codex-authored plan is reviewed by claude (review-plan-by-claude)
    assert "claude" in clis and "codex" not in clis, clis
    prompt = " ".join(log[-1]["argv"])
    assert "iteration 7" in prompt, prompt
    assert "docs/plans/dispatch_plan_claude.md" in prompt, prompt


def test_review_normal_mode_commit_claude_invokes_claude_same_ai(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    out_file = tmp_path / "out-commit-claude.md"
    result = _run_review(
        target,
        ["MODE=commit", "ACTOR=claude", f"REVIEW_COMMIT_OUT_CLAUDE={out_file}"],
        extra_env={"PATH": f"{shim_dir}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    log = json.loads(argv_log.read_text())
    clis = [entry["cli"] for entry in log]
    # same-AI Tier-1: a Claude commit is reviewed by claude (review-commit-by-claude)
    assert "claude" in clis and "codex" not in clis, clis


def test_review_normal_mode_commit_codex_invokes_codex_same_ai(tmp_path):
    target = _bootstrap_fixture(tmp_path)
    _hermetic_git_setup(target)
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    out_file = tmp_path / "out-commit-codex.md"
    result = _run_review(
        target,
        ["MODE=commit", "ACTOR=codex", f"REVIEW_COMMIT_OUT_CODEX={out_file}"],
        extra_env={"PATH": f"{shim_dir}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    log = json.loads(argv_log.read_text())
    clis = [entry["cli"] for entry in log]
    # same-AI Tier-1: a Codex commit is reviewed by codex (review-commit-by-codex)
    assert "codex" in clis and "claude" not in clis, clis


def test_review_non_allowlist_actor_mode_filtered_to_needs_ask(tmp_path):
    """Tier-2 claude[bot] hardening (PR #35): MODE/ACTOR are sanitized to a fixed
    allowlist via `$(filter)` at the MAKE level (no shell), so a non-allowlist
    value — including shell metacharacters — filters to empty (→ NEEDS-ASK) and
    never reaches the recipe shell. Proves no command injection via ACTOR/MODE."""
    target = _bootstrap_fixture(tmp_path)
    marker = tmp_path / "INJECTED"
    # A QUOTE-BREAKING payload (the `"` escapes the `ACTOR="..."` assignment) —
    # this is what genuinely injected against the pre-fix `ACTOR="$(ACTOR)"`
    # (a bare-`;` payload is already neutralized by the double-quoting, so it
    # would NOT prove the fix). `$(filter)` empties it → NEEDS-ASK, never shell.
    result = _run_review(
        target,
        ["MODE=plan", f'ACTOR=x"; touch {marker}; echo "', "REVIEW_RESOLVE=1"],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    resolved = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert "NEEDS-ASK" in resolved, resolved
    for t in _ALL_REVIEW_TARGETS:
        assert t not in resolved
    assert not marker.exists(), "ACTOR value reached the shell — command injection!"

    # A bogus MODE (also quote-breaking) is likewise filtered → NEEDS-ASK.
    result2 = _run_review(
        target, ['MODE=plan"; rm -rf /; echo "', "ACTOR=claude", "REVIEW_RESOLVE=1"]
    )
    assert result2.returncode == 0, result2.stderr + result2.stdout
    assert "NEEDS-ASK" in [line.strip() for line in result2.stdout.splitlines() if line.strip()]


def test_review_non_allowlist_actor_normal_mode_does_not_invoke_or_inject(tmp_path):
    """Smoke Tier-1 F2 (PR #35): the resolve-mode injection test short-circuits
    before the sub-make, so it only proves the DECISION is safe. This exercises
    the NORMAL-mode recipe shell path too (no REVIEW_RESOLVE): a quote-breaking
    ACTOR filters to empty → NEEDS-ASK (normal-mode exit 2), with NO review CLI
    invoked and NO injected marker — proving the recipe shell never sees the
    raw value on the live-dispatch path either."""
    target = _bootstrap_fixture(tmp_path)
    shim_dir, argv_log = _shim_dir_capturing_argv(tmp_path)
    marker = tmp_path / "INJECTED_NORMAL"
    result = _run_review(
        target,
        ["MODE=plan", f'ACTOR=x"; touch {marker}; echo "'],  # no REVIEW_RESOLVE → normal mode
        extra_env={"PATH": f"{shim_dir}:{os.environ['PATH']}"},
    )
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "NEEDS-ASK" in result.stdout
    assert not marker.exists(), "ACTOR reached the shell in normal mode — command injection!"
    assert not argv_log.exists(), "no review CLI should run for a NEEDS-ASK dispatch"
