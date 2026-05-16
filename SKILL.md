# dev-project-setup

> Bootstrap a working dev workflow into Python / Node-TS / Go projects. PR #1 shipped Python; PR #2 added Node-TS (Biome + vitest + TypeScript + Husky); PR #3 adds **Go** (gofumpt + golangci-lint + native git hooks). All three v1 languages now supported.

## When to invoke

Use this skill when the user wants to spin up a new project (or an existing greenfield project with no Makefile / CI / hooks) with a sensible dev-tooling baseline:

- `make check`-equivalent CI on GitHub Actions
- pre-commit (lint+format) + pre-push (tests) git hooks
- bidirectional plan-review (`make review-plan-by-codex` / `make review-plan-by-claude`)
- coherent doc set (`AGENTS.md` / `CLAUDE.md` / `CONTRIBUTING.md` / `BACKLOG.md` / `docs/plans/`)
- optional `claude[bot]` PR review via workflow, optional Codex web-UI review setup doc

## How to invoke

Invoke via the skill repo's per-project venv (never the system Python, never the parent project's venv):

```bash
cd ~/.claude/skills/dev-project-setup
./venv/bin/python bootstrap.py [--dry-run | --diff | --apply | --restore MANIFEST] \
    --language {python,nodejs,go} \
    --project-name <slug> \
    --out <target-dir> \
    [--github-review {none,claude,both-docs}] \
    [--github-owner <owner>] \
    [--github-repo <repo>] \
    [--overwrite-existing] \
    [--enable-smoke]
```

`--project-name` must match `^[a-z][a-z0-9-]*$`.

**One-time setup:** the skill's venv lives at `~/.claude/skills/dev-project-setup/venv/`. If it doesn't exist yet, run `make install` in that dir once.

## Safety contract

- Default mode is **dry-run**. No flag means no writes.
- `--diff` prints a unified diff against any existing files at `--out`. Still no writes.
- `--apply` writes files atomically (per-file `.bootstrap-tmp` + rename) AFTER fsync'ing a JSON restore manifest to `$TMPDIR`.
- `--apply` aborts non-zero if any target file already exists, unless `--overwrite-existing` is passed (explicit consent).
- `--restore <manifest>` reverses an apply: written content goes back, created files are removed, created directories are removed (only if empty). User edits since apply are SKIPPED with a warning — never clobbered.

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

- **Python projects**: `pre-commit` framework (Python tool). `make install-hooks` runs `./venv/bin/pre-commit install` + the pre-push variant.
- **Node-TS projects**: Husky v9 + lint-staged. `make install` already arms hooks via `package.json`'s `"prepare": "husky"` script; `make install-hooks` is a defensive idempotent re-arm (e.g. for users who ran `npm install --ignore-scripts`).

```bash
cd <out>
make install        # python: venv + pip; node: npm install + arms husky
make install-hooks  # registers / re-arms git hooks (requires .git/)
```

See [docs/usage.md](docs/usage.md) for the full CLI surface and walkthroughs.
