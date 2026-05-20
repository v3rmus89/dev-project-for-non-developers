# Plan PR: tighten CLAUDE.md / AGENTS.md information architecture + add gh-repo hint

## Context

The skill currently loads ~182 lines into every Claude Code session via `CLAUDE.md`, and
~141 lines into every read-only review session via `AGENTS.md`. Both files were grown
incrementally across PR #1–#7 — most additions earned their place at the time, but the
result is verbose enough that priority signal dilutes. The PR #7 trial against
`call-details/` surfaced the issue empirically: when the rendered `CLAUDE.md.new`
(~160 lines) merged with the user's existing 96-line CLAUDE.md, the combined version
hit 233 lines before any tightening — at that point, the "every line earns its place"
test was failing.

The user's stated principle: **CLAUDE.md should be short** — it's the always-on context;
every line should be either a rule you can't afford to forget OR a pointer to where
detail lives. **Detail-rich content** (workflow steps, prompt templates, calibration
paragraphs, examples) **belongs in `CONTRIBUTING.md`**, which is consulted on-demand,
not loaded into context every session.

This plan tightens the skill repo's own `CLAUDE.md` + `AGENTS.md` (the dogfood docs)
AND the templates that render to generated projects, absorbing verbose detail into
`CONTRIBUTING.md` (skill + tmpl). Plus adds a `gh repo create` hint to the post-apply
"next steps" output when `--github-review != none` and no remote is detected (per user
request 2026-05-20).

### Pre-loop user-decided scope constraints (before iter-1)

- **Target line counts**: `CLAUDE.md` (skill's own) ~120-130 lines; `AGENTS.md` ~80-100;
  `CLAUDE.md.tmpl` / `AGENTS.md.tmpl` similar. Hard target is **density** (every line
  earns its place), not the exact number.
- **Byte-identity invariant**: the "## Triaging review findings" section must remain
  byte-identical across six surfaces (`CLAUDE.md` + `AGENTS.md` + `docs/plans/README.md`
  + their 3 `shared/*.tmpl` counterparts), enforced by
  `tests/test_triage_byte_identity.py`. Any wording change cascades across all 6.
- **Four-questions test invariant**: `tests/test_triage_byte_identity.py::
  test_four_questions_extension_present` asserts exact substring text for the 4
  questions. New short version must preserve: "Before deciding (a/b/c/d), ask these
  four questions" + each question's first sentence ("Is the premise correct?", "Is
  the suggested fix the best fix", "What else does this finding imply?", "Does folding
  introduce a contradiction").
- **No content loss**: verbose content moved out of CLAUDE.md/AGENTS.md/templates must
  land in CONTRIBUTING.md + shared/CONTRIBUTING.md.tmpl so the cross-refs resolve.
- **gh-hint is a code change, not a doc change**: small addition to
  `bootstrap_lib/cli.py`'s post-apply success path; one if-branch + one print.
- **PR #17 merge-conflict risk**: PR #17 (open) heavily modifies `bootstrap_lib/cli.py`
  but doesn't touch the success-print block of `main()`. The gh-hint edit happens in
  the v1 success path (untouched by PR #17). When PR #17 merges, the gh-hint also
  needs landing in adopt-mode's `_main_apply_adopt` success path — flagged as a
  follow-up here (NOT in scope for this PR).

### Sequencing within this PR

The PR ships as multiple focused commits:

1. **Commit 1**: Triage section shrink across the 6 byte-identity surfaces +
   absorb the verbose content (calibration paragraph, plateau rule, evidence-table
   format) into CONTRIBUTING.md + shared/CONTRIBUTING.md.tmpl. Most coordinated
   piece (byte-identity test passes after).
2. **Commit 2**: Tighten CLAUDE.md (skill's own) other sections — plan-review-loop,
   self-improvement-loop, mandatory-human-approval-gate, focused-commits — moving
   detail to CONTRIBUTING.md.
3. **Commit 3**: Mirror Commit 2's changes to `shared/CLAUDE.md.tmpl`, preserving
   Jinja conditionals.
4. **Commit 4**: Tighten AGENTS.md (skill's own) other sections + mirror to
   `shared/AGENTS.md.tmpl`.
5. **Commit 5**: Add gh-repo-create hint to `bootstrap_lib/cli.py`'s v1 post-apply
   success path + test.

Tier-1 review per commit before push. Total estimated 4-6 hours including loop overhead.

## Scope

### IN scope

| # | Change | Where |
|---|---|---|
| 1 | Shrink "## Triaging review findings" verbose block (24 lines) → short version (~17 lines): 4-option bullets compressed to 1 sentence each, drop "The loop converges faster…" filler, drop "These four questions add ~30 seconds…" filler, drop the Calibration paragraph, drop the plateau-rule paragraph. Keep the 4 options + the 4 questions (with exact substring text per byte-identity test). End with: "See `CONTRIBUTING.md` for the full triage discipline: imp-3 calibration, plateau rule, evidence-table format." | `CLAUDE.md`, `AGENTS.md`, `docs/plans/README.md`, `shared/CLAUDE.md.tmpl`, `shared/AGENTS.md.tmpl`, `shared/docs-plans-README.md.tmpl` (all 6 byte-identity surfaces) |
| 2 | Add the verbose content moved out of the triage section to `CONTRIBUTING.md` + `shared/CONTRIBUTING.md.tmpl` — new section "## Triaging review findings (full discipline)" placed BEFORE the existing "## Tier-1 review — prompt template for in-session subagents". Includes calibration paragraph + plateau rule + evidence-table format guidance. | `CONTRIBUTING.md`, `shared/CONTRIBUTING.md.tmpl` |
| 3 | Tighten `CLAUDE.md` (skill's own) ## Plan review loop section from 34 lines → ~8 lines: keep the rule ("write to `docs/plans/...`, run review-plan-by-codex + claude, stop when no imp-3 remain"), drop the detailed iteration cadence + filename convention + bootstrap-exception. Move detail to CONTRIBUTING.md. | `CLAUDE.md` |
| 4 | Tighten `CLAUDE.md` ## Two-tier code review from 8 lines → ~6 lines: keep Tier-1 + Tier-2 rule, drop "Both feed the same…" sentence. | `CLAUDE.md` |
| 5 | Tighten `CLAUDE.md` ## Self-improvement loop (LESSONS.md) from 10 lines → ~6 lines: keep "read LESSONS.md at session start" + 1-line writable-vs-read-only summary + pointer. Move full writable-vs-read-only protocol to CONTRIBUTING.md. | `CLAUDE.md` |
| 6 | Tighten `CLAUDE.md` ## Mandatory human-approval gate from 12 lines → ~6 lines: keep the 4-step rule (summary→approve/changes/read-full→fold→approve→commit), drop the "Wait for…" elaboration. Pointer to docs/plans/README.md step 3 for canonical wording. | `CLAUDE.md` |
| 7 | Tighten `CLAUDE.md` ## Focused commits from 14 lines → ~6 lines: keep the rule + 4-line bash example + "Don't `git add .`" warning. Drop the elaboration. Pointer to CONTRIBUTING.md per-change checklist. | `CLAUDE.md` |
| 8 | Mirror items 3-7 to `shared/CLAUDE.md.tmpl`, preserving Jinja conditionals (`{% if package_manager %}`, `{% if github_review_mode %}`, etc.). The template has language-specific + package-manager-specific branches that the skill's own CLAUDE.md doesn't. | `shared/CLAUDE.md.tmpl` |
| 9 | Tighten `AGENTS.md` (skill's own): keep "What to flag with high confidence" + "What NOT to flag" + "Local quality gate" + "Plan Review Guidance" + "Tone" sections (these are reviewer-specific). Tighten "Cross-session state recovery" + "Self-improvement loop" sections (mirror CLAUDE.md cuts). | `AGENTS.md` |
| 10 | Mirror item 9 to `shared/AGENTS.md.tmpl`. | `shared/AGENTS.md.tmpl` |
| 11 | Add gh-repo-create hint to `bootstrap_lib/cli.py`'s v1 post-apply success path (around line 598-610, the `if args.github_review != "none":` block). When the apply succeeds AND `--github-review != none` AND target directory has NO git remote (`git -C <out> remote` returns empty), print: `"create the GitHub repo + push:\n  cd <out> && git init && git add -A && git commit -m 'initial bootstrap' && gh repo create <owner>/<repo> --source=. --push --public"` (or similar). | `bootstrap_lib/cli.py` |
| 12 | Tests: extend `tests/test_bootstrap_cli.py` to verify the gh-hint fires when expected + doesn't fire when remote already exists. | `tests/test_bootstrap_cli.py` |

### NOT in scope

- **gh-hint in adopt-mode's `_main_apply_adopt` success path** — that code doesn't exist
  on main yet (lives in PR #17). After PR #17 merges, a follow-up PR will mirror the
  hint into the adopt-mode success path.
- **CONTRIBUTING.md restructure beyond absorbing the moved content** — the existing
  CONTRIBUTING.md sections (One-time setup, Per-change checklist, Branch naming, etc.)
  stay as-is. Only the new "## Triaging review findings (full discipline)" section is
  added.
- **Restructure of docs/plans/README.md beyond the triage section change** — the
  surrounding content (When to write a plan, File naming, Workflow) stays.
- **Re-running the selftest overlap test** — only impacted if a selftested template
  changes shape (none here do).
- **`Key implementation invariants` section in skill's CLAUDE.md** — those are
  load-bearing technical constraints that earn their place. Preserve verbatim.
- **`Hard rules — PII` section** (only in the call-details merge, not in skill's
  CLAUDE.md) — keep verbatim in the call-details version (already done outside this PR).
- **Substantive English rewrites of preserved text** — the goal is to MOVE detail to
  CONTRIBUTING.md, not to RE-WRITE detail. The text that stays in CLAUDE.md stays
  as-is for the un-moved sections. Reduces risk of accidental wording drift that
  breaks the byte-identity test.
- **`tests/test_triage_byte_identity.py` modifications** — the test stays as-is; the
  new short triage block must pass it. The 4-questions-presence test also stays as-is;
  the short block preserves the required substrings.
- **Updating `BACKLOG.md` to add the "adopt-mode gh-hint follow-up" entry** — this is
  noted in the implementation PR's BACKLOG.md addition, not in the plan.

## Subsystem breakdown

### Bucket A — Triage section shrink (6 surfaces) + CONTRIBUTING.md absorption (2 surfaces)

| File | Change |
|---|---|
| `CLAUDE.md` | Replace lines 68-90 (current verbose triage block) with the new short version (~17 lines). |
| `AGENTS.md` | Replace lines 95-117 (byte-identical block) with the same new short version. |
| `docs/plans/README.md` | Replace the triage section (find by grep `^## Triaging`) with the same new short version. |
| `shared/CLAUDE.md.tmpl` | Replace the triage section with the same new short version. |
| `shared/AGENTS.md.tmpl` | Replace the triage section with the same new short version. |
| `shared/docs-plans-README.md.tmpl` | Replace the triage section with the same new short version. |
| `CONTRIBUTING.md` | Add new section "## Triaging review findings (full discipline)" BEFORE the existing "## Tier-1 review — prompt template" section. Content: calibration paragraph + plateau rule + evidence-table format guidance. Also update line 114 of existing per-change checklist to refer to "the (a/b/c/d) framework below" instead of "in `CLAUDE.md`". |
| `shared/CONTRIBUTING.md.tmpl` | Mirror the new section + line-114 update from CONTRIBUTING.md. |

### Bucket B — Skill's own CLAUDE.md tightening (other sections)

| Section | Current lines | Target | What stays | What moves to CONTRIBUTING.md |
|---|---|---|---|---|
| Commands table | 22 | 22 | Full table | (nothing) |
| What this repo is | 8 | 8 | Full content | (nothing) |
| Plan review loop | 34 | 8 | Lead sentence + 2-line `make review-plan-by-codex` + `make review-plan-by-claude` invocation, "stop when no imp-3" rule, pointer to CONTRIBUTING.md for filename convention + bootstrap-exception + iteration cadence + consistency self-check detail | The Filename convention paragraph, the Bootstrap exception paragraph, the When-to-stop bullets, the Pre-next-iter consistency self-check paragraph |
| Triaging review findings | 23 | 17 | (covered by Bucket A) | (full discipline → CONTRIBUTING.md, per Bucket A) |
| Two-tier code review | 8 | 6 | Tier-1 + Tier-2 rules | "Both feed the same (a/b/c/d) triage rule…" sentence (already implied) |
| Cross-session state recovery | 5 | 4 | First paragraph compressed | The "If multiple plan files…" elaboration |
| Pre-coding gate | 9 | 9 | Full content | (nothing — this section is dense already) |
| Self-improvement loop | 10 | 6 | "Read LESSONS.md at session start" + 1-line writable-vs-read-only summary + pointer | The full writable-vs-read-only protocol + promote/archive rules |
| Mandatory human-approval gate | 12 | 6 | 4-step rule | Elaboration of each step + the docs/plans/README.md step-3 pointer (kept as 1-line) |
| Focused commits | 14 | 6 | Rule + bash example + "Don't `git add .`" | (nothing — already short) |
| Python version | 5 | 5 | Full content | (nothing) |
| Environment | 5 | 5 | Full content | (nothing) |
| Key implementation invariants | 13 | 13 | Full content | (nothing — load-bearing technical constraints) |

**Estimated new total**: 22 + 8 + 8 + 17 + 6 + 4 + 9 + 6 + 6 + 6 + 5 + 5 + 13 + section-separator blanks (~14) = **~129 lines**. Within 120-130 target.

### Bucket C — shared/CLAUDE.md.tmpl tightening

Mirror Bucket B. Preserve all Jinja conditionals:
- `{% if language == "python" %}` and `{% if package_manager == "uv" %}` for language/PM-specific guidance
- `{% if github_review_mode == "claude" %}` etc. for github-review-specific notes
- `{{ project_name }}`, `{{ python_version }}` etc. variable substitutions

The template renders to ~120-130 lines for typical Python+uv project contexts.

### Bucket D — AGENTS.md + shared/AGENTS.md.tmpl tightening

| Section | Current lines | Target | What stays | What moves |
|---|---|---|---|---|
| Header + intro | 10 | 10 | Full content | (nothing) |
| What to flag with high confidence | 45 | 45 | Full content (reviewer-specific) | (nothing) |
| What NOT to flag | 5 | 5 | Full content | (nothing) |
| Local quality gate | 3 | 3 | Full content | (nothing) |
| Plan Review Guidance | 37 | 37 | Full content (reviewer-specific) | (nothing) |
| Triaging review findings | 23 | 17 | (covered by Bucket A) | (covered by Bucket A) |
| Cross-session state recovery | 5 | 4 | Mirror CLAUDE.md cut | |
| Self-improvement loop | 10 | 6 | Mirror CLAUDE.md cut | (full protocol already in CONTRIBUTING.md per Bucket A) |
| Tone | 5 | 5 | Full content | (nothing) |

**Estimated new total**: 10+45+5+3+37+17+4+6+5 + section-separator blanks (~9) = **~141 lines**. Slightly above the 80-100 target — but the "What to flag with high confidence" + "Plan Review Guidance" sections are reviewer-specific and can't be moved to CONTRIBUTING.md without losing their purpose. AGENTS.md is read by review-only agents who can't read CONTRIBUTING.md mid-review (well, they CAN, but the rules need to be at-hand for fast triage). Targeting AGENTS.md ~135 lines is realistic; going below 100 would require dropping reviewer-specific guidance which is exactly what AGENTS.md exists to carry.

**Decision**: Accept AGENTS.md at ~135 lines (down from 141 — 6-line savings from triage shrink + Self-improvement compression).

### Bucket E — gh-hint code change

In `bootstrap_lib/cli.py`'s `main()`, the v1 `--apply` success block (around line 598-610), add a new block:

```python
if args.github_review != "none":
    # Detect: does target_root have a git remote already?
    try:
        result = subprocess.run(
            ["git", "-C", str(target_root), "remote"],
            capture_output=True, text=True, check=False,
        )
        has_remote = result.returncode == 0 and result.stdout.strip()
    except (FileNotFoundError, OSError):
        has_remote = False

    if not has_remote:
        owner = args.github_owner or "<owner>"
        repo = args.github_repo or args.project_name
        print("")
        print(f"create the GitHub repo + push (target has no git remote yet):")
        print(f"  cd {target_root}")
        print(f"  git init && git add -A && git commit -m 'initial bootstrap'")
        print(f"  gh repo create {owner}/{repo} --source=. --push --public")
        print(f"  (or --private; requires `gh` CLI authenticated)")
```

Placement: AFTER the existing CLAUDE_CODE_OAUTH_TOKEN instructions if `--github-review != none`, OR BEFORE them (TBD during impl based on flow readability). Suggested: BEFORE the OAuth-token instructions, because creating the repo logically comes first.

### Bucket F — Tests

| Test | Assertion |
|---|---|
| `test_triage_byte_identity.py::test_triage_block_byte_identical_across_six_surfaces` | Continues to pass — the new short block is byte-identical across all 6 surfaces. |
| `test_triage_byte_identity.py::test_four_questions_extension_present` | Continues to pass — the 4 question substrings are preserved verbatim. |
| `test_dogfood_doc_sanity.py` | Continues to pass — the triage heading still exists. |
| NEW `test_bootstrap_cli.py::test_gh_repo_hint_when_no_remote` | Apply to a fresh target, assert "gh repo create" appears in stdout when --github-review=claude + no remote. |
| NEW `test_bootstrap_cli.py::test_gh_repo_hint_absent_when_remote_exists` | Pre-init target with `git init` + add a remote, apply, assert "gh repo create" does NOT appear. |
| `test_shim_cli_help_consistency.py` | Continues to pass — no `_flags.py` changes. |
| All other tests | Continue to pass. |

## Architecture decisions

- **CLAUDE.md vs CONTRIBUTING.md**: CLAUDE.md is the always-on session context;
  CONTRIBUTING.md is consulted on-demand. Rule of thumb: every line in CLAUDE.md
  must be a *rule* you can't forget OR a *pointer* to where detail lives. Workflow
  steps, prompt templates, calibration paragraphs go in CONTRIBUTING.md.
- **AGENTS.md vs CONTRIBUTING.md**: AGENTS.md is read by *review-only* agents; it
  carries reviewer-specific guidance that those agents need at hand. Reviewers CAN
  read CONTRIBUTING.md, but the rules they apply (triage + 4-questions) need to be
  in AGENTS.md for fast access. AGENTS.md ends up larger than CLAUDE.md because it
  carries reviewer-specific content.
- **Byte-identity invariant preserved**: the "## Triaging review findings" section
  stays byte-identical across the 6 surfaces (3 dogfood + 3 templates). The new
  shorter version is the new canonical bytes.
- **gh-hint is informational, not actionable**: the skill prints a hint; the user
  runs `gh repo create` themselves. The skill doesn't invoke `gh` or modify GitHub
  remote state — keeps the safety contract (manifest-based reversibility) intact.
- **Two-phase rollout vs one PR**: shipped as 5 focused commits in one PR rather
  than 5 separate PRs because the changes are tightly coupled (the CLAUDE.md tightening
  + CONTRIBUTING.md absorption are interdependent; splitting would create an
  intermediate state where CLAUDE.md references content not yet in CONTRIBUTING.md).
- **PR #17 merge handling**: this PR lands independently of PR #17. After PR #17
  merges, a small follow-up PR mirrors the gh-hint into adopt-mode's
  `_main_apply_adopt` success path. Flagged in BACKLOG.md.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Byte-identity test fails due to trailing whitespace / newline drift across the 6 surfaces | Use Python script with `text.replace(OLD, NEW)` to ensure exact byte match; run test after each surface edit. |
| Four-questions test fails because a question substring got accidentally shortened | Preserve the question text verbatim in the new short block (closes the test's exact-substring assertion). |
| Wording drift in CLAUDE.md cut sections introduces an unintended meaning change | Move-not-rewrite discipline: text that stays in CLAUDE.md stays as-is; text moved to CONTRIBUTING.md is moved verbatim (no re-wording). |
| CONTRIBUTING.md cross-refs from CLAUDE.md become broken if CONTRIBUTING.md is renamed / restructured | Document in CONTRIBUTING.md's own header that cross-refs from CLAUDE.md exist; flag if a future restructure proposal removes or renames sections. |
| gh-hint subprocess call fails / hangs on weird targets (NFS, slow filesystems) | Use `subprocess.run(check=False, timeout=5)` + treat any exception as "no remote detected, print hint"; never fail the apply because of gh-hint detection. |
| Test `test_gh_repo_hint_when_no_remote` flaky if `gh` CLI not installed | Use `git -C <out> remote` for detection (not `gh remote`); `git` is already a hard prereq. The hint text contains `gh repo create` but the detection doesn't depend on `gh`. |
| PR #17's cli.py changes conflict with the gh-hint addition on merge | gh-hint is added in the v1 success block (line ~598-610 of main.cli on main); PR #17 added the adopt-mode dispatch BEFORE this block but didn't modify the block itself. No conflict expected; flagged as follow-up after PR #17 merges. |
| The "absorb into CONTRIBUTING.md" piece grows CONTRIBUTING.md from 190 → ~280 lines | Accepted. CONTRIBUTING.md is consulted on-demand; size matters less than for CLAUDE.md. |

## Verification (acceptance criteria)

### Phase 1 — pre-implementation evidence (this plan PR)

- [ ] Plan converges (no imp-3 findings remain in iter-N's Codex + Claude reviews).
- [ ] Mandatory human-approval gate completed.

### Phase 2 — post-implementation gates

(Ordered; gate 1 must pass before gate 2, etc.)

1. **Draft Implementation PR opened** on branch `impl/tighten-info-architecture`
   (branched from main; not from PR #17's branch).
2. **All 5 focused commits land** in order: triage shrink + CONTRIBUTING absorb,
   CLAUDE.md tightening, shared/CLAUDE.md.tmpl tightening, AGENTS.md +
   shared/AGENTS.md.tmpl tightening, gh-hint code.
3. **Per-commit Tier-1 review** (`make review-commit-by-claude`) clean (no imp-3
   findings) before push.
4. **`make check` passes** (full pytest + ruff suite).
5. **`tests/test_triage_byte_identity.py` passes** — confirms triage byte-identity
   across 6 surfaces.
6. **`tests/test_dogfood_doc_sanity.py` passes** — confirms triage heading + bullets
   still present.
7. **`tests/test_bootstrap_cli.py::test_gh_repo_hint_when_no_remote` passes** + the
   no-fire counterpart passes.
8. **Final line counts measured**:
   - `CLAUDE.md` (skill): 120-130 (acceptable: 115-140)
   - `AGENTS.md` (skill): ~135 (down from 141)
   - `shared/CLAUDE.md.tmpl`: 160-180 (renders to ~120-130)
   - `shared/AGENTS.md.tmpl`: ~115 (down from 119)
   - `CONTRIBUTING.md`: ~270-290 (up from 190; absorbed content)
   - `shared/CONTRIBUTING.md.tmpl`: ~330-350 (up from 252)
9. **PR ready-for-review** triggers `claude[bot]` Tier-2 auto-review.
10. **Tier-2 findings triaged** per (a/b/c/d).
11. **Merge** when CI green + no imp-3 Tier-2 findings remain.

## Iteration log (this plan)

| Iter | Findings | Verdict |
|---|---|---|
| 1 (codex) | (TBD — will run after this draft) | (TBD) |
| 1 (claude) | (TBD) | (TBD) |
| ... | ... | ... |

## Evidence table — what was folded and where

| Source | Finding | Fold location | Triage |
|---|---|---|---|

## Lessons surfaced

(none yet)

## What we are NOT doing in this PR

- Adopt-mode (PR #17) gh-hint — follow-up PR after PR #17 merges.
- CONTRIBUTING.md restructure beyond absorbing moved content.
- Restructure of docs/plans/README.md beyond the triage section.
- Wording rewrites of preserved CLAUDE.md / AGENTS.md sections (move-not-rewrite).
- Updates to BACKLOG.md (handled in impl PR).
- Cross-language adoption-mode (Node, Go) — parked separately.

## Critical files to read before each iter's review

- `CLAUDE.md` (skill repo's own) — current 182 lines
- `AGENTS.md` (skill repo's own) — current 141 lines
- `CONTRIBUTING.md` (skill repo's own) — current 190 lines
- `shared/CLAUDE.md.tmpl` — current 228 lines (renders 120-130 for typical context)
- `shared/AGENTS.md.tmpl` — current 119 lines
- `shared/CONTRIBUTING.md.tmpl` — current 252 lines
- `docs/plans/README.md` + `shared/docs-plans-README.md.tmpl` — current 157 lines each
- `tests/test_triage_byte_identity.py` — the byte-identity test (6 surfaces)
- `tests/test_dogfood_doc_sanity.py` — the triage-presence test
- `bootstrap_lib/cli.py` lines 591-612 — the v1 post-apply success block where gh-hint
  goes
- `tests/test_bootstrap_cli.py` — pattern for the new gh-hint tests
- PR #17 (open) — the adoption-mode work in flight; this PR is independent but its
  gh-hint will need a mirror-edit in `_main_apply_adopt` after PR #17 merges
