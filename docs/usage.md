# Using the `dev-project-setup` skill

## Local prerequisites

Before running `make install` or invoking the skill, ensure these are on PATH:

- `make` — POSIX `make`. BSD make on macOS works; GNU make works on Linux. (Hard prereq: you can't `make doctor` to diagnose missing `make`.)
- `python3.12` — required. `python3` on macOS may be 3.9.x; the skill repo's `Makefile` invokes `python3.12 -m venv` explicitly.
- venv support — `python3.12 -m venv` must work. On Linux you may need `apt install python3.12-venv`.
- `pip` + network access to PyPI — for installing pinned `jinja2`, `pyyaml`, `pytest`, `ruff`, `pre-commit`.
- `git` — required by the GENERATED project's `make install-hooks` (runs `pre-commit install`, guarded by `test -d .git`).

Optional:

- `claude` CLI — only for the **local** `make review-plan-by-claude` target. Not needed for `make check` or the GitHub Actions workflow.
- `codex` CLI — only for the **local** `make review-plan-by-codex` target. Same scoping as above.

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

### Render/apply args (required when not in `--restore` mode)

| Flag | Description |
|---|---|
| `--language python` | target language. PR #1 supports `python` only |
| `--project-name <slug>` | must match `^[a-z][a-z0-9-]*$` (lowercase ASCII + digits + hyphens, leading letter, no path separators) |
| `--out <dir>` | target directory; created ONLY during `--apply` |
| `--github-review {none,claude,both-docs}` | default `none` — no Claude workflow / OAuth secret dependency unless explicitly opted in |
| `--github-owner <owner>` | required when `--github-review != none` |
| `--github-repo <repo>` | required when `--github-review != none` |
| `--overwrite-existing` | required during `--apply` if any target file already exists |
| `--enable-smoke` | also emit `docs/SMOKE.md` skeleton (default: omit) |

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

## Post-bootstrap hook adoption

The bootstrap process itself never installs git hooks. To wire up pre-commit + pre-push hooks in the generated project, the user runs:

```bash
cd <out>
make install         # creates per-project venv + installs dev deps
make install-hooks   # registers hooks via the target project's venv/bin/pre-commit
```

`make install-hooks` is a target IN THE GENERATED PROJECT, NOT a bootstrap CLI flag. Hooks live in the target project's `.git/hooks/` and reference the target project's `./venv/bin/python` — they survive moves or rebuilds of the skill repo.

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

## Bootstrap-exception note (PR #1)

PR #1 of the skill itself uses Boxette's `make review-plan` (Codex direction only) for its plan-review because the skill's own bidirectional review loop is part of what PR #1 ships. From PR #2 onward the skill self-hosts the loop. The CI workflow, `claude[bot]` review, and Codex auto-review may skip on PR #1's own PR for the same bootstrap reason — the workflow files themselves are part of what PR #1 ships.

## Reference

- `SKILL.md` — invocation entry-point doc consumed by Claude Code's skill registry
- `docs/plans/2026-05-15-skill-pr1-minimal-python-bootstrap.md` — the converged plan PR #1 implements
- `BACKLOG.md` — parked decisions and follow-up triggers
