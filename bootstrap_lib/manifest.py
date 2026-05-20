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
    """Restore a target_root to its pre-apply state using the manifest.

    Dispatches on `format_version`:
      v1 → `_restore_v1` (PR #1 contract: created files removed, overwritten
           files written back from `content_before_b64`).
      v2 → `_restore_v2` (Bucket B per-policy matrix: WRITE deletes,
           OVERWRITE writes back, WRITE_NEW removes the `.new` file,
           APPEND_MERGE truncates to `pre_append_length`. SKIP entries
           don't appear in v2 manifests per the mutation-only contract).

    Both paths return (n_restored, n_removed, n_skipped, n_rejected).
    """
    if stderr is None:
        stderr = sys.stderr
    if m.format_version == MANIFEST_FORMAT_V1:
        return _restore_v1(m, stderr)
    if m.format_version == MANIFEST_FORMAT_V2:
        return _restore_v2(m, stderr)
    # Constructor's _SUPPORTED_FORMAT_VERSIONS check guarantees we never reach
    # here; defensive fail-loud for the impossible-but-someone-bypassed-init case.
    raise ValueError(f"unsupported manifest format_version={m.format_version}")


def _restore_v1(m, stderr):
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


# ─── v2 per-policy restore matrix (Bucket B) ────────────────────────────────
#
# Each per-policy handler returns one of:
#   "restored" — file mutated back to pre-apply state
#   "removed"  — file deleted (was a create that we're undoing)
#   "skipped"  — left in place (SHA mismatch / missing / interrupted apply /
#                unknown policy)
#
# v2 uses `target_path` + `sha256_before_target_path` / `sha256_after_target_path`
# as the authoritative mutation surface (Bucket B): for WRITE_NEW these point
# at the `.new` file, not the original; for APPEND_MERGE they point at the
# original and `pre_append_length` says where to truncate. WRITE + OVERWRITE
# always have `target_path == path` so the v2 fields collapse to the v1 SHAs.


def _restore_v2_write(entry, target_root, stderr):
    """WRITE was a create — restore by deleting if SHA matches `sha256_after_target_path`.

    Missing file → assume user already removed it (no-op skip, no warning).
    SHA mismatch → user edited the file we created (preserve their edit).
    """
    target_path_str = entry["target_path"]
    target_path = target_root / target_path_str
    if not target_path.exists():
        stderr.write(f"SKIP {target_path_str}: file missing; already removed (no-op)\n")
        return "skipped"
    current_sha = _sha256(target_path.read_bytes())
    if current_sha == entry["sha256_after_target_path"]:
        target_path.unlink()
        return "removed"
    stderr.write(f"SKIP {target_path_str}: user edit detected; left in place\n")
    return "skipped"


def _restore_v2_overwrite(entry, target_root, stderr):
    """OVERWRITE modified an existing file — restore by writing
    `content_before_b64` back atomically and restoring `mode_before`.

    SHA == `sha256_after_target_path` → apply succeeded; restore.
    SHA == `sha256_before_target_path` → apply was interrupted; no-op.
    Otherwise → user edit; SKIP with warning.
    """
    target_path_str = entry["target_path"]
    target_path = target_root / target_path_str
    if not target_path.exists():
        stderr.write(
            f"SKIP {target_path_str}: file missing; left absent (user deletion "
            "or interrupted apply — restore is conservative)\n"
        )
        return "skipped"
    current_sha = _sha256(target_path.read_bytes())
    if current_sha == entry["sha256_after_target_path"]:
        content = base64.b64decode(entry["content_before_b64"])
        bio.atomic_write(target_path, content)
        os.chmod(target_path, entry["mode_before"])
        return "restored"
    if current_sha == entry["sha256_before_target_path"]:
        # Apply was interrupted before this entry's write; nothing to undo.
        return "skipped"
    stderr.write(f"SKIP {target_path_str}: user edit detected; left in place\n")
    return "skipped"


def _restore_v2_write_new(entry, target_root, stderr):
    """WRITE_NEW created `<path>.new` next to the original; original untouched.

    SHA-check is on `target_path` (the `.new` file). Missing `.new` → benign
    (user already removed the `.new`); no warning. SHA mismatch → user edited
    the `.new`; preserve it.
    """
    target_path_str = entry["target_path"]
    target_path = target_root / target_path_str
    if not target_path.exists():
        stderr.write(f"SKIP {target_path_str}: .new file missing; user already removed (no-op)\n")
        return "skipped"
    current_sha = _sha256(target_path.read_bytes())
    if current_sha == entry["sha256_after_target_path"]:
        target_path.unlink()
        return "removed"
    stderr.write(f"SKIP {target_path_str}: .new file edited; preserving user changes\n")
    return "skipped"


def _restore_v2_append_merge(entry, target_root, stderr):
    """APPEND_MERGE appended lines to the original — restore by truncating
    to `pre_append_length` bytes.

    SHA == `sha256_after_target_path` → apply succeeded; truncate.
    SHA == `sha256_before_target_path` → apply was interrupted; no-op.
    Otherwise → user edit; SKIP with warning.
    """
    target_path_str = entry["target_path"]
    target_path = target_root / target_path_str
    if not target_path.exists():
        stderr.write(
            f"SKIP {target_path_str}: file missing; left absent (user deletion "
            "or interrupted apply — restore is conservative)\n"
        )
        return "skipped"
    current_sha = _sha256(target_path.read_bytes())
    if current_sha == entry["sha256_after_target_path"]:
        # Truncate to pre-append length.
        with open(target_path, "rb+") as f:
            f.truncate(entry["pre_append_length"])
            f.flush()
            os.fsync(f.fileno())
        return "restored"
    if current_sha == entry["sha256_before_target_path"]:
        # Apply was interrupted before the append; nothing to undo.
        return "skipped"
    stderr.write(f"SKIP {target_path_str}: user edit detected; left in place\n")
    return "skipped"


_V2_RESTORE_HANDLERS = {
    "WRITE": _restore_v2_write,
    "OVERWRITE": _restore_v2_overwrite,
    "WRITE_NEW": _restore_v2_write_new,
    "APPEND_MERGE": _restore_v2_append_merge,
}


def _restore_v2(m, stderr):
    """Bucket B v2 restore matrix dispatcher.

    SKIP entries don't appear in v2 manifests by contract (mutation-only); if
    one shows up anyway, the dispatch hits the unknown-policy branch and
    warn-and-skips rather than crashing the whole restore.
    """
    target_root = Path(m.target_root).resolve()
    n_restored = 0
    n_removed = 0
    n_skipped = 0
    n_rejected = 0

    # Path-safety pre-flight: validate `target_path` (the actual mutation
    # surface for v2) for every entry BEFORE any filesystem action.
    for entry in m.entries:
        try:
            validate_target_path(target_root, entry["target_path"])
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

    # Per-policy dispatch
    for entry in m.entries:
        policy = entry.get("policy")
        handler = _V2_RESTORE_HANDLERS.get(policy)
        if handler is None:
            target_path_str = entry.get("target_path") or entry.get("path", "?")
            stderr.write(
                f"SKIP {target_path_str}: unknown policy {policy!r}; "
                "manifest may be from a future version or corrupted\n"
            )
            n_skipped += 1
            continue
        outcome = handler(entry, target_root, stderr)
        if outcome == "restored":
            n_restored += 1
        elif outcome == "removed":
            n_removed += 1
        else:
            n_skipped += 1

    # Remove created_directories in reverse-depth order, only if empty.
    # (Same contract as v1 — a directory created by apply that's now empty is
    # an apply-side artifact; one that user dropped content into stays.)
    sorted_dirs = sorted(m.created_directories, key=lambda p: (-len(Path(p).parts), p))
    for d in sorted_dirs:
        dir_path = target_root / d
        if dir_path.is_dir():
            with contextlib.suppress(OSError):
                dir_path.rmdir()

    stderr.write(
        f"{n_restored} files restored, {n_removed} files removed, "
        f"{n_skipped} skipped due to modification, "
        f"{n_rejected} rejected for path-safety\n"
    )
    return (n_restored, n_removed, n_skipped, n_rejected)
