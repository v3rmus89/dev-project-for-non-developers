"""Restore behaviour — 10 subtests covering the conservative restore decision
table (Codex iter-13 finding #1).

Subtests:
(a) overwritten files restored
(b) created files removed
(c) unlisted files ignored
(d) user-modified created file preserved (SKIP)
(d') user-modified overwritten file preserved (SKIP) — closes iter-4 finding #1
(e) path-safety: relative traversal rejected — closes iter-2 finding #1
(f) path-safety: absolute path rejected
(g) path-safety: symlink escape rejected — closes iter-3 finding #3
(h) created directories removed — closes iter-12 finding #1
(i) created directories with user content preserved
(j) file mode restored — closes iter-12 finding #2
"""

from __future__ import annotations

import base64
import hashlib
import os

from bootstrap_lib import manifest as manifest_mod


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _make_manifest(target_root, entries, created_directories=None):
    return manifest_mod.Manifest(
        target_root=str(target_root),
        github_review_mode="none",
        entries=entries,
        created_directories=created_directories or [],
    )


def test_a_overwritten_files_restored(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    pre_a = b"# original A\n"
    pre_b = b"# original B\n"
    (target / "a.txt").write_bytes(pre_a)
    (target / "b.txt").write_bytes(pre_b)

    new_a = b"# new A\n"
    new_b = b"# new B\n"
    entries = [
        {
            "path": "a.txt",
            "existed_before": True,
            "sha256_before": _sha256(pre_a),
            "content_before_b64": _b64(pre_a),
            "mode_before": 0o644,
            "action_planned": "overwrite",
            "sha256_after": _sha256(new_a),
            "mode_after": 0o644,
        },
        {
            "path": "b.txt",
            "existed_before": True,
            "sha256_before": _sha256(pre_b),
            "content_before_b64": _b64(pre_b),
            "mode_before": 0o644,
            "action_planned": "overwrite",
            "sha256_after": _sha256(new_b),
            "mode_after": 0o644,
        },
    ]
    # Simulate post-apply state
    (target / "a.txt").write_bytes(new_a)
    (target / "b.txt").write_bytes(new_b)

    m = _make_manifest(target, entries)
    n_r, n_rm, n_sk, n_rj = manifest_mod.restore_from_manifest(m)
    assert (n_r, n_rm, n_sk, n_rj) == (2, 0, 0, 0)
    assert (target / "a.txt").read_bytes() == pre_a
    assert (target / "b.txt").read_bytes() == pre_b
    # Codex iter-21 P1: restore must be crash-safe (atomic_write); after a
    # clean run there are no .bootstrap-tmp artifacts under target.
    leftover = list(target.rglob("*.bootstrap-tmp"))
    assert leftover == [], leftover


def test_b_created_files_removed(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    new_a = b"# new A\n"
    new_b = b"# new B\n"
    (target / "a.txt").write_bytes(new_a)
    (target / "b.txt").write_bytes(new_b)

    entries = [
        {
            "path": "a.txt",
            "existed_before": False,
            "sha256_before": None,
            "content_before_b64": None,
            "mode_before": None,
            "action_planned": "create",
            "sha256_after": _sha256(new_a),
            "mode_after": 0o644,
        },
        {
            "path": "b.txt",
            "existed_before": False,
            "sha256_before": None,
            "content_before_b64": None,
            "mode_before": None,
            "action_planned": "create",
            "sha256_after": _sha256(new_b),
            "mode_after": 0o644,
        },
    ]
    m = _make_manifest(target, entries)
    n_r, n_rm, n_sk, n_rj = manifest_mod.restore_from_manifest(m)
    assert (n_r, n_rm, n_sk, n_rj) == (0, 2, 0, 0)
    assert not (target / "a.txt").exists()
    assert not (target / "b.txt").exists()


def test_c_unlisted_files_ignored(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    (target / "manifest-tracked.txt").write_bytes(b"tracked")
    (target / "untracked.txt").write_bytes(b"user content")

    entries = [
        {
            "path": "manifest-tracked.txt",
            "existed_before": False,
            "sha256_before": None,
            "content_before_b64": None,
            "mode_before": None,
            "action_planned": "create",
            "sha256_after": _sha256(b"tracked"),
            "mode_after": 0o644,
        },
    ]
    m = _make_manifest(target, entries)
    manifest_mod.restore_from_manifest(m)
    # untracked.txt must still exist
    assert (target / "untracked.txt").exists()
    assert (target / "untracked.txt").read_bytes() == b"user content"


def test_d_user_modified_created_file_preserved(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    apply_content = b"# bootstrap output\n"
    (target / "a.txt").write_bytes(apply_content)
    # User then edits it
    user_edit = b"# user wrote over it\n"
    (target / "a.txt").write_bytes(user_edit)

    entries = [
        {
            "path": "a.txt",
            "existed_before": False,
            "sha256_before": None,
            "content_before_b64": None,
            "mode_before": None,
            "action_planned": "create",
            "sha256_after": _sha256(apply_content),
            "mode_after": 0o644,
        },
    ]
    m = _make_manifest(target, entries)
    n_r, n_rm, n_sk, n_rj = manifest_mod.restore_from_manifest(m)
    assert (n_r, n_rm, n_sk, n_rj) == (0, 0, 1, 0)
    # File preserved
    assert (target / "a.txt").read_bytes() == user_edit


def test_d_prime_user_modified_overwritten_file_preserved(tmp_path):
    """Codex iter-4 finding #1 — symmetric protection."""
    target = tmp_path / "proj"
    target.mkdir()
    pre = b"# original\n"
    apply_content = b"# bootstrap overwrote\n"
    (target / "y.txt").write_bytes(apply_content)
    # User then edits
    user_edit = b"# user wrote over it\n"
    (target / "y.txt").write_bytes(user_edit)

    entries = [
        {
            "path": "y.txt",
            "existed_before": True,
            "sha256_before": _sha256(pre),
            "content_before_b64": _b64(pre),
            "mode_before": 0o644,
            "action_planned": "overwrite",
            "sha256_after": _sha256(apply_content),
            "mode_after": 0o644,
        },
    ]
    m = _make_manifest(target, entries)
    _r, _rm, n_sk, _rj = manifest_mod.restore_from_manifest(m)
    assert n_sk == 1
    assert (target / "y.txt").read_bytes() == user_edit


def test_d_double_prime_user_deleted_overwritten_file_not_restored(tmp_path):
    """Codex iter-20 P1: an overwritten file that's missing at restore time
    falls into 'current SHA matches neither' — conservative rule says SKIP,
    not restore. Prevents restore from undoing a user `rm`."""
    target = tmp_path / "proj"
    target.mkdir()
    pre = b"# original\n"
    apply_content = b"# bootstrap overwrote\n"
    f = target / "y.txt"
    # Simulate: existed before apply, was overwritten, then user deleted
    # Don't write apply_content; just leave file absent.

    entries = [
        {
            "path": "y.txt",
            "existed_before": True,
            "sha256_before": _sha256(pre),
            "content_before_b64": _b64(pre),
            "mode_before": 0o644,
            "action_planned": "overwrite",
            "sha256_after": _sha256(apply_content),
            "mode_after": 0o644,
        },
    ]
    m = _make_manifest(target, entries)
    _r, _rm, n_sk, _rj = manifest_mod.restore_from_manifest(m)
    assert n_sk == 1
    # File MUST NOT come back — user's deletion is preserved
    assert not f.exists()


def test_e_path_safety_relative_traversal_rejected(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"sensitive")

    entries = [
        {
            "path": "../outside.txt",
            "existed_before": True,
            "sha256_before": _sha256(b"sensitive"),
            "content_before_b64": _b64(b"sensitive"),
            "mode_before": 0o644,
            "action_planned": "overwrite",
            "sha256_after": _sha256(b"new"),
            "mode_after": 0o644,
        },
    ]
    m = _make_manifest(target, entries)
    _r, _rm, _sk, n_rj = manifest_mod.restore_from_manifest(m)
    assert n_rj >= 1
    # outside file MUST be untouched
    assert outside.read_bytes() == b"sensitive"


def test_f_path_safety_absolute_path_rejected(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    entries = [
        {
            "path": "/tmp/outside.txt",
            "existed_before": False,
            "sha256_before": None,
            "content_before_b64": None,
            "mode_before": None,
            "action_planned": "create",
            "sha256_after": "deadbeef" * 8,
            "mode_after": 0o644,
        },
    ]
    m = _make_manifest(target, entries)
    _r, _rm, _sk, n_rj = manifest_mod.restore_from_manifest(m)
    assert n_rj >= 1


def test_g_path_safety_symlink_escape_rejected(tmp_path):
    """Codex iter-3 finding #3."""
    target = tmp_path / "proj"
    target.mkdir()
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    (outside / "file.txt").write_bytes(b"sensitive")
    (target / "link").symlink_to(outside)

    entries = [
        {
            "path": "link/file.txt",
            "existed_before": True,
            "sha256_before": _sha256(b"sensitive"),
            "content_before_b64": _b64(b"sensitive"),
            "mode_before": 0o644,
            "action_planned": "overwrite",
            "sha256_after": _sha256(b"new"),
            "mode_after": 0o644,
        },
    ]
    m = _make_manifest(target, entries)
    _r, _rm, _sk, n_rj = manifest_mod.restore_from_manifest(m)
    assert n_rj >= 1
    assert (outside / "file.txt").read_bytes() == b"sensitive"


def test_h_created_directories_removed(tmp_path):
    """Codex iter-12 finding #1: byte-AND-tree-identical rollback."""
    target = tmp_path / "greenfield"
    target.mkdir()
    # Apply created these nested dirs + files
    (target / ".github" / "workflows").mkdir(parents=True)
    (target / ".github" / "workflows" / "ci.yml").write_bytes(b"workflow")
    (target / "docs" / "plans").mkdir(parents=True)
    (target / "docs" / "plans" / "README.md").write_bytes(b"plans")
    (target / "scripts").mkdir()
    (target / "scripts" / "runner.py").write_bytes(b"runner")

    entries = [
        {
            "path": ".github/workflows/ci.yml",
            "existed_before": False,
            "sha256_before": None,
            "content_before_b64": None,
            "mode_before": None,
            "action_planned": "create",
            "sha256_after": _sha256(b"workflow"),
            "mode_after": 0o644,
        },
        {
            "path": "docs/plans/README.md",
            "existed_before": False,
            "sha256_before": None,
            "content_before_b64": None,
            "mode_before": None,
            "action_planned": "create",
            "sha256_after": _sha256(b"plans"),
            "mode_after": 0o644,
        },
        {
            "path": "scripts/runner.py",
            "existed_before": False,
            "sha256_before": None,
            "content_before_b64": None,
            "mode_before": None,
            "action_planned": "create",
            "sha256_after": _sha256(b"runner"),
            "mode_after": 0o644,
        },
    ]
    m = _make_manifest(
        target,
        entries,
        created_directories=[".github", ".github/workflows", "docs", "docs/plans", "scripts"],
    )
    manifest_mod.restore_from_manifest(m)
    # Tree should be empty (files removed AND parent dirs removed)
    assert list(target.iterdir()) == []


def test_i_created_dirs_with_user_content_preserved(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    (target / "scripts").mkdir()
    (target / "scripts" / "manifest-file.py").write_bytes(b"managed")
    (target / "scripts" / "user-file.txt").write_bytes(b"user content")

    entries = [
        {
            "path": "scripts/manifest-file.py",
            "existed_before": False,
            "sha256_before": None,
            "content_before_b64": None,
            "mode_before": None,
            "action_planned": "create",
            "sha256_after": _sha256(b"managed"),
            "mode_after": 0o644,
        }
    ]
    m = _make_manifest(target, entries, created_directories=["scripts"])
    manifest_mod.restore_from_manifest(m)
    assert (target / "scripts").exists()  # not deleted (non-empty)
    assert (target / "scripts" / "user-file.txt").exists()
    assert not (target / "scripts" / "manifest-file.py").exists()


def test_j_file_mode_restored(tmp_path):
    """Codex iter-12 finding #2: 0o644 -> apply made it 0o755 -> restore returns to 0o644."""
    target = tmp_path / "proj"
    target.mkdir()
    pre = b"# original\n"
    apply_content = b"# bootstrap overwrote\n"
    f = target / "scripts" / "runner.sh"
    f.parent.mkdir()
    f.write_bytes(pre)
    os.chmod(f, 0o644)
    # Simulate apply
    f.write_bytes(apply_content)
    os.chmod(f, 0o755)

    entries = [
        {
            "path": "scripts/runner.sh",
            "existed_before": True,
            "sha256_before": _sha256(pre),
            "content_before_b64": _b64(pre),
            "mode_before": 0o644,
            "action_planned": "overwrite",
            "sha256_after": _sha256(apply_content),
            "mode_after": 0o755,
        }
    ]
    m = _make_manifest(target, entries)
    manifest_mod.restore_from_manifest(m)
    assert f.read_bytes() == pre
    assert (os.stat(f).st_mode & 0o777) == 0o644
