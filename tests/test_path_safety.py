"""Path-safety tests at both layers (renderer and CLI).

Closes Codex iter-7 finding #4 + iter-8 finding #2: the path-safety check
runs at TWO layers (inside render.render_all AND in
apply_pipeline._cli_layer_path_safety, which cli.main calls). The test monkey-patches render_all to BYPASS the renderer-layer
check, proving the CLI-layer check is the actual safety boundary.
"""

from __future__ import annotations

import io as io_module
import sys

import pytest

from bootstrap_lib import cli, paths, render


def test_renderer_layer_rejects_relative_traversal():
    """First-tier defense: validate_target_path called from inside render_all."""
    with pytest.raises(paths.PathSafetyError):
        paths.validate_target_path("/tmp/__validate__", "../escape.txt")


def test_renderer_layer_rejects_absolute_path():
    with pytest.raises(paths.PathSafetyError):
        paths.validate_target_path("/tmp/__validate__", "/etc/passwd")


def test_renderer_layer_rejects_symlink_escape(tmp_path):
    """Closes Codex iter-3 finding #3."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not yours")

    target_root = tmp_path / "target"
    target_root.mkdir()
    (target_root / "link").symlink_to(outside)

    with pytest.raises(paths.PathSafetyError):
        paths.validate_target_path(target_root, "link/secret.txt")


def test_cli_layer_path_safety_catches_bypass(tmp_path, monkeypatch):
    """Closes Codex iter-8 finding #2.

    Monkey-patch render.render_all to return an unsafe path — bypassing the
    renderer-layer guard. The CLI-layer guard must still fire.
    """
    poisoned_output = {"../escape.txt": b"malicious"}
    monkeypatch.setattr(render, "render_all", lambda *a, **kw: poisoned_output)

    target = tmp_path / "proj"
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = io_module.StringIO()
    sys.stderr = io_module.StringIO()
    try:
        rc = cli.main(
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
        err = sys.stderr.getvalue()
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    assert rc == 2
    assert "path-safety" in err
    # No manifest should have been written, no files materialised
    leftover = list(target.rglob("*")) if target.exists() else []
    assert all(not p.is_file() for p in leftover), "no files should have been written"


def test_validate_target_path_returns_resolved_path(tmp_path):
    target_root = tmp_path / "proj"
    target_root.mkdir()
    result = paths.validate_target_path(target_root, "Makefile")
    assert str(result).startswith(str(target_root.resolve()))
