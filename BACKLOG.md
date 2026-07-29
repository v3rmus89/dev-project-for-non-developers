# Backlog — parked decisions and future work

Items here are explicit "we will do this someday" decisions, recorded so they
don't get lost between sessions. Each item lists **why it's parked**, **what
triggers picking it up**, and **rough effort**.

Newer items at the top.

Closed and superseded items live in [BACKLOG-archive.md](BACKLOG-archive.md).

---

## Standing policy

### New review-loop features need an A/B-measured win first

**Rule**: before adding a feature to the plan-review / commit-review loop — a new
target, a new pass, a new prompt section, another reviewer round — measure that it
beats the status quo on a real plan. No measured win, no addition.

**Why**: the loop is the repo's heaviest process surface, and its cost is paid on
every substantive PR by every future session. Features accrete easily (each one is
locally plausible) and are near-impossible to remove later, because nothing records
whether they ever fired. Two data points motivate the rule: the `continue`-thread
A/B, which disconfirmed an intuitively obvious saving (`continue` consumed **1.69x
more uncached input** than fresh — the price-independent figure the verdict rests
on; the est-cost ratio of ~1.81 in the same note is explicitly placeholder-priced —
see [docs/design-notes/2026-06-01-continue-thread-ab-result.md](docs/design-notes/2026-06-01-continue-thread-ab-result.md)),
and the optional `/simplify` pass, which shipped as a documented step and shows no
evidence of ever having fired in a shipped PR record (retired into the Tier-1 focus
list by the pre-expansion refactors plan, AD7).

**How to satisfy it**: `scripts/ab-replay.py` is the existing harness — it replays
one real checked-in plan through both arms and reports the cost ratio. A qualitative
win ("the review reads better") counts only if it is stated as a claim someone else
could check against the two outputs.

**Scope**: this governs additions to the loop. Fixes to an existing target
(correctness, safety, a broken guard) are not features and need no A/B.

---

## Follow-ups from the pre-expansion structural refactors (Buckets A–E)

Parked during the Buckets A–E work
([docs/plans/2026-07-05-pre-expansion-structural-refactors.md](docs/plans/2026-07-05-pre-expansion-structural-refactors.md)).

### Resolve intra-page anchors in the markdown link gate (`markdown-anchor-resolution`)

**Status**: parked (Bucket D Tier-1, imp-1). `tests/test_markdown_link_integrity.py`
proves that every in-repo link TARGET exists, but exempts the `#anchor` part: a
link to a real file at a heading that no longer exists passes. `docs/usage.md`'s
runbook already carries one such link (`#worked-example-downstream-app-shape`),
correct today, unprotected tomorrow.

**Why parked**: the fix needs GitHub's heading-slug algorithm — lowercasing,
punctuation stripping, and the `-1`/`-2` suffixes GitHub appends to duplicate
headings. Getting it subtly wrong produces FALSE failures on correct links,
which is worse than the gap: a gate that cries wolf gets weakened or deleted.
The link gate's value comes from being trusted, so this only lands with the slug
rules pinned by their own tests.

**Trigger to pick up**: the first time a broken anchor is actually found (in
review, or by a reader), OR when any shipped doc gains a generated table of
contents — at that point anchors become load-bearing rather than incidental.

**Rough effort**: ~half a day (slug function + duplicate-suffix handling + tests
+ one pass fixing whatever it turns up).

---

### `--mode=upgrade`: re-adopt engine keyed to an OWNERSHIP model (`adopt-upgrade-ownership-engine`)

**Status**: parked — the scaling answer for keeping adopted projects up to date.
Today's story is the manual runbook in `docs/usage.md` ("Bringing an adopted project
up to date"): run each sync script by hand, per project, dry-run first. That is the
right answer at 2–3 adopted projects and the wrong one at 10.

**Why not whole-file tracking**: the obvious design — hash each shipped file,
auto-update the ones the owner hasn't touched — cannot work for the files that
matter most. A downstream `CLAUDE.md` holds the project's own details *next to* the
shared rules, so it can never hash-match as a whole file: per-file tracking would
never auto-update it, and whole-file replacement would destroy the owner's half.
Ownership is per-REGION, not per-file, so the engine has to be too.

**Design sketch** — three ownership classes:

1. **Skill-owned whole files** (scripts, prompts, the CI workflow) — file-hash
   tracking; auto-update while the file still matches what the skill last wrote.
2. **Managed REGIONS inside mixed-ownership files** (the shared `##` sections; the
   Makefile sentinel block) — region-hash tracking; auto-update only while the
   region still matches what the skill last wrote, per-region consent when the owner
   has edited inside it. This closes today's `scripts/propagate-shared-rules.py`
   gap, where in-section owner edits are overwritten with only the dry-run diff as
   a guard. Regions are heading-matched at first, upgradeable to sentinel comments
   that the first run inserts.
3. **Owner files** — never auto-touched.

**Grounding fact**: the engine needs a durability design of its own. Today's
manifests are `tempfile.mkstemp` temp files (`bootstrap_lib/manifest.py`,
`manifest_path()`) — rollback artifacts scoped to one `--apply`, not a durable
record of what the skill wrote. A lockfile written into the target is a feature, and
a real design decision, not an implementation detail.

**Trigger to pick up**: the **3rd** real adopted project, OR the **2nd** time one
skill change requires touching every adopted project by hand — whichever comes
first.

**Rough effort**: ~1 week (ownership record format + region matcher + consent UX +
per-class tests), plus the design decision on where the durable record lives.

---

## Follow-ups from the #46 / #50 Tier-2 review

### `loop-status` malformed-latest: a keyless foreign file at a higher iter still masks a valid latest (`loop-status-malformed-latest-keyless-foreign`)

**Status**: parked (Codex P2 on downstream-app PR #50). PR #46 closed the *parseable*
foreign-key direction (`_latest_files_for_stem` now key-filters footers that parse),
but a foreign review file that is **malformed/keyless** — same plan stem (basename),
higher iteration, in a shared `/tmp` — is still kept as a candidate (no key to filter
on), becomes `top_iter`, and makes `main()` report `malformed-latest`/exit 1 even when
THIS plan's latest *keyed* review is valid. A false positive (the mirror of the false
negative PR #45 fixed); pre-existing in the malformed-latest feature, only narrowed by #46.

**Why parked**: there is no small fix — a malformed file can't be attributed to a plan by
content (it doesn't parse), and the filename stem is the only link, which is exactly the
collision point. The robust fix is to put the review `KEY` in the output **filename/glob**
(`plan-review-<stem>-<key>-by-<actor>-iter-<N>.md`) so even unparseable files are
attributable by name — that touches the review-file naming contract across the Makefile
review targets + `loop-status` glob + `_load_iters` + tests + downstream. Likelihood is the
same low class as the original (dated plan slugs make cross-repo same-basename collisions
near-impossible) and the impact is advisory only (a spurious `malformed-latest` notice).

**Trigger to pick up**: two repos sharing `/tmp` actually collide on a plan basename and a
driver sees a spurious `malformed-latest`, OR the review-file naming convention is changed
for another reason.

**Rough effort**: ~half a day (naming-convention change + glob/parse updates + tests + re-sync).

---

### Forward-pin the drifted machinery test files to downstream-app (`downstream-app-machinery-test-parity`)

**Status**: parked (claude[bot] Tier-2 imp-2 on PR #50). The C4 forward-pin synced the
machinery *code* (scripts + Makefile lines) but not its tests, so downstream-app' suite does not
exercise the new `malformed-latest` / key-filter / `_FenceTracker` paths. Still pre-PR-#45 in
downstream-app: `tests/test_loop_status.py` and `tests/test_review_plan_fact_check.py`.

**Why not a trivial byte-identical sync (the real blocker)**: the skill and downstream-app have
divergent ruff policies — the skill sets `ignore = ["E501"]` ("let ruff format handle line
length"), so its shared test files carry long fixture lines (e.g. 122-col `json.dumps` footer
literals in `test_loop_status.py`), while downstream-app **enforces** E501 at line-length 100. A
byte-identical `cp` therefore fails downstream-app' `make check` lint — tried in PR #50, reverted
in `a9fa16b`. Closing this cleanly needs one of: (a) wrap the skill's shared test fixtures to
≤100 cols so they sync byte-identical to the stricter downstream, or (b) reconcile the ruff
configs (e.g. downstream-app ignores E501 under `tests/**`). Separately, `tests/test_review_loop_artifacts.py`
is **repo-adapted, NOT byte-identical** anyway — the skill's version drives a fixture through
the skill's `bootstrap.py` (absent in downstream-app) — so not every machinery test file can be
byte-identical.

Also: the skill itself has **no direct `_FenceTracker` unit test** (only indirect coverage via
`extract_active_text` / `parse_fact_roots`). Adding one only downstream would create drift — add
it in the skill first if at all (claude[bot] called it polish).

**Trigger to pick up**: the next downstream-app machinery sync, or a fence / malformed-latest
regression slips through downstream.

**Rough effort**: ~half a day (option (a): wrap skill test fixtures ≤100 cols + verify both
repos green + sync; or option (b): ruff-config reconciliation + sync).

---

## Follow-ups from PR-0 hardening (fact-check post-merge review)

PR #30 shipped the `review-plan-fact-check-by-{codex,claude}` targets +
`scripts/extract-plan-facts.py` + `scripts/verify-plan-facts.py`. A post-merge
review surfaced four gaps; containment (gap 2) and the under-scan regression
tests (gap 3) were fixed in the PR-0-hardening PR. The two below are deferred.

### Deterministic CLI-flag semantic verification (`fact-check-cli-flag-verification`)

**Status**: parked — `verify-plan-facts.py` classifies every `cli_flag_ref` as
`not_verifiable` (documented in its docstring). Catching a semantic flag
conflict (e.g. `--apply` + `--dry-run`, mutually exclusive in
`bootstrap_lib/_flags.py`) needs either (a) importing the CLI-under-test's
parser — impossible, because the script ships to downstream projects verbatim
from its single working copy `scripts/verify-plan-facts.py` (`SHARED_VERBATIM_MAP`
in `bootstrap_lib/render.py`) and must stay stdlib-only (no
`bootstrap_lib` dependency), or (b) executing the CLI — which violates the
no-execute safety boundary (iter-4 FN1). Generic, safe flag-semantics
verification is a genuine design problem, not a quick addition.

**Trigger to pick up**:
- A plan loop repeatedly ships CLI-flag-conflict drift the deterministic
  extractor can't catch (the iter-3 F3 `--apply --dry-run` class recurs).

**Starting requirements / candidate design**:
- An OPT-IN, repo-local verifier hook: the generic script looks for an optional
  `scripts/verify-plan-facts-local.py` (NOT shipped in the template) that the
  host repo provides; if present, delegate `cli_flag_ref` checks to it. The
  host hook MAY import its own resolver (e.g. `bootstrap_lib.cli._resolve_mode`)
  and run `parse_args` on flag combinations in a no-`main()`, side-effect-free
  harness. Absent the hook, `cli_flag_ref` stays `not_verifiable`.
- Requires capturing flag COMBINATIONS (full command incantations) in
  `extract-plan-facts.py`, not just individual `--flag` tokens.
- Tests: repo-local hook fixture proving `--apply --dry-run` fails + a valid
  combo passes; downstream-shaped fixture proving the generic script stays
  `not_verifiable` (no hook) without error.

**Rough effort**: ~1–1.5 days.

---

### Live-AI fallback for the fact-check review targets (`fact-check-ai-fallback`)

**Status**: parked — the `review-plan-fact-check-by-{codex,claude}` Makefile
targets only check `command -v` for the CLI. If `codex`/`claude` is installed
but unauthenticated / rate-limited / network-blocked, the target fails even
though the deterministic `extract`+`verify` JSON (the load-bearing part) is
still useful.

**Trigger to pick up**:
- The fact-check pre-pass runs where the live CLI is flaky (CI, offline) and
  the deterministic output alone would suffice.

**Starting requirements**:
- Add a deterministic-only path: run `extract-plan-facts.py | verify-plan-facts.py`
  and emit the JSON even when the live-AI judgment layer is unavailable; the
  target degrades to "deterministic findings only" with a clear notice rather
  than a hard failure.

**Rough effort**: ~1–2 hours.

---

## Follow-ups from skill-pr10 (harvest plan-tango B/C/D/E)

### Skill wrapper in plan mode (`skill-wrapper-pr-followup`)

**Status**: parked — Bucket A was scoped out of PR #10 after 6 cross-review iterations failed to plateau (imp-3 trajectory: 3→4→4→3→4→3). Three architectural blockers remain unresolved (iter-7 F2 fold — deferral needs a durable record so the blockers don't get lost).

**Trigger to pick up**:
- The adopt-mode `.gitignore` parent-ignore neutralization problem gets a clean solution (`APPEND_MERGE` cannot neutralize a parent `.claude/` ignore — iter-6 F2).
- A working `pre_skip_check` design that doesn't violate the manifest/atomic-write/restore contract is available (iter-6 F3).
- The 3-branch acceptance verification (Claude/Codex/Other × plan-review/commit-review = 6 branches) is designed and tested (iter-5 F6, iter-5 F7).

**Starting requirements (iter-1..6 F-series findings)**:
- iter-1 F3 / iter-2 F1 / iter-3 F1 / iter-4 F1 / iter-5 F1: `.gitignore` parent-safe unignore block for `.claude/` — 5 iterations of refinement; final two-pass `adopt.py` approach still has the neutralization hole (iter-6 F2).
- iter-6 F2: `APPEND_MERGE` cannot NEUTRALIZE a parent `.claude/` ignore — needs a `.gitignore`-rewrite mechanism not yet designed.
- iter-6 F3: proposed `pre_skip_check` violates atomic-write/restore contract — design needs rethinking.
- iter-2 F5 / iter-4 F5: Skill wrap-list grows incrementally; Skill encodes cross-direction reviewer rule.
- iter-2 F6 / iter-2 F7: V-21 Skill template ↔ dogfood byte-identity test + `AskUserQuestion` in `allowed-tools`.
- iter-5 F6 / iter-5 F7: V-1 tests all 3 approval branches (Claude/Codex/Other); commit-review same-AI branching added to Skill.
- iter-3 F5: AGENTS.md has no approval-gate paragraph — NOT a target for keyword swap (scope confirmed removed).

**Rough effort**: ~1 week. The Evidence table in `docs/plans/archive/2026-05-27-skill-pr10-harvest-plan-tango-improvements.md` carries the full iter-1..6 triage record.

---

### Continue-thread mode for Codex (`continue-thread-pr-followup`)

**Status**: MEASURED 2026-06-01 — **STAY-FRESH** (flip disconfirmed; `continue` ran **1.69x costlier** — see `docs/design-notes/2026-06-01-continue-thread-ab-result.md`). `THREAD_MODE` stays `fresh`; no full-rigor escalation. Re-open only if resume gains history-compaction; history below retained.

**V-13 COMPLETE (2026-05-29, commit da776ee)** — ⚠️ **schema CORRECTED by the first live gate (2026-05-30)**: fixture captured at
`tests/fixtures/codex-json-session.jsonl`; 7 validation tests pass. Key findings:
- **Session ID field**: the resumable id is `thread.started.thread_id` in the `codex exec --json`
  **STDOUT stream** (8-4-4-4-12 UUIDv7). The `session_meta.payload.id` that V-13 pinned is the codex
  **rollout-FILE** schema (`~/.codex/sessions/<Y>/<M>/<D>/rollout-<ts>-<thread_id>.jsonl`), where
  `session_meta.payload.id == thread_id`. V-13 captured the file, not the stream; the extractor reads
  `thread.started.thread_id` (a real stream sample lives at `tests/fixtures/codex-json-stream.jsonl`).
- **Cache token field confirmed**: `event_msg.payload.info.total_token_usage.cached_input_tokens`
  (field name matches plan assumption).
- **Guard required**: `info` can be `null` on the first `token_count` event (before
  the model's first call). Any Bucket F code reading `cached_input_tokens` must guard
  `if info is not None`. Fixture null-info variant + guard test parked below.

**PR-1 PLAN IN REVIEW (2026-05-29)**: plan at `docs/plans/archive/2026-05-29-skill-pr1-bucket-f-continue-thread.md`.
Iter 1 + 2 folded (5 imp-3 total, all addressed). Key verified items:
- Stale-session fallback matcher: `"no rollout found for thread id"` (verified live 2026-05-29).
- Atomic THREAD_FILE write pattern (`.tmp` + UUID validate + `mv`).
- V-13.5 (CORRECTED 2026-05-30) is a 3-gate read-only-ENFORCED check: (a) thread-id continuity — the resume `--json` stream re-emits `thread.started` with the same `thread_id`; (b) read-only enforced — a write is BLOCKED (probe file absent) AND the resumed rollout file's `turn_context.payload.sandbox_policy.type == "read-only"`. The old cwd-inheritance gate is DROPPED (the recipe runs resume from the repo, not `/tmp`).
- A/B replay uses direct `codex exec/resume --json` (bypasses Make target).
- `THREAD_MODE`/`THREAD_FILE`/`THREAD_JSONL_FILE` added to `run-with-clean-env.py` EXACT_DROP.

**Trigger to pick up**:
- ~~A real `codex exec --json` JSONL output is captured~~ **DONE** — V-13 complete.
- ~~V-13.5 protocol: 3-assertion gate~~ ~~UPDATED to 4-assertion gate~~ — **CORRECTED (2026-05-30) to a 3-gate read-only-ENFORCED check** (thread-id continuity + write-BLOCKED + resumed-rollout `sandbox_policy.type == "read-only"`; cwd gate dropped). Run the V-13.5 verifier (`scripts/verify-v13-5.py`) before merge.
- ~~A long plan loop (>8 iters) makes Codex token cost a real operational concern.~~ **SUPERSEDED 2026-06-01** — measured stay-fresh (see Status).

**Starting requirements (iter-1..5 F-series findings)**:
- ~~iter-1 F5: Bucket F `session_id` JSONL schema is only stub-tested~~ — **RESOLVED**. Resumable id is `thread.started.thread_id` (stream); `session_meta.payload.id` is the rollout-file equivalent (corrected 2026-05-30).
- iter-3 F2 / iter-4 F2 → **CORRECTED 2026-05-30**: `codex exec resume` does NOT inherit `-C`/`--sandbox` (it defaults to `workspace-write`). `--sandbox`/`-C` stay CLI-rejected on resume, so the recipe forces read-only via `-c sandbox_mode=read-only`; V-13.5 verifies read-only is ENFORCED.
- ~~iter-5 F4: V-13.5 file-absence-only check~~ — **CORRECTED to the 3-gate read-only-ENFORCED check** (2026-05-30; see above).

**Parked items from V-13 Tier-1 review (2026-05-29)**:
- (F1) Add null-info `token_count` fixture line + `test_token_count_info_can_be_null`
  test before any Bucket F code reads `info.total_token_usage`.
- (F2) Add `test_no_user_instructions_or_base_instructions` assertion (absent-or-short)
  before any fixture update that includes these large fields from the real stream.
- (F3/F4) Extend fixture with `turn_context` stubs (`effort`, `permission_profile`,
  `user_instructions=null`) and `session_meta.git` block before Bucket F impl.

**Rough effort**: V-13 complete (~30 min actual). Remaining: ~30 min V-13.5 + ~1 day full impl.

---

## Follow-ups from the config-shadowing fix

Parked items from [docs/plans/archive/2026-05-21-skill-config-shadowing-fix.md](docs/plans/archive/2026-05-21-skill-config-shadowing-fix.md) (Bucket E).

### TOML section-merge for adoption-into-existing-`pyproject.toml` (imp-2)

**Status**: parked — adoption mode currently SKIPs an existing non-trivial
`pyproject.toml` (rule (g)/(h)) and emits the B2 advisory telling the owner to
merge the skill's `[tool.ruff]` / `[tool.pytest.ini_options]` tables by hand.
A section-merge would offer to add those tables automatically when they are
absent, with owner confirmation.

**Why parked**: the existing SKIP + advisory is a *safe, informed* outcome;
auto-injecting config is the very class of bug the config-shadowing fix
closed, so a merge feature needs its own careful design (idempotency, restore
semantics, owner consent).

**Trigger to pick up**: adoption mode gains an owner-confirmed config-merge
capability, or repeated user requests to auto-apply the skill's tool config.

**Rough effort**: ~half a day (plan + implementation).

---

### `tox.ini` / `setup.cfg` as additional pytest-config shadow sources (imp-1)

**Status**: parked — the B1 shadow scan covers `ruff.toml` / `.ruff.toml` /
`pytest.ini`. pytest also reads config from `tox.ini` (`[tool:pytest]`) and
`setup.cfg` (`[tool:pytest]`).

**Why parked**: `pytest.ini` is the common standalone case; `tox.ini` /
`setup.cfg` pytest config is rarer in new projects and lower-priority.

**Trigger to pick up**: a real adoption target is found keeping pytest config
in `tox.ini` / `setup.cfg`.

**Rough effort**: ~1 hour (extend the scan to parse those files for a
`[tool:pytest]` section + tests).

---

### Nested (non-top-level) standalone-config scan (imp-1)

**Status**: parked — the B1 shadow scan is **top-level only** (`target_root`,
not recursive). A monorepo with sub-directory `ruff.toml`s would not be scanned.

**Why parked**: the skill targets single small projects; a recursive scan also
risks surfacing sensitive nested path names and noisy partial shadows.

**Trigger to pick up**: a monorepo-shaped adoption target with sub-directory
`ruff.toml`s.

**Rough effort**: ~half a day (needs a privacy-aware recursive-scan design).

---

### Migrate the skill repo's own `ruff.toml` / `pytest.ini` into `pyproject.toml` (imp-1)

**Status**: parked — the config-shadowing fix moved the *generated* projects'
config into `pyproject.toml`, but the skill repo's own `ruff.toml` /
`pytest.ini` were left as-is.

**Why parked**: the skill repo is not a bootstrapped artifact; migrating its
lint config could surface new lint errors on the skill's own code mid-PR, which
should not ride along on an unrelated change.

**Trigger to pick up**: a maintenance window where surfacing/fixing any new
lint findings on the skill's own code is acceptable.

**Rough effort**: ~1 hour (mechanical migration + fix any new findings).

---

### Node / Go config-file shadowing (imp-2)

**Status**: parked — the skill ships `biome.json` (Node) and `.golangci.yml`
(Go). Biome also discovers `biome.jsonc`; `golangci-lint` also discovers
`.golangci.{yaml,toml,json}`. A target-owned alternate-extension config can
therefore shadow the skill's file — the same class of bug the Python
config-shadowing fix addressed. Surfaced by Codex Tier-2 on the plan PR.

**Why parked**: the config-shadowing fix was scoped to Python, where the bug
actually bit (downstream-app dogfooding). Node/Go adoption mode is itself parked
for a follow-up, so the shadow handling belongs with that work.

**Trigger to pick up**: adoption-mode shadow handling is extended beyond
Python, or a real Node/Go adoption target is found owning an alternate-extension
config.

**Rough effort**: ~half a day (alongside Node/Go adoption-mode work).

---

## Follow-ups from the interactive-intake work (skill PR #8)

### Non-interactive `--describe "..."` CLI flag (imp-1)

**Status**: parked — PR #9 (smart stack suggestion) shipped the suggestion as
an *interactive-intake* step only. A non-interactive `--describe "<brief>"`
flag would let a scripted / CI invocation get the same language suggestion
without the guided flow.

**Why parked**: PR #9's plan scoped this out deliberately — a `--describe`
flag is a larger surface (argv parsing, non-TTY semantics, how a suggestion
interacts with an explicit `--language`). The interactive step covers the
non-coder use case the skill is built for.

**Triggers to pick up**: a real need for scripted / non-interactive stack
suggestion (e.g. a wrapper tool or a CI bootstrap that wants the suggestion).

**Rough effort**: ~2-3 hours (a flag + argv wiring + tests; the
`stack_suggest` engine already exists).

---

### Interactive intake: explicit cancel option on the output-directory re-ask (imp-1)

**Status**: parked. **Source**: Tier-1 review during skill PR #8 implementation.

**Why parked**: `intake.run_intake`'s output-directory loop re-asks `--out`
whenever the chosen folder is an existing project; the only ways out are
picking a clean folder or pressing Ctrl-D / Ctrl-C (both handled cleanly,
exit 0). A user with only existing-project folders to offer has no
explicit in-loop "cancel" choice. Ctrl-C is a working, documented escape,
so this is UX polish, not a correctness gap.

**Triggers to pick up**: a user reports feeling stuck in the
output-directory re-ask, or the next change to the intake flow.

**Rough effort**: ~20 min — accept an explicit "cancel" word at the
output-directory prompt and return `None` (same as the confirm gate's
cancel).

---

## Skill follow-ups

### Direct `--install-hooks` flag with target-venv creation

**Status**: parked (removed from PR #1's CLI in iter-16).

**Why parked**: running `pre-commit install` from the skill repo's
interpreter would tie target-project hooks to the skill repo's venv, so
hooks break if the skill repo moves or is rebuilt. The clean fix (create
the target venv first, install pre-commit there, then run `pre-commit
install` via the target's interpreter) is bigger than PR #1 can absorb.

For now, hook adoption is the generated project's `make install-hooks`
target — see `docs/usage.md`'s "Post-bootstrap hook adoption" section.

**Triggers to pick up**:
- User requests a one-step bootstrap-with-hooks for a common workflow.
- Frequent forgotten-`make install-hooks` after bootstrap in real adoption.

**Rough effort**: ~half a day. Needs to (1) create target venv during
bootstrap when `--install-hooks` is passed, (2) install pre-commit into
THAT venv, (3) invoke pre-commit via the target venv's Python, (4)
record hooks as restorable in the manifest (or document them as out of
manifest scope).

---

### Retroactively add triage rule + two-tier review docs + observability layer to Acme

**Status**: now actionable as a follow-up side-task (post-PR-#5).

**Why parked**: the "Don't fold by default — triage" rule was developed
during this skill's plan-review loop. PR #4 added the four-questions
extension + Two-tier code review section. PR #5 added `make status` for
cross-session recovery + `LESSONS.md` self-improvement loop + plan-file
Implementation log convention. Acme (the source repo this skill
extracts patterns from) doesn't have any of these yet. PR #4 + #5 ship
the relevant `shared/CLAUDE.md.tmpl` / `shared/AGENTS.md.tmpl` /
`shared/CONTRIBUTING.md.tmpl` / `shared/docs-plans-README.md.tmpl` /
`shared/Makefile.review.tmpl` / `shared/LESSONS.md.tmpl` sections;
Acme can adopt by copying.

**Triggers to pick up**: anyone working on Acme's plan-review workflow,
OR the next substantive Acme plan-review starts.

**Rough effort**: ~2 hours — copy (1) the triage block with four-questions
extension, (2) the Two-tier code review section, (3) `make status` target,
(4) `LESSONS.md` scaffold, (5) cross-session-recovery + self-improvement-loop
instructions in CLAUDE.md + AGENTS.md, (6) plan-file structural convention
in docs/plans/README.md.

---

### Console-script packaging for the skill (`pip install -e .` + entry_points)

**Status**: parked.

**Why parked**: PR #1 ships only the
`./venv/bin/python bootstrap.py` invocation path to keep the deployment
surface minimal. A console-script entry point would let users run
`dev-project-setup --apply ...` after `pip install -e .` on the skill
repo, but adds packaging surface area.

**Triggers to pick up**: first user who installs the skill via `pip` and
asks why there's no shell entry-point.

**Rough effort**: ~1 hour. Add `[project.scripts]` to `pyproject.toml`,
verify `pip install -e .` works in a fresh venv, document in `docs/usage.md`.

---

### Add frontend variants to nodejs language template

**Status**: parked.

**Why parked**: PR #2 ships framework-agnostic Node-TS (Biome + vitest + TypeScript). A true browser frontend needs additional opinionated picks: a bundler (Vite is the obvious default), a framework (React / Vue / Svelte / SvelteKit / Next.js), DOM-testing setup (jsdom or happy-dom for vitest), a dev server config. PR #2 keeps nodejs framework-agnostic so the skill stays small.

**Triggers to pick up**:
- Sandeep starts his first frontend project (most likely trigger).
- A second contributor needs a frontend variant.

**Rough effort**: ~half a day per variant. Simplest adoption path: "scaffold with `npm create vite@latest my-app -- --template react-ts` FIRST, then apply the skill on top to add Makefile / Husky / CI / plan-review-loop". The skill's nodejs scaffold composes additively. If we want a one-shot bootstrap: add `--frontend=react-vite|sveltekit|none` to `bootstrap.py` invoking the appropriate `npm create` underneath, then layering the universal scaffolds on top.

**Rough order of preference**: React+Vite first (most demand), SvelteKit second (Sandeep's stated curiosity), Vue third only if requested.

---

### Go project layout option (cmd/<name>/ vs root-level main.go)

**Status**: parked.

**Why parked**: PR #3 ships top-level `main.go` + `main_test.go` (Go's idiomatic single-binary layout). Multi-binary projects use `cmd/<name>/main.go`; library projects use no `main.go` at all. A future option flag (`--go-layout=root|cmd|library`) could let the user pick at bootstrap time.

**Triggers to pick up**: first user needs a multi-binary Go scaffold, or a Go library template.

**Rough effort**: ~half a day.

---

### Bump pinned Go tool versions (gofumpt, golangci-lint)

**Status**: parked.

**Why parked**: PR #3 pinned `GOFUMPT_VERSION ?= v0.9.2` and `GOLANGCI_LINT_VERSION ?= v2.12.2` (verified upstream as of 2026-05). The Go ecosystem moves quickly; rather than chase the latest at every plan iteration, PR #3 freezes the verified pin.

**Triggers to pick up**:
- ~6 months elapsed since the last pin.
- A user reports gofumpt v0.9.2 doesn't handle a Go 1.26+ syntax feature.
- golangci-lint upstream deprecates v2.12.x.

**Rough effort**: ~15 min. Update the two Makefile vars in `languages/go/Makefile.tmpl`, re-run smoke walk.

---

### Switch generated CI to `actions/cache` for Go tool binaries

**Status**: parked.

**Why parked**: PR #3 ships `setup-go@v5` with `cache: false` (because stdlib-only smoke project has no `go.sum`, and `setup-go`'s cache keys on `go.sum`). Tool binaries (gofumpt, golangci-lint) get re-installed on every CI run via `make install` — fast enough for current scope (~10-15s).

**Triggers to pick up**: first project where CI time on tool installs becomes a real concern.

**Rough effort**: ~half a day. Explicit `actions/cache@v4` step in `ci.yml.tmpl` keyed on Makefile vars, restore `./bin/` from cache.

---

### Broader `make selftest-bootstrap` coverage

**Status**: parked.

**Why parked**: `tests/test_selftest_overlap.py` covers 5 deterministic
overlap checks. Broader coverage (the full skill-repo `Makefile`,
`pyproject.toml`, `requirements-dev.txt`, the overlay docs) needs
context-dependent diffing that's larger than PR #1 can absorb.

**Triggers to pick up**: first drift incident between an overlay doc and
its template that the existing 5 checks miss.

**Rough effort**: ~half a day.

---

### `docs/upgrading.md` and `docs/design-notes.md`

**Status**: parked.

**Why parked**: the merged plan's directory tree included these. PR #1
keeps scope tight to `docs/usage.md`.

**Triggers to pick up**: first significant breaking change in a future PR
that needs upgrade-path docs.

**Rough effort**: ~2 hours each.

---

### Investigate `codex exec --ephemeral` for plan reviews

**Status**: parked.

**Why parked**: `make review-plan-by-codex` invokes `codex exec` without
`--ephemeral`, so Codex persists session data to `~/.codex/`. For most
plan content (workflow / infrastructure / feature scoping) this isn't a
meaningful exposure. For plans containing PII, real user data, or secrets
it would be.

Adding `--ephemeral` isn't a one-line change — needs to confirm it
composes correctly with `--output-last-message` (the mechanic the
bidirectional loop depends on).

**Triggers to pick up**: first substantive plan whose content includes
sensitive material.

**Rough effort**: ~30 min (verify, document, edit Makefile).

---

### Investigate Codex doc-only-PR auto-review skip

**Status**: parked (carried over from Acme's observation).

**Why parked**: Codex's GitHub auto-review may skip PRs whose diff is
entirely documentation. Acme observed this on two consecutive
plan-only PRs (#7, #8). PR #1 of this skill is also doc-heavy.

**Triggers to pick up**: third consecutive plan-only PR gets skipped, OR
a code PR gets skipped.

**Rough effort**: ~30 min investigation.

---

### 🟡 Per-file `--decisions` / skip / abort interactive flow — interactive DONE

**Status**: partially shipped — **interactive flow DONE** (PR #7); only the
non-interactive `--decisions` JSON remains. **Updated 2026-06-09 (backlog audit).**

**What shipped**: PR #7's `--mode=adopt` delivered the interactive per-file
decide loop (`bootstrap_lib/adopt_ui.py::_interactive_decide`): per-file
`[r]ecommended / [s]kip / [d]iff / [n]ew / [o]verwrite (typed confirm) /
[a]ppend / [q]uit-abort`. This covers the merged plan's original "asks
per-file" intent.

**What remains parked**: only the **non-interactive** `--decisions` JSON file
for scripted/CI runs — the interactive flow makes it low-value.

**Triggers to pick up**: a real scripted/CI partial-overlay case that cannot
use the interactive prompt.

**Rough effort**: ~half a day (the JSON variant only).

---

## PR #4 follow-ups

### `bootstrap.py --enable-github-review={claude,both-docs}` for retroactive Tier-2 (imp-2)

**Status**: parked.

**Why parked**: A `--github-review=none` user who later wants to add bots
must currently re-run `bootstrap.py --apply` with ALL required args
(`--language`, `--project-name`, `--out`, `--github-owner`, `--github-repo`)
plus `--overwrite-existing`. Too clunky for user-facing docs. A single
`--enable-github-review` flag would write ONLY the github-review-conditional
files (`.github/workflows/claude-review.yml`, `docs/codex-github-review-setup.md`
overlay, PR template's reviewer checklist) with `--overwrite-existing`
semantics on those specific files.

**Triggers to pick up**: first `--github-review=none` user wants to add
bots later.

**Rough effort**: ~half a day.

---

### Codex/Claude reviewer alternation per iteration (imp-1)

**Status**: parked.

**Why parked**: PR #4's plan-review loop ran 6 Codex iterations + 1 Claude
iter (Claude direction returned only a summary — known `--permission-mode plan`
quirk). Could alternate reviewers to halve loop cost, but risks losing
complementary catches that each reviewer surfaces.

**Triggers to pick up**: subscription limits hit again on PR #5 or beyond,
AND idea-(a)/(b) prompt improvements don't reduce loop count enough.

**Rough effort**: ~1 day to design + measure on a real PR.

---

### `review-plan-fact-check-by-{claude,codex}` subagent target (imp-2)

**Status**: unparked → shipped in PR #30 (feat/pr0-review-plan-fact-check).

**Why parked**: separate from idea-(b) consistency check. A narrow subagent
that reads the plan + the current repo, and for every file path / test name /
line number / module reference in the plan, verifies it matches reality.
Catches the plan-vs-repo factual-mismatch class of findings (~25% of what
Codex finds) before Codex does.

**Triggers to pick up**: if iter-N reviews on upcoming PRs keep finding
plan-vs-repo factual mismatches.

**Rough effort**: ~half a day.

---

## PR #7 follow-ups

### Adopt-mode's `Makefile` `run` target is hardcoded to `src/main.py` (imp-2)

**Status**: parked. **Source**: PR #7 adopt-mode trial against `downstream-app`.

**Why parked**: the skill's `Makefile` ships `run: uv run python src/main.py`
— correct for the greenfield smoke layout, wrong for an adopted real
project whose entry point is elsewhere (`downstream-app` uses a
`[project.scripts]` console script). After an adopt run, `make run` points
at a placeholder (or, once the placeholder is dropped per the entry above,
a missing file).

**Triggers to pick up**: the next adopt-mode change, or a user reports
`make run` broken after an adopt run.

**Rough effort**: ~1h — in adopt mode, detect the target's real entry
point (e.g. `[project.scripts]`) and retarget `run`, or leave `run` as a
documented TODO for the user to fill in.

---

### Adopt-mode does not add `pre-commit` to the target's dev dependencies (imp-2)

**Status**: parked. **Source**: PR #7 adopt-mode trial against `downstream-app`.

**Why parked**: adopt mode applies `.pre-commit-config.yaml` and the
`make install-hooks` target, but `make install-hooks` runs
`uv run pre-commit install` — and adopt mode (correctly) does not
overwrite the target's real `pyproject.toml`, so `pre-commit` is missing
from the target's dev-dependency group and `make install-hooks` fails.
(Distinct from the parked "Direct `--install-hooks` flag" entry under
"Skill follow-ups", which is about a skill-side bootstrap flag.)

**Triggers to pick up**: the first adopt user runs `make install-hooks`
and it fails on a missing `pre-commit`.

**Rough effort**: ~1h — adopt mode appends `pre-commit` to the detected
dev-dependency group (or prints a one-line "add pre-commit to your dev
deps" hint after applying `.pre-commit-config.yaml`).

---

### Adopt-mode: `AGENTS.md` can collide with the target's `.gitignore` (imp-1)

**Status**: parked. **Source**: PR #7 adopt-mode trial against `downstream-app`.

**Why parked**: `downstream-app`'s `.gitignore` listed `AGENTS.md` (it had
been ignored as Codex-CLI scratch residue). The skill's `AGENTS.md` is a
*tracked* reviewer-guidance deliverable, so an ignored `AGENTS.md` is
silently never committed and the GitHub review bots never read it. Adopt
mode writes the file but does not notice the gitignore conflict.

**Triggers to pick up**: an adopt user whose `.gitignore` already lists
`AGENTS.md` reports the review bots having no repo-specific guidance.

**Rough effort**: ~30 min — adopt mode detects an `AGENTS.md` entry in the
target's `.gitignore` and warns (or documents the conflict in the
adopt-mode docs).

---

### Annotate `--diff` headers with adopt-mode policy recommendations (imp-2)

**Status**: parked. **Source**: Tier-1 doc review on Bucket F docs commit (PR #17).

**Why parked**: Plan PR #16 Scope #8 + Bucket A row 8 specified that
plain `bootstrap.py --diff --language python` should run the analyzer
in read-only mode and annotate each unified-diff header with the
recommended policy (e.g. `--- a/CLAUDE.md (target: 96 lines)` /
`+++ b/CLAUDE.md (recommendation: WRITE_NEW)`). PR #7's impl path
focused on `--apply --mode=adopt` end-to-end; the `--diff` annotator
was not shipped. Plain `--diff` currently produces standard
`difflib.unified_diff` headers without policy annotations.

The Bucket F docs reference this caveat inline in the worked example;
the recommendation report (Step 2 of adopt-mode) shows the policy
per file, so the user-facing gap is only in the read-only-preview
workflow.

**Triggers to pick up**:
- A user requests inline policy annotations during `--diff` preview.
- Bucket E live trial surfaces the read-only-preview UX gap as a
  blocker to confident adopt-mode adoption.

**Rough effort**: ~2 hours — extend `_print_diff` in `bootstrap_lib/cli.py`
to call `adopt.analyze_target` when `args.language == "python"` (no
manifest, no writes), then inject policy strings into the `fromfile`/
`tofile` arg shape. Tests in `tests/test_bootstrap_cli.py` + new
fixture in `tests/test_mode_adopt_smoke.py` for the annotated diff
shape.

---

### Path-safety validation for `--mode=adopt` against sensitive target paths (imp-2)

**Status**: parked. **Source**: claude[bot] Tier-2 review on Plan PR #16 (finding #1).

**Why parked**: PR #7's `--mode=adopt` doesn't add path-safety validation
against sensitive target paths (those containing `secrets/`, `data/`,
customer content, real PII directories). The existing renderer-layer +
CLI-layer path-safety check guards against `..`/absolute-path escapes
but doesn't refuse to operate against paths that LOOK like production
data directories. The first version's blast radius is bounded by adopt
mode's per-file consent model (every recommendation is shown + decided
with the owner), but an extra refuse-by-default for sensitive paths
would be defense-in-depth.

**Triggers to pick up**:
- First user reports adoption-mode acting against a path containing
  `secrets/` or `data/`.
- A near-miss during a Tier-2 review of a future adoption-mode PR.

**Rough effort**: ~1 hour — add a path-pattern check in
`bootstrap_lib/cli.py` before adopt-mode dispatch (refuse paths matching
`secrets/`, `data/`, `customer_data/`, configurable via flag for
intentional opt-in). Tests in `tests/test_bootstrap_cli.py`.

---

### Adoption-mode: align line-ending handling between gitignore normalization and append-merge (imp-1)

**Status**: parked. **Source**: Tier-1 review on `plan_adoption_entries` impl
commit (PR #17).

**Why parked**: `_normalize_gitignore_lines` (used by rule (d) membership
check in `recommend_policy`) decodes UTF-8 and uses `str.splitlines()`,
which handles `\r\n`/`\r`/`\v`/`\f` line endings. But
`compute_append_merge_bytes` (used to compute the post-apply bytes and
the apply-time write) operates in bytes and uses `bytes.split(b"\n")`,
which only splits on `\n` and leaves `\r` in each line.

For a CRLF-terminated target `.gitignore` (Windows-cloned repo, mixed
toolchain), rule (d)'s membership check matches `b"venv/"` (post-strip),
but the merge function's appended `raw_line` retains the `\r`, producing
a mixed `\r\n` + `\n` output on the next apply.

The PR #7 scope (downstream-app/ trial on macOS) uses LF-terminated
gitignore, so this doesn't fire. Real-but-deferrable.

**Triggers to pick up**:
- First user reports `.gitignore` mojibake or churn on a Windows-
  cloned repo using `--mode=adopt`.
- A test failure on a CI matrix that runs on Windows (not currently
  configured).

**Rough effort**: ~30 min — either (a) align both to bytes-split on
`\n` with `\r` stripped before processing, or (b) align both to
`str.splitlines()` after UTF-8 decode. Tests in `TestComputeAppendMergeBytes`
need one CRLF round-trip test added.

---

### Adoption-mode: route APPEND_MERGE restore through atomic_write for parity with OVERWRITE (imp-2)

**Status**: parked. **Source**: Tier-1 review on v2 restore matrix impl commit (PR #17).

**Why parked**: `_restore_v2_append_merge` uses
`open(path, "rb+").truncate(pre_append_length) + flush + fsync` to undo
APPEND_MERGE applies. `truncate(N)` is atomic-at-inode-level on POSIX
filesystems (the file length is old-or-new, never partial bytes), so
the safety contract holds. But v1 OVERWRITE restore routes through
`bio.atomic_write` (tmp + `os.replace`) per Codex iter-21 P1's
"no in-place truncation" discipline, and APPEND_MERGE diverges from
that pattern. Marginally weaker consistency story than "all restore
paths route through atomic_write."

The alternative (read `[:pre_append_length]` bytes + atomic_write)
costs one extra read per APPEND_MERGE entry — negligible at PR #7's
trial scale (1 collision file).

**Triggers to pick up**:
- First reported crash-during-restore bug that surfaces APPEND_MERGE
  truncation state inconsistency.
- A future audit of "all restore mutations route through atomic_write"
  catching this divergence.

**Rough effort**: ~30 min — replace truncate block with `data = full[:pre_append_length]; bio.atomic_write(target_path, data)`. Tests
already assert post-restore content equality, no test changes needed.

---

### Adoption-mode: thread `target_content` from analyze_target to recommend_policy (imp-1)

**Status**: parked. **Source**: Tier-1 review on `analyze_target` impl commit (PR #17).

**Why parked**: `_compute_target_meta` reads each existing target file
once; `recommend_policy` re-reads the same file (for rules b/d/f/g that
need bytes). For PR #7's downstream-app collision set (4 files), that's
8 reads vs 4 — negligible. For a target with hundreds of colliding
files, the double-read could matter. The current docstring on
`recommend_policy` explains the design choice: TargetMeta is deliberately
content-free per Scope #11 privacy boundary — but a separate `bytes`
parameter wouldn't violate that.

**Triggers to pick up**:
- First user reports adopt-mode running noticeably slow against a large
  target (>100 colliding files).
- Performance benchmarks added to the CI run.

**Rough effort**: ~1 hour — add `target_content: bytes | None = None`
parameter to `recommend_policy`; `analyze_target` passes the buffer
from `_compute_target_meta`'s read (via a small refactor of
`_compute_target_meta` to optionally return content alongside meta).
Update all existing `recommend_policy` callers in tests.

---

### Adoption-mode rule (d): `.gitignore` order-aware merge for `!negation` patterns (imp-1)

**Status**: parked. **Source**: Tier-1 review on `recommend_policy` impl commit (PR #17).

**Why parked**: `_normalize_gitignore_lines` (`bootstrap_lib/adopt.py`)
uses a `set` for line-membership, which is correct for the common case
(skill adds new positive patterns missing from target's gitignore) and
order-blind by design. Gitignore semantics ARE order-dependent in one
edge case: `*.log` followed by `!important.log` differs from the reverse
order. The current APPEND_MERGE always appends to end, so if the skill
template ever includes `!negation` patterns that need to come AFTER
specific positive matches in the target, the merge would produce
semantically-different behavior than a hand-written ordering.

The downstream-app collision set used for PR #7's trial doesn't have
`!negation` patterns; the skill's own `.gitignore.tmpl` doesn't either.
Real-but-deferrable.

**Triggers to pick up**:
- First user reports APPEND_MERGE producing wrong gitignore semantics
  after running `--mode=adopt` on a project with negation patterns.
- The skill's `.gitignore.tmpl` ever adds a `!negation` pattern.

**Rough effort**: ~1 hour — extend `_normalize_gitignore_lines` to
return an ordered list with positional metadata; rewrite the APPEND_MERGE
contract to insert `!negation` lines in semantically-correct positions
rather than always-end-append. Manifest v2 `pre_append_length` would
need to become a more general "pre-merge state hash" for restore to work.

---

### Filesystem-stress test for v1→v2 restore (imp-2)

**Status**: parked. **Source**: claude[bot] Tier-2 review on Plan PR #16 (finding #2).

**Why parked**: PR #7's manifest v2 introduces per-policy restore
semantics (`WRITE` removes created file, `OVERWRITE` writes
content_before_b64 back, `WRITE_NEW` removes `.new`, `APPEND_MERGE`
truncates to `pre_append_length`). The standard tests cover the happy
path + SHA-mismatch guard, but not filesystem-stress scenarios
(disk-full mid-restore, permission changes between manifest write and
restore, `EACCES` on `os.chmod`, `ENOSPC` on `write`, race with another
process). PR #1's restore had the same gap; PR #7 inherits + extends.

**Triggers to pick up**:
- First reported restore failure under disk-full or permission-change
  scenarios.
- A future PR rewrites restore internals (worth covering before
  shipping).

**Rough effort**: ~half a day. Add a fixture with monkey-patched
filesystem operations in `tests/test_manifest.py` covering: (i) ENOSPC
mid-restore, (ii) EACCES on chmod, (iii) target file modified between
manifest write and restore (SHA mismatch — already covered, but
exercise the cleanup path), (iv) partial restore (some files restored,
some failed — verify cleanup state).

---

## PR #6 follow-ups

### Pin uv binary version in CI (imp-1)

**Status**: parked.

**Why parked**: Generated CI uses `astral-sh/setup-uv@v8.1.0` (action ref pinned — required because setup-uv v8 has no floating major tag). The uv BINARY version is NOT pinned — the action's default (latest stable uv) is what gets installed. `uv.lock` provides per-project reproducibility, so the binary version drift is OK for most cases.

**Triggers to pick up**:
- First time the action's default-latest uv binary breaks a smoke walk.
- User reports CI non-determinism from uv version drift.

**Rough effort**: ~30 min — add `version:` input to the `astral-sh/setup-uv@v8.1.0` invocations in both `languages/python/ci.yml.tmpl` (generated CI) and `.github/workflows/ci.yml` (skill repo CI) + docstring explaining the trade-off.

---

### uv migration tool (`bootstrap.py --migrate-from=pip --to=uv`)

**Status**: parked.

**Why parked**: PR #6 added uv support but does NOT convert existing pip projects to uv (adoption-mode respects the user's existing tooling). A migration tool would: read `requirements*.txt`, convert pin lines to `[dependency-groups].dev` in `pyproject.toml`, run initial `uv sync` to create `uv.lock`, optionally delete `requirements*.txt` after success.

**Triggers to pick up**:
- A user explicitly asks "I have a pip project; how do I switch to uv?"
- The PR #7 trial on `downstream-app/` surfaces this as a common adoption need.

**Rough effort**: ~1 day — design + impl + tests + docs.

---

### Library-style scaffold (`--library` flag)

**Status**: parked.

**Why parked**: PR #6's greenfield uv mode ships in "non-package" mode (`[project]` table, no `[build-system]`) — correct for application starters, but doesn't support building a wheel. A `--library` flag would: add `src/<project_import_name>/__init__.py` package layout + `[build-system] uv_build` + `dependencies = []` stays + add `[project.scripts]` entry for installable CLIs.

**Triggers to pick up**: First user with a real library-publishing use case.

**Rough effort**: ~half a day — new scaffold files + tests + Architecture-decision doc edits.

---

## PR #5 follow-ups

### `sync-plan-to-ui` Makefile target (imp-1)

**Status**: parked.

**Why parked**: Claude Code's plan-mode UI reads from `~/.claude/plans/<file>.md`
which is separate from the in-repo `docs/plans/<file>.md`. As iterations
proceed in-repo, the UI version drifts. A `make sync-plan-to-ui PLAN_FILE=...
UI_NAME=...` target would `cp` the in-repo file over the UI file.

**Triggers to pick up**: if the drift causes another confusion incident
like the one in PR #5 plan loop (user opened the plan-mode UI and saw the
iter-1 version while the repo had iter-6).

**Rough effort**: ~15 min — a tiny `cp` target with safety check.

---

### Investigate Codex GitHub bot's ready-state auto-fire reliability (imp-1)

**Status**: parked (investigation) — **workaround shipped** (`docs/usage.md`). **Updated 2026-06-09 (backlog audit).**

**New data point (2026-06-09)**: Codex again did NOT auto-fire on PR #38's
ready-state; the explicit `@codex review` nudge worked. With PR #9 / #10 + #38,
the "third consecutive non-fire" trigger is effectively met — the investigation
(GitHub-app webhook config + Codex bot release notes) is now actionable, not
just deferred.

**Why parked**: empirically, Codex Tier-2 review didn't auto-fire on
`gh pr ready` transition during Plan PR #9 + Impl PR #10. Both required
explicit `@codex review` comment to trigger. Codex DID auto-fire on Impl
PR #11. Pattern unclear — might be timing, might be the specific PR
content shape, might be GitHub-app config.

**Triggers to pick up**: third consecutive PR where Codex doesn't
auto-fire on ready-state. Then investigate the GitHub app's webhook
config + recent Codex GitHub-bot release notes.

**Workaround until investigated**: documented in `docs/usage.md` —
always comment `@codex review` after `gh pr ready` if Codex doesn't
auto-fire within ~5 min.

**Rough effort**: ~30 min investigation + ~15 min doc note if it turns
out to be a known limitation.

---

### Helper script to auto-append a reviewed impl-log row (imp-1)

**Status**: parked.

**Why parked**: per PR #5 plan, `## Implementation log` rows are
proposed by Tier-1 review and pasted by the driver into the plan file
(then a separate docs-only commit). PR #5's "Capture is semi-automatic"
design principle (closes Codex iter-5 #5) explicitly acknowledged the
manual paste step as a trade-off. A helper script (`make append-impl-log
PLAN_FILE=... ROW='...'` or one that parses the Tier-1 output) would
automate this.

**Trigger to pick up**: if driver-forgets-to-paste happens twice on any
post-PR-#5 implementation PR.

**Rough effort**: ~1 hour.

---

### Review-target shell-injection hardening for PLAN_FILE / ITERATION passthrough (imp-2)

**Status**: parked.

**Why parked**: PR #35's `make review` dispatcher sanitizes its MODE/ACTOR
inputs via a `$(filter)` allowlist, but `PLAN_FILE` / `ITERATION` are still
expanded directly into the recipe shell (`PLAN_FILE="$(PLAN_FILE)"` in the
sub-make call) — and the `review-plan-by-*` / `review-commit-by-*` sub-targets
they dispatch to ALSO embed `$(PLAN_FILE)` / `$(ITERATION)` directly in their
shell prompts and `test -f` guards. So this is a PRE-EXISTING injection class
spanning every review target, NOT introduced by the dispatcher — a
dispatcher-only fix would be cosmetic because the sub-target re-introduces it.
The trust model matches MODE/ACTOR (values come from the user's own shell or
the `/dev-review` command's fixed args — no untrusted-input boundary), so
severity is low. Surfaced by the PR #35 live `/dev-review commit` smoke (Tier-1
F1).

A SECOND, related class (PR #35 codex re-review): make-level `$(shell ...)`
execution. Because make expands `$(VAR)` fully (re-scanning the result), a
value like `make review ACTOR='$(shell rm -rf ~)codex'` runs the embedded
`$(shell)` when the dispatcher evaluates `$(filter … ,$(ACTOR))` — verified,
and `$(value)`/`$(origin)` do NOT prevent it (the filter argument is
re-expanded). This is inherent to GNU make (it affects every `$(VAR)` in every
recipe/target, not just the dispatcher) and is bounded by the same
no-untrusted-input trust model. There is no clean make-level fix (you cannot
inspect a value without expanding it); the practical mitigation is "don't pass
untrusted strings to `make`", same as any Makefile. Likely WONTFIX unless an
untrusted-input path appears; documented here so it isn't re-triaged each pass.

**Trigger to pick up**: a repo-wide review-target hardening pass — single-quote
`$(PLAN_FILE)` (e.g. `$(subst ','\'',$(PLAN_FILE))`) and numeric-filter
`ITERATION` across ALL `review-*` recipes + the dispatcher (byte-identical in
`Makefile` + `shared/Makefile.review.tmpl`) — OR if any review target ever
consumes PLAN_FILE/ITERATION (or MODE/ACTOR) from an untrusted source.

**Rough effort**: ~2 hours (all review-* recipes in both Makefile surfaces + tests).

**Done in PR #35** (not parked): the `.gitignore` MODE-preservation half of the
codex re-review — NEUTRALIZE now captures `mode_before` and apply+restore chmod
to it, so a private (e.g. 0600) ignore file is never loosened to 0644.

---

### Migrate `claude-review.yml` off `claude-code-action@beta` (imp-2)

**Status**: parked 2026-07-25 — the workflow now pins `model: claude-sonnet-5`
explicitly (both `.github/workflows/claude-review.yml` and
`shared/claude-review.yml.tmpl`), after the `@beta` action's built-in default
model (`claude-sonnet-4-20250514`, retired 2026-06-15) started returning 404 on
every `pull_request` run — first observed on PR #50, where auth succeeded (the
2026-07-13 CLAUDE_CODE_OAUTH_TOKEN refresh worked) but the model lookup failed.
The pin fixes the break; `@beta` remains a deprecated moving tag whose other
defaults can drift the same way.

**Trigger to pick up**: the next change that touches the claude-review workflow
template for any other reason, OR the next `@beta`-attributable breakage.

**Starting requirements**: migrate to `anthropics/claude-code-action@v1` — the
input surface differs from `@beta` (e.g. `direct_prompt` was renamed; verify the
current input set against the v1 `action.yml` rather than bumping the tag
blind), so it needs the template + dogfood byte-identity pass and a live PR
smoke. Consider `fallback_model` at the same time (weigh silent degradation vs
no-review-at-all for an advisory bot).

---
