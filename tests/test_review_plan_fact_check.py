"""Tests for scripts/extract-plan-facts.py and scripts/verify-plan-facts.py.

Closes FN4 from the iter-7 design gaps (PR-0 implementation): local pytest
tests for the new fact-check scripts.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
EXTRACT_SCRIPT = SKILL_ROOT / "scripts" / "extract-plan-facts.py"
VERIFY_SCRIPT = SKILL_ROOT / "scripts" / "verify-plan-facts.py"
FIXTURES_DIR = SKILL_ROOT / "tests" / "fixtures" / "fact-check"


def _extract(plan_file: Path) -> dict:
    r = subprocess.run(
        [sys.executable, str(EXTRACT_SCRIPT), str(plan_file)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"extract exited {r.returncode}: {r.stderr}"
    return json.loads(r.stdout)


def _verify(facts_json: str, root: Path) -> dict:
    r = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "-", str(root)],
        input=facts_json,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"verify exited {r.returncode}: {r.stderr}"
    return json.loads(r.stdout)


def test_active_bad_plan_findings():
    """The bad-plan fixture has exactly 1 passing fact and 4 failing ones.
    The Loop-outcome section is excluded and its fake reference is not extracted."""
    fixture = FIXTURES_DIR / "active-bad-plan.md"

    facts_data = _extract(fixture)
    assert len(facts_data["facts"]) == 5, (
        f"expected 5 facts (1 good + 4 bad), got {len(facts_data['facts'])}: "
        f"{[f['raw'] for f in facts_data['facts']]}"
    )

    result = _verify(json.dumps(facts_data), SKILL_ROOT)

    summary = result["summary"]
    assert summary["verified"] == 1, (
        f"expected 1 verified, got {summary['verified']}: {result['verified']}"
    )
    assert summary["failed"] == 4, f"expected 4 failed, got {summary['failed']}: {result['failed']}"

    raw_values = {f["raw"] for f in facts_data["facts"]}
    assert "also-excluded-xyz.py" not in raw_values, (
        "Loop-outcome section was not excluded — historical fact leaked into extracted list"
    )


def test_absolute_path_outside_roots_is_unsupported_external():
    """Codex Tier-2 P2 regression: absolute paths outside declared fact roots
    must land in unsupported_external, NOT verified (POSIX `root / abs` drops root)."""
    import tempfile

    # Build a minimal facts JSON with an absolute path that definitely exists on
    # the machine (the verify script itself) but is NOT under the declared root.
    with tempfile.TemporaryDirectory() as empty_root:
        facts_data = {
            "plan_file": "synthetic",
            "fact_roots": [empty_root],  # declare a root that doesn't contain VERIFY_SCRIPT
            "facts": [
                {
                    "type": "file_ref",
                    "raw": str(VERIFY_SCRIPT),
                    "path": str(VERIFY_SCRIPT),
                },
            ],
        }
        result = _verify(json.dumps(facts_data), Path(empty_root))

    assert result["summary"]["unsupported_external"] == 1, (
        "absolute path outside declared fact roots must be unsupported_external, "
        f"not verified/failed: {result}"
    )
    assert result["summary"]["verified"] == 0, (
        "absolute path outside declared fact roots must NOT be verified"
    )


def test_meta_plan_snapshot_clean():
    """Facts in the meta-plan snapshot (PR-0 deliverables) must all verify
    cleanly — zero failures expected once PR-0 is merged."""
    fixture = FIXTURES_DIR / "meta-plan-snapshot.md"

    facts_data = _extract(fixture)
    assert facts_data["facts"], "snapshot must contain at least one fact"

    result = _verify(json.dumps(facts_data), SKILL_ROOT)

    assert result["summary"]["failed"] == 0, (
        f"meta-plan snapshot has unexpected failures: {result['failed']}"
    )
    assert result["summary"]["verified"] > 0, (
        "no facts verified — snapshot may be empty or all facts unrecognised"
    )


# ── Gap 2: fact-root containment + privacy scoping (PR-0 hardening) ──────────


def test_relative_parent_escape_not_verified(tmp_path):
    """Containment: a relative ``../`` path that climbs out of the declared
    root must NEVER verify, even when the escaped file exists. It lands in
    unsupported_external, not verified."""
    root = tmp_path / "repo"
    root.mkdir()
    # A real file OUTSIDE the root, reachable only via ../
    (tmp_path / "outside.py").write_text("def secret(): pass\n")

    facts_data = {
        "plan_file": "synthetic",
        "fact_roots": [str(root)],
        "facts": [{"type": "file_ref", "raw": "`../outside.py`", "path": "../outside.py"}],
    }
    result = _verify(json.dumps(facts_data), root)

    assert result["summary"]["verified"] == 0, (
        f"relative ../ escape must not verify even though the file exists: {result}"
    )
    assert result["summary"]["unsupported_external"] == 1, (
        f"relative ../ escape should be unsupported_external: {result}"
    )


def test_fact_roots_ignored_in_historical_section(tmp_path):
    """Privacy scoping: a Fact-roots heading nested under an excluded
    historical section does NOT declare read roots (parse runs on active text)."""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# Plan\n\n## Scope\n\nReal active work.\n\n## Iteration log\n\n### Fact roots\n\n- /etc\n"
    )
    facts_data = _extract(plan)
    assert facts_data["fact_roots"] == [], (
        f"Fact-roots under a historical section must be ignored: {facts_data['fact_roots']}"
    )


def test_fact_roots_ignored_in_code_fence(tmp_path):
    """Privacy scoping: a Fact-roots block shown inside a code fence is an
    example, not a declaration — it must be ignored."""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# Plan\n\n## Scope\n\nDeclare roots like this:\n\n"
        "```\n## Fact roots\n\n- /etc\n```\n\nThat is the syntax.\n"
    )
    facts_data = _extract(plan)
    assert facts_data["fact_roots"] == [], (
        f"Fact-roots inside a code fence must be ignored: {facts_data['fact_roots']}"
    )


def test_fact_roots_parsed_in_active_section(tmp_path):
    """Positive case: a Fact-roots block in an active, non-fenced section IS
    parsed (both bare and backtick-wrapped absolute paths)."""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# Plan\n\n## Fact roots\n\n- /Users/example/repo\n- `/opt/other`\n\n## Scope\n\nwork\n"
    )
    facts_data = _extract(plan)
    assert facts_data["fact_roots"] == ["/Users/example/repo", "/opt/other"], (
        f"active Fact-roots block must be parsed: {facts_data['fact_roots']}"
    )


def test_buried_symlink_via_rglob_not_verified(tmp_path):
    """Containment (rglob branch): a bare filename whose only match under the
    root is a buried symlink pointing OUTSIDE the root must not verify. This
    exercises the _find_file rglob fallback specifically (the exact-path join
    does not exist, so the _escapes_all_roots gate passes and the rglob branch
    is reached)."""
    import os

    root = tmp_path / "repo"
    (root / "deep").mkdir(parents=True)
    outside = tmp_path / "secret.py"
    outside.write_text("def leak(): pass\n")
    os.symlink(outside, root / "deep" / "shadow.py")  # buried symlink, escapes root

    facts_data = {
        "plan_file": "synthetic",
        "fact_roots": [str(root)],
        "facts": [{"type": "file_ref", "raw": "`shadow.py`", "path": "shadow.py"}],
    }
    result = _verify(json.dumps(facts_data), root)
    assert result["summary"]["verified"] == 0, (
        f"buried symlink escaping the root must not verify via rglob: {result}"
    )


def test_exact_path_symlink_escape_not_verified(tmp_path):
    """Containment (exact-path / gate): a symlink at the referenced path that
    resolves outside the root must not verify."""
    import os

    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "secret.py"
    outside.write_text("def leak(): pass\n")
    os.symlink(outside, root / "link.py")

    facts_data = {
        "plan_file": "synthetic",
        "fact_roots": [str(root)],
        "facts": [{"type": "file_ref", "raw": "`link.py`", "path": "link.py"}],
    }
    result = _verify(json.dumps(facts_data), root)
    assert result["summary"]["verified"] == 0, (
        f"exact-path symlink escaping the root must not verify: {result}"
    )
