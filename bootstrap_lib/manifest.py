import base64
import contextlib
import datetime
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from bootstrap_lib import io as bio
from bootstrap_lib.paths import PathSafetyError, validate_target_path

EXECUTABLE_TARGETS = {
    "scripts/run-with-clean-env.py",
    ".husky/pre-commit",
    ".husky/pre-push",
    "hooks/pre-commit",
    "hooks/pre-push",
}

# Manifest format versions:
#   v1 (legacy / `--apply` path) — entries: path / existed_before / sha256_before /
#       content_before_b64 / mode_before / action_planned / sha256_after / mode_after
#   v2 (`--apply --mode=adopt` path) — v1 fields PLUS per-policy fields:
#       policy, target_path, sha256_before_target_path, sha256_after_target_path,
#       pre_append_length. SKIP entries are NOT in v2 manifests (mutation-only).
#
# Backward-compat dispatch (Bucket B): when loading a manifest, `format_version`
# absent or None → treated as v1 (preserves PR #1-#6 manifest compat); `2` →
# v2 semantics. Any other value → ValueError (fail-loud on unknown future
# versions rather than silently mis-interpreting).
MANIFEST_FORMAT_V1 = 1
MANIFEST_FORMAT_V2 = 2
_SUPPORTED_FORMAT_VERSIONS = frozenset({MANIFEST_FORMAT_V1, MANIFEST_FORMAT_V2})


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def default_mode_for(rel_path: str) -> int:
    if rel_path in EXECUTABLE_TARGETS:
        return 0o755
    return 0o644


class Manifest:
    def __init__(
        self,
        target_root,
        github_review_mode,
        entries,
        created_directories,
        created_at=None,
        format_version=MANIFEST_FORMAT_V1,
    ):
        if format_version not in _SUPPORTED_FORMAT_VERSIONS:
            raise ValueError(
                f"unsupported manifest format_version={format_version!r}; "
                f"supported: {sorted(_SUPPORTED_FORMAT_VERSIONS)}"
            )
        self.target_root = target_root
        self.github_review_mode = github_review_mode
        self.entries = entries
        self.created_directories = created_directories
        self.created_at = created_at or datetime.datetime.now(datetime.UTC).isoformat()
        self.format_version = format_version

    def to_dict(self):
        return {
            "created_at": self.created_at,
            "target_root": str(self.target_root),
            "github_review_mode": self.github_review_mode,
            "entries": self.entries,
            "created_directories": self.created_directories,
            "format_version": self.format_version,
        }

    @classmethod
    def from_dict(cls, data):
        # `format_version` absent / None → v1 (preserves PR #1-#6 manifest
        # backward-compat per Bucket B). `2` → v2. Anything else → ValueError
        # (raised by the constructor via _SUPPORTED_FORMAT_VERSIONS check).
        raw_version = data.get("format_version")
        format_version = MANIFEST_FORMAT_V1 if raw_version is None else raw_version
        return cls(
            target_root=data["target_root"],
            github_review_mode=data["github_review_mode"],
            entries=data["entries"],
            created_directories=data.get("created_directories", []),
            created_at=data.get("created_at"),
            format_version=format_version,
        )


def manifest_path():
    # mkstemp guarantees uniqueness even when two --apply runs land in the
    # same second — closes Codex iter-21 P2. The timestamp prefix keeps
    # the manifests human-sortable; the random suffix prevents collisions.
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    fd, path = tempfile.mkstemp(
        prefix=f"dev-project-setup-restore-{timestamp}-",
        suffix=".json",
    )
    os.close(fd)
    return Path(path)


def plan_entries(target_root, planned_files):
    root = Path(target_root)
    entries = []
    pre_existing_dirs = set()
    if root.exists():
        for dirpath, _dirnames, _filenames in os.walk(root):
            rel = Path(dirpath).relative_to(root)
            if str(rel) != ".":
                pre_existing_dirs.add(str(rel))

    needed_dirs = set()
    for rel_path in sorted(planned_files):
        content = planned_files[rel_path]
        target = root / rel_path
        parent = Path(rel_path).parent
        while str(parent) not in (".", ""):
            if str(parent) not in pre_existing_dirs:
                needed_dirs.add(str(parent))
            parent = parent.parent

        if target.exists():
            existing = target.read_bytes()
            existing_mode = os.stat(target).st_mode & 0o777
            entries.append(
                {
                    "path": rel_path,
                    "existed_before": True,
                    "sha256_before": _sha256(existing),
                    "content_before_b64": base64.b64encode(existing).decode("ascii"),
                    "mode_before": existing_mode,
                    "action_planned": "overwrite",
                    "sha256_after": _sha256(content),
                    "mode_after": default_mode_for(rel_path),
                }
            )
        else:
            entries.append(
                {
                    "path": rel_path,
                    "existed_before": False,
                    "sha256_before": None,
                    "content_before_b64": None,
                    "mode_before": None,
                    "action_planned": "create",
                    "sha256_after": _sha256(content),
                    "mode_after": default_mode_for(rel_path),
                }
            )

    created_directories = sorted(needed_dirs, key=lambda p: (len(Path(p).parts), p))
    return entries, created_directories


def write_manifest(m):
    path = manifest_path()
    payload = json.dumps(m.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    with open(path, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    return path


def load_manifest(path):
    with open(path, "rb") as f:
        data = json.loads(f.read().decode("utf-8"))
    return Manifest.from_dict(data)


def restore_from_manifest(m, stderr=None):
    if stderr is None:
        stderr = sys.stderr

    # v1 manifests use the legacy restore semantics below (PR #1 contract).
    # v2 manifests need the per-policy restore matrix (Bucket B) which lands in
    # a follow-up commit; raise loud here rather than silently mis-restoring.
    if m.format_version != MANIFEST_FORMAT_V1:
        raise NotImplementedError(
            f"manifest format_version={m.format_version} requires the v2 "
            "per-policy restore matrix (Bucket B); not yet implemented in "
            "this commit"
        )

    target_root = Path(m.target_root).resolve()
    n_restored = 0
    n_removed = 0
    n_skipped = 0
    n_rejected = 0

    # Path-safety pre-flight: validate every entry BEFORE any filesystem action
    for entry in m.entries:
        try:
            validate_target_path(target_root, entry["path"])
        except PathSafetyError as e:
            stderr.write(f"REJECT path-safety: {e}\n")
            n_rejected += 1
    for d in m.created_directories:
        try:
            validate_target_path(target_root, d)
        except PathSafetyError as e:
            stderr.write(f"REJECT directory path-safety: {e}\n")
            n_rejected += 1
    if n_rejected:
        stderr.write(f"aborting restore: {n_rejected} entry/entries rejected for path-safety\n")
        return (n_restored, n_removed, n_skipped, n_rejected)

    # Restore files
    for entry in m.entries:
        target_path = target_root / entry["path"]
        if entry["existed_before"]:
            if target_path.exists():
                current = target_path.read_bytes()
                current_sha = _sha256(current)
                if current_sha == entry["sha256_after"]:
                    # Crash-safe write-back: closes Codex iter-21 P1. A bare
                    # write_bytes truncates in place; if the restore is
                    # interrupted, the user is left with an empty or partial
                    # file. Route through atomic_write for the same tmp+rename
                    # discipline as apply.
                    content = base64.b64decode(entry["content_before_b64"])
                    bio.atomic_write(target_path, content)
                    os.chmod(target_path, entry["mode_before"])
                    n_restored += 1
                elif current_sha == entry["sha256_before"]:
                    pass
                else:
                    stderr.write(
                        "SKIP {}: user edit detected; left in place\n".format(entry["path"])
                    )
                    n_skipped += 1
            else:
                # Overwritten file is missing at restore time. Current state
                # matches neither sha256_after nor sha256_before — conservative
                # rule says SKIP (Codex iter-20 P1: never undo a user deletion
                # even if the apply might just have been interrupted).
                stderr.write(
                    "SKIP {}: file missing; left absent (user deletion or "
                    "interrupted apply — restore is conservative)\n".format(entry["path"])
                )
                n_skipped += 1
        else:
            if target_path.exists():
                current = target_path.read_bytes()
                current_sha = _sha256(current)
                if current_sha == entry["sha256_after"]:
                    target_path.unlink()
                    n_removed += 1
                else:
                    stderr.write(
                        "SKIP {}: user edit detected; left in place\n".format(entry["path"])
                    )
                    n_skipped += 1
            # else: file missing → apply was interrupted before write; no-op

    # Remove created directories in reverse-depth order, only if empty
    sorted_dirs = sorted(m.created_directories, key=lambda p: (-len(Path(p).parts), p))
    for d in sorted_dirs:
        dir_path = target_root / d
        if dir_path.is_dir():
            # Non-empty (e.g. user dropped content) — leave it
            with contextlib.suppress(OSError):
                dir_path.rmdir()

    stderr.write(
        f"{n_restored} files restored, {n_removed} files removed, {n_skipped} skipped due to modification, "
        f"{n_rejected} rejected for path-safety\n"
    )
    return (n_restored, n_removed, n_skipped, n_rejected)
