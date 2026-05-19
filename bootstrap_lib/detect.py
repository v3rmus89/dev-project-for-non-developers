import tomllib
from pathlib import Path
from typing import NamedTuple, Union


class DetectionResult(NamedTuple):
    """Result of `detect_package_manager`.

    `manager` is `"uv"`, `"pip"`, or `None`. `None` means the caller should
    apply its own default (the CLI applies `"uv"` for `--language=python`).

    `reason` is a stable string explaining which heuristic branch fired.
    Branches: `"marker: <filename>"` for positive markers, `"ambiguous: ..."`
    for pyproject-without-PM-markers, `"malformed: ..."` for TOML parse
    failure, `"greenfield: ..."` for absent or signal-less directories.
    """

    manager: Union[str, None]
    reason: str


# Sentinel returned by `_load_pyproject` when the file exists but doesn't parse.
_PARSE_FAILED = object()


def _load_pyproject(out_dir: Path):
    """Return parsed pyproject.toml dict, `_PARSE_FAILED` sentinel, or None.

    None → file doesn't exist. Sentinel → file exists but TOML is malformed.
    """
    pyproject = out_dir / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        return tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return _PARSE_FAILED


def _first_requirements_match(out_dir: Path) -> Union[str, None]:
    """Return the filename of the first `requirements*.txt` match, or None.

    Sorted alphabetically for stable test output. The leading-`requirements`
    glob covers `requirements.txt`, `requirements-dev.txt`,
    `requirements-test.txt`, `requirements-prod.txt`, `requirements-lock.txt`,
    etc. — closes Codex Tier-2 #4 (the plan's promised `requirements*.txt`
    wildcard contract).
    """
    # Filter to files only — a directory named `requirements-test.txt`
    # shouldn't count as a pip marker (closes Tier-1 Codex #2).
    matches = sorted(p for p in out_dir.glob("requirements*.txt") if p.is_file())
    return matches[0].name if matches else None


def detect_package_manager(out_dir: "Path | str | None") -> DetectionResult:
    """Detect Python package manager from files in `out_dir`.

    Accepts `Path`, `str`, or `None` (closes Claude iter-2 #3 — `args.out`
    is a `str` from argparse and can be `None` in dry-run/diff modes).

    Priority: positive-uv > positive-pip > ambiguous (None manager) >
    malformed (None, fires only when no positive pip marker either) >
    greenfield (None). The CLI applies `"uv"` default for any None-manager
    case.
    """
    if out_dir is None:
        return DetectionResult(None, "greenfield: out_dir absent")
    out_dir = Path(out_dir)
    if not out_dir.exists():
        return DetectionResult(None, "greenfield: out_dir absent")

    # Rule 2 — positive uv marker (highest priority).
    #
    # `.is_file()` (not `.exists()`) — a directory accidentally named
    # `uv.lock` shouldn't false-positive (closes Tier-1 Codex #2).
    if (out_dir / "uv.lock").is_file():
        return DetectionResult("uv", "marker: uv.lock")

    # Parse pyproject.toml once and cache the result. Subsequent rules
    # consume the cached dict or the sentinel.
    pyproject = _load_pyproject(out_dir)

    # Rule 3 — [tool.uv] table in pyproject.toml.
    #
    # Both `tool` and `tool.uv` must be tables (dicts). Without the
    # `isinstance(..., dict)` guards, malformed-but-parseable pyprojects
    # could false-positive (e.g. `tool = "uv"` would let `"uv" in "uv"`
    # match) — closes Tier-1 Codex #1.
    if isinstance(pyproject, dict):
        tool = pyproject.get("tool")
        if isinstance(tool, dict) and isinstance(tool.get("uv"), dict):
            return DetectionResult("uv", "marker: [tool.uv] in pyproject.toml")

    # Rule 4 — [build-system] build-backend = "uv_build" (PEP 517 kebab-case
    # key; closes Codex Tier-2 #3 — earlier draft used `backend` which is
    # the wrong TOML key and would have missed real uv adoption cases).
    #
    # `isinstance(..., dict)` guard prevents crash if `build-system` is
    # a scalar (would AttributeError on `.get`) — closes Tier-1 Codex #1.
    if isinstance(pyproject, dict):
        build_system = pyproject.get("build-system")
        if isinstance(build_system, dict) and build_system.get("build-backend") == "uv_build":
            return DetectionResult("uv", "marker: uv_build backend in pyproject.toml")

    # Rule 5 — positive pip marker (requirements*.txt glob).
    #
    # Order matters: this check runs BEFORE the malformed-pyproject branch
    # so a pip marker is preserved when pyproject is malformed (closes
    # Codex Tier-2 #5).
    req_match = _first_requirements_match(out_dir)
    if req_match is not None:
        return DetectionResult("pip", f"marker: {req_match}")

    # Rule 6 — pyproject parses cleanly but has no PM markers (manager=None
    # so the CLI's advisory can print the explicit override hint; closes
    # Claude iter-2 #1 — earlier draft returned ("uv", "ambiguous: ...")
    # which made the CLI ambiguous-advisory branch dead code).
    if isinstance(pyproject, dict):
        return DetectionResult(None, "ambiguous: pyproject.toml present but no PM markers")

    # Rule 7 — pyproject exists but is malformed.
    if pyproject is _PARSE_FAILED:
        return DetectionResult(None, "malformed pyproject.toml; treating as no signals")

    # Rule 8 — greenfield (no signals at all).
    return DetectionResult(None, "greenfield: no PM signals")


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
