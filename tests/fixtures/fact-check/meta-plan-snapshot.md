# PR-0 Deliverables Snapshot (Fact-Check Test Fixture)

A curated subset of verifiable facts from the PR-0 planning document.
All referenced files, symbols, and Makefile targets exist in the skill
repo after PR-0 merges.  Used by `test_meta_plan_snapshot_clean` to
confirm zero failures post-merge.

## Scope

### Scripts shipped in PR-0

- `scripts/extract-plan-facts.py` — fact extractor for plan Markdown
- `scripts/verify-plan-facts.py` — deterministic verifier (no AI, no subprocess)

### Shared templates

- `shared/scripts-extract-plan-facts.py.tmpl`
- `shared/scripts-verify-plan-facts.py.tmpl`

### Key functions

- `extract_active_text()` — filters historical sections from plan text
- `extract_facts()` — extracts typed facts from active plan content
- `verify()` — verifies all facts and returns structured results

### Makefile targets added in PR-0

- `make review-plan-fact-check-by-codex`
- `make review-plan-fact-check-by-claude`
