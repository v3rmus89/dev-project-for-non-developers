# Plan PR: tighten CLAUDE.md / AGENTS.md information architecture + add gh-repo hint

## Context

The skill currently loads ~182 lines into every Claude Code session via `CLAUDE.md`, and
~141 lines into every read-only review session via `AGENTS.md`. Both files were grown
incrementally across PR #1–#7 — most additions earned their place at the time, but the
result is verbose enough that priority signal dilutes. The PR #7 trial against
`call-details/` surfaced the issue empirically: the rendered `CLAUDE.md.new` (~160
lines) merged with the user's existing 96-line CLAUDE.md hit 233 lines before any
tightening.

The user's principle: **CLAUDE.md should be short** — it's the always-on context; every
line should be either a rule you can't afford to forget OR a pointer to where detail
lives. **Detail-rich content** (workflow steps, prompt templates, calibration paragraphs)
**belongs in `docs/plans/README.md` (canonical for plan-loop discipline) or
`CONTRIBUTING.md`** (consulted on-demand).

**Iter-1 fold note (Claude 3-2)**: most of the "verbose detail" CLAUDE.md carries is
already canonically present in `docs/plans/README.md`:
- Filename convention (`/tmp/plan-review-…-iter-N.md`) → `docs/plans/README.md:27-35`
- Bootstrap exception → DROPPED from CLAUDE.md (iter-3 fold Claude 3): CLAUDE.md's
  Bootstrap exception is PR-#1-specific Boxette-precursor detail ("PR #1's own plan
  was reviewed via Boxette's `make review-plan`…"); `docs/plans/README.md:101-105`
  has a DIFFERENT bootstrap exception (about plan-PR/impl-PR collapsing for
  bootstrap plans). They're NOT equivalent. Accepted dropped-content trade-off:
  PR-#1 historical trivia is low-value at PR #17. The README.md bootstrap exception
  covers the broader convention; CLAUDE.md doesn't need to repeat it.
- When-to-stop / no-imp-3 rule → `docs/plans/README.md:131-148`
- Consistency self-check cadence → `docs/plans/README.md:52-59`
- Human-approval-gate per-step elaboration → `docs/plans/README.md:60-67`

So **CLAUDE.md's correct move** for these sections is to delete the elaboration and
point at `docs/plans/README.md`, NOT to duplicate into CONTRIBUTING.md. The only
genuinely-orphan content is the **self-improvement writable-vs-read-only protocol**
(lives only in CLAUDE.md + AGENTS.md). That single piece either stays in CLAUDE.md or
gets one new CONTRIBUTING.md section (decision: stay in CLAUDE.md compressed; see Bucket B).

This plan tightens the skill repo's own `CLAUDE.md` + `AGENTS.md` (the dogfood docs) AND
the templates that render to generated projects. Pointers replace verbose elaboration
where `docs/plans/README.md` is already canonical. CONTRIBUTING.md absorbs only the
verbose triage content (calibration + plateau rule), which is
NOT in docs/plans/README.md. Plus a `gh repo create` hint in cli.py's v1 post-apply
success path.

### Pre-loop user-decided scope constraints

- **Target line counts**:
  - `CLAUDE.md` (skill's own): ~120-130 lines (down from 182).
  - `AGENTS.md` (skill's own): **revised to ~134-141 per Bucket C analysis** (down
    from 141 — see iter-1 fold note below). Reviewer-specific sections ("What to flag
    with high confidence", "Plan Review Guidance") can't move without losing their
    purpose, so the 80-100 target from the initial brief is not achievable without
    cutting reviewer-critical content. **(d)-class decision flagged for human-approval
    gate**: accept the modest ~134-141 target (only 0-7 line savings from triage
    shrink + self-improvement compression), or rewrite reviewer guidance to fit ~100
    (separate exercise out of scope here).
  - `CLAUDE.md.tmpl` / `AGENTS.md.tmpl` rendered output: similar to dogfood targets.
  - Hard target is **density** (every line earns its place), not the exact number.
- **Byte-identity invariant**: the "## Triaging review findings" section must remain
  byte-identical across six surfaces (`CLAUDE.md` + `AGENTS.md` + `docs/plans/README.md`
  + their 3 `shared/*.tmpl` counterparts), enforced by
  `tests/test_triage_byte_identity.py`. Any wording change cascades across all 6.
- **Four-questions test invariant**: `tests/test_triage_byte_identity.py::
  test_four_questions_extension_present` asserts exact substring text for the 4
  questions. New short version must preserve: "Before deciding (a/b/c/d), ask these
  four questions" + each question's first sentence.
- **Selftest overlap invariant**: `tests/test_selftest_overlap.py` checks
  `shared/docs-plans-README.md.tmpl` byte-renders to match `docs/plans/README.md`. So
  changes to these two files must be byte-identical in lockstep. The plan's Bucket A
  triage-shrink already affects both surfaces; the test IS in scope (iter-1 fold).
- **No content loss**: detail moved out of CLAUDE.md/AGENTS.md/templates MUST land at
  the canonical destination: `docs/plans/README.md` for plan-loop / human-approval
  detail (already there — just point at it); `CONTRIBUTING.md` for the verbose triage
  calibration/plateau/evidence-table content (one new section).
- **gh-hint is a code change**: small addition to `bootstrap_lib/cli.py`'s v1
  post-apply success path. Uses safe explicit-paths pattern (NOT `git add -A` —
  contradicts `LESSONS.md:48`).
- **PR #17 merge-conflict status**: **needs to be verified at impl time** (iter-1
  fold — the original plan claimed "no conflict" based on line numbers measured
  against PR #17's branch, not main). PR #17 adds the adopt-mode dispatch BEFORE
  the v1 success block on its branch; whether it modifies the v1 block itself is
  to-be-checked when impl PR opens.

### Sequencing within this PR

Ships as **4 focused commits** (iter-1 fold: merge CLAUDE.md edit + shared/CLAUDE.md.tmpl
mirror into one commit to avoid non-triage drift; same for AGENTS.md + tmpl. Net: 5
sub-tasks → 4 commits):

1. **Commit 1**: Triage section shrink across all 6 byte-identity surfaces + add the
   "## Triaging review findings (full discipline)" section to `CONTRIBUTING.md` +
   `shared/CONTRIBUTING.md.tmpl` + the same-AI Tier-1 wording fix in CONTRIBUTING.md
   lines 111/190 + tmpl 196/251 (iter-4 fold Codex 2). byte-identity test +
   selftest_overlap test must pass after.
2. **Commit 2**: Tighten CLAUDE.md other sections AND mirror to `shared/CLAUDE.md.tmpl`
   in the SAME commit (closes Claude 2-4 imp-2 — no byte-identity test guards
   non-triage CLAUDE.md↔tmpl consistency, so atomic edit prevents drift). **This
   commit also updates `tests/test_dogfood_doc_sanity.py` lines 127-130 + docstring**
   (iter-4 fold Claude 2.2) — Commit 2 introduces `@codex review` to CLAUDE.md, so the
   test that forbids it must be updated in the SAME commit or Commit 2 leaves pytest
   red at its own Tier-1 review.
3. **Commit 3**: Tighten AGENTS.md (skill's own) + mirror to `shared/AGENTS.md.tmpl`
   atomic.
4. **Commit 4**: Add gh-repo-create hint to `bootstrap_lib/cli.py`'s v1 post-apply
   success path + the 8 NEW `test_bootstrap_cli.py` gh-hint tests.

Tier-1 review per commit before push. Total estimated 3-5 hours including loop overhead.

## Scope

### IN scope

| # | Change | Where |
|---|---|---|
| 1 | Shrink "## Triaging review findings" verbose block (23 lines) → short version (~17 lines): 4-option bullets compressed to 1 sentence each, drop "The loop converges faster…" filler, drop "These four questions add ~30 seconds…" filler, drop the Calibration paragraph (moves to CONTRIBUTING.md), drop the plateau-rule paragraph (moves to CONTRIBUTING.md). Keep the 4 options + the 4 questions (with exact substring text per byte-identity test). End with: "See `CONTRIBUTING.md` for the full triage discipline: imp-3 calibration and the plateau rule." **Accepted dropped-content trade-off** (iter-3 fold Claude 5 per user direction): the (d) bullet's operational guardrails — `"Default is NOT (d)"`, the "30 seconds before merge, would they be surprised" heuristic, "Note (d) outcomes in the evidence table as `surfaced:`" — are dropped (not routed to CONTRIBUTING.md) since the (d) bullet compresses to one sentence. The keyword + brief description of (d) remain; the operational nuance is lost. Acceptable because the 4-questions check + the (a/b/c/d) bullet keywords carry the bulk of the discipline. | `CLAUDE.md`, `AGENTS.md`, `docs/plans/README.md`, `shared/CLAUDE.md.tmpl`, `shared/AGENTS.md.tmpl`, `shared/docs-plans-README.md.tmpl` (all 6 byte-identity surfaces) |
| 2 | Add new section "## Triaging review findings (full discipline)" to `CONTRIBUTING.md` + `shared/CONTRIBUTING.md.tmpl`, placed BEFORE the existing "## Tier-1 review — prompt template for in-session subagents". Includes ONLY: the calibration paragraph (imp-3 definition) and the plateau rule (iter-2.5 / iter-3.5 fold: NO "evidence-table format guidance" — that was phantom content; the actual format reference stays inside the (a/b/c/d) bullets which remain in the short CLAUDE.md/AGENTS.md block). **(iter-4 fold Codex 1)**: do NOT update CONTRIBUTING.md **line 114** (`shared/CONTRIBUTING.md.tmpl:199`) — its pointer "the (a/b/c/d) framework in `CLAUDE.md`" remains correct after this PR (the (a/b/c/d) bullets stay in CLAUDE.md compressed; only calibration+plateau move to CONTRIBUTING.md). Earlier plan-text proposing a "below in this document" edit was a broken cross-ref since the framework is NOT moving here. **(iter-4 fold Codex 2)**: this is a DIFFERENT line — update CONTRIBUTING.md **lines 111 + 190** + tmpl lines **196 + 251** (the `make review-commit-by-claude … # or review-commit-by-codex` command + the non-Claude-Code-sessions parenthetical) — replace the bare `# or review-commit-by-codex` / "or `make review-commit-by-codex`" with same-AI Tier-1 wording: "Tier-1 uses the same AI as the implementer (closes BACKLOG.md:557; cross-AI review is Tier-2's job)." | `CONTRIBUTING.md`, `shared/CONTRIBUTING.md.tmpl` |
| 3 | Tighten `CLAUDE.md` ## Plan review loop section from 34 lines → ~6 lines: keep the rule ("write to `docs/plans/...`, run review-plan-by-codex + claude, stop when no imp-3 remain"), drop the detailed iteration cadence + filename convention + bootstrap-exception. **End with**: "See `docs/plans/README.md` for filename convention, bootstrap exception, when-to-stop rule, and consistency self-check cadence" — pointing at the existing canonical surface, NOT duplicating to CONTRIBUTING.md (iter-1 fold). | `CLAUDE.md` |
| 4 | Tighten `CLAUDE.md` ## Two-tier code review from 8 lines → ~6 lines, with **iter-2 user-direction refold (positive-framing not negative-caveats)**: the current text contains a NEGATIVE caveat "(Codex GitHub bot is NOT configured in this project. Retroactively adding it is non-trivial today — see BACKLOG for the planned `--enable-github-review` flag.)" — DROP this caveat entirely. Replace with positive description of what IS active: "Tier-2 (after push): `claude[bot]` + `chatgpt-codex-connector[bot]` auto-fire on PR open / draft→ready; re-trigger via `@claude review this` or `@codex review` comments." (Skill repo has both bots active; positive description matches reality without naming what's missing.) Closes BACKLOG.md:416. Also fold **iter-2 Codex #4** at same time: tighten the Tier-1 same-AI ambiguity — "use the same AI as the implementer" (BACKLOG.md:557). | `CLAUDE.md` |
| 5 | Tighten `CLAUDE.md` ## Self-improvement loop (LESSONS.md) from 10 lines → **~8 lines** (iter-2 fold Claude 2-4: target raised from 6 to 8 to preserve the LESSONS.md entry-format spec at CLAUDE.md:123 and promote/archive rules at line 126 — the format spec is the only place a driver learns how to write a LESSONS entry; can't drop silently). Keep: "read LESSONS.md at session start" + 1-line writable-vs-read-only summary + entry-format spec (`### YYYY-MM-DD: <mistake>` + Trigger/Rule/Status) + promote/archive rule + pointer to AGENTS.md for read-only-context details. NO new CONTRIBUTING.md section. | `CLAUDE.md` |
| 6 | Tighten `CLAUDE.md` ## Mandatory human-approval gate from 12 lines → ~6 lines: keep the 4-step rule (summary→wait→fold→commit), drop the per-step elaboration. **End with**: "See `docs/plans/README.md` step 3 for the canonical wording" (already canonical there, iter-1 fold). | `CLAUDE.md` |
| 7 | Tighten `CLAUDE.md` ## Cross-session state recovery from 5 lines → 4 lines (iter-3.5 fold consistency #4 — Bucket B shrinks it but no Scope item covered it). Keep the first paragraph compressed: "If you're starting a fresh session / resumed after compaction / uncertain whether work X is already done: run `make status` BEFORE proposing changes." Drop the "If multiple plan files…" elaboration paragraph. **Must-preserve tokens** (iter-3 fold Claude 2): the `## Cross-session state recovery` heading + the `"make status"` substring (asserted by `test_dogfood_doc_sanity.py::test_cross_session_recovery_instruction_present`). | `CLAUDE.md` |
| 8 | Tighten `CLAUDE.md` ## Focused commits from 14 lines → ~6 lines: keep the rule + 4-line bash example + "Don't `git add .`" warning. Pointer to CONTRIBUTING.md per-change checklist. | `CLAUDE.md` |
| 9 | Mirror items 3, 5, 6, 7, 8 to `shared/CLAUDE.md.tmpl` in the SAME commit (Claude 2-4 fold — avoid drift). **Item 4 (Two-tier section) does NOT mirror as-is** (iter-2 fold Codex 3-2 + Claude 3-2): in the template, the Two-tier section is conditional on `github_review_mode`. Update: (i) `claude` branch: drop the stale "Codex bot NOT configured" caveat; describe only `claude[bot]` positively; (ii) `both-docs` branch: describe both bots positively (`claude[bot]` + `chatgpt-codex-connector[bot]`); (iii) `none` branch: existing minimal mention stays. Preserve all other Jinja conditionals (`{% if package_manager %}`, etc.). | `shared/CLAUDE.md.tmpl` |
| 10 | Tighten `AGENTS.md` (skill's own): keep "What to flag with high confidence" + "What NOT to flag" + "Local quality gate" + "Plan Review Guidance" + "Tone" sections (reviewer-specific; CAN'T move without losing purpose). Tighten "Cross-session state recovery" (5 → 4) + "Self-improvement loop" (10 → 6 — AGENTS.md keeps just the read-only-reviewer protocol; the LESSONS format-spec lives in CLAUDE.md per item 5's 8-line target, not mirrored here). | `AGENTS.md` |
| 11 | **Mirror ONLY the Cross-session-recovery + Self-improvement shrinks** from item 10 to `shared/AGENTS.md.tmpl` in the SAME commit (iter-2 fold Claude 2-5: the template's other sections ("What to flag", "Plan Review Guidance") have structurally different content from the dogfood — they're a generic baseline vs the dogfood's skill-repo-specific 35-line block). The triage block already shrinks via Bucket A's Commit 1 across both surfaces. | `shared/AGENTS.md.tmpl` |
| 12 | Add gh-repo-create hint to `bootstrap_lib/cli.py`'s v1 post-apply success block (lines 358-378 on main). Detection: distinguish "no `.git/` directory" (target needs `git init`) vs "`.git/` exists but no remote" (only needs remote creation). **Safe-pattern hint**: use `git status` + explicit-paths checklist (NEVER literal `git add -A` / `git add .` substrings — iter-2 fold Claude 3-1: hint warning text would self-trip the regression-guard test; reword to "stage files explicitly with `git add <path>`; never stage everything blind"). **`gh repo create` visibility (iter-4 fold Codex 4)**: print TWO explicit alternative command lines (`--private` and `--public`) under a "choose ONE" comment + a closing "no default — pick deliberately" note. Original iter-3 placeholder `<--private|--public>` was shell-metacharacter unsafe (`<` `|` `>` would be parsed as redirection/pipe on copy-paste). Two explicit lines preserves the iter-3 intent (force deliberate choice; no `--public` default) AND is copy-paste safe for the non-coder audience. **For `--github-review=both-docs`** (iter-4 fold Claude 2.3 — corrected placement): hint additionally points at the existing `docs/codex-github-review-setup.md` for the Codex web-UI setup; this pointer prints whenever `github_review == "both-docs"`, INDEPENDENT of `has_remote` (Codex bot enablement is a web-UI step orthogonal to repo creation). Don't duplicate the 3-step block in cli.py; the doc is the single source of truth (iter-3 fold Claude 4). **For `--github-review=claude`**: gh-hint + existing OAuth-token hint. **For `--github-review=none`**: NO gh-hint (iter-3 fold per user direction — `none` mode means no GitHub assumptions; user didn't supply `--github-owner`/`--github-repo` so a hint can't be specific). **Lint cleanliness (iter-4 fold Claude 2.1)**: drop the `f` prefix on `print(...)` lines without `{…}` interpolation (F541); simplify `except` tuple to `(OSError, subprocess.SubprocessError)` — `FileNotFoundError` is a subclass of `OSError`, redundant. **Implementation note**: also add `import subprocess` to `cli.py`'s import block. | `bootstrap_lib/cli.py` |
| 13 | Tests: (i) extend `tests/test_bootstrap_cli.py` with **8 NEW tests** total (iter-4 fold Claude 2.3 adds one): 3 detection-state (no-`.git/`, `.git/`-no-remote, has-remote-no-fire), 1 regression guard (no literal `git add -A`/`.`), 1 visibility-two-alternatives test (iter-4 fold Codex 4 — assert BOTH `--private` and `--public` command lines appear AND a "choose ONE" guidance line AND NO `<--private|--public>` shell-metacharacter substring AND no bare `--push` line lacking a `--private`/`--public` flag), 1 none-mode-no-hint guard, 1 both-docs-points-at-setup-doc check **with target lacking a remote** (iter-3), 1 NEW both-docs-points-at-setup-doc check **with target ALREADY having a remote** (iter-4 fold Claude 2.3 — proves pointer prints regardless of `has_remote`). (ii) Update `tests/test_dogfood_doc_sanity.py` invariant at **lines 127-130** (iter-4 fold Claude 1.1 — was incorrectly cited as `:125` in iter-3; line 125 is the `claude[bot]` assertion, the `@codex review` block is 127-130) to allow `@codex review` in root CLAUDE.md (Scope item 4). ALSO reconcile the function's docstring (lines 116-119) which currently says "selftest catches drift between shared/CLAUDE.md.tmpl and the dogfood mirror" — after Scope item 4, dogfood Two-tier deliberately diverges from template's `claude` branch; docstring must reflect this. **(iter-4 fold Claude 2.2)**: this test update lands in **Commit 2** (the same commit that introduces `@codex review` to CLAUDE.md), NOT Commit 4 — otherwise Commit 2 leaves pytest red at Tier-1 review time. (iii) `tests/test_selftest_overlap.py::test_overlap_docs_plans_readme` must continue to pass (Commit 1 impacts it). (iv) **Must-preserve-token discipline** (iter-3 fold Claude 2): the 4 existing `test_dogfood_doc_sanity.py` substring tests + the `test_shared_templates.py` Two-tier parametrize must all keep passing — substring constraints listed inline in Bucket E test table; preserve-tokens added to Scope items 4/5/7/9/10. | `tests/test_bootstrap_cli.py`, `tests/test_dogfood_doc_sanity.py` |

### NOT in scope

- **gh-hint in adopt-mode's `_main_apply_adopt` success path** — that code doesn't exist
  on main yet (lives in PR #17). After PR #17 merges, a follow-up PR will mirror the
  hint into the adopt-mode success path.
- **CONTRIBUTING.md restructure beyond Bucket A** — only the new "## Triaging review
  findings (full discipline)" section is added. Other sections (One-time setup,
  Per-change checklist, Branch naming, Emergency override, Skill repo specifics,
  Tier-1 prompt template) stay as-is.
- **`docs/plans/README.md` restructure beyond the triage section change** — the
  surrounding content (When to write a plan, File naming, Workflow with the canonical
  plan-loop detail) stays. CLAUDE.md POINTERS to it; README.md's content doesn't
  change beyond the triage section.
- *(struck through at iter-1.5 per user direction: Codex-bot wording fix IS folded into
  this PR — see Scope item 4.)*
- **`Key implementation invariants` section in skill's CLAUDE.md** — load-bearing
  technical constraints; preserve verbatim.
- **Substantive English rewrites of preserved text** — move-not-rewrite discipline:
  text that stays in CLAUDE.md stays as-is for the un-moved sections. Reduces risk
  of accidental wording drift breaking the byte-identity test.
- **`tests/test_triage_byte_identity.py` modifications** — the test stays as-is; the
  new short triage block must pass it. The 4-questions-presence test also stays as-is.
- **Updating `BACKLOG.md`** — add the "adopt-mode gh-hint follow-up" entry in the
  impl PR (not in this plan).

## Subsystem breakdown

### Bucket A — Triage section shrink (6 surfaces) + CONTRIBUTING.md absorption (2 surfaces)

| File | Change |
|---|---|
| `CLAUDE.md` | Replace lines 68-90 (current verbose triage block) with the new short version (~17 lines). |
| `AGENTS.md` | Replace lines 95-117 (byte-identical block) with the same new short version. |
| `docs/plans/README.md` | Replace the triage section with the same new short version. |
| `shared/CLAUDE.md.tmpl` | Replace the triage section with the same new short version. |
| `shared/AGENTS.md.tmpl` | Replace the triage section with the same new short version. |
| `shared/docs-plans-README.md.tmpl` | Replace the triage section with the same new short version. |
| `CONTRIBUTING.md` | Add new section "## Triaging review findings (full discipline)" BEFORE the existing "## Tier-1 review — prompt template" section. Content: **moved verbatim** — calibration paragraph (current CLAUDE.md line 88) + plateau rule (current CLAUDE.md line 90). No "evidence-table format guidance" — that's referenced inside the (a/b/c/d) bullets which STAY in the short block (iter-2 fold Claude 2-3: phantom content corrected). **(iter-4 fold)**: line-**114** pointer "the (a/b/c/d) framework in `CLAUDE.md`" stays — NOT updated (iter-4 Codex 1: the framework isn't moving to CONTRIBUTING.md, so the pointer remains correct). ALSO (iter-4 fold Codex 2): edit the DIFFERENT lines **111 + 190** (the Tier-1 review command + non-Claude-Code parenthetical) to replace `# or review-commit-by-codex` / "or `make review-commit-by-codex`" with same-AI Tier-1 wording — closes BACKLOG.md:557. |
| `shared/CONTRIBUTING.md.tmpl` | Mirror the new section. Also mirror the same-AI Tier-1 edits at tmpl lines 196 + 251 (iter-4 fold Codex 2). No change to tmpl line 199 — the framework pointer stays (iter-4 fold Codex 1: framework stays in CLAUDE.md). |

**Selftest_overlap impact** (iter-1 fold): `tests/test_selftest_overlap.py:81-85` checks
`shared/docs-plans-README.md.tmpl` byte-renders to `docs/plans/README.md`. Both files
get the same triage shrink in this Bucket; the test passes after Commit 1 because the
edits are byte-identical lockstep.

### Bucket B — Skill's own CLAUDE.md tightening + shared/CLAUDE.md.tmpl mirror (atomic Commit 2)

| Section | Current | Target | What stays in CLAUDE.md | What moves; destination |
|---|---|---|---|---|
| Commands table | 22 | 22 | Full table | (nothing) |
| What this repo is | 8 | 8 | Full content | (nothing) |
| Plan review loop | 34 | 6 | Lead rule + 2-line invocation + 1-line "stop when no imp-3" + 1-line pointer | Filename convention, when-to-stop bullets, consistency self-check paragraph → POINT AT `docs/plans/README.md` (already canonical there; iter-1 fold). **Bootstrap exception**: dropped from CLAUDE.md (iter-3 fold Claude 3 per user direction) — the PR-#1-specific Boxette-precursor detail is low-value historical trivia at PR #17. `docs/plans/README.md:101-105` has a DIFFERENT bootstrap exception about plan-PR/impl-PR collapsing; not equivalent. Accepted dropped-content trade-off. |
| Triaging review findings | 23 | 17 | (covered by Bucket A) | Calibration + plateau → `CONTRIBUTING.md` (Bucket A; evidence-table format stays inside the (a/b/c/d) bullets which remain in the short block — iter-2 fold Claude 2-3) |
| Two-tier code review | 8 | 6 | Tier-1 (same-AI as implementer) + Tier-2 positive description (both bots in dogfood; per-mode conditional in template) | Negative "Codex bot NOT configured" caveat removed; "Both feed the same…" sentence (already implied); same-AI Tier-1 ambiguity tightened (iter-2 refold) |
| Cross-session state recovery | 5 | 4 | First paragraph compressed | "If multiple plan files…" elaboration |
| Pre-coding gate | 9 | 9 | Full content | (nothing — dense already) |
| Self-improvement loop | 10 | 8 | "Read LESSONS.md at session start" + writable-vs-read-only summary + LESSONS.md entry-format spec + promote/archive rule + pointer to AGENTS.md | (nothing — iter-2 fold Claude 2-4: preserved format spec + promote/archive in CLAUDE.md; the savings come from removing prose padding, not dropping content) |
| Mandatory human-approval gate | 12 | 6 | 4-step rule | Per-step elaboration → POINT AT `docs/plans/README.md:60-67` step 3 (already canonical; iter-1 fold) |
| Focused commits | 14 | 6 | Rule + bash example + "Don't `git add .`" | (nothing — already short) |
| Python version | 5 | 5 | Full content | (nothing) |
| Environment | 5 | 5 | Full content | (nothing) |
| Key implementation invariants | 13 | 13 | Full content (load-bearing) | (nothing) |

**Estimated new total** (iter-2 fold Claude 2-4: self-improvement 6→8 lines to preserve format-spec): 22 + 8 + 6 + 17 + 6 + 4 + 9 + 8 + 6 + 6 + 5 + 5 + 13 + ~14 separator blanks = **~129 lines**. Still within 120-130 target.

### Bucket C — AGENTS.md + shared/AGENTS.md.tmpl tightening (atomic Commit 3)

| Section | Current | Target | What stays | What moves |
|---|---|---|---|---|
| Header + intro | 10 | 10 | Full content | (nothing) |
| What to flag with high confidence | 35 | 35 | Full content (reviewer-specific) | (nothing) |
| What NOT to flag | 5 | 5 | Full content | (nothing) |
| Local quality gate | 5 | 5 | Full content | (nothing) |
| Plan Review Guidance | 37 | 37 | Full content (reviewer-specific) | (nothing) |
| Triaging review findings | 23 | 17 | (covered by Bucket A) | (covered by Bucket A) |
| Cross-session state recovery | 5 | 4 | Compressed | "If multiple plan files…" elaboration |
| Self-improvement loop | 10 | 6 | Read LESSONS at session start + Reviewer-is-read-only rule + Do-NOT-edit + propose-not-append-in-review | Drop prose elaboration / `(Writable-session drivers…)` cross-ref line. **(iter-2 fold Claude 2-4: NOT "promote/archive elaboration" — that text isn't in AGENTS.md, it's only in CLAUDE.md; description corrected to match actual section content.)** |
| Tone | 6 | 6 | Full content | (nothing) |

**Current total** (iter-1.5 fold: arithmetic corrected — section headings + content + blanks): 10+35+5+5+37+23+5+10+6 = 136 content lines + ~5 between-section blanks = **141 lines** (matches `wc -l`). **Estimated new total**: 10+35+5+5+37+17+4+6+6 = 125 + ~9 separator blanks (after triage + self-improvement shrink) = **~134-135 lines** (range accommodates separator-blank uncertainty). Modest ~6-7-line reduction.

**(d)-class decision flagged for human-approval gate**: AGENTS.md cannot hit the
pre-loop ~80-100 target without cutting the 35-line "What to flag" or 37-line "Plan
Review Guidance" sections — both reviewer-specific and load-bearing. Accept revised
target ~134-141 (modest 0-7 line savings depending on compression tightness), OR
rewrite the reviewer-specific sections more tersely (separate exercise — out of scope
for IA refactor).

### Bucket D — gh-hint code change (Commit 4)

In `bootstrap_lib/cli.py`'s `main()`, the v1 `--apply` success block at **lines 358-378
on main** (iter-1 fold: corrected from "598-610" which was PR-#17-branch-relative).
Insert the gh-hint detection + print logic **INSIDE the existing `if args.github_review
!= "none":` block** (iter-2 fold Claude 1-1: no second conditional), BEFORE the existing
OAuth-token prints:

```python
# (existing) inside the if args.github_review != "none" block,
# BEFORE the existing CLAUDE_CODE_OAUTH_TOKEN prints, add:

    # Detect: does target_root have a git remote already?
    # Two states: (a) no .git/ at all → user needs `git init` first;
    # (b) .git/ exists but no remote → user only needs remote creation
    # (iter-1 fold: Claude 1-3 — distinguish the two cases for accurate
    # hints). Use `git -C ... remote` (subprocess, not gh CLI; gh is an
    # optional prereq but git is required).
    git_dir = target_root / ".git"
    has_git = git_dir.is_dir()
    has_remote = False
    if has_git:
        try:
            result = subprocess.run(
                ["git", "-C", str(target_root), "remote"],
                capture_output=True, text=True, check=False, timeout=5,
            )
            has_remote = result.returncode == 0 and bool(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            # iter-4 fold Claude 2.1: drop redundant FileNotFoundError
            # (subclass of OSError). SubprocessError covers TimeoutExpired
            # (which does NOT subclass OSError).
            has_remote = False

    if not has_remote:
        # iter-1 fold: Codex #1 — safe-pattern checklist, NOT bulk add.
        # iter-2 fold Claude 3-1: warning text MUST NOT contain literal
        # "git add -A" or "git add ." substrings (would self-trip the
        # regression test that asserts those substrings never appear).
        # iter-4 fold Claude 2.1: drop `f` prefix on lines without {…}
        # interpolation (F541 lint).
        # iter-4 fold Codex 4: visibility = two explicit alternatives
        # (no shell-metacharacter placeholder `<--private|--public>` —
        # `<` `|` `>` would be parsed as redirection/pipe if copy-pasted).
        print("")
        if not has_git:
            print("create the GitHub repo + push:")
            print(f"  cd {target_root}")
            print("  git init")
            print("  git status --short                 # review what's about to be staged")
            print("  git add <path1> <path2> ...        # stage explicitly per `git status` output")
            print("  git commit -m 'initial bootstrap'")
            print("  # choose ONE — copy the line for the visibility you want:")
            print(f"  gh repo create {args.github_owner}/{args.github_repo} --source=. --push --private    # private (recommended for new code with secrets)")
            print(f"  gh repo create {args.github_owner}/{args.github_repo} --source=. --push --public     # public (anyone can see)")
        else:
            print("your repo isn't on GitHub yet — create the remote + push:")
            print(f"  cd {target_root}")
            print("  git status --short                 # review uncommitted changes first")
            print("  git add <path1> <path2> ...        # stage explicitly")
            print("  git commit -m 'initial bootstrap'  # only if there are pending changes")
            print("  # choose ONE — copy the line for the visibility you want:")
            print(f"  gh repo create {args.github_owner}/{args.github_repo} --source=. --push --private    # private (recommended for new code with secrets)")
            print(f"  gh repo create {args.github_owner}/{args.github_repo} --source=. --push --public     # public (anyone can see)")
        print("  (requires `gh` CLI authenticated; no default — pick deliberately)")

    # iter-4 fold Claude 2.3: Codex setup pointer moved OUT of the
    # `if not has_remote:` block. Codex GitHub review is a one-time web-UI
    # step, orthogonal to repo creation — print it whenever
    # github_review == "both-docs", whether the target has a remote yet
    # or not. (Doc-rendering invariant: docs/codex-github-review-setup.md
    # is rendered only in both-docs mode per render.py.)
    if args.github_review == "both-docs":
        print("")
        print("  enable Codex GitHub review for this repo (one-time, web-UI):")
        print(f"    see {target_root}/docs/codex-github-review-setup.md")
```

**Placement**: INSIDE the existing `if args.github_review != "none":` block (iter-2 fold Claude 1-1: avoid two consecutive identical conditionals), BEFORE the OAuth-token prints — because creating the repo logically comes first (repo-creation → push → workflows fire → OAuth token needed for `claude[bot]` to post). **(iter-4 fold Claude 2.3)**: the both-docs Codex-setup pointer is INSIDE `!= "none"` but OUTSIDE `if not has_remote:` — both-docs setup is web-UI and orthogonal to remote existence.

**Iter-1 fold (Claude 1-2)**: dropped the `or "<owner>"` / `or args.project_name`
fallbacks — when `--github-review != none`, `_resolve_mode` already requires both
flags (cli.py:84). They can never be None at this point.

### Bucket E — Tests

| Test | Assertion |
|---|---|
| `test_triage_byte_identity.py::test_triage_block_byte_identical_across_six_surfaces` | Continues to pass — new short block is byte-identical across all 6 surfaces. |
| `test_triage_byte_identity.py::test_four_questions_extension_present` | Continues to pass — 4 question substrings preserved verbatim. |
| `test_dogfood_doc_sanity.py` | **MUST be updated in Commit 2** (iter-4 fold Claude 2.2): the `claude`-mode invariant at **lines 127-130** (iter-4 fold Claude 1.1 line-ref correction; `:125` is the `claude[bot]` assertion, not the `@codex review` one) currently asserts root CLAUDE.md does NOT mention `@codex review`. Scope item 4 adds the `@codex review` keyword to CLAUDE.md (skill repo's dogfood, both bots active — verified via PR #16 reviews). Update the assertion. ALSO reconcile the function's docstring (lines 116-119) — "catches drift between shared/CLAUDE.md.tmpl and the dogfood mirror" no longer holds for the Two-tier section since it intentionally diverges (Scope item 9). The shared-template invariant in `test_shared_templates.py:404` stays unchanged. |
| `test_selftest_overlap.py::test_overlap_docs_plans_readme` | Continues to pass after Commit 1 — `shared/docs-plans-README.md.tmpl` and `docs/plans/README.md` get the same triage shrink in lockstep (iter-1 fold: previously claimed unaffected, false). |
| NEW `test_bootstrap_cli.py::test_gh_repo_hint_when_no_git_dir` | Apply to a fresh target with no `.git/`, assert `git init` + `gh repo create` appear in stdout when --github-review=claude. |
| NEW `test_bootstrap_cli.py::test_gh_repo_hint_when_git_no_remote` | Pre-`git init` the target, apply, assert ONLY `gh repo create` (no `git init` re-run) appears. |
| NEW `test_bootstrap_cli.py::test_gh_repo_hint_absent_when_remote_exists` | Pre-init + add a remote, apply, assert NO gh-hint appears. |
| NEW `test_bootstrap_cli.py::test_gh_repo_hint_never_uses_bulk_add` | Apply to a fresh target, assert NEITHER `git add -A` NOR `git add .` appears in stdout. (iter-1 fold: Codex #1 — safety regression guard.) |
| NEW `test_bootstrap_cli.py::test_gh_repo_hint_visibility_two_alternatives` | Apply to a fresh target (iter-4 fold Codex 4 — renamed from `_visibility_placeholder_not_hardcoded_public`). Assert BOTH a `--private` command line AND a `--public` command line appear; assert "choose ONE" guidance line appears; assert the literal string `<--private|--public>` does NOT appear (shell-metacharacter safety); assert no command line ends at `--push` lacking a visibility flag (no silent default). |
| NEW `test_bootstrap_cli.py::test_gh_repo_hint_absent_in_none_mode` | Apply with `--github-review=none` to a fresh target, assert NO gh-hint appears (iter-3 fold per user direction — `none` mode skips the hint entirely). |
| NEW `test_bootstrap_cli.py::test_both_docs_mode_points_at_codex_setup_doc_no_remote` | Apply with `--github-review=both-docs` to a fresh (no-remote) target, assert stdout references `docs/codex-github-review-setup.md` (NOT inlined steps — iter-3 fold Claude 4). |
| NEW `test_bootstrap_cli.py::test_both_docs_mode_points_at_codex_setup_doc_with_remote` | Apply with `--github-review=both-docs` to a target that ALREADY has a remote (iter-4 fold Claude 2.3 — Codex web-UI setup is orthogonal to repo creation; pointer must print whether the target has a remote or not). Assert stdout references `docs/codex-github-review-setup.md`. |
| `test_shim_cli_help_consistency.py` | Continues to pass — no `_flags.py` changes. |
| `test_dogfood_doc_sanity.py::test_self_improvement_loop_instruction_present` (iter-3 fold Claude 2) | Must continue to pass — CLAUDE.md compressed self-improvement section preserves substrings `"writable implementation session"` (or `"writable-session"`) AND `"read-only"`; AGENTS.md preserves `"read-only"` AND (`"do not edit"` OR `"do not append"`). **Must-preserve-tokens added to Scope items 5 and 10** (iter-3.5 renumber). |
| `test_dogfood_doc_sanity.py::test_cross_session_recovery_instruction_present` (iter-3 fold Claude 2) | Must keep `## Cross-session state recovery` heading AND `"make status"` substring. |
| `test_dogfood_doc_sanity.py::test_two_tier_section_present_in_dogfood_claude_md` (iter-3 fold Claude 2) | Must keep `claude[bot]`, `@claude review`, `review-commit-by-claude`/`-codex` substrings. |
| `test_shared_templates.py` Two-tier parametrize (iter-3 fold Claude 2) | Per-mode exact substrings: `claude` branch must contain `"BOTH tiers"` AND must NOT contain `"@codex review"`/`"chatgpt-codex-connector"`; `both-docs` must contain `"@codex review"` + `"BOTH tiers"`; `none` must NOT contain `"BOTH tiers"`/`"claude[bot]"`/`"@codex review"`. **Must-preserve-tokens added to Scope items 4 and 9** (iter-3.5 renumber). |
| All other tests | Continue to pass. |

## Architecture decisions

- **CLAUDE.md vs CONTRIBUTING.md vs docs/plans/README.md**: three on-demand surfaces.
  CLAUDE.md is always-on session context — short rules + pointers. `docs/plans/README.md`
  is the canonical home for **plan-loop discipline** (filename convention, bootstrap
  exception, when-to-stop rule, consistency self-check cadence, human-approval-gate
  wording) — CLAUDE.md POINTS at it for these topics. `CONTRIBUTING.md` is the
  canonical home for **per-change workflow detail** (Tier-1 prompt templates,
  per-change checklist, triage calibration + plateau) —
  CLAUDE.md POINTS at it for these.
- **AGENTS.md vs CONTRIBUTING.md**: AGENTS.md is read by *review-only* agents that
  may not be able to read other docs mid-review. So AGENTS.md carries reviewer-specific
  guidance (what to flag, plan-review guidance) inline. Verbose triage detail still
  refs CONTRIBUTING.md (reviewers CAN read on-demand for that).
- **Byte-identity invariant preserved**: triage section stays byte-identical across
  the 6 surfaces (3 dogfood + 3 templates). The new shorter version is the new canonical.
- **gh-hint is informational + safe**: prints a hint; user runs `gh` themselves.
  Detection distinguishes no-`.git/` vs `.git/-but-no-remote` (iter-1 fold: Claude 1-3).
  Hint NEVER includes `git add -A` / `git add .` (iter-1 fold: Codex #1; contradicts
  `LESSONS.md:48`). User explicitly picks files. `gh repo create` visibility is shown
  as TWO explicit alternative lines (`--private` / `--public`) — no shell-metacharacter
  placeholder, no silent default (iter-4 fold Codex 4).
- **Atomic CLAUDE.md+tmpl and AGENTS.md+tmpl commits** (iter-1 fold: Claude 2-4) —
  no byte-identity test guards non-triage drift between dogfood and templates, so the
  commit boundary itself prevents drift. **Exception** (iter-4 fold Claude 2.4): the
  Two-tier section intentionally diverges between dogfood CLAUDE.md (both bots) and the
  template's `claude` Jinja branch (`claude[bot]` only) — the atomic commit still bundles
  them, but the manual-diff gate treats that section's divergence as by-design.
- **PR #17 merge handling**: independent of PR #17. Follow-up PR after PR #17 merges
  mirrors gh-hint into adopt-mode's `_main_apply_adopt`. Iter-1 fold: the original
  "no conflict expected" claim is downgraded to "verify at impl time" — the line
  numbers cited in v0 of this plan were measured against PR #17's branch (not main).
- **Self-improvement protocol stays in CLAUDE.md compressed** (iter-1 fold) — no new
  CONTRIBUTING.md section needed; the protocol fits in 8 lines of CLAUDE.md (raised from 6 at iter-2 to preserve LESSONS.md entry-format spec + promote/archive rule) +
  reference to AGENTS.md for read-only-context detail.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Byte-identity test fails due to trailing whitespace / newline drift across the 6 surfaces | Use Python script with `text.replace(OLD, NEW)` to ensure exact byte match; run test after each surface edit. |
| Four-questions test fails because a question substring got shortened | Preserve question text verbatim in new short block. |
| Selftest_overlap test fails because `docs/plans/README.md` and `shared/docs-plans-README.md.tmpl` drift | Bucket A applies the same triage shrink to both files in lockstep; run `test_selftest_overlap.py` after Commit 1. |
| Wording drift in moved-to-CONTRIBUTING.md content vs original CLAUDE.md (e.g. silent meaning change) | Move-not-rewrite discipline: text moved to CONTRIBUTING.md (calibration + plateau only — iter-3.5 fold) is moved verbatim from current CLAUDE.md lines 88 + 90. |
| CLAUDE.md cross-refs to `docs/plans/README.md` become broken if README.md is restructured | Future README.md restructure proposals should grep for cross-refs (e.g. `rg "docs/plans/README.md"`) before changing section headings. Trade-off: this isn't enforced by a test; relies on author discipline. |
| gh-hint subprocess call hangs on slow filesystems (NFS, etc.) | `subprocess.run(check=False, timeout=5)` + `except (OSError, subprocess.SubprocessError)` (iter-4 fold Claude 2.1: dropped redundant `FileNotFoundError` — subclass of `OSError`; `SubprocessError` covers `TimeoutExpired`). Detection failure → no hint printed; apply still succeeds. |
| User runs the hint's bulk-paste command, accidentally commits secrets | Mitigated by Codex #1 fold: the hint NEVER uses `git add -A`. It uses `git status --short` + `git add <files>` pattern. Test `test_gh_repo_hint_never_uses_bulk_add` enforces. |
| Test `test_gh_repo_hint_*` flaky on CI without `gh` CLI | Detection uses `git -C <out> remote`, not `gh`. `git` is already hard prereq. Test asserts hint-text appears, doesn't run `gh`. |
| PR #17's cli.py changes conflict with the gh-hint addition on merge | **Iter-3 fold Codex 1: scope decision made** — adopt-mode gh-hint is **always out of scope for this PR**, regardless of merge order. PR #17 lands first OR this PR lands first: in either case, the gh-hint mirror into `_main_apply_adopt` is a SEPARATE follow-up PR (small, focused). Avoids silent scope expansion based on timing. Verify at impl time that PR #17 doesn't modify the v1 success block (lines 358-378 on main); if it does, rebase. |
| GitLab / non-GitHub remote suppresses the gh-hint | **Accepted UNDOCUMENTED limitation** (iter-3 fold Codex 6; iter-4 fold Codex 5 — corrected: the earlier text claimed a CLAUDE.md doc note, but no Scope item or Bucket implements it, so the claim was dishonest). Detection uses `git remote` (any remote suppresses). A GitLab/local-only remote would suppress the GitHub-creation hint even though GitHub auto-review won't work without a GitHub remote. **Trade-off**: precise GitHub-remote detection (parsing `git remote -v` for `github.com` URLs) adds complexity; current detection serves the common case (`--github-review != none` users typically push to GitHub). No doc note is added in this PR — the edge case is rare for the non-coder Python-bootstrap audience and the hint fails-open (no hint ≠ broken apply). If a real user hits this, a follow-up adds precise detection. |
| `CONTRIBUTING.md` ↔ `shared/CONTRIBUTING.md.tmpl` drift (iter-3 fold Claude 7) | No byte-identity test guards this pair. Atomic Commit 1 (bundles CONTRIBUTING.md + tmpl edits) prevents intermediate drift. Manual diff during Tier-1 review verifies cuts mirror. Parity with the CLAUDE.md/AGENTS.md atomic-commit rationale. |
| Non-triage CLAUDE.md ↔ shared/CLAUDE.md.tmpl drift (no byte-identity test) | Atomic Commit 2 (CLAUDE.md + tmpl in same commit) prevents intermediate drift. Manual diff during Tier-1 review verifies the cuts mirror — **EXCEPT the Two-tier section, which intentionally diverges** (iter-4 fold Claude 2.4): dogfood CLAUDE.md describes both bots; the template's `claude` Jinja branch describes only `claude[bot]` (per Scope item 9). The manual diff must treat that section's divergence as expected, not drift. |

## Verification (acceptance criteria)

### Phase 1 — pre-implementation evidence (this plan PR)

- [ ] Plan converges (no imp-3 findings remain in iter-N's Codex + Claude reviews).
- [ ] Mandatory human-approval gate completed.

### Phase 2 — post-implementation gates

(Ordered; gate 1 must pass before gate 2.)

1. **Draft Implementation PR opened** on branch `refactor/tighten-info-architecture`
   (iter-1 fold: was `impl/...`, not in CONTRIBUTING.md branch convention).
2. **All 4 focused commits land** in order: triage shrink + CONTRIBUTING absorb +
   same-AI Tier-1 wording fix; CLAUDE.md+tmpl atomic tightening + `test_dogfood_doc_sanity.py`
   `@codex review` invariant update; AGENTS.md+tmpl atomic tightening; gh-hint code +
   8 tests.
3. **Per-commit Tier-1 review** (`make review-commit-by-{claude,codex}` — same AI
   as implementer per iter-2 fold of BACKLOG.md:557) clean (no imp-3 findings) before
   push. **Then** append the Tier-1-suggested impl-log row to the `## Implementation
   log (this PR)` section (located AFTER the Evidence table; see the section heading below) via a SEPARATE docs-only commit (per CONTRIBUTING.md:116).
4. **`make check` passes** (full pytest + ruff suite).
5. **`test_triage_byte_identity.py` passes** — triage byte-identity across 6 surfaces.
6. **`test_dogfood_doc_sanity.py` passes** — triage heading still present.
7. **`test_selftest_overlap.py` passes** — `docs-plans-README.md.tmpl` byte-identical
   to `docs/plans/README.md` (iter-1 fold: was incorrectly excluded; this gate is new).
8. **New `test_bootstrap_cli.py` gh-hint tests pass** — 8 tests (iter-4 fold Claude 2.3
   adds the with-remote both-docs variant):
   (i) no-`.git/`, (ii) `.git/`-no-remote, (iii) has-remote (no fire),
   (iv) never-uses-bulk-add regression guard, (v) visibility-two-alternatives
   (both `--private` and `--public` lines present, "choose ONE" guidance, no
   `<--private|--public>` shell-metacharacter substring, no silent default),
   (vi) `--github-review=none` no-hint guard, (vii) `--github-review=both-docs`
   points at `docs/codex-github-review-setup.md` with a no-remote target,
   (viii) `--github-review=both-docs` points at the same doc with an
   already-has-remote target.
9. **Final line counts measured**:
   - `CLAUDE.md` (skill): 120-130 (acceptable: 115-140)
   - `AGENTS.md` (skill): ~135 (down from 141 — modest, **(d)-decision accepted**
     per pre-loop revision)
   - `shared/CLAUDE.md.tmpl`: ~170-180 (down from 228; mirrors the CLAUDE.md ~55-line cut; renders to ~130-145 for typical Python+uv context — the rendered output is shorter than the template because Jinja conditionals trim language-specific branches; iter-4 fold Claude 1.2: this ~130-145 band is the single agreed rendered-size figure — the Critical-files note is synced to it)
   - `shared/AGENTS.md.tmpl`: ~109-113 (down from 119 — iter-4 fold Claude 1.2: the triage shrink alone removes ~6 lines, 23→17, before the self-improvement shrink; the earlier "~115" estimate undercounted)
   - `CONTRIBUTING.md`: ~205-220 (up from 190; absorbs only triage-section
     full-discipline — iter-1 fold: NOT also absorbing plan-loop/human-approval which
     stay in `docs/plans/README.md`)
   - `shared/CONTRIBUTING.md.tmpl`: ~265-280 (up from 252)
10. **Manual diff CLAUDE.md vs shared/CLAUDE.md.tmpl** — non-triage sections mirror
    in shape (atomic Commit 2 prevents drift; this gate is the human-discipline check),
    **except the Two-tier section, which intentionally diverges per Scope item 9**
    (iter-4 fold Claude 2.4 — dogfood = both bots; template `claude` branch =
    `claude[bot]` only). That divergence is expected, not a gate failure.
11. **Manual diff AGENTS.md vs shared/AGENTS.md.tmpl** — non-triage sections mirror.
12. **PR ready-for-review** triggers `claude[bot]` Tier-2 auto-review.
13. **Tier-2 findings triaged** per (a/b/c/d) with 4-questions check.
14. **Merge** when CI green + no imp-3 Tier-2 findings remain.

## Iteration log (this plan)

| Iter | Findings | Verdict |
|---|---|---|
| 1 (codex) | 2 imp-3 + 3 imp-2 | do not implement yet — see iter-1 fold log below |
| 1 (claude) | 2 imp-3 + 5 imp-2 + 4 imp-1 | needs another iteration — see iter-1 fold log below |
| 1-fold | All (a)-folds applied: gh-hint safe-pattern (Codex #1), content-destination rerouted to `docs/plans/README.md` (Codex #2 / Claude 3-1+3-2), selftest_overlap test added (Codex #3 / Claude 2-3), AGENTS.md target revised + arithmetic fixed (Codex #5 / Claude 2-5), cli.py line numbers corrected to 358-378 (Claude 2-1), subprocess timeout + broader except (Claude 2-2), atomic Commits 2/3 (Claude 2-4), branch prefix `refactor/...` (Claude 1-1), dead-code fallbacks dropped (Claude 1-2), gh-hint two-state detection (Claude 1-3). Codex #4 (Codex-bot wording) rejected as out-of-scope. Claude 1-4 (line-count estimates hand-wavy) rejected as already covered by acceptance band. |
| 1.5 consistency | 8 internal drifts after iter-1 fold (tmpl gate target, AGENTS.md arithmetic, gh-hint test count, triage 23 not 24 lines, README.md no-content-change reconciliation, Bucket C ref, sequencing wording, code comment match) | All folded as wording/arithmetic corrections |
| 1.5 (d)-decisions | User direction: AGENTS.md target ~134-141 accepted; content-destination via `docs/plans/README.md` confirmed; **Codex-bot wording fold revised from (c) reject → (a) fold** (closes BACKLOG.md:416) | Folded into Scope item 4 |
| 2 (codex) | 3 imp-3 + 2 imp-2 | do not implement yet — see iter-2 fold log below |
| 2 (claude) | 2 imp-3 + 5 imp-2 + 2 imp-1 | needs another iteration — see iter-2 fold log below |
| 2-fold | All (a)-folds applied. **User-direction refold on Codex-bot scope** (per "should we have negative caveats at all?"): drop the "Codex bot NOT configured" negative caveat entirely; replace with positive description of what IS active. Dogfood (CLAUDE.md): "both bots". Template (shared/CLAUDE.md.tmpl): conditional on `github_review_mode` — `claude` branch describes only `claude[bot]`, `both-docs` describes both. **User-direction expansion on gh-hint**: when `--github-review=both-docs`, also surface the manual Codex web-UI setup step (one-time per repo). Plus mechanical (a)-folds: subprocess import (Codex 3 / Claude 2-2), hint text reworded to avoid literal "git add -A" substring (Claude 3-1), Two-tier same-AI ambiguity tightened (Codex 4), Implementation log section added (Codex 5), evidence-table-format phantom content dropped (Claude 2-3), self-improvement target 6→8 to preserve format-spec (Claude 2-4), AGENTS dogfood/tmpl conflation clarified (Claude 2-5), two-consecutive-ifs merged (Claude 1-1), PR #17 merge direction both-ways (Claude 1-2). Codex 2 + Claude 2-1 (internal contradictions) folded by NOT-in-scope cleanup. |
| 2.5 consistency | 11 internal drifts after iter-2 fold: Bucket D placement contradiction (intro vs code sample vs placement note), test_dogfood_doc_sanity stale "continues to pass" claim, evidence-table-format phantom still in 3 stale spots, self-improvement 6 vs 8 in Arch decisions, AGENTS.md target stale ~125-135 in evidence table, 134/135 range drift, Tests-item test-count discrepancy, AGENTS.md-tighten item cross-ref to wrong CLAUDE.md item-5 number, Bucket B Two-tier row didn't reflect iter-2 refold, gate 3 "above" vs actual "below" Implementation log location, "10 drifts" listed only 8. | All folded as wording/arithmetic corrections |
| 3 (codex) | 3 imp-3 + 3 imp-2 | do not implement yet — see iter-3 fold below |
| 3 (claude) | 1 imp-3 + 4 imp-2 + 2 imp-1 | needs another iteration — see iter-3 fold below |
| 3-fold | All (a)-folds applied. **(d)-decisions per user direction**: `none` mode skips gh-hint entirely (Codex 2 / Claude 1 both reviewers' Option A); `gh repo create` visibility = `<--private\|--public>` placeholder, no `--public` default (Codex 3); bootstrap-exception dropped from CLAUDE.md (Claude 3 — not equivalent to README.md's bootstrap exception; accepted dropped historical trivia); (a/b/c/d) bullets compress to 1 sentence each with (d) operational guardrails dropped (Claude 5 — accepted trade-off). Plus mechanical folds: adopt-mode out-of-scope regardless of merge order (Codex 1 — eliminates scope flip-flop); Codex 4 evidence-table-format phantom continued cleanup; Codex 5 (both-docs acceptance under-verified) addressed via the both-docs setup-doc test added to Bucket E; both-docs Codex setup → cross-ref existing doc (Claude 4); GitLab/non-GitHub remote accepted as limitation (Codex 6); 4 must-preserve-token tests added to Bucket E with substring constraints (Claude 2); CONTRIBUTING.md ↔ tmpl drift row added to Risks (Claude 7); cli.py + LESSONS.md line numbers cleanup (Claude 6). |
| 3.5 consistency | 5 internal drifts after iter-3 fold: AGENTS.md target range ~135-141 vs ~134-141 (pre-loop misquoted Bucket C), evidence-table-format phantom STILL stale in Scope item 2 + Risks row (missed by iter-2.5/iter-3 cleanup), Phase 2 gate 8 says "7 tests" but enumerated only 4, CLAUDE.md Cross-session-recovery shrink (5→4) had no Scope item — Bucket B covered it but Scope items 3-7 omitted; added as new Scope item 7 with renumber 7-12 → 8-13; cosmetic evidence-table commit-merge wording. | All folded; renumbered cross-refs (Scope items 8→9, 10→11, 11→12, 12→13 + token-preservation lines updated) |
| 4 (codex) | 3 imp-3 + 2 imp-2 | do not implement yet — see iter-4 fold below |
| 4 (claude) | 0 imp-3 + 4 imp-2 + 2 imp-1 | ready after minor edits — see iter-4 fold below |
| 4-fold | **2 real imp-3** (one Codex imp-3 rejected — see below). (a)-folds: CONTRIBUTING.md:111 pointer NOT changed — framework stays in CLAUDE.md, the planned "below in this document" edit was a broken cross-ref (Codex 1); same-AI Tier-1 wording fix added to CONTRIBUTING.md 111/190 + tmpl 196/251, closes BACKLOG.md:557 properly (Codex 2 — earlier plan claimed closure via CLAUDE.md edit alone, but CONTRIBUTING.md still had the ambiguity); `gh repo create` visibility = TWO explicit `--private`/`--public` lines instead of shell-metacharacter-unsafe `<--private\|--public>` placeholder (Codex 4); GitLab-remote limitation corrected to "accepted UNDOCUMENTED" — earlier text claimed a CLAUDE.md doc note that no Scope item delivered (Codex 5); Bucket D code lint fixes — drop `f` on no-interpolation prints (F541), `except` tuple simplified to `(OSError, subprocess.SubprocessError)` (Claude 2.1); `test_dogfood_doc_sanity.py` `@codex review` update assigned to Commit 2 + line-ref corrected 125→127-130 + docstring reconciliation (Claude 2.2 + 1.1); both-docs Codex-setup pointer moved OUT of `if not has_remote:` — fires whenever both-docs regardless of remote (Claude 2.3); Two-tier intentional-divergence carve-out added to Gate 10 + Risks + Architecture (Claude 2.4); line-count estimates synced — `shared/AGENTS.md.tmpl` ~109-113, `shared/CLAUDE.md.tmpl` rendered band ~130-145 single figure (Claude 1.2). **Codex 3 REJECTED (c)**: claimed skill-repo dogfood is claude-only (PR template lists only `claude[bot]`) — premise wrong; verified via `gh pr view 16` that PR #16 was reviewed by BOTH `chatgpt-codex-connector` + `claude` bots. The PR template IS stale (missing Codex bot) — flagged as a separate follow-up, out of scope for the IA refactor. Test count 7 → 8 NEW (Claude 2.3 with-remote variant). |

## Evidence table — what was folded and where

| Source | Finding (one-line) | Triage | Where in plan |
|---|---|---|---|
| Codex iter-1 #1 | `git add -A` unsafe per LESSONS.md:48 | **(a) fold** | Bucket D code sample uses safe explicit-paths pattern + `git status` checklist; new test `test_gh_repo_hint_never_uses_bulk_add`; Architecture-decisions "gh-hint informational + safe" bullet |
| Codex iter-1 #2 / Claude 3-1+3-2 | "No content loss" contradicts NOT-in-scope; verbose detail already in `docs/plans/README.md`, not CONTRIBUTING.md | **(a) major refold** | Buckets A+B re-routed: plan-loop / human-approval detail → POINT AT `docs/plans/README.md`; self-improvement protocol → stays in CLAUDE.md compressed; only triage calibration/plateau/evidence-table → CONTRIBUTING.md |
| Codex iter-1 #3 / Claude 2-3 | NOT-in-scope falsely says selftest_overlap unaffected | **(a) fold** | Bucket E test list now includes `test_overlap_docs_plans_readme`; Phase 2 gate 7 added; NOT-in-scope claim removed |
| Codex iter-1 #4 | Codex-bot wording is stale in files we touch | **(a) fold** (iter-1.5 revision per user direction) | Scope item 4 now includes the Codex-bot wording fix: "Tier-2 runs both `claude[bot]` + `chatgpt-codex-connector[bot]`" in CLAUDE.md, with proper Jinja-conditional in `shared/CLAUDE.md.tmpl` for `github_review_mode`. Closes BACKLOG.md:416. |
| Codex iter-1 #5 / Claude 2-5 | AGENTS.md target ~80-100 unachievable; arithmetic doesn't add up | **(a) fold + (d) surface to human** | Pre-loop constraint revised: AGENTS.md ~134-141 acceptable; Bucket C arithmetic corrected; (d)-decision flagged for human-approval gate |
| Claude 2-1 | cli.py line numbers wrong (598-610 is PR-#17-branch, not main) | **(a) fold** | Bucket D: "lines 358-378 on main"; Risks row downgraded "no-conflict" claim to "verify at impl time" |
| Claude 2-2 | gh-hint subprocess missing `timeout=` + can't catch TimeoutExpired | **(a) fold** | Bucket D code includes `timeout=5` + `except (..., subprocess.SubprocessError)`; Risks row reconciled |
| Claude 2-4 | No byte-identity test for non-triage CLAUDE.md↔tmpl drift | **(a) fold** | Sequencing reduced 5 → 4 commits (CLAUDE.md+tmpl merged atomic into Commit 2; AGENTS.md+tmpl merged atomic into Commit 3 — see Sequencing section). Phase 2 gates 10+11 added for manual diff check |
| Claude 1-1 | Branch prefix `impl/` not in CONTRIBUTING list | **(a) fold** | Phase 2 gate 1: `refactor/tighten-info-architecture` |
| Claude 1-2 | Dead-code `or "<owner>"` fallbacks | **(a) fold** | Bucket D code sample drops the fallbacks; comment explains why |
| Claude 1-3 | gh-hint says `git init` even when target is already a git repo | **(a) fold** | Bucket D distinguishes no-`.git/` vs `.git/-but-no-remote`; two-state print logic |
| Claude 1-4 | Line-count estimates hand-wavy | **(c) reject** | Acceptance band already absorbs estimate noise; line-count is auditable post-impl via `wc -l` |
| Codex iter-2 #1 / Claude 3-2 | Codex-bot wording fold breaks claude-mode tests; underspecified for template | **(a) fold + user-direction refold (positive-framing)** | Scope item 4: drop negative caveat entirely; Scope item 9: explicit per-`github_review_mode` template branches; positive description (skill repo's dogfood = both bots active; template `claude` = only claude[bot]; template `both-docs` = both bots) |
| Codex iter-2 #2 / Claude 2-1 | Plan internally contradicts on Codex-bot scope (NOT-in-scope + Critical files still say out-of-scope) | **(a) fold** | NOT-in-scope bullet removed; Critical files note flipped to "folded by this PR (Scope item 4)" |
| Codex iter-2 #3 / Claude 2-2 | Bucket D uses `subprocess` but `cli.py` doesn't import it | **(a) fold** | Scope item 12 + Bucket D explicitly add `import subprocess` to cli.py's import block |
| Codex iter-2 #4 | Same-AI Tier-1 ambiguity in Two-tier section (BACKLOG.md:557) | **(a) fold** | Scope item 4 also tightens "use the same AI as the implementer; cross-AI review is Tier-2"; closes BACKLOG.md:557 |
| Codex iter-2 #5 | Missing `## Implementation log (this PR)` section per docs/plans/README.md:85 | **(a) fold** | New section added (below); Phase 2 gate added for impl-log row appending per CONTRIBUTING.md:116 |
| Claude iter-2 3-1 | gh-hint warning text literally contains "git add -A" / "git add ." substrings → self-trips its own regression-guard test | **(a) fold** | Bucket D code reworded: "stage explicitly per `git status` output" — no literal forbidden substrings |
| Claude iter-2 2-3 | "Evidence-table format guidance" is phantom content (not a standalone paragraph) | **(a) fold** | Dropped from moved-content list everywhere; CONTRIBUTING.md new section contains ONLY calibration + plateau (verbatim from CLAUDE.md lines 88+90) |
| Claude iter-2 2-4 | Self-improvement shrink would drop LESSONS.md format spec + promote/archive rule with no destination | **(a) fold** | Scope item 5 target raised 6 → 8 lines to preserve format-spec + promote/archive in CLAUDE.md |
| Claude iter-2 2-5 | Bucket C conflates dogfood AGENTS.md with shared/AGENTS.md.tmpl (structurally different sections) | **(a) fold** | Scope item 11 clarifies: mirror ONLY Cross-session-recovery + Self-improvement shrinks; "What to flag" / "Plan Review Guidance" differ by design |
| Claude iter-2 1-1 | Bucket D produces two consecutive identical `if args.github_review != "none":` blocks | **(a) fold** | Bucket D placement note: gh-hint goes INSIDE existing `if`, before OAuth prints |
| Claude iter-2 1-2 | PR #17 merge ordering covered only one direction | **(a) fold** | Risks row updated: states which PR lands first OR notes both directions |
| User direction (iter-2 expansion) | gh-hint should include Codex web-UI setup step | **(a) fold — superseded iter-3/iter-4** | Original iter-2 design printed a 3-line inline Codex setup block. iter-3 fold Claude 4 replaced it with a 2-line pointer to `docs/codex-github-review-setup.md` (single source of truth, avoids ChatGPT-UI drift). iter-4 fold Claude 2.3 moved that pointer OUT of `if not has_remote:` so it fires for any both-docs run. Current Bucket D = 2-line pointer, not inline steps. |
| Codex iter-4 #1 | Plan's CONTRIBUTING.md line-114 edit ("the (a/b/c/d) framework below in this document") is a broken cross-ref — the framework is NOT moving to CONTRIBUTING.md | **(a) fold** | Scope item 2 + Bucket A: line-111 pointer to CLAUDE.md stays unchanged; planned edit dropped |
| Codex iter-4 #2 | Plan claims to close BACKLOG.md:557 but CONTRIBUTING.md still has `# or review-commit-by-codex` same-AI Tier-1 ambiguity (lines 111 + 190; tmpl 196 + 251) | **(a) fold** | Scope item 2 extended: edit those 4 lines to same-AI Tier-1 wording in Commit 1; verified against `LESSONS.md` 2026-05-19 entry |
| Codex iter-4 #3 | Claims skill-repo dogfood is `claude`-only (PR template lists only `claude[bot]`); plan's "both bots active" claim is wrong | **(c) reject — premise wrong** | Verified `gh pr view 16`: PR #16 reviewed by BOTH `chatgpt-codex-connector` + `claude` bots — both ARE active. The `.github/pull_request_template.md` IS stale (missing Codex bot row); flagged as separate follow-up, out of scope for the IA refactor |
| Codex iter-4 #4 | `gh repo create ... <--private\|--public>` placeholder is shell-metacharacter unsafe (`<` `\|` `>`) for copy-paste | **(a) fold** | Bucket D: print TWO explicit `--private` / `--public` command lines under "choose ONE"; preserves the iter-3 "force deliberate choice / no `--public` default" intent. Test renamed `_visibility_two_alternatives` |
| Codex iter-4 #5 | Risks row claims GitLab-limitation is documented in CLAUDE.md, but no Scope item delivers that doc note | **(a) fold** | Risks row corrected to "accepted UNDOCUMENTED limitation" — honest; the edge case is rare for the audience and fails-open |
| Claude iter-4 2.1 | Bucket D code sample trips F541 (`print(f"…")` without `{}`) + redundant `FileNotFoundError` in `except` | **(a) fold** | Bucket D: `f` prefix dropped on no-interpolation prints; `except (OSError, subprocess.SubprocessError)`; Risks row re-synced |
| Claude iter-4 2.2 | `test_dogfood_doc_sanity.py` `@codex review` update not assigned to a commit — Commit 2 introduces the keyword, leaving pytest red | **(a) fold** | Scope item 13(ii) + Sequencing: test update lands in Commit 2 |
| Claude iter-4 2.3 | both-docs Codex-setup pointer nested inside `if not has_remote:` — both-docs targets that already have a remote get no pointer | **(a) fold** | Bucket D: pointer moved OUT of `if not has_remote:`, fires whenever `github_review == "both-docs"`; NEW 8th test for the with-remote case |
| Claude iter-4 2.4 | Plan contradicts itself: Scope item 9 makes Two-tier intentionally diverge dogfood↔template, but Gate 10 / Risks / Architecture assert non-triage sections mirror | **(a) fold** | Carve-out clause added to Gate 10, Risks row, Architecture-decisions atomic-commit bullet |
| Claude iter-4 1.1 | `test_dogfood_doc_sanity.py:125` line-ref wrong (125 is `claude[bot]` assertion; `@codex` block is 127-130); stale docstring | **(a) fold** | Line-ref corrected throughout; docstring reconciliation added to Scope item 13(ii) |
| Claude iter-4 1.2 | Line-count estimates internally inconsistent (`shared/AGENTS.md.tmpl` −4 vs actual ~−6-10; `shared/CLAUDE.md.tmpl` rendered ~140-160 vs ~130-145) | **(a) fold** | `shared/AGENTS.md.tmpl` → ~109-113; rendered band unified to ~130-145 in gate 9 + Critical-files |

## Implementation log (this PR)

(empty; gets populated per Tier-1 review during impl, per CONTRIBUTING.md:116
mandate that each substantive commit's Tier-1-suggested impl-log row is appended in a
separate docs-only commit)

| short-sha | what landed | deviations from plan, or 'none' | issues faced, or 'none' |
|---|---|---|---|

## Lessons surfaced

- **Plan author error to avoid**: line-number references in plans should be measured
  against the branch the plan will be implemented on (main, in this case), not the
  branch the author was working in when drafting (Claude 2-1). When citing
  `cli.py:N`, always run `git checkout main` first and `wc -l` to verify.
- **Information-architecture risk**: "move detail to CONTRIBUTING.md" is the wrong
  default when `docs/plans/README.md` is already canonical. The default move for
  plan-loop discipline is "point at docs/plans/README.md", not "duplicate into
  CONTRIBUTING.md" (Claude 3-2). This is a project-specific lesson that should land
  in `LESSONS.md` during impl (after impl PR's first Tier-1).

## What we are NOT doing in this PR

- Adopt-mode (PR #17) gh-hint — follow-up PR after PR #17 merges.
- CONTRIBUTING.md restructure beyond Bucket A's new triage section.
- Restructure of docs/plans/README.md beyond the triage section.
- Wording rewrites of preserved CLAUDE.md / AGENTS.md sections (move-not-rewrite).
- Updates to BACKLOG.md (handled in impl PR).
- Cross-language adoption-mode (Node, Go) — parked separately.
- Full both-docs promotion (Codex setup docs, PR-template changes, broad test
  updates) — out of scope; this PR scopes the Codex-bot wording fix to *describing
  what IS active* (skill repo's dogfood) without changing the skill's `--github-review`
  default emission.
- **`.github/pull_request_template.md` Codex-bot row** (iter-4 fold Codex 3) — the
  skill repo's PR template lists only `claude[bot]` in its AI-reviewer checklist, even
  though `chatgpt-codex-connector[bot]` also auto-reviews (verified via PR #16). That
  template is genuinely stale, but fixing it is a separate one-line follow-up — not
  part of the CLAUDE.md/AGENTS.md/CONTRIBUTING.md IA refactor this PR scopes.

## Critical files to read before each iter's review

- `CLAUDE.md` (skill repo's own) — current 182 lines
- `AGENTS.md` (skill repo's own) — current 141 lines
- `CONTRIBUTING.md` (skill repo's own) — current 190 lines
- `docs/plans/README.md` — current 157 lines (already canonical for plan-loop;
  CLAUDE.md will POINT here)
- `shared/CLAUDE.md.tmpl` — current 228 lines (rendered output varies by context: ~130-145 for typical Python+uv runs — iter-4 fold Claude 1.2: synced to the single agreed band in Phase-2 gate 9; the 228 line count is the unrendered template with Jinja conditionals)
- `shared/AGENTS.md.tmpl` — current 119 lines
- `shared/CONTRIBUTING.md.tmpl` — current 252 lines
- `shared/docs-plans-README.md.tmpl` — current 157 lines
- `tests/test_triage_byte_identity.py` — the byte-identity test (6 surfaces)
- `tests/test_selftest_overlap.py` — checks docs-plans-README.md.tmpl byte-renders
  to docs/plans/README.md (iter-1 fold: was missed; is in scope)
- `tests/test_dogfood_doc_sanity.py` — the triage-presence test
- `bootstrap_lib/cli.py` lines **358-378** — the v1 post-apply success block where
  gh-hint goes (iter-1 fold: corrected from 598-610)
- `tests/test_bootstrap_cli.py` — pattern for the new gh-hint tests
- `LESSONS.md:48` — the don't-bulk-add lesson the gh-hint must respect
- `BACKLOG.md:416` — the Codex-bot wording entry, **folded by this PR** (Scope item 4); will be marked ✅ Done in impl PR's BACKLOG.md edit.
- `BACKLOG.md:557` — the same-AI Tier-1 ambiguity entry, **folded by this PR** (Scope item 4 also); marked ✅ Done at impl time.
- `tests/test_dogfood_doc_sanity.py` **lines 127-130** (iter-4 fold Claude 1.1 — `:125` was the wrong line; 125 is the `claude[bot]` assertion, the `@codex review` block is 127-130) — the dogfood invariant that asserts root CLAUDE.md does NOT mention `@codex review`; must be updated to ALLOW the mention (positive Codex-bot description in Scope item 4 includes `@codex review` keyword). The function docstring (lines 116-119) must also be reconciled — see Scope item 13(ii).
- `tests/test_shared_templates.py:404` — the template-side invariant for `claude` mode; stays unchanged (template's `claude` branch only describes `claude[bot]`, no `@codex`).
- PR #17 (open) — the adoption-mode work in flight; this PR is independent but its
  gh-hint will need a mirror-edit in `_main_apply_adopt` after PR #17 merges (verify
  no-conflict claim at impl time)
