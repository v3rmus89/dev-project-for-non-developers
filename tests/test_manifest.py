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


class TestManifestFormatVersion:
    """PR #7 Bucket B: `format_version` field at the manifest top level.

    v1 (default, `--apply` path) preserves PR #1-#6 backward-compat. v2
    (`--apply --mode=adopt` path) adds per-policy entry fields. Unknown
    values raise ValueError at construction time. Restore of a v2 manifest
    raises NotImplementedError in this commit (full v2 restore matrix lands
    in a follow-up).
    """

    def test_default_format_version_is_v1(self, tmp_path):
        m = manifest_mod.Manifest(
            target_root=str(tmp_path),
            github_review_mode="none",
            entries=[],
            created_directories=[],
        )
        assert m.format_version == manifest_mod.MANIFEST_FORMAT_V1
        assert m.format_version == 1

    def test_to_dict_emits_format_version(self, tmp_path):
        m = manifest_mod.Manifest(
            target_root=str(tmp_path),
            github_review_mode="none",
            entries=[],
            created_directories=[],
        )
        data = m.to_dict()
        assert "format_version" in data
        assert data["format_version"] == 1

    def test_v1_round_trip_preserves_format_version(self, tmp_path, monkeypatch):
        """A v1 manifest written + loaded retains format_version=1."""
        import tempfile

        monkeypatch.setenv("TMPDIR", str(tmp_path))
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        m = manifest_mod.Manifest(
            target_root=str(tmp_path),
            github_review_mode="none",
            entries=[],
            created_directories=[],
        )
        path = manifest_mod.write_manifest(m)
        loaded = manifest_mod.load_manifest(path)
        assert loaded.format_version == 1

    def test_legacy_manifest_without_format_version_loads_as_v1(self, tmp_path):
        """Pre-PR-#7 manifests on disk have NO `format_version` key. The
        backward-compat dispatch must treat them as v1 (NOT crash, NOT default
        to a future version)."""
        legacy_data = {
            "created_at": "2026-05-19T00:00:00+00:00",
            "target_root": str(tmp_path),
            "github_review_mode": "none",
            "entries": [],
            "created_directories": [],
            # NO `format_version` key — this is the PR #1-#6 on-disk shape.
        }
        m = manifest_mod.Manifest.from_dict(legacy_data)
        assert m.format_version == manifest_mod.MANIFEST_FORMAT_V1

    def test_legacy_manifest_format_version_null_loads_as_v1(self, tmp_path):
        """`format_version: null` (explicit None) is treated as v1, same as
        an absent field — the dispatch contract handles both shapes."""
        data = {
            "created_at": "2026-05-19T00:00:00+00:00",
            "target_root": str(tmp_path),
            "github_review_mode": "none",
            "entries": [],
            "created_directories": [],
            "format_version": None,
        }
        m = manifest_mod.Manifest.from_dict(data)
        assert m.format_version == manifest_mod.MANIFEST_FORMAT_V1

    def test_v2_construction_with_explicit_format_version(self, tmp_path):
        m = manifest_mod.Manifest(
            target_root=str(tmp_path),
            github_review_mode="none",
            entries=[],
            created_directories=[],
            format_version=2,
        )
        assert m.format_version == 2

    def test_v2_round_trip_preserves_format_version_and_new_entry_fields(
        self, tmp_path, monkeypatch
    ):
        """A v2 manifest with the new per-policy entry fields round-trips
        through JSON without loss. Entries are dicts (no schema enforcement
        at the Manifest layer); the new fields just need to survive JSON +
        load."""
        import tempfile

        monkeypatch.setenv("TMPDIR", str(tmp_path))
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

        # Synthetic v2 entries — one of each mutating policy. SKIP entries
        # are NOT in v2 manifests (mutation-only contract per Bucket B).
        entries = [
            {
                # WRITE — created file, didn't exist before.
                "path": "new.txt",
                "policy": "WRITE",
                "target_path": "new.txt",
                "existed_before": False,
                "content_before_b64": None,
                "mode_before": None,
                "sha256_before": None,
                "sha256_after": "a" * 64,
                "sha256_before_target_path": None,
                "sha256_after_target_path": "a" * 64,
                "pre_append_length": None,
                "mode_after": 0o644,
            },
            {
                # OVERWRITE — modified existing file; v1-style content_before.
                "path": "exists.txt",
                "policy": "OVERWRITE",
                "target_path": "exists.txt",
                "existed_before": True,
                "content_before_b64": base64.b64encode(b"old").decode("ascii"),
                "mode_before": 0o644,
                "sha256_before": _sha256(b"old"),
                "sha256_after": "b" * 64,
                "sha256_before_target_path": _sha256(b"old"),
                "sha256_after_target_path": "b" * 64,
                "pre_append_length": None,
                "mode_after": 0o644,
            },
            {
                # WRITE_NEW — wrote `.new` next to original; original untouched.
                "path": "CLAUDE.md",
                "policy": "WRITE_NEW",
                "target_path": "CLAUDE.md.new",
                "existed_before": True,
                "content_before_b64": None,  # original unmodified
                "mode_before": None,
                "sha256_before": None,
                "sha256_after": "c" * 64,
                "sha256_before_target_path": None,  # `.new` file didn't exist before
                "sha256_after_target_path": "c" * 64,
                "pre_append_length": None,
                "mode_after": 0o644,
            },
            {
                # APPEND_MERGE — appended missing lines to original.
                "path": ".gitignore",
                "policy": "APPEND_MERGE",
                "target_path": ".gitignore",
                "existed_before": True,
                "content_before_b64": None,  # restore uses truncation, not write-back
                "mode_before": 0o644,
                "sha256_before": _sha256(b"venv/\n"),
                "sha256_after": "d" * 64,
                "sha256_before_target_path": _sha256(b"venv/\n"),
                "sha256_after_target_path": "d" * 64,
                "pre_append_length": len(b"venv/\n"),
                "mode_after": 0o644,
            },
        ]

        m = manifest_mod.Manifest(
            target_root=str(tmp_path),
            github_review_mode="none",
            entries=entries,
            created_directories=[],
            format_version=2,
        )
        path = manifest_mod.write_manifest(m)
        loaded = manifest_mod.load_manifest(path)
        assert loaded.format_version == 2
        assert loaded.entries == entries  # dict-by-dict equality
        # Spot-check the new fields specifically
        write_new_entry = next(e for e in loaded.entries if e["policy"] == "WRITE_NEW")
        assert write_new_entry["target_path"] == "CLAUDE.md.new"
        assert write_new_entry["sha256_before_target_path"] is None
        append_merge_entry = next(e for e in loaded.entries if e["policy"] == "APPEND_MERGE")
        assert append_merge_entry["pre_append_length"] == len(b"venv/\n")

    def test_unsupported_format_version_raises_value_error(self, tmp_path):
        """Unknown future versions fail-loud at construction rather than
        silently misinterpreting the manifest."""
        import pytest

        with pytest.raises(ValueError, match="unsupported manifest format_version"):
            manifest_mod.Manifest(
                target_root=str(tmp_path),
                github_review_mode="none",
                entries=[],
                created_directories=[],
                format_version=99,
            )

    def test_from_dict_with_unsupported_format_version_raises(self, tmp_path):
        import pytest

        data = {
            "created_at": "2026-05-19T00:00:00+00:00",
            "target_root": str(tmp_path),
            "github_review_mode": "none",
            "entries": [],
            "created_directories": [],
            "format_version": 99,
        }
        with pytest.raises(ValueError, match="unsupported manifest format_version"):
            manifest_mod.Manifest.from_dict(data)

    def test_restore_raises_not_implemented_for_v2(self, tmp_path):
        """v2 restore matrix lands in a follow-up commit; until then, calling
        restore on a v2 manifest must fail-loud, not silently fall through to
        v1 semantics (which would do the wrong thing for WRITE_NEW / APPEND_MERGE)."""
        import io

        import pytest

        m = manifest_mod.Manifest(
            target_root=str(tmp_path),
            github_review_mode="none",
            entries=[],
            created_directories=[],
            format_version=2,
        )
        with pytest.raises(NotImplementedError, match="v2 per-policy restore matrix"):
            manifest_mod.restore_from_manifest(m, stderr=io.StringIO())

    def test_restore_works_for_v1_unchanged(self, tmp_path, monkeypatch):
        """Regression guard: PR #7's format_version dispatch must not break
        the existing PR #1 restore flow for v1 manifests."""
        import tempfile

        monkeypatch.setenv("TMPDIR", str(tmp_path))
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        target_root = tmp_path / "proj"
        target_root.mkdir()
        planned = {"Makefile": b"# new\n"}
        entries, created_dirs = manifest_mod.plan_entries(target_root, planned)
        m = manifest_mod.Manifest(
            target_root=str(target_root),
            github_review_mode="none",
            entries=entries,
            created_directories=created_dirs,
        )
        # apply
        (target_root / "Makefile").write_bytes(b"# new\n")
        # restore: file matches sha256_after → should be removed
        import io

        out = io.StringIO()
        _n_restored, n_removed, _n_skipped, n_rejected = manifest_mod.restore_from_manifest(
            m, stderr=out
        )
        assert n_removed == 1
        assert n_rejected == 0
        assert not (target_root / "Makefile").exists()
