"""Manifest round-trip + mode round-trip tests."""

from __future__ import annotations

import base64
import hashlib
import json

from bootstrap_lib import manifest as manifest_mod


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_round_trip_basic(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    target_root = tmp_path / "proj"
    target_root.mkdir()
    (target_root / "Makefile").write_text("# pre-existing\n")

    planned = {
        "Makefile": b"# new content\n",
        "scripts/run-with-clean-env.py": b"#!/usr/bin/env python3\nprint('hi')\n",
        "tests/test_smoke.py": b"def test_x(): assert True\n",
    }
    entries, created_dirs = manifest_mod.plan_entries(target_root, planned)

    m = manifest_mod.Manifest(
        target_root=str(target_root),
        github_review_mode="none",
        entries=entries,
        created_directories=created_dirs,
    )
    path = manifest_mod.write_manifest(m)
    assert path.exists()
    # The manifest path lives under the injected TMPDIR
    assert str(path).startswith(str(tmp_path))

    loaded = manifest_mod.load_manifest(path)
    assert loaded.target_root == str(target_root)
    assert loaded.github_review_mode == "none"
    assert loaded.entries == entries
    assert loaded.created_directories == created_dirs


def test_sha256_recomputes(tmp_path):
    target_root = tmp_path / "proj"
    target_root.mkdir()
    content = b"# fresh\n"
    planned = {"Makefile": content}
    entries, _ = manifest_mod.plan_entries(target_root, planned)
    assert entries[0]["sha256_after"] == _sha256(content)
    assert entries[0]["existed_before"] is False


def test_content_b64_round_trip(tmp_path):
    target_root = tmp_path / "proj"
    target_root.mkdir()
    pre_existing = b"\x00\x01\x02binary\xff"
    (target_root / "data.bin").write_bytes(pre_existing)
    planned = {"data.bin": b"replacement"}
    entries, _ = manifest_mod.plan_entries(target_root, planned)
    decoded = base64.b64decode(entries[0]["content_before_b64"])
    assert decoded == pre_existing
    assert entries[0]["existed_before"] is True
    assert entries[0]["sha256_before"] == _sha256(pre_existing)


def test_mode_round_trip_0755(tmp_path, monkeypatch):
    """Codex iter-12 finding #2 + iter-15 finding #3."""
    import tempfile

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    target_root = tmp_path / "proj"
    target_root.mkdir()
    planned = {"scripts/run-with-clean-env.py": b"#!/usr/bin/env python3\n"}
    entries, _ = manifest_mod.plan_entries(target_root, planned)
    assert entries[0]["mode_after"] == 0o755
    # Round-trip through json
    m = manifest_mod.Manifest(
        target_root=str(target_root),
        github_review_mode="none",
        entries=entries,
        created_directories=[],
    )
    path = manifest_mod.write_manifest(m)
    raw = json.loads(path.read_text())
    # JSON has no octal literal — stored as decimal int 493
    assert raw["entries"][0]["mode_after"] == 493
    loaded = manifest_mod.load_manifest(path)
    assert loaded.entries[0]["mode_after"] == 0o755


def test_created_directories_listed(tmp_path):
    """Codex iter-12 finding #1."""
    target_root = tmp_path / "greenfield"
    planned = {
        "Makefile": b"x",
        "scripts/runner.sh": b"y",
        ".github/workflows/ci.yml": b"z",
        "docs/plans/README.md": b"q",
    }
    _entries_unused, created_dirs = manifest_mod.plan_entries(target_root, planned)
    # Expected: scripts, .github, .github/workflows, docs, docs/plans
    expected = {"scripts", ".github", ".github/workflows", "docs", "docs/plans"}
    assert set(created_dirs) == expected
    # Reverse-depth sort means deeper dirs come AFTER shallower ones
    # (plan_entries sorts by depth ascending; restore sorts descending)
    for path in created_dirs:
        assert path in expected


def test_manifest_path_honours_tmpdir(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    p = manifest_mod.manifest_path()
    assert str(p).startswith(str(tmp_path))
    assert "dev-project-setup-restore" in p.name
    assert p.suffix == ".json"


def test_manifest_path_is_unique_under_rapid_calls(tmp_path, monkeypatch):
    """Codex iter-21 P2: two --apply runs in the same second must NOT
    collide on manifest path."""
    import tempfile

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    paths = {manifest_mod.manifest_path() for _ in range(20)}
    assert len(paths) == 20, "manifest paths collided under rapid calls"


def test_pre_existing_directories_not_listed(tmp_path):
    target_root = tmp_path / "proj"
    target_root.mkdir()
    (target_root / "scripts").mkdir()  # pre-existing
    (target_root / "docs").mkdir()  # pre-existing
    planned = {
        "scripts/runner.sh": b"y",
        "docs/plans/README.md": b"q",
        ".github/workflows/ci.yml": b"z",
    }
    _entries, created_dirs = manifest_mod.plan_entries(target_root, planned)
    # `scripts` and `docs` pre-existed → NOT listed; `docs/plans`, `.github`,
    # `.github/workflows` are new → listed.
    assert "scripts" not in created_dirs
    assert "docs" not in created_dirs
    assert "docs/plans" in created_dirs
    assert ".github" in created_dirs
    assert ".github/workflows" in created_dirs
