# dev-project-setup

> Bootstrap a working dev workflow into Python / Node-TS / Go projects. PR #1 ships **Python only**.

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
    --language python \
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

## Post-bootstrap hook adoption

The generated project ships a `make install-hooks` target. Bootstrap itself never installs git hooks; the user runs them in the target project's venv:

```bash
cd <out>
make install         # creates per-project venv + installs dev deps
make install-hooks   # registers pre-commit + pre-push hooks (requires .git/)
```

See [docs/usage.md](docs/usage.md) for the full CLI surface and walkthroughs.
