# Skill PR #1 — minimal-working Python bootstrap with bidirectional plan-review baked in

> Per-PR expansion of subsystems A–F from the merged skill plan ([`Boxette docs/plans/2026-05-15-dev-project-setup-skill.md`](https://github.com/v3rmus89/boxette-tgbot/blob/main/docs/plans/2026-05-15-dev-project-setup-skill.md)). This plan is concrete file-and-test detail; architectural decisions already settled in the merged plan are referenced, not re-litigated.

## Context

The merged skill plan partitions Skill PR #1 into six subsystems with per-subsystem acceptance gates so reviewers can reject a single subsystem without blocking the others. What the merged plan does NOT do is enumerate the concrete files, test cases, and per-test assertions an implementing session needs. This plan fills that gap for the `dev-project-for-non-developers` repo (skill name: `dev-project-setup`; repo name and skill name intentionally differ per the README — repo audience-focused, skill action-focused).

PR #1 is also the **bootstrap exception**: before this plan was added, the new repo contained only `README.md` + `.gitignore` (this plan file is the first substantive content; it lands together with the code per the bootstrap-exception pattern). The plan-review loop, the `make check` gate, and the AI-reviewer workflows are PART of what PR #1 ships, so they cannot gate PR #1 itself. PR #1's own plan is reviewed using Boxette's existing `make review-plan` (Codex direction only). From Skill PR #2 onward the loop runs against the skill's own self-hosted bidirectional targets.

PR #1 lands plan + code in a **single PR** (the bootstrap-exception pattern explicitly documented in `docs/plans/README.md` of Boxette and the merged plan's Build sequence).

## Scope

PR #1 commits the following files to `dev-project-for-non-developers`. Three buckets — skill code, templates, and the skill repo's own dogfooded dev workflow.

### Bucket 1: Skill code

| File | Purpose |
|---|---|
| `SKILL.md` | Skill metadata + entry-point invocation guidance (so `~/.claude/skills/dev-project-setup/` is discoverable by Claude Code) |
| `bootstrap.py` | CLI entry; thin wrapper that imports `bootstrap_lib.cli` and dispatches |
| `bootstrap_lib/__init__.py` | Package marker |
| `bootstrap_lib/cli.py` | `argparse` definitions; full flag list (closes Codex iter-10 finding #5 + iter-17 finding #1 — `--install-hooks` REMOVED per iter-16, this row is the authoritative public CLI): `--dry-run` (default), `--diff`, `--apply`, `--restore <manifest>`, `--language python`, `--project-name <slug>`, `--out <dir>`, `--github-review={none,claude,both-docs}`, `--github-owner <owner>`, `--github-repo <repo>`, `--overwrite-existing`, `--enable-smoke`. `docs/usage.md` documents every flag; `tests/test_bootstrap_cli.py` asserts each flag appears in `--help` output |
| `bootstrap_lib/detect.py` | Greenfield vs existing-project detection; collision listing |
| `bootstrap_lib/manifest.py` | Restore manifest writer/reader; per-file SHA-256 + content snapshot; JSON serialisation at `<tempfile.gettempdir()>/dev-project-setup-restore-<ISO8601>.json` (honours `TMPDIR`/`TEMP`/`TMP` env vars — closes Codex iter-9 finding #3; aligns with Architecture section's manifest-path spec) |
| `bootstrap_lib/render.py` | Jinja2 environment, template loading, mode-conditional emission for `--github-review` |
| `bootstrap_lib/io.py` | Atomic write (`<target>.bootstrap-tmp` + `os.rename`); apply phase never removes files; SIGTERM-safe cleanup |
| `bootstrap_lib/paths.py` | (Codex iter-7 finding #4 + iter-8 finding #2 + iter-13 finding #3) Shared `validate_target_path(target_root, rel_path)` — path-safety boundary used by both render/apply and restore. Rejects absolute paths, `..` traversal, symlink escapes. Called from inside `render.render_all` AND from the CLI apply-planning layer (two-tier defense). |
| `scripts/run-with-clean-env.py` | Prefix-aware env-var scrubber for the **skill repo's own** Makefile (Bucket 3). Make's `env -u` is exact-name-only; this helper rebuilds `os.environ` excluding any key matching `CLAUDE_CODE_` / `CODEX_` prefixes, then `os.execvp`s into the CLI. **Committed mode 0755** (closes Codex iter-5 finding #4 — the skill repo's review targets invoke this directly as an executable; missing executable bit would make the targets dead-on-arrival in the skill repo). The skill emits a **copy** of this script into each generated project via `shared/scripts-run-with-clean-env.py.tmpl` (see Bucket 2) so `Makefile.review.tmpl` can reference it as a path relative to the bootstrapped project, not the skill repo. |

### Bucket 2: Templates

`languages/python/` (10 files):
- `Makefile.tmpl` — `help / install / install-hooks / test / lint / format / check / run` targets (closes Codex iter-11 finding #2 — `make help` was an acceptance requirement but `help` wasn't explicitly listed. Convention: every target documented with `## description` after the recipe header; `.PHONY: help install install-hooks ...`; `help` recipe uses `grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST)` to print the list). **`restart` REMOVED from PR #1's generated Makefile** per Codex iter-18 finding #3 — it was a Boxette-ism (bot restart) with no generic meaning, and the prior "only when run-able" hedge was contradicted because PR #1 always emits `src/main.py`. `install` creates `venv/` (per-project venv at the project root, NOT global) if absent and installs `requirements-dev.txt` into it; `test`/`lint`/`format`/`check` all invoke tools via `venv/bin/...` so a fresh clone produces the same toolchain versions on every machine — closes Codex iter-3 finding #2 (smoke walk doesn't depend on parent test env's `ruff`/`pytest`). **`install-hooks` is separate (Codex iter-8 finding #3)**: generated `make install` does NOT touch `.git/hooks/` — it would fail in non-git tempdirs (the smoke test runs in a non-git tempdir) and conflicts with the `--install-hooks` bootstrap flag's explicit-opt-in semantics. Generated `make install-hooks` runs `./venv/bin/pre-commit install && ./venv/bin/pre-commit install --hook-type pre-push`, guarded with `@test -d .git || { echo "skipping: not a git repo"; exit 0; }`. Generated `make install` prints "next step: `make install-hooks` if this is a git repo" after success.
- `.pre-commit-config.yaml.tmpl` — ruff on commit + pytest on push (per-language hook config per merged plan's language table)
- `pyproject.toml.tmpl` — minimal Python project metadata; ruff config inline OR via `ruff.toml.tmpl`
- `requirements-dev.txt.tmpl` — pinned `ruff==0.15.12`, `pre-commit>=3.7,<5`, `pytest>=8.0,<9` (concrete versions match Boxette's `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/requirements-dev.txt` — same toolchain on every generated project; closes Codex iter-6 finding #4)
- `ruff.toml.tmpl` — lint + format config
- `pytest.ini.tmpl` — testpaths, addopts
- `.gitignore.tmpl` — Python-specific defaults (`venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`)
- `ci.yml.tmpl` — `.github/workflows/ci.yml` for the generated project; sequence is `actions/checkout@v4 → actions/setup-python@v5 (python_version from substitution context) → make install → make check` (closes Codex iter-4 finding #2 — `make check` alone would assume `ruff`/`pytest` already installed; CI on a fresh runner won't have them)
- `tests-test_smoke.py.tmpl` — one trivial passing test so `pytest` has something to find
- `src-main.py.tmpl` — one trivial module so `make run` has a callable target

`shared/` (12 files):
- `AGENTS.md.tmpl` — derived from Boxette's `AGENTS.md`, retains "Plan Review Guidance" + per-language Codex review guidance, strips Boxette-specific bot/API sections
- `CLAUDE.md.tmpl` — derived from Boxette's `CLAUDE.md`, retains Commands table + Plan review loop + focused-commits guidance, strips bot-specific restart rule + API quirks + PINFL section
- `CONTRIBUTING.md.tmpl` — derived from Boxette's `CONTRIBUTING.md`, retains per-change workflow + one-time setup + Codex CLI + Claude CLI install/login
- `BACKLOG.md.tmpl` — derived from Boxette's `BACKLOG.md`; ships pre-populated with `--ephemeral` (Codex) and `--no-session-persistence` (Claude) parked entries, plus a "Claude/Codex CLI flag drift" entry whose trigger is `make preflight-review-tooling` failing, plus a "Retroactively add triage rule to Boxette's plan-review docs" entry (trigger: after PR #1 lands)
- `pull_request_template.md.tmpl` — derived from Boxette's `.github/pull_request_template.md`; reviewer checklist sections are `{% if %}`-gated by `--github-review` mode
- `claude-review.yml.tmpl` — derived from Boxette's `.github/workflows/claude-review.yml`
- `docs-plans-README.md.tmpl` → renders to `docs/plans/README.md`; same workflow as Boxette's plus the bidirectional review filename convention (`-by-codex-` / `-by-claude-`) and the bootstrap-exception clause
- `docs-SMOKE.md.tmpl` → renders to `docs/SMOKE.md`; only emitted when `--enable-smoke` flag is set (default: omit; PR #1 wires the flag but the template content is a minimal placeholder — projects fill in their own)
- `docs-codex-github-review-setup.md.tmpl` → renders to `docs/codex-github-review-setup.md`; only emitted in `--github-review=both-docs` mode
- `editorconfig.tmpl` → renders to `.editorconfig`
- `Makefile.review.tmpl` — Jinja-rendered chunk containing `review-plan-by-codex`, `review-plan-by-claude`, and `preflight-review-tooling` targets. Included into the per-language `Makefile.tmpl` via Jinja `{% include 'Makefile.review.tmpl' %}` so each language Makefile gets the same three targets without duplication.
- `scripts-run-with-clean-env.py.tmpl` → renders to `scripts/run-with-clean-env.py` in the generated project, mode 0755 (post-write `os.chmod(target, 0o755)`). Same content as the skill repo's own `scripts/run-with-clean-env.py`. The Makefile review targets reference it as `$(CURDIR)/scripts/run-with-clean-env.py` — relative to the bootstrapped project's root, not the skill repo. Without this emission the generated project's review targets would be dead-on-arrival (closes Codex iter-1 finding #1).

### Bucket 3: Skill repo's own dev workflow (dogfood)

Because the skill cannot bootstrap itself (chicken-and-egg), PR #1 ships hand-written first-class copies of the workflow at the skill repo's root. These match what the skill produces, but are NOT generated from templates:

- `Makefile` — `install / test / lint / format / check`, plus `review-plan-by-codex` / `review-plan-by-claude` / `preflight-review-tooling` (so the skill repo's own plans use the skill's own targets from PR #2 onward)
- `pyproject.toml` — `dev-project-setup` package + dev-deps
- `requirements-dev.txt` — pinned `ruff`, `pytest`, `pre-commit`, `jinja2`, `pyyaml`
- `ruff.toml`, `pytest.ini`
- `.pre-commit-config.yaml`
- `.github/workflows/ci.yml` — sequence `actions/checkout@v4 → actions/setup-python@v5 (3.12) → make install → make check` on push and PR (same sequence the skill produces in generated projects)
- `.github/workflows/claude-review.yml` — same as the template ships
- `.github/pull_request_template.md` — same surface as the template ships (mode = `claude` for this repo)
- `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `BACKLOG.md` — hand-written for the skill repo
- `README.md` — updated as part of PR #1 (closes Codex iter-17 finding #3): edit the "Adoption safety contract" line that currently mentions `--install-hooks` opt-in. Replace with: "The merged plan originally included `--install-hooks` as a bootstrap-side opt-in; PR #1 ships hook adoption via the generated project's `make install-hooks` target instead (scoped to the target project's venv). Direct `--install-hooks` flag is parked as follow-up work." Keeps the README's repo-public framing aligned with what PR #1 actually ships
- `docs/plans/README.md` — the workflow doc
- `docs/plans/2026-05-15-skill-pr1-minimal-python-bootstrap.md` — **this plan file itself** (Codex iter-4 finding #5): PR #1 lands plan + code together (bootstrap-exception pattern documented at the top of this file). The plan remains committed permanently in `docs/plans/` after PR #1 ships — it's the institutional record of why these design decisions were made (per Boxette's `docs/plans/README.md` rationale: "Plans become institutional memory").
- `docs/usage.md` — skill invocation guide (closes Codex iter-3 finding #6 + iter-17 finding #1): when to use the skill, full CLI surface (all flags: `--overwrite-existing`, `--github-review`, `--github-owner`, `--github-repo`, `--enable-smoke` — NO `--install-hooks`, that was removed in iter-16), the safety contract (dry-run default → diff → apply → restore), `--restore <manifest>` walkthrough with example output, the bootstrap-exception note for PR #1, and the **post-bootstrap hook adoption flow**: `cd <out> && make install && make install-hooks` (the latter target only exists in the GENERATED project's Makefile, not in the bootstrap CLI). Hand-written for PR #1; lives at the skill repo root, NOT generated into bootstrapped projects. `docs/upgrading.md` and `docs/design-notes.md` from the merged plan's directory tree are parked for follow-up.

**Selftest drift detection (narrow, PR #1 in-scope)** — closes Codex iter-1 finding #5. Two sources of truth exist on day one (templates + Bucket 3 dogfood files); without any drift check reviewers can't tell whether the hand-written copies actually match the generated output. PR #1 ships `tests/test_selftest_overlap.py` covering a **narrow, deterministic** subset of files where the substitution context is fully knowable:

| Skill-repo dogfood file | Template rendered against | Why this file is in scope |
|---|---|---|
| `.editorconfig` | `shared/editorconfig.tmpl` | No substitution vars; pure copy |
| `.github/workflows/claude-review.yml` | `shared/claude-review.yml.tmpl` rendered with `github_owner=v3rmus89`, `github_repo=dev-project-for-non-developers`, `github_review_mode=claude` | Substitutions are static repo metadata |
| `.github/pull_request_template.md` | `shared/pull_request_template.md.tmpl` rendered with `github_review_mode=claude` | Same |
| `docs/plans/README.md` | `shared/docs-plans-README.md.tmpl` rendered with `project_name=dev-project-setup` | Same |
| **Review-section block of `Makefile`** (lines from `# ── Plan-review automation` to end of `preflight-review-tooling`) | `shared/Makefile.review.tmpl` rendered with the skill repo's context | (Codex iter-5 finding #5) PR #2 onward will use the skill's own targets to self-host the bidirectional review loop; if the dogfood Makefile's review section drifts from the template, PR #2 may use a different workflow than generated projects. Extract just the review-section lines from the Makefile (a sed range or a sentinel-comment region) and diff against the rendered template. |

Test logic: for each row, render the template with the documented context, then `assertEqual(rendered, Path(dogfood_file).read_bytes())` (or, for the Makefile review-section row, `assertEqual(rendered, extracted_review_block)`). If they differ, the test prints a unified diff and fails — forcing the maintainer to either re-sync the dogfood file or update the template.

**Out of selftest scope** (parked for a follow-up PR): `Makefile` (the dogfood Makefile includes `shared/Makefile.review.tmpl` plus language-specific targets — diffing requires assembling the full Makefile from fragments, more complex than PR #1 can absorb), `pyproject.toml` / `requirements-dev.txt` (the skill repo's own deps are a superset of what a generated Python project gets — `jinja2`, `pyyaml` are skill-only), `AGENTS.md` / `CLAUDE.md` / `CONTRIBUTING.md` (these have skill-repo-specific overlays).

**Dogfood-docs Boxette-isms scan (Codex iter-10 finding #3)**: even though the overlay docs aren't byte-for-byte selftested, PR #1 ships `tests/test_dogfood_doc_sanity.py` that runs the same no-Boxette-isms scan from Subsystem C tests against the committed `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, and `.github/pull_request_template.md` at the skill repo root. Forbidden terms: `Boxette`, `Telegram`, `bot/`, `PINFL`, `customs`, `signup`, `payment`, `boxette.db`, `i18n/ru.json`. Allowlist: this plan file (`docs/plans/2026-05-15-skill-pr1-minimal-python-bootstrap.md`) AND any file under `docs/plans/` is allowed to reference Boxette because the plans cite Boxette as the source-of-truth for the patterns — those references are historical attribution, not active guidance.

## Local prerequisites (Codex iter-16 finding #3)

PR #1's local quality gate has unstated machine dependencies that maintainers and CI environments must have BEFORE running `make install` / `make check`. Documented in `docs/usage.md`:

- `make` — POSIX `make` (BSD make on macOS is fine; GNU make works too)
- `python3.12` — the skill (and bootstrap shim's version check) requires 3.12+. `python3` may be 3.9.x on macOS; the skill repo's `make install` invokes `python3.12 -m venv` explicitly.
- venv support — `python3.12 -m venv` must work without extra `apt install python3.12-venv` on Linux (or equivalent for the host distro)
- `pip` + network access to PyPI — for installing pinned `jinja2`, `pyyaml`, `pytest`, `ruff`, `pre-commit`
- `git` — required for the generated project's `make install-hooks` target (runs `pre-commit install`; guarded by `test -d .git`)
- Optional: `claude` CLI, `codex` CLI — only for `make preflight-review-tooling` and the manual local review targets

`make doctor` Makefile target (new in PR #1): runs `command -v <tool>` for each prereq and prints a summary. Non-zero exit on missing core prereqs; advisory output for the optional ones. Document this target in the README so first-time users can self-diagnose.

## Deployment / invocation contract

(Closes Codex iter-9 finding #2 — `~/.claude/skills/dev-project-setup/` as the discoverable path doesn't say HOW the skill is invoked or which interpreter resolves its runtime deps.)

PR #1 documents a single supported invocation pattern. `SKILL.md` instructs Claude Code to invoke the skill via the repo-local venv:

```
cd ~/.claude/skills/dev-project-setup
./venv/bin/python bootstrap.py --apply --language python --project-name <slug> --out <dir>
```

This means:
- Users (or Claude Code following `SKILL.md`) MUST run `make install` once after first cloning / symlinking the skill repo — that creates `venv/` and installs `requirements-dev.txt` (which includes `jinja2`, `pyyaml`, `pre-commit` — all runtime deps, not just dev deps).
- `requirements-dev.txt` is a misnomer for some entries (`jinja2`, `pyyaml`, `pre-commit` are runtime); a follow-up PR can split into `requirements.txt` + `requirements-dev.txt`. PR #1 ships them in one file with a comment marking which are runtime vs dev to keep scope tight.
- Bootstrap's only runtime dep is `jinja2` (iter-16/iter-17 reaffirmed: `--install-hooks` REMOVED, so bootstrap process never touches `pre_commit`). On missing `jinja2`, bootstrap exits 2 with `"missing dep: re-run 'make install' in <skill_root>"` (uses absolute resolved skill root for the hint, mirroring iter-8's rollback fix). The generated project's `make install-hooks` target is where `pre_commit` runs locally — not via the bootstrap process.
- A console script (`pip install -e .` + `entry_points`) is parked as a follow-up — PR #1 ships only the `./venv/bin/python bootstrap.py` path so the deployment surface is minimal.

**`bootstrap.py` is a Python-3.6-compatible shim** (closes Codex iter-10 finding #1 — invoking a 3.12-syntax module under `python3` 3.9.6 would fail with SyntaxError before our dependency-check ran). The shim contains only ASCII Python compatible with 3.6+. **Canonical check order** (originally closed Codex iter-12 finding #3 — the historical ambiguity was between competing missing-dep paths for `--apply --install-hooks`; iter-16 removed that flag entirely, so the order now is simpler but the canonical-order discipline still holds for `jinja2` and version checks):

1. If `-h` or `--help` in `sys.argv[1:]`, dispatch directly to argparse `--help` WITHOUT importing `jinja2` (Codex iter-12 finding #4 — `--help` is a no-deps cold path; lets users discover flags before running `make install`). **Shim and cli.py share flag metadata via `bootstrap_lib/_flags.py`** (closes Codex iter-16 finding #2 — a hand-mirrored second argparse would silently drift; the shared module is the single source of truth). `bootstrap_lib/_flags.py` is Python-3.6 compatible (no third-party imports, no type hints requiring 3.10+, just plain data: `FLAGS = [{"name": "--language", "choices": ["python"], "required_in_mode": "render_apply", "help": "..."}, ...]`). Both the shim's `argparse.ArgumentParser` setup and `cli.py`'s parser consume this metadata. New `test_shim_cli_help_consistency`: invoke shim `--help` (under a venv WITHOUT jinja2) and full-cli `--help` (with deps installed); diff the help output and assert byte-equal (modulo prog-name).
2. Check `sys.version_info >= (3, 12)`; if not, exit 2 with "this skill requires Python 3.12+; you have <version>. Re-run via `./venv/bin/python bootstrap.py ...` after `make install`."
3. Try `import jinja2`; on ImportError exit 2 with "missing dep `jinja2`: re-run 'make install' in <skill_root>".
4. Import `from bootstrap_lib.cli import main` and call `main(argv)`. CLI then:
   - Validates `--project-name` slug
   - Validates `--github-owner` / `--github-repo` are present when `--github-review != none`
   - Proceeds with render/apply/etc.

Since `--install-hooks` was removed from PR #1's CLI surface (Codex iter-16 finding #1), the shim no longer needs to import `pre_commit`. Bootstrap's only runtime dep is `jinja2`. `pre-commit` is still pinned in `requirements-dev.txt` because the GENERATED `make install-hooks` target needs it locally — but the bootstrap process itself doesn't call into it.

This order is asserted by `tests/test_canonical_check_order.py`: 4 subtests (help-no-deps / wrong-Python / missing-jinja2 / happy path) — count revised per iter-16 since the `missing-pre_commit` and `non-git` branches moved out of the bootstrap process and into the generated `make install-hooks` (where they're handled by the Makefile's `test -d .git` guard).

**Acceptance for deployment contract**: `tests/test_deployed_invocation.py`:
- (a) Happy path: `./venv/bin/python <abs-bootstrap.py> --apply ...` from a cwd OTHER than the skill repo; assert success.
- (b) Hermetic missing-dep test: create a temp venv with `python3.12 -m venv <tmpvenv>` (NOT installing requirements-dev.txt), then run `<tmpvenv>/bin/python <abs-bootstrap.py> --apply ...`; assert exit 2 with "missing dep: re-run 'make install'" — proves the shim catches `jinja2` absence deterministically. Closes Codex iter-10 finding #1: doesn't depend on whatever `jinja2` happens to exist in the parent test env or in system `python3`.
- (c) Hermetic wrong-interpreter test: `python3.9` (or whatever happens to be `python3` on the test machine — skipped if `python3.9` not available) running the shim; assert exit 2 with "requires Python 3.12+". Proves the version check fires before the syntax errors in `bootstrap_lib/*.py` could even be hit.

## Architecture

Mirrors the merged plan's directory tree, narrowed to the PR #1 subset (no `languages/nodejs/`, no `languages/go/`). Pinned implementation choices:

- **Python**: 3.12+ (matches Boxette + supports `str | None` union syntax)
- **Templating**: Jinja2 with `{% raw %}…{% endraw %}` for verbatim brace-heavy blocks (Makefile recipe lines, GitHub Actions `${{ }}` references, JSON examples)
- **Substitution variables**: `project_name`, `language`, `python_version`, `enable_smoke`, `github_owner`, `github_repo`, `github_review_mode`. **PR #1 hardcodes `python_version = "3.12"`** (closes Codex iter-18 finding #4) — set in `bootstrap_lib/cli.py` before the render call; no `--python-version` CLI flag in PR #1. The variable still flows through the render context so future PRs can override it. `tests/test_python_templates.py` asserts the rendered `ci.yml` contains `python-version: '3.12'`.
- **Restore manifest**: JSON at `<tempfile.gettempdir()>/dev-project-setup-restore-<ISO8601-timestamp>.json` — uses Python's `tempfile.gettempdir()` (honours `TMPDIR`/`TEMP`/`TMP` env vars) rather than hard-coded `/tmp/`. Closes Codex iter-8 finding #4 — tests can inject an isolated `TMPDIR` to assert manifest absence without false positives from shared `/tmp/`. Top-level fields `{"created_at": ..., "target_root": ..., "github_review_mode": str, "entries": [...], "created_directories": [str, ...]}`. (`install_hooks: bool` field REMOVED per iter-17 finding #1 — `--install-hooks` was removed from the bootstrap CLI in iter-16; the manifest no longer needs to record it since bootstrap never installs hooks. Restore output also no longer prints the manual-uninstall hint, since there are no hooks to uninstall from a bootstrap-induced state.) **Created-directory tracking (Codex iter-12 finding #1)**: `created_directories` lists every directory that apply mkdir'd (e.g. `.github/workflows`, `docs/plans`, `scripts`, `tests`, `src`), in creation order. Restore removes them in reverse-depth order, only if empty AND only if their resolved path is within `target_root` (path-safety). Pre-existing directories are NOT recorded and NOT touched by restore. **File-mode tracking (Codex iter-12 finding #2 + iter-15 finding #3)**: each entry has `mode_before: int|null` and `mode_after: int`. **JSON encoding**: stored as **decimal integers** (JSON has no octal literal — `0o644` is Python syntax only; `json.dump(0o644)` writes `420`). Implementer-facing convention: Python code always uses octal literals (`0o644`, `0o755`) and lets `json.dump` write decimal; on load, `int` values are passed directly to `os.chmod` (which accepts decimal or octal equivalently). Tests in `test_manifest.py` include a round-trip assertion: write a manifest with `mode_after = 0o755`, reload it, assert `loaded.entries[0].mode_after == 0o755` (equality holds because both are the same int value `493` decimal). Apply calls `os.chmod(target, mode_after)` after the atomic write. Restore for overwritten files writes `content_before_b64` AND `os.chmod(target, mode_before)`. Each entry now: `{"path": str (relative to target_root), "existed_before": bool, "sha256_before": str|null, "content_before_b64": str|null, "mode_before": int|null, "action_planned": "create"|"overwrite", "sha256_after": str, "mode_after": int}` (all ints decimal in serialized JSON).
- **Crash-safe manifest durability** (closes Codex iter-2 finding #2): both `sha256_before` (recorded by inspecting the pre-apply tree) AND `sha256_after` (computed deterministically from the rendered output bytes — Jinja2 is deterministic for a given context) are **computed during the pre-apply rendering phase**, NOT after each write. The complete manifest is written and `fsync`'d to disk BEFORE the first `os.rename` runs. This means a SIGTERM mid-apply can never leave the manifest with `null` `sha256_after` values for files that were already created — the hash was always in the manifest.
- **Conservative restore decision table** (closes Codex iter-13 finding #1 — earlier wording had a contradiction where "neither hash matches" was "write back" but `sha256_after` mismatch was also "skip"; safer to skip in every ambiguous case):

| File status | current SHA-256 | Restore action |
|---|---|---|
| existed_before=true (overwritten) | `== sha256_after` | Write `content_before_b64` back + chmod `mode_before`. Apply succeeded; rollback is safe. |
| existed_before=true (overwritten) | `== sha256_before` | No-op. Apply was interrupted before writing this file; current state IS the pre-apply state. |
| existed_before=true (overwritten) | neither (file present, different content) | SKIP with warning "user edit or partial write detected; left in place". Conservative — never clobbers user edits. |
| existed_before=true (overwritten) | **file missing** | SKIP with warning "file missing; left absent (user deletion or interrupted apply — restore is conservative)". Closes Codex iter-20 P1 — a missing overwritten file matches neither sha256_after nor sha256_before, so the conservative rule says skip rather than write the pre-apply content back; otherwise restore would undo a user deletion. The interrupted-apply edge case is the price of the conservative property. |
| existed_before=false (created) | `== sha256_after` | `os.remove(target)` (apply succeeded; rollback removes the new file). |
| existed_before=false (created) | file missing | No-op. Apply was interrupted before creating this file. |
| existed_before=false (created) | neither (some other content) | SKIP with warning. User edit detected. |

The SIGTERM test (`tests/test_sigterm_mid_apply.py`) is extended to assert byte-identical rollback after restore, not just absence of `.bootstrap-tmp` artifacts. `test_restore.py` subtest (j) extended to cover the partial-overwrite-with-user-edit case explicitly.
- **Atomic writes**: `<target>.bootstrap-tmp` followed by `os.rename` (POSIX atomic on same filesystem); `atexit` + signal handler removes any stale `.bootstrap-tmp` artifacts on SIGTERM/SIGINT
- **Apply-phase no-removal guarantee**: `--apply` never `os.remove`s a target file — it only creates new files or overwrites existing ones. `--restore <manifest>` is the ONE path that may delete, and it deletes only entries where the manifest recorded `existed_before=false` (i.e. files the apply phase created). Restore **refuses** to touch any file not listed in the manifest. This split closes Codex iter-1 finding #2 — the previous "never `os.remove`" wording contradicted the restore-byte-identical acceptance test.

  Restore semantics in full:
  - Manifest schema: see Architecture section for the authoritative field list (Codex iter-14 finding #4 — single source of truth). Entry fields include `path`, `existed_before`, `sha256_before`, `content_before_b64`, `mode_before`, `action_planned`, `sha256_after`, `mode_after`. Top-level fields include `entries[]` and `created_directories[]`.
  - For each entry: **safety check applies to BOTH overwritten and created files** (closes Codex iter-4 finding #1 — symmetric protection): restore recomputes current SHA-256, compares against `sha256_after`. If match → action proceeds (write `content_before_b64` back for overwritten, `os.remove` for created). If mismatch → action is SKIPPED with a warning ("file modified since apply; left in place — remove or revert manually if desired"). Without this, restore would silently overwrite a user's post-apply edits to a Makefile / workflow / doc.
  - **Path-safety validation before any restore action** (closes Codex iter-2 finding #1): for each manifest entry, resolve `(target_root / entry.path).resolve()` and assert the resolved path is a descendant of `target_root.resolve()`. Reject entries with absolute paths, `..` traversal, symlinks pointing outside `target_root`, or any resolved-path-outside-target. A malicious or corrupted manifest with `../outside.txt` or `/etc/passwd` aborts the restore with a clear error before any filesystem action. Tests in `tests/test_restore.py` cover `../outside.txt`, `/tmp/outside.txt`, and symlink-out edge cases (subtest (e) and (f) below).
  - Restore prints a summary at exit: `N files restored, M files removed, K skipped due to modification, R rejected for path-safety`.

## Subsystem A — Bootstrap engine + safety primitives

**Files**: `bootstrap.py`, `bootstrap_lib/{cli,detect,manifest,render,io,paths}.py` (paths.py added per Codex iter-13/iter-14 finding — shared path-safety boundary between render/apply and restore).

**CLI surface** (settled in merged plan, reproduced here for completeness):

**Two top-level modes** (closes Codex iter-5 finding #1 — restore must run standalone with only a manifest path; **parser shape decided per Codex iter-13 finding #4 + corrected per Codex iter-15 finding #1**: `--restore` stays a flag at the top level, NOT a subcommand — preserves the documented rollback hint string `<sys.executable> <abs-bootstrap.py> --restore <manifest>` that's printed in failure status blocks. Implementation uses `argparse.add_mutually_exclusive_group(required=False)` for the mode group `[--dry-run, --diff, --apply, --restore <manifest>]`; when no mode flag is provided, cli.py defaults to `dry-run` (matches the documented "dry-run by default" safety contract). Render/apply args (`--language`, `--project-name`, `--out`, etc.) are validated only when the chosen mode is render/apply; cli.py raises a clear error if any render/apply arg appears alongside `--restore`. New test in `test_bootstrap_cli.py`: `test_no_mode_flag_defaults_to_dry_run` — invoking `bootstrap.py --language python --project-name x --out /tmp/y` with NO mode flag exits 0 and performs a filesystem-pure dry-run.):

```
# Render/apply mode
bootstrap.py [--dry-run | --diff | --apply] \
  --language python                      (required in render/apply mode; PR #1 supports `python` only)
  --project-name <slug>                  (required in render/apply mode; must match `^[a-z][a-z0-9-]*$` — closes Codex iter-9 finding #4; lowercase ASCII + digits + hyphens, starting with a letter, no path separators / no `.` / no `..`. cli.py rejects with exit 2 + "invalid project name: must match ^[a-z][a-z0-9-]*$ — e.g. 'my-project', 'foo123'" when violated. Python import name (when needed in template) is derived by replacing `-` with `_`.)
  --out <dir>                            (required in render/apply mode; target directory; created ONLY during --apply — dry-run / --diff must not touch the filesystem; closes Codex iter-2 finding #4)
  --github-review {none,claude,both-docs}  (default: none per merged plan — no Claude workflow / OAuth secret dependency unless explicitly opted in; closes Codex iter-1 finding #4)
  --github-owner <owner>                 (Codex iter-13 finding #2 — required when --github-review != none; explicit flag to avoid magic git-remote derivation that can fail on greenfield projects with no origin yet)
  --github-repo <repo>                   (same — required when --github-review != none)
  # --install-hooks REMOVED from PR #1 per Codex iter-16 finding #1 — running
  # pre-commit from the skill repo's interpreter would tie target-project hooks
  # to the skill repo's venv (hooks break if skill repo moves). Users instead run
  # `cd <target> && make install && make install-hooks` after bootstrap. The
  # generated `make install-hooks` target (Subsystem F now Subsystem F') uses
  # the TARGET project's `./venv/bin/pre-commit`, scoping hooks correctly.
  # See "What we are NOT doing" section. Parked for a follow-up PR that
  # creates the target venv before the hook install.
  --overwrite-existing                   (REQUIRED on --apply when any target file already exists at --out — closes Codex iter-3 finding #1; see "Collision policy" below)
  --enable-smoke                         (emit docs/SMOKE.md)

# Restore mode (standalone, exclusive of render/apply args)
bootstrap.py --restore <manifest-path>
  # Refuses --language / --project-name / --out / --apply / --dry-run / etc.;
  # the manifest carries everything restore needs (target_root,
  # github_review_mode, file entries, created_directories). The exact command printed in the
  # rollback hint after a failed apply is `<sys.executable> <absolute-path-to-bootstrap.py> --restore <manifest>` (closes Codex iter-7 finding #1 AND iter-8 finding #1 — `python` literal isn't portable AND bare `bootstrap.py` only works from the skill repo cwd. Bootstrap formats the hint with `f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} --restore {shlex.quote(manifest_path)}"` so the command is runnable from any cwd — required when bootstrap is invoked by absolute path, from a target project's dir, or via a `~/.claude/skills/dev-project-setup/` symlink)
  # with no other args — and that command must run cleanly. Tested by
  # `test_restore_does_not_require_language_project_or_out`.
```

**`--github-owner`/`--github-repo` policy (Codex iter-13 finding #2)**: when `--github-review` is `claude` or `both-docs`, the substitution vars `github_owner` and `github_repo` must be set. CLI rule: `cli.py` requires `--github-owner` AND `--github-repo` flags when `--github-review != none`; absence → exit 2 with `"--github-review={mode} requires --github-owner and --github-repo (no implicit git-remote discovery — greenfield projects often have no origin yet)"`. Auto-derivation from `git remote get-url origin` is explicitly NOT implemented in PR #1 — too brittle for greenfield (no remote) and ambiguous when multiple remotes exist. Parked for follow-up if demand emerges. Test cases in `tests/test_bootstrap_cli.py`: (a) `--github-review=none` without owner/repo — succeeds; (b) `--github-review=claude` without owner/repo — exits 2; (c) `--github-review=claude --github-owner v3rmus89 --github-repo my-proj` — succeeds.

**Collision policy (Codex iter-3 finding #1)**: `--apply` against a `--out` that contains any pre-existing target file aborts non-zero by default with a "collision detected — re-run with `--overwrite-existing` to consent, or use `--diff` first to see what would change" message. `--overwrite-existing` is the explicit non-interactive consent flag. This matches the merged plan's "asks per-file" intent (the skill is non-interactive, so we collapse to a single repo-wide consent flag rather than per-file prompts — simpler than the merged plan's "overwrite/skip/diff/abort" wording, but achieves the same safety property: existing files are never silently overwritten). Test: `test_apply_aborts_on_collision_without_flag` in `tests/test_bootstrap_cli.py` (see Subsystem A tests). Per-file skip is parked for a follow-up PR (would need `--decisions` JSON file or interactive mode).

**Per-module responsibility**:

- `cli.py` — `argparse` definitions, top-level dispatch. Validates mutually-exclusive flag combinations (`--restore` is incompatible with `--apply`, etc.). Enforces collision policy: if `inspect_target` reports any existing files and `--overwrite-existing` is absent, exit 2 with the consent prompt.
- `detect.py` — `inspect_target(out_dir)` returns a list of `(path, exists, would_action)` tuples. Used by `--dry-run` / `--diff` / `--apply` alike, AND by `cli.py` to enforce the collision policy.
- `manifest.py` — `write_manifest(target_root, planned_entries) -> Path`, `load_manifest(path) -> Manifest`, `restore_from_manifest(manifest)`. SHA-256 + base64-encoded content snapshot per file. Manifest format JSON.
- `render.py` — Jinja2 `Environment(loader=FileSystemLoader([languages/python, shared]))`; `render_all(context, mode)` returns a `{rel_path: bytes}` dict respecting `--github-review` mode (filters out templates that shouldn't emit for the mode).
- `io.py` — `atomic_write(target_path, content_bytes)` writes to `<target>.bootstrap-tmp` then `os.rename`. `cleanup_tmp_artifacts(root)` finds and removes stale `.bootstrap-tmp` files (used by `--restore` after a crash). Signal handlers installed on entry to the apply phase, removed on clean exit.
- `paths.py` (Codex iter-7 finding #4 + iter-8 finding #2) — `validate_target_path(target_root: Path, rel_path: str) -> Path` shared between render/apply and restore. Rejects absolute paths, `..` traversal, symlink escapes (resolve `target_root / rel_path` and assert the resolved path is a descendant of `target_root.resolve()`). **Called from TWO distinct layers, not just `render.render_all` — closes Codex iter-8 finding #2**:
  1. Inside `render.render_all` (primary boundary; catches accidental template-map bugs)
  2. In `cli.py`'s apply-planning layer, applied to the FINAL `{rel_path: bytes}` map returned by `render_all` — runs BEFORE collision detection, manifest write, diff, or apply. This second pass is the real safety boundary that holds even if `render_all` is monkey-patched (as the test does to verify the apply-side check actually runs at the CLI layer, not inside the renderer).

**Test execution boundary** (Codex iter-10 finding #4 — monkey-patches don't cross subprocess boundaries; tests that depend on them MUST run in-process):
- **In-process** (call `bootstrap_lib.cli.main(argv)` directly): all tests that monkey-patch `render_all` / `subprocess.run` / Python-level seams — `test_bootstrap_cli.py`, `test_manifest.py`, `test_atomic_writes.py`, `test_restore.py`, `test_path_safety.py`, `test_github_review_modes.py`, `test_shared_templates.py`, `test_python_templates.py`, `test_selftest_overlap.py`, `test_dogfood_doc_sanity.py`. (Per iter-17 finding #1: `test_install_hooks.py` ships only the `test_generated_install_hooks_uses_target_venv` subtest in PR #1, which is subprocess-based — see below — so it's no longer in the in-process list.)
- **Subprocess** (spawn `bootstrap.py` via `subprocess.run([sys.executable, "bootstrap.py", ...])`): tests that need real process boundaries — `test_sigterm_mid_apply.py`, `test_deployed_invocation.py`, `test_install_hooks.py` (`test_generated_install_hooks_uses_target_venv` spawns `make install` + `make install-hooks` as subprocesses), the smoke walks in `test_smoke_python_generated.py` (after the in-process render/apply paths are exercised by other tests).

**Tests** (under `tests/`):

| File | Asserts |
|---|---|
| `tests/test_bootstrap_cli.py` | argparse rejects `--apply` without required args; `--restore` is exclusive with `--apply`; `--diff` implies `--dry-run`; default mode is dry-run; **slug validation (Codex iter-9 finding #4)**: parametrised `test_project_name_validation` — positive: `valid-project`, `foo123`, `a` all accepted; negative: `My-Project` (uppercase), `with spaces`, `../escape`, `foo/bar`, `` (empty), `1starts-with-digit` all rejected with exit 2 + the documented error message. **`--diff` produces real unified diff output (Codex iter-7 finding #3)**: `test_diff_emits_unified_diff_no_writes` — fixture with an existing file whose content differs from what the template would render; assert (a) stdout contains `--- ` / `+++ ` headers and at least one `-` / `+` line for the differing content; (b) `--out` is NOT created if it didn't exist before; (c) no `.bootstrap-tmp` files anywhere in the tree afterwards; (d) **isolated tmpdir for manifest assertion (Codex iter-8 finding #4)**: test injects an isolated `TMPDIR=<pytest-tmp_path>` (bootstrap honours `TMPDIR` for manifest paths instead of hard-coding `/tmp/`), then assert that isolated tmpdir contains no `dev-project-setup-restore-*.json` after the diff run. Avoids the brittleness of asserting absence in shared `/tmp/`; **collision policy (iter-3 finding #1)**: `test_apply_aborts_on_collision_without_flag` — fixture with one pre-existing file at `--out`; bootstrap `--apply` (no `--overwrite-existing`) exits 2 with the consent message; followed by `--apply --overwrite-existing` succeeds and writes the manifest; **restore-mode standalone (iter-5 finding #1)**: `test_restore_does_not_require_language_project_or_out` — invoking `[sys.executable, "bootstrap.py", "--restore", "/tmp/m.json"]` with no other flags succeeds (assuming a valid manifest); invoking restore with `--language` or `--project-name` or `--out` exits non-zero with "those flags are not valid in restore mode". **Tests use `sys.executable` not literal `python` (Codex iter-7 finding #1)** |
| `tests/test_manifest.py` | Round-trip: `write_manifest(...)` → `load_manifest(...)` returns equal data; SHA-256 of each entry matches recomputation; content-snapshot decode is bytewise-identical |
| `tests/test_atomic_writes.py` | `atomic_write` creates `<file>.bootstrap-tmp` first then renames; concurrent reader sees either old content or new content, never partial; `cleanup_tmp_artifacts` removes stale `.bootstrap-tmp` files without touching others |
| `tests/test_path_safety.py` | (Codex iter-7 finding #4 + iter-8 finding #2) Apply-side path-safety: monkey-patch `render_all` to return an entry with `path="../AGENTS.md"` (or absolute path, or symlink-escape rel-path), thereby BYPASSING the inside-renderer check; assert `bootstrap.py --apply` STILL fails BEFORE manifest write and BEFORE any file write, with a clear PathSafetyError. This explicitly proves the CLI-layer second pass is the real safety boundary — without it the monkey-patch would let unsafe paths slip past. |
| `tests/test_restore.py` | Ten subtests (Codex iter-12 findings #1 + #2 added 2 more): (a) **overwritten files restored** — fixture with 2 files, apply overwrites both (no user edits between apply and restore), restore writes pre-apply content back; (b) **created files removed** — fixture with 1 file, apply creates 2 new ones (no user edits between), restore deletes those 2 new ones; (c) **unlisted files ignored** — manifest references only files in target/; restore refuses to touch any file outside that list, prints warning instead; (d) **user-modified created file preserved** — apply creates file X, user then edits X, restore detects SHA-256 mismatch with `sha256_after`, SKIPS the delete, prints "left in place" warning; (d') **user-modified overwritten file preserved** (Codex iter-4 finding #1) — apply overwrites file Y, user then edits Y, restore detects SHA-256 mismatch with `sha256_after`, SKIPS the write-back, prints "left in place" warning — proves symmetric protection across created vs overwritten cases; (e) **path-safety: relative traversal rejected** — hand-craft a manifest with `path: "../outside.txt"`; assert `load_manifest` or `restore_from_manifest` raises a clear PathSafetyError before any filesystem action; (f) **path-safety: absolute path rejected** — manifest with `path: "/tmp/outside.txt"`; same; (g) **path-safety: symlink escape rejected** (Codex iter-3 finding #3) — create `target/link → /tmp/outside-dir/`, manifest entry `path: "link/file.txt"`; assert restore aborts before any filesystem action; assert `/tmp/outside-dir/` is unchanged; (h) **created directories removed** (Codex iter-12 finding #1) — fixture greenfield; apply creates nested `.github/workflows/ci.yml` plus several others (target dirs `.github/workflows`, `docs/plans`, `scripts`, `tests`, `src` all NEW); restore deletes files AND the empty parent dirs in reverse-depth order; assert `os.listdir(target)` is empty post-restore (proves byte-AND-tree-identical rollback); (i) **created directories with user content preserved** — same as (h), but user drops `user-file.txt` inside `scripts/` between apply and restore; restore deletes the file `scripts/run-with-clean-env.py` from manifest but LEAVES `scripts/` (not empty) and the user file untouched; (j) **file mode restored** (Codex iter-12 finding #2) — fixture with `scripts/runner.sh` mode `0o644` (existing); apply overwrites with content mode `0o755` (a different shell script the skill might emit hypothetically); restore returns content AND mode to `0o644`; assert `os.stat(target).st_mode & 0o777 == 0o644`. Final assertion in (a)+(b)+(h): `diff -r <pre-apply-snapshot> <restored-project>` is byte-empty AND tree-structure-identical. |
| `tests/test_sigterm_mid_apply.py` | **Deterministic sync via test-only pause hook (closes Codex iter-5 finding #2 — polling for a microsecond-lived `.bootstrap-tmp` artifact is racy on fast machines).** Bootstrap recognises `DEV_PROJECT_SETUP_PAUSE_AFTER_FIRST_WRITE=<sentinel-path>` env var: after the manifest is fsync'd AND the first file has been renamed into place, bootstrap touches `<sentinel-path>` then blocks until SIGTERM. Test spawns `bootstrap.py --apply ...` with this env set, waits for the sentinel file to appear (deterministic — no polling for a transient artifact), sends SIGTERM, assert manifest path is printed to stderr; runs `--restore <printed-manifest>`; assert (a) no `.bootstrap-tmp` files remain in the target tree, AND (b) **byte-identical rollback**: `diff -r <pre-apply-snapshot> <restored-project>` is empty. Without `DEV_PROJECT_SETUP_PAUSE_AFTER_FIRST_WRITE` the env var has no effect (no production code path uses it). |

**Acceptance gate** (per merged plan + iter-1 finding #2 split):
- `--dry-run` against the fixture produces a known list, no writes
- `--apply` followed by `--restore <manifest>` produces a bytewise-identical copy of the pre-apply fixture (covers both overwritten-file restore and created-file delete paths)
- `--restore` refuses to touch any file not listed in the manifest
- `--restore` skips deletion (with warning, not error) for created files whose SHA-256 has changed since apply — protects user edits
- Killing the bootstrap with SIGTERM mid-apply leaves no half-written `.bootstrap-tmp` artifacts after a follow-up `--restore`

## Subsystem B — Python language templates + generated-project smoke

**Files**: all 10 files under `languages/python/` listed in Scope.

**Template authoring rules**:
- Every `{{var}}` substitution must use a name from the substitution-variables list.
- **Unresolved-variable detection via Jinja2 `StrictUndefined`** (closes Codex iter-11 finding #1 — a naive text grep for `{{` / `}}` in rendered output would false-positive on GitHub Actions' `${{ ... }}` syntax that legitimately survives rendering): `bootstrap_lib/render.py` uses `Environment(undefined=jinja2.StrictUndefined)` so any unsubstituted Jinja variable raises `jinja2.exceptions.UndefinedError` at render time, BEFORE the rendered bytes are written or asserted on. Per-template test (`tests/test_python_templates.py` / `tests/test_shared_templates.py`) renders against the synthetic context inside `pytest.raises(UndefinedError)` expectations being absent — if anything is unresolved, render throws. The rendered output is then free to contain `${{ ... }}` (GitHub Actions) and other dollar-brace syntax without flagging.
- Brace-heavy templates (Makefile, ci.yml, claude-review.yml) wrap brace-sensitive sections in `{% raw %}…{% endraw %}` to bypass Jinja interpretation. **(Codex iter-14 finding #1 — corrected): the leading `$` does NOT protect `${{ ... }}` from Jinja; Codex verified locally that Jinja with `StrictUndefined` still parses the inner `{{ secrets.FOO }}` and raises `UndefinedError`.** ALL GitHub Actions `${{ ... }}` expressions in template files MUST be wrapped in `{% raw %}${{ ... }}{% endraw %}` blocks. Render test asserts (a) `ci.yml.tmpl` and `claude-review.yml.tmpl` render without `UndefinedError`, (b) `claude-review.yml.tmpl` (rendered with `github_review_mode=claude`) contains the substring `secrets.CLAUDE_CODE_OAUTH_TOKEN`, (c) `ci.yml.tmpl` (default mode) does NOT contain any Claude-secret references — generic CI doesn't need OAuth (closes the iter-14 ambiguity about `ci.yml` having `CLAUDE_CODE_OAUTH_TOKEN`, which was wrong; only `claude-review.yml` needs it).

**Per-template render-and-parse assertions**:

| Template | Parser used |
|---|---|
| `Makefile.tmpl` | `make -n -f -` (dry-run parse only; doesn't run targets); also assert `make help` lists all expected targets; **install/install-hooks separation (Codex iter-8 finding #3)**: assert generated `install` target's recipe does NOT call `pre-commit install`; assert separate `install-hooks` target exists with `.git/` guard |
| `.pre-commit-config.yaml.tmpl` | `yaml.safe_load` |
| `pyproject.toml.tmpl` | `tomllib.loads` (Python 3.11+) |
| `requirements-dev.txt.tmpl` | line-by-line `package(==\|>=).*` regex; **plus assert no `<pinned>` placeholder remains** (Codex iter-6 finding #4 — proves concrete pins were chosen at plan time, not deferred to implementation) |
| `ruff.toml.tmpl`, `pytest.ini.tmpl` | `tomllib.loads` / `configparser.read_string` |
| `.gitignore.tmpl` | non-empty + at least one expected line (`venv/`) |
| `ci.yml.tmpl` | `yaml.safe_load`; assert the step sequence is `checkout → setup-python → make install → make check` in that order — closes Codex iter-4 finding #2 |
| `tests-test_smoke.py.tmpl` | `compile(source, '<test>', 'exec')` (syntactic Python) |
| `src-main.py.tmpl` | same |

**Generated-project smoke test** (`tests/test_smoke_python_generated.py`):

Two-step flow per merged plan:

```python
# Step 1: dry-run, assert no writes — including no creation of --out itself
# Use sys.executable not literal "python" — closes Codex iter-7 finding #1
target = tmp_path / "smoke-test"
assert not target.exists()  # precondition
result = subprocess.run([sys.executable, "bootstrap.py", "--language", "python",
                         "--project-name", "smoke-test", "--out", str(target)],
                        check=True, capture_output=True, text=True)
assert not target.exists(), "dry-run must not create --out (Codex iter-2 finding #4)"
# Assert the printed file list matches the expected set for github_review_mode=none
# (the default) — closes Codex iter-11 finding #4
expected_paths = {
    "Makefile", "pyproject.toml", "requirements-dev.txt", "ruff.toml",
    "pytest.ini", ".gitignore", ".pre-commit-config.yaml", ".editorconfig",
    ".github/workflows/ci.yml", ".github/pull_request_template.md",
    "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "BACKLOG.md",
    "docs/plans/README.md", "scripts/run-with-clean-env.py",
    "tests/test_smoke.py", "src/main.py",
}
# Mode=none means NO claude-review.yml; assert it's NOT in the list
assert ".github/workflows/claude-review.yml" not in result.stdout, \
    "default --github-review=none must not emit claude-review.yml (Codex iter-1 finding #4)"
for path in expected_paths:
    assert path in result.stdout, f"dry-run output missing expected path: {path}"

# Step 2: --apply, then make install + make check inside.
# install runs FIRST (Codex iter-3 finding #2) — the generated Makefile's
# `make install` creates a venv and installs requirements-dev.txt, so the
# subsequent `make check` uses the project's pinned toolchain rather than
# whatever ruff/pytest happens to be on PATH from the parent test env.
subprocess.run([sys.executable, "bootstrap.py", "--apply", "--language", "python",
                "--project-name", "smoke-test", "--out", str(target)],
               check=True)
result_install = subprocess.run(["make", "install"], cwd=str(target),
                                capture_output=True, text=True)
assert result_install.returncode == 0, result_install.stderr
result = subprocess.run(["make", "check"], cwd=str(target),
                        capture_output=True, text=True)
assert result.returncode == 0, result.stderr
# Codex iter-16 finding #4: also smoke-test `make run` since `run` is part of
# the generated Makefile surface but was previously unverified
# src-main.py.tmpl's body is a trivial `print("hello from <project_name>")` so
# `make run` is expected to exit 0 quickly without hanging
result_run = subprocess.run(["make", "run"], cwd=str(target),
                            capture_output=True, text=True, timeout=10)
assert result_run.returncode == 0, result_run.stderr
assert "smoke-test" in result_run.stdout
```

The test uses pytest's `tmp_path` fixture (per-test tempdir) so parallel runs don't clobber. The dry-run precondition + post-assertion together prove that dry-run is filesystem-pure — Codex iter-2 finding #4 closed.

**Acceptance gate**: generated-project smoke walk is green; per-template render-and-parse tests are green; `make check` inside the generated project is green.

## Subsystem C — Shared templates

**Files**: all 12 files under `shared/` listed in Scope (count corrected per Codex iter-2 finding #5).

**Source-of-truth mapping** (each .tmpl derives from a Boxette file):

| Template | Boxette source | Notes on what to strip |
|---|---|---|
| `shared/AGENTS.md.tmpl` | `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/AGENTS.md` | Strip Telegram-bot-specific review guidance; retain Plan Review Guidance + per-language Codex review guidance template. **Includes the "Don't fold by default — triage" rule** (see "Triage rule for both reviewers" below) — applies when Codex reviews a Claude-authored plan |
| `shared/CLAUDE.md.tmpl` | `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/CLAUDE.md` | Strip bot-restart rule, API quirks, PINFL section, City/district logic; retain Commands table, Plan review loop, focused-commits guidance. **Includes the "Don't fold by default — triage" rule** — applies when Claude reviews a Codex-authored plan |
| `shared/CONTRIBUTING.md.tmpl` | `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/CONTRIBUTING.md` | Retain per-change workflow, one-time setup, Codex CLI install/login, Claude CLI install/login |
| `shared/BACKLOG.md.tmpl` | `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/BACKLOG.md` | Strip Boxette-specific entries; ship with four starter entries: `--ephemeral` (Codex), `--no-session-persistence` (Claude — symmetric to `--ephemeral`), "Claude/Codex CLI flag drift" (trigger: preflight target fails), "Retroactively add triage rule to Boxette's plan-review docs" (trigger: after PR #1 lands) |
| `shared/pull_request_template.md.tmpl` | `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/.github/pull_request_template.md` | Reviewer-checklist section wrapped in `{% if github_review_mode in ['claude','both-docs'] %}` for claude[bot]; `{% if github_review_mode == 'both-docs' %}` for chatgpt-codex-connector[bot] |
| `shared/claude-review.yml.tmpl` | `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/.github/workflows/claude-review.yml` | Substitute `{{github_owner}}` / `{{github_repo}}` for any repo-pinned references. **Generic-prompt rewrite (Codex iter-4 finding #3)**: Boxette's workflow prompt explicitly mentions Telegram bot, payments, API drift, i18n, PII, PINFL — all bot-specific. Rewrite the prompt to be project-agnostic: instruct Claude to read the generated `AGENTS.md` + `CLAUDE.md` for project-specific risk classes, and review against THOSE rather than against any baked-in domain. Generic risk categories to keep: security vulnerabilities (OWASP-style), regressions, hard-coded secrets, test coverage gaps. |
| `shared/docs-plans-README.md.tmpl` | `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/docs/plans/README.md` | Add bidirectional-review filename convention paragraph; add bootstrap-exception clause referencing the skill's bootstrap-exception (PR #1). **Documents the "Don't fold by default — triage" rule** as part of step-2 of the workflow (see "Triage rule for both reviewers" below) — this is what makes the loop terminate faster (the merged Boxette plan converged in 3 iterations; this skill plan took 16 because every finding was folded by default) |
| `shared/docs-SMOKE.md.tmpl` | n/a | Skeleton template with placeholder smoke-walk steps |
| `shared/docs-codex-github-review-setup.md.tmpl` | n/a | Walkthrough for enabling Codex web-UI GitHub auto-review for the project |
| `shared/editorconfig.tmpl` | n/a | Standard `.editorconfig` |
| `shared/Makefile.review.tmpl` | derived from `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/Makefile` lines 66–115 | Three targets (codex, claude, preflight); reviewer-aware `PLAN_REVIEW_OUT` filename; `env -u` scrub list enumerated explicitly |
| `shared/scripts-run-with-clean-env.py.tmpl` | new (no Boxette source) | Same content as the skill repo's `scripts/run-with-clean-env.py`; emits to `scripts/run-with-clean-env.py` in generated project, mode 0755. Listed in Subsystem D as the actual review-tooling dependency, repeated here for completeness so Subsystem C's mapping table is exhaustive (closes Codex iter-2 finding #5). |

### Triage rule for both reviewers (the "Don't fold by default" rule)

Lessons-learned from this plan's 16-iteration convergence (vs the merged Boxette plan's 3): the loop terminates faster when the plan author triages findings instead of folding everything. This rule is templatised into `shared/CLAUDE.md.tmpl`, `shared/AGENTS.md.tmpl`, and `shared/docs-plans-README.md.tmpl` so every bootstrapped project inherits it. It's ALSO retroactively added to the skill repo's own Bucket-3 hand-written `CLAUDE.md`/`AGENTS.md`/`docs/plans/README.md` (so the skill repo itself uses the rule for PR #2 onward).

**Wording (used verbatim in all three templates):**

> ## Triaging review findings
>
> When you receive a Codex review (in Claude Code) or a Claude review (in Codex), do **NOT fold every finding by default**. The loop converges faster — and produces a tighter plan — when each finding is triaged. For each finding decide:
>
> - **(a) Fold now** — the plan is wrong, contradictory, or would produce a broken implementation without this change. Fold into the plan body. Document in the evidence table.
> - **(b) Park to BACKLOG** — the finding is real and worth fixing, but deferrable. Add an entry to `BACKLOG.md` with an explicit trigger (e.g. "fix when first user reports stale `.git/hooks/` after skill repo move"). Note in the evidence table as `parked: <reason>`.
> - **(c) Reject** — the finding is stylistic, out-of-scope for this PR, or implementation-review territory (will be caught during code review of the implementation PR, not now). Note in the evidence table as `rejected: <reason>` so the decision is documented even though no plan-text changes.
> - **(d) Surface to human (`ask me`) — use sparingly, only when the change is material** — pause folding and surface to the human ONLY when the finding would materially change the PR's user-facing surface: a documented CLI flag being removed/renamed/added, a deliverable being dropped or expanded, the safety/risk model shifting in a way the user might disagree with. **Default is NOT (d)** — for smaller UX choices, reasonable implementation defaults, scope-trim decisions that aren't surprising, decide as (a/b/c) using engineering judgment and surface ALL such autonomous decisions in the end-of-loop final-plan summary (the existing mandatory-human-approval gate). The bar for (d): *if you imagine showing the change to the user 30 seconds before merge, would they be surprised by the decision?* If yes, (d) now. If no, decide and surface in the final summary. Note (d) outcomes in the evidence table as `surfaced: <user's decision>`.
>
> Only (a) folds modify the plan body during the iteration. (b), (c), and (d) still produce evidence-table entries — the decision matters even when no plan text changes. (d) additionally pauses the loop for a human turn before the iteration proceeds. This makes engineering judgment visible to future reviewers and to the implementer.
>
> **Calibration**: imp-3 should mean "if we ship without this, the PR doesn't work" — not "if we shipped this, an adversarial test could fail." Imp-3 ≠ "would be more correct." When in doubt about whether a finding is a real blocker, ask: *can the PR ship with a working `make check` and a green smoke walk without this change?* If yes, it's at most imp-2, and probably (b) or (c).
>
> **No strict iteration cap** — but watch the trajectory. If imp-3 count plateaus at 1-2 across 3 consecutive iterations and the findings are increasingly narrow edge cases, the loop is at diminishing returns; surface the remaining items to the human-approval gate with explicit framing ("these are real but deferrable; ship plan + fold during implementation"). The human decides whether to continue iterating or accept.

This subsection is **shipped as part of three templates**, not just consumed in-session:
- `shared/CLAUDE.md.tmpl` — under the "Plan review loop" section
- `shared/AGENTS.md.tmpl` — under "Plan Review Guidance"
- `shared/docs-plans-README.md.tmpl` — as step-2 of the documented workflow

And applied retroactively to:
- Bucket 3's `CLAUDE.md`, `AGENTS.md`, `docs/plans/README.md` (the skill repo's own hand-written copies)

**Out of scope for PR #1**: applying this same rule retroactively to Boxette's `CLAUDE.md` + `AGENTS.md` + `docs/plans/README.md`. That's a small Boxette-side PR that lands separately — flagged in BACKLOG as a follow-up. Reason it's not in PR #1: PR #1 ships only to this new repo; touching Boxette would expand the PR scope across two repos.

**Tests** (`tests/test_shared_templates.py`):
- Per-template render with synthetic context using `Environment(undefined=jinja2.StrictUndefined)`. Unsubstituted variables raise `UndefinedError` at render time — the test asserts render succeeds (no exception). This avoids false positives on legitimate `${{ ... }}` GitHub Actions tokens in rendered output (closes Codex iter-11 finding #1)
- YAML templates: `yaml.safe_load` parses successfully
- Markdown templates: simple link-target check (every `](path)` either starts with `http`, `#`, or is a relative path that's plausible for the generated project)
- `pull_request_template.md.tmpl` rendered three times (once per `--github-review` mode) — see Subsystem E for the per-mode assertions
- **No-Boxette-isms scan (Codex iter-4 finding #3)**: per-template rendered-content scan asserts NONE of the following strings appear in any shared template's output: `Boxette`, `Telegram`, `bot/`, `PINFL`, `i18n/ru.json`, `boxette.db`, `customs`, `signup`, `payment` (case-insensitive). This catches accidental leaks from copying Boxette's domain-specific text into a generic template. If a template legitimately needs to reference the project (e.g. `{{project_name}}` placeholder), it uses a Jinja variable, not a hard-coded string.
- **Triage-rule presence scan**: asserts the heading `## Triaging review findings` AND all four triage-bullets `(a) Fold now`, `(b) Park to BACKLOG`, `(c) Reject`, `(d) Surface to human` appear in each of: rendered `shared/CLAUDE.md.tmpl`, rendered `shared/AGENTS.md.tmpl`, rendered `shared/docs-plans-README.md.tmpl`. Same assertion runs against the skill repo's own Bucket-3 `CLAUDE.md`/`AGENTS.md`/`docs/plans/README.md` (via `tests/test_dogfood_doc_sanity.py`). Drift = test fail.

**Acceptance gate**: all shared templates render against the synthetic context; no orphan Jinja syntax remains; YAML parses; tests green.

## Subsystem D — Bidirectional plan-review Makefile fragments

**Files**:
- `shared/Makefile.review.tmpl` — the three targets
- `scripts/run-with-clean-env.py` — prefix-aware env scrubber

**`Makefile.review.tmpl` contents** (paraphrased; full content in the template):

```makefile
# Filename convention: include the reviewer in the path so per-reviewer
# iteration counters are independent.
PLAN_REVIEW_OUT_CODEX  ?= /tmp/plan-review-$(notdir $(basename $(PLAN_FILE)))-by-codex-iter-$(ITERATION).md
PLAN_REVIEW_OUT_CLAUDE ?= /tmp/plan-review-$(notdir $(basename $(PLAN_FILE)))-by-claude-iter-$(ITERATION).md

review-plan-by-codex:
    @test -n "$(PLAN_FILE)" || { echo "Usage: ..."; exit 1; }
    @test -f "$(PLAN_FILE)" || { echo "Plan file not found"; exit 1; }
    @command -v codex >/dev/null 2>&1 || { echo "codex CLI not found"; exit 1; }
    $(CURDIR)/scripts/run-with-clean-env.py \
      -- codex exec -C "$(CURDIR)" --sandbox read-only --color never \
         --output-last-message "$(PLAN_REVIEW_OUT_CODEX)" \
         "<review prompt — same as Boxette's, modulo iteration text>"
    @echo "Codex review written to: $(PLAN_REVIEW_OUT_CODEX)"
    @cat "$(PLAN_REVIEW_OUT_CODEX)"

review-plan-by-claude:
    @test -n "$(PLAN_FILE)" || { echo "Usage: ..."; exit 1; }
    @test -f "$(PLAN_FILE)" || { echo "Plan file not found"; exit 1; }
    @command -v claude >/dev/null 2>&1 || { echo "claude CLI not found"; exit 1; }
    $(CURDIR)/scripts/run-with-clean-env.py \
      -- claude --print --permission-mode plan --add-dir "$(CURDIR)" \
         --output-format text \
         "<review prompt — same as the codex side>" \
      > "$(PLAN_REVIEW_OUT_CLAUDE)"
    @echo "Claude review written to: $(PLAN_REVIEW_OUT_CLAUDE)"
    @cat "$(PLAN_REVIEW_OUT_CLAUDE)"

preflight-review-tooling:
    # Run manually after CLI updates. Test suite (test_preflight_tooling.py)
    # uses shims and never invokes the real CLIs — `make check` must not
    # consume subscription quota (Codex iter-2 finding #3).
    # 1. CLIs on PATH
    @command -v codex >/dev/null 2>&1 || { echo "codex CLI not found"; exit 1; }
    @command -v claude >/dev/null 2>&1 || { echo "claude CLI not found"; exit 1; }

    # 2. Flag smoke — exec each CLI through the SAME wrapper and with the
    # SAME flag shape the review targets use, including `-C "$(CURDIR)"` for
    # codex (closes Codex iter-4 finding #4 — preflight that bypasses the
    # wrapper or omits -C can pass while the real review target fails).
    @$(CURDIR)/scripts/run-with-clean-env.py -- \
        codex exec -C "$(CURDIR)" --sandbox read-only --color never \
        --output-last-message /tmp/preflight-codex.txt \
        "Reply with the single word: ok" >/dev/null 2>&1 \
        || { echo "codex flag smoke failed — see merged plan risk table"; exit 1; }
    @$(CURDIR)/scripts/run-with-clean-env.py -- \
        claude --print --permission-mode plan --add-dir "$(CURDIR)" \
        --output-format text \
        "Reply with the single word: ok" >/dev/null 2>&1 \
        || { echo "claude flag smoke failed — see merged plan risk table"; exit 1; }

    # 3. Tested-baseline version advisory (warn, not fail — version drift may still work)
    @codex --version | grep -q "0\.130\." \
        || echo "WARN: tested baseline is codex-cli 0.130.0; you have $$(codex --version)"
    @claude --version | grep -q "2\.1\.139" \
        || echo "WARN: tested baseline is Claude Code 2.1.139; you have $$(claude --version)"

    @echo "✓ preflight ok"
```

**`scripts/run-with-clean-env.py`** — accepts `[--keep-claude-code] [--keep-codex] -- <cmd> <args...>`. Rebuilds `os.environ` excluding keys starting with `CLAUDE_CODE_` and `CODEX_` (unless explicitly kept), unsets `MAKEFLAGS`/`MAKELEVEL`/`MAKEOVERRIDES`/`MFLAGS`/`PLAN_FILE`/`ITERATION`/`PLAN_REVIEW_OUT*`, then `os.execvp`s the command.

**Tests**:

| File | Asserts |
|---|---|
| `tests/test_makefile_review_targets.py` | After bootstrap into a fixture, `make help` in the fixture lists `review-plan-by-codex`, `review-plan-by-claude`, `preflight-review-tooling`; the per-reviewer filename convention is honoured (assert `PLAN_REVIEW_OUT_CODEX` and `PLAN_REVIEW_OUT_CLAUDE` are distinct variables). **Stale-PWD robustness (Codex iter-9 finding #1)**: invoke `make -C <fixture>` from a different cwd with a deliberately stale `PWD` env var; assert shim `codex`/`claude` receives the fixture path (i.e. the generated project root) via `-C` / `--add-dir`, not the stale `PWD`. Proves `$(CURDIR)` is used consistently throughout `Makefile.review.tmpl`, not `$(PWD)`. |
| `tests/test_preflight_tooling.py` | **Shim-only — never invokes real Claude / Codex CLIs** (closes Codex iter-2 finding #3 — `make check` must not depend on installed AI tools or consume subscription quota). Three layers: (a) **missing CLI**: mock PATH to omit `claude` / `codex` respectively; assert `make preflight-review-tooling` exits non-zero with a "CLI not found" message. (b) **flag smoke failure**: install shim `claude` / `codex` scripts on a controlled PATH that exit non-zero when invoked with the actual flag set (`--permission-mode plan` / `exec --sandbox read-only`); assert preflight exits non-zero with "flag smoke failed". (c) **version drift advisory**: shim CLI reports `claude --version: 2.99.0` (success), assert preflight exits 0 but stdout contains `WARN: tested baseline`. (d) **shim success path**: shims that succeed cleanly + report matching versions; assert exit 0 + no WARN. Real-CLI invocation is a manual gate: running `make preflight-review-tooling` directly from a developer shell with the real CLIs on PATH. A separate live-mode test `test_preflight_live_optional` is gated behind `RUN_LIVE_AI_PREFLIGHT=1` env var (skipped by default; useful when bumping baseline versions). |
| `tests/test_env_scrubber.py` | `run-with-clean-env.py` with `CLAUDE_CODE_FOO=bar` and `CODEX_BAZ=quux` in env; spawn a child that prints `os.environ`; assert neither var appears in child env. **Preflight wrapper assertion (Codex iter-4 finding #4)**: assert preflight target invokes the wrapper (via shim that records its argv when invoked) for BOTH the codex and claude flag-smoke commands — proves preflight exercises the same code path as the review targets, not a stripped-down version |

**Acceptance gate**:
- Both `review-plan-by-codex` and `review-plan-by-claude` visible in generated `make help`
- `make preflight-review-tooling` exits 0 only when (a) both CLIs are PATH-resolvable AND (b) flag-smoke commands succeed; version-mismatch is advisory only (exits 0 with WARN)
- Env scrubber strips `CLAUDE_CODE_*` and `CODEX_*` from child env
- Generated-project smoke (per Codex iter-1 finding #1 follow-up): bootstrap into a tempdir, run `make preflight-review-tooling` with shim CLIs on PATH, assert it exits 0; then run BOTH review targets with shim CLIs (Codex iter-7 finding #2 — claude direction was previously untested, leaving PR #2's self-hosted loop unverified; Codex iter-15 finding #2 — shims must mirror the real CLI's output mechanism):
  - `make review-plan-by-codex PLAN_FILE=docs/plans/_smoke_plan.md ITERATION=1` with shim `codex` that **parses `--output-last-message <path>` from its argv and writes canned review text to that path** (NOT a stdout-only echo — the Makefile target relies on `codex exec --output-last-message <path>` to materialise the output file; an echo-only shim wouldn't produce it). Assert `/tmp/plan-review-_smoke_plan-by-codex-iter-1.md` exists and contains the canned text.
  - `make review-plan-by-claude PLAN_FILE=docs/plans/_smoke_plan.md ITERATION=1` with shim `claude` that prints canned review text to stdout. Assert `/tmp/plan-review-_smoke_plan-by-claude-iter-1.md` exists and contains the canned text (proves the shell-redirect-to-output-file path works, since `claude` has no `--output-last-message` equivalent and uses stdout redirect).

## Subsystem E — `--github-review` modes

**Mode behaviour** (reproduced from merged plan; default is `none` per Codex iter-1 finding #4 — keeps bootstrap free of hidden OAuth-secret / subscription dependencies unless explicitly opted in):

| Mode | `.github/workflows/claude-review.yml` | PR template AI-reviewer section | Extra files |
|---|---|---|---|
| `none` (default) | NOT emitted | omitted entirely (no orphan checklist text) | — |
| `claude` (opt-in via `--github-review=claude`) | emitted | claude[bot] checklist only | — |
| `both-docs` (opt-in via `--github-review=both-docs`) | emitted | claude[bot] + chatgpt-codex-connector[bot] checklists | `docs/codex-github-review-setup.md` emitted |

The skill repo's own dogfood files (Bucket 3) use `claude` mode because this repo intentionally runs Claude auto-review on PRs — that's a deliberate per-repo choice, not the CLI default applied to bootstrapped projects.

**Implementation**:
- `bootstrap_lib/render.py` filters the template-emission list by mode (drops `claude-review.yml.tmpl` for `none`; drops `docs-codex-github-review-setup.md.tmpl` for all but `both-docs`).
- `pull_request_template.md.tmpl` uses Jinja `{% if github_review_mode in ['claude','both-docs'] %}` for the claude[bot] section and `{% if github_review_mode == 'both-docs' %}` for the codex-bot section.

**Tests** (`tests/test_github_review_modes.py`) — three subtests, parametrised:

```python
# Three parametrised modes + one extra test for the default (no --github-review flag passed)
# proving CLI default is "none" — closes Codex iter-1 finding #4.
# Codex iter-14 finding #2: opt-in modes pass --github-owner/--github-repo per
# the iter-13 CLI rule; mode=none omits them.
@pytest.mark.parametrize("mode,expected_workflow_exists,expected_extra_doc_exists,expected_pr_mentions",
                         [("none", False, False, []),
                          ("claude", True, False, ["claude[bot]"]),
                          ("both-docs", True, True, ["claude[bot]", "chatgpt-codex-connector[bot]"])])
def test_github_review_mode(tmp_path, mode, expected_workflow_exists, expected_extra_doc_exists, expected_pr_mentions):
    args = ["--apply", "--language", "python", "--project-name", "test",
            "--out", str(tmp_path), "--github-review", mode]
    if mode != "none":
        args += ["--github-owner", "test-owner", "--github-repo", "test-repo"]
    run_bootstrap(args)
    workflow = tmp_path / ".github" / "workflows" / "claude-review.yml"
    extra_doc = tmp_path / "docs" / "codex-github-review-setup.md"
    pr_template = (tmp_path / ".github" / "pull_request_template.md").read_text()

    assert workflow.exists() == expected_workflow_exists
    assert extra_doc.exists() == expected_extra_doc_exists
    for mention in expected_pr_mentions:
        assert mention in pr_template
    # No-orphan-checklist assertion: any reviewer mention implies the matching file exists
    if "claude[bot]" in pr_template:
        assert workflow.exists()
    if "chatgpt-codex-connector[bot]" in pr_template:
        assert extra_doc.exists()

def test_default_mode_is_none(tmp_path):
    # No --github-review flag passed; default must be 'none'
    run_bootstrap(["--apply", "--language", "python", "--project-name", "test",
                   "--out", str(tmp_path)])
    assert not (tmp_path / ".github" / "workflows" / "claude-review.yml").exists()
    pr_template = (tmp_path / ".github" / "pull_request_template.md").read_text()
    assert "claude[bot]" not in pr_template
    assert "chatgpt-codex-connector[bot]" not in pr_template
```

**Acceptance gate**: per-mode test passes for all three modes + default-is-none test passes; no orphan checklist text in any mode.

## Subsystem F — Generated `make install-hooks` target (replaces `--install-hooks` flag)

**Per Codex iter-16 finding #1**, the bootstrap `--install-hooks` flag is REMOVED from PR #1 (its dual-venv semantics would tie target-project hooks to the skill repo's venv). The generated project's `make install-hooks` target — using the TARGET project's own `./venv/bin/pre-commit` — replaces it cleanly. Hooks are scoped to the project they protect; restore manifest still doesn't cover them (they're git-side artifacts).

**Behaviour** (revised):
- `bootstrap.py --apply` writes `.pre-commit-config.yaml` to the target root. Prints: "next steps:\n  `cd <out> && make install` (sets up venv + deps)\n  `make install-hooks` (registers git hooks, requires .git/ — run `git init` first if greenfield)"
- Generated `make install-hooks` (under `languages/python/Makefile.tmpl`): runs `./venv/bin/pre-commit install && ./venv/bin/pre-commit install --hook-type pre-push`, guarded by `@test -d .git || { echo "skipping: not a git repo"; exit 0; }`. Uses target project's venv interpreter, NOT the skill repo's. Resulting hook scripts reference `<target>/venv/bin/python` — survive skill repo moves.
- `bootstrap.py --restore` does NOT need to mention hooks anymore (bootstrap never installs them in PR #1).

**Legacy `--install-hooks` flag**: removed in iter-16; iter-17 finding #5 cleared the detailed legacy implementation block from the active plan body because its imperative wording risked being implemented accidentally. The full legacy spec (default-off flag, `pre_commit install` via `sys.executable`, manifest `install_hooks` field, 5 subtests, etc.) is parked in `BACKLOG.md` as: **"Direct `--install-hooks` flag with target-venv creation"** — trigger: user requests one-step bootstrap-with-hooks for a common workflow. No plan-body details kept here.

**Tests** (`tests/test_install_hooks.py`) — PR #1 ships ONE test (Codex iter-16 finding #1 + iter-17 finding #2):

| Subtest | Asserts |
|---|---|
| `test_generated_install_hooks_uses_target_venv` | Bootstrap into a git-initialised tempdir, run `make install` then `make install-hooks` inside the target. Assert: (a) `.git/hooks/pre-commit` exists. (b) **Ownership check (Codex iter-17 finding #2 — `head -1` was wrong because real pre-commit hooks start with a shell shebang)**: the resolved absolute path to the target project's `venv/bin/python` appears SOMEWHERE in the hook file's contents (grep, not first-line). (c) **Negative ownership check**: the resolved absolute path to the skill repo's `venv/bin/python` does NOT appear anywhere in the hook file — proves the hook is scoped to the target project, not the skill repo. Closes the iter-16 imp-3 + iter-17 finding #2. |

**Acceptance gate**: `test_generated_install_hooks_uses_target_venv` green. PR #1's Subsystem F is effectively "remove the bootstrap flag, rely on the generated `make install-hooks` target" — a smaller scope than the original; the deeper hook-install ergonomics (failure status blocks, manifest tracking, etc.) belong to the parked follow-up.

## Skill repo's own `make check`

The skill repo's `Makefile` matches Boxette's pattern (closes Codex iter-5 finding #3 — bare `pip`/`pytest`/`ruff`/`pre-commit` would use whatever's on global PATH, defeating the "same gate" claim and tripping on the system `python3` being 3.9.6 vs `python3.12` available separately):

```makefile
PYTHON ?= ./venv/bin/python

.PHONY: help venv install install-hooks test lint format check

help:           ## list all targets with descriptions (Codex iter-11 finding #2)
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

venv:                          ## create venv with python3.12
    @test -d venv || python3.12 -m venv venv

install: venv                  ## install dev deps into venv (does NOT register hooks — see install-hooks)
    $(PYTHON) -m pip install -r requirements-dev.txt
    @echo "next step: 'make install-hooks' if this is a git repo"

install-hooks:                 ## install pre-commit hooks (requires .git/; safe to skip in non-git tempdirs)
    @test -d .git || { echo "skipping: not a git repo"; exit 0; }
    ./venv/bin/pre-commit install
    ./venv/bin/pre-commit install --hook-type pre-push

test:       ## run pytest via venv
    $(PYTHON) -m pytest -v

lint:       ## ruff check + format-check via venv
    $(PYTHON) -m ruff check .
    $(PYTHON) -m ruff format --check .

format:     ## auto-fix lint + apply format via venv
    $(PYTHON) -m ruff check --fix .
    $(PYTHON) -m ruff format .

check: lint test  ## CI-equivalent — all tool invocations go through $(PYTHON)

# Plus the three review targets — hand-written at PR #1 to be byte-identical
# to what `shared/Makefile.review.tmpl` renders with the skill repo's own
# context (closes Codex iter-5 finding #5 — see tests/test_selftest_overlap.py)
```

The skill repo's `requirements-dev.txt` (concrete pins per Codex iter-6 finding #4 — matches Boxette where applicable, deliberate choice elsewhere):

```
ruff==0.15.12
pytest>=8.0,<9
pre-commit>=3.7,<5
jinja2>=3.1,<4
pyyaml>=6.0,<7
```

CI workflow `.github/workflows/ci.yml` runs `make check` on push and on every PR. This is the same gate the skill produces for bootstrapped projects.

**Acceptance gate**: `cd /Users/sandeep/Desktop/Code/dev-project-for-non-developers && make check` green locally; CI green on the PR.

## Risks + mitigations (PR-#1-specific)

| Risk | Mitigation |
|---|---|
| PR #1 doesn't have CI on its first push (workflow file is part of what it ships) | Expected and documented. `claude[bot]` review may skip on PR #1 itself — the third+-doc-only-PR pattern from Boxette. Codex auto-review may also skip. Reviewers run locally via `make check` + smoke walk + plan-review loop. From PR #2 onward CI runs on every push. |
| Hand-written first-class copies of workflow files (Bucket 3) drift from templates (Bucket 2) | **PR #1 in scope (5 overlap checks per iter-6 finding #2)**: `tests/test_selftest_overlap.py` diffs rendered template output against the committed first-class copies for 5 deterministic checks: `.editorconfig`, `claude-review.yml`, `pull_request_template.md`, `docs/plans/README.md`, AND the **review-section block of `Makefile`** (extracted by sentinel-comment markers, diffed against the rendered `shared/Makefile.review.tmpl`). The Makefile review-section row is mandatory because PR #2 self-hosts the bidirectional review loop and needs the dogfood Makefile's review/preflight commands to match the template byte-for-byte. **Parked for follow-up**: broader `make selftest-bootstrap` Makefile wrapper covering the non-deterministic Bucket-3 files (rest of Makefile, pyproject.toml, AGENTS.md, CLAUDE.md, CONTRIBUTING.md). |
| `bootstrap.py` SIGTERM-mid-apply test flaky on slow CI | **Deterministic sync via sentinel file (Codex iter-6 finding #3 — corrected from iter-5; polling for `.bootstrap-tmp` was racy)**: bootstrap recognises `DEV_PROJECT_SETUP_PAUSE_AFTER_FIRST_WRITE=<sentinel-path>` env var; after manifest fsync + first file rename, touches sentinel then blocks. Test waits for sentinel, sends SIGTERM, runs `--restore`, asserts byte-identical rollback. No polling on transient artifacts. |
| `pre-commit install` subprocess test environment dependency (historical from iter-6) | Obsoleted by iter-17 finding #1 + #5: the only Subsystem F test in PR #1 (`test_generated_install_hooks_uses_target_venv`) runs `make install-hooks` end-to-end as a subprocess — no monkey-patching needed. `pre-commit` is still a pinned dev dep so it's installed when CI runs `make install`. |
| Jinja2 dependency adds a runtime cost to bootstrap | Pinned `jinja2>=3.1,<4` in `requirements-dev.txt`; `bootstrap.py` shim special-cases `-h`/`--help` BEFORE the jinja2 import (Codex iter-12 finding #4 — `--help` works even when `make install` hasn't been run, important for first-time discovery). Other invocations DO import jinja2 (small runtime cost; the lazy-import optimisation in the original wording was unnecessarily clever). Canonical check order documented in the Deployment section. |
| Restore manifest contains base64-encoded content snapshots — large files balloon manifest size | PR #1 only writes template files (all well under 10KB each); manifest size budget < 1MB. Document the limitation. A future skill PR adds a "manifest skips files larger than N bytes" flag — parked. |

## Verification (acceptance criteria for THIS PR)

Split into two phases per Codex iter-17 finding #7 (the new repo currently has only README + .gitignore + this plan — most gates only become runnable AFTER PR #1's code lands):

### Phase 1 — pre-implementation evidence (runnable now, before code is written)

1. **Plan-review loop** run on THIS plan via Boxette's `make review-plan` (the bootstrap exception — this repo doesn't self-host the loop yet). Stopping rule per merged plan / `docs/plans/README.md`: triage rule applied; remaining imp-3 findings either folded or explicitly accepted-as-trade-off and surfaced to human approval.
2. **Active-surface consistency check** (closes Codex iter-17 finding #4 + iter-18 finding #1) — manual grep before opening the PR, expanded to cover ALL active public surfaces, not just the plan file:
   ```bash
   grep -rn --include='*.md' --include='*.tmpl' --include='*.py' \
     "install-hooks\|install_hooks\|pre_commit" \
     README.md SKILL.md docs/ languages/ shared/ bootstrap.py bootstrap_lib/ 2>/dev/null
   ```
   (The grep also covers `docs/plans/2026-05-15-skill-pr1-minimal-python-bootstrap.md`, but the broader sweep catches drift in README/usage/SKILL/templates/dogfood docs — closes iter-18 finding #1 where iter-17's narrow grep would have missed the README's stale `--install-hooks` advertisement.)
   Categorise every match as one of:
   - **active**: refers to the GENERATED `make install-hooks` target or to `pre_commit` as a generated-project dependency (legitimate)
   - **legacy/backlog**: lives inside a clearly-marked legacy section, evidence-table row, or BACKLOG entry (historical record, OK)
   - **forbidden**: appears in an ACTIVE PR #1 public surface (CLI flag list, manifest schema, deployment-contract check order, test list, README adoption-safety line, docs/usage.md scope, SKILL.md, dogfood docs) — must be cleaned up
   Forbidden matches → fix before opening the PR. Same check for any other "removed feature" in future iterations: the surface-drift failure mode this catches (iter-17 finding #1; iter-18 finding #1 re-caught it for README) is exactly what the triage rule's "fold completely" obligation prevents structurally — but doing the grep is the safety net.
3. **MANDATORY human-approval gate** satisfied (Sandeep replies `approve` after seeing the final-plan summary)

### Phase 2 — post-implementation gates (runnable only after PR #1's code lands)

All gates below require the skill repo's `Makefile`, `pyproject.toml`, and test suite to exist — those are themselves shipped in PR #1, so these gates are pre-merge-of-PR-#1, post-write-of-PR-#1-code.

4. All six per-subsystem acceptance gates green:
   - A. `tests/test_bootstrap_cli.py`, `test_manifest.py`, `test_atomic_writes.py`, `test_restore.py`, `test_sigterm_mid_apply.py`, `test_path_safety.py` all pass
   - B. `tests/test_python_templates.py` + `test_smoke_python_generated.py` pass
   - C. `tests/test_shared_templates.py` passes
   - D. `tests/test_makefile_review_targets.py` + `test_preflight_tooling.py` + `test_env_scrubber.py` pass
   - E. `tests/test_github_review_modes.py` passes (3 parametrised modes + default-is-none subtest)
   - F. `tests/test_install_hooks.py` passes (1 subtest: `test_generated_install_hooks_uses_target_venv`. Codex iter-16 finding #1 removed the bootstrap `--install-hooks` flag; the 5 legacy subtests are parked for a follow-up PR.)
   - Selftest drift: `tests/test_selftest_overlap.py` passes (5 deterministic overlap checks — 4 files + Makefile review-section block, per iter-6 finding #2)
5. Skill repo's `make check` green locally
6. **`make doctor` smoke** (closes Codex iter-17 finding #6, corrected per iter-18 finding #2): `make help` lists `doctor`; running `make doctor` with all core tools on PATH exits 0; running with `python3.12` shimmed off PATH (controlled `PATH=` containing only `/usr/bin:/bin` plus a stub `git`, NO `python3.12`) exits non-zero with a clear "missing dep: python3.12" message; same for `git`. Optional-tool absence (`claude` / `codex` not on PATH) produces an advisory note but does NOT fail. **`make` itself is NOT tested as "missing" — it's a hard prerequisite documented in README; you cannot run `make doctor` to diagnose missing `make` (circular), and on macOS `/usr/bin/make` always exists so the shim is impossible to construct cleanly.**
7. Generated-project smoke walk: dry-run produces expected file list, `--apply` succeeds, `cd <smoke-dir> && make install && make check && make run` all green; `make install-hooks` registers hooks scoped to the target venv (`test_generated_install_hooks_uses_target_venv` covers this)
8. `make preflight-review-tooling` is **optional/manual** evidence (Codex iter-10 finding #2 — making it a hard pre-merge gate would tie PR readiness to local paid CLIs + login state, exactly the hidden dependency the shim tests were meant to avoid). Run it: (a) when bumping the Claude/Codex baseline versions; (b) before enabling the local review targets for a new machine. Routine PR gating relies on shim-based `test_preflight_tooling.py` + the plan-review evidence from Phase 1
9. Draft PR opened from branch `feat/skill-pr1-minimal-python-bootstrap`

Post-merge: PR #2 (Node-TS) is unblocked; it can reuse the now-shipped Bucket 1 and Bucket 2.shared/ verbatim, only adding `languages/nodejs/`.

## Iteration log (this plan)

| Iter | Findings | Verdict |
|---|---|---|
| 1 | 5 (4× importance-3, 1× importance-2) | do not implement yet — all 5 folded into iter-2 draft |
| 2 | 5 (3× importance-3, 2× importance-2) | do not implement yet — all 5 folded into iter-3 draft |
| 3 | 6 (3× importance-3, 3× importance-2) | do not implement yet — all 6 folded into iter-4 draft |
| 4 | 6 (3× importance-3, 2× importance-2, 1× importance-1) | do not implement yet — all 6 folded into iter-5 draft |
| 5 | 6 (3× importance-3, 2× importance-2, 1× importance-1) | do not implement yet — all 6 folded into iter-6 draft |
| 6 | 4 (1× importance-3, 3× importance-2) | do not implement yet — all 4 folded into iter-7 draft |
| 7 | 4 (2× importance-3, 2× importance-2) | do not implement yet — all 4 folded into iter-8 draft |
| 8 | 4 (2× importance-3, 2× importance-2) | do not implement yet — all 4 folded into iter-9 draft |
| 9 | 4 (2× importance-3, 2× importance-2) | do not implement yet — all 4 folded into iter-10 draft |
| 10 | 5 (1× importance-3, 3× importance-2, 1× importance-1) | do not implement yet — all 5 folded into iter-11 draft (imp-3 count halved from iter-9) |
| 11 | 4 (1× importance-3, 2× importance-2, 1× importance-1) | do not implement yet — all 4 folded into iter-12 draft |
| 12 | 4 (2× importance-3, 2× importance-2) | do not implement yet — all 4 folded into iter-13 draft |
| 13 | 5 (2× importance-3, 3× importance-2) | do not implement yet — all 5 folded into iter-14 draft |
| 14 | 5 (2× importance-3, 2× importance-2, 1× importance-1) | do not implement yet — all 5 folded into iter-15 draft |
| 15 | 3 (1× importance-3, 2× importance-2) | do not implement yet — all 3 folded into iter-16 draft (imp-3 count back to 1) |
| 16 | 4 (1× importance-3, 2× importance-2, 1× importance-1) | all 4 folded; intended to halt for approval but user surfaced new Codex findings before approving |
| 17 | 7 (2× importance-3, 4× importance-2, 1× importance-1) | **first iteration to use the triage rule explicitly** — all 7 triaged as (a) fold (none rose to (b)/(c)/(d) because most were cleanup from incomplete iter-16 fold). Findings #1, #5 were the same root cause (residue from iter-16's `--install-hooks` removal). Finding #4 introduced the "active-surface consistency check" — a structural prevention of this exact failure mode. Loop halts at iter-17 pending approval |
| 18 | 4 (0× importance-3, 3× importance-2, 1× importance-1) | **stopping rule met** — Codex verdict "ready after minor edits"; zero imp-3. User chose to fold all 4 + skip re-review. All 4 triaged as (a) fold — none touch CLI surface or safety contract; all are internal hardening |
| 19 | 0 (Codex review skipped per user direction; iter-18 verdict was already "ready after minor edits") | folded iter-18's 4 findings into plan body; ready for implementation |
| 20 | 1 (Codex GitHub auto-review on the open PR; 1× P1 / imp-2) | folded — restore decision table missed the "overwritten file missing" case; current code unconditionally restored, which would undo a user deletion. Fix: SKIP with warning. Test: `test_d_double_prime_user_deleted_overwritten_file_not_restored`. Plan table now has the 4th overwritten-row explicitly. |
| 21 | 2 (Codex re-review on the iter-20 fold commit; 1× P1 + 1× P2 / imp-2 + imp-2) | folded — (1) restore's write-back used bare `write_bytes` instead of `atomic_write`, breaking crash-safety symmetry with apply; (2) manifest path used second-level timestamp precision, two `--apply` runs in the same second would collide and clobber. Fixes: route restore write-back through `bio.atomic_write` (still chmod after), switch `manifest_path()` to `tempfile.mkstemp(prefix=..., suffix=".json")`. Tests: extended `test_a_overwritten_files_restored` to assert no `.bootstrap-tmp` leftovers post-restore; new `test_manifest_path_is_unique_under_rapid_calls` proves 20 rapid calls produce 20 distinct paths. |
| 22 | 2 (Codex re-review on the iter-21 fold commit; 1× P1 + 1× P2 / imp-2 + imp-2) | folded — (1) if `_apply` writes some files and a later `atomic_write`/`chmod` raises, the failure path only printed `apply failed: <e>` — manifest path + restore hint were lost so user had partial state + no rollback command; (2) restore CLI ignored the `restore_from_manifest` return tuple — when `n_rejected > 0` (path-safety violation aborted the restore), CLI still returned 0 so scripted rollback wrongly reported success. Fixes: split `_apply` into `_prepare_apply` (writes manifest) + `_apply_writes` (does file writes); `main()` keeps `manifest_p` across the write phase and prints the rollback hint on failure. Restore branch now returns `1 if n_rj > 0 else 0`. Tests: `test_partial_apply_failure_still_prints_restore_hint` (monkey-patches `io.atomic_write` to raise on the 3rd call, asserts manifest path + rollback hint in stderr); `test_restore_returns_nonzero_when_path_safety_rejects` (hand-crafted manifest with `/tmp/outside.txt`, asserts exit non-zero). |
| 23 | 4 (Codex re-review on the iter-22 fold commit; 2× P1 + 2× P2) | mixed triage — (1) P1 manifest.py:186 "restore not atomic" REJECTED as stale re-flag (iter-21 fold already routed write-back through `bio.atomic_write` at line 185; finding text contradicts current code); (2) P1 cli.py:279 "no restore hint on partial-apply" REJECTED as stale re-flag (iter-22 fold already prints manifest path + rollback hint at lines 272-278 before the `return 1`); (3) P2 io.py:47 "orphan .bootstrap-tmp on failure" FOLDED — `atomic_write`'s `finally` only discarded from `_pending_tmp`; signal/atexit cleanup couldn't see it; if write/fsync/replace raised, the orphan was left on disk; fix tracks a `renamed` flag and unlinks the tmp on failure; (4) P2 io.py:45 "Windows portability" FOLDED — replaced `os.rename` with `os.replace` so `--overwrite-existing` works cross-platform (rename fails on Windows when target exists; replace is atomic on POSIX and replaces on Windows). Tests: `test_atomic_write_overwrites_existing_target` + `test_atomic_write_cleans_tmp_on_write_failure` (monkey-patches `os.fsync` to raise, asserts no `.bootstrap-tmp` artifacts remain). |

## Evidence table — what was folded and where

| Iter | Importance | Finding | Action |
|---|---|---|---|
| 1 | 3 | `scripts/run-with-clean-env.py` referenced from generated `Makefile.review.tmpl` but never emitted into generated projects — review targets dead-on-arrival | Added `shared/scripts-run-with-clean-env.py.tmpl` to Bucket 2 (mode 0755 via post-write `os.chmod`); Makefile target reference changed to `$(CURDIR)/scripts/run-with-clean-env.py` (relative to bootstrapped project, not skill repo). Subsystem D acceptance gate now includes a generated-project smoke that bootstraps + runs preflight + runs one review target with shim CLIs |
| 1 | 3 | Restore semantics contradicted no-removal guarantee — restore must remove created files for byte-identical rollback, but plan said bootstrap never removes | Split the rule: `--apply` is no-removal; `--restore` may delete entries with `existed_before=false`. Added `sha256_after` field to manifest so restore can detect user edits and skip the delete with a warning. Restore refuses to touch unlisted files. `tests/test_restore.py` expanded to 4 subtests (overwritten / created / unlisted-ignored / user-modified-preserved) |
| 1 | 3 | `preflight-review-tooling` only checked `command -v` + version warning; couldn't catch CLI flag drift | Rewrote preflight to exec both CLIs with the EXACT flags the review targets use (`codex exec --sandbox read-only --output-last-message`, `claude --print --permission-mode plan --add-dir --output-format text`). Failure → exit non-zero. Version-mismatch stays advisory (WARN only). `tests/test_preflight_tooling.py` now has 3 layers: missing CLI / flag-smoke failure / version-drift advisory |
| 1 | 3 | `--github-review` default of `claude` would emit a workflow requiring `CLAUDE_CODE_OAUTH_TOKEN` for every bootstrap — hidden secret dependency | Changed CLI default to `none` (matches merged plan's "default for an experimental project"); explicit `--github-review=claude` is opt-in. Skill repo's own dogfood files stay at `claude` mode as a deliberate per-repo choice. Added `test_default_mode_is_none` subtest asserting no workflow / no checklist text when flag omitted |
| 1 | 2 | Selftest drift detection deferred — two sources of truth on day one with no diff check | Added `tests/test_selftest_overlap.py` to PR #1 scope, initially covering 4 deterministic files (`.editorconfig`, `claude-review.yml`, `pull_request_template.md`, `docs/plans/README.md`); iter-5 added the Makefile review-section block as a 5th check (see iter-5 evidence). Test renders template against fixed context, diffs against committed dogfood file. Broader-coverage Makefile wrapper stays parked for follow-up |
| 2 | 3 | Restore manifest path entries could escape `target_root` (e.g. `../outside.txt` or `/etc/passwd`) and let a corrupted/malicious manifest write/delete outside the project | Added path-safety validation step in restore: resolve `(target_root / entry.path).resolve()`, reject absolute paths, `..` traversal, symlinks-out, and any resolved-path-outside-target. Restore aborts before any filesystem action when invalid. `tests/test_restore.py` grows to 6 subtests with explicit (e) `../outside.txt` and (f) `/tmp/outside.txt` cases |
| 2 | 3 | `sha256_after` durability not crash-safe — a SIGTERM after `os.rename` but before manifest update would leave a created file with no hash recorded | Manifest is now computed and persisted in full BEFORE the first write — both `sha256_before` (from pre-apply inspection) and `sha256_after` (from deterministic Jinja2 rendering of the planned output bytes) are recorded up front. Manifest is `fsync`'d before any `os.rename`. Restore-after-SIGTERM path documented: matching-hash files deleted, non-matching files skipped with warning. `tests/test_sigterm_mid_apply.py` extended to assert byte-identical rollback (not just absence of `.bootstrap-tmp` artifacts) |
| 2 | 3 | `make check` would invoke real Claude/Codex CLIs (live "with real CLIs available locally, assert exit 0" path); test gate depends on installed AI tools + consumes subscription quota | `tests/test_preflight_tooling.py` is now fully shim-based — 4 layers (missing CLI / flag-smoke failure / version-drift advisory / shim success). Real-CLI invocation is a manual `make preflight-review-tooling` step; opt-in live test `test_preflight_live_optional` gated behind `RUN_LIVE_AI_PREFLIGHT=1` (skipped in CI/regular `make check`) |
| 2 | 2 | `--out` "created if missing" contradicted dry-run's "no writes" — smoke test allowed target dir to exist after dry-run | Tightened spec: `--out` is created ONLY during `--apply`; dry-run / `--diff` are filesystem-pure. Smoke-test code rewritten to use `tmp_path` fixture + precondition + post-assertion that target does NOT exist after dry-run |
| 2 | 2 | `shared/` count drift: Scope said 12 files (added `scripts-run-with-clean-env.py.tmpl`) but Subsystem C still said "all 11 files" and its mapping table omitted the new template | Subsystem C wording updated to 12; mapping table extended with the new row (cross-referencing Subsystem D where it's first introduced) |
| 3 | 3 | Existing-file collision policy under-specified: `--apply` could silently overwrite Makefile/CI/docs at any pre-existing target | Added explicit collision-policy section: `--apply` aborts with exit 2 if any target file exists, unless `--overwrite-existing` consent flag is passed. New CLI flag added; `test_apply_aborts_on_collision_without_flag` subtest added to `test_bootstrap_cli.py`. Per-file skip/diff/abort dialog parked for a follow-up (would need `--decisions` JSON or interactive mode) |
| 3 | 3 | Generated-project smoke ran `make check` without `make install` first — would rely on parent test env's ruff/pytest | Smoke walk now runs `make install` then `make check`. `languages/python/Makefile.tmpl` clarified: `install` creates per-project `venv/` and installs `requirements-dev.txt`; all tooling invocations go through `venv/bin/...` so fresh-clone CI gets the pinned toolchain |
| 3 | 3 | Restore path-safety claimed symlink-out coverage but test matrix only had `../` and `/` cases | Added subtest (g) `test_restore_rejects_symlink_escape`: target/link → /tmp/outside-dir, manifest entry under link/, assert restore aborts pre-action and outside dir is unchanged. Total restore subtests now 7 |
| 3 | 2 | Selftest-drift status contradictory: risk-row said "parked for PR #1" but the test was in PR #1 scope | Risk-row rewritten: narrow `tests/test_selftest_overlap.py` is PR #1 in-scope (4 deterministic files); broader `make selftest-bootstrap` Makefile wrapper for non-deterministic files is parked. Single source of truth for the decision |
| 3 | 2 | Install-hook failure left a half-success state with no clear recovery instruction | Added `test_install_hooks_failure_status_block`: assert exit non-zero AND stderr contains manifest path, restore command, "hooks not covered by manifest" caveat, and which install invocation failed with its exit code |
| 3 | 2 | Merged plan's `docs/usage.md` silently dropped from PR #1 scope | Added `docs/usage.md` to Bucket 3 (skill repo root, hand-written): when-to-use, full CLI surface, safety contract, restore walkthrough, bootstrap-exception note. `docs/upgrading.md` + `docs/design-notes.md` from the merged plan's tree explicitly parked |
| 4 | 3 | Restore could clobber user edits to OVERWRITTEN files — `existed_before=true` path wrote `content_before_b64` back unconditionally; protection only existed for created files | Symmetric protection: restore now checks current SHA-256 against `sha256_after` for BOTH overwritten and created cases. Mismatch → SKIP with warning. Added subtest (d') `test_restore_overwritten_file_user_edit_preserved`; total restore subtests now 8 |
| 4 | 3 | CI workflows specified to "run `make check`" without `make install` first — `make check` assumes ruff/pytest pre-installed; fresh CI runners would fail | Both generated `ci.yml.tmpl` AND skill repo's own `.github/workflows/ci.yml` rewritten to sequence `checkout → setup-python (3.12) → make install → make check`. `tests/test_python_templates.py` asserts the step ordering in rendered ci.yml |
| 4 | 3 | `claude-review.yml.tmpl` derived verbatim from Boxette's workflow whose prompt references Telegram bot, payments, API drift, PINFL — domain leakage into every generated project's PR reviewer | Subsystem C mapping table now requires generic-prompt rewrite: Claude reads generated `AGENTS.md`/`CLAUDE.md` for project risks rather than baked-in domain. Added no-Boxette-isms scan to `tests/test_shared_templates.py` (fails on `Boxette`, `Telegram`, `bot/`, `PINFL`, `customs`, `signup`, `payment`, etc. case-insensitive) |
| 4 | 2 | Preflight bypassed `scripts/run-with-clean-env.py` wrapper and omitted Codex's `-C "$(CURDIR)"` — could pass while the real review target fails | Preflight Makefile target rewritten to invoke wrapper for both codex and claude flag-smoke commands, with `-C "$(CURDIR)"` matching the real codex review target. `tests/test_env_scrubber.py` extended to assert wrapper is invoked during preflight (via shim that records its argv) |
| 4 | 2 | "Plan + code in one PR" stated up front but Bucket 3 didn't list the plan file itself — implementer might commit only code | Added `docs/plans/2026-05-15-skill-pr1-minimal-python-bootstrap.md` (this file) to Bucket 3 explicitly; documented that it remains committed permanently as institutional memory per Boxette's `docs/plans/README.md` |
| 4 | 1 | `test_install_hooks.py` had 5 subtests in the table but "all four subtests green" in the acceptance gate | Acceptance text changed to "all five subtests green"; cross-reference in main Verification section updated to (5 subtests) |
| 5 | 3 | `--restore <manifest>` documented with no other args, but argparse marked `--language` / `--project-name` / `--out` as required globally — rollback command from a failed apply would fail before restore runs | Split CLI surface into two top-level modes (render/apply vs restore-standalone); restore mode refuses render-args. Added `test_restore_does_not_require_language_project_or_out` to `test_bootstrap_cli.py` |
| 5 | 3 | SIGTERM mid-apply test polled for a transient `.bootstrap-tmp` artifact — racy on fast machines; could pass without actually testing interruption | Introduced `DEV_PROJECT_SETUP_PAUSE_AFTER_FIRST_WRITE=<sentinel>` test-only env var: bootstrap touches sentinel after manifest fsync + first rename, then blocks. Test waits for sentinel deterministically, sends SIGTERM, runs restore, asserts byte-identical rollback. Production code path is unaffected when env var unset |
| 5 | 3 | Skill repo's own dogfood Makefile used bare `pip` / `pytest` / `ruff` / `pre-commit` — bypassed `venv/`, would pick up global tools; on this workspace `python3` is 3.9.6 vs `python3.12` separate | Dogfood Makefile rewritten to match Boxette's pattern: `PYTHON ?= ./venv/bin/python`; `venv` target creates with `python3.12`; install / test / lint / format all invoke via `$(PYTHON) -m ...` and `./venv/bin/pre-commit`. Closes the "same gate" claim properly |
| 5 | 2 | Skill repo's own `scripts/run-with-clean-env.py` invoked directly as executable but Bucket 3 didn't require committed mode 0755 | Bucket 1 entry for the script now explicitly says "committed mode 0755"; matches the generated-project copy's post-write chmod |
| 5 | 2 | PR #2's self-hosted bidirectional review depends on dogfood Makefile review section matching `shared/Makefile.review.tmpl`; selftest table didn't cover it | Selftest table row added for the review-section block of the Makefile: extract the lines from `# ── Plan-review automation` to end of `preflight-review-tooling` via a sed range / sentinel comment, render the template, assert equality. Drift fails the test |
| 5 | 1 | Context wording said the repo "currently contains only README.md + .gitignore" but the plan file now exists too | Reworded to "before this plan was added, the new repo contained only..." — pre-state, not current state |
| 6 | 3 | `--install-hooks` invoked bare `pre-commit` subprocess — depended on global PATH; test_install_hooks_runs_after_writes was marked skippable when pre-commit not on PATH (weakened acceptance gate) | Rewrote install path to `subprocess.run([sys.executable, "-m", "pre_commit", "install", ...])`. `pre-commit` is now a hard pinned dep of the bootstrap env (in skill repo + generated project's `requirements-dev.txt`). Test is path-scrubbed (`PATH=/usr/bin:/bin`) and NEVER skipped — proves install goes through `sys.executable -m pre_commit`, not any global binary |
| 6 | 2 | Selftest count drift (4 vs 5): iter-5 added Makefile review-section row but risk table + verification section still said "4 deterministic files" | Updated risk-table row + verification bullet to "5 deterministic overlap checks"; iter-1 evidence row now mentions iter-5's 5th check addition. Single source of truth for the count |
| 6 | 2 | Risk table's SIGTERM-mid-apply mitigation regressed to the polling-for-`.bootstrap-tmp` model that iter-5 explicitly rejected | Risk-table row rewritten to the sentinel-based flow: `DEV_PROJECT_SETUP_PAUSE_AFTER_FIRST_WRITE=<sentinel-path>`, bootstrap touches sentinel + blocks after manifest fsync + first rename, test waits for sentinel deterministically. Matches Subsystem A test spec |
| 6 | 2 | `requirements-dev.txt.tmpl` and skill repo's `requirements-dev.txt` had `<pinned>` placeholders for pytest / pre-commit / pyyaml — deferred a toolchain decision past the plan-review gate | Concrete pins chosen at plan time, matching Boxette where applicable: `ruff==0.15.12`, `pytest>=8.0,<9`, `pre-commit>=3.7,<5`, `jinja2>=3.1,<4`, `pyyaml>=6.0,<7`. Template test asserts no `<pinned>` placeholder remains in rendered output |
| 7 | 3 | Rollback command everywhere said `python bootstrap.py --restore ...` — but `python` is not on PATH on this Mac (`python3`=3.9.6, `python3.12` is the only valid choice). The documented rollback path would fail exactly when needed | Replaced all literal `python` references with `sys.executable`/`shlex.quote(sys.executable)` in bootstrap output formatting AND in test subprocess invocations. Tests assert the printed restore command starts with the current interpreter's path, not the bare string `python` |
| 7 | 3 | Generated-project smoke only exercised `review-plan-by-codex`, not `review-plan-by-claude` — the Claude direction (stdout redirect to output file, different flag set) was untested; PR #2's self-hosted bidirectional loop would not be validated | Added second smoke invocation: `make review-plan-by-claude` with a shim `claude` that prints canned text; assert the output file exists at the per-reviewer path `/tmp/plan-review-<slug>-by-claude-iter-1.md`. Catches shell-redirect bugs, wrong output-variable references, wrapper-path issues |
| 7 | 2 | `--diff` was promised as the inspection path before consenting to overwrite, but tests only asserted "`--diff` implies `--dry-run`" — no verification that real diff output is produced, no writes happen, no manifest is created, no target dir is created | Added `test_diff_emits_unified_diff_no_writes` in `test_bootstrap_cli.py`: asserts (a) `--- ` / `+++ ` headers + actual `-`/`+` diff lines in stdout, (b) `--out` not created when absent before, (c) no `.bootstrap-tmp` artifacts, (d) no manifest written to `/tmp/` |
| 7 | 2 | Path-safety only validated during restore — a renderer mapping bug like `../AGENTS.md` would write outside `target_root` during apply before restore ever ran | Added shared `bootstrap_lib/paths.py` with `validate_target_path(target_root, rel_path)`; called from `render.render_all` BEFORE manifest is written. New `tests/test_path_safety.py` covers apply-side: absolute path / `..` / symlink-escape rejected pre-write |
| 8 | 3 | Rollback command still hard-coded `bootstrap.py` (relative path) — only works from skill repo cwd; would fail when bootstrap is run via absolute path from a target project | Rollback hint now formats with `f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} --restore ..."`. Test added: invoke bootstrap from a different cwd via absolute path, capture printed restore command, exec it from yet another cwd via `shell=True`, assert exit 0 — proves the hint is fully self-contained |
| 8 | 3 | Apply-side path-safety test monkey-patched `render_all` itself — if the check lives INSIDE `render_all`, monkey-patching skips it and the test gives false confidence | Validation now runs at TWO layers: inside `render_all` (catches accidental template-map bugs) AND in `cli.py`'s apply-planning pass over the final `{rel_path: bytes}` map. Test explicitly bypasses the renderer-layer check via monkey-patch and asserts the CLI-layer check still catches it — proves the real safety boundary is at the CLI layer |
| 8 | 2 | Generated `make install` ambiguous about hook installation — `install` calling `pre-commit install` would fail in non-git tempdirs (smoke test cwd) and conflicts with `--install-hooks` flag's explicit-opt-in | Split: generated `make install` does NOT touch `.git/hooks/` (prints "next step: `make install-hooks` if this is a git repo"); separate `make install-hooks` target runs `pre-commit install` with a `test -d .git` guard. Template test asserts the separation |
| 8 | 2 | `/tmp` manifest absence assertion brittle — `/tmp/` may contain stale `dev-project-setup-restore-*.json` from prior runs | Manifest path now uses `tempfile.gettempdir()` (honours `TMPDIR`/`TEMP`/`TMP`); test injects isolated `TMPDIR=<pytest-tmp_path>` and asserts no manifest file lands there |
| 9 | 3 | `Makefile.review.tmpl` mixed `$(PWD)` and `$(CURDIR)` — `PWD` is env-inherited and can be stale under `make -C <dir>`, causing review targets to point at the wrong repo | Replaced every `$(PWD)` with `$(CURDIR)` throughout `Makefile.review.tmpl`, the preflight target, and the in-plan code samples. Added stale-PWD robustness subtest to `test_makefile_review_targets.py`: `make -C <fixture>` from a different cwd with deliberately stale `PWD`; assert shims receive the fixture path |
| 9 | 3 | Deployed-skill invocation contract undefined — runtime deps (`jinja2`, `pre_commit`) only appeared as dev deps, no statement of which interpreter resolves them when invoked via `~/.claude/skills/dev-project-setup/` | Added "Deployment / invocation contract" section. Single supported path: `./venv/bin/python bootstrap.py` after a one-time `make install`. Bootstrap detects missing `jinja2` / `pre_commit` and exits 2 with "missing dep: re-run 'make install' in <skill_root>" using the absolute resolved skill-root path. `requirements-dev.txt` marks runtime entries inline. Console-script packaging parked. New `tests/test_deployed_invocation.py` proves the path works from a non-skill-root cwd |
| 9 | 2 | Bucket 1 manifest.py row hard-coded `/tmp/...` even after iter-8 architecture spec moved to `tempfile.gettempdir()` — implementers working file-by-file would follow the stale instruction | Bucket 1 row updated to match Architecture: `<tempfile.gettempdir()>/dev-project-setup-restore-<ISO8601>.json`. Single source of truth |
| 9 | 2 | `--project-name` had no validation rule — spaces, `..`, uppercase, empty string would silently produce a project that fails later at install/import/CI | Specified regex `^[a-z][a-z0-9-]*$` (lowercase + digits + hyphens, leading letter, no path separators). cli.py rejects on violation with exit 2 + documented error. Python import name derived by `-` → `_`. Added parametrised `test_project_name_validation` with 4 positive and 6 negative cases |
| 10 | 3 | Deployment negative test ("system python3 without jinja2") was non-hermetic — `python3` could be 3.9.6 (fails earlier with SyntaxError on 3.12-only syntax) or could already have jinja2 from global site-packages. Test couldn't deterministically exercise the missing-dep path | Two-part fix: (a) Make `bootstrap.py` a Python-3.6-compatible shim — version-check and dep-import-check BEFORE importing 3.12-syntax `bootstrap_lib/*.py`; (b) Test creates a hermetic temp venv with `python3.12 -m venv` and NO requirements installed, then invokes the shim — exits 2 with "missing dep" deterministically. Separate test for wrong-interpreter (python3.9 if available; otherwise skipped) asserts "requires Python 3.12+" |
| 10 | 2 | Verification step listed `make preflight-review-tooling` green with REAL `claude`+`codex` as a hard pre-merge gate — exactly the hidden subscription dependency the shim tests were meant to remove | Demoted to optional/manual evidence: run when bumping CLI baselines or enabling local review targets on a new machine. Routine PR gating is shim-based `test_preflight_tooling.py` + the plan-review evidence already captured |
| 10 | 2 | Dogfood `AGENTS.md`/`CLAUDE.md`/`CONTRIBUTING.md` were excluded from selftest because they have overlays, but the no-Boxette-isms scan only ran against shared templates — overlay docs could still leak Telegram/payment/PINFL guidance and steer PR #2's self-hosted reviews wrongly | Added `tests/test_dogfood_doc_sanity.py`: same forbidden-terms scan as Subsystem C, applied to committed dogfood `AGENTS.md`/`CLAUDE.md`/`CONTRIBUTING.md`/pull_request_template.md. Allowlist for the plan files under `docs/plans/` (historical attribution to Boxette is intentional there) |
| 10 | 2 | Tests relying on monkey-patching didn't state whether they ran in-process or in a subprocess — across-subprocess monkey-patches would silently not exercise the intended failure paths | Added explicit "Test execution boundary" subsection: monkey-patch-dependent tests call `bootstrap_lib.cli.main(argv)` in-process; subprocess tests reserved for SIGTERM, deployed-invocation, runnable-from-elsewhere assertion, and smoke walks. For pre-commit subprocess failure: isolated PYTHONPATH with a fake `pre_commit` package, not a monkey-patch |
| 10 | 1 | Bucket 1 `cli.py` row didn't list `--overwrite-existing` or `--enable-smoke` flags that later sections required | Bucket 1 row updated to the full flag list; `docs/usage.md` acceptance now requires `--help` coverage of every documented flag; `tests/test_bootstrap_cli.py` asserts every flag is in `--help` output |
| 11 | 3 | Naive text-grep for `{{` / `}}` in rendered output would false-positive on legitimate GitHub Actions `${{ ... }}` tokens — would either fail valid workflow templates or pressure removing valid syntax | Switched to `Environment(undefined=jinja2.StrictUndefined)` — unresolved variables raise `UndefinedError` at render time, no text-grep needed. Tests assert render succeeds without `UndefinedError`. Rendered output can freely contain `${{ ... }}` since Jinja's default `{{ }}` delimiters don't match the `$`-prefixed form |
| 11 | 2 | `make help` was an acceptance requirement but `help` target wasn't listed in the Makefile.tmpl scope or shown in the dogfood Makefile snippet | Added `help` to both the generated `Makefile.tmpl` scope AND the dogfood Makefile snippet, with `.PHONY` declaration and the standard `grep -E ... ## description` recipe. Per-template test asserts `help` is listed in `make help` output |
| 11 | 2 | `--install-hooks` against a non-git `--out` would fail at hook install AFTER all files are written — predictable half-success state | Added pre-render precondition: `bootstrap.py --apply --install-hooks` checks `(target_root / ".git").exists()` BEFORE any render or write; if absent, exit 2 immediately with "run `git init` OR re-run without --install-hooks". New `test_install_hooks_aborts_when_not_git_repo` subtest |
| 11 | 1 | Verification said "dry-run produces expected file list" but the smoke test only asserted `--out` wasn't created — didn't actually check the printed file list | Smoke test now captures stdout and asserts the dry-run output contains every expected path (18 paths) AND does NOT contain `.github/workflows/claude-review.yml` (because default `--github-review=none`) |
| 12 | 3 | Restore was NOT byte-AND-tree-identical because the manifest tracked only files; empty parent dirs (`.github/workflows`, `docs/plans`, `scripts`, `tests`, `src`) created by apply would remain after restore, breaking `diff -r` byte-empty check | Added `created_directories: [str, ...]` to manifest top-level; restore removes them in reverse-depth order, only if empty AND inside `target_root`. Pre-existing dirs never touched. Added subtests (h) created-dirs-removed and (i) user-content-preserved-in-dirs to `test_restore.py` (total now 10) |
| 12 | 3 | File modes not tracked — `scripts/run-with-clean-env.py` chmod'd to 0755 after write, but manifest stored only hashes; overwriting a `0644` file with new bytes + new mode would leave the new mode behind on restore | Added `mode_before: int|null` and `mode_after: int` to each manifest entry. Apply runs `os.chmod(target, mode_after)` post-write. Restore for overwritten files writes content back AND `os.chmod(target, mode_before)`. Subtest (j) covers an overwritten-script mode-restore |
| 12 | 2 | Shim and CLI both had dependency checks but in unspecified order — `--apply --install-hooks` against a non-git target in an env missing `pre_commit` had two competing error paths | Canonical check order documented: help→version→jinja2→pre_commit→cli(main)→slug→.git→apply. Importance: import errors trump user-input errors (missing dep always wins over missing `.git`). New `test_canonical_check_order.py` with 5 parametrised branches |
| 12 | 2 | Risk table said `bootstrap.py --help` should not pay jinja2 import cost, but shim spec imported jinja2 before importing cli — `--help` before `make install` would error | Shim's first step (BEFORE jinja2 import) special-cases `-h`/`--help`: dispatches to argparse `--help` directly, mirroring the cli's flag list. Risk-table row rewritten to match. Test: hermetic temp venv WITHOUT jinja2 installed runs `bootstrap.py --help` and asserts exit 0 + help text printed |
| 13 | 3 | Restore decision table contradicted itself: "neither hash matches → write back" vs "sha256_after mismatch → skip" could clobber user edits | Replaced narrative with an explicit 6-row decision table (overwritten × 3 SHA states + created × 3 SHA states). Conservative rule: any mismatch with `sha256_after` AND not matching `sha256_before` → SKIP with warning, never clobber. `test_restore.py` subtest (j) extended to assert this for both partial-overwrite and user-edit paths |
| 13 | 3 | `--github-review={claude,both-docs}` required `github_owner` + `github_repo` substitution vars but CLI had no way to set them — greenfield projects couldn't use the flag | Added `--github-owner` and `--github-repo` CLI flags; cli.py requires both when `--github-review != none` and exits 2 with a clear message otherwise. Explicitly NOT auto-deriving from `git remote get-url origin` (brittle for greenfield, ambiguous with multiple remotes). New parametrised test in `test_bootstrap_cli.py` covers 3 cases: mode=none-no-owner-OK / mode=claude-no-owner-exit-2 / mode=claude-with-owner-OK |
| 13 | 2 | `bootstrap_lib/paths.py` was in Subsystem A detail but missing from Bucket 1's committed-file list | Added Bucket 1 row for `bootstrap_lib/paths.py` with cross-references to iter-7/8/13 findings |
| 13 | 2 | Restore parser shape ambiguous: text said "argparse subparsers" but syntax was `--restore <manifest>` (flag, not subcommand) | Decided explicitly: keep `--restore` as a flag inside `argparse.add_mutually_exclusive_group(required=True)` — preserves the rollback-hint string format already documented across iter-7/iter-8 evidence. cli.py raises a clear error if render/apply args appear alongside `--restore` |
| 13 | 2 | "What we are NOT doing" said adoption is `--diff` then "per-file decisions" — but per-file decisions are explicitly parked, only `--overwrite-existing` exists | Reworded to: "adoption flow: `--diff` to inspect, then either abort + manual edits OR repo-wide `--apply --overwrite-existing`. Per-file skip/decisions parked." Matches what PR #1 actually ships |
| 14 | 3 | Iter-11's claim that `${{ ... }}` GitHub Actions tokens slip past Jinja was WRONG — Codex verified locally that `StrictUndefined` still parses the inner `{{ secrets.FOO }}` and raises `UndefinedError`. Templates containing actions expressions would fail render | All `${{ ... }}` in shared templates (`claude-review.yml.tmpl`, `ci.yml.tmpl`) MUST be wrapped in `{% raw %}${{ ... }}{% endraw %}` blocks. Render test asserts (a) successful render without UndefinedError, (b) `claude-review.yml` rendered output contains `secrets.CLAUDE_CODE_OAUTH_TOKEN`, (c) default-mode `ci.yml` does NOT contain Claude secret references (clarification of an iter-14 ambiguity — generic CI has no OAuth dep) |
| 14 | 3 | `test_github_review_mode` parametrisation for `claude` / `both-docs` didn't pass `--github-owner` / `--github-repo` flags that iter-13 made mandatory — test would fail under iter-13's own CLI rule | Test fixture updated: when `mode != "none"`, append `--github-owner test-owner --github-repo test-repo` to args. Separate negative test from iter-13's `test_bootstrap_cli.py` proves opt-in modes WITHOUT owner/repo exit 2 |
| 14 | 2 | Subsystem A "Files:" line listed `cli/detect/manifest/render/io` but omitted `paths.py` (which was in Bucket 1 and made a safety boundary elsewhere) | Subsystem A files line now includes `paths.py` explicitly |
| 14 | 2 | Restore-section's manifest-entry list was stale (omitted `sha256_after` / `mode_before` / `mode_after`) — implementers working from restore section could build old schema | Replaced restore-section schema list with a back-reference to the Architecture section (single source of truth). Field list aligned across both sections |
| 14 | 1 | `test_canonical_check_order.py` said "5 subtests" but listed 6 branches (help, wrong-Python, missing-jinja2, missing-pre_commit, non-git, happy-path) | Count corrected to 6 |
| 15 | 3 | iter-13's CLI fix made the mode group `required=True` — but the documented "dry-run is the default" contract requires the mode group to be optional with a dry-run fallback. Documented smoke test (no mode flag) would have failed | `add_mutually_exclusive_group(required=False)`; cli.py defaults to `dry-run` when no mode flag is provided. Added `test_no_mode_flag_defaults_to_dry_run` subtest |
| 15 | 2 | Codex review-target smoke shim was "echoes canned text to stdout", but the Makefile target uses `codex exec --output-last-message <path>` — stdout echo wouldn't materialise the output file | Codex shim now parses `--output-last-message <path>` from its argv and writes canned text to that path. Claude shim stays stdout-only (Claude target uses shell redirect, not a Codex-style flag) |
| 15 | 2 | `mode_before`/`mode_after` documented as "octal e.g. `0o644`" but JSON has no octal literal — `json.dump(0o644)` writes `420`, creating an ambiguity about wire format | Explicit decision: stored as decimal JSON integers (since octal and decimal are the same int values at the Python layer, and `os.chmod` accepts both forms). Manifest round-trip test asserts `mode_after = 0o755` survives write→read and equals `0o755` (== 493 decimal) |
| 16 | 3 | `--install-hooks` invoked pre-commit via `sys.executable` (skill repo's interpreter) — but the hook script then references the skill repo's venv, not the target's. Hooks break if the skill repo moves/rebuilds. Hidden adoption dependency outside the restore manifest | **Removed `--install-hooks` from PR #1's bootstrap CLI entirely**. Replaced with the generated project's `make install-hooks` target (Subsystem F'), which uses `./venv/bin/pre-commit` (target project's own venv). Bootstrap prints "next step: `cd <out> && make install && make install-hooks`" after apply. New `test_generated_install_hooks_uses_target_venv` asserts the resulting hook script's shebang/python reference points at the target's venv, not the skill repo. The legacy `--install-hooks` flag with proper target-venv creation is parked for a follow-up PR |
| 16 | 2 | Shim's `--help` parser was hand-mirrored from `bootstrap_lib.cli` — silent drift risk between help text users see (pre-`make install`) and actual cli behaviour (post-`make install`) | Introduced shared `bootstrap_lib/_flags.py` (Python-3.6 compatible, no third-party imports — just a data list of flag definitions). Both the shim and cli.py consume it as the single source of truth. New `test_shim_cli_help_consistency` runs shim `--help` (under jinja2-less venv) and full cli `--help` (with deps), asserts byte-equal modulo prog-name |
| 16 | 2 | Local prereqs (`make`, `python3.12`, venv support, PyPI access, optional `claude`/`codex` CLIs) were nowhere documented — implementers/CI maintainers could hit them before reaching real checks | Added "Local prerequisites" section to plan + `docs/usage.md`. New `make doctor` target runs `command -v` checks for each tool, prints summary; non-zero exit on missing core prereqs |
| 16 | 1 | Generated `make run` target was part of the Makefile surface but never smoke-tested — could ship broken first-run UX while `make check` stays green | Smoke walk now invokes `make run` after `make check`, with a 10s timeout; `src-main.py.tmpl` prints `f"hello from {{project_name}}"` so the test asserts `"smoke-test"` appears in stdout and exit code 0 |
| 17 | 3 | **(a) fold** — iter-16's `--install-hooks` removal was mechanically incomplete: flag still listed in Bucket 1 cli.py row, docs/usage.md description, deployment-contract check order, manifest schema (`install_hooks: bool`), restore-mode CLI comment, AND the legacy implementation block sat inside active Subsystem F with imperative wording an implementer would follow | Removed all references from active surfaces: cli.py flag list (line 24), docs/usage.md scope (line 75), deployment check order (line 120), manifest top-level schema (line 149), restore-mode comment (line 204), test-execution-boundary lists (lines 227-228), Subsystem F legacy block (lines 544-566 → replaced with one-line backlog pointer). Historical references in evidence-table rows kept as record |
| 17 | 3 | **(a) fold** — `head -1 .git/hooks/pre-commit` assertion was wrong; real pre-commit hook files start with a shell shebang, the Python venv path lives later in the file | Test now asserts: (a) hook file contains the resolved absolute target-project `venv/bin/python` path SOMEWHERE in its contents (grep, not first-line); (b) hook file does NOT contain the skill repo's `venv/bin/python` path. Catches the actual ownership property |
| 17 | 2 | **(a) fold** — README still advertised `--install-hooks` opt-in as part of the adoption-safety contract; future implementers reading the repo top would see a different public surface than the PR plan | Added README update to Bucket 3: rewrite the merged-plan adoption-contract line to mention `make install-hooks` (post-bootstrap, generated-project-side) as the PR #1 hook adoption path, with `--install-hooks` parked as follow-up |
| 17 | 2 | **(a) fold** — no mechanical check that "removed flag is gone from active surfaces"; iter-16's incomplete fold proved the failure mode | Added "Active-surface consistency check" step to Verification Phase 1: manual grep before opening the PR, with explicit categorisation rule (active / legacy-or-backlog / forbidden). Lightweight by design per Codex's suggestion. Codifies the prevention of this exact regression for future "remove this flag" folds |
| 17 | 2 | **(a) fold** — same root as F1: the legacy `--install-hooks` implementation block (with detailed imperative wording, subprocess calls, 5 tests) sat INSIDE active Subsystem F; implementer agents follow nearby concrete instructions | Deleted the legacy block from the plan body. Replaced with a one-line backlog pointer: `BACKLOG.md` entry "Direct `--install-hooks` flag with target-venv creation" — trigger: user request. Subsystem F is now just the generated `make install-hooks` target + one passing test |
| 17 | 2 | **(a) fold** — `make doctor` was added in iter-16 but had no acceptance test; could ship broken while plan claims local-tooling dependency was handled | Added Verification gate #6: `make help` lists `doctor`; `make doctor` exits 0 with all core tools present, non-zero with shimmed-missing core tool, advisory-only for missing optional `claude`/`codex` CLIs |
| 17 | 1 | **(a) fold** — Verification list conflated "runnable now" gates (plan-review evidence) with "runnable post-implementation" gates (skill repo `make check`); reviewers could assume gates were runnable before code lands | Split Verification into Phase 1 (pre-implementation evidence: plan review + active-surface grep + human approval) and Phase 2 (post-implementation gates: per-subsystem tests, `make check`, `make doctor`, smoke walk, draft PR). Honest about what's runnable when |
| 18 | 2 | **(a) fold** — README at line 31 still advertised `--install-hooks` as part of the adoption-safety contract; iter-17's narrow active-surface grep (plan file only) couldn't catch this exact drift | Expanded Verification Phase 1 step 2 grep to `grep -rn` across README + SKILL.md + docs/ + languages/ + shared/ + bootstrap.py + bootstrap_lib/. Plan-text README update was already scheduled; the grep is now the structural backstop |
| 18 | 2 | **(a) fold** — `make doctor`'s missing-`make` shim test (iter-17) was invalid: `PATH=/usr/bin:/bin` still finds `/usr/bin/make` on macOS, and you can't `make doctor` to diagnose missing `make` (circular) | Replaced missing-`make` clause with missing-`python3.12` and missing-`git` shim tests (constructable PATH with stub `git` and no `python3.12`). Documented `make` itself as a hard README prereq |
| 18 | 2 | **(a) fold** — `restart` listed in generated Python Makefile surface but had no spec or smoke coverage; it's a Boxette-ism (bot restart) that would always ship because PR #1 always emits `src/main.py`, contradicting the "only when run-able" hedge | Removed `restart` from `languages/python/Makefile.tmpl` row. Surface is now `help / install / install-hooks / test / lint / format / check / run`. No spec or test for restart in PR #1 |
| 18 | 1 | **(a) fold** — `python_version` was in the substitution-variables list but its origin was unspecified; CLI had no `--python-version` flag while `ci.yml.tmpl` consumed `{{python_version}}` | Architecture section now states `python_version = "3.12"` is hardcoded in render context for PR #1 (`bootstrap_lib/cli.py`). Added `test_python_templates.py` assertion that rendered `ci.yml` contains `python-version: '3.12'`. Variable still flows through context so future PRs can override |
| 20 | 2 | **(a) fold** — Codex GitHub auto-review (P1): restore decision table missed the "overwritten file is MISSING at restore time" branch. Code in `bootstrap_lib/manifest.py:182-186` unconditionally restored the pre-apply content; for an overwritten file the user later deleted (`rm`), restore would undo the user's deletion. Violates the documented conservative-restore property | Changed the branch to SKIP with a clear warning. Added subtest `test_d_double_prime_user_deleted_overwritten_file_not_restored` (total restore subtests now 11). Plan's restore decision table has an explicit 4th overwritten-row covering the missing-file case. Trade-off: the interrupted-apply path (apply died before writing this overwritten file) is now also a SKIP, which is the conservative cost of never clobbering a user deletion |
| 21 | 2 | **(a) fold** — Codex re-review (P1): restore's write-back used bare `target_path.write_bytes(content)` which truncates the file in place. If `--restore` is interrupted mid-write, user is left with empty or partial content; violates the crash-safe property that apply already has via `io.atomic_write` | Routed the write-back through `bio.atomic_write(target_path, content)` (chmod still happens after). Symmetric with apply's discipline. Extended `test_a_overwritten_files_restored` to assert no `.bootstrap-tmp` artifacts remain after a clean restore |
| 21 | 2 | **(a) fold** — Codex re-review (P2): `manifest_path()` formatted the timestamp at second precision; two `--apply` runs landing in the same second under the same `TMPDIR` would write to the same path, clobbering the first manifest. The first apply's rollback hint then points at the wrong manifest | Replaced the hand-built path with `tempfile.mkstemp(prefix="dev-project-setup-restore-{timestamp}-", suffix=".json")`. Timestamp prefix preserves human sortability; mkstemp's random suffix guarantees uniqueness across processes/threads. New `test_manifest_path_is_unique_under_rapid_calls` proves 20 rapid calls produce 20 distinct paths |
| 22 | 2 | **(a) fold** — Codex re-review on iter-21 commit (P1): apply failure mid-write only printed `apply failed: <e>` — manifest path and restore hint were lost because they lived inside `_apply`. User left with partial state + no rollback command (despite the manifest being safely on disk) | Split `_apply` into `_prepare_apply` (entries + manifest write) and `_apply_writes` (atomic writes). `main()` now holds `manifest_p` across the write phase. The failure path prints `apply failed mid-write: <e>` + "target tree may be in a partial state" + manifest path + rollback hint. Test `test_partial_apply_failure_still_prints_restore_hint` monkey-patches `io.atomic_write` to raise on the 3rd call and asserts the hint appears |
| 22 | 2 | **(a) fold** — Codex re-review on iter-21 commit (P2): restore CLI ignored `restore_from_manifest`'s return tuple. A path-safety-rejected manifest aborts with `n_rejected > 0` and no work done, but CLI returned 0 — scripted rollback flows wrongly reported success | Restore branch in `cli.py:main()` now captures the tuple and returns `1 if n_rj > 0 else 0`. SKIP counts don't trigger non-zero (user-edit detection is expected behaviour, not a CLI failure). Test `test_restore_returns_nonzero_when_path_safety_rejects` hand-crafts a manifest with `/tmp/outside.txt` and asserts non-zero exit |
| 23 | 2 | **(c) reject** — Codex re-review on iter-22 commit (P1): "Restore overwritten files atomically" at `manifest.py:186` and "Print the restore manifest when apply fails after writes" at `cli.py:279`. Both stale re-flags — the iter-21 + iter-22 folds are in place at those exact line numbers. `manifest.py:185` already calls `bio.atomic_write`; `cli.py:272-278` already prints the manifest path + rollback hint. Codex's analysis appears to be running on cached/old state | No code change. Evidence-table entry documents the rejection so future reviewers see the triage decision |
| 23 | 2 | **(a) fold** — Codex re-review on iter-22 commit (P2 #1): `atomic_write`'s `finally` only discarded the orphan from `_pending_tmp`, which is what the signal/atexit cleanup consults. If `open/write/fsync/replace` raised, the `.bootstrap-tmp` file was left on disk forever (no cleanup, no signal, no atexit can see it after the discard) | Added a `renamed` flag; the `finally` now unlinks the tmp file when the rename didn't complete. Test `test_atomic_write_cleans_tmp_on_write_failure` monkey-patches `os.fsync` to raise and asserts no `.bootstrap-tmp` artifacts remain |
| 23 | 2 | **(a) fold** — Codex re-review on iter-22 commit (P2 #2): `os.rename(tmp, target)` fails on Windows when `target` exists. `--overwrite-existing` would silently break for every collided file on Windows | Replaced `os.rename` with `os.replace` — atomic on POSIX (same as rename), and replaces on Windows. Test `test_atomic_write_overwrites_existing_target` exercises the overwrite-existing case |

## What we are NOT doing in this PR

- **No `languages/nodejs/` or `languages/go/`** — PR #2 and PR #3 respectively per merged plan.
- **No auto-GitHub-repo creation** — `gh repo create` + branch protection is parked indefinitely.
- **No migration mode beyond simple file-add** — adoption flow: `--diff` to inspect, then either abort + manual edits OR repo-wide `--apply --overwrite-existing` to consent. Per-file skip/decisions are parked (closes Codex iter-13 finding #5). No surgical Makefile refactor.
- **No `make selftest-bootstrap` Makefile target** — the dogfood check exists as `tests/test_selftest_overlap.py` (in PR #1 scope; closes Codex iter-1 finding #5), but wrapping it as a standalone Makefile target with broader file coverage is parked.
- **No MCP-based plan-review wrapper** — the merged plan parks this as out-of-scope for v1.
- **No `--enable-smoke` template content beyond a skeleton** — projects that need `docs/SMOKE.md` author their own per-flow walkthroughs.
- **No retroactive update of Boxette's `CLAUDE.md`/`AGENTS.md`/`docs/plans/README.md`** to add the triage rule. That's a separate Boxette PR (touching another repo would expand PR #1's scope across two repos). Tracked as a BACKLOG follow-up; trigger: after PR #1 lands and we run the next substantive Boxette plan-review.

## Critical files to read before iter-1 review

For Codex / Claude (whichever reviews this plan): inspect these to verify plan assumptions against repository state:

- `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/docs/plans/2026-05-15-dev-project-setup-skill.md` — the merged plan; subsystems A–F are defined there
- `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/Makefile` lines 66–115 — source of `Makefile.review.tmpl`'s `review-plan-by-codex` target
- `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/.github/workflows/claude-review.yml` — source of `shared/claude-review.yml.tmpl`
- `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/.github/pull_request_template.md` — source of `shared/pull_request_template.md.tmpl`
- `/Users/sandeep/Desktop/Code/Boxette/Telegram bot/CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `BACKLOG.md`, `docs/plans/README.md` — sources of the corresponding `shared/*.tmpl` files
- `/Users/sandeep/Desktop/Code/dev-project-for-non-developers/README.md` — the new repo's framing (repo name vs skill name distinction)
- `/Users/sandeep/Desktop/Code/dev-project-for-non-developers/.gitignore` — the new repo's only other existing file
