# Harvest 4 plan-tango improvements into our review loop (B/C/D/E)

**Scope split (iter-6 decision)**: this PR was originally scoped to 6 buckets (A/B/C/D/E/F). After 6 cross-review iters + 5 consistency self-checks failed to plateau (imp-3 trajectory: 3→4→4→3→4→3), the scope was narrowed to B/C/D/E. Bucket A (in-plan-mode Skill) and Bucket F (continue-thread) deferred to follow-up PRs. See iter-6 iteration log + the NOT-in-scope table for the deferral rationale and the iter-1..6 findings captured as their starting requirements.

**Destination filename (after approval):** `docs/plans/2026-05-27-skill-pr10-harvest-plan-tango-improvements.md`

## Context

`egsok/plan-tango` is a Claude Code plugin that auto-converges a plan via a Claude↔Codex review loop. We compared it to our `make review-plan-by-*` pipeline and found the following:

- **Our design is human-anchored** (Claude triages per-finding via the (a/b/c/d) rule + 4 pre-fold questions; human approves once at end-of-loop). Plan-tango's auto-apply trades that discipline for speed. We keep ours.
- **What plan-tango does better, mechanically**: it works inside plan mode (Skill design); it snapshots the plan before each iter; it sha256-checks the plan between iters to catch external edits; it detects oscillation / stuck / regression; it reuses one Codex thread with a `<reset_iteration>` block to cut cost on long loops; it has a structured verdict contract so the stop condition is mechanical instead of prose-eyeballed.
- **The 13-15 iter case we hit** (downstream-app `docs/plans/2026-05-25-phase-5a-prep-amendments.md`, 8 Codex passes + 7 consistency passes + 2 closings = 17 iters) was **not** oscillation — it was a real convergence over a 744-line plan, where each Codex pass found genuinely new findings, sometimes introduced by prior folds. iter 11 was the first imp-3=0; iter 13 saw imp-3 return because the iter-11 fold introduced a new (fictional) `llm.ping()` API. A structured verdict footer + stop classifier would have flagged the iter-11 inflection mechanically. Continue-thread mode would have cut Codex cost meaningfully across 8 passes of a 700-line plan.

**Outcome we want**: fewer-friction reviews (no exit-from-plan-mode), cheaper long loops (cache hits), mechanical stop signals (no prose-reading), automatic catch of oscillation / regression / external-edit footguns — *without* surrendering the per-finding triage discipline or the final-approval gate.

**Regression safety:** auto-testable via new tests (snapshot creation, hash-mismatch abort, verdict-footer parse, stop classifier on synthetic + recorded fixtures), plus the existing `tests/test_selftest_overlap.py` ensures Makefile↔template parity.

**Outcome measurement:** internal change — no business metric. Internal proxy: the iter count on the next medium plan (target: ≤ 5 vs the recent 17 — the structured stop classifier + loop-ack/loop-reset discipline should accelerate plateau detection). The (a) plan-mode exit count and (c) Codex token cost are out of scope here — they belong to the deferred Bucket A and F follow-up PRs.

## Scope

### IN-scope (this PR)

| # | Bucket | What lands |
|---|---|---|
| B | Plan-hash integrity check + explicit fold-ack + `loop-reset` | `Makefile` + `shared/Makefile.review.tmpl`: repo-aware `KEY` (`sha256(realpath(CURDIR)+":"+realpath(PLAN_FILE))[:12]`) keys all stateful artifacts. Before each integer iter, sha256 the plan; persist to `$(HASH_FILE)`. On mismatch, abort pointing the driver at consistency + `loop-ack` (legitimate fold) or `loop-reset` (start over). Consistency target writes `$(CONS_FILE)`. `loop-ack` requires `sha256(plan) == cons-marker` before restamping; runs consistency-until-no-drift (iter-6 F1 fold). |
| C | Per-iter snapshot | Same Makefile/template: before each integer-iter reviewer call, `cp "$(PLAN_FILE)" "$(SNAP_DIR)/iter$(ITERATION).bak"`. Rollback = `cp` back. |
| D | Structured verdict footer (plan-review only) | Extend the plan-review prompts only — `review-plan-by-codex` and `review-plan-by-claude` — to append a fenced JSON block: `{verdict, severity_counts:{3,2,1}, findings:[{id, importance, section_or_line, title, fingerprint}…]}`. `fingerprint` is the content-derived stable identity (iter-4 F3). Consistency self-check and commit reviews are NOT extended (existing consumer contracts). |
| E | Oscillation / stuck / regression detector | New script `scripts/loop-status.py` + matching `shared/scripts-loop-status.py.tmpl` (registered in `SHARED_TEMPLATE_MAP`; added to `EXECUTABLE_TARGETS`). `make loop-status PLAN_FILE=…`. Reads plan-review iter outputs **filtered by repo-aware `KEY`** (iter-6 F5 fold — basename-only globbing would let one repo's outputs poison another's classification). Output: `STATUS: needs-iter / converged / converged-with-polish / oscillating / stuck / regressed / malformed`. Identity via `fingerprint`. |

### NOT-in-scope (explicit rejects, with rationale)

| Rejected / Deferred | Why |
|---|---|
| **Bucket A: In-plan-mode Skill wrapper (DEFERRED)** | After 6 iters of folds, Bucket A surfaced 3 architectural blockers we don't have working answers for: (1) adopt-mode `.gitignore` parent-ignore neutralization — `APPEND_MERGE` cannot neutralize a parent `.claude/` ignore, and we don't have a `.gitignore`-rewrite mechanism (iter-6 F2); (2) my proposed `pre_skip_check` violates the manifest/atomic-write contract (iter-6 F3); (3) cross-direction + commit-review same-AI branching needs two distinct AskUserQuestion flows + 6 branches of acceptance verification (iter-5 F6, F7). **The impl-PR's commit 4 ADDS a `BACKLOG.md` entry "skill-wrapper-pr-followup"** capturing these blockers + the iter-1..6 F-series findings as starting requirements (iter-7 F2 fold — without this, the deferral has no durable record). *This plan PR is plan-only; the BACKLOG addition lands with the implementation PR, not here.* |
| **Bucket F: Continue-thread mode for Codex (DEFERRED)** | Bucket F needs (a) a real `codex exec --json` JSONL fixture captured to verify the session-id field name, and (b) a 3-assertion sandbox + cwd inheritance verification (V-13.5 strengthened in iter-5 F4). Both gates have to PASS before flipping the default. We don't want to gate the rest of the PR on capturing this fixture or running the verification. **The impl-PR's commit 4 ADDS a `BACKLOG.md` entry "continue-thread-pr-followup"** capturing the iter-1..5 F-series findings + the V-13/V-13.5 protocol as starting requirements (iter-7 F2 fold). |
| Auto-apply / Codex-driven fold classifier | Would gut the (a/b/c/d) + 4-question discipline that closes our highest-impact mistake-class (LESSONS.md 2026-05-17). Plan-tango's tradeoff is not ours. |
| Lock files / resume after Ctrl-C | Overkill for a single-driver workflow. |
| Opus final sanity-check (plan-tango `--final-check`) | Covered by our existing N.5 consistency self-check + Tier-1 commit review + Tier-2 bot review. |
| Removing the 6-surface byte-identity test for the triage block | Load-bearing (LESSONS.md 2026-05-25). |
| Further CLAUDE.md trim using downstream-app PR #22 taxonomy | Out of scope. Worth a separate trim PR. |
| Hard cap of 12 iters | We have the plateau rule + (once E lands) the structured stop classifier. |

## Subsystem breakdown


### Bucket B — Plan-hash integrity check

**File**: `shared/Makefile.review.tmpl` + mirror in `Makefile` (SELFTEST-OVERLAP block).

**Repo-aware artifact KEY (consistency 4.5 F2 + D-12 fold)**: ALL stateful `/tmp` artifacts in Buckets B / C / F derive their path from a single repo-aware key:

```make
# Defined once at the top of the review-targets section of Makefile.review.tmpl:
KEY = $(shell python3 -c "import hashlib,os; \
  k = os.path.realpath('$(CURDIR)') + ':' + os.path.realpath('$(PLAN_FILE)'); \
  print(hashlib.sha256(k.encode()).hexdigest()[:12])")
HASH_FILE       = /tmp/plan-review-$(KEY).hash
CONS_FILE       = /tmp/plan-review-$(KEY).consistency
SNAP_DIR        = /tmp/plan-snapshots/$(KEY)
```

Read-only review outputs (`/tmp/plan-review-<basename>-by-{codex,claude}-iter-*.md`) keep their existing basename naming — they're per-output, not stateful, and the existing convention is preserved for `make status` + Codex/Claude reviewers that already read these paths.

**Hash-check mechanic**: each review target gets a preamble (using the KEY-derived paths above):

```make
# Before invoking the reviewer:
CURR_HASH=$$(shasum -a 256 "$(PLAN_FILE)" | awk '{print $$1}')
if [ -f "$(HASH_FILE)" ]; then
  PREV_HASH=$$(cat "$(HASH_FILE)")
  if [ "$$CURR_HASH" != "$$PREV_HASH" ] && [ "$(ITERATION)" -gt 1 ]; then
    echo "Plan hash changed since iter $$(( $(ITERATION) - 1 )) — external edit or unacknowledged fold detected."
    echo "Expected: $$PREV_HASH"
    echo "Got:      $$CURR_HASH"
    echo "If this was a legitimate fold:"
    echo "  1) make review-plan-consistency-by-claude PLAN_FILE=$(PLAN_FILE) ITERATION=N.5"
    echo "  2) fold any drift the consistency check finds"
    echo "  3) make loop-ack PLAN_FILE=$(PLAN_FILE)"
    echo "  4) re-run this review target."
    echo "If you want to discard the loop and start over: make loop-reset PLAN_FILE=$(PLAN_FILE) (deletes hash/cons/thread state)."
    echo "Snapshots remain in $(SNAP_DIR)/."
    exit 2
  fi
fi
# Reviewer call here…
# After successful reviewer call:
echo "$$CURR_HASH" > "$(HASH_FILE)"
```

The hash is updated **after** the reviewer call succeeds. On `ITERATION=1` the check is skipped — first iter has no baseline.

**Scope of hash + snapshot (iter-2 F4 fold)**: the hash check + snapshot preamble is added ONLY to the integer plan-review targets (`review-plan-by-codex`, `review-plan-by-claude`). It is NOT added to `review-plan-consistency-by-claude` (which runs at iter `1.5`, `2.5`, …) — fractional iter values would break the `[ "$(ITERATION)" -gt 1 ]` shell integer check, AND the consistency check is meant to be lightweight + idempotent against a freshly-folded plan. Commit-review targets also skip the preamble (they review a commit, not a plan file).

**iter-1 F1 fold + iter-3 F4 fold — fold-ack with consistency-check enforcement**: the driver legitimately edits the plan between iters (folding findings). Without an ack step, iter 2's check would see the post-fold plan as an "external edit" and abort. Solution: introduce a `make loop-ack PLAN_FILE=…` target that re-stamps the hash file — but **with a consistency-marker precondition (iter-3 F4)** so the driver can't accidentally bless a folded-but-un-self-checked plan:

- The consistency target (`review-plan-consistency-by-claude`) writes a marker file `/tmp/plan-review-<slug>.consistency` containing `sha256(plan at time of consistency check)` after a successful run.
- `loop-ack` reads BOTH: the current plan hash AND the consistency marker. Before re-stamping the integrity hash, it asserts `sha256(plan) == consistency-marker contents`. If they differ (driver folded findings AFTER the last consistency check, or never ran consistency), `loop-ack` refuses with: "Plan has changed since last consistency check. Run `make review-plan-consistency-by-claude PLAN_FILE=… ITERATION=N.5` before acking."
- This makes the driver workflow's review → fold → consistency → fold drift → loop-ack → next sequence ENFORCED, not just documented.

```make
loop-ack:
	@test -n "$(PLAN_FILE)" || { echo "Usage: make loop-ack PLAN_FILE=docs/plans/<file>.md"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	@CURR_HASH=$$(shasum -a 256 "$(PLAN_FILE)" | awk '{print $$1}'); \
	  if [ ! -f "$(CONS_FILE)" ]; then \
	    echo "No consistency marker found at $(CONS_FILE)."; \
	    echo "Run \`make review-plan-consistency-by-claude PLAN_FILE=$(PLAN_FILE) ITERATION=N.5\` before acking."; \
	    exit 3; \
	  fi; \
	  CONS_HASH=$$(cat "$(CONS_FILE)"); \
	  if [ "$$CURR_HASH" != "$$CONS_HASH" ]; then \
	    echo "Plan has changed since last consistency check (cons=$$CONS_HASH, curr=$$CURR_HASH)."; \
	    echo "Run \`make review-plan-consistency-by-claude PLAN_FILE=$(PLAN_FILE) ITERATION=N.5\` before acking."; \
	    exit 3; \
	  fi; \
	  echo "$$CURR_HASH" > "$(HASH_FILE)"; \
	  echo "Acknowledged. Hash file: $(HASH_FILE) → $$CURR_HASH"
```

And the consistency target gets a one-line addition to write the marker:

```make
# At the end of review-plan-consistency-by-claude (after the cat ...):
@shasum -a 256 "$(PLAN_FILE)" | awk '{print $$1}' > $(CONS_FILE)
```

(Consistency 3.5 F6 fold — without this line, `loop-ack` would never find the marker and the gate would block every ack.)

**`loop-reset` target (iter-5 F2 fold)** — explicit, documented escape hatch (NOT a hidden bypass via "delete the hash file"):

```make
loop-reset:
	@test -n "$(PLAN_FILE)" || { echo "Usage: make loop-reset PLAN_FILE=docs/plans/<file>.md"; exit 1; }
	@rm -f "$(HASH_FILE)" "$(CONS_FILE)"
	@rm -rf "$(SNAP_DIR)"
	@echo "Loop state reset. Hash/consistency/snapshot artifacts removed for this plan."
	@echo "Next plan-review will start at iter 1 with no baseline."
```

This is the ONLY documented way to discard the integrity hash without going through `loop-ack`. The hash-mismatch abort message points users to `loop-reset` (for "start over") or to `consistency + loop-ack` (for "ack this fold") — never to "delete the hash file by hand".

**Driver workflow** (iter-2 F4 + iter-6 F1 fold — consistency-until-no-drift loop):
1. Run iter N review → hash file = `sha256(plan as reviewed)`
2. Driver triages + folds findings → plan file changes
3. **Consistency-until-no-drift loop** (iter-6 F1): repeat until consistency returns "no drift" or the driver decides nothing more is folding:
   - `make review-plan-consistency-by-claude PLAN_FILE=… ITERATION=N.5` — writes `$(CONS_FILE) = sha256(plan at this moment)`
   - If drift found AND driver wants to fold → fold the drift items → plan changes → `$(CONS_FILE)` is now stale → loop back to step (a)
   - If no drift OR driver accepts remaining items as not-worth-folding → exit loop, proceed
4. Driver runs `make loop-ack PLAN_FILE=…` → asserts `sha256(plan) == $(CONS_FILE)` (which is true because step 3's last consistency run wrote it against the current state). On success, restamps `$(HASH_FILE) = sha256(plan)`.
5. Driver runs iter N+1 review → hash check sees no mismatch → proceeds.

If step 4 ever fails (`$(CONS_FILE)` stale or missing), the message points back to step 3 — driver re-runs consistency and folds any new drift before retrying ack.

If the driver SKIPS step 3, iter N+1 aborts with the mismatch message — exactly the desired catch for "I forgot to ack" or "an external edit happened too". The cost of one extra command is acceptable for the discipline + safety net.

### Bucket C — Per-iter snapshot

**Scope** (consistency 2.5 F6 fold): same integer-only scoping as Bucket B's hash check — snapshot fires ONLY on `review-plan-by-codex` / `review-plan-by-claude` (integer iters). The consistency self-check (`ITERATION=N.5`) and commit-review targets are excluded — a reader who jumps straight to Bucket C should see the same constraint Bucket B documents.

**File**: same Makefile + template.

**Mechanic** (uses the repo-aware `KEY` from Bucket B — per D-12 / consistency 4.5 F2):

```make
mkdir -p "$(SNAP_DIR)"
SNAP_PATH="$(SNAP_DIR)/iter$(ITERATION).bak"
cp "$(PLAN_FILE)" "$$SNAP_PATH"
echo "Snapshot: $$SNAP_PATH"
```

Snapshot happens BEFORE the reviewer call — captures the plan as input to iter N. Rollback recipe printed at the start of each review output footer.

### Bucket D — Structured verdict footer (plan-review prompts only)

**iter-1 F4 fold — scope narrowed**: footer is added ONLY to the two plan-review prompts (`review-plan-by-codex`, `review-plan-by-claude`). NOT added to: consistency self-check (already returns a numbered contradictions list — adding JSON muddies that contract; loop-status doesn't read those anyway), commit reviews via `tier1_prompt` (already require a precise implementation-log table-row format; JSON would conflict + Tier-1 has no need for a stop classifier — it's a single-pass review).

**File**: extend the plan-review prompts in `shared/Makefile.review.tmpl`.

**Footer contract** (iter-2 F2 + iter-3 F3 fold — switched to 4-backtick outer fence to avoid double-fence parse confusion + restructured finding identification to a structured array so the classifier doesn't depend on title-stability): each plan-review reviewer is asked to APPEND (after the prose) a fenced JSON block AND also tag each prose finding with its `id`. The literal block in the reviewer output looks like:

````
```json-verdict
{
  "verdict": "needs-iter|converged|do-not-implement",
  "severity_counts": {"3": <N>, "2": <N>, "1": <N>},
  "key": "<the $(KEY) value from the Makefile — repo-isolating per iter-6 F5>",
  "findings": [
    {"id": "F1", "importance": 3, "section_or_line": "Bucket B:115", "title": "Hash check blocks legitimate folds", "fingerprint": "bucket-b-115:hash-check-blocks-legitimate-folds"},
    {"id": "F2", "importance": 3, "section_or_line": "Scope E + render.py:9", "title": "Missing shared script templates", "fingerprint": "render.py-9:missing-shared-script-templates"}
  ]
}
```
````

- `verdict` is the reviewer's call (mapped from existing prose: "ready after minor edits" → `converged`, "needs another iteration" → `needs-iter`, "do not implement yet" → `do-not-implement`).
- `severity_counts` lets the stop classifier mechanically see when imp-3 hits 0.
- **`findings` is the structured array (iter-3 F3 + iter-4 F3 fold).** Each entry has:
  - `id` — `F<N>` per-review cross-reference label, MATCHES the prose. **NOT used for identity** — it changes between iters as ordering/severity shifts.
  - `importance` — 3 / 2 / 1.
  - `section_or_line` — stable anchor (plan section + line, OR file:line of the cited problem).
  - `title` — one-line description, human-readable.
  - **`fingerprint`** — deterministic identity, of the form `<section-or-line-slug>:<title-slug>`, where slugs are `lower(replace_nonalpha("-")).strip("-")`. Reviewers compute this from the same `section_or_line` + `title` values they emit. The stop classifier uses `fingerprint` (NOT `id`) for oscillation/stuck identity. Two reviewers using identical anchors + titles produce identical fingerprints.
- The reviewer prompt requires each prose finding to begin with `**F<N> (importance N):**` matching the footer's `id`. The `id` is a prose convenience — the classifier doesn't depend on it.
- (Removed `pr_drift` field — was only set by consistency check, which is no longer in scope for the footer.)

**Parser**: tolerant — extracts the fenced block via regex, accepts trailing prose after it. Malformed JSON → `STATUS: malformed`. Missing block → `STATUS: footer-missing`. Both surfaced by the stop classifier so the driver sees the contract was breached.

**The prose stays.** The footer is *additive* — the driver still reads the prose to triage. The footer exists for the stop classifier and for future automation, not as a replacement for the human-readable finding list.

### Bucket E — Oscillation / stuck / regression detector

**File**: new `scripts/loop-status.py`, ~150 lines, PLUS its shared-template counterpart `shared/scripts-loop-status.py.tmpl` (registered in `bootstrap_lib/render.py`'s `SHARED_TEMPLATE_MAP` — **iter-1 F2 fold**: without registration, bootstrapped projects render a Makefile target calling a missing script). Plus `make loop-status PLAN_FILE=…` in `shared/Makefile.review.tmpl` (+ mirror).

**Inputs** (iter-6 F5 fold — repo-keyed): glob `/tmp/plan-review-<basename>-by-{codex,claude}-iter-*.md` then **filter by `$(KEY)` match** — each footer carries the `KEY` value the review was run against (added to the footer schema below). Outputs whose `KEY` doesn't match the current `$(KEY)` are skipped (they're from a different repo's plan that happens to share a basename). Consistency self-check outputs and commit-review outputs are NOT consumed. Parse footers. Build per-iter `{verdict, severity_counts, findings: [{id, importance, section_or_line, title, fingerprint}]}` records — `fingerprint` is required (`_identity` function uses it). Missing/malformed `fingerprint` on any finding → `STATUS: malformed`.

**Logic** (per plan-tango's stop conditions, adapted; consistency 3.5 F3 fold — rewritten to use the iter-3 F3 structured findings shape):

```python
def _identity(f):
    """Stable identity for a finding: the reviewer-emitted fingerprint.
    NOT (id, section_or_line) — F<N> ids are per-review labels and shift
    between iters (iter-4 F3 fix). Fingerprint is content-derived from
    section_or_line + title slugs, so it's stable across reviewers + iters."""
    return f["fingerprint"]

def classify(iters):
    if not iters:
        return "no-iters"
    last = iters[-1]
    counts = last["severity_counts"]
    if last["verdict"] == "converged" and sum(counts.values()) == 0:
        return "converged"
    if counts.get("3", 0) == 0 and counts.get("2", 0) + counts.get("1", 0) > 0:
        return "converged-with-polish"  # stop here, fold remaining as polish or BACKLOG
    if len(iters) >= 2:
        prev_ids = {_identity(f) for f in iters[-2]["findings"]}
        curr_ids = {_identity(f) for f in iters[-1]["findings"]}
        if prev_ids == curr_ids:
            return "stuck"
    if len(iters) >= 3:
        n_minus_2 = {_identity(f) for f in iters[-3]["findings"]}
        n_minus_1 = {_identity(f) for f in iters[-2]["findings"]}
        n = {_identity(f) for f in iters[-1]["findings"]}
        # findings that disappeared at N-1 and came back at N
        if any(ident in n_minus_2 and ident not in n_minus_1 and ident in n for ident in n):
            return "oscillating"
    if len(iters) >= 2 and counts.get("3", 0) > iters[-2]["severity_counts"].get("3", 0):
        return "regressed"
    return "needs-iter"
```

**Output**: prints `STATUS: <classification>` + a 1-line rationale. If `converged-with-polish` or `converged`, prints the recommended next step ("stop the loop and proceed to human approval; remaining N polish findings can be folded inline or parked to BACKLOG"). If `oscillating` / `stuck`, prints which finding fingerprints are doing it so the driver can investigate.

**The driver still decides whether to stop.** This script gives a mechanical signal; it does not BREAK the loop. The human-approval gate remains the only commit-blocking gate.


## Architecture decisions

| # | Decision | Alternative | Why we chose this |
|---|---|---|---|
| D-1 | Snapshots go to `/tmp/plan-snapshots/`, NOT `docs/plans/.snapshots/` | Checked-in snapshot dir | Plan history is already in git. `/tmp` is transient and matches the existing `/tmp/plan-review-*-iter-*.md` convention. No `.gitignore` churn. |
| D-12 | All `/tmp` stateful artifacts (hash, consistency, thread, snapshot) use a **repo-aware artifact key** (iter-4 F4 fold), NOT just `$(notdir $(basename $(PLAN_FILE)))` | Use basename-only (current iter-3 design) | Two repos can both have `docs/plans/2026-05-27-test.md`. Basename-only keying lets one loop poison another's hash/thread state. Repo-aware key: `KEY = sha256(realpath(CURDIR) + ":" + realpath(PLAN_FILE))[:12]`. All artifact paths derived from `KEY` instead of `$(notdir $(basename …))`. The existing read-only review-output globs (`/tmp/plan-review-<basename>-by-{codex,claude}-iter-*.md`) can stay basename-only — they're read-only output files, not stateful. The stateful set: hash, consistency, thread, snapshot dir — those switch to `KEY`. |
| D-2 | Verdict footer is JSON in a fenced block, NOT a separate file | Sidecar `<plan>.iter{N}.verdict.json` | Single artifact per iter is simpler to inspect by hand. Parser handles trailing-prose gracefully. |
| D-5 | Stop classifier prints STATUS but does NOT exit non-zero on `oscillating` / `stuck` | Make it fail the build | Detector is advisory. Driver decides. Failing the build would make the script unsafe to wire into hooks. |
| D-6 | Triage block byte-identity test stays | Replace with pointer-based single-source | The 6-surface duplication is the cost of being a skill that bootstraps OTHER projects. The test is cheap; drift is expensive. LESSONS.md 2026-05-25 captured this. |
| D-8 | Approval-gate wording in CLAUDE.md is path-agnostic ("explicit user approval"), with the keyword enumeration moved to `docs/plans/README.md` step 3 | Branched per-path wording | Keeps CLAUDE.md tight (≤2 lines added: Commands-table entries for `loop-status` / `loop-ack` / `loop-reset` + the keyword swap). Prepares the wording for the deferred Skill PR (Bucket A) which will need the path-agnostic generalization. AGENTS.md is NOT in scope (iter-3 F5 — no gate paragraph to swap). |
| D-9 | Hash check uses an explicit `make loop-ack` after folds, NOT auto-detection | Auto-detect via Edit-tool hooks, or skip the integrity check entirely | **iter-1 F1 fold**: legitimate folds and unintended external edits are indistinguishable by file diff. Explicit ack is the only honest signal. Cost is low. |
| D-10 | Verdict footer added to plan-review prompts only, NOT consistency or commit reviews | Add footer to all reviewer outputs uniformly | **iter-1 F4 fold**: consumer (loop-status) only reads plan-review files; consistency check has its own list-of-contradictions contract; commit reviews have the implementation-log row contract. |

## Risks + mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Stop classifier sees ambiguous footer (malformed JSON, missing fields) and the driver stops trusting it | imp-2 | Tolerant parser. On `malformed` / `footer-missing`, print explicit "reviewer did not produce a valid footer; falling back to prose-only stop signal" + the raw last 200 chars. |
| Snapshot dir `/tmp/plan-snapshots/$(KEY)/` is volatile (cleared on reboot) | imp-1 | Acceptable. Snapshots are mid-loop rollback aid, not long-term audit (the evidence table in the plan is the audit trail). |
| Bucket D footer-prompt extension makes Codex reviews longer (more tokens, slower) | imp-1 | Footer is ~150 tokens. Acceptable for the value of mechanical stop. |
| **iter-1 F1**: driver forgets to run `make loop-ack` after a fold and iter N+1 aborts with mismatch | imp-2 | The abort message explicitly mentions the consistency + `loop-ack` workflow. After 2-3 cycles the driver builds the habit. Worst case = one wasted abort cycle per session; the snapshot in `$(SNAP_DIR)` is preserved. |
| **iter-1 F2 + iter-2 F3**: bootstrap-rendered project tries to use `make loop-status` but `scripts/loop-status.py` is missing OR not executable | imp-3 (before fold) → imp-1 (after fold) | Shared template `shared/scripts-loop-status.py.tmpl` registered in `SHARED_TEMPLATE_MAP`. Rendered path added to `bootstrap_lib/manifest.py:EXECUTABLE_TARGETS`. |
| **iter-2 F4**: hash check fires on consistency self-check iter `1.5` and breaks the `-gt 1` shell integer check | imp-3 (before fold) → imp-1 (after fold) | Hash + snapshot preamble scoped to integer plan-review targets only. Consistency target unchanged. Driver workflow: review → fold → **consistency-until-no-drift** → `loop-ack` → next integer review (iter-6 F1 refined the consistency step to a loop). |
| **iter-6 F1**: `loop-ack` deadlocks if the consistency check itself surfaces drift that the driver folds | imp-3 (before fold) → imp-1 (after fold) | `loop-ack` requires `sha256(plan) == $(CONS_FILE)`. The driver runs consistency-until-no-drift in step 3 of the workflow — every fold of consistency-surfaced drift requires a fresh consistency run before ack. Documented in Bucket B workflow steps 3-4. |
| **iter-6 F5**: `loop-status` could read another repo's review outputs that share a plan basename | imp-2 | Footer now carries a `key` field; classifier filters review outputs by `$(KEY)` match. Outputs from other repos are skipped. |

## Verification

(V-1, V-1.5, V-2.1, V-2.2's Skill-side assertions, V-13, V-13.5, V-14, V-15, V-21 deferred along with Buckets A + F to the follow-up PRs. V-2.2's helper-script render assertion stays — Bucket E ships in this PR. V-20 stays — iter-7 F4 fold: the CLAUDE.md keyword-swap docs change in commit 4 is in-scope, so V-20 must verify it; only the Skill-specific part of V-20 was deferred.)

| # | What | How |
|---|---|---|
| V-2.2 | Helper script (`scripts/loop-status.py`) renders + is executable in bootstrapped project | Bootstrap a python project via `dev-project-setup` into `/tmp/dev-test/`, confirm the script exists and has execute bit; run `make loop-status PLAN_FILE=<dummy>` in the bootstrapped project — expect graceful "no iters" output, not a missing-script error. |
| V-3 | Snapshot created before each integer iter | `tests/test_review_loop_artifacts.py` — run a stubbed review with FAKE `codex` AND `claude` executables on `PATH` (iter-7 F3 fold — both binaries need mocking; the real CLI tests are reserved for manual smoke). Assert `$(SNAP_DIR)/iter1.bak` exists and equals the input plan. |
| V-4 | Hash check aborts on UNACKNOWLEDGED external modification (iter-1 F1 fold) | `tests/test_review_loop_artifacts.py` — run iter 1, manually edit the plan WITHOUT running `loop-ack`, run iter 2, assert exit code 2 and the abort message mentioning `make loop-ack`. |
| V-4.5 | Legitimate driver-fold + consistency-check + `loop-ack` succeeds | Same test file, FAKE `codex` + `claude` on `PATH` (iter-7 F3) — run iter 1, edit the plan (simulated fold), run `make review-plan-consistency-by-claude PLAN_FILE=… ITERATION=1.5` (writes the marker), run `make loop-ack PLAN_FILE=…`, run iter 2, assert success AND hash file now equals `sha256(plan post-fold)`. ALSO assert that skipping the consistency step before ack makes `loop-ack` exit 3 with the "no consistency marker" / "plan changed since marker" message. |
| V-5 | Hash check skipped on `ITERATION=1` | Same — run iter 1 with NO hash file present, assert success. |
| V-6 | Verdict footer parser handles well-formed JSON | `tests/test_loop_status.py` — fixture file with valid footer → parser returns expected dict. |
| V-7 | Verdict footer parser handles malformed JSON | Same — fixture with invalid JSON → `STATUS: malformed`. |
| V-8 | Verdict footer parser handles missing block | Same — fixture with prose only → `STATUS: footer-missing`. |
| V-9 | Stop classifier: `converged-with-polish` | Synthetic fixture: 3 iters, last has imp-3=0, imp-2=2 → classify returns `converged-with-polish`. |
| V-10 | Stop classifier: `oscillating` | Synthetic fixture: iter N-2 has finding `fingerprint` X, iter N-1 doesn't, iter N has X back → returns `oscillating` with the offending fingerprint. (Consistency 3.5 F8 + iter-4 F3 fold: "hash" → "identity" → "fingerprint" terminology aligned with the Bucket D footer schema.) |
| V-11 | Stop classifier: `stuck` | Synthetic fixture: iter N-1 fingerprints == iter N fingerprints → returns `stuck`. |
| V-12 | Stop classifier: `regressed` | Synthetic fixture: imp-3 count grew → returns `regressed`. |
| V-16 | `make loop-status PLAN_FILE=…` exits 0 on `converged` and `converged-with-polish`; exits non-zero on `malformed` only | Direct invocation test in `tests/test_loop_status.py`. Globs only plan-review files (per Bucket D narrowed scope); filters by footer `key` match (iter-6 F5); ignores consistency + commit-review files in `/tmp/`. |
| V-16.5 | `make loop-status` ignores review-output files from OTHER repos with the same plan basename (iter-6 F5 fold) | `tests/test_loop_status.py` — drop a synthetic plan-review iter file with a NON-matching `key` field into `/tmp/`; assert it's filtered out and does NOT influence the classification. |
| V-17 | Existing `tests/test_selftest_overlap.py` still passes | The Makefile changes mirror the template changes 1:1. |
| V-18 | Existing `tests/test_triage_byte_identity.py` still passes | We don't touch the triage block. |
| V-19 | Existing `tests/test_dogfood_doc_sanity.py` still passes | We don't trim any pinned sections. The CLAUDE.md gate paragraph gets ONE keyword swap (consistency 3.5 F5 fold — "expands" wording from iter-1 was stale once iter-3 narrowed the change to a single swap); heading + bullet markers untouched. |
| V-20 | `docs/plans/README.md` step 3 names BOTH delivery mechanisms; CLAUDE.md stays path-agnostic | Light grep test in `tests/test_dogfood_doc_sanity.py`: assert `docs/plans/README.md` step-3 block mentions both "ExitPlanMode" (or "plan-mode") AND a chat-keyword phrase; assert CLAUDE.md gate paragraph does NOT enumerate either (it pointers-out to step 3). |
| V-22 | `BACKLOG.md` carries durable entries for the deferred Buckets A + F (iter-7 F2 fold) | `tests/test_dogfood_doc_sanity.py` grep: assert `BACKLOG.md` contains both `skill-wrapper-pr-followup` and `continue-thread-pr-followup` headings + a "Trigger" / "Starting requirements" subsection in each + references to the iter-1..6 F-series finding-numbers. |

## Implementation rollout

One PR, 4 focused commits (one per bucket + one for docs). Each commit lands the template change AND the rendered-into-root mirror in lockstep so `test_selftest_overlap.py` stays green at every commit.

| Commit | Bucket | Files |
|---|---|---|
| 1 | B + C — Hash + snapshot + `loop-ack` + `loop-reset` + consistency-marker | `shared/Makefile.review.tmpl` (5 changes: `KEY` derivation block, hash check pre-review, snapshot pre-review, `loop-ack` target with consistency-marker precondition + iter-6 F1 consistency-until-no-drift loop, `loop-reset` target, one-line addition to `review-plan-consistency-by-claude` target to WRITE the marker), `Makefile`, tests for V-3 / V-4 / V-4.5 / V-5 |
| 2 | D — Verdict footer (plan-review prompts only) | `shared/Makefile.review.tmpl` (extend only `review-plan-by-codex` + `review-plan-by-claude` prompts with the `findings: [{id, importance, section_or_line, title, fingerprint}…]` footer per iter-4 F3 / iter-5 F3), `Makefile`, tests for V-6 / V-7 / V-8 |
| 3 | E — Stop classifier | `scripts/loop-status.py` (new, uses `fingerprint` identity + filters review-output files by `KEY` per iter-6 F5), `shared/scripts-loop-status.py.tmpl` (new, registered in `SHARED_TEMPLATE_MAP`), `bootstrap_lib/manifest.py` (add `scripts/loop-status.py` to `EXECUTABLE_TARGETS`), `shared/Makefile.review.tmpl` (`make loop-status` target), `Makefile`, tests for V-9 / V-10 / V-11 / V-12 / V-16 |
| 4 | Docs + BACKLOG | `CLAUDE.md`: 1-line additions to Commands table for `loop-status`, `loop-ack`, `loop-reset`. The "Mandatory human-approval gate" paragraph gets ONE keyword swap — "wait for **approve** / **changes: …** / **read full file first**" → "wait for **explicit user approval**" (path-agnostic, prepares for the deferred Skill PR). `CONTRIBUTING.md`: 2-line note documenting the new make targets in the per-change workflow. `docs/plans/README.md` step 3: expanded to enumerate two delivery mechanisms (plan-mode UI + chat keyword) — only file that grows. **`BACKLOG.md` (iter-7 F2 fold): add 2 entries — `skill-wrapper-pr-followup` and `continue-thread-pr-followup` — each with trigger conditions + the iter-1..6 F-series findings as starting requirements.** Triage block + dogfood-pinned headings UNTOUCHED. Mirror keyword swap to `shared/CLAUDE.md.tmpl`; mirror step-3 expansion to `shared/docs-plans-README.md.tmpl`. `shared/AGENTS.md.tmpl` UNTOUCHED (per iter-3 F5). Confirm `tests/test_triage_byte_identity.py` + `tests/test_dogfood_doc_sanity.py` still pass. |

After commit 4, run `make check` and `make test` to confirm the full test surface still green.

## Manual smoke (post-merge, before declaring the PR done)

1. Create a 3-line throwaway plan at `docs/plans/2026-05-27-test-loop-harvest.md`.
2. From a terminal, run `make review-plan-by-codex PLAN_FILE=docs/plans/2026-05-27-test-loop-harvest.md ITERATION=1`. (No plan-mode Skill in this PR scope — that's the deferred Bucket A.)
3. Confirm `$(SNAP_DIR)/iter1.bak` exists (SNAP_DIR = `/tmp/plan-snapshots/$(KEY)`).
4. Confirm `$(HASH_FILE)` exists.
5. Confirm the review output ends with a `json-verdict` fenced block containing `findings: [{…, fingerprint}…]`.
6. Run `make loop-status PLAN_FILE=docs/plans/2026-05-27-test-loop-harvest.md` — expect `STATUS: needs-iter` or `converged-with-polish`.
7. **Legitimate-fold path**: edit the plan (simulate a fold), run `make review-plan-consistency-by-claude PLAN_FILE=… ITERATION=1.5` (writes `$(CONS_FILE)`), then `make loop-ack PLAN_FILE=…`, then run iter 2 — expect success AND new hash stored.
8. **Loop-ack-deadlock avoidance (iter-6 F1)**: simulate a consistency-check finding drift — after the step-7 fold, edit the plan AGAIN before running `loop-ack`. Expect `loop-ack` exit 3 with "plan changed since marker". Re-run consistency, then `loop-ack` — expect success.
9. **External-edit path**: edit the plan WITHOUT consistency or `loop-ack`, run iter 3 — expect hash-mismatch abort + abort message points to consistency + `loop-ack` + `loop-reset` (NOT "remove the hash file by hand").
10. **`loop-reset` path**: `make loop-reset PLAN_FILE=…` — expect `$(HASH_FILE)` / `$(CONS_FILE)` / `$(SNAP_DIR)` removed; next review starts fresh.
11. **Cross-repo isolation (iter-6 F5)**: in a sibling repo with a plan of the same basename, run the same review targets — verify artifact files are at different `$(KEY)`-derived paths (no collision).
12. Delete the throwaway plan file + the `/tmp` artifacts.

## Rollback

- If Bucket D (footer) breaks reviews because Codex/Claude refuse the format: revert commit 2. B/C/E still functional. `loop-status` falls back to `STATUS: footer-missing` until the footer is restored.
- If Bucket E (`loop-status`) misclassifies: the script is advisory — drivers can ignore its output and apply the plateau rule by reading the prose. Revert commit 3 only if the script actively breaks the build (it doesn't gate anything by design — D-5).
- Bucket B's `loop-ack` / `loop-reset` mechanics are scoped to integer plan-review targets; reverting commit 1 doesn't affect consistency or commit reviews.
- Full revert: `git revert <merge-commit>`. `/tmp` artifacts (`$(HASH_FILE)`, `$(CONS_FILE)`, `$(SNAP_DIR)`) are unobtrusive; no migration needed.

## Iteration log (this plan)

| Iter | Reviewer | Date | Counts (3/2/1) | Verdict | Notes |
|---|---|---|---|---|---|
| 1 | Codex (main) | 2026-05-27 | 3 / 3 / 0 | do not implement yet | All 6 folded as (a). F1 (imp-3) hash-check vs legitimate folds → added `make loop-ack` + D-9 + V-4.5. F2 (imp-3) missing shared script templates → added `shared/scripts-loop-status.py.tmpl` + `shared/scripts-extract-codex-session-id.sh.tmpl` + SHARED_TEMPLATE_MAP registration + V-2 extension. F3 (imp-3) `.gitignore` ignores `.claude/` → added precise unignore + bootstrap-side mirror + V-1.5. F4 (imp-2) verdict footer scope too broad → narrowed Bucket D to plan-review only + D-10 + removed `pr_drift` field. F5 (imp-2) Codex JSON schema unverified → flipped `THREAD_MODE` default to `fresh` + added fixture-capture pre-step + D-3 rewritten. F6 (imp-2) Skill claim verified too late → added pre-merge acceptance gate after commit 1 + D-11 + contingency in Rollback. Implementation rollout commits 1, 4, 5 grew; commit 3 narrowed. New risk rows for F1/F2/F3/F5/F6. |
| 1.5 | Claude (consistency self-check) | 2026-05-27 | doc-drift × 7 | folded | F1 SKILL.md sample wrap-list missing `loop-ack` → added. F2 V-2 too early in commit 1 (helper scripts not yet rendered) → split into V-2.1 (commit 1) + V-2.2 (commit 5). F3 "6 commits" header vs conditional 5b → updated to "6-7 commits" + new commit-5b row added to the rollout table. F4 Rollback wording denied default-flip path → reworded "pre-5b default is fresh, post-5b is continue". F5 SKILL.md "When to use" plan-only but wraps commit-review → broadened the "When to use" condition. F6 Bucket A omits SKILL template's SHARED_TEMPLATE_MAP registration → added explicit subsection. F7 D-8 "~0 lines" vs commit-6 "1-line pointer" → softened to "≤2 lines". No new V entries. |
| 2 | Codex (main) | 2026-05-27 | 4 / 3 / 0 | do not implement yet | All 7 folded as (a). F1 (imp-3) `.gitignore` child-unignore doesn't override parent-dir ignore → corrected to parent-safe `.claude/*` + child reincludes pattern (5-line block). F2 (imp-3) nested triple-backtick fence breaks Markdown → outer fence switched to 4-backticks. F3 (imp-3) `EXECUTABLE_TARGETS` missing the new scripts → added to `bootstrap_lib/manifest.py:EXECUTABLE_TARGETS`; V-2.2 extended with `os.access(X_OK)`. F4 (imp-3) hash/ack fires on iter `1.5` consistency and breaks `-gt 1` → scoped hash + snapshot to integer plan-review targets only; driver workflow now explicitly includes consistency between fold and ack. F5 (imp-2) Skill ships with targets that don't exist at commit 1 → Skill wrap-list grows incrementally: commit-1 = existing targets only, commit-2 adds `loop-ack`, commit-4 adds `loop-status`. F6 (imp-2) no parity test for new Skill template ↔ dogfood → V-21 added. F7 (imp-2) `AskUserQuestion` promised but not in `allowed-tools` → added. New risk rows for F4/F6/F7. |
| 2.5 | Claude (consistency self-check) | 2026-05-27 | doc-drift × 6 | folded | F1 Scope row A stale ("1-line" unignore) → updated to "parent-safe 5-line block". F2 rollout commits 2/4 didn't list Skill files for the wrap-list growth → added to file lists. F3 rollout commits 4/5 didn't list `manifest.py` for `EXECUTABLE_TARGETS` → added. F4 evidence iter-1 F2 referenced stale "V-2"/"V-2 extension" → relabelled to V-2.2 (for F2 row) and V-2.1 (for F3 row). F5 Makefile line range mismatch (94-209 vs 80-209) → standardized on 80-209 (the SELFTEST-OVERLAP block start). F6 Bucket C didn't restate integer-only scoping → added explicit scope subsection cross-referencing Bucket B. No new V entries. |
| 3 | Codex (main) | 2026-05-27 | 4 / 3 / 0 | do not implement yet | All 7 folded as (a). F1 (imp-3) `.gitignore` "writes/appends" violates manifest contract → split into greenfield (`shared/.gitignore.tmpl`, normal write) + adopt-mode (`shared/.gitignore.append.tmpl` via `APPEND_MERGE`). F2 (imp-3) `codex exec resume` may lose `-C` + `--sandbox` flags → defensively re-pass them; added V-13.5 sandbox write-test gate. F3 (imp-3) finding-hash contract too vague → restructured footer to `findings: [{id, importance, section_or_line, title}]`; classifier uses `id + section_or_line`; prose tagged with `**F<N> (importance N):**`. F4 (imp-3) `loop-ack` doesn't enforce consistency → consistency target writes `/tmp/plan-review-<slug>.consistency` marker; `loop-ack` requires `sha256(plan) == marker` before restamping. F5 (imp-2) AGENTS.md has no approval-gate paragraph → removed from keyword-swap scope; D-8 + V-20 + commit 6 + `shared/AGENTS.md.tmpl` references updated. F6 (imp-2) V-21 not assigned to a rollout commit → added to commit 1. F7 (imp-2) `make check` sequenced too early → moved to after commit 6 / 5b. |
| 3.5 | Claude (consistency self-check) | 2026-05-27 | doc-drift × 8 | folded | F1 Bucket A approval-gate paragraph still listed AGENTS.md → removed. F2 Bucket B loop-ack Makefile snippet didn't implement the consistency-marker precondition that the prose required → snippet rewritten + consistency target gets the marker-write line. F3 Bucket E classifier pseudocode still operated on `iters[-1].fingerprints` not the new `findings: [{id, …}]` shape → pseudocode rewritten with `_identity(f) = (id, section_or_line)`. F4 V-4.5 + Manual smoke step 7 didn't include the consistency call between fold and ack → both updated to include it + verify the skip case. F5 V-19 said "expands the section" but commit 6 narrowed to a 1-keyword swap → V-19 wording corrected. F6 commit 2 didn't enumerate the consistency-target marker-write Makefile change → added. F7 V-13 vs commit 5b mentioned only one gate (V-13) but iter-3 F2 added a second (V-13.5) → V-13 + V-13.5 + 5b row updated. F8 V-10 still said "hash X" → updated to "identity (id, section_or_line)". No new V entries. |
| 4 | Codex (main) | 2026-05-27 | 3 / 2 / 0 | do not implement yet | imp-3 dropped from 4 → 3 — first downward step. All 5 folded as (a). F1 (imp-3) `.gitignore` shared-template idea conflicts with renderer's per-language `.gitignore.tmpl` map → edit the 3 language templates directly with the unignore block; drop `shared/.gitignore.tmpl` + `shared/.gitignore.append.tmpl`. F2 (imp-3) iter-3 F2 over-defensive `-C/--sandbox` flags on `codex exec resume` are CLI-rejected (verified) → reverted; rely on inheritance + V-13.5 verifies. **LESSON surfaced** (in `## Lessons surfaced`): over-defensive folds can introduce new imp-3. F3 (imp-3) `F<N>` not stable for identity → added `fingerprint` field (`<section-slug>:<title-slug>`); classifier uses `fingerprint`, not `id`. Scope row D updated to mention `findings` not `finding_fingerprints`. F4 (imp-2) `/tmp` artifact keys collide across repos → D-12 added; all stateful artifacts use `KEY = sha256(realpath(CURDIR)+":"+realpath(PLAN_FILE))[:12]`. F5 (imp-2) Skill doesn't encode cross-direction rule → added explicit AskUserQuestion branching; Skill never offers "run both". |
| 4.5 | Claude (consistency self-check) | 2026-05-27 | doc-drift × 8 | folded | F1 commit 1 file list still listed dropped `shared/.gitignore.tmpl` etc → replaced with the 3 `languages/*/.gitignore.tmpl` paths. F2 D-12's `KEY` not propagated into Bucket B/C/F snippets → added `KEY` definition block at top of Bucket B; all snippets now reference `$(KEY)`-derived paths (`HASH_FILE`, `CONS_FILE`, `THREAD_FILE`, `SNAP_DIR`). F3 evidence iter-4 F4 overstated V-item updates → clarified the V items reference paths that resolve through `$(KEY)`. F4 Risk F3 "Bootstrap step appends…" wording → replaced with "5-line block lives inside each language's `.gitignore.tmpl`". F5 Scope row A wording stale (shared-template/append framing) → rewrote to "block lives inside each language's `.gitignore.tmpl`; adopt-mode handled by existing `APPEND_MERGE`". F6 V-13 cross-reference "iter-3 F2 read-only-sandbox verification" → reworded: V-13.5 is now the PRIMARY inheritance verification, not "defensive backup". F7 D-8 "≤2 lines" vs commit 6 "~0 lines" → reconciled with "≤2 added gross / ~0 net" framing. F8 evidence iter-3 F3 reads as current-state → tagged `[SUPERSEDED by iter-4 F3]`. No new V entries. |
| 5 | Codex (main) | 2026-05-27 | 4 / 3 / 0 | do not implement yet | All 7 folded as (a). F1 (imp-3) adopt-mode `.claude/` still broken — `adopt.py:415` SKIPs the Skill before `.gitignore` rewrite → added two-pass adopt logic (`.gitignore` first, then SKIP-rescan + Skill write). F2 (imp-3) hash-abort message bypasses `loop-ack` via "remove $(HASH_FILE)" advice → rewrote abort message to require consistency + loop-ack; added explicit `make loop-reset` target as the documented escape hatch. F3 (imp-3) Bucket E input schema missing `fingerprint` → added; malformed/missing → `STATUS: malformed`. F4 (imp-3) V-13.5 file-absence false-pass → strengthened to require sandbox-denial event + cwd assertion + file absence (all 3 must pass). F5 (imp-2) V-1 contingency contradicts rollout — commits 2/4/6 still touch Skill → contingency rewritten to "cancel + replan" (commits 2/4/6 don't ship without commit 1). F6 (imp-2) V-1 only tested one branch → V-1 now tests Claude / Codex / Other branches separately. F7 (imp-2) commit-review under-specified → added commit-review same-AI branching to the Skill (LESSONS.md 2026-05-19); Skill NEVER offers cross-AI Tier-1. |
| 5.5 | Claude (consistency self-check) | 2026-05-27 | doc-drift × 10 | folded | F1/F2/F3 evidence rows for iter-1 F3, iter-3 F1, iter-3 F2 missing `[SUPERSEDED]` tags → added (matching the iter-3 F3 convention). F4 commit 1 file list missing `bootstrap_lib/adopt.py` (required by iter-5 F1 two-pass adopt) → added. F5 Scope row F cited only V-13 for the default flip → added V-13.5. F6 D-3 same omission → added V-13.5 + sandbox-inheritance framing. F7 V-1 + pre-merge gate only verified plan-review branching, not commit-review → manual smoke rewritten with both paths (3 branches each). F8 same omission on post-merge manual smoke → fixed in F7's rewrite. F9 D-8 "Skill +" enumeration vs "≤2 lines" arithmetic mismatch → kept as-is. F10 Iteration log row 1 narrative still cites "V-2 extension" → kept (historical narrative). No new V entries. |
| 6 | Codex (main) | 2026-05-27 | 3 / 2 / 0 | do not implement yet | iter-3 F4 loop-ack mechanic revealed a fundamental hole: `loop-ack` deadlocks if consistency finds drift (marker is now stale). F2: my iter-5 F1 adopt-mode fix was still wrong (`APPEND_MERGE` can't NEUTRALIZE a parent `.claude/` ignore). F3: proposed `pre_skip_check` violates atomic-write/restore contract. F4/F5: smaller imp-2 finds (V-1 branch coverage, loop-status repo-keying). **DECISION POINT — split PR**: after 6 iters of folds + 5 consistency checks failed to plateau (imp-3: 3→4→4→3→4→3), Bucket A's adopt.py architectural blockers (F2 + F3) are too large for this PR. Scope NARROWED to B/C/D/E. Bucket A + Bucket F deferred to follow-up PRs with iter-1..6 findings as starting requirements. Only iter-6 F1 (loop-ack-deadlock → consistency-until-no-drift loop) and F5 (loop-status repo-keyed inputs via footer `key` field) folded into the surviving scope. F2/F3/F4 are captured in the deferred A/F BACKLOG entries. |
| 6.split | Driver (post-loop replan) | 2026-05-27 | n/a — scope decision | applied | Restructured the plan: removed Bucket A + F section bodies (~140 lines deleted); IN-scope table reduced to B/C/D/E; NOT-in-scope table now lists A + F as DEFERRED with their iter-1..6 finding-numbers; Implementation rollout reduced from 6-7 commits to 4 commits; Pre-merge acceptance gate (Bucket-A-specific) deleted; Manual smoke rewritten without Skill steps; Rollback rewritten without A/F contingencies. Plan length dropped from ~570 to ~450 lines. |
| 6.5 | Claude (consistency self-check) | 2026-05-27 | doc-drift × 14 | folded | The split introduced large drift between IN-scope (B/C/D/E) and the Architecture/Risks/Verification/Outcome sections which still treated A/F as in-scope. Folded: dropped D-3 / D-4 / D-7 / D-11 (Skill/Continue-thread-specific); reworded D-8 to reflect docs-only scope; trimmed Risks to 8 entries (from 16); Verification preamble lists deferred V items; Outcome measurement (a)+(c) acknowledged as deferred. |
| 7 | Codex (main) | 2026-05-27 | 3 / 2 / 1 | do not implement yet | All 6 folded as (a). F1 (imp-3) split cleanup incomplete — Bucket F leftovers (`THREAD_FILE`, `extract-codex-session-id.sh`, `codex-json-session.jsonl` fixture) still in active sections → removed from Bucket B `KEY` block, Bucket E description, `loop-reset` snippet, manual smoke. F2 (imp-3) BACKLOG entries referenced but not actually added → commit 4 file list now includes `BACKLOG.md` with 2 entries + V-22 enforces presence via test. F3 (imp-3) V-3 / V-4.5 use real `claude` CLI → both updated to require fake `codex` AND `claude` on `PATH` for the automated path. F4 (imp-2) V-20 listed as both deferred AND active → preamble clarified; V-20 stays in scope for the docs swap, only Skill-specific assertion deferred. F5 (imp-2) legacy/no-footer outputs from other repos → noted as edge case; basename-only outputs without footer get `STATUS: footer-missing` and are not classified as same-repo (matches existing Bucket D parser contract). F6 (imp-1) stale "hashes" terminology + broken local link → renamed to "fingerprints"; absolute path link fixed. |
| Tier-2 | claude[bot] (post-push review) | 2026-05-27 | 1 / 1 / 1 | needs minor edits | F1 (imp-3): bot claimed missing BACKLOG entries are a "broken implementation contract". **Rejected (c)** — bot misframed plan-PR vs impl-PR scope. The plan body explicitly states "impl-PR's commit 4 ADDS…"; PR description says "plan-only PR". Added a 1-word clarification ("impl-PR's commit 4") to NOT-in-scope rows for extra explicitness. F2 (imp-2): external absolute path is brittle. **Folded (a)** — added "external reference — may not be accessible" caveat + noted that the inline Iteration log restates the relevant trajectory data. F3 (imp-1): bot self-rejected ("acceptable as-is"). **No action.** Codex Tier-2 not triggered (draft PR). |

## Evidence table — what was folded and where

| Source | Finding | Importance | Resolution | Touched sections |
|---|---|---|---|---|
| Codex iter-1 F1 | Hash check blocks legitimate folds between iters | 3 | Added `make loop-ack` mechanic; abort message names the ack command; Skill exposes loop-ack as a button. Driver workflow now: review → fold → ack → next review. | Scope row B; Bucket B mechanics (new fold-ack subsection); D-9 (new); Risks (F1 row); V-4 rephrased ("UNACKNOWLEDGED external mod"); V-4.5 (new); Manual smoke steps 7-8; Implementation rollout commit 2; Iteration log; Evidence table |
| Codex iter-1 F2 | `SHARED_TEMPLATE_MAP` does not register the new helper scripts → bootstrapped projects render a broken Makefile | 3 | Added `shared/scripts-loop-status.py.tmpl` + `shared/scripts-extract-codex-session-id.sh.tmpl`; both registered in `SHARED_TEMPLATE_MAP`. V-2.2 extended to assert render + executability in bootstrapped projects. | Scope rows E + F; Bucket E (template counterpart); Bucket F (template counterpart); V-2.2; Risks (F2 row); Implementation rollout commits 4 + 5; Critical files |
| Codex iter-1 F3 | `.gitignore:46` ignores `.claude/` entirely — Skill never lands in git | 3 | Added precise unignore block (parent-safe `.claude/*` + child reincludes). **[SUPERSEDED by iter-4 F1]** — initial fold proposed a separate `shared/.gitignore.tmpl` append step; iter-4 F1 corrected to embedding the block inside each language's `.gitignore.tmpl`. **[FURTHER SUPERSEDED by iter-5 F1]** — adopt-mode required a two-pass `adopt.py` change. V-1.5 (new) still asserts `git check-ignore` returns no match (unchanged). | Scope row A; Bucket A (new `.gitignore` subsection); V-1.5 (new); V-2.1; Risks (F3 row); Implementation rollout commit 1; Rollback note |
| Codex iter-1 F4 | Verdict footer added to consistency + commit reviews would conflict with existing consumer contracts | 2 | Narrowed Bucket D scope to plan-review prompts only (`review-plan-by-codex`, `review-plan-by-claude`). Removed `pr_drift` field (was only set by consistency check). Bucket E inputs scope updated. | Scope row D + E; Bucket D heading + exclusion paragraph; Bucket E inputs paragraph; D-10 (new); V-16 (glob scope); Implementation rollout commit 3 |
| Codex iter-1 F5 | Bucket F's `session_id` JSONL schema is only stub-tested — real field name may differ | 2 | Flipped `THREAD_MODE` default from `continue` to `fresh` for v1. Added pre-commit-5 fixture-capture step (real `codex exec --json` output saved to `tests/fixtures/codex-json-session.jsonl`). V-13 reads the real fixture. Default flip to `continue` deferred to commit 5b after V-13 passes. | Scope row F; Bucket F mechanics (default flip + fixture); D-3 rewritten; Risks (F5 row); V-13 rewritten; Implementation rollout commit 5 (+ new commit 5b) |
| Codex iter-1 F6 | Bucket A's plan-mode-from-Skill claim only verified in post-merge smoke — risk of dead wrapper | 2 | Added pre-merge acceptance gate (new section) that runs after commit 1 and BEFORE commits 2-6. Contingency in Rollback re-scopes Bucket A to a terminal orchestrator if gate fails. D-11 documents the decision. | Bucket A (new pre-merge gate paragraph); D-11 (new); Risks (F6 row); Pre-merge acceptance gate (new section, before Manual smoke); Rollback (contingency paragraph); Implementation rollout commit 1 (PAUSE marker) |
| Codex iter-2 F1 | Naive `.gitignore` child-unignore doesn't override parent-dir ignore — verified via `git check-ignore` | 3 | Corrected to parent-safe pattern (`.claude/*` + `!.claude/skills/` + `.claude/skills/*` + `!.claude/skills/dev-review/` + `!.claude/skills/dev-review/**`). 5 lines instead of 4. | Bucket A `.gitignore` subsection |
| Codex iter-2 F2 | Nested triple-backtick fences in the Bucket D footer example break Markdown — Bucket E heading risks rendering as code | 3 | Outer fence switched to 4-backticks; inner ` ```json-verdict ` stays as 3-backticks. Bucket E heading now renders correctly. | Bucket D footer contract block |
| Codex iter-2 F3 | `EXECUTABLE_TARGETS` in `bootstrap_lib/manifest.py:14` lists only existing scripts — new scripts would render without execute bit | 3 | New entries added to `EXECUTABLE_TARGETS`. V-2.2 extended with `os.access(path, os.X_OK)` assertion. | Risks (F2 row extended); V-2.2 |
| Codex iter-2 F4 | Hash + snapshot preamble fires on `ITERATION=1.5` consistency check, breaking `-gt 1` integer compare; driver workflow also omitted consistency between fold and ack | 3 | Scoped hash + snapshot to integer plan-review targets only (consistency target unchanged). Driver workflow rewritten: review → fold → consistency → fold drift → loop-ack → next integer review (6 steps). | Bucket B scope note (new); Bucket B driver workflow (6 steps); Risks (F4 row new) |
| Codex iter-2 F5 | Skill template at commit 1 lists targets (`loop-ack`, `loop-status`) that don't exist until commits 2 / 4 — pre-merge gate would validate a Skill making false promises | 2 | Skill wrap-list grows incrementally: commit 1 ships only the existing make targets; commits 2 and 4 append their new targets to the Skill via small Edits. Pre-merge gate at commit 1 only exercises what commit-1 ships. | Bucket A SKILL.md wrap-list paragraph |
| Codex iter-2 F6 | No template ↔ dogfood byte-identity test for the new `shared/skill-dev-review.tmpl` ↔ `.claude/skills/dev-review/SKILL.md` pair | 2 | V-21 added — 6th `SELFTEST_OVERLAP_TARGETS` entry in `tests/test_selftest_overlap.py`. | V-21 (new) |
| Codex iter-2 F7 | Skill body says it uses `AskUserQuestion` but `allowed-tools` omits it | 2 | Added `AskUserQuestion` to `allowed-tools`. | Bucket A SKILL.md frontmatter; Risks (F7 row new) |
| Codex iter-3 F1 | Ad-hoc `.gitignore` "append/create" in bootstrap violates the manifest + atomic-write + restore contract | 3 | Originally proposed `shared/.gitignore.tmpl` + `shared/.gitignore.append.tmpl` via `APPEND_MERGE`. **[SUPERSEDED by iter-4 F1]** — that approach conflicted with the renderer's per-language `.gitignore.tmpl` map and Jinja's language-first loader order. Final approach (iter-4 F1 + iter-5 F1): edit each language's `.gitignore.tmpl` directly + add two-pass `adopt.py` for adopt-mode. | Bucket A `.gitignore` subsection (rewritten); V-2.1 extended; Implementation commit 1 (file list grew) |
| Codex iter-3 F2 | `codex exec resume` help doesn't list `-C`/`--sandbox`; default flip to `continue` would risk losing the read-only sandbox guarantee on iters ≥ 2 | 3 | Originally added defensive `-C "$(CURDIR)" --sandbox read-only` re-passing on resume call. **[SUPERSEDED by iter-4 F2]** — those flags are rejected by the actual CLI (`unexpected argument`). Reverted. Replaced with V-13.5 sandbox + cwd inheritance verification (strengthened in iter-5 F4 to three required assertions). **Lesson surfaced** about over-defensive folds. | Bucket F mechanics (resume command updated); Pre-implementation fixture-capture (additional gate added) |
| Codex iter-3 F3 | `finding_fingerprints = sha1[:8](title + file:line)` is brittle — reviewer prose isn't required to keep titles or anchors stable | 3 | Replaced with structured `findings: [{id, importance, section_or_line, title}]` array. **[SUPERSEDED by iter-4 F3]** — initial fold used `(id, section_or_line)` as identity, but `id` (`F<N>`) shifts between iters; iter-4 F3 corrected identity to a content-derived `fingerprint` field. Prose findings still lead with `**F<N> (importance N):**`. | Bucket D footer contract (rewritten — `fingerprint` per iter-4 F3); Bucket E classifier `_identity` function |
| Codex iter-3 F4 | `loop-ack` only re-stamps the hash; doesn't enforce that the driver ran the consistency self-check between fold and ack | 3 | Consistency target now writes `/tmp/plan-review-<slug>.consistency` (containing the post-consistency-check plan hash). `loop-ack` requires `sha256(plan) == consistency-marker` before restamping the integrity hash — refuses with a clear message if they differ. Makes the documented workflow ENFORCED. | Bucket B `loop-ack` mechanic; consistency-target description (in commit 6 docs) |
| Codex iter-3 F5 | AGENTS.md has no Mandatory human-approval gate paragraph; the planned keyword swap has no target text | 2 | Removed AGENTS.md from the keyword-swap scope. D-8 + V-20 + commit 6 file lists updated; `shared/AGENTS.md.tmpl` no longer modified. | Implementation commit 6; D-8; V-20 |
| Codex iter-3 F6 | V-21 (Skill template/dogfood byte parity test) added but not owned by any rollout commit | 2 | Assigned V-21 to commit 1 (where both files are introduced). | Implementation commit 1 file list / tests |
| Codex iter-3 F7 | `make check` + `make test` sequenced after commit 5, but commits 5b and 6 still change Makefile defaults / docs / dogfood tests | 2 | Moved the final gate to after commit 6 (and after 5b if it ships). | Implementation rollout footer |
| Codex iter-4 F1 | `.gitignore` shared-template design (from iter-3 F1) conflicts with the renderer's per-language `.gitignore.tmpl` map + Jinja loader's language-first lookup order | 3 | Edit each language's `.gitignore.tmpl` directly (`languages/python/.gitignore.tmpl`, `languages/nodejs/.gitignore.tmpl`, `languages/go/.gitignore.tmpl`) with the 5-line unignore block. Drop `shared/.gitignore.tmpl` + `shared/.gitignore.append.tmpl`. Adopt-mode unaffected (existing planned `.gitignore` already routes through `APPEND_MERGE`). V-2.1 extended to assert per-language. | Bucket A bootstrapped-projects subsection (rewritten); rollout commit 1 (file list updated); V-2.1; Critical files |
| Codex iter-4 F2 | iter-3 F2's defensive `-C / --sandbox` flags on `codex exec resume` are rejected by the actual CLI (`unexpected argument`) — would ship a broken Bucket F | 3 | Reverted: resume call drops the flags; relies on inheritance from the original session (same as plan-tango). V-13.5 already verifies inheritance behavior. **Lesson surfaced** about over-defensive folds. | Bucket F mechanics (resume command); `## Lessons surfaced`; iteration log row 4 |
| Codex iter-4 F3 | Stop classifier's `(id, section_or_line)` identity is unstable — `F<N>` ids are per-review labels that shift across iters | 3 | Added `fingerprint` field to the footer (`<section-or-line-slug>:<title-slug>`). Classifier uses `fingerprint` exclusively. `id` stays as a prose cross-reference. Scope row D updated from `finding_fingerprints` to `findings`. | Scope row D; Bucket D footer contract (rewritten); Bucket E classifier `_identity` function; V-10 |
| Codex iter-4 F4 | `/tmp` stateful artifacts (hash, consistency, thread, snapshot) keyed only by `$(notdir $(basename PLAN_FILE))` — two repos with same plan basename poison each other | 2 | D-12 added. All stateful `/tmp` paths use `KEY = sha256(realpath(CURDIR) + ":" + realpath(PLAN_FILE))[:12]`. Read-only review-output files stay basename-keyed (no state). Consistency 4.5 F2: the `KEY` definition + path derivations are PROPAGATED into the Bucket B / Bucket C / Bucket F Makefile snippets (iter-4's evidence row originally overstated V-item updates — those V items reference snapshot/hash paths which now resolve through `$(KEY)`, so the original mention stands by transitivity). | D-12 (new); Buckets B / C / F Makefile snippets (rewritten); V-3 / V-4 / V-4.5 paths through `$(SNAP_DIR)` / `$(HASH_FILE)` / `$(CONS_FILE)` |
| Codex iter-4 F5 | Skill doesn't encode the cross-direction reviewer rule from CLAUDE.md (Claude-authored → Codex; Codex-authored → Claude) | 2 | Skill flow extended: AskUserQuestion the author, branch to the cross-direction target, never offer "run both". Pre-merge gate + Manual smoke exercise the branching. | Bucket A approval-gate-implication paragraph (new cross-direction subsection); V-1; Manual smoke |
| Codex iter-5 F1 | adopt-mode `.claude/` handling still broken — `adopt.py:415` SKIPs Skill before `.gitignore` rewrite | 3 | Two-pass adopt: first pass rewrites `.gitignore` (`APPEND_MERGE` adds the unignore block), second pass re-runs SKIP-check; Skill file now lands. New test fixture with existing `.gitignore` containing `.claude/`. | Bucket A bootstrapped-projects subsection (rewritten with two-pass logic); V-2.1 (per-language assertion); Implementation commit 1 (adopt.py edit added) |
| Codex iter-5 F2 | Hash-abort message advised "remove $(HASH_FILE) to acknowledge" → bypasses `loop-ack` + consistency-marker gate | 3 | Rewrote abort message: now points users to consistency + `loop-ack`. Added explicit `make loop-reset` target as the documented escape hatch (removes hash/cons/thread/snapshot state for the plan). | Bucket B hash-check snippet (abort message rewritten); Bucket B (new `loop-reset` target snippet); Implementation commit 2 |
| Codex iter-5 F3 | Bucket E input record shape didn't include `fingerprint` — classifier `_identity` requires it | 3 | Updated Bucket E "Inputs" prose to include `fingerprint` in the record shape. Missing/malformed `fingerprint` → `STATUS: malformed`. | Bucket E Inputs paragraph |
| Codex iter-5 F4 | V-13.5 file-absence-only check can false-pass (write may have silently succeeded, cwd may be wrong) | 3 | Strengthened V-13.5: three required assertions — sandbox-denial event in JSONL stdout + file absence + `pwd` equals `realpath($(CURDIR))`. Single failure → don't ship 5b. | V-13.5 (rewritten) |
| Codex iter-5 F5 | V-1 contingency said "ship commits 2-6 without commit 1" but those commits still touch Skill files → contingency wasn't executable | 2 | Rewrote contingency: V-1 failure = cancel + replan. New PR drops Bucket A entirely; terminal-orchestrator alternative is a SEPARATE PR. | Rollback section (contingency paragraph rewritten) |
| Codex iter-5 F6 | V-1 only verified one branch direction (Claude → Codex), not the other | 2 | Manual smoke + V-1 acceptance gate now tests all 3 branches (Claude, Codex, Other→cancel) separately. | Pre-merge acceptance gate (3-branch test); V-1 |
| Codex iter-5 F7 | Skill advertised commit-review without specifying same-AI rule → could re-introduce LESSONS.md 2026-05-19 mistake | 2 | Added explicit commit-review same-AI branching to the Skill: "Who implemented this commit? Claude/Codex/Other"; never offers cross-AI Tier-1. | Bucket A cross-direction subsection (added commit-review path) |

## Implementation log (this PR)

| short-sha | one-line what landed | deviations from plan, or 'none' | issues faced, or 'none' |
|---|---|---|---|
| f28d962 | Bucket B+C: KEY derivation, hash-check, snapshot, loop-ack, loop-reset | CONS_FILE path uses repo-aware $(KEY) (not slug-only) — matches D-12 fold intent | Tab chars in Make recipe continuations required Python-level byte replacement (Edit tool can't match literal tab in old_string) |
| 884f165 | V-5: add stale-hash sub-case (Tier-1 F1 fold) | none | Missing coverage discovered during Tier-1 review of f28d962 |
| 2a3c7c0 | Bucket D first pass: json-verdict footer instruction in both plan-review prompts | "json-verdict code fence" wording (caught by Tier-1 as ambiguous) | Makefile tab-char matching required Python fallback again |
| 2341f7d | Fix(bucket-d): rename to "json code fence"; guard non-dict in _parse_footer | none (Tier-1 fix commit) | none |
| 28ca082 | Bucket E: scripts/loop-status.py + shared template + manifest.py + make target + V-9/10/11/12/16/16.5/f2/f3 tests | classify() converged-with-polish was incorrectly nested under verdict==converged check (caught by Tier-1) | ruff format pass required after initial write; template sync after format |
| 64c3021 | Fix(bucket-e): F1 partial oscillation, F2 malformed-on-missing-fingerprint, F3 standalone converged-with-polish branch (Tier-1 catches) | none (all 3 are deviations from initial impl corrected to match plan pseudocode) | Template re-sync (cp) after classify() fix |
| 6dab035 | Docs/BACKLOG commit 4: Commands table, keyword swap, BACKLOG entries, V-20/V-22 tests | Pre-existing ruff lint fixes in test_loop_status.py carried in this commit | none |

## Lessons surfaced (this PR)

- **Over-defensive folds can introduce new imp-3 findings.** iter-3 F2 added `-C / --sandbox` flags to `codex exec resume` "defensively"; iter-4 F2 verified empirically that the CLI rejects them. The defensive add was wrong — resume INHERITS those settings, and adding rejected flags would have shipped a broken Bucket F. Rule: when folding a "this might be unsafe" finding, prefer adding a *verification step* (test, gate, runtime check) over adding *defensive command-line flags* you haven't tested. Defensive flags assert a contract that may not exist; verification steps probe what's actually true. Candidate for LESSONS.md.

## Critical files to read before each iter's review

- [Makefile:80-209](Makefile) — current review targets (the SELFTEST-OVERLAP block)
- [shared/Makefile.review.tmpl](shared/Makefile.review.tmpl) — template counterpart; ALL changes happen here first, then mirror to Makefile
- [tests/test_triage_byte_identity.py](tests/test_triage_byte_identity.py) — confirm this stays untouched
- [tests/test_selftest_overlap.py](tests/test_selftest_overlap.py) — confirm Makefile↔template mirror still valid
- [LESSONS.md:98-104](LESSONS.md) — the percent-trim lesson (relevant when reviewer suggests "also trim CLAUDE.md while you're here")
- [LESSONS.md:108-114](LESSONS.md) — Tier-1 same-AI rule (relevant when reviewer suggests changing review-direction semantics)
- [docs/plans/README.md](docs/plans/README.md) — section taxonomy (this plan file follows it)
- [CLAUDE.md](CLAUDE.md) — confirm the harvest does NOT contradict the triage / pre-coding / approval-gate sections
- [egsok/plan-tango plugins/plan-tango/skills/run/SKILL.md](https://github.com/egsok/plan-tango/blob/main/plugins/plan-tango/skills/run/SKILL.md) — the source we're harvesting from; useful for the reviewer to cross-check claims about plan-tango's mechanics
- `~/code/downstream-app/docs/plans/2026-05-25-phase-5a-prep-amendments.md` (**external reference — may not be accessible to all reviewers; this is a sibling repo on the original driver's machine**) — the 17-iter case study that motivates Bucket E. The Iteration log + Evidence table inside this plan file restate the relevant trajectory data inline, so reviewers without access to the sibling repo can still verify the convergence pattern.
