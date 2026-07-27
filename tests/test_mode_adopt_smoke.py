"""Bucket D smoke tests for `--apply --mode=adopt` — two fixtures (closes
Codex iter-6 #5).

Why two fixtures:
  (i)  all-safe — only manual_review_needed=False collisions; runs end-
       to-end with `--auto-accept-recommendations` and NO prompts. A
       single auto-accept-only smoke would hang / EOF on mr=True files,
       so we split.
  (ii) downstream-app-shaped — full 4-collision shape including CLAUDE.md
       + pyproject.toml (both mr=True). Stdin decision script piped via
       heredoc (`stdin_text` argument to `run_cli`) — closes Codex
       iter-5 #1: heredoc/pipe input works portably across CI.

Both fixtures verify the load-bearing safety contracts:
  - Collision-abort does NOT fire (--mode=adopt supersedes the plain-
    apply `--overwrite-existing` contract).
  - Restore manifest captures the right policies (SKIP entries are NOT
    in the manifest per Bucket B mutation-only contract).
  - `--restore` does NOT delete pre-existing files classified as
    OVERWRITE / SKIP — the explicit safety regression guard against
    Codex iter-1 #3 (rules (b)/(c)/(e) were classifying existing files
    as WRITE while WRITE's restore deleted them).
"""

from __future__ import annotations

import io as io_module
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from bootstrap_lib import cli, manifest, render
from bootstrap_lib.cli import _build_context, _build_parser


def run_cli(argv, *, stdin_text=""):
    """In-process cli.main(argv) with injected stdin (StringIO)."""
    old_stdin, old_stdout, old_stderr = sys.stdin, sys.stdout, sys.stderr
    sys.stdin = io_module.StringIO(stdin_text)
    sys.stdout = io_module.StringIO()
    sys.stderr = io_module.StringIO()
    try:
        rc = cli.main(list(argv))
    except SystemExit as e:
        rc = e.code
    finally:
        out = sys.stdout.getvalue()
        err = sys.stderr.getvalue()
        sys.stdin, sys.stdout, sys.stderr = old_stdin, old_stdout, old_stderr
    return rc, out, err


def _planned_files_for(project_name, target_out):
    """Pre-render the skill's planned files so fixtures can construct
    byte-identical pre-existing targets that trip rule (c) SKIP."""
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            project_name,
            "--out",
            str(target_out),
        ]
    )
    ctx = _build_context(args, package_manager="uv")
    return render.render_all(ctx, language="python")


@pytest.fixture
def tmpdir_isolated(tmp_path, monkeypatch):
    """Isolate manifest writes (TMPDIR) so the test doesn't pollute /tmp.

    Also resets tempfile.tempdir which manifest_path() consults via
    `tempfile.mkstemp(...)`."""
    monkeypatch.setenv("TMPDIR", str(tmp_path / ".tmp"))
    (tmp_path / ".tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / ".tmp"))
    return tmp_path


def _extract_manifest_path(stdout):
    m = re.search(r"restore manifest: (\S+)", stdout)
    assert m, f"no restore manifest in stdout: {stdout!r}"
    return Path(m.group(1))


# ─── Fixture (i) — all-safe (manual_review_needed=False end-to-end) ─────────


class TestAllSafeFixture:
    """Fixture (i): every collision is manual_review_needed=False. Runs
    end-to-end with `--auto-accept-recommendations` and no prompts.

    Engineered collisions (each triggers a specific Scope #5 rule, all
    mr=False — covers ALL FOUR mr=False rule branches b/c/d/e):
      .python-version    same pin but no trailing newline → rule (e) SKIP
                         (engineered to BYPASS rule (c) precedence: target
                         `b"3.12"` vs skill `b"3.12\\n"` → sha256 differs
                         so rule (c) doesn't fire; pin parses to "3.12"
                         on both sides so rule (e) match-branch fires)
      .gitignore         skill patterns MISSING → rule (d) APPEND_MERGE
      .pre-commit-config.yaml  byte-identical → rule (c) SKIP
      .editorconfig            empty existing → rule (b) OVERWRITE
    All other planned files: missing → rule (a) WRITE.
    """

    def _setup_target(self, target_root):
        """Pre-populate target_root for the all-safe scenario; returns a
        snapshot of pre-existing-byte-content so post-test asserts can
        verify SKIP-classified files are byte-identical."""
        target_root.mkdir()
        # Pre-render the skill to get the canonical bytes for byte-identical
        # files (rule (c) SKIP requires exact byte match).
        planned = _planned_files_for("x", target_root)

        # rule (e) SKIP — `.python-version` with same pin but different bytes
        # (no trailing newline). Skill renders `3.12\n`; we write `3.12`. The
        # SHA differs → rule (c) doesn't fire; the pin parses identically →
        # rule (e) match-branch fires. Covers rule (e) end-to-end.
        python_version_no_newline = b"3.12"
        (target_root / ".python-version").write_bytes(python_version_no_newline)
        # rule (c) SKIP — byte-identical .pre-commit-config.yaml
        (target_root / ".pre-commit-config.yaml").write_bytes(planned[".pre-commit-config.yaml"])
        # rule (d) APPEND_MERGE — subset of skill's patterns
        gitignore_subset = b"venv/\n*.pyc\n"  # skill has many more
        (target_root / ".gitignore").write_bytes(gitignore_subset)
        # rule (b) OVERWRITE — empty existing
        (target_root / ".editorconfig").write_bytes(b"")

        return {
            ".python-version": python_version_no_newline,
            ".pre-commit-config.yaml": planned[".pre-commit-config.yaml"],
            ".gitignore": gitignore_subset,
            ".editorconfig": b"",
        }, planned

    def test_all_safe_runs_to_completion_under_auto_accept_no_prompts(self, tmpdir_isolated):
        """End-to-end: 4 mr=False collisions + 15 fresh creates apply
        cleanly under `--auto-accept-recommendations`. NO prompts fire
        because all collisions are mr=False."""
        target = tmpdir_isolated / "target"
        pre_snapshot, _planned = self._setup_target(target)

        rc, out, err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
                "--auto-accept-recommendations",
                # Combine with --non-interactive: tightens the contract —
                # if any prompt would fire, the run fails. The fact that
                # this passes proves NO mr=True file is in the plan.
                "--non-interactive",
            ],
        )
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        assert "adopt-mode apply" in out

        # Collision-abort MUST NOT have fired (the plain-apply contract).
        assert "collision detected" not in err
        assert "--overwrite-existing" not in err

        # Files that were rule (c) SKIP: NOT in manifest, byte-identical
        # on disk after apply.
        assert (target / ".python-version").read_bytes() == pre_snapshot[".python-version"]
        assert (target / ".pre-commit-config.yaml").read_bytes() == pre_snapshot[
            ".pre-commit-config.yaml"
        ]

        # Rule (d) APPEND_MERGE: .gitignore now contains BOTH original
        # patterns AND new patterns from the skill.
        merged = (target / ".gitignore").read_bytes()
        assert b"venv/" in merged  # original
        assert b"*.pyc" in merged  # original
        # Skill adds more patterns; pick one that's reasonably skill-specific.
        # (Don't assert specific skill content — just that it grew.)
        assert len(merged) > len(pre_snapshot[".gitignore"]), (
            "APPEND_MERGE should have added skill patterns to the target .gitignore"
        )

        # Rule (b) OVERWRITE: .editorconfig was empty → now has skill content.
        assert (target / ".editorconfig").read_bytes() != b""

        # Rule (a) WRITE: missing files got created. Spot-check a few.
        assert (target / "Makefile").exists()
        assert (target / "pyproject.toml").exists()
        assert (target / "CLAUDE.md").exists()

    def test_all_safe_manifest_does_not_include_skip_entries(self, tmpdir_isolated):
        """Bucket B mutation-only contract: SKIP entries (rules (c), (e))
        are NOT in the v2 manifest. Verifies the safety-regression guard
        from Codex iter-6 #3."""
        target = tmpdir_isolated / "target"
        self._setup_target(target)

        rc, out, _err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
                "--auto-accept-recommendations",
                "--non-interactive",
            ],
        )
        assert rc == 0
        manifest_p = _extract_manifest_path(out)
        loaded = manifest.load_manifest(manifest_p)
        assert loaded.format_version == 2

        # Index entries by path
        paths_in_manifest = {e["path"] for e in loaded.entries}
        # SKIP'd files MUST NOT appear in the manifest
        assert ".python-version" not in paths_in_manifest, (
            "rule (c) SKIP'd .python-version leaked into v2 manifest — "
            "violates mutation-only contract"
        )
        assert ".pre-commit-config.yaml" not in paths_in_manifest, (
            "rule (c) SKIP'd .pre-commit-config.yaml leaked into v2 manifest"
        )
        # APPEND_MERGE + OVERWRITE + WRITE MUST appear
        assert ".gitignore" in paths_in_manifest
        assert ".editorconfig" in paths_in_manifest
        assert "Makefile" in paths_in_manifest

    def test_all_safe_restore_does_not_delete_skip_classified_files(self, tmpdir_isolated):
        """Critical safety: `--restore` must NOT delete pre-existing files
        that adopt-mode classified as SKIP. Closes Codex iter-1 #3 hole
        (rules (b)/(c)/(e) were classifying existing files as WRITE while
        WRITE's restore deleted them)."""
        target = tmpdir_isolated / "target"
        pre_snapshot, _planned = self._setup_target(target)

        rc, out, _err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
                "--auto-accept-recommendations",
                "--non-interactive",
            ],
        )
        assert rc == 0
        manifest_p = _extract_manifest_path(out)

        # Restore
        rc, _out, _err = run_cli(["--restore", str(manifest_p)])
        assert rc == 0

        # SKIP'd files MUST still exist with original bytes (never touched).
        assert (target / ".python-version").exists(), (
            "restore deleted a SKIP'd pre-existing file — iter-1 #3 hole regressed"
        )
        assert (target / ".python-version").read_bytes() == pre_snapshot[".python-version"]
        assert (target / ".pre-commit-config.yaml").exists()
        assert (target / ".pre-commit-config.yaml").read_bytes() == pre_snapshot[
            ".pre-commit-config.yaml"
        ]

        # OVERWRITE'd file (.editorconfig, was empty) → restore writes empty back.
        assert (target / ".editorconfig").exists()
        assert (target / ".editorconfig").read_bytes() == pre_snapshot[".editorconfig"]

        # APPEND_MERGE'd file (.gitignore) → restore truncates to original.
        assert (target / ".gitignore").read_bytes() == pre_snapshot[".gitignore"]

        # WRITE'd files (originally missing) → restore deletes.
        assert not (target / "Makefile").exists()
        assert not (target / "pyproject.toml").exists()
        assert not (target / "CLAUDE.md").exists()


# ─── Fixture (ii) — downstream-app-shaped (mr=True via stdin heredoc) ─────────


class TestDownstreamAppShapedFixture:
    """Fixture (ii): full 4-collision shape matching the empirically-
    verified downstream-app collision set per Plan Context line 13:
      .gitignore, .python-version, CLAUDE.md, pyproject.toml

    Two are mr=True (CLAUDE.md → rule (f) WRITE_NEW; pyproject.toml →
    rule (g) SKIP). Stdin decision script piped via heredoc; closes
    Codex iter-5 #1 (heredoc/pipe input works portably).
    """

    def _setup_target(self, target_root):
        target_root.mkdir()
        # rule (d) APPEND_MERGE — partial gitignore (skill patterns missing)
        gitignore_subset = b"venv/\n*.pyc\n"
        (target_root / ".gitignore").write_bytes(gitignore_subset)
        # rule (c) byte-identical .python-version → SKIP (matches skill 3.12)
        # (matches the downstream-app target, which already pins 3.12)
        (target_root / ".python-version").write_bytes(b"3.12\n")
        # rule (f) WRITE_NEW — CLAUDE.md with >20 lines (non-trivial domain content)
        claude_original = b"# Project CLAUDE.md\n\n" + b"line of domain content\n" * 30
        (target_root / "CLAUDE.md").write_bytes(claude_original)
        # rule (g) SKIP — pyproject.toml with [tool.*] (non-trivial)
        pyproject_original = (
            b'[project]\nname = "downstream-app"\nversion = "0.1.0"\n'
            b"\n[tool.ruff]\nline-length = 100\n"
        )
        (target_root / "pyproject.toml").write_bytes(pyproject_original)
        return {
            ".gitignore": gitignore_subset,
            ".python-version": b"3.12\n",
            "CLAUDE.md": claude_original,
            "pyproject.toml": pyproject_original,
        }

    # Stdin decision script: 2 prompts fire (CLAUDE.md + pyproject.toml).
    # Both prompts get `\n` (accept recommendation = [r]ecommended default).
    # The recommendations are: CLAUDE.md → WRITE_NEW; pyproject.toml → SKIP.
    _accept_recommended_decisions = "\n\n"

    def test_downstream_app_shape_runs_with_stdin_heredoc(self, tmpdir_isolated):
        """End-to-end with two mr=True prompts piped via stdin. User
        accepts both recommendations."""
        target = tmpdir_isolated / "target"
        pre_snapshot = self._setup_target(target)

        rc, _out, err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
            ],
            stdin_text=self._accept_recommended_decisions,
        )
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        # Collision-abort MUST NOT have fired
        assert "collision detected" not in err

        # CLAUDE.md UNTOUCHED (WRITE_NEW writes .new alongside original)
        assert (target / "CLAUDE.md").read_bytes() == pre_snapshot["CLAUDE.md"]
        assert (target / "CLAUDE.md.new").exists()
        # The .new file is the skill template (different content)
        assert (target / "CLAUDE.md.new").read_bytes() != pre_snapshot["CLAUDE.md"]

        # pyproject.toml UNTOUCHED (SKIP'd; user reviews diff manually)
        assert (target / "pyproject.toml").read_bytes() == pre_snapshot["pyproject.toml"]
        assert not (target / "pyproject.toml.new").exists()

        # .python-version UNTOUCHED (byte-identical → SKIP rule (c))
        assert (target / ".python-version").read_bytes() == pre_snapshot[".python-version"]

        # .gitignore APPEND_MERGED — contains original + new patterns
        merged = (target / ".gitignore").read_bytes()
        assert b"venv/" in merged
        assert b"*.pyc" in merged
        assert len(merged) > len(pre_snapshot[".gitignore"])

        # Missing files (rule a) got written — spot-check
        assert (target / "Makefile").exists()
        # Bucket A: the greenfield-only placeholders are SUPPRESSED in adopt
        # mode (the target already has its own source + tests).
        assert not (target / "src" / "main.py").exists()
        assert not (target / "tests" / "test_smoke.py").exists()

    def test_downstream_app_shape_manifest_v2_structure(self, tmpdir_isolated):
        """Verify the v2 manifest: format_version=2; SKIP entries (CLAUDE.md
        wait — CLAUDE.md is WRITE_NEW, IS in manifest; only true SKIPs i.e.
        .python-version + pyproject.toml are NOT in manifest)."""
        target = tmpdir_isolated / "target"
        self._setup_target(target)

        rc, out, _err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
            ],
            stdin_text=self._accept_recommended_decisions,
        )
        assert rc == 0
        manifest_p = _extract_manifest_path(out)
        loaded = manifest.load_manifest(manifest_p)
        assert loaded.format_version == 2

        paths_in_manifest = {e["path"] for e in loaded.entries}
        # SKIPs NOT in manifest
        assert ".python-version" not in paths_in_manifest
        assert "pyproject.toml" not in paths_in_manifest
        # APPEND_MERGE + WRITE_NEW + WRITEs ARE in manifest
        assert ".gitignore" in paths_in_manifest
        assert "CLAUDE.md" in paths_in_manifest  # WRITE_NEW entry (target_path=.new)
        assert "Makefile" in paths_in_manifest

        # WRITE_NEW entry's target_path should be CLAUDE.md.new
        claude_entry = next(e for e in loaded.entries if e["path"] == "CLAUDE.md")
        assert claude_entry["policy"] == "WRITE_NEW"
        assert claude_entry["target_path"] == "CLAUDE.md.new"

    def test_downstream_app_shape_restore_preserves_skip_and_unchanged_files(self, tmpdir_isolated):
        """The load-bearing safety property: `--restore` undoes the writes
        but does NOT touch pre-existing SKIP / OVERWRITE / WRITE_NEW-original
        files. Critical for the live trial against downstream-app/."""
        target = tmpdir_isolated / "target"
        pre_snapshot = self._setup_target(target)

        rc, out, _err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
            ],
            stdin_text=self._accept_recommended_decisions,
        )
        assert rc == 0
        manifest_p = _extract_manifest_path(out)

        # Restore
        rc, _out, _err = run_cli(["--restore", str(manifest_p)])
        assert rc == 0

        # Pre-existing files MUST be byte-identical to pre-apply state.
        assert (target / "CLAUDE.md").read_bytes() == pre_snapshot["CLAUDE.md"]
        assert (target / "pyproject.toml").read_bytes() == pre_snapshot["pyproject.toml"]
        assert (target / ".python-version").read_bytes() == pre_snapshot[".python-version"]
        assert (target / ".gitignore").read_bytes() == pre_snapshot[".gitignore"]

        # The .new file MUST be removed by restore (WRITE_NEW restore).
        assert not (target / "CLAUDE.md.new").exists()

        # The WRITE'd missing files MUST be removed. (src/main.py is NOT in
        # this set — Bucket A suppresses it in adopt mode — so spot-check a
        # genuinely-written rule-(a) file instead.)
        assert not (target / "Makefile").exists()
        assert not (target / ".editorconfig").exists()

    def test_downstream_app_shape_user_skips_claude_via_stdin(self, tmpdir_isolated):
        """User picks [s]kip on the CLAUDE.md prompt → no .new file written."""
        target = tmpdir_isolated / "target"
        pre_snapshot = self._setup_target(target)

        # CLAUDE.md → [s]kip; pyproject.toml → [r]ecommended (= SKIP anyway)
        decisions = "s\n\n"
        rc, _out, _err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
            ],
            stdin_text=decisions,
        )
        assert rc == 0
        # CLAUDE.md untouched, no .new written
        assert (target / "CLAUDE.md").read_bytes() == pre_snapshot["CLAUDE.md"]
        assert not (target / "CLAUDE.md.new").exists()
        # Other files still wrote
        assert (target / "Makefile").exists()


# ─── Shadow-scan escalation — end-to-end (config-shadowing fix plan) ────────


class TestShadowEscalationE2E:
    """B1/B2 end-to-end through the CLI: a target-owned standalone tool
    config must not let `--non-interactive` adoption go green with shadowed
    config."""

    def test_owned_ruff_toml_no_pyproject_exits_2(self, tmpdir_isolated):
        """Target owns a standalone ruff.toml and has NO pyproject.toml →
        the escalated pyproject.toml write is manual_review_needed=True, so
        `--auto-accept-recommendations --non-interactive` exits 2 instead of
        silently writing a pyproject.toml whose [tool.ruff] is dead."""
        target = tmpdir_isolated / "target"
        target.mkdir()
        (target / "ruff.toml").write_bytes(b"line-length = 88\n")

        rc, out, err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
                "--auto-accept-recommendations",
                "--non-interactive",
            ],
        )
        assert rc == 2, f"expected exit 2 (escalation), got rc={rc}; err={err!r}"
        # The report — printed before the abort — carried the B1 advisory.
        assert "config-shadowing advisory" in out
        assert "ruff.toml" in out

    def test_existing_pyproject_with_tool_shows_b2_advisory(self, tmpdir_isolated):
        """Target with a non-trivial pyproject.toml ([tool.ruff]) → rule (g)
        SKIP; the report carries the B2 advisory pointing at `--diff`."""
        target = tmpdir_isolated / "target"
        target.mkdir()
        (target / "pyproject.toml").write_bytes(
            b'[project]\nname = "p"\n\n[tool.ruff]\nline-length = 88\n'
        )

        rc, out, _err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
                "--auto-accept-recommendations",
                "--non-interactive",
            ],
        )
        # rule (g) SKIP is manual_review_needed=True → exit 2 under
        # --non-interactive; the report still carried the B2 advisory.
        assert rc == 2, f"expected exit 2, got rc={rc}"
        assert "left untouched (SKIP)" in out
        assert "--diff" in out


# ─── NEUTRALIZE round-trip — full CLI (Part 2E / S11 / iter-2 FN1) ──────────


class TestNeutralizeRoundTrip:
    """End-to-end through the real CLI (run_cli → cli.main → analyze →
    decide → plan_adoption_entries → _apply_adoption_writes → restore): a target
    that gitignores `.claude/` AND has skill-mergeable `.gitignore` patterns.

    After `--apply --mode=adopt` (consent given): `.gitignore` carries BOTH the
    APPEND_MERGE patterns AND the NEUTRALIZE sentinel block, the command file is
    git-visible, and it landed on disk. After `--restore`: `.gitignore` is
    BYTE-IDENTICAL to pre-apply, the command file is removed, and the created
    `.claude/` / `.claude/commands/` dirs are gone (iter-3 FN3). This drives the
    ordering-sensitive apply AND restore through production code (not a
    hand-sequenced loop)."""

    _CMD = ".claude/commands/dev-review.md"

    def _git_ignored(self, target_root, rel_path):
        """True iff `git check-ignore` reports rel_path as ignored (plain form:
        rc=0 ignored, rc=1 not — a trailing `!`-negation wins as rc=1)."""
        r = subprocess.run(
            ["git", "check-ignore", rel_path],
            cwd=str(target_root),
            capture_output=True,
            text=True,
        )
        # rc 0 = ignored, rc 1 = not ignored. Anything else (e.g. 128 = not a
        # git repo) is a test-harness error that must NOT masquerade as
        # "not ignored" and silently pass a post-apply assertion.
        assert r.returncode in (0, 1), f"git check-ignore errored (rc={r.returncode}): {r.stderr!r}"
        return r.returncode == 0

    def _setup_target(self, target_root):
        target_root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(target_root), check=True)
        # `.claude/` → triggers NEUTRALIZE for the command; `venv/`/`*.pyc` are a
        # subset of the skill's `.gitignore` → triggers APPEND_MERGE on the SAME
        # file (the crux: both tier-0 APPEND_MERGE and tier-1 NEUTRALIZE).
        original_gitignore = b".claude/\nvenv/\n*.pyc\n"
        (target_root / ".gitignore").write_bytes(original_gitignore)
        return {".gitignore": original_gitignore}

    def test_neutralize_apply_then_restore_byte_identical(self, tmpdir_isolated):
        target = tmpdir_isolated / "target"
        pre = self._setup_target(target)
        # Pre-apply: the command file is gitignored by the `.claude/` rule.
        assert self._git_ignored(target, self._CMD), "fixture must gitignore the command pre-apply"

        # `r\n` accepts the single NEUTRALIZE prompt (every other planned file is
        # a fresh rule-(a) WRITE → manual_review_needed=False → no prompt).
        rc, out, err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
            ],
            stdin_text="r\n",
        )
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        assert "collision detected" not in err

        # `.gitignore` carries BOTH the APPEND_MERGE patterns and the NEUTRALIZE block.
        gi = (target / ".gitignore").read_bytes()
        assert b"venv/" in gi and b"*.pyc" in gi  # originals preserved
        assert manifest.NEUTRALIZE_SENTINEL.encode() in gi  # NEUTRALIZE block landed
        assert len(gi) > len(pre[".gitignore"]) + len(
            manifest.NEUTRALIZE_SENTINEL
        )  # APPEND_MERGE grew it too

        # The command is now git-VISIBLE (un-ignored) and landed on disk.
        assert not self._git_ignored(target, self._CMD), (
            "the un-ignore block must make it trackable"
        )
        assert (target / self._CMD).exists()

        # ── restore ──
        manifest_p = _extract_manifest_path(out)
        rc, _o, _e = run_cli(["--restore", str(manifest_p)])
        assert rc == 0

        # `.gitignore` byte-identical to pre-apply (NEUTRALIZE block removed AND
        # APPEND_MERGE truncated — the descending-restore composition).
        assert (target / ".gitignore").read_bytes() == pre[".gitignore"]
        # command file removed; created `.claude/` dirs cleaned (not pre-existing).
        assert not (target / self._CMD).exists()
        assert not (target / ".claude").exists()
        # …and the command is gitignored again (back to the original rule).
        assert self._git_ignored(target, self._CMD)

    def test_neutralize_skip_leaves_gitignore_and_command_untouched(self, tmpdir_isolated):
        """User [s]kips the NEUTRALIZE prompt → `.gitignore` keeps only the
        APPEND_MERGE patterns (no sentinel block) and the command file is NOT
        written (it would be invisible to git anyway)."""
        target = tmpdir_isolated / "target"
        self._setup_target(target)

        rc, _out, err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
            ],
            stdin_text="s\n",  # skip the NEUTRALIZE decision
        )
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        gi = (target / ".gitignore").read_bytes()
        assert manifest.NEUTRALIZE_SENTINEL.encode() not in gi, "skip must NOT append the block"
        assert not (target / self._CMD).exists(), "skip must NOT write the (still-ignored) command"

    def test_neutralize_preserves_private_gitignore_mode(self, tmpdir_isolated):
        """Tier-2 codex P2 (PR #35): NEUTRALIZE must PRESERVE a private (0600)
        `.gitignore` mode through apply AND restore — never loosen it to 0644.
        Drives the real CLI apply + restore (chmod to the captured mode_before)."""
        import os
        import stat

        target = tmpdir_isolated / "target"
        self._setup_target(target)
        gi = target / ".gitignore"
        os.chmod(gi, 0o600)

        rc, out, err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
            ],
            stdin_text="r\n",
        )
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        assert manifest.NEUTRALIZE_SENTINEL.encode() in gi.read_bytes()  # NEUTRALIZE ran
        assert stat.S_IMODE(os.stat(gi).st_mode) == 0o600, "apply must preserve the 0600 mode"

        manifest_p = _extract_manifest_path(out)
        rc, _o, _e = run_cli(["--restore", str(manifest_p)])
        assert rc == 0
        assert stat.S_IMODE(os.stat(gi).st_mode) == 0o600, "restore must preserve the 0600 mode"


# ─── Bucket A — greenfield-only placeholder suppression in adopt mode ────────


class TestGreenfieldPlaceholderSuppression:
    """Bucket A: the greenfield-only entrypoint + smoke placeholders
    (`src/main.py`, `tests/test_smoke.py`) must NOT land in adopt mode — adopt
    brings the skill into a project that already has its own source + tests.
    Greenfield `--apply` keeps them (the filter is adopt-path-only)."""

    def test_constant_names_are_real_planned_files_and_greenfield_keeps_them(self, tmp_path):
        """The suppressed names must be REAL python planned-file keys (a typo'd
        constant would silently suppress nothing) AND greenfield render must
        still include them (suppression is adopt-only, not a render change)."""
        planned = _planned_files_for("x", tmp_path)
        for name in render.GREENFIELD_ONLY_PLACEHOLDERS["python"]:
            assert name in planned, f"{name!r} is not a real python planned-file key"
        # The mode-agnostic greenfield render KEEPS the placeholders.
        assert "src/main.py" in planned
        assert "tests/test_smoke.py" in planned

    def test_adopt_suppresses_placeholders_but_writes_other_creates(self, tmpdir_isolated):
        """End-to-end: adopt into a target lacking the placeholders → they are
        NOT written, while the other rule-(a) creates still land."""
        target = tmpdir_isolated / "target"
        target.mkdir()
        rc, out, err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
                "--non-interactive",
            ],
        )
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        assert "adopt-mode apply" in out
        # Suppressed — never written.
        assert not (target / "src" / "main.py").exists()
        assert not (target / "tests" / "test_smoke.py").exists()
        # Other rule-(a) creates still landed.
        assert (target / "Makefile").exists()
        assert (target / "pyproject.toml").exists()
        assert (target / ".editorconfig").exists()

    def test_suppressed_placeholders_absent_from_manifest(self, tmpdir_isolated):
        """The placeholders must not appear as manifest entries either (they
        were filtered before plan_adoption_entries, so there is nothing to
        restore)."""
        target = tmpdir_isolated / "target"
        target.mkdir()
        rc, out, _err = run_cli(
            [
                "--apply",
                "--mode",
                "adopt",
                "--language",
                "python",
                "--project-name",
                "x",
                "--out",
                str(target),
                "--non-interactive",
            ],
        )
        assert rc == 0
        loaded = manifest.load_manifest(_extract_manifest_path(out))
        paths_in_manifest = {e["path"] for e in loaded.entries}
        assert "src/main.py" not in paths_in_manifest
        assert "tests/test_smoke.py" not in paths_in_manifest


# ─── Bucket B — standalone Makefile.review delivery in adopt mode ────────────


class TestBucketBStandaloneMakefileReview:
    """Bucket B: the plan-review machinery is inlined into the generated
    Makefile via `{% include 'Makefile.review.tmpl' %}`. When the target OWNS a
    Makefile (adopt SKIPs it) the machinery never lands while the scripts it
    calls do — so deliver it as a standalone `Makefile.review` WRITE + an
    `include` hint naming the colliding targets. When the target has NO Makefile,
    the written base Makefile already inlines the fragment, so the standalone
    copy is dropped."""

    _ADOPT_ARGS = (
        "--apply",
        "--mode",
        "adopt",
        "--language",
        "python",
        "--project-name",
        "x",
    )

    def _setup_target_owning_makefile(self, target_root):
        """A non-trivial existing Makefile (rule (h) SKIP, manual_review=True)
        that defines a `review:` target — the exact name that collides with the
        fragment's `review` dispatcher (R-B1)."""
        target_root.mkdir()
        (target_root / "Makefile").write_bytes(
            b".PHONY: test review\n\ntest:\n\tpytest\n\nreview:\n\t@echo old review\n"
        )

    def test_owns_makefile_emits_standalone_review_and_include_hint(self, tmpdir_isolated):
        target = tmpdir_isolated / "target"
        self._setup_target_owning_makefile(target)
        # The existing Makefile is the only manual-review prompt (rule (h) SKIP).
        # Accept the recommended SKIP with "r\n" so the target keeps its Makefile.
        rc, out, err = run_cli([*self._ADOPT_ARGS, "--out", str(target)], stdin_text="r\n")
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        # Base Makefile SKIPped — untouched.
        assert (target / "Makefile").read_bytes().startswith(b".PHONY: test review")
        # Standalone Makefile.review WRITTEN, carrying the review dispatcher.
        review = target / "Makefile.review"
        assert review.exists(), (
            "standalone Makefile.review must be written when the target owns a Makefile"
        )
        assert b"review:" in review.read_bytes()
        # The scripts the machinery calls also landed (rule (a) WRITE) — they now
        # have a home (the previously-orphaned-scripts bug).
        assert (target / "scripts" / "loop-status.py").exists()
        # Include hint printed, naming the REAL collision (`review`).
        assert "include Makefile.review" in out
        assert "remove your existing review target" in out
        # Tier-2 codex round-4: the skill's Makefile was SKIPped (owner owns one),
        # so its `install-hooks` recipe never landed — don't advertise it.
        assert "make install-hooks" not in out

    def test_owns_makefile_review_is_in_manifest_and_restore_deletes_it(self, tmpdir_isolated):
        """R-3: Makefile.review is a rule-(a) WRITE → it is in the v2 manifest and
        restore deletes it; the target's own Makefile is untouched throughout."""
        target = tmpdir_isolated / "target"
        self._setup_target_owning_makefile(target)
        original_makefile = (target / "Makefile").read_bytes()

        rc, out, _err = run_cli([*self._ADOPT_ARGS, "--out", str(target)], stdin_text="r\n")
        assert rc == 0
        assert (target / "Makefile.review").exists()
        loaded = manifest.load_manifest(_extract_manifest_path(out))
        entry = next(e for e in loaded.entries if e["path"] == "Makefile.review")
        assert entry["policy"] == "WRITE"

        rc, _o, _e = run_cli(["--restore", str(_extract_manifest_path(out))])
        assert rc == 0
        assert not (target / "Makefile.review").exists(), "WRITE → restore must delete it"
        assert (target / "Makefile").read_bytes() == original_makefile, "owner Makefile untouched"

    def test_no_makefile_drops_standalone_review(self, tmpdir_isolated):
        """Fixture B: target has its own source but NO Makefile → the base
        Makefile is a rule-(a) WRITE that inlines the fragment, so the standalone
        copy is dropped (not written, not in manifest, no include hint)."""
        target = tmpdir_isolated / "target"
        target.mkdir()
        (target / "src").mkdir()
        (target / "src" / "app.py").write_bytes(b"# the target's real entrypoint\n")

        rc, out, err = run_cli([*self._ADOPT_ARGS, "--out", str(target), "--non-interactive"])
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        # Base Makefile written (it inlines the review fragment) …
        assert (target / "Makefile").exists()
        assert b"review:" in (target / "Makefile").read_bytes()
        # … and NO redundant standalone Makefile.review.
        assert not (target / "Makefile.review").exists()
        assert "include Makefile.review" not in out
        loaded = manifest.load_manifest(_extract_manifest_path(out))
        assert "Makefile.review" not in {e["path"] for e in loaded.entries}

    def test_owner_overwrites_makefile_drops_standalone_review(self, tmpdir_isolated):
        """Tier-2 codex P2: pass 1 keyed on the Makefile RECOMMENDATION (SKIP),
        but the owner can answer [o]verwrite. The skill's Makefile (which inlines
        the fragment) then becomes the active one, so the standalone Makefile.review
        must be DROPPED and the include hint suppressed — else duplicate `review`
        targets once the owner includes it."""
        target = tmpdir_isolated / "target"
        self._setup_target_owning_makefile(target)
        # The Makefile is the only prompt (rule (h) SKIP). [o] + typed OVERWRITE.
        rc, out, err = run_cli(
            [*self._ADOPT_ARGS, "--out", str(target)], stdin_text="o\nOVERWRITE\n"
        )
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        # Skill Makefile written (it inlines the review fragment) …
        assert b"review:" in (target / "Makefile").read_bytes()
        # … so NO redundant standalone + NO include hint + not in manifest.
        assert not (target / "Makefile.review").exists()
        assert "include Makefile.review" not in out
        loaded = manifest.load_manifest(_extract_manifest_path(out))
        assert "Makefile.review" not in {e["path"] for e in loaded.entries}

    def test_owner_picks_new_for_makefile_keeps_standalone_review(self, tmpdir_isolated):
        """The [n]ew counterpart of the codex-P2 case: the skill's Makefile goes
        to Makefile.new and the owner's Makefile stays ACTIVE (no inline fragment),
        so the standalone Makefile.review is KEPT and the include hint still fires."""
        target = tmpdir_isolated / "target"
        self._setup_target_owning_makefile(target)
        rc, out, err = run_cli([*self._ADOPT_ARGS, "--out", str(target)], stdin_text="n\n")
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        assert (target / "Makefile.new").exists()  # skill's Makefile as .new (inactive)
        assert (target / "Makefile.review").exists()  # standalone KEPT
        assert "include Makefile.review" in out
        # owner's Makefile untouched + still active
        assert (target / "Makefile").read_bytes().startswith(b".PHONY: test review")

    def test_target_owns_makefile_review_skip_keeps_theirs_no_hint(self, tmpdir_isolated):
        """Tier-2 codex P2 (round 2): a target that already owns BOTH a Makefile
        AND a Makefile.review. If the owner SKIPs the existing Makefile.review,
        no fresh standalone is written — so `makefile_review_emitted` (now
        ground-truthed from the actual WRITE/OVERWRITE entries) is False and the
        include hint must NOT fire, and their Makefile.review stays untouched."""
        target = tmpdir_isolated / "target"
        self._setup_target_owning_makefile(target)
        existing_review = b"# my own Makefile.review\nreview:\n\t@echo mine\n"
        (target / "Makefile.review").write_bytes(existing_review)
        # Two prompts now (Makefile + Makefile.review, both rule (h) SKIP, mr=True,
        # in sorted order). Accept the recommended SKIP for both.
        rc, out, err = run_cli([*self._ADOPT_ARGS, "--out", str(target)], stdin_text="\n\n")
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        # Their Makefile.review is untouched (SKIP) …
        assert (target / "Makefile.review").read_bytes() == existing_review
        # … no fresh WRITE/OVERWRITE of it in the manifest …
        loaded = manifest.load_manifest(_extract_manifest_path(out))
        assert not any(
            e["path"] == "Makefile.review" and e["policy"] in ("WRITE", "OVERWRITE")
            for e in loaded.entries
        )
        # … and the include hint does NOT fire (we wrote no fresh standalone).
        assert "include Makefile.review" not in out

    def test_target_makefile_already_has_machinery_drops_standalone(self, tmpdir_isolated):
        """Tier-2 codex round-3 P2: a target whose Makefile already inlines the
        review machinery (carries the fragment's SELFTEST-OVERLAP sentinel — e.g.
        a project previously bootstrapped by this skill) must NOT get a redundant
        standalone Makefile.review or an include hint (they would duplicate the
        inline targets)."""
        target = tmpdir_isolated / "target"
        target.mkdir()
        (target / "Makefile").write_bytes(
            b".PHONY: test\ntest:\n\tpytest\n\n"
            b"# SELFTEST-OVERLAP-BEGIN: shared/Makefile.review.tmpl\n"
            b"review:\n\t@echo dispatch\n"
            b"# SELFTEST-OVERLAP-END: shared/Makefile.review.tmpl\n"
        )
        # rule (h) SKIP (differs from skill render), mr=True → accept SKIP.
        rc, out, err = run_cli([*self._ADOPT_ARGS, "--out", str(target)], stdin_text="r\n")
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        assert not (target / "Makefile.review").exists()
        assert "include Makefile.review" not in out
