# Active Bad Plan (Fact-Check Test Fixture)

This fixture is used by tests/test_review_plan_fact_check.py (no backticks — avoids extracting the path as a fact).
It contains exactly 1 passing fact and 4 failing facts in active sections,
plus one fact in a historical section that must NOT be extracted.

## Scope

### Passing reference

The repository entry point is `bootstrap.py` — exists in SKILL_ROOT.

### Failing references

- Missing file: `no-such-file-xyz-not-real.py`
- Out-of-range line reference: `bootstrap.py:99999`
- Non-existent symbol: `nonexistent_xyz_function_not_real()`
- Non-existent make target: `make this-target-does-not-exist-xyz`

## Loop outcome

This section is historical and must be excluded by the extractor.
The file reference below must NOT appear in the extracted facts list.

- Excluded reference: `also-excluded-xyz.py`
