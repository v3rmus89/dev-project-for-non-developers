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
