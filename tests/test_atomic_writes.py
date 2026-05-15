from __future__ import annotations

from bootstrap_lib import io as bio


def test_atomic_write_creates_then_renames(tmp_path):
    target = tmp_path / "Makefile"
    bio.atomic_write(target, b"hello\n")
    assert target.read_bytes() == b"hello\n"
    # After successful write, no .bootstrap-tmp residue
    leftover = list(tmp_path.rglob("*.bootstrap-tmp"))
    assert leftover == []


def test_atomic_write_creates_parents(tmp_path):
    target = tmp_path / "deep" / "nested" / "path" / "file.txt"
    bio.atomic_write(target, b"content")
    assert target.exists()
    assert target.read_text() == "content"


def test_atomic_write_uses_tmp_suffix(tmp_path, monkeypatch):
    """Verify the tmp path is actually `<target>.bootstrap-tmp` during the
    write window."""
    target = tmp_path / "Makefile"
    seen_tmp_paths = []
    real_replace = bio.os.replace

    def spy_replace(src, dst):
        seen_tmp_paths.append(str(src))
        real_replace(src, dst)

    monkeypatch.setattr(bio.os, "replace", spy_replace)
    bio.atomic_write(target, b"x")
    assert seen_tmp_paths == [str(target) + bio.TMP_SUFFIX]


def test_cleanup_tmp_artifacts(tmp_path):
    # Create some stale bootstrap-tmp files + one regular file
    (tmp_path / "Makefile.bootstrap-tmp").write_text("stale")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "config.yaml.bootstrap-tmp").write_text("stale2")
    (tmp_path / "real.txt").write_text("keep")

    bio.cleanup_tmp_artifacts(tmp_path)

    assert not (tmp_path / "Makefile.bootstrap-tmp").exists()
    assert not (tmp_path / "nested" / "config.yaml.bootstrap-tmp").exists()
    assert (tmp_path / "real.txt").exists()


def test_atomic_write_overwrites_existing_target(tmp_path):
    """Codex iter-23 P2#2: os.replace (vs os.rename) must succeed when the
    target already exists — proves --overwrite-existing works cross-platform."""
    target = tmp_path / "existing"
    target.write_bytes(b"old content")
    bio.atomic_write(target, b"new content")
    assert target.read_bytes() == b"new content"
    leftover = list(tmp_path.rglob("*.bootstrap-tmp"))
    assert leftover == []


def test_atomic_write_cleans_tmp_on_write_failure(tmp_path, monkeypatch):
    """Codex iter-23 P2#1: if write/fsync/replace raises, the orphan
    .bootstrap-tmp must NOT be left on disk. The signal-handler cleanup
    can't see it after `_pending_tmp.discard`, so the inline finally must
    unlink it."""
    target = tmp_path / "doomed"

    # Make os.fsync raise to simulate mid-write failure
    def boom(_fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(bio.os, "fsync", boom)
    with __import__("pytest").raises(OSError):
        bio.atomic_write(target, b"will fail")
    leftover = list(tmp_path.rglob("*.bootstrap-tmp"))
    assert leftover == [], f"orphan tmp file left on disk: {leftover}"


def test_concurrent_read_sees_old_or_new_never_partial(tmp_path):
    """Smoke check: atomic_write is a single os.rename, which is atomic on the
    same filesystem. The test below is a structural sanity check — a true
    concurrency test would need threads/processes and timing. We assert the
    weaker but still informative property: after the call returns, the file
    has the new content (not partial).
    """
    target = tmp_path / "data"
    target.write_text("old")
    bio.atomic_write(target, b"new-and-different")
    assert target.read_bytes() == b"new-and-different"
