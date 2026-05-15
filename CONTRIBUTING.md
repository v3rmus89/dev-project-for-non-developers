# Contributing to dev-project-setup

The per-change workflow for the skill repo itself.

---

## One-time setup (fresh clone)

```bash
cd /path/to/dev-project-for-non-developers
make install        # creates venv if missing, installs deps
make install-hooks  # registers pre-commit + pre-push git hooks (requires .git/)
make doctor         # verifies local prereqs are present
```

Prereqs are documented in [docs/usage.md](docs/usage.md) — `python3.12`,
`make`, `git`, network access to PyPI; optional `claude` / `codex` CLIs
for the local review targets.

### Codex CLI (required for `make review-plan-by-codex`)

```bash
# Install (see https://developers.openai.com/codex):
brew install --cask codex     # or per the official docs

# Log in (one-time; opens browser):
codex login

# Verify:
command -v codex && codex --version
```

### Claude CLI (required for `make review-plan-by-claude`)

```bash
# Install:
npm install -g @anthropic-ai/claude-code   # or per the official docs

# Log in:
claude login

# Verify:
command -v claude && claude --version
```

If either CLI is unavailable, the corresponding `make review-plan-by-*`
target exits cleanly with an install hint.

---

## Per-change checklist

1. **Plan**: substantive change → `docs/plans/YYYY-MM-DD-<slug>.md` plus
   the bidirectional review loop. Trivial change → skip planning.

2. **Workspace check**:
   ```bash
   git status --short
   ```

3. **Sync**:
   ```bash
   git pull --ff-only
   ```

4. **Verify baseline**:
   ```bash
   make check
   ```

5. **Branch**:
   ```bash
   git checkout -b feat/my-thing
   ```

6. **Implement**. Tests for new helpers, defensive cases for new public APIs.

7. **Auto-fix + verify**:
   ```bash
   make format
   make check
   ```

8. **Commit focused units**:
   - One logical change per commit. Imperative title, body explaining "why".
   - **Do NOT** `git add .` — pick files explicitly.

9. **Push** and open a draft PR:
   ```bash
   git push -u origin <branch>
   gh pr create --draft
   ```

10. **Watch CI** — merge only when green. PR #1 is the bootstrap exception:
    its workflow files are part of what it ships, so CI may skip on PR #1
    itself. From PR #2 onward, CI runs.

---

## Branch naming

```
feat/<thing>
fix/<thing>
docs/<thing>
refactor/<thing>
```

---

## Emergency override

`git push --no-verify` skips the pre-push pytest hook. Use only in a real
emergency. Add a note in the commit message explaining why.

Routine "tests are slow / I'll fix it later" is not legitimate use.

---

## Skill repo specifics

When editing the skill itself, mind these invariants:

- `bootstrap.py` is Python 3.6-compatible. The shim runs version + jinja2
  checks BEFORE importing 3.12-syntax modules in `bootstrap_lib/`.
- `bootstrap_lib/_flags.py` is the single source of truth for argparse.
  Don't hand-mirror flags in `bootstrap.py`.
- Path-safety runs at TWO layers (renderer + CLI). Both must remain.
- The "Triaging review findings" rule is byte-identical across
  `shared/CLAUDE.md.tmpl` / `shared/AGENTS.md.tmpl` /
  `shared/docs-plans-README.md.tmpl` AND the dogfood `CLAUDE.md` /
  `AGENTS.md`. Drift fails `tests/test_dogfood_doc_sanity.py`.
- Five selftest overlap checks (`.editorconfig`,
  `.github/workflows/claude-review.yml`,
  `.github/pull_request_template.md`, `docs/plans/README.md`, and the
  Makefile review-section block) diff rendered templates against the
  committed dogfood copies. If you change a selftested template, the
  dogfood file must update in lockstep — and vice versa.
