"""Tests for the bootstrap CLI surface (argparse, slug validation, mode flags,
collision policy, github-owner/repo policy, restore-mode standalone).

Per Codex iter-10 finding #4: monkey-patch-dependent tests run IN-PROCESS by
calling bootstrap_lib.cli.main(argv). Subprocess tests live in
test_smoke_python_generated.py / test_sigterm_mid_apply.py / etc.
"""

from __future__ import annotations

import io as io_module
import subprocess
import sys
from pathlib import Path

import pytest

from bootstrap_lib import cli
from bootstrap_lib._flags import add_flags

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


def run_cli(argv):
    """Run cli.main(argv) in-process, capturing stdout/stderr."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = io_module.StringIO()
    sys.stderr = io_module.StringIO()
    try:
        rc = cli.main(list(argv))
    except SystemExit as e:
        rc = e.code
    finally:
        out = sys.stdout.getvalue()
        err = sys.stderr.getvalue()
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return rc, out, err


def test_every_flag_appears_in_help():
    """Closes Codex iter-10 finding #1: --help must show every documented flag."""
    import argparse

    parser = argparse.ArgumentParser(prog="bootstrap.py")
    add_flags(parser)
    help_text = parser.format_help()
    for flag in [
        "--dry-run",
        "--diff",
        "--apply",
        "--restore",
        "--language",
        "--project-name",
        "--out",
        "--github-review",
        "--github-owner",
        "--github-repo",
        "--overwrite-existing",
        "--enable-smoke",
        "--package-manager",
    ]:
        assert flag in help_text, f"{flag} missing from --help"


@pytest.mark.parametrize("language", ["python", "nodejs", "go"])
@pytest.mark.parametrize(
    "slug,valid",
    [
        ("valid-project", True),
        ("foo123", True),
        ("a", True),
        ("my-cool-app-2", True),
        ("My-Project", False),  # uppercase
        ("with spaces", False),
        ("../escape", False),
        ("foo/bar", False),
        ("", False),
        ("1starts-with-digit", False),
        ("_underscore", False),
    ],
)
def test_project_name_validation(tmp_path, slug, valid, language):
    rc, _out, err = run_cli(
        ["--apply", "--language", language, "--project-name", slug, "--out", str(tmp_path)]
    )
    if valid:
        assert rc == 0, err
    else:
        assert rc == 2, f"expected rejection for {slug!r}"
        # All slugs that the renderer would refuse should hit the slug guard,
        # not the github-owner/repo guard or render path. Empty -> argparse
        # treats as missing.
        if slug != "":
            assert "invalid project name" in err or "missing required" in err


def test_no_mode_flag_defaults_to_dry_run(tmp_path):
    """Closes Codex iter-15 finding #1."""
    target = tmp_path / "x"
    assert not target.exists()
    rc, out, err = run_cli(
        ["--language", "python", "--project-name", "test-x", "--out", str(target)]
    )
    assert rc == 0, err
    assert not target.exists(), "dry-run must not create --out"
    assert "dry-run:" in out


def test_apply_aborts_on_collision_without_flag(tmp_path):
    """Closes Codex iter-3 finding #1."""
    target = tmp_path / "proj"
    target.mkdir()
    (target / "Makefile").write_text("# pre-existing\n")
    rc, _out, err = run_cli(
        ["--apply", "--language", "python", "--project-name", "proj-x", "--out", str(target)]
    )
    assert rc == 2
    assert "collision detected" in err
    assert "--overwrite-existing" in err
    # Now with consent it should succeed
    rc, _out, err = run_cli(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "proj-x",
            "--out",
            str(target),
            "--overwrite-existing",
        ]
    )
    assert rc == 0, err


def test_diff_emits_unified_diff_no_writes(tmp_path, monkeypatch):
    """Closes Codex iter-7 finding #3."""
    import tempfile

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    target = tmp_path / "proj"
    target.mkdir()
    # Pre-existing file that will differ from rendered output
    (target / "Makefile").write_text("# wrong content\n")

    rc, out, _err = run_cli(
        ["--diff", "--language", "python", "--project-name", "proj-x", "--out", str(target)]
    )
    assert rc == 0
    assert "--- " in out
    assert "+++ " in out
    # No bootstrap-tmp artifacts
    leftover = list(target.rglob("*.bootstrap-tmp"))
    assert not leftover, leftover
    # No manifest in isolated TMPDIR
    manifests = list(tmp_path.glob("dev-project-setup-restore-*.json"))
    assert not manifests, "diff should not write a manifest"


def test_diff_does_not_create_missing_out(tmp_path):
    target = tmp_path / "nope"
    assert not target.exists()
    rc, _out, _err = run_cli(
        ["--diff", "--language", "python", "--project-name", "x", "--out", str(target)]
    )
    assert rc == 0
    assert not target.exists(), "diff must not create --out (Codex iter-2 finding #4)"


def test_github_review_owner_repo_required_when_not_none(tmp_path):
    """Closes Codex iter-13 finding #2."""
    # (a) mode=none without owner/repo: OK
    rc_a, _out, _err = run_cli(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(tmp_path / "a"),
        ]
    )
    assert rc_a == 0

    # (b) mode=claude without owner/repo: exit 2
    rc_b, _out, err_b = run_cli(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "y",
            "--out",
            str(tmp_path / "b"),
            "--github-review",
            "claude",
        ]
    )
    assert rc_b == 2
    assert "--github-owner" in err_b
    assert "--github-repo" in err_b

    # (c) mode=claude with owner/repo: OK
    rc_c, _out, _err = run_cli(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "z",
            "--out",
            str(tmp_path / "c"),
            "--github-review",
            "claude",
            "--github-owner",
            "test-owner",
            "--github-repo",
            "test-repo",
        ]
    )
    assert rc_c == 0


def test_restore_does_not_require_language_project_or_out(tmp_path):
    """Closes Codex iter-5 finding #1. Uses sys.executable not literal `python`
    (closes Codex iter-7 finding #1)."""
    # First do a real apply to produce a manifest
    target = tmp_path / "proj"
    rc, out, _err = run_cli(
        ["--apply", "--language", "python", "--project-name", "x", "--out", str(target)]
    )
    assert rc == 0
    # Extract manifest path from output
    manifest_line = [line for line in out.splitlines() if line.startswith("restore manifest:")]
    assert manifest_line
    manifest_p = manifest_line[0].split(":", 1)[1].strip()

    # Restore mode standalone: no other flags
    result = subprocess.run(
        [sys.executable, str(BOOTSTRAP_PY), "--restore", manifest_p],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    # Restore with render-only flags should be rejected
    target2 = tmp_path / "proj2"
    target2.mkdir()
    result_bad = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--restore",
            manifest_p,
            "--language",
            "python",
        ],
        capture_output=True,
        text=True,
    )
    assert result_bad.returncode != 0
    assert "not valid in restore mode" in result_bad.stderr


def test_target_root_not_created_when_manifest_write_fails(tmp_path, monkeypatch):
    """Codex iter-24 P1: a partial mkdir of `--out` without a durable
    manifest violates the recoverability contract. The fix removes the
    pre-manifest mkdir; this test asserts that if manifest_write raises,
    target_root is NOT left on disk."""
    from bootstrap_lib import manifest as manifest_module

    def boom(_m):
        raise OSError("simulated disk-full during manifest write")

    monkeypatch.setattr(manifest_module, "write_manifest", boom)

    target = tmp_path / "should-not-be-created"
    assert not target.exists()
    rc, _out, err = run_cli(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "test",
            "--out",
            str(target),
        ]
    )
    assert rc == 1
    assert "apply failed before manifest write" in err
    # The whole point of the fix: target_root must NOT have been created
    assert not target.exists(), (
        "target_root should not be created if manifest write fails — "
        "no rollback path was established"
    )


def test_partial_apply_failure_still_prints_restore_hint(tmp_path, monkeypatch):
    """Codex iter-22 P1: if _apply_writes raises mid-write, the user must
    still see the manifest path + restore hint so they can roll back the
    partial state."""
    from bootstrap_lib import io as bio_module

    call_count = {"n": 0}
    original_atomic_write = bio_module.atomic_write

    def flaky_write(target_path, content_bytes):
        call_count["n"] += 1
        if call_count["n"] >= 3:
            raise OSError("simulated mid-apply disk failure")
        return original_atomic_write(target_path, content_bytes)

    monkeypatch.setattr(bio_module, "atomic_write", flaky_write)

    target = tmp_path / "partial"
    rc, _out, err = run_cli(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "partial",
            "--out",
            str(target),
        ]
    )
    assert rc == 1
    assert "apply failed mid-write" in err
    assert "restore manifest:" in err
    assert "to rollback:" in err


def test_restore_returns_nonzero_when_path_safety_rejects(tmp_path, monkeypatch):
    """Codex iter-22 P2: a manifest that aborts in restore_from_manifest
    (e.g. path-safety violation) must surface as a non-zero CLI exit."""
    import tempfile as _tempfile

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(_tempfile, "tempdir", str(tmp_path))

    # Hand-craft a manifest with an absolute-path entry (path-safety violation)
    import base64
    import hashlib
    import json as _json

    target = tmp_path / "proj"
    target.mkdir()
    manifest_path = tmp_path / "evil-manifest.json"
    payload = {
        "created_at": "2026-05-15T00:00:00Z",
        "target_root": str(target),
        "github_review_mode": "none",
        "entries": [
            {
                "path": "/tmp/outside.txt",
                "existed_before": False,
                "sha256_before": None,
                "content_before_b64": None,
                "mode_before": None,
                "action_planned": "create",
                "sha256_after": hashlib.sha256(b"x").hexdigest(),
                "mode_after": 0o644,
            }
        ],
        "created_directories": [],
    }
    manifest_path.write_text(_json.dumps(payload))
    rc, _out, err = run_cli(["--restore", str(manifest_path)])
    assert rc != 0
    assert "REJECT" in err or "rejected" in err
    _ = base64  # keep import alive in case base64 referenced from sibling tests


def test_apply_prints_oauth_token_hint_for_opt_in_modes(tmp_path):
    """When --github-review is claude or both-docs, the next-steps printout
    must surface the CLAUDE_CODE_OAUTH_TOKEN secret-setup step. Without
    that hint, users push the project to GitHub without the secret and
    silently get no claude[bot] reviews."""
    target = tmp_path / "proj"
    rc, out, _err = run_cli(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "test",
            "--out",
            str(target),
            "--github-review",
            "claude",
            "--github-owner",
            "x",
            "--github-repo",
            "y",
        ]
    )
    assert rc == 0
    assert "CLAUDE_CODE_OAUTH_TOKEN" in out
    assert "claude setup-token" in out


def test_apply_omits_oauth_token_hint_in_none_mode(tmp_path):
    """In default --github-review=none, no claude-review workflow is
    emitted, so the secret-setup hint must NOT appear (would only confuse
    the user about a workflow they don't have)."""
    target = tmp_path / "proj"
    rc, out, _err = run_cli(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "test",
            "--out",
            str(target),
        ]
    )
    assert rc == 0
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in out


def test_overwrite_existing_alone_is_fine_on_empty_target(tmp_path):
    target = tmp_path / "empty"
    rc, _out, _err = run_cli(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(target),
            "--overwrite-existing",
        ]
    )
    assert rc == 0


# ──────────────────────────────────────────────────────────────────────
# --package-manager flag (PR #6 Bucket A — closes plan iter-3 #2 +
# Codex iter-3 #2 + Claude iter-2 #1/#6 + Codex Tier-2 #6)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("language", ["nodejs", "go"])
def test_package_manager_rejected_for_non_python_language(tmp_path, language):
    """Closes Codex iter-3 #2: help text + cli.py validation must agree.

    Help text says "Only valid with --language=python." — cli.py rejects
    the combination with a clear error message.
    """
    target = tmp_path / "x"
    rc, _out, err = run_cli(
        [
            "--apply",
            "--language",
            language,
            "--project-name",
            "x",
            "--out",
            str(target),
            "--package-manager",
            "uv",
        ]
    )
    assert rc == 2
    assert "--package-manager only valid with --language=python" in err


def test_package_manager_rejected_in_restore_mode(tmp_path):
    """Closes Codex iter-3 #2 (restore branch): --package-manager must be
    in _resolve_mode's restore-mode invalid-flag list. Symmetric with
    --language, --out, --apply, etc."""
    manifest_p = tmp_path / "manifest.json"
    manifest_p.write_text("{}")  # invalid manifest but we should fail on the flag check first
    rc, _out, err = run_cli(["--restore", str(manifest_p), "--package-manager", "uv"])
    assert rc == 2
    assert "--package-manager" in err
    assert "not valid in restore mode" in err


@pytest.mark.parametrize("github_review", ["none", "claude", "both-docs"])
def test_package_manager_valid_with_python_across_github_modes(tmp_path, github_review):
    """`--package-manager=uv` valid combinations across all 3 github-review modes."""
    target = tmp_path / "x"
    argv = [
        "--apply",
        "--language",
        "python",
        "--project-name",
        "x",
        "--out",
        str(target),
        "--package-manager",
        "uv",
        "--github-review",
        github_review,
    ]
    if github_review != "none":
        argv += ["--github-owner", "v3rmus89", "--github-repo", "test"]
    rc, _out, err = run_cli(argv)
    assert rc == 0, err


def test_package_manager_absence_greenfield_python_no_advisory(tmp_path):
    """`--package-manager` absence with greenfield Python → no advisory printed.

    Closes Claude iter-2 #1: greenfield default is unsurprising, no advisory.
    """
    target = tmp_path / "new-project"  # doesn't exist
    rc, _out, err = run_cli(
        [
            "--dry-run",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(target),
        ]
    )
    assert rc == 0
    # No "info:" advisory line.
    assert "info: detected" not in err
    assert "defaulting package_manager" not in err


def test_package_manager_absence_existing_uv_marker_prints_advisory(tmp_path):
    """`--package-manager` absence with existing uv-marker dir → context has
    `"uv"` + stderr contains positive-marker advisory."""
    target = tmp_path / "existing-uv"
    target.mkdir()
    (target / "uv.lock").write_text("")
    rc, _out, err = run_cli(
        [
            "--dry-run",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(target),
        ]
    )
    assert rc == 0
    assert "info: detected package_manager='uv'" in err
    assert "uv.lock" in err  # the reason string


def test_package_manager_absence_existing_pip_marker_prints_advisory(tmp_path):
    """`--package-manager` absence with existing pip-marker dir → context has
    `"pip"` + stderr advisory mentions pip."""
    target = tmp_path / "existing-pip"
    target.mkdir()
    (target / "requirements.txt").write_text("")
    rc, _out, err = run_cli(
        [
            "--dry-run",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(target),
        ]
    )
    assert rc == 0
    assert "info: detected package_manager='pip'" in err
    assert "requirements.txt" in err


def test_package_manager_absence_ambiguous_pyproject_prints_override_hint(tmp_path):
    """`--package-manager` absence with ambiguous-pyproject dir → context has
    `"uv"` (CLI default) + stderr contains the explicit override-hint advisory.

    Closes Claude iter-2 #1: this is the test that proves the ambiguous-specific
    advisory actually fires. Without rule 6 returning manager=None + the CLI's
    `or "uv"` defaulting, the override-hint branch was logically dead.
    """
    target = tmp_path / "ambiguous"
    target.mkdir()
    (target / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n')
    rc, _out, err = run_cli(
        [
            "--dry-run",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(target),
        ]
    )
    assert rc == 0
    assert "pass --package-manager=pip to override" in err
    assert "defaulting package_manager='uv'" in err


def test_explicit_pip_on_ambiguous_pyproject_prints_no_advisory(tmp_path):
    """`--package-manager=pip` explicit on ambiguous-pyproject dir → context has
    `"pip"` + no advisory (explicit flag = no advisory rule)."""
    target = tmp_path / "ambiguous"
    target.mkdir()
    (target / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n')
    rc, _out, err = run_cli(
        [
            "--dry-run",
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(target),
            "--package-manager",
            "pip",
        ]
    )
    assert rc == 0
    # No advisory of any kind because user was explicit.
    assert "info:" not in err
    assert "defaulting" not in err


def test_build_context_stays_pure(tmp_path):
    """`_build_context` accepts a `package_manager` kwarg but does NO filesystem I/O.

    Closes Claude iter-2 #6: detection lives in `main()`/`_resolve_package_manager`,
    NOT inside `_build_context`. Existing tests that call `_build_context` with
    synthetic args (no real --out filesystem) must still work.
    """
    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            "/nonexistent/path/that/does/not/exist",
        ]
    )
    # Calling _build_context without package_manager should not raise and
    # should NOT touch the filesystem.
    context = cli._build_context(args)
    assert context["language"] == "python"
    assert context["package_manager"] is None  # kwarg default


def test_build_context_respects_package_manager_kwarg(tmp_path):
    """`_build_context(args, package_manager="uv")` puts uv in the context."""
    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "--language",
            "python",
            "--project-name",
            "x",
            "--out",
            str(tmp_path),
        ]
    )
    context = cli._build_context(args, package_manager="uv")
    assert context["package_manager"] == "uv"


def test_resolve_package_manager_for_non_python_returns_none(tmp_path):
    """For non-Python languages, no detection runs and no manager is resolved."""
    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "--language",
            "nodejs",
            "--project-name",
            "x",
            "--out",
            str(tmp_path),
        ]
    )
    effective_pm, detected = cli._resolve_package_manager(args)
    assert effective_pm is None
    assert detected is None
