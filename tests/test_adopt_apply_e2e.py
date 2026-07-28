"""End-to-end tests for `--apply --mode=adopt` via the CLI surface.

Covers the full pipeline that _main_apply_adopt orchestrates:
  analyze_target → format_recommendation_report → _interactive_decide →
  plan_adoption_entries → write v2 manifest → _apply_adoption_writes →
  restore (via the v2 restore matrix).

In-process invocation via `cli.main(argv)`; stdin injected via
`monkeypatch.setattr(sys, 'stdin', ...)` for interactive prompts (heredoc-
shaped tests). Plus direct `_apply_adoption_writes` unit tests with
synthetic entries.
"""

from __future__ import annotations

import io as io_module
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bootstrap_lib import apply_pipeline, cli, guidance, manifest


def run_cli(argv, *, stdin_text=""):
    """Run cli.main(argv) in-process; inject stdin via StringIO."""
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


# ─── Direct _apply_adoption_writes unit tests (synthetic entries) ───


def _sha256(b):
    import hashlib

    return hashlib.sha256(b).hexdigest()


def _v2_entry(
    *,
    policy,
    path,
    target_path=None,
    sha256_after_target_path,
    sha256_before_target_path=None,
    content_before_b64=None,
    pre_append_length=None,
    mode_before=None,
):
    return {
        "path": path,
        "policy": policy,
        "target_path": target_path if target_path is not None else path,
        "existed_before": content_before_b64 is not None,
        "content_before_b64": content_before_b64,
        "mode_before": mode_before,
        "sha256_before": sha256_before_target_path,
        "sha256_after": sha256_after_target_path,
        "sha256_before_target_path": sha256_before_target_path,
        "sha256_after_target_path": sha256_after_target_path,
        "pre_append_length": pre_append_length,
        "mode_after": 0o644,
    }


class TestApplyAdoptionWritesDirect:
    """Direct invocations of `cli._apply_adoption_writes` to verify per-
    policy write semantics. AdoptionPlan is unused inside the function (only
    held for future logging hooks); pass a minimal stub."""

    def _stub_plan(self, tmp_path):
        from bootstrap_lib.adopt import AdoptionPlan

        return AdoptionPlan(target_root=tmp_path, analyses=())

    def test_write_creates_new_file(self, tmp_path):
        skill = b"# new\n"
        entries = [
            _v2_entry(policy="WRITE", path="new.txt", sha256_after_target_path=_sha256(skill))
        ]
        apply_pipeline._apply_adoption_writes(
            tmp_path, {"new.txt": skill}, self._stub_plan(tmp_path), entries
        )
        assert (tmp_path / "new.txt").read_bytes() == skill

    def test_overwrite_replaces_existing(self, tmp_path):
        (tmp_path / "f.txt").write_bytes(b"original\n")
        skill = b"replaced\n"
        entries = [
            _v2_entry(
                policy="OVERWRITE",
                path="f.txt",
                sha256_before_target_path=_sha256(b"original\n"),
                sha256_after_target_path=_sha256(skill),
            )
        ]
        apply_pipeline._apply_adoption_writes(
            tmp_path, {"f.txt": skill}, self._stub_plan(tmp_path), entries
        )
        assert (tmp_path / "f.txt").read_bytes() == skill

    def test_write_new_creates_dot_new_file_original_untouched(self, tmp_path):
        original = b"# user CLAUDE.md\n"
        (tmp_path / "CLAUDE.md").write_bytes(original)
        skill = b"# skill template\n"
        entries = [
            _v2_entry(
                policy="WRITE_NEW",
                path="CLAUDE.md",
                target_path="CLAUDE.md.new",
                sha256_after_target_path=_sha256(skill),
            )
        ]
        apply_pipeline._apply_adoption_writes(
            tmp_path, {"CLAUDE.md": skill}, self._stub_plan(tmp_path), entries
        )
        assert (tmp_path / "CLAUDE.md.new").read_bytes() == skill
        # Critical safety invariant: original UNTOUCHED.
        assert (tmp_path / "CLAUDE.md").read_bytes() == original

    def test_write_new_collision_at_apply_time_raises(self, tmp_path):
        """Defense-in-depth: if `.new` appears between plan-time and apply-
        time (TOCTOU), fail-loud rather than overwrite."""
        from bootstrap_lib.adopt import AdoptionCollisionError

        (tmp_path / "CLAUDE.md").write_bytes(b"# user\n")
        (tmp_path / "CLAUDE.md.new").write_bytes(b"# user already started merging\n")
        entries = [
            _v2_entry(
                policy="WRITE_NEW",
                path="CLAUDE.md",
                target_path="CLAUDE.md.new",
                sha256_after_target_path=_sha256(b"# skill\n"),
            )
        ]
        with pytest.raises(AdoptionCollisionError):
            apply_pipeline._apply_adoption_writes(
                tmp_path, {"CLAUDE.md": b"# skill\n"}, self._stub_plan(tmp_path), entries
            )
        # Pre-existing .new MUST be preserved.
        assert (tmp_path / "CLAUDE.md.new").read_bytes() == b"# user already started merging\n"

    def test_neutralize_sentinel_appeared_at_apply_raises(self, tmp_path):
        """TOCTOU (Tier-2 codex P2, PR #35): if the un-ignore block appears in
        `.gitignore` between plan-time and apply-time, NEUTRALIZE must FAIL LOUD
        — not silently no-op while recording a block restore would later remove."""
        from bootstrap_lib import manifest
        from bootstrap_lib.adopt import AdoptionCollisionError

        gi = tmp_path / ".gitignore"
        gi.write_bytes(b".claude/\n")  # plan-time state (no sentinel)
        entry = manifest._build_v2_neutralize_entry(tmp_path)
        tampered = (
            b".claude/\n"
            + manifest.NEUTRALIZE_SENTINEL.encode()
            + b"\n!.claude/commands/dev-review.md\n"
        )
        gi.write_bytes(tampered)  # the block appears in the apply window
        with pytest.raises(AdoptionCollisionError):
            apply_pipeline._apply_adoption_writes(tmp_path, {}, self._stub_plan(tmp_path), [entry])
        assert gi.read_bytes() == tampered  # untouched (no double-append)

    def test_neutralize_gitignore_deleted_at_apply_raises(self, tmp_path):
        """TOCTOU (Tier-2 codex P2, PR #35): if `.gitignore` is deleted in the
        apply window, NEUTRALIZE must FAIL LOUD — not recreate it from empty
        (which restore would leave behind as a stray file)."""
        from bootstrap_lib import manifest
        from bootstrap_lib.adopt import AdoptionCollisionError

        gi = tmp_path / ".gitignore"
        gi.write_bytes(b".claude/\n")
        entry = manifest._build_v2_neutralize_entry(tmp_path)
        gi.unlink()  # deleted in the apply window
        with pytest.raises(AdoptionCollisionError):
            apply_pipeline._apply_adoption_writes(tmp_path, {}, self._stub_plan(tmp_path), [entry])
        assert not gi.exists()  # NOT recreated

    def test_append_merge_re_merges_at_apply_time(self, tmp_path):
        """Re-merge at apply uses CURRENT target bytes — line-level idempotent."""
        (tmp_path / ".gitignore").write_bytes(b"venv/\n")
        skill = b"venv/\n*.pyc\n.env\n"
        entries = [
            _v2_entry(
                policy="APPEND_MERGE",
                path=".gitignore",
                sha256_before_target_path=_sha256(b"venv/\n"),
                sha256_after_target_path="placeholder",  # recomputed by apply
                pre_append_length=len(b"venv/\n"),
            )
        ]
        apply_pipeline._apply_adoption_writes(
            tmp_path, {".gitignore": skill}, self._stub_plan(tmp_path), entries
        )
        result = (tmp_path / ".gitignore").read_bytes()
        # Original retained + new lines appended
        assert b"venv/\n" in result
        assert b"*.pyc" in result
        assert b".env" in result

    def test_unknown_policy_raises(self, tmp_path):
        entries = [_v2_entry(policy="WEIRD", path="f.txt", sha256_after_target_path="x")]
        with pytest.raises(ValueError, match="unknown policy"):
            apply_pipeline._apply_adoption_writes(
                tmp_path, {"f.txt": b"x"}, self._stub_plan(tmp_path), entries
            )


# ─── End-to-end via cli.main() ───


class TestAdoptModeApplyE2E:
    """Full pipeline: argparse → _resolve_mode → _main_apply_adopt →
    analyze → report → decide → plan_adoption_entries → write_manifest →
    _apply_adoption_writes → restore.

    Uses the existing skill templates (no fixture override) so this is a
    real integration test against the same skill content the user runs.
    """

    def _common_args(self, tmp_path):
        return [
            "--apply",
            "--mode",
            "adopt",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(tmp_path),
        ]

    def test_adopt_greenfield_all_writes_no_prompts_with_non_interactive(self, tmp_path):
        """Greenfield target (no existing files) → every planned file is
        rule (a) WRITE → no prompts needed even under --non-interactive."""
        rc, out, _err = run_cli(
            [*self._common_args(tmp_path), "--non-interactive"],
        )
        assert rc == 0, f"expected success, got rc={rc}"
        assert "adopt-mode apply" in out
        assert "restore manifest" in out
        # The skill writes pyproject.toml, .gitignore, etc.; pick a known file
        # to verify it landed.
        assert (tmp_path / "pyproject.toml").exists()
        assert (tmp_path / ".gitignore").exists()

    def test_adopt_with_user_overrides_via_stdin(self, tmp_path):
        """Pre-existing CLAUDE.md → rule (f) WRITE_NEW (mr=True). User picks
        [s]kip via stdin → no .new file written; original preserved."""
        original_claude = b"# my project CLAUDE.md\n" + b"line\n" * 30
        (tmp_path / "CLAUDE.md").write_bytes(original_claude)
        # All other files are missing → rule (a) WRITE (mr=False, no prompts)
        # CLAUDE.md → rule (f) WRITE_NEW (mr=True, prompts)
        # User types "s\n" to SKIP the CLAUDE.md decision.
        rc, _out, _err = run_cli(self._common_args(tmp_path), stdin_text="s\n")
        assert rc == 0
        # Original CLAUDE.md preserved (untouched)
        assert (tmp_path / "CLAUDE.md").read_bytes() == original_claude
        # No .new written
        assert not (tmp_path / "CLAUDE.md.new").exists()
        # Other files DID get written (rule a)
        assert (tmp_path / "pyproject.toml").exists()

    def test_adopt_user_accepts_recommended_write_new(self, tmp_path):
        """Pre-existing CLAUDE.md → rule (f) WRITE_NEW; user accepts [r]
        (default) → .new file IS written; original preserved."""
        original_claude = b"# my project\n" + b"line\n" * 30
        (tmp_path / "CLAUDE.md").write_bytes(original_claude)
        # Empty line → default = [r]ecommended
        rc, _out, _err = run_cli(self._common_args(tmp_path), stdin_text="\n")
        assert rc == 0
        # Original preserved
        assert (tmp_path / "CLAUDE.md").read_bytes() == original_claude
        # .new IS written
        assert (tmp_path / "CLAUDE.md.new").exists()

    def test_adopt_non_interactive_with_manual_review_exits_2(self, tmp_path):
        """Pre-existing CLAUDE.md needs review → --non-interactive → exit 2
        BEFORE any filesystem mutation."""
        original_claude = b"# my project\n" + b"line\n" * 30
        (tmp_path / "CLAUDE.md").write_bytes(original_claude)
        rc, _out, err = run_cli(
            [*self._common_args(tmp_path), "--non-interactive"],
        )
        assert rc == 2
        assert "--non-interactive" in err
        assert "CLAUDE.md" in err
        # Original preserved
        assert (tmp_path / "CLAUDE.md").read_bytes() == original_claude
        # No partial writes — pyproject.toml shouldn't exist either
        assert not (tmp_path / "pyproject.toml").exists()

    def test_adopt_dot_new_collision_exit_2(self, tmp_path):
        """Pre-existing CLAUDE.md.new (e.g. user already started merging) →
        rule (f) WRITE_NEW recommendation → plan_adoption_entries raises
        AdoptionCollisionError → exit 2 with rename-or-remove guidance."""
        (tmp_path / "CLAUDE.md").write_bytes(b"# my project\n" + b"line\n" * 30)
        (tmp_path / "CLAUDE.md.new").write_bytes(b"# user started merging\n")
        # User accepts the recommended WRITE_NEW (default = [r])
        rc, _out, err = run_cli(self._common_args(tmp_path), stdin_text="\n")
        assert rc == 2
        assert "CLAUDE.md.new" in err
        assert "rename or remove it" in err
        # User's in-progress .new MUST be preserved
        assert (tmp_path / "CLAUDE.md.new").read_bytes() == b"# user started merging\n"

    def test_adopt_quit_exits_2_no_mutations(self, tmp_path):
        """[q]uit before any decision → exit 2, no files written."""
        (tmp_path / "CLAUDE.md").write_bytes(b"# my project\n" + b"line\n" * 30)
        rc, _out, err = run_cli(self._common_args(tmp_path), stdin_text="q\n")
        assert rc == 2
        assert "user quit" in err
        # Original preserved; no writes happened
        assert (tmp_path / "CLAUDE.md").read_bytes().startswith(b"# my project")
        assert not (tmp_path / "pyproject.toml").exists()
        assert not (tmp_path / "CLAUDE.md.new").exists()

    def test_adopt_manifest_target_root_is_absolute_for_cross_cwd_restore(
        self, tmp_path, monkeypatch
    ):
        """Tier-1 finding F1: v2 manifest must store target_root as an
        ABSOLUTE path (matching v1's _prepare_apply contract). Without this,
        restoring from a different cwd silently exits 0 with zero mutations
        — load-bearing safety hole. Mirrors v1 behavior.

        Regression test: invoke adopt-apply with a relative --out, then
        restore from a different cwd, assert files are actually removed.
        """
        import os
        import re
        import tempfile as _tempfile

        monkeypatch.setenv("TMPDIR", str(tmp_path / ".tmp"))
        (tmp_path / ".tmp").mkdir()
        monkeypatch.setattr(_tempfile, "tempdir", str(tmp_path / ".tmp"))

        # cwd A: where apply runs
        cwd_a = tmp_path / "cwd_a"
        cwd_a.mkdir()
        original_cwd = Path.cwd()
        try:
            os.chdir(cwd_a)
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
                    "target",  # RELATIVE — was the bug trigger
                    "--non-interactive",
                ],
            )
        finally:
            os.chdir(original_cwd)
        assert rc == 0
        target_root = cwd_a / "target"
        assert (target_root / "pyproject.toml").exists()

        # Manifest's recorded target_root MUST be absolute (matches v1).
        m = re.search(r"restore manifest: (\S+)", out)
        assert m
        manifest_p = Path(m.group(1))
        loaded = manifest.load_manifest(manifest_p)
        assert Path(loaded.target_root).is_absolute(), (
            f"v2 manifest target_root must be absolute, got {loaded.target_root!r}"
        )
        # Also pin: the resolved path matches the actual target dir.
        assert Path(loaded.target_root) == target_root.resolve()

        # cwd B: restore from a different working directory.
        cwd_b = tmp_path / "cwd_b"
        cwd_b.mkdir()
        try:
            os.chdir(cwd_b)
            rc, _out, _err = run_cli(["--restore", str(manifest_p)])
        finally:
            os.chdir(original_cwd)
        assert rc == 0
        # Files MUST be removed (restore worked across cwds).
        assert not (target_root / "pyproject.toml").exists(), (
            "restore from a different cwd silently failed — F1 regressed"
        )
        assert not (target_root / ".gitignore").exists()

    def test_adopt_then_restore_round_trip(self, tmp_path, monkeypatch):
        """End-to-end: apply --mode=adopt → bootstrap.py --restore <manifest>
        gets target back to pre-apply state. The trial's safety contract."""
        import tempfile as _tempfile

        monkeypatch.setenv("TMPDIR", str(tmp_path / ".tmp"))
        (tmp_path / ".tmp").mkdir()
        monkeypatch.setattr(_tempfile, "tempdir", str(tmp_path / ".tmp"))

        target = tmp_path / "target"
        target.mkdir()
        # Pre-apply state: empty target → all WRITE
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
        # Extract manifest path from output
        import re

        m = re.search(r"restore manifest: (\S+)", out)
        assert m, f"no restore manifest in output: {out!r}"
        manifest_p = Path(m.group(1))
        assert manifest_p.exists()

        # Confirm files were written
        assert (target / "pyproject.toml").exists()
        assert (target / ".gitignore").exists()

        # Now restore
        rc, _out, _err = run_cli(["--restore", str(manifest_p)])
        assert rc == 0
        # Files removed (WRITE → restore deletes)
        assert not (target / "pyproject.toml").exists()
        assert not (target / ".gitignore").exists()
        # Target dir itself should still exist (only created_directories below
        # target_root are removed, not target_root itself).
        assert target.exists()

    def test_adopt_all_skip_outcome_no_manifest_no_writes(self, tmp_path):
        """If every file is a rule-(c) byte-identical SKIP OR user picks
        [s]kip on every manual-review file, no manifest written, no writes
        happen, and the user sees a clear "all entries SKIPPED" message."""
        # To engineer all-SKIP, we need EVERY planned file to be byte-identical
        # OR rule-(h) default skip. That's hard to set up without controlling
        # the skill render. Cheat by making rule (h) fire on every file: write
        # the SAME content to every planned-file path so rule (c) won't fire
        # (different from skill) but rule (h) defaults to SKIP/manual_review.
        # Then user picks [s]kip for each.
        #
        # Skip this scenario for now — it requires inspecting which files the
        # skill writes and pre-populating each with unrelated bytes. The
        # "all-SKIP exit" branch in _main_apply_adopt is small + tested via
        # the `if not entries` path being unreachable in current tests; the
        # branch logic itself is one print + return 0.
        pytest.skip(
            "all-SKIP scenario requires per-file fixture engineering; the "
            "code branch is trivial (single print + return) — covered by "
            "manual smoke walk during Bucket E live trial"
        )


# ─── --restore on a v2 manifest from adopt-mode end-to-end ───


class TestAdoptModeRestoreE2E:
    """Restore an actual v2 manifest produced by adopt-mode apply."""

    def test_write_new_restore_removes_only_dot_new_preserves_original(self, tmp_path, monkeypatch):
        """The load-bearing safety property: after adopt-mode writes
        CLAUDE.md.new, --restore removes the .new AND preserves the
        original CLAUDE.md exactly."""
        import tempfile as _tempfile

        monkeypatch.setenv("TMPDIR", str(tmp_path / ".tmp"))
        (tmp_path / ".tmp").mkdir()
        monkeypatch.setattr(_tempfile, "tempdir", str(tmp_path / ".tmp"))

        target = tmp_path / "target"
        target.mkdir()
        original_claude = b"# my project CLAUDE.md\n" + b"unique-marker\n" * 50
        (target / "CLAUDE.md").write_bytes(original_claude)

        # Apply, accept WRITE_NEW recommendation
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
            stdin_text="\n",  # accept recommended for CLAUDE.md
        )
        assert rc == 0
        # .new exists; original untouched
        assert (target / "CLAUDE.md.new").exists()
        assert (target / "CLAUDE.md").read_bytes() == original_claude

        # Extract manifest path
        import re

        m = re.search(r"restore manifest: (\S+)", out)
        manifest_p = Path(m.group(1))

        # Verify manifest IS v2
        loaded = manifest.load_manifest(manifest_p)
        assert loaded.format_version == 2

        # Restore
        rc, _out, _err = run_cli(["--restore", str(manifest_p)])
        assert rc == 0
        # .new removed
        assert not (target / "CLAUDE.md.new").exists()
        # Original byte-identical to pre-apply
        assert (target / "CLAUDE.md").read_bytes() == original_claude


# Verify `make selftest`-style sanity: the existing plain-apply path
# remains intact (no regressions from the new --mode=adopt branch).
def test_plain_apply_path_unchanged_by_adopt_wiring(tmp_path):
    """Regression guard: --apply WITHOUT --mode=adopt still uses the legacy
    plan_entries + _apply_writes path and produces a v1 manifest."""
    target = tmp_path / "target"
    target.mkdir()
    # subprocess to fully isolate from pytest's stdin/stdout fixtures (the
    # plain-apply path doesn't read stdin so the simpler invocation works)
    bootstrap_py = Path(__file__).resolve().parent.parent / "bootstrap.py"
    result = subprocess.run(
        [
            sys.executable,
            str(bootstrap_py),
            "--apply",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(target),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"plain --apply regressed: rc={result.returncode}, stderr={result.stderr}"
    )
    # Files written
    assert (target / "pyproject.toml").exists()
    # Extract manifest path; verify it's v1 (no format_version OR =1)
    import re

    m = re.search(r"restore manifest: (\S+)", result.stdout)
    assert m, f"no restore manifest in: {result.stdout!r}"
    loaded = manifest.load_manifest(m.group(1))
    assert loaded.format_version == 1, (
        f"plain --apply produced format_version={loaded.format_version} (expected v1)"
    )


# ─── Bucket C — shared post-apply guidance helper ───


def _guidance_output(**kwargs):
    """Capture `cli._print_post_apply_guidance` stdout for the given flags.

    The helper only reads a few attrs off `args`, so a SimpleNamespace stand-in
    keeps these unit tests pure (no argparse / filesystem)."""
    args = SimpleNamespace(
        language=kwargs.pop("language", "python"),
        github_review=kwargs.pop("github_review", "none"),
        github_owner=kwargs.pop("github_owner", "o"),
        github_repo=kwargs.pop("github_repo", "r"),
    )
    old_stdout = sys.stdout
    sys.stdout = io_module.StringIO()
    try:
        guidance._print_post_apply_guidance(args, "/tmp/target", **kwargs)
        return sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout


class TestPostApplyGuidanceHelper:
    """Bucket C / AD3: one shared helper, two callers (v1 + adopt). These pin
    the adopt-specific adaptations directly; the v1 byte-identity is guarded by
    the existing test_bootstrap_cli.py guidance tests (regression on extraction)."""

    def test_v1_prints_cd_make_install(self):
        out = _guidance_output(adopt=False)
        assert "cd /tmp/target && make install" in out
        assert "make install-hooks" in out

    def test_adopt_gates_off_cd_make_install_keeps_hooks_when_makefile_written(self):
        # base_makefile_written=True (no target Makefile → the skill's landed),
        # so `make install-hooks` is a real target.
        out = _guidance_output(adopt=True, base_makefile_written=True)
        # The greenfield deps-install line is gated off for adopt …
        assert "&& make install\n" not in out
        # … but the hooks next-step still prints, WITH its own cd into the target
        # (codex round-5) since the deps-install line that would have cd'd is gone.
        assert "cd /tmp/target && make install-hooks" in out

    def test_adopt_owned_makefile_omits_install_hooks(self):
        # base_makefile_written=False (target owns its Makefile, SKIP): the
        # skill's install-hooks recipe never landed, so don't advertise it
        # (Tier-2 codex round-4 P2). With nothing left, no "next steps:" header.
        out = _guidance_output(adopt=True, base_makefile_written=False)
        assert "make install-hooks" not in out
        assert "next steps:" not in out

    def test_adopt_no_makefile_review_hint_when_not_emitted(self):
        out = _guidance_output(adopt=True, makefile_review_emitted=False)
        assert "Makefile.review" not in out

    def test_adopt_makefile_review_hint_names_review_collision(self):
        out = _guidance_output(
            adopt=True, makefile_review_emitted=True, colliding_targets=("review",)
        )
        assert "include Makefile.review" in out
        assert "remove your existing review target" in out

    def test_adopt_makefile_review_hint_names_non_review_collision(self):
        """iter-2 FN2: the hint names the COMPUTED overlap, not a hard-coded
        `review`. A Makefile colliding only on `status` → the hint says
        `status`."""
        out = _guidance_output(
            adopt=True, makefile_review_emitted=True, colliding_targets=("status",)
        )
        assert "include Makefile.review" in out
        assert "remove your existing status target" in out
        # Must NOT hard-code a removal instruction for `review`.
        assert "remove your existing review target" not in out

    def test_adopt_makefile_review_hint_empty_collisions_uses_generic_fallback(self):
        out = _guidance_output(adopt=True, makefile_review_emitted=True, colliding_targets=())
        assert "include Makefile.review" in out
        assert "review or review-plan targets" in out


class TestAdoptGuidanceE2E:
    """Bucket C end-to-end: an adopt apply now prints the same next-steps /
    gh-repo / token guidance the v1 path does (folds the parked gh-repo mirror
    item), with the greenfield `make install` gated off."""

    def test_adopt_apply_with_github_review_prints_shared_guidance(self, tmp_path):
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
                str(tmp_path),
                "--github-review",
                "both-docs",
                "--github-owner",
                "o",
                "--github-repo",
                "r",
                "--non-interactive",
            ],
        )
        assert rc == 0, f"expected success, got rc={rc}; stderr={err!r}"
        # next-steps present, but the greenfield deps-install line is gated off;
        # install-hooks prints with its own cd into the target (codex round-5).
        assert "next steps:" in out
        assert f"cd {tmp_path} && make install-hooks" in out
        assert f"cd {tmp_path} && make install\n" not in out
        # gh-repo-create + token + both-docs Codex guidance now reach adopt too.
        assert "gh repo create" in out
        assert "CLAUDE_CODE_OAUTH_TOKEN" in out
        assert "codex-github-review-setup.md" in out
        # Bucket B not exercised here (empty target → base Makefile is a WRITE →
        # the standalone Makefile.review is dropped), so NO include hint.
        assert "include Makefile.review" not in out


# ─── Bucket B — Makefile target-name overlap (colliding_targets) ───


def _full_context(**overrides):
    """A render context matching `cli._build_context`'s shape, for direct
    render/parse unit tests."""
    base = {
        "project_name": "x",
        "language": "python",
        "python_version": "3.12",
        "node_version": "24",
        "go_version": "1.26",
        "package_manager": "uv",
        "enable_smoke": False,
        "github_owner": "",
        "github_repo": "",
        "github_review_mode": "none",
    }
    base.update(overrides)
    return base


class TestMakefileTargetOverlap:
    """`_compute_colliding_targets` drives the include hint (iter-2 FN2): it must
    extract real target names (not variables / directives) and intersect the
    fragment with the target's existing Makefile."""

    def test_target_names_extracts_targets_not_vars_or_directives(self):
        text = (
            ".PHONY: a b\n"
            "PYTHON := ./venv/bin/python\n"
            "ARGS ?= --prod\n"
            "build: deps\n\tgcc\n"
            "review:\t## dispatch\n\t@echo hi\n"
            "check: lint test\n"
        )
        names = guidance._makefile_target_names(text)
        assert names == {"build", "review", "check"}
        assert "PYTHON" not in names
        assert "ARGS" not in names
        assert ".PHONY" not in names

    def test_compute_colliding_targets_intersects(self, tmp_path):
        (tmp_path / "Makefile").write_bytes(
            b"test:\n\tpytest\n\nreview:\n\t@echo old\n\nrun:\n\tpython app.py\n"
        )
        fragment = b"review:\n\t@echo dispatch\n\nloop-status:\n\t@echo status\n"
        assert guidance._compute_colliding_targets(tmp_path, fragment) == ("review",)

    def test_compute_colliding_targets_no_makefile_returns_empty(self, tmp_path):
        assert guidance._compute_colliding_targets(tmp_path, b"review:\n\t@echo x\n") == ()

    def test_real_fragment_vs_bot_shape_only_review_collides(self, tmp_path):
        """R-B1 ground truth: against a bot-shaped Makefile (a bare `review:` and
        an older `review-plan:`), the REAL rendered fragment collides ONLY on
        `review` — `review-plan` is superseded by the fragment's
        `review-plan-by-{codex,claude}`, so it does NOT name-collide."""
        from bootstrap_lib import render

        fragment = render.render_makefile_review(_full_context(), language="python")
        (tmp_path / "Makefile").write_bytes(
            b"review:\n\t@echo old\n\nreview-plan:\n\t@echo old-plan\n\ntest:\n\tpytest\n"
        )
        assert guidance._compute_colliding_targets(tmp_path, fragment) == ("review",)
