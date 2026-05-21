"""Bucket D smoke tests for `--apply --mode=adopt` — two fixtures (closes
Codex iter-6 #5).

Why two fixtures:
  (i)  all-safe — only manual_review_needed=False collisions; runs end-
       to-end with `--auto-accept-recommendations` and NO prompts. A
       single auto-accept-only smoke would hang / EOF on mr=True files,
       so we split.
  (ii) call-details-shaped — full 4-collision shape including CLAUDE.md
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


# ─── Fixture (ii) — call-details-shaped (mr=True via stdin heredoc) ─────────


class TestCallDetailsShapedFixture:
    """Fixture (ii): full 4-collision shape matching the empirically-
    verified call-details collision set per Plan Context line 13:
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
        # (matches the call-details target, which already pins 3.12)
        (target_root / ".python-version").write_bytes(b"3.12\n")
        # rule (f) WRITE_NEW — CLAUDE.md with >20 lines (non-trivial domain content)
        claude_original = b"# Project CLAUDE.md\n\n" + b"line of domain content\n" * 30
        (target_root / "CLAUDE.md").write_bytes(claude_original)
        # rule (g) SKIP — pyproject.toml with [tool.*] (non-trivial)
        pyproject_original = (
            b'[project]\nname = "call-details"\nversion = "0.1.0"\n'
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

    def test_call_details_shape_runs_with_stdin_heredoc(self, tmpdir_isolated):
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
        assert (target / "src" / "main.py").exists()

    def test_call_details_shape_manifest_v2_structure(self, tmpdir_isolated):
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

    def test_call_details_shape_restore_preserves_skip_and_unchanged_files(self, tmpdir_isolated):
        """The load-bearing safety property: `--restore` undoes the writes
        but does NOT touch pre-existing SKIP / OVERWRITE / WRITE_NEW-original
        files. Critical for the live trial against call-details/."""
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

        # The WRITE'd missing files MUST be removed.
        assert not (target / "Makefile").exists()
        assert not (target / "src" / "main.py").exists()

    def test_call_details_shape_user_skips_claude_via_stdin(self, tmpdir_isolated):
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
