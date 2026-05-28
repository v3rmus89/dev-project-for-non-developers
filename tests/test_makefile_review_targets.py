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
