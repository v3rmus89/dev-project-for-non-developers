# dev-project-setup

> Bootstrap a working dev workflow into Python / Node-TS / Go projects. PR #1 shipped Python; PR #2 added Node-TS (Biome + vitest + TypeScript + Husky); PR #3 added **Go** (gofumpt + golangci-lint + native git hooks); PR #6 added **uv** support for Python (greenfield default; pip-mode kept for adoption + explicit opt-out); PR #7 added **`--mode=adopt`** — per-file analyze-then-decide-with-owner UX for safely adopting the skill into existing Python projects. All three v1 languages now supported.

## When to invoke

Use this skill when the user wants to spin up a new project (or an existing greenfield project with no Makefile / CI / hooks) with a sensible dev-tooling baseline:

- `make check`-equivalent CI on GitHub Actions
- pre-commit (lint+format) + pre-push (tests) git hooks
- bidirectional plan-review (`make review-plan-by-codex` / `make review-plan-by-claude`) + Tier-1 commit review (`make review-commit-by-*`) + consistency self-check (`make review-plan-consistency-by-claude`)
- coherent doc set (`AGENTS.md` / `CLAUDE.md` / `CONTRIBUTING.md` / `BACKLOG.md` / `LESSONS.md` / `docs/plans/`)
- `make status` recovery target — synthesizes git + open PRs + active plan + active lessons for post-compaction sessions
- `LESSONS.md` append-only self-improvement log with writable-vs-read-only rule
- optional `claude[bot]` PR review via workflow, optional Codex web-UI review setup doc

## How to invoke

Invoke via the skill repo's per-project venv (never the system Python, never the parent project's venv):

```bash
cd ~/.claude/skills/dev-project-setup
./venv/bin/python bootstrap.py [--dry-run | --diff | --apply | --restore MANIFEST] \
    --language {python,nodejs,go} \
    --project-name <slug> \
    --out <target-dir> \
    [--package-manager {uv,pip}] \
    [--mode adopt] \
    [--auto-accept-recommendations] \
    [--non-interactive] \
    [--github-review {none,claude,both-docs}] \
    [--github-owner <owner>] \
    [--github-repo <repo>] \
    [--overwrite-existing] \
    [--enable-smoke]
```

`--project-name` must match `^[a-z][a-z0-9-]*$`.

`--package-manager` is **Python-only**. Default `uv` for greenfield; auto-detect for adoption (positive markers: `uv.lock`, `[tool.uv]`, `uv_build` backend > `requirements*.txt` for pip). Pass `--package-manager=pip` to opt out and stay on pip+venv.

`--mode=adopt` is an **adoption modifier of `--apply`** (NOT a fifth mode). Requires `--apply`; rejected with `--dry-run` / `--diff` / `--restore` / `--language != python` / `--overwrite-existing`. Enables per-file analyze-then-decide-with-owner UX for safe adoption into existing projects — see `docs/usage.md`'s "Adoption mode" section. For read-only inspection, use `--diff` (plain `--diff --language python` annotates the unified diff with policy recommendations).

`--auto-accept-recommendations` (with `--mode=adopt` only): auto-applies every policy with `manual_review_needed=false` without a prompt; `manual_review_needed=true` files still need a decision.

`--non-interactive` (with `--mode=adopt` only): any required prompt becomes a fail-loud exit 2. Combine with `--auto-accept-recommendations` for the CI contract: accept everything safe, fail on anything needing review.

**One-time setup:** the skill's venv lives at `~/.claude/skills/dev-project-setup/venv/`. If it doesn't exist yet, run `make install` in that dir once.

## Safety contract

- Default mode is **dry-run**. No flag means no writes.
- `--diff` prints a unified diff against any existing files at `--out`. Still no writes.
- `--apply` writes files atomically (per-file `.bootstrap-tmp` + rename) AFTER fsync'ing a JSON restore manifest to `$TMPDIR`.
- **Plain `--apply`** aborts non-zero if any target file already exists, unless `--overwrite-existing` is passed (explicit consent — nuclear escape hatch for greenfield bootstraps that drifted).
- **`--apply --mode=adopt`** uses per-file recommendations (analyze-then-decide-with-owner). Collisions are NOT a hard abort — instead the analyzer recommends a policy per file (`SKIP` / `WRITE` / `OVERWRITE` / `WRITE_NEW` / `APPEND_MERGE`) and the user decides on flagged files via stdin prompts. The default rule (Scope #5 rule h) for any unrecognized existing file is `SKIP` with manual review required — never destructive `WRITE`. **`WRITE_NEW`** writes `<path>.new` alongside the original so the user can `diff -u <path> <path>.new` before manually merging; the original is never touched. **`APPEND_MERGE`** is restricted to `.gitignore` (line-level idempotent merge).
- `--restore <manifest>` reverses an apply for both v1 (plain) and v2 (adopt-mode) manifests. v1: written content goes back, created files removed, empty created dirs removed. v2: per-policy restore matrix — `WRITE` deletes, `OVERWRITE` writes the pre-apply snapshot back, `WRITE_NEW` removes the `.new` file (original untouched throughout), `APPEND_MERGE` truncates the file to its pre-append length. User edits since apply are SKIPPED with a warning across both versions — never clobbered.

After `--apply` succeeds, the printed `to rollback:` line is a self-contained command you can re-run from anywhere to roll back.

## GitHub secret for opt-in `--github-review` modes

When the user picks `--github-review=claude` or `--github-review=both-docs`, the generated project includes `.github/workflows/claude-review.yml`. That workflow requires a `CLAUDE_CODE_OAUTH_TOKEN` repo secret on the target repo — without it, the workflow runs but the action fails auth and no review is posted.

Tell the user this is a required step right after `gh repo create` / their first push:

1. Install https://github.com/apps/claude on their account (one-time per user)
2. Run `claude setup-token` locally (one-time; opens browser)
3. Add the printed token as repo secret `CLAUDE_CODE_OAUTH_TOKEN` via `Settings → Secrets and variables → Actions`

The same token works across all their repos. The bootstrap's post-apply printout surfaces this hint when `--github-review != none`.

## Post-bootstrap hook adoption

The generated project ships a `make install-hooks` target. Bootstrap itself never installs git hooks; the user runs them in the target project. The Makefile target is identical across languages; the underlying hook framework differs:

- **Python projects (uv mode, default for greenfield)**: `pre-commit` framework, invoked via `uv run pre-commit`. `make install` runs `uv sync` (creates `.venv/` + `uv.lock`). **Commit `uv.lock`** after first `make install` — generated CI runs `uv sync --locked` (strict-lock enforcement, like `npm ci`) and will fail if the lockfile isn't committed.
- **Python projects (pip mode)**: `pre-commit` framework, invoked via `./venv/bin/pre-commit`. `make install` creates a per-project `venv/` + pip-installs deps from `requirements-dev.txt`.
- **Node-TS projects**: Husky v9 + lint-staged. `make install` already arms hooks via `package.json`'s `"prepare": "husky"` script; `make install-hooks` is a defensive idempotent re-arm (e.g. for users who ran `npm install --ignore-scripts`).

```bash
cd <out>
make install        # python+uv: uv sync (.venv/ + uv.lock); python+pip: venv + pip; node: npm install + arms husky
make install-hooks  # registers / re-arms git hooks (requires .git/)
```

See [docs/usage.md](docs/usage.md) for the full CLI surface and walkthroughs.
