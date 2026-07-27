# C4 — sync `downstream-app`' plan-review loop with the skill (full catch-up)

## Context

This is the **C4** follow-up carved out of
[2026-06-08-plan-review-loop-overiteration-guardrails.md](2026-06-08-plan-review-loop-overiteration-guardrails.md)
(see its "NOT in this plan" → C4 bullet). The guardrails plan added C1–C3
(strict imp-3 calibration in the review prompts; "executable runbooks stay out
of the plan"; the same-class-regeneration circuit-breaker) plus the
cap-consistency-self-check follow-up, and shipped them to the skill in PR #37
(`64d94bd`) and PR #38 (`93366c0`). C4 was deferred because `downstream-app` had a
dirty, actively-changing tree at the time (the post-2b implementation, 15+
modified files).

**Why now.** As of 2026-06-10 a read-only check shows `downstream-app` is
effectively clean (one *untracked, unrelated* plan doc:
`docs/plans/2026-06-02-period-reports-delivery-scheduling.md`) and C1–C3 have
merged — both of C4's preconditions are met.

**What the check also revealed (the real scope).** `downstream-app` was
bootstrapped from this skill around 2026-05 and has since **drifted**. It is
missing not just C1–C3 but the entire fact-check pre-pass (PR #30), the
loop-status / JSON-fence convergence machinery, the `review` dispatcher
(PR #35), and all of the skill's review-loop tests. The user chose the **full
catch-up** scope: re-sync `downstream-app`' whole plan-review subsystem with the
skill's current state — adapting, not blindly overwriting, the places where
`downstream-app` deliberately diverged (its PII hard-rules, its Codex orientation,
its `CLAUDE.md` structure).

This is well-motivated: `downstream-app`' own 19-iteration post-2b doc-layout loop
is the incident that *motivated* C1–C3. It is exactly the repo that needs the
convergence machinery and the runbook/regeneration guardrails.

**Regression safety.** C4's artifacts land in `downstream-app`, not this skill
repo. Verification is therefore *manual in `downstream-app`*: its own `make check`
stays green after the additions, and every newly-added target actually runs.
This skill repo's existing byte-identity + `propagate-shared-rules` tests guard
the *source* side only.

**Outcome measurement.** No business metric — internal workflow-tooling change.
The outcome is "`downstream-app`' plan-review loop gains the same drift-guardrails,
fact-check pre-pass, and convergence tracking the skill now has." Observable only
as future-loop quality (fewer ritual iterations; same-class regeneration caught
early), not a number.

## Scope

### IN scope

| # | Item | Source (skill) → Target (`downstream-app`) |
|---|------|------------------------------------------|
| 1 | **Fact-check pre-pass** | render `shared/scripts-extract-plan-facts.py.tmpl` + `shared/scripts-verify-plan-facts.py.tmpl` → downstream-app' `scripts/{extract,verify}-plan-facts.py`; add `review-plan-fact-check-by-{codex,claude}` targets + `FACT_CHECK_*`/`PLAN_FACT_CHECK_OUT_*` **and the shared `$(KEY)` var** (added here — Bucket A lands before Bucket B, which reuses it); `test_review_plan_fact_check.py` lands with this bucket (rewritten downstream-app-local per Bucket G's boundary) |
| 2 | **Convergence machinery** | copy `scripts/loop-status.py`; add `loop-status`/`loop-ack`/`loop-reset` targets (**reusing `$(KEY)` from Bucket A**); upgrade the `review-plan-by-{codex,claude}` prompts to emit the JSON fence (`verdict`/`severity_counts`/`key`/`findings`+fingerprints) and `**FN (importance N):**` tags; `test_loop_status.py` lands with this bucket |
| 3 | **C1 calibration prose** | fold the strict imp-3 calibration block into `downstream-app`' `review-plan-by-{codex,claude}` prompts (lands together with the JSON-fence upgrade — same prompt string) |
| 4 | **C2 + C3 + cap-consistency rule docs** | propagate into downstream-app' `CONTRIBUTING.md` + `docs/plans/README.md` ("Stopping the loop") — mechanical where headings already match, hand-aligned where they do not |
| 5 | **`review` dispatcher** | add the `review` MODE/ACTOR target (PR #35) |
| 6 | **Reviewer-surface reconciliation (`CLAUDE.md` + `AGENTS.md`)** | hand-adapt the skill's plan-review-loop / triage / two-tier / human-approval-gate guidance into `downstream-app`' `CLAUDE.md` (`## Process discipline`), AND assess + align `downstream-app`' `AGENTS.md` (the GitHub/Codex reviewer-bot surface) against the source AGENTS — **preserving** its `## Hard rules — PII`, Codex orientation, and any downstream-app-specific guidance. (downstream-app' AGENTS.md already has *partial* dispatcher + calibration coverage — this is an align-deltas pass, not a wholesale rewrite.) |
| 7 | **Test parity + green check** | **owns the rewrite-boundary rule for ALL ported tests** (no `SKILL_ROOT`/`bootstrap.py`/skill-fixture dependency) + **lands the cross-cutting tests** `test_makefile_review_targets.py` (introspect downstream-app' **live** Makefile/scripts; drop `_bootstrap_fixture`) and `test_review_loop_artifacts.py` (adapt to downstream-app' target set) + the **final green-gate**. Feature-specific tests land with their bucket (A: `test_review_plan_fact_check.py`; B: `test_loop_status.py`), each obeying this boundary. Confirm `downstream-app`' `make check` stays green |

### NOT in scope

| Item | Why out |
|------|---------|
| The `/dev-review` Claude slash-command (the skill repo's tracked `.claude/commands/dev-review.md`) | It is a **Claude Code** feature with no `codex` equivalent (`.claude/commands/*` is only read by Claude Code); `downstream-app` is Codex-oriented and reaches the dispatcher via `make review` directly. **Verification (Bucket F):** the **adapted reviewer surfaces** (`CLAUDE.md`/`AGENTS.md`/`CONTRIBUTING.md`/`docs/plans/README.md`) must not reference a `/dev-review` command that does not exist there — they currently do not, and Bucket F must not introduce one when adapting the skill's `CLAUDE.md`. This frozen plan copy names `/dev-review` only to mark it out-of-scope, so the check excludes the plan file itself (see Verification). |
| Porting C4 into the `Telegram bot` repo | Separate, larger reconciliation (that repo is Codex-only, no `LESSONS.md`, triage nested differently) — its own follow-up; see the session's sequencing decision |
| `propagate-shared-rules.py` *into* downstream-app | downstream-app is a propagation *target*, not a propagator; adding the tool itself is optional and deferred unless downstream-app needs to re-propagate downstream |
| Re-rendering downstream-app' product code / non-review Makefile targets | This is a plan-review-subsystem sync only; product targets (`docker-*`, pipeline, PII) are untouched |
| `test_triage_byte_identity.py` / `test_shim_cli_help_consistency.py` / `test_github_review_modes.py` | Skill-internal dogfood / shim / github-mode tests with no downstream-app analogue |

## Subsystem breakdown

Buckets are described at **intent fidelity** (per the C2 rule this plan ports):
*what* lands and *where it comes from*, not line-level content. The source files
in this skill repo are the canonical text; implementation copies/renders them and
verifies by execution + Tier-1, not by transcribing into this plan.

### Bucket A — Fact-check pre-pass (PR #30 port)

- **Lands:** in downstream-app' `scripts/` — `extract-plan-facts.py` + `verify-plan-facts.py`
  (rendered from the skill's `shared/scripts-*-plan-facts.py.tmpl`, which are
  already generic + **stdlib-only** — this invariant must hold: no
  `bootstrap_lib` import, since the templates ship downstream); the
  `review-plan-fact-check-by-{codex,claude}` Makefile targets + the
  `FACT_CHECK_FACTS_OUT` / `FACT_CHECK_VERIFY_OUT` / `PLAN_FACT_CHECK_OUT_*`
  vars; **the shared `$(KEY)` Makefile var — added HERE, since Bucket A lands
  before Bucket B (which reuses it)**; `tests/test_review_plan_fact_check.py`
  (rewritten downstream-app-local per Bucket G's boundary).
- **Verified at impl:** `make review-plan-fact-check-by-codex PLAN_FILE=<a downstream-app plan>`
  emits the deterministic `extract | verify` JSON; the unit test passes.

### Bucket B — Convergence machinery (loop-status + JSON fence + circuit-breaker)

- **Lands:** downstream-app' `scripts/loop-status.py`; `loop-status` / `loop-ack` /
  `loop-reset` targets (**reusing `$(KEY)` added in Bucket A**); the
  **review-prompt upgrade** — the `review-plan-by-{codex,claude}` prompts gain
  the trailing JSON code-fence (`verdict` mapped from the verdict phrase,
  `severity_counts`, `key`, `findings[]` with `id`/`section_or_line`/`title`/
  `fingerprint`) and the `**FN (importance N):**` prose tags that `loop-status.py`
  consumes; `tests/test_loop_status.py`.
- **Intra-bucket ordering (load-bearing):** the prompt must emit the fence
  **before or with** `loop-status.py` landing — `loop-status` reads the fence;
  without it there is nothing to read.
- **Shell-safety invariant:** the prompt strings are double-quoted Makefile args.
  Keep them shell-safe — no backticks, no `$(`, no literal double-quotes; single
  quotes for inner quoting (LESSONS 2026-06-09 "shell-safe prompt text").
- **Verified at impl:** `make loop-status PLAN_FILE=<plan>` reports convergence;
  a synthetic same-fingerprint regeneration across two iters is flagged.

### Bucket C — C1 calibration prose

- **Lands:** the strict imp-3 calibration block ("Calibrate importance strictly…
  a feasibility dependency stays importance-3… when unsure, ask: can the PR ship
  with a green `make check`…") folded into the same `review-plan-by-*` prompt
  strings Bucket B upgrades. **C and B co-edit one string → land as one commit.**
- **Verified at impl:** prompt-text presence test (mirrors the skill's
  review-target test); shell-safety check.

### Bucket D — C2 + C3 + cap-consistency rule docs

- **Lands:** into downstream-app' `CONTRIBUTING.md` — C2 ("Keep executable runbooks
  out of the plan"), C3 ("Second trigger — same-class regeneration"), and "Cap
  the consistency self-check"; into downstream-app' `docs/plans/README.md`
  ("Stopping the loop") — the matching short-form stop signals.
- **Mechanism:** mechanical section-swap where a `## `-heading already matches;
  hand-aligned where downstream-app' heading text differs (its triage section is
  `## Triaging review findings (full discipline)` — **Bucket F renames this to the
  managed `## Triaging review findings`**; the plateau base rule already exists at
  `CONTRIBUTING.md:201` for C3 to extend).
- **Verified at impl:** the four rule strings are present; `make check` green.

### Bucket E — `review` dispatcher

- **Lands:** the `review` target (MODE={plan,commit} ACTOR={claude,codex}
  dispatch; plan = cross-direction, commit = same-AI) + its `$(filter)` allowlist
  sanitization of MODE/ACTOR.
- **Verified at impl:** `make review MODE=commit ACTOR=codex` dispatches to
  `review-commit-by-codex` (downstream-app is Codex-oriented).

### Bucket F — Reviewer-surface reconciliation (`CLAUDE.md` + `AGENTS.md`, hand-adaptation)

- **`CLAUDE.md` lands:** the skill's plan-review-loop / triage-(a/b/c/d) /
  two-tier-review / mandatory-human-approval-gate guidance, **adapted into**
  downstream-app' existing `## Process discipline` section structure — *not* a
  section-overwrite.
- **`AGENTS.md` lands (FN2):** an **align-deltas** pass over downstream-app'
  `AGENTS.md` (the surface the GitHub/Codex review bots read) against the source
  AGENTS — bringing its `make review` dispatcher guidance and strict imp-3
  calibration to current. downstream-app' AGENTS.md already carries *partial*
  coverage, so this is alignment, not a wholesale rewrite.
- **`/dev-review` guard (FN3):** when adapting `CLAUDE.md`, do **not** introduce a
  reference to `/dev-review` — it is a Claude-Code-only command with no `codex`
  equivalent, deliberately not ported (see NOT-in-scope). Verify the **adapted
  reviewer surfaces** (`CLAUDE.md`/`AGENTS.md`/`CONTRIBUTING.md`/`docs/plans/README.md`)
  remain free of any `/dev-review` mention — the check excludes this frozen plan
  copy, which names it only as the not-ported example (see Verification).
- **Preserve, do not touch:** `## Hard rules — PII`, `## Gotchas`, and
  downstream-app' Codex-first review phrasing. This is the highest-judgment bucket;
  it is reviewed as prose, by a human, before commit.
- **Heading rename (DECIDED — approval gate 2026-06-10, user: yes):** rename
  downstream-app' `CONTRIBUTING.md` triage heading `## Triaging review findings
  (full discipline)` → the skill's managed `## Triaging review findings`, so the
  triage section becomes mechanically propagatable via `propagate-shared-rules.py`'s
  default `--section` in future syncs (no per-call override). Tier-1 confirms any
  downstream-app cross-references to the old heading text are updated in the same
  commit.

### Bucket G — Test parity + green-check verification

- **Owns the rewrite-boundary rule (FN5) for ALL ported tests:** no ported test
  may depend on `bootstrap.py`, `SKILL_ROOT`, or a skill-repo fixture — else
  downstream-app' `make check` fails on a literal port. Each is rewritten
  downstream-app-local (introspect downstream-app' live Makefile/scripts; tmp copies
  only for isolated artifact tests).
- **Lands the cross-cutting tests** (these need the full target set, so they come
  last):
  - `test_makefile_review_targets.py` — drop its `SKILL_ROOT`/`bootstrap.py`
    `_bootstrap_fixture`; assert against downstream-app' **live** Makefile/scripts.
  - `test_review_loop_artifacts.py` — adapt artifact-path assertions to
    downstream-app' target set.
- **Feature-specific tests land with their bucket** (each obeying the rule above):
  `test_review_plan_fact_check.py` → Bucket A (repoint script paths at
  downstream-app' `scripts/`; carry local fixtures); `test_loop_status.py` →
  Bucket B (portable, no skill deps).
- **Final green-gate:** `downstream-app`' full `make check` (lint + product
  test-suite + all new review-loop tests) is green.

## Architecture decisions

1. **Plan home = skill repo for the review loop; a frozen copy lands in
   `downstream-app` for implementation (FN1).** The skill has the *superior* review
   machinery (JSON-fence convergence, fact-check pre-pass, cap-consistency), so the
   C4 plan is authored + cross-reviewed here. **At implementation start the
   converged plan is committed verbatim into downstream-app'
   `docs/plans/2026-06-10-c4-sync-downstream-app-plan-review-loop.md` as a frozen
   reference copy** — landed as the FIRST downstream-app commit. This resolves the
   cross-repo Tier-1 binding gap: `make review-commit-by-codex PLAN_FILE=docs/plans/2026-06-10-…md`
   and `make status` in downstream-app then bind to a *local* plan file, and
   **implementation-log rows are appended to the downstream-app copy** (where the
   work happens). The skill-repo copy stays the review-loop + evidence record; the
   two are byte-identical at freeze and diverge only by their logs (skill:
   iteration/evidence; downstream-app: implementation). **Alternative:** author
   entirely in downstream-app — rejected, its review machinery is the outdated thing
   C4 exists to fix. **Overrule me if** you'd rather author in downstream-app despite
   the weaker loop.

2. **Adapt, don't overwrite, the reviewer surfaces `CLAUDE.md` + `AGENTS.md`
   (Bucket F).** downstream-app diverged both on purpose (PII hard-rules, Codex-first).
   A blind section-overwrite would clobber product-specific safety guidance. We fold
   the skill's process guidance *into* downstream-app' structure (and align AGENTS'
   deltas), reviewed as prose by a human before commit.

3. **Cross-repo fact-roots for iter-0.5 (verified behavior).** The plan
   references files in BOTH repos, so the `## Fact roots` block declares BOTH the
   skill checkout and the downstream-app checkout. Confirmed empirically (iter-0.5
   dry run): the deterministic `extract`+`verify` pre-pass reads files in either
   declared root — it is NOT confined to the skill tree, and a block listing only
   one root makes the *other* root's files read as false `failed`. **The real
   limitation is bare-name ambiguity:** a bare `CONTRIBUTING.md` exists in both
   roots and resolves to whichever is checked first — fine for existence/line-range
   (both pass), but it cannot catch a "wrong-repo" reference. Mitigation: the
   `## Critical files` section segregates skill-vs-downstream-app refs under explicit
   subheadings, and the iter-1 cross-review inspects both repos for semantic drift.
   The `--section` cli-flag stays `not_verifiable` (documented).

4. **Clean-tree precondition + own branch + git-revert rollback** (C4's original
   safety contract). Implementation starts only when `downstream-app`' tree is
   clean. The one untracked file
   (`docs/plans/2026-06-02-period-reports-delivery-scheduling.md`) is unrelated
   and untracked — C4's git-revert rollback never touches it; either commit/stash
   it first or leave it (it does not block a clean C4 revert). `CODE_ROLLBACK_BASE`
   = downstream-app HEAD at impl start (currently `f341cd0`; re-pin at impl start as
   it may advance).

5. **Tier-1 during downstream-app implementation uses downstream-app' machinery, bound
   to the local frozen plan copy (FN1).** Each focused commit in downstream-app is
   Tier-1 reviewed via *its* targets (`make review-commit-by-codex
   PLAN_FILE=docs/plans/2026-06-10-…md` — the frozen copy from decision 1). The
   catch-up upgrades those targets, so later buckets benefit from the machinery
   earlier buckets land; landing the frozen plan copy first lets every subsequent
   bucket's Tier-1 bind to it.

6. **Stdlib-only invariant for the fact scripts** carries downstream unchanged —
   the rendered downstream-app copies must not import `bootstrap_lib` or any
   non-stdlib dependency.

7. **Pin the source sync base (FN4).** Because the catch-up *copies from* this
   skill repo, pin `SOURCE_SYNC_BASE` = the skill SHA whose Makefile/scripts/docs
   are the source of truth — currently `18a64be` (skill `main`; the C4 plan branch
   adds no machinery changes, so the machinery source is `main`, not the branch
   tip). **Preflight at impl start:** verify the skill checkout is at
   `SOURCE_SYNC_BASE`; if it has advanced, re-run the iter-0.5 fact-check + a fresh
   source diff so the catch-up neither misses nor over-includes changes outside C4.
   Paired with `CODE_ROLLBACK_BASE` (decision 4) this is a clean two-SHA model:
   **copy-from** `SOURCE_SYNC_BASE`, **revert-to** `CODE_ROLLBACK_BASE`.

## Risks + mitigations

| Risk | Mitigation |
|------|------------|
| Over-imposing skill machinery on a diverged *product* repo | Buckets D/F adapt rather than overwrite; PII/Codex content explicitly preserved; human-approval gate reviews the CLAUDE.md + AGENTS prose |
| Ported tests break downstream-app' `make check` (skill-local `bootstrap.py`/`SKILL_ROOT` deps) | Bucket G rewrites each test downstream-app-local (FN5); hard rule: no skill-repo dep; gated on green `make check` before catch-up is declared done |
| JSON-fence ↔ loop-status coupling lands half-done | Bucket B intra-ordering: prompt emits fence with/before loop-status; a synthetic regeneration test proves the pair works |
| Cross-repo Tier-1 review can't bind to a skill-repo plan (FN1) | Decision 1: a frozen plan copy is committed into downstream-app as the FIRST commit; Tier-1 + `make status` bind to it locally; impl-log rows live there |
| Source machinery drifts before impl, silently changing what's copied (FN4) | Decision 7: `SOURCE_SYNC_BASE` pinned (`18a64be`); impl-start preflight re-runs fact-check + source diff if the skill checkout has advanced |
| AGENTS.md reviewer surface left stale by a CLAUDE.md-only sync (FN2) | Bucket F align-deltas pass over AGENTS.md; Verification asserts dispatcher + calibration guidance is current |
| Prompt edits introduce shell-injection / break the Makefile arg | Shell-safety invariant (Bucket B); presence + no-backtick tests mirror the skill's |
| downstream-app' clean-tree precondition regresses mid-impl | Re-check `git status` at impl start; `CODE_ROLLBACK_BASE` pinned; each bucket its own commit for granular revert |

## Verification

- **Per-bucket:** each new/upgraded target smoke-runs in downstream-app (fact-check
  emits JSON; `loop-status` reports; `review` dispatches; the four rule strings
  present).
- **End-to-end:** run one real cross-review iteration on a *downstream-app* plan
  using the upgraded machinery — confirm the JSON fence parses, `loop-status`
  reads it, and the fact-check pre-pass runs as iter-0.5.
- **Green gate:** `downstream-app`' `make check` (lint + product tests + ported
  review-loop tests) passes before catch-up is declared done.
- **Cross-repo binding (FN1):** after the frozen plan copy lands,
  `make review-commit-by-codex PLAN_FILE=docs/plans/2026-06-10-…md` and
  `make status` in downstream-app both resolve it locally (no "PLAN_FILE not found").
- **Source preflight (FN4):** impl start verifies the skill checkout is at
  `SOURCE_SYNC_BASE` (`18a64be`); a mismatch forces a re-run of iter-0.5 + source diff.
- **Reviewer surfaces (FN2/FN3):** downstream-app' `AGENTS.md` carries current
  dispatcher + calibration guidance; a `dev-review` grep over the **adapted
  reviewer surfaces** (`CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`,
  `docs/plans/README.md`) returns nothing (no dangling reference to an unported
  command) — **excluding this frozen plan copy**, which intentionally names
  `/dev-review` as the deliberately-not-ported command. A bare
  `grep -r dev-review docs/` would match the frozen copy itself and false-fail.
- **Rollback proof:** `git revert` of the catch-up commit range restores
  downstream-app to `CODE_ROLLBACK_BASE` with a still-green `make check`.

## Implementation rollout

**Impl-start preflight (FN4):** confirm downstream-app' tree is clean and the skill
checkout is at `SOURCE_SYNC_BASE` (`18a64be`); pin `CODE_ROLLBACK_BASE` =
downstream-app HEAD.

Suggested order (each bucket = one focused commit in `downstream-app`, Tier-1
reviewed via downstream-app' machinery; buckets after step 1 are largely independent):

1. **Frozen plan copy (FN1)** — commit the converged plan verbatim into
   downstream-app' `docs/plans/`, FIRST, so every later bucket's Tier-1 can bind to
   it locally.
2. **Bucket D** (rule docs) — cheapest, immediate guardrail value, no new infra.
3. **Bucket A** (fact-check pre-pass) — adds `$(KEY)` + the fact scripts/targets.
4. **Buckets B+C** (convergence machinery + C1 calibration) — one prompt-upgrade
   commit + loop-status; the largest bucket.
5. **Bucket E** (`review` dispatcher).
6. **Bucket F** (`CLAUDE.md` + `AGENTS.md` reconciliation) — human-reviewed prose.
7. **Bucket G** (test parity + green-check) — closes the catch-up.

Rollback: `git revert` the bucket commits in reverse; `CODE_ROLLBACK_BASE` pinned
at impl start.

## Iteration log (this plan)

| Iter | Reviewer | Date | Findings (3/2/1) | Verdict |
|------|----------|------|------------------|---------|
| 0.5 | Fact-check (deterministic, no AI layer) | 2026-06-10 | n/a | **clean** — 26/26 concrete facts verified (paths, line refs, `make` targets across both repos); 1 `not_verifiable` (`--section` cli-flag, documented). Pre-iter-1 fixes (mechanism, not plan drift): declared BOTH fact roots (a one-root block false-fails the other root's files); standardized downstream-app destination refs to `downstream-app' \`<rel>\``. |
| 1 | Codex | 2026-06-10 | 0/5/0 | needs-iter → **all 5 imp-2 folded (a)**. Codex read both repos (cross-repo worked). FN1 plan-binding, FN3 dev-review premise, FN4 source-pin, FN5 test-deps all verified correct against cited files; FN2 (AGENTS stale) premise *overstated* — folded the valid core (AGENTS in-scope) with the nuance noted. 0 imp-3 → at stop threshold; iter-1.5 consistency next, no ritual iter-2 unless folds surface imp-3. |
| 1.5 | Claude self-check | 2026-06-10 | 0/2/0 | **2 genuine contradictions** (not cosmetic) → both folded: (C-1) `$(KEY)` ownership reassigned Bucket B→A (A lands first, B reuses); (C-2) test double-ownership resolved (feature tests land with their bucket; cross-cutting tests + rewrite-boundary rule + green-gate in Bucket G). Manual cross-ref verification confirms consistency; **pass-2 skipped per the cap rule** — localized, verified fixes, not ritual. **Converged: 0 imp-3, all imp-2 addressed.** |

## Evidence table — what was folded and where

| Iter | Finding | Imp | Decision | Where folded / why parked-rejected |
|------|---------|-----|----------|------------------------------------|
| 1 | FN1 — cross-repo Tier-1 plan-binding undefined | 2 | (a) fold | Premise verified. Decision 1 rewritten: frozen plan copy committed into downstream-app as first commit; Tier-1 + `make status` bind locally; impl-log lives there. Also Decision 5, Implementation rollout step 1, Risks, Verification. |
| 1 | FN2 — AGENTS.md reviewer surface omitted/stale | 2 | (a) fold | Premise *partially* overstated (downstream-app/AGENTS.md has partial coverage, not "lacks"). Folded valid core: Bucket F renamed to cover CLAUDE.md + AGENTS.md (align-deltas); Scope item 6, Verification, Risks updated. |
| 1 | FN3 — `/dev-review` exclusion false premise | 2 | (a) fold | Premise verified — `.claude/commands/dev-review.md` IS tracked in skill. NOT-in-scope rationale corrected (Claude-Code-only, no codex equivalent); Bucket F adds a "don't introduce `/dev-review`" guard + Verification grep. |
| 1 | FN4 — source sync base not pinned | 2 | (a) fold | Premise verified (`18a64be`/`f341cd0`). New Decision 7 `SOURCE_SYNC_BASE` + impl-start preflight; Implementation log header, rollout preflight, Risks updated. |
| 1 | FN5 — test-port rewrite boundary underspecified | 2 | (a) fold | Premise verified (`test_makefile_review_targets.py` uses `bootstrap.py`/`SKILL_ROOT`; `test_review_plan_fact_check.py` too; `test_loop_status.py` clean). Scope item 7 + Bucket G now give a per-test downstream-app-local rewrite boundary + hard rule. |
| 1.5 | C-1 — `$(KEY)` assigned to Bucket B but needed earlier by Bucket A | 2 | (a) fold | `$(KEY)` reassigned to Bucket A (Scope items 1+2, Bucket A/B bodies); B reuses it. A lands at rollout step 3, before B at step 4. |
| 1.5 | C-2 — `test_loop_status.py` + `test_review_plan_fact_check.py` double-owned (feature bucket AND Bucket G) | 2 | (a) fold | Convention set: feature tests land with their bucket (A/B); Bucket G owns the rewrite-boundary rule + cross-cutting tests (`test_makefile_review_targets.py`, `test_review_loop_artifacts.py`) + final green-gate. Scope item 7 + Bucket G reframed. |
| gate | #3 — triage-heading rename (was "optional, do not assume") | n/a | (a) fold (human gate) | User approved baking it in (2026-06-10). Bucket F's "Optional durable improvement" → **DECIDED yes**: rename downstream-app' triage heading to the managed `## Triaging review findings`. Bucket D cross-ref added. |
| Tier-2 | Codex (GitHub) — `grep -r dev-review` false-fails on the frozen plan copy | 3 | (a) fold | Premise verified: this plan file contains `/dev-review` at 9 lines; once frozen into downstream-app' `docs/plans/`, a bare repo-wide grep matches it, so Bucket F's check would false-fail even when the adapted surfaces are clean. Scoped the `dev-review` check to the **adapted reviewer surfaces** (excluding the frozen copy) at NOT-in-scope (L64), the Bucket F guard, and Verification. claude[bot] imp-1 (user-specific fact-root paths) **(c) rejected** — absolute roots are load-bearing for the fact-check pre-pass (decision 3). |

## Implementation log (this PR)

**SOURCE_SYNC_BASE** (skill repo SHA copied from): `18a64be` (skill `main`, 2026-06-10).
**CODE_ROLLBACK_BASE** (downstream-app HEAD at impl start): _pending — pin at impl start (currently `f341cd0`)._
Implementation-log rows live in the **downstream-app** frozen copy (decision 1); this skill-repo table tracks bucket landings for cross-reference.

| Bucket | Commit | Date | Summary | check | Tier-1 |
|--------|--------|------|---------|-------|--------|
| _pending_ | | | | | |

## Lessons surfaced (this PR)

_pending — reviewer-proposed lessons triaged here; real ones → `LESSONS.md`._

## Critical files to read before each iter's review

**In this skill repo (source of truth for what's being ported):**
- `Makefile` — review targets (`review` dispatcher L131; `review-plan-by-*`
  L160/L222 with the C1 calibration + JSON fence; `loop-{status,ack,reset}`
  L343–368; `review-plan-fact-check-by-*` L453/L473; `$(KEY)` + `FACT_CHECK_*` vars)
- `scripts/loop-status.py`, `scripts/{extract,verify}-plan-facts.py`,
  `shared/scripts-*-plan-facts.py.tmpl`
- `CONTRIBUTING.md` — `## Triaging review findings (full discipline)` (L193),
  plateau + C2/C3/cap-consistency (L202–210)
- `docs/plans/README.md` — "Stopping the loop" (L137–160)
- `AGENTS.md` — source reviewer surface (`## Dispatching reviews (Codex)` ~L58,
  the dispatcher + calibration guidance Bucket F aligns)
- `.claude/commands/dev-review.md` — the tracked Claude-Code command deliberately
  NOT ported (FN3); explains why downstream-app gets no `/dev-review`
- `tests/test_loop_status.py` (portable), `test_review_plan_fact_check.py` +
  `test_makefile_review_targets.py` (skill-local deps — see FN5 rewrite boundary),
  `test_review_loop_artifacts.py`

**In `downstream-app` (the target — current drifted state):**
- `Makefile` — current review targets (older prompts, no fence/fact-check/loop)
- `CONTRIBUTING.md` — has plateau base (L201), triage section, lacks C2/C3/cap
- `docs/plans/README.md` — "Stopping the loop" heading present (L131), body lacks
  the new stop signals
- `CLAUDE.md` — divergent structure (`## Process discipline`, `## Hard rules — PII`)
- `AGENTS.md` — reviewer surface with *partial* dispatcher + calibration coverage
  (FN2 align-deltas target), tracked + not gitignored
- `tests/` — no review-loop tests present

## Fact roots

- ~/code/dev-project-for-non-developers (this skill repo — source files being ported)
- ~/code/downstream-app (the target repo — current drifted state; cross-repo, see architecture decision 3)
