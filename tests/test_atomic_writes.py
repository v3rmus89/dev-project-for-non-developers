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
    real_rename = bio.os.rename

    def spy_rename(src, dst):
        seen_tmp_paths.append(str(src))
        real_rename(src, dst)

    monkeypatch.setattr(bio.os, "rename", spy_rename)
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
