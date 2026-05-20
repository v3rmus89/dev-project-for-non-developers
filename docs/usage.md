# Using the `dev-project-setup` skill

## Local prerequisites

Before running `make install` or invoking the skill, ensure these are on PATH:

- `make` — POSIX `make`. BSD make on macOS works; GNU make works on Linux. (Hard prereq: you can't `make doctor` to diagnose missing `make`.)
- `python3.12` — required for the skill itself. `python3` on macOS may be 3.9.x; the skill repo's `Makefile` invokes `python3.12 -m venv` explicitly.
- venv support — `python3.12 -m venv` must work. On Linux you may need `apt install python3.12-venv`.
- `pip` + network access to PyPI — for installing pinned `jinja2`, `pyyaml`, `pytest`, `ruff`, `pre-commit`.
- `git` — required by every generated project's `make install-hooks` (guarded by `test -d .git`).
- `node` + `npm` — required if you'll bootstrap **nodejs** projects (`--language nodejs`). The skill repo's own `make check` smoke-tests the Node walk; without `node` on PATH locally it skips cleanly, but CI must have Node 24 via `actions/setup-node`.

Optional:

- `claude` CLI — needed for the **local** `make review-plan-by-claude`, `make review-commit-by-claude`, and `make review-plan-consistency-by-claude` targets. Not needed for `make check` or the GitHub Actions workflow.
- `codex` CLI — needed for the **local** `make review-plan-by-codex` and `make review-commit-by-codex` targets. Same scoping as above.

Run `make doctor` after `make install` to verify the core prereqs are present.

## CLI surface

```
./venv/bin/python bootstrap.py [MODE] [render-args]
```

### Modes (mutually exclusive; default is `--dry-run`)

| Flag | Effect |
|---|---|
| `--dry-run` | (default) print planned writes; no filesystem changes |
| `--diff` | print a unified diff against existing files at `--out`; no filesystem changes |
| `--apply` | actually write files (writes restore manifest first) |
| `--restore MANIFEST` | reverse an apply using the manifest path printed in the prior `to rollback:` line |

> `--mode=adopt` is a **per-file adoption modifier of `--apply`** — NOT a 5th mode. See the [Adoption mode](#adoption-mode---modeadopt) section below.

### Render/apply args (required when not in `--restore` mode)

| Flag | Description |
|---|---|
| `--language {python,nodejs,go}` | target language. PR #1 shipped Python; PR #2 added Node-TS (Biome + vitest + TypeScript + Husky); PR #3 added Go (gofumpt + golangci-lint + native git hooks); PR #6 added uv support for Python. All three v1 languages supported |
| `--project-name <slug>` | must match `^[a-z][a-z0-9-]*$` (lowercase ASCII + digits + hyphens, leading letter, no path separators) |
| `--out <dir>` | target directory; created ONLY during `--apply` |
| `--package-manager {uv,pip}` | **Python only.** Default `uv` for greenfield; auto-detected when bootstrapping into an existing project (positive markers: `uv.lock`, `[tool.uv]` table, or `build-backend = "uv_build"` in `pyproject.toml` → `uv`; `requirements*.txt` glob → `pip`). Use `pip` to opt out. See "Python: uv vs pip" section below for the full guide |
| `--github-review {none,claude,both-docs}` | default `none` — no Claude workflow / OAuth secret dependency unless explicitly opted in |
| `--github-owner <owner>` | required when `--github-review != none` |
| `--github-repo <repo>` | required when `--github-review != none` |
| `--overwrite-existing` | required during plain `--apply` if any target file already exists. **For adopting the skill into an existing project, prefer `--apply --mode=adopt`** (per-file recommendations) instead of this nuclear overwrite. Rejected when combined with `--mode=adopt` (conflicting consent models) |
| `--enable-smoke` | also emit `docs/SMOKE.md` skeleton (default: omit) |
| `--mode adopt` | **Python-only** adoption modifier of `--apply`. Enables per-file analyze-then-decide-with-owner UX. Requires `--apply`; rejected with `--dry-run` / `--diff` / `--restore` / `--language != python` / `--overwrite-existing`. See [Adoption mode](#adoption-mode---modeadopt) below |
| `--auto-accept-recommendations` | (with `--mode=adopt` only) auto-applies every policy with `manual_review_needed=false` without a prompt. `manual_review_needed=true` files still need a decision. Rejected if used outside `--mode=adopt` |
| `--non-interactive` | (with `--mode=adopt` only) any required prompt becomes a fail-loud exit 2. Combine with `--auto-accept-recommendations` for CI ("accept everything safe, fail on anything needing review"). Rejected if used outside `--mode=adopt` |

## Safety contract (dry-run by default → diff → apply → restore)

1. **`--dry-run`** prints the list of files the skill would write. Filesystem is untouched.
2. **`--diff`** is a fuller inspection — unified diff against any existing files at `--out`. Filesystem is still untouched.
3. **`--apply`** writes files. BEFORE the first write:
   - A JSON restore manifest is written to `$TMPDIR/dev-project-setup-restore-<timestamp>.json` and `fsync`'d.
   - The manifest records every file's pre-apply SHA-256 + content snapshot (base64) + mode, every directory the apply will create, and the planned post-apply SHA-256 + mode.
   - Each file is written via `<target>.bootstrap-tmp` + `os.rename` (atomic on POSIX same-filesystem).
   - SIGTERM/SIGINT during apply removes any stale `.bootstrap-tmp` artifacts via signal handlers + `atexit`.
   - The printed `to rollback:` line is a self-contained absolute-path command — runnable from any cwd.

4. **`--restore <manifest>`** reverses an apply:
   - All entry paths are validated for safety before any filesystem action (absolute paths, `..` traversal, symlink escapes all rejected).
   - For each entry, the current SHA-256 is compared against the manifest's `sha256_after`:
     - Match → the apply did write it. Overwritten files get their `content_before_b64` written back + mode restored; created files get `os.remove`d.
     - Match against `sha256_before` instead → the apply was interrupted before this file. No-op.
     - Neither → user edit since apply. SKIPPED with a warning ("left in place").
   - Created directories are removed in reverse-depth order, but only if empty.

## Adoption mode (`--mode=adopt`)

`--apply --mode=adopt` adapts the skill's templates onto an **existing** Python project safely, file-by-file, with the owner deciding on anything risky. It's the recommended path for adding the skill's workflow (CI / hooks / docs / plan-loop) to a project that already has its own `CLAUDE.md`, `pyproject.toml`, `.gitignore`, etc.

**When to use it**:

- The target directory has pre-existing files that you don't want clobbered (CLAUDE.md with domain content, pyproject.toml with project-specific deps, etc.).
- You want a per-file recommendation report BEFORE writes happen — not a blanket "abort on any collision" (plain `--apply`) or "overwrite everything" (`--apply --overwrite-existing`).
- You want a `.new` file written alongside `CLAUDE.md` so you can review the skill's template + manually merge what you want.

**When NOT to use it**:

- Greenfield projects (no files in target) — plain `--apply` is fine; adopt-mode adds no value.
- Non-Python languages (Node / Go) — adopt-mode is Python-only in PR #7. Node/Go adoption-mode is parked for follow-up.

### How it works (4 phases)

1. **Analyze** — every planned file is inspected against the target. The analyzer produces a `TargetMeta` per file (size, sha256, line count, heading count, structural flags like `[dependency-groups]` or `python-version` pin, gitignored-by-git source:line reference). NO raw file content is captured — only derived markers, hashes, structural counts (privacy boundary).
2. **Recommend** — per-file policy via 9 heuristic rules (evaluated in order; first match wins):

   | Rule | Trigger | Policy | Manual review? |
   |---|---|---|---|
   | (a0) | missing AND ignored by `git check-ignore` | `SKIP` | **yes** (always) |
   | (a) | missing AND not ignored | `WRITE` | no |
   | (b) | exists AND empty / whitespace-only | `OVERWRITE` | no |
   | (c) | exists AND byte-identical to skill template | `SKIP` | no |
   | (d) | `.gitignore` AND skill patterns NOT all present | `APPEND_MERGE` | no |
   | (e) | `.python-version` AND any pin | `SKIP` | no |
   | (f) | `CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING.md` / `BACKLOG.md` / `LESSONS.md` AND >20 lines OR has custom headings | `WRITE_NEW` | **yes** |
   | (g) | `pyproject.toml` AND has `[project] dependencies`, `[tool.*]`, or `[dependency-groups]` | `SKIP` | **yes** |
   | (h) | DEFAULT (existing non-empty file, no recognized pattern) | `SKIP` | **yes** |

   Rule (h) is the core safety guarantee: any unrecognized existing file gets `SKIP` with manual review — never destructive `WRITE`.

3. **Decide** — only files with `manual_review_needed=true` trigger an interactive prompt. The per-file allowed-actions matrix:
   - **always available**: `[r]ecommended` (default — just press Enter) / `[s]kip` / `[d]iff` / `[?]help` / `[q]uit`
   - `[n]ew` (WRITE_NEW): for any manual-review file
   - `[a]ppend` (APPEND_MERGE): **`.gitignore` only** (line-level idempotent merge)
   - `[o]verwrite`: always available BUT requires typed `OVERWRITE` (uppercase, case-sensitive) — single-keystroke `o` won't suffice (safety against stray-keystroke destruction of CLAUDE.md)

4. **Apply** — each non-SKIP entry is written atomically; SKIP entries don't appear in the v2 restore manifest (mutation-only contract). The manifest is fsync'd BEFORE any filesystem write, so `--restore` rolls back partial-apply states.

### Worked example (call-details/ shape)

Suppose `~/Desktop/Code/Boxette/call-details/` already has `CLAUDE.md` (50 lines of domain content), `pyproject.toml` (with `[tool.ruff]`), `.gitignore` (with `venv/\n*.pyc\n`), and `.python-version` (pins `3.12`). 15 other files the skill writes are missing.

**Step 1**: inspect with `--diff` (read-only; no `--mode=adopt` needed):

```bash
./venv/bin/python bootstrap.py --diff --language python \
    --project-name call-details \
    --out ~/Desktop/Code/Boxette/call-details/
```

Prints a unified diff per file (`--- a/<path>` / `+++ b/<path>` headers, plain `difflib.unified_diff` shape). Read it to understand what each collision file's skill-template-vs-target diff looks like before running adopt-mode. *(Note: a richer `--diff` mode that annotates each diff header with the recommended policy was specified in Bucket A row 8 but is not yet implemented; tracked in `BACKLOG.md` for a follow-up PR. For now, the recommendation report (Step 2) shows the policy per file.)*

**Step 2**: run `--apply --mode=adopt`:

```bash
./venv/bin/python bootstrap.py --apply --mode=adopt --language python \
    --project-name call-details \
    --out ~/Desktop/Code/Boxette/call-details/
```

The recommendation report is printed first:

```
adoption recommendation: 19 file(s) analyzed at ~/Desktop/Code/Boxette/call-details

automatic (17):

  APPEND_MERGE  .gitignore
                target: 2 lines, sha256:568b5ad5
                reason: 5 skill .gitignore pattern(s) missing from target; append-only line-level merge

  SKIP          .python-version
                target: 1 line, pin=3.12, sha256:7a41a413
                reason: target content matches skill template byte-for-byte; no-op

  WRITE         Makefile
                target: missing
                reason: target file does not exist; safe to create

  ... (14 more automatic entries) ...

manual review needed (2):

  WRITE_NEW     CLAUDE.md
                target: 50 lines, 4 headings, sha256:21fc8398
                reason: target CLAUDE.md has domain content (>20 lines or custom headings); preserve original and write .new for manual merge

  SKIP          pyproject.toml
                target: 24 lines, sha256:f7d5e29c
                reason: target pyproject.toml has [project] deps, [tool.*], or [dependency-groups]; review the diff manually with --diff

summary: APPEND_MERGE=1 SKIP=2 WRITE=15 WRITE_NEW=1  (2 need your decision)
```

Then the interactive prompts fire for the 2 mr=True files. Pressing Enter accepts the recommendation; type `s`+Enter to skip; `d`+Enter shows the unified diff inline; `?`+Enter shows the action help. For `[o]`, you'll be prompted to type `OVERWRITE` exactly (uppercase) to confirm.

After decisions land:

```
adopt-mode apply: 17 mutating entries written to ~/Desktop/Code/Boxette/call-details/
restore manifest: /var/folders/.../dev-project-setup-restore-20260520T120000Z.json
to rollback: /Users/me/skill/venv/bin/python /Users/me/skill/bootstrap.py --restore /var/folders/.../dev-project-setup-restore-20260520T120000Z.json
```

**Step 3**: review what changed. `CLAUDE.md` is unchanged; `CLAUDE.md.new` was written alongside it. Diff manually:

```bash
diff -u CLAUDE.md CLAUDE.md.new
# inspect, merge what you want, then `rm CLAUDE.md.new` when done
```

**Step 4**: if you're unhappy with anything, roll back:

```bash
./venv/bin/python bootstrap.py --restore /var/folders/.../dev-project-setup-restore-20260520T120000Z.json
```

The restore is **policy-aware**: `WRITE` entries get deleted, `OVERWRITE` entries get the pre-apply content written back, `WRITE_NEW` entries get their `.new` file removed (original was never touched throughout), `APPEND_MERGE` entries get truncated to their pre-append byte length. SKIP'd files are NOT in the manifest and never get touched by restore.

### CI contract (`--auto-accept-recommendations` + `--non-interactive`)

For CI runs that adopt the skill into a known-good shape:

```bash
./venv/bin/python bootstrap.py --apply --mode=adopt --language python \
    --project-name $PROJECT_NAME \
    --out $TARGET_DIR \
    --auto-accept-recommendations \
    --non-interactive
```

Semantics:

- Every `manual_review_needed=false` file auto-applies (no prompt).
- Any `manual_review_needed=true` file (rule a0 / f / g / h, OR a SKIP'd file the analyzer can't classify) triggers a fail-loud exit 2.

This is the "accept everything safe, fail on anything needing review" contract. It's the natural CI shape — if the target has unexpected domain content, CI fails and a human looks at it.

### Restore safety guarantees

The v2 restore matrix preserves these invariants:

- `--restore` never deletes a pre-existing file classified as `SKIP` or `OVERWRITE`. (The hole-class that the iter-1 #3 plan fold closed — rules (b)/(c)/(e) had previously classified existing files as `WRITE`, and `WRITE`'s restore deletes the path.)
- `--restore` never touches the original file when the policy was `WRITE_NEW` — only the `.new` file is removed.
- `--restore` uses SHA-guarded checks: if you edited the file between apply and restore, the entry is SKIPped with a warning (never clobbered).
- Path-safety pre-flight runs BEFORE any filesystem mutation — `..` traversal, absolute paths, symlink escapes all rejected.

### Limitations + caveats

- **`APPEND_MERGE` is `.gitignore`-only** in PR #7. Other file types (e.g. `README.md` with a "Status" section append) are too risky for automated merging — recommended path is `SKIP` with manual diff.
- **Adoption-mode is Python-only** in PR #7. Node/Go adoption-mode is parked for follow-up; the same Scope #5 rules will need language-specific tweaks (e.g. `[tool.uv]` → `package.json` "dependencies" for nodejs).
- **No undo within an interactive session**. If you pick the wrong policy mid-prompt, `[q]uit` aborts the entire run (no files written yet); fix your thinking and re-run.
- **The `.new` collision rule** fails loud if `<original>.new` already exists at plan-time. Rename / remove the existing `.new` before running adopt-mode.

## Post-bootstrap hook adoption

The bootstrap process itself never installs git hooks. To wire up the pre-commit + pre-push hooks in the generated project:

```bash
cd <out>
make install        # python+uv: uv sync (.venv/ + uv.lock); python+pip: venv + pip; nodejs: npm install + arms husky
make install-hooks  # registers / re-arms git hooks (requires .git/)
```

`make install-hooks` is a target IN THE GENERATED PROJECT, NOT a bootstrap CLI flag. The Makefile-target surface is identical across languages; the underlying tool differs:

- **Python (uv mode)**: hooks via `pre-commit` framework, invoked through `uv run pre-commit`. `make install-hooks` runs `uv run pre-commit install` (commit-side) + `uv run pre-commit install --hook-type pre-push`. The framework's own deps live in `.venv/` managed by uv.
- **Python (pip mode)**: hooks via `pre-commit` framework, invoked through the project venv. `make install-hooks` runs `./venv/bin/pre-commit install` (commit-side) + `./venv/bin/pre-commit install --hook-type pre-push`.
- **Node-TS**: hooks via Husky v9 + lint-staged. Hooks are armed automatically during `npm install` (via `package.json`'s `"prepare": "husky"` script); `make install-hooks` is a defensive idempotent re-arm path (e.g. for users who ran `npm install --ignore-scripts`).

Hooks live in `.git/hooks/` (Python), `.husky/` (Node), or `hooks/` via `core.hooksPath` (Go) and survive moves or rebuilds of the skill repo.

### Python: uv vs pip

**What `uv` is** (one paragraph for the non-developer audience): `uv` is a fast Rust-based Python package manager from Astral (~10–100× faster than pip in practice). It manages a per-project virtual environment (`.venv/`) for you, locks every dependency precisely in `uv.lock` so installs reproduce on any machine, and can install Python itself via `uv python install`. Same `pyproject.toml`, mostly compatible with pip-era tooling. Commands look like `uv add requests`, `uv run pytest`, `uv sync` — no manual venv activation needed.

**When each mode fires:**

| Scenario | Mode picked | Why |
|---|---|---|
| `--language=python --out=<empty-or-nonexistent-dir>` | `uv` (default) | greenfield Python → modern path |
| `--language=python --out=<existing-dir-with-uv.lock>` | `uv` (auto-detected) | positive uv marker `uv.lock` |
| `--language=python --out=<existing-dir-with-[tool.uv]>` | `uv` (auto-detected) | positive uv marker in pyproject.toml |
| `--language=python --out=<existing-dir-with-build-backend="uv_build">` | `uv` (auto-detected) | positive uv marker (PEP 517 key, kebab-case) |
| `--language=python --out=<existing-dir-with-requirements*.txt>` | `pip` (auto-detected) | positive pip marker (wildcard glob — covers `requirements.txt`, `requirements-dev.txt`, `requirements-test.txt`, etc.) |
| `--language=python --out=<existing-pyproject-no-PM-markers>` | `uv` (CLI default) + override-hint advisory | ambiguous; advisory on stderr surfaces the choice |
| `--language=python --package-manager=pip` | `pip` (explicit override) | escape hatch; ignores detection |

**Install instructions for `uv` itself** (one-time per machine):

```bash
# macOS:
brew install uv
# Linux / WSL:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or via pipx (any platform):
pipx install uv
```

**Commit `uv.lock` after the first `make install`.** Generated CI runs `uv sync --locked` (strict-lock enforcement, analogous to Node's `npm ci`) — without a committed `uv.lock`, CI fails loudly. The local `make install` recipe uses bare `uv sync` (auto-creates the lock on first run), so the typical flow is:

```bash
make install
git add uv.lock
git commit -m "lock dependencies"
```

**Escape hatch**: if uv breaks for any reason (broken release, exotic environment, corporate policy), pass `--package-manager=pip` to bootstrap and the generated project uses the classic pip+venv flow instead. Same `make` targets work; only the underlying tools differ.

### Node-TS specifics

- **First-install flow**: after `git init && git add . && git commit -m "initial bootstrap"`, run `make install`. The first `npm install` generates `package-lock.json` — commit it as a follow-up commit so CI's `npm ci` is reproducible.
- **Node version**: pinned to 24 (Active LTS as of 2026-05). Override at the renderer level if needed — `node_version` is a substitution variable that flows through the context (no `--node-version` CLI flag in PR #2; parked).
- **Hook framework**: Husky v9 (no `husky install` / `husky add` subcommands — those were removed). The `.husky/pre-commit` + `.husky/pre-push` files are checked into the repo; `.husky/_/` is gitignored runtime output.

### Go specifics

- **First-install flow**: after `git init && git add . && git commit -m "initial bootstrap"`, run `make install` (does `go mod download` + project-local `go install` of pinned gofumpt + golangci-lint into `./bin/`). **`go.sum` is generated only when you add non-stdlib dependencies** — the stdlib-only smoke project has none.
- **Go version**: pinned to 1.26 (current Active LTS as of 2026-05). Override at the renderer level if needed — `go_version` is a substitution variable; no `--go-version` CLI flag in PR #3 (parked).
- **Module path**: `github.com/{github_owner}/{github_repo}` when `--github-owner` + `--github-repo` are passed; falls back to bare `{project_name}` otherwise. Auto-derived; no separate `--module-path` flag.
- **Hook framework**: Native git hooks. `make install-hooks` runs `git config core.hooksPath hooks`. No `pre-commit` framework, no Husky. **Rollback**: `git config --unset core.hooksPath` restores the default `.git/hooks/` directory. If you had a previous `core.hooksPath` value set, `make install-hooks` prints an explicit restore command (e.g. `git config core.hooksPath "your-previous-value"`).
- **Tool versions**: gofumpt + golangci-lint pinned in Makefile vars (`GOFUMPT_VERSION`, `GOLANGCI_LINT_VERSION`). Bump in the Makefile + re-run `make install`.
- **CI cache**: `setup-go@v5` keys cache on `go.sum`. Since the smoke project has none, generated `ci.yml` ships `cache: false`; you re-enable `cache: true` once `go.sum` exists.

## GitHub setup checklist (when emitting opt-in review modes)

When bootstrapping with `--github-review=claude` or `--github-review=both-docs`, the generated project ships `.github/workflows/claude-review.yml`. That workflow needs an OAuth token to post reviews as `claude[bot]`. **Without the secret, the workflow runs but the action fails the auth step and no review is posted.**

One-time setup right after pushing the new repo to GitHub:

1. Install the Claude Code GitHub App on your account (one-time per user): https://github.com/apps/claude
2. Generate the OAuth token: `claude setup-token` (one-time per user; opens browser)
3. Add it as a repo secret via `Settings → Secrets and variables → Actions → New repository secret`:
   - Name: `CLAUDE_CODE_OAUTH_TOKEN`
   - Value: the token Claude printed

The same token value works across multiple repos (per-user, not per-repo). Generating a new token does NOT invalidate older ones.

For `--github-review=both-docs` you also need to enable Codex's GitHub auto-review per-repo via the Codex web UI — see the generated project's `docs/codex-github-review-setup.md`.

## `--restore` walkthrough

```bash
$ ./venv/bin/python bootstrap.py --apply --language python --project-name my-app --out /tmp/my-app
apply successful: wrote 18 files to /tmp/my-app
restore manifest: /var/folders/.../dev-project-setup-restore-20260515T120000Z.json
to rollback: /Users/me/skill/venv/bin/python /Users/me/skill/bootstrap.py --restore /var/folders/.../dev-project-setup-restore-20260515T120000Z.json
next steps:
  cd /tmp/my-app && make install
  make install-hooks  # registers git hooks, requires .git/

# Decided to roll back?
$ /Users/me/skill/venv/bin/python /Users/me/skill/bootstrap.py --restore /var/folders/.../dev-project-setup-restore-20260515T120000Z.json
0 files restored, 18 files removed, 0 skipped due to modification, 0 rejected for path-safety
```

## Observability (`make status`)

After bootstrap, the generated project ships a `make status` target that synthesizes recovery information for cross-session / post-compaction continuity:

- **Current branch activity** — current branch name + last 10 commits on `HEAD`
- **Recent main activity** — last 10 commits on `origin/main` → `main` → `HEAD` (fallback chain)
- **Open PRs** — `gh pr list --state open` (graceful fallback if `gh` missing/unauthed)
- **Active plan** — `PLAN_FILE=` override OR mtime-sorted `docs/plans/*.md` (README filtered, multi-plan WARN listing top-3); tails the Iteration log + Implementation log sections (fence-aware extraction skips fenced examples)
- **Active lessons** — `LESSONS.md` "Active" section (up to ~50 lines)
- **Local repo state** — `git status --short`
- **Health checks** — `command -v git gh claude codex` (inlined; never fails the target)

Run at session start, or any time the agent is uncertain whether work X is already done. The instruction is also in `CLAUDE.md` + `AGENTS.md` ("Cross-session state recovery" section).

```bash
$ cd generated-project
$ make status
── Current branch activity ──
(branch: main)
abc1234 Latest commit
...
```

Use `make status PLAN_FILE=docs/plans/<active>.md` when the mtime auto-detect might pick the wrong file.

## Tier-2 reviewer triggers

The `claude-review.yml` workflow (when emitted via `--github-review={claude,both-docs}`) auto-fires `claude[bot]` on PR open / draft→ready transitions. Re-trigger on subsequent pushes by commenting `@claude review this` on the PR.

The Codex GitHub bot (when configured via the web UI per `docs/codex-github-review-setup.md`) auto-fires on PR open / draft→ready / `@codex review` comments. **Observed reliability caveat**: in some cases the Codex bot does NOT auto-fire on `gh pr ready` (timing-dependent; cause unclear). Workaround: if Codex Tier-2 hasn't fired within ~5 min of marking a PR ready, comment `@codex review` explicitly. See BACKLOG entry "Investigate Codex GitHub bot's ready-state auto-fire reliability".

## Self-improvement loop (`LESSONS.md`)

The generated project also ships `LESSONS.md` (empty by default; the skill-repo's own ships with seed entries).

**Writable-session-only append rule**: a writable implementation session appends lessons directly after a user push-back or a Tier-1/2 finding that surfaces a new mistake-class. A read-only review session (Codex GitHub bot, `make review-plan-by-codex`, etc.) proposes lessons in its output instead — the driver triages later.

See `CLAUDE.md` / `AGENTS.md` "Self-improvement loop" section for the full protocol.

## Bootstrap-exception note (PR #1)

PR #1 of the skill itself uses Boxette's `make review-plan` (Codex direction only) for its plan-review because the skill's own bidirectional review loop is part of what PR #1 ships. From PR #2 onward the skill self-hosts the loop. The CI workflow, `claude[bot]` review, and Codex auto-review may skip on PR #1's own PR for the same bootstrap reason — the workflow files themselves are part of what PR #1 ships.

## Reference

- `SKILL.md` — invocation entry-point doc consumed by Claude Code's skill registry
- `docs/plans/2026-05-15-skill-pr1-minimal-python-bootstrap.md` — the converged plan PR #1 implements
- `BACKLOG.md` — parked decisions and follow-up triggers
