from pathlib import Path


def inspect_target(target_root, planned_files):
    root = Path(target_root)
    out = []
    for rel_path in sorted(planned_files):
        target = root / rel_path
        exists = target.exists()
        out.append(
            {
                "path": rel_path,
                "exists": exists,
                "would_action": "overwrite" if exists else "create",
            }
        )
    return out


def has_collisions(inspection):
    return any(e["exists"] for e in inspection)
