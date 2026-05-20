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
    values raise ValueError at construction time. v2 restore matrix is
    implemented (`TestRestoreV2` below); the older NotImplementedError
    behavior was a chunk-1 stub.
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

    def test_restore_v2_empty_manifest_no_op(self, tmp_path):
        """An empty v2 manifest (no entries) returns all-zero counters
        without crashing. The v2 dispatch is reachable from `restore_from_manifest`."""
        import io

        m = manifest_mod.Manifest(
            target_root=str(tmp_path),
            github_review_mode="none",
            entries=[],
            created_directories=[],
            format_version=2,
        )
        n_restored, n_removed, n_skipped, n_rejected = manifest_mod.restore_from_manifest(
            m, stderr=io.StringIO()
        )
        assert (n_restored, n_removed, n_skipped, n_rejected) == (0, 0, 0, 0)

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


def _v2_entry(
    *,
    policy: str,
    path: str,
    target_path: str | None = None,
    sha256_after_target_path: str,
    sha256_before_target_path: str | None = None,
    content_before_b64: str | None = None,
    pre_append_length: int | None = None,
    mode_before: int | None = None,
):
    """Build a v2 manifest entry. Defaults to `target_path == path`."""
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


def _v2_manifest(target_root, entries, created_directories=None):
    return manifest_mod.Manifest(
        target_root=str(target_root),
        github_review_mode="none",
        entries=entries,
        created_directories=created_directories or [],
        format_version=manifest_mod.MANIFEST_FORMAT_V2,
    )


def _restore(m):
    import io

    out = io.StringIO()
    return manifest_mod.restore_from_manifest(m, stderr=out), out.getvalue()


class TestRestoreV2:
    """v2 per-policy restore matrix (Bucket B). Each row's three states are
    pinned: happy path (SHA == sha256_after_target_path), interrupted-apply
    (SHA == sha256_before_target_path), user-edit (SHA mismatch). Plus
    missing-file edge cases and path-safety rejection."""

    # ─── WRITE: created file; restore deletes if SHA matches ───
    def test_v2_write_happy_path_removes_created_file(self, tmp_path):
        content = b"# created by apply\n"
        (tmp_path / "new.txt").write_bytes(content)
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="WRITE",
                    path="new.txt",
                    sha256_after_target_path=_sha256(content),
                )
            ],
        )
        (counters, _out) = _restore(m)
        n_restored, n_removed, n_skipped, n_rejected = counters
        assert (n_restored, n_removed, n_skipped, n_rejected) == (0, 1, 0, 0)
        assert not (tmp_path / "new.txt").exists()

    def test_v2_write_user_edit_skip_with_warning(self, tmp_path):
        """User edited the created file after apply → preserve their edit."""
        (tmp_path / "new.txt").write_bytes(b"USER EDITED THIS\n")
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="WRITE",
                    path="new.txt",
                    sha256_after_target_path=_sha256(b"original content\n"),
                )
            ],
        )
        (counters, out) = _restore(m)
        _, n_removed, n_skipped, _ = counters
        assert n_removed == 0
        assert n_skipped == 1
        assert (tmp_path / "new.txt").exists()
        assert "user edit detected" in out

    def test_v2_write_missing_file_noop(self, tmp_path):
        """File missing → user already removed it; no-op skip (no warning)."""
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="WRITE",
                    path="never_existed.txt",
                    sha256_after_target_path="a" * 64,
                )
            ],
        )
        (counters, out) = _restore(m)
        _, n_removed, n_skipped, _ = counters
        assert n_removed == 0
        assert n_skipped == 1
        assert "already removed" in out

    # ─── OVERWRITE: modified existing file; restore writes content_before back ───
    def test_v2_overwrite_happy_path_writes_content_before_back(self, tmp_path):
        import base64

        before = b"# original user content\n"
        after = b"# applied skill content\n"
        (tmp_path / "Makefile").write_bytes(after)
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="OVERWRITE",
                    path="Makefile",
                    sha256_before_target_path=_sha256(before),
                    sha256_after_target_path=_sha256(after),
                    content_before_b64=base64.b64encode(before).decode("ascii"),
                    mode_before=0o644,
                )
            ],
        )
        (counters, _out) = _restore(m)
        n_restored, _, _, _ = counters
        assert n_restored == 1
        assert (tmp_path / "Makefile").read_bytes() == before

    def test_v2_overwrite_interrupted_apply_noop(self, tmp_path):
        """SHA matches `sha256_before_target_path` → apply was interrupted
        before this entry's write; nothing to undo (silent skip)."""
        import base64

        before = b"# original\n"
        after = b"# applied\n"
        (tmp_path / "Makefile").write_bytes(before)
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="OVERWRITE",
                    path="Makefile",
                    sha256_before_target_path=_sha256(before),
                    sha256_after_target_path=_sha256(after),
                    content_before_b64=base64.b64encode(before).decode("ascii"),
                    mode_before=0o644,
                )
            ],
        )
        (counters, out) = _restore(m)
        n_restored, _n_removed, n_skipped, _ = counters
        assert n_restored == 0
        assert n_skipped == 1
        # No warning text for interrupted-apply (it's a benign case)
        assert "user edit" not in out
        assert (tmp_path / "Makefile").read_bytes() == before

    def test_v2_overwrite_user_edit_skip_with_warning(self, tmp_path):
        import base64

        before = b"# original\n"
        (tmp_path / "Makefile").write_bytes(b"USER EDITED AFTER APPLY\n")
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="OVERWRITE",
                    path="Makefile",
                    sha256_before_target_path=_sha256(before),
                    sha256_after_target_path=_sha256(b"# applied\n"),
                    content_before_b64=base64.b64encode(before).decode("ascii"),
                    mode_before=0o644,
                )
            ],
        )
        (counters, out) = _restore(m)
        _, _, n_skipped, _ = counters
        assert n_skipped == 1
        assert "user edit detected" in out

    def test_v2_overwrite_missing_file_conservative_skip(self, tmp_path):
        """User deleted the file after apply → conservative SKIP (never undo
        a user deletion). Matches PR #1's v1 contract."""
        import base64

        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="OVERWRITE",
                    path="gone.txt",
                    sha256_before_target_path=_sha256(b"x"),
                    sha256_after_target_path=_sha256(b"y"),
                    content_before_b64=base64.b64encode(b"x").decode("ascii"),
                    mode_before=0o644,
                )
            ],
        )
        (counters, out) = _restore(m)
        _, _, n_skipped, _ = counters
        assert n_skipped == 1
        assert "file missing" in out

    # ─── WRITE_NEW: created `.new` next to original; restore removes `.new` ───
    def test_v2_write_new_happy_path_removes_new_file(self, tmp_path):
        """`.new` file unmodified → remove it. Original CLAUDE.md untouched."""
        original_content = b"# user's domain CLAUDE.md\n"
        new_content = b"# skill template CLAUDE.md\n"
        (tmp_path / "CLAUDE.md").write_bytes(original_content)
        (tmp_path / "CLAUDE.md.new").write_bytes(new_content)
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="WRITE_NEW",
                    path="CLAUDE.md",
                    target_path="CLAUDE.md.new",
                    sha256_before_target_path=None,  # .new didn't exist pre-apply
                    sha256_after_target_path=_sha256(new_content),
                )
            ],
        )
        (counters, _out) = _restore(m)
        _, n_removed, _, _ = counters
        assert n_removed == 1
        assert not (tmp_path / "CLAUDE.md.new").exists()
        # Original MUST be preserved.
        assert (tmp_path / "CLAUDE.md").read_bytes() == original_content

    def test_v2_write_new_user_edited_new_file_preserves_it(self, tmp_path):
        """User edited the `.new` file → preserve their edit."""
        original_content = b"# original\n"
        (tmp_path / "CLAUDE.md").write_bytes(original_content)
        (tmp_path / "CLAUDE.md.new").write_bytes(b"USER ANNOTATED THE NEW\n")
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="WRITE_NEW",
                    path="CLAUDE.md",
                    target_path="CLAUDE.md.new",
                    sha256_before_target_path=None,
                    sha256_after_target_path=_sha256(b"# applied .new\n"),
                )
            ],
        )
        (counters, out) = _restore(m)
        _, n_removed, n_skipped, _ = counters
        assert n_removed == 0
        assert n_skipped == 1
        assert (tmp_path / "CLAUDE.md.new").exists()
        assert "preserving user changes" in out
        # Original still preserved.
        assert (tmp_path / "CLAUDE.md").read_bytes() == original_content

    def test_v2_write_new_missing_new_file_benign(self, tmp_path):
        """User already removed the `.new`; no-op skip (no warning)."""
        (tmp_path / "CLAUDE.md").write_bytes(b"# original\n")
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="WRITE_NEW",
                    path="CLAUDE.md",
                    target_path="CLAUDE.md.new",
                    sha256_before_target_path=None,
                    sha256_after_target_path=_sha256(b"# anything\n"),
                )
            ],
        )
        (counters, out) = _restore(m)
        _, n_removed, n_skipped, _ = counters
        assert n_removed == 0
        assert n_skipped == 1
        # Original untouched
        assert (tmp_path / "CLAUDE.md").read_bytes() == b"# original\n"
        assert "user already removed" in out

    # ─── APPEND_MERGE: appended lines; restore truncates to pre_append_length ───
    def test_v2_append_merge_happy_path_truncates_to_pre_append_length(self, tmp_path):
        before = b"venv/\n*.pyc\n"
        after = b"venv/\n*.pyc\n__pycache__/\n.env\n"
        (tmp_path / ".gitignore").write_bytes(after)
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="APPEND_MERGE",
                    path=".gitignore",
                    sha256_before_target_path=_sha256(before),
                    sha256_after_target_path=_sha256(after),
                    pre_append_length=len(before),
                    mode_before=0o644,
                )
            ],
        )
        (counters, _out) = _restore(m)
        n_restored, _, _, _ = counters
        assert n_restored == 1
        # Truncated back to pre-append state.
        assert (tmp_path / ".gitignore").read_bytes() == before

    def test_v2_append_merge_interrupted_apply_noop(self, tmp_path):
        """SHA == `sha256_before_target_path` → apply was interrupted before
        the append; no-op (silent skip, no warning)."""
        before = b"venv/\n"
        (tmp_path / ".gitignore").write_bytes(before)
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="APPEND_MERGE",
                    path=".gitignore",
                    sha256_before_target_path=_sha256(before),
                    sha256_after_target_path=_sha256(b"venv/\n.env\n"),
                    pre_append_length=len(before),
                )
            ],
        )
        (counters, out) = _restore(m)
        n_restored, _, n_skipped, _ = counters
        assert n_restored == 0
        assert n_skipped == 1
        assert "user edit" not in out
        assert (tmp_path / ".gitignore").read_bytes() == before

    def test_v2_append_merge_user_edit_skip_with_warning(self, tmp_path):
        before = b"venv/\n"
        (tmp_path / ".gitignore").write_bytes(b"COMPLETELY DIFFERENT USER CONTENT\n")
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="APPEND_MERGE",
                    path=".gitignore",
                    sha256_before_target_path=_sha256(before),
                    sha256_after_target_path=_sha256(b"venv/\n.env\n"),
                    pre_append_length=len(before),
                )
            ],
        )
        (counters, out) = _restore(m)
        _, _, n_skipped, _ = counters
        assert n_skipped == 1
        assert "user edit detected" in out

    def test_v2_append_merge_missing_file_conservative_skip(self, tmp_path):
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="APPEND_MERGE",
                    path="gone.gitignore",
                    sha256_before_target_path=_sha256(b"x"),
                    sha256_after_target_path=_sha256(b"y"),
                    pre_append_length=1,
                )
            ],
        )
        (counters, out) = _restore(m)
        _, _, n_skipped, _ = counters
        assert n_skipped == 1
        assert "file missing" in out

    # ─── Dispatcher + path-safety + unknown-policy ───
    def test_v2_mixed_entries_all_policies_in_one_manifest(self, tmp_path):
        """Sanity check: a single v2 manifest containing one entry per
        mutating policy restores cleanly end-to-end. This is the call-details
        shape — the realistic adopt-mode payload."""
        import base64

        # WRITE: created Makefile
        makefile_content = b"all:\n\techo hi\n"
        (tmp_path / "Makefile").write_bytes(makefile_content)
        # OVERWRITE: modified pre-existing config
        config_before = b"setting=old\n"
        config_after = b"setting=new\n"
        (tmp_path / "config.txt").write_bytes(config_after)
        # WRITE_NEW: .new written next to original CLAUDE.md
        claude_original = b"# user CLAUDE.md\n"
        claude_new = b"# skill CLAUDE.md\n"
        (tmp_path / "CLAUDE.md").write_bytes(claude_original)
        (tmp_path / "CLAUDE.md.new").write_bytes(claude_new)
        # APPEND_MERGE: appended .gitignore
        gi_before = b"venv/\n"
        gi_after = b"venv/\n.env\n"
        (tmp_path / ".gitignore").write_bytes(gi_after)

        entries = [
            _v2_entry(
                policy="WRITE",
                path="Makefile",
                sha256_after_target_path=_sha256(makefile_content),
            ),
            _v2_entry(
                policy="OVERWRITE",
                path="config.txt",
                sha256_before_target_path=_sha256(config_before),
                sha256_after_target_path=_sha256(config_after),
                content_before_b64=base64.b64encode(config_before).decode("ascii"),
                mode_before=0o644,
            ),
            _v2_entry(
                policy="WRITE_NEW",
                path="CLAUDE.md",
                target_path="CLAUDE.md.new",
                sha256_before_target_path=None,
                sha256_after_target_path=_sha256(claude_new),
            ),
            _v2_entry(
                policy="APPEND_MERGE",
                path=".gitignore",
                sha256_before_target_path=_sha256(gi_before),
                sha256_after_target_path=_sha256(gi_after),
                pre_append_length=len(gi_before),
            ),
        ]
        m = _v2_manifest(tmp_path, entries)
        (counters, _out) = _restore(m)
        n_restored, n_removed, n_skipped, n_rejected = counters
        # OVERWRITE + APPEND_MERGE restore via mutation; WRITE + WRITE_NEW remove.
        assert n_restored == 2
        assert n_removed == 2
        assert n_skipped == 0
        assert n_rejected == 0
        # Verify each file's final state.
        assert not (tmp_path / "Makefile").exists()  # WRITE removed
        assert (tmp_path / "config.txt").read_bytes() == config_before  # OVERWRITE
        assert not (tmp_path / "CLAUDE.md.new").exists()  # WRITE_NEW removed
        assert (tmp_path / "CLAUDE.md").read_bytes() == claude_original  # untouched
        assert (tmp_path / ".gitignore").read_bytes() == gi_before  # truncated

    def test_v2_path_safety_rejection_aborts_before_mutation(self, tmp_path):
        """A v2 entry whose `target_path` escapes target_root must be rejected
        BEFORE any filesystem action, exactly like v1."""
        evil_content = b"# pretend skill secret\n"
        (tmp_path / "innocent.txt").write_bytes(evil_content)
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="WRITE",
                    path="innocent.txt",
                    target_path="../escape.txt",  # path-traversal attempt
                    sha256_after_target_path=_sha256(evil_content),
                )
            ],
        )
        (counters, out) = _restore(m)
        n_restored, n_removed, _n_skipped, n_rejected = counters
        assert n_rejected == 1
        assert n_restored == 0
        assert n_removed == 0
        assert "REJECT path-safety" in out
        # innocent.txt was never touched.
        assert (tmp_path / "innocent.txt").read_bytes() == evil_content

    def test_v2_unknown_policy_warn_and_skip(self, tmp_path):
        """Defensive: an unrecognized policy (manifest from a future version
        or corrupted) → warn-and-skip, NOT crash the whole restore."""
        (tmp_path / "f.txt").write_bytes(b"x")
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="WEIRD_FUTURE_POLICY",
                    path="f.txt",
                    sha256_after_target_path=_sha256(b"x"),
                )
            ],
        )
        (counters, out) = _restore(m)
        _, _, n_skipped, _ = counters
        assert n_skipped == 1
        assert "unknown policy" in out
        # File untouched
        assert (tmp_path / "f.txt").exists()

    def test_v2_created_directories_cleanup(self, tmp_path):
        """Empty created directories are removed in reverse-depth order, same
        as v1 (only if still empty at restore time)."""
        # Synthetic scenario: apply created subdir/ + subdir/nested/file.txt.
        sub = tmp_path / "subdir"
        nested = sub / "nested"
        nested.mkdir(parents=True)
        f = nested / "file.txt"
        content = b"x\n"
        f.write_bytes(content)
        m = _v2_manifest(
            tmp_path,
            [
                _v2_entry(
                    policy="WRITE",
                    path="subdir/nested/file.txt",
                    sha256_after_target_path=_sha256(content),
                )
            ],
            created_directories=["subdir", "subdir/nested"],
        )
        (counters, _out) = _restore(m)
        _, n_removed, _, _ = counters
        assert n_removed == 1
        # Both created dirs should now be gone (empty after file removal).
        assert not nested.exists()
        assert not sub.exists()
