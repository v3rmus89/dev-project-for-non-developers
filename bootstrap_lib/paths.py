import os
from pathlib import Path


class PathSafetyError(ValueError):
    """Raised when a target-relative path escapes its target_root."""


def validate_target_path(target_root, rel_path):
    if os.path.isabs(rel_path):
        raise PathSafetyError(f"absolute path not allowed: {rel_path!r}")
    root = Path(target_root).resolve()
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathSafetyError(
            f"path escapes target_root: {rel_path!r} resolves to {str(candidate)!r}, outside {str(root)!r}"
        ) from exc
    return candidate
