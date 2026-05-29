# PR-0 fact-check — post-merge hardening record (2026-05-29)

**Status**: hardening record. PR-0 (the `review-plan-fact-check-by-{codex,claude}`
targets + `scripts/extract-plan-facts.py` + `scripts/verify-plan-facts.py`)
**SHIPPED on 2026-05-28 in PR #30** — this is NOT a pre-implementation note. It
records a post-merge review of the shipped code and the hardening done in
response. (An earlier draft mis-framed these as pre-implementation decisions;
corrected per the review's FN4 — the code already existed.)

## What PR-0 is (shipped in PR #30)

`make review-plan-fact-check-by-{codex,claude}` run a deterministic extractor
(`scripts/extract-plan-facts.py`) that pulls file / line / symbol / make-target /
cli-flag references from a plan's ACTIVE sections, then a deterministic verifier
(`scripts/verify-plan-facts.py`) that checks them against declared fact roots
without mutating state. Both ship to downstream projects via
`shared/scripts-*.py.tmpl` (stdlib-only, byte-identical to the dogfood copies).
The live-AI review target wraps these for judgment-only checks and is NOT part
of `make check`.

## Post-merge review findings + disposition

A focused cross-direction review (Codex) of the shipped code, plus a Tier-1
re-review, surfaced four gaps:

| Gap | What | Disposition |
|---|---|---|
| 2 | Containment: a relative `../` escape verified as in-root; the `_find_file` rglob fallback + `_grep_symbol` + `_grep_make_target` would read buried symlinks pointing outside the root; `parse_fact_roots` honored `## Fact roots` blocks inside historical/fenced sections | **FIXED** — a single `_within()` containment predicate now guards every read site (resolve() collapses `..` and symlinks); `parse_fact_roots` runs on active text + is fence-aware. (commits `a4b14b8`, `0f8af96`) |
| 3 | Tests asserted `failed==0` on a curated snapshot but never pinned the iter-7 under-scan class itself | **FIXED** — tests now assert active `###` sub-blocks AND table rows are scanned, and `Iteration log` / `Evidence table` facts are excluded. (commit `1533d75`) |
| 1 | `cli_flag_ref` is `not_verifiable` — the `--apply --dry-run` semantic-conflict class isn't caught deterministically | **DEFERRED** → BACKLOG `fact-check-cli-flag-verification`. The shared script can't import a repo CLI parser (downstream projects lack it) and can't execute the CLI (no-execute boundary); needs an opt-in repo-local hook. |
| 4 | Review targets only `command -v` the CLI; no fallback when it's installed-but-unauthenticated | **DEFERRED** → BACKLOG `fact-check-ai-fallback`. |

## iter-7 FN1 / FN2 / FN3 vs shipped reality

The three iter-7 design questions this note originally set out to "resolve" were
in fact already addressed by the shipped PR-0: the active/historical split is a
denylist of historical headings (FN1); the deterministic-core / AI-wrapper split
exists, with the verifier in `make check` and the live-AI target outside it
(FN2); and an explicit `## Fact roots` block with a current-repo default is the
privacy model (FN3). The hardening above closed the containment + test-coverage
corners the post-merge review found in that shipped implementation.
