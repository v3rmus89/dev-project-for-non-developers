# Trial report — PR #7 `--mode=adopt` against `downstream-app/`

> One-time structured trial-experience write-up per plan Scope #11. NOT a typo
> for `LESSONS.md` (the two artifacts are intentionally distinct: this is the
> single-shot trial deliverable; LESSONS.md is the ongoing append-only log).
>
> **Privacy boundary**: per Scope #11, this report contains NO secrets, NO
> transcript / customer / PII content, NO raw file excerpts. Safe content:
> filenames, file sizes, sha256 hashes, structural categories, policy
> decisions + reasoning. The trial target (`~/code/downstream-app/`)
> contains `secrets/`, `data/`, customer-domain code; none of that surfaces here.

## (a) Trial target shape

**Target**: `~/code/downstream-app/` — a real Python project on
branch `customer-cases-redial-linking-v1` at SHA `2ae59e27e761e8e635ed4cd9edcf6e199afba44a`.
Uses `uv` (auto-detected via `uv.lock`).

**Planned files**: 19 (the standard Python skill render with `--project-name=downstream-app`).

**Collision baseline** (verified empirically; closes Codex iter-3 #5
correction of the pre-empirical "8 collisions" guess):

| Path | Status | Size | Pre-apply sha256 |
|---|---|---|---|
| `.gitignore` | MODIFY (rule d) | 924 bytes | `3b395f679b...` |
| `.python-version` | MODIFY (rule c) | 5 bytes | `7b55f8e67b...` |
| `CLAUDE.md` | MODIFY (rule f) | 6518 bytes, 96 lines, 6 headings | `dd8c81911b...` |
| `pyproject.toml` | MODIFY (rule g) | 1619 bytes, 64 lines, has `[dependency-groups]` | `4b66423f31...` |

**Empirically-verified count**: 4 MODIFY + 15 CREATE = 19 planned files.

The pre-empirical "8 collisions" number (PR #6 BACKLOG) had erroneously
counted `README.md` + `uv.lock` (which exist in target but aren't bootstrap
writes) and `src/` + `tests/` (which are directories, not file collisions).
Corrected in BACKLOG.md during this PR.

**Gitignore preflight** (per Codex iter-6 #4 fold): `git check-ignore -v --`
against all 15 planned CREATE paths surfaced **AGENTS.md** as the only
ignored planned create (matched `.gitignore:48:AGENTS.md`). Rule (a0) fires
→ recommended SKIP with `manual_review_needed=True`.

**Pre-existing target dirs**: `src/`, `tests/`, `scripts/` all pre-existed
(no `created_directories` entry needed); `docs/` existed but `docs/plans/`
didn't; `.github/` + `.github/workflows/` didn't exist.

## (b) Phase A empirical findings + rehearsal-decision-script

**Per-file analyzer output** (from the live `--dry-run` + `--mode=adopt`
analyze phase):

| Path | Rule | Policy | mr | Confidence |
|---|---|---|---|---|
| `.editorconfig` | (a) | WRITE | False | high |
| `.github/pull_request_template.md` | (a) | WRITE | False | high |
| `.github/workflows/ci.yml` | (a) | WRITE | False | high |
| `.gitignore` | (d) | APPEND_MERGE | False | high |
| `.pre-commit-config.yaml` | (a) | WRITE | False | high |
| `.python-version` | (c) | SKIP | False | high |
| `AGENTS.md` | (a0) | SKIP | **True** | high |
| `BACKLOG.md` | (a) | WRITE | False | high |
| `CLAUDE.md` | (f) | WRITE_NEW | **True** | medium |
| `CONTRIBUTING.md` | (a) | WRITE | False | high |
| `LESSONS.md` | (a) | WRITE | False | high |
| `Makefile` | (a) | WRITE | False | high |
| `docs/plans/README.md` | (a) | WRITE | False | high |
| `pyproject.toml` | (g) | SKIP | **True** | medium |
| `pytest.ini` | (a) | WRITE | False | high |
| `ruff.toml` | (a) | WRITE | False | high |
| `scripts/run-with-clean-env.py` | (a) | WRITE | False | high |
| `src/main.py` | (a) | WRITE | False | high |
| `tests/test_smoke.py` | (a) | WRITE | False | high |

**Summary distribution**: WRITE=14, APPEND_MERGE=1, WRITE_NEW=1, SKIP=3 (one
via rule (c) byte-identical, one via rule (a0), one via rule (g)).

**Owner pre-decided rehearsal-decision-script** (chosen at the AskUserQuestion
gate; piped via heredoc `printf 's\n\n\n'` for both rehearsal + live apply):

| File (mr=True) | Decision | Resulting policy |
|---|---|---|
| `AGENTS.md` | `s` ([s]kip) | SKIP (no manifest entry; gitignored file stays absent) |
| `CLAUDE.md` | `\n` ([Enter] = [r]ecommended) | WRITE_NEW (`.new` written; original untouched) |
| `pyproject.toml` | `\n` ([Enter] = [r]ecommended) | SKIP (original byte-identical; no manifest entry) |

**Rationale for the conservative path** (recorded for trial-report Section (b)
per plan Scope #11): the trial's safety goal is "validate the engine
end-to-end without committing to any destructive write". `[s]kip` for the
gitignored AGENTS.md path avoids the silent-write-to-invisible-file failure
mode that rule (a0) is designed to prevent. `[r]ecommended` for CLAUDE.md +
pyproject.toml accepts the safest default in both cases (WRITE_NEW preserves
the original; SKIP leaves pyproject.toml untouched).

## (c) Phase B validation — Scope #5 rule-by-rule fire-correctness

Heuristics are **LOCKED at iter-2** per the plan; this section is observational
only. Each row asserts whether the live analyzer's classification matches
what the plan predicts.

| Rule | Plan-predicted trigger | Observed | Misfire? |
|---|---|---|---|
| (a0) | missing AND ignored_by_git | AGENTS.md → SKIP/mr=True | no — fired correctly; `.gitignore:48` source reference captured (pattern correctly redacted per privacy fold) |
| (a) | missing AND not ignored | 14 missing files → WRITE/mr=False | no — every non-ignored missing CREATE classified WRITE |
| (b) | empty / whitespace-only existing | (no triggering file in target) | n/a — fixture (i) of the smoke suite exercises rule (b); not exercised in this real-target trial |
| (c) | byte-identical to skill | `.python-version` (5 bytes = `3.12\n` matches skill) → SKIP/mr=False | no — fired correctly; rule (c) takes precedence over rule (e) for byte-identical content (per `test_c_fires_before_e_for_byte_identical_python_version`) |
| (d) | `.gitignore` AND skill patterns missing | `.gitignore` (924b) → APPEND_MERGE (17 lines added) | no — fired correctly; merged file is 1077b post-apply |
| (e) | `.python-version` AND any pin | (overshadowed by rule (c) in this target) | n/a — rule (c) fired first since target's bytes are byte-identical to skill's |
| (f) | domain markdown + non-trivial | CLAUDE.md (96 lines, 6 headings) → WRITE_NEW/mr=True | no — fired correctly; `.new` written, original untouched |
| (g) | `pyproject.toml` + non-trivial | pyproject.toml (`[dependency-groups]` detected) → SKIP/mr=True | no — fired correctly; user reviews diff manually |
| (h) | DEFAULT for unrecognized existing | (no triggering file in target) | n/a — downstream-app has no "miscellaneous unknown existing files" in the collision set |

**Misfire count**: 0. All firing rules behaved exactly as the plan predicts.
No rule needed loop-back to Phase C.

**Misfire-split rule** (per Sequencing Phase B + Risks-row, canonical at
plan Bucket E Phase A): had any `manual_review_needed=false` misfire
occurred, it would have triggered in-PR loop-back to Phase C and the
remediation would be recorded inline here with the file-name + rule-change
pair. None did. Had any `manual_review_needed=true` misfire occurred, it
would be logged as a UX gap in Section (e) below. None did.

## (d) Phase D apply result

**Rehearsal-on-minimal-copy** (Phase D-2):

- `REHEARSAL_DIR=$(mktemp -d -t pr7-rehearsal-XXXXXX)` → 4 collision files
  copied via `cp -a`; `mkdir -p` for src/tests/docs/plans/.github/workflows;
  `git init` + `git add .gitignore` + commit; `.git/info/exclude` mirrored
  from live target (closes Codex Tier-2 PR #16 #27).
- Apply with heredoc decisions: 16 mutating entries written; 3 prompts
  fired in expected order (AGENTS.md → CLAUDE.md → pyproject.toml);
  rehearsal manifest at `dev-project-setup-restore-20260520T093822Z-3y27ynm_.json`.
- **Post-apply byte-identical assertion**: CLAUDE.md (dd8c8191), pyproject.toml
  (4b66423f), .python-version (7b55f8e6) all unchanged from pre-rehearsal SHAs.
- **Restore round-trip**: `--restore` → counters `(1 restored, 15 removed, 0 skipped, 0 rejected)`.
  Post-restore SHA check: all 4 pre-existing files **byte-identical to pre-rehearsal**;
  all 15 mutating files removed; AGENTS.md correctly still absent (was SKIP'd,
  never created); no `.new` file remaining.

**Rehearsal verdict**: the engine + restore matrix work end-to-end on real
downstream-app content. Safety contract holds.

**Live apply** (Phase D-3):

- Preflight: ORIGINAL_BRANCH=`customer-cases-redial-linking-v1`,
  ORIGINAL_SHA=`2ae59e27e761e8e635ed4cd9edcf6e199afba44a`. Dirty state
  (`.claude/settings.json` modified + `.claude/scheduled_tasks.lock` +
  `tools/` untracked) stashed via `git stash push --include-untracked`;
  STASH_SHA=`93bf8f1678e29bad2b6e1903ce1df1c6f3eba6ef` captured for by-ref
  pop on rollback (closes Codex Tier-2 PR #16 #28 + #30).
- Trial branch created: `feat/pr7-trial-adoption` from ORIGINAL_SHA.
- Apply with heredoc decisions: 16 mutating entries written; manifest at
  `dev-project-setup-restore-20260520T095206Z-g5pyttu7.json`. Manifest's
  `target_root` is absolute (verified F1 fix from Tier-1 on `_main_apply_adopt`).
- **Post-apply byte-identical assertion on live**: CLAUDE.md, pyproject.toml,
  .python-version all byte-identical to pre-live SHAs (matched the rehearsal SHAs;
  same target content).

**Mutation surface** (per Codex Tier-2 PR #16 #12 + #16 — both `git diff --stat`
AND `git status --short --ignored=matching` captured because diff-stat undercounts
untracked `.new` files):

`git diff --stat`:
```
 .gitignore | 17 +++++++++++++++++
 1 file changed, 17 insertions(+)
```

`git status --short --ignored=matching` (trial-relevant lines only):
```
 M .gitignore
?? .editorconfig
?? .github/                        (contains pull_request_template.md + workflows/ci.yml)
?? .pre-commit-config.yaml
?? BACKLOG.md
?? CLAUDE.md.new
?? CONTRIBUTING.md
?? LESSONS.md
?? Makefile
?? docs/plans/                     (contains README.md)
?? pytest.ini
?? ruff.toml
?? scripts/run-with-clean-env.py
?? src/main.py
?? tests/test_smoke.py
```

(Pre-existing ignored entries like `!! .DS_Store`, `!! .venv/`, `!! data/`,
`!! secrets/` are unrelated to the trial; they're target's existing state.)

**Manifest summary**:
- `format_version`: 2
- `target_root`: `/Users/sandeep/Desktop/Code/Acme/downstream-app` (absolute)
- `created_directories`: `['.github', '.github/workflows', 'docs/plans']`
- 16 entries by policy: WRITE=14, APPEND_MERGE=1, WRITE_NEW=1

**Was downstream-app/ better off after?** Subjectively yes — the adopt-mode
landed a clean set of dev-workflow scaffolding (Makefile, CI workflow,
pre-commit + pre-push hooks via pre-commit framework, plan-loop docs)
without touching CLAUDE.md / pyproject.toml / .python-version. The user
can now review CLAUDE.md.new manually and decide what (if anything) to
merge. The `.gitignore` got 17 lines of skill patterns appended that were
missing (visible via `git diff .gitignore`).

**Anything broken?** No. The pre-existing project's domain code, secrets/,
data/, .venv/, .env, etc. are all untouched (they weren't planned files).
The 3 SKIP-classified collision files are byte-identical to pre-apply.
The .gitignore mutation is additive (line-level idempotent append-merge);
re-running the same apply produces the same result.

**Restore round-trip on live**: not executed in this trial run (the user
chose to keep the trial state for manual review of CLAUDE.md.new). If
executed, would produce the same `(1 restored, 15 removed, 0 skipped, 0 rejected)`
shape as rehearsal, returning target byte-identical to pre-apply.

## (e) Skill UX gaps surfaced

**1. `--diff` does not show policy annotations** (imp-2; doc-side caveat
landed; BACKLOG entry filed during Bucket F).
Plan Scope #8 + Bucket A row 8 specified that plain `--diff --language python`
should annotate each unified-diff header with the recommended policy. PR #7
shipped the full `--apply --mode=adopt` path but not the `--diff` annotator;
users wanting a read-only preview see only the standard `difflib.unified_diff`
output, NOT the policy recommendation. Workaround: run `--apply --mode=adopt`
and read the report (Step 2 of usage.md's worked example).

**2. Privacy fold caught a real-world leak vector** (imp-3; folded inline
during PR #7 impl).
The rule (a0) recommendation reason captures the matching gitignore line for
the user to look up the rule manually. The pre-fold version returned
`<source>:<line>:<pattern>` (e.g. `.gitignore:48:AGENTS.md`); after the fold
it's `<source>:<line>` only (e.g. `.gitignore:48`). On downstream-app/, the
matching pattern is `AGENTS.md` (not sensitive). But the principle catches the
class of leaks: had the user's gitignore pattern been
`secrets/customer-acme-corp/*`, the pre-fold reason would have leaked it.
Validated end-to-end on real downstream-app content.

**3. v2 manifest needed absolute `target_root` for cross-cwd restore** (imp-3;
folded inline during `_main_apply_adopt` Tier-1 review).
A v2 manifest written from cwd A with `--out ./target` recorded the relative
path; `bootstrap.py --restore` from cwd B would silently exit 0 with zero
mutations. Fixed: `str(Path(target_root).resolve())` mirrors v1's `_prepare_apply`
exactly. The live trial's manifest correctly records the absolute target_root
(`/Users/sandeep/Desktop/Code/Acme/downstream-app`) — pinned by direct read
during Phase D verification.

**4. Tier-1 vs plan-loop catch ratio**: PR #7's 13 impl commits had 11 Tier-1
reviews; 2 caught real imp-3 holes that the 7-iter Codex plan loop missed at
integration boundaries (#2 + #3 above). The plan loop converged on safe-by-
design contracts; the integration-boundary holes only existed in code, not
in the plan, so Tier-1 was the only gate that could catch them.

## (f) Recommendations for future skill polish

(Pre-existing PR #7 follow-up entries in BACKLOG.md already capture most of
these; this list cross-references the parked items.)

1. **`--diff` policy annotator** (imp-2) — BACKLOG entry "Annotate `--diff`
   headers with adopt-mode policy recommendations" filed during Bucket F.
   Trigger: a user requests inline annotations during read-only preview.

2. **Rule (a0) UX**: AGENTS.md is gitignored in this target, prompting the
   user. After the trial it's clear that "gitignored planned-create" almost
   always wants SKIP (the file's invisible to git, so writing it confuses
   later git workflows). The interactive prompt could surface a one-line
   gitignore-pattern hint (e.g. "AGENTS.md is ignored by .gitignore:48 —
   you almost certainly want [s]kip"). Minor UX; park for follow-up if
   real-world users tell us they wanted SKIP-only-default for rule (a0).

3. **No "next steps" guidance in adopt-mode success path** (rejected during
   Tier-1 of `_main_apply_adopt` as cosmetic). The plain-apply success block
   prints `cd <out> && make install`; adopt-mode does not. For trial-style
   adoption, the user probably has an existing workflow; the silence is
   intentional. Park.

4. **Adoption-mode for Node + Go** — parked per Scope NOT-in-scope. Same
   Scope #5 rules need language-specific tweaks (e.g. `[tool.uv]` → `package.json`
   "dependencies" for nodejs; `go.mod` for go). Trigger: first user request
   for non-Python adopt-mode.

5. **Trial-report-vs-LESSONS.md** distinction held cleanly: this report is
   a one-shot trial deliverable; new mistake-classes surfaced during PR #7
   work were appended to LESSONS.md in the relevant impl session (none in
   this trial — the engine behaved as designed).

## Trial-loop closing notes

- **Heuristics**: locked at iter-2 per plan Architecture decision; held
  throughout the trial. No in-PR loop-back to Phase C needed.
- **Plan↔impl drift**: 1 known item (`--diff` annotator); caught + filed
  during Bucket F docs review. Engine itself matches the plan exactly.
- **Safety contracts upheld**:
  - Pre-existing files (CLAUDE.md, pyproject.toml, .python-version) byte-identical
  - Rule (h) safety floor never triggered destructively (no rule (h) fires in this
    target; the floor is the SKIP default for unrecognized existing files)
  - Rule (a0) ignored-create correctly went through manual_review (AGENTS.md)
  - Restore round-trip byte-identical on rehearsal
  - APPEND_MERGE additive + idempotent (re-running produces same .gitignore)
  - WRITE_NEW never touched the original (CLAUDE.md byte-identical)

**Trial verdict**: Bucket E ✅ complete. Engine + safety contracts ship-ready.

---

*PR #7 (this PR) ships the engine + smoke tests + docs + this trial report.
Live apply on downstream-app/ left on `feat/pr7-trial-adoption` branch for
the user's manual review of CLAUDE.md.new. Rollback recipe (Phase D-4)
documented inline in plan Bucket E if needed; the rehearsal proved the
contract works.*
