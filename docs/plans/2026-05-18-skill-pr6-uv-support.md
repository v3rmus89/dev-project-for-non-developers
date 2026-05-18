# Skill PR #6 — uv support for Python

> Adds `--package-manager={uv,pip}` to the `dev-project-setup` skill's Python language. **uv is the new default for greenfield Python projects**; pip-venv stays supported for adoption-into-existing-projects + explicit opt-out. Auto-detection picks the right mode when applying onto an existing project. Mirrors PR #3's structural pattern (additive variant within an existing language, not a new language).

## Context

PR #1–#5 shipped: Python (PR #1), Node-TS (PR #2), Go (PR #3), two-tier review + plan-loop improvements (PR #4), observability + self-improvement layer (PR #5). The plan was for PR #6 to be the **real-project trial on `~/Desktop/Code/Boxette/call-details/`**. Pre-trial inspection of the target surfaced a blocking conflict: the target uses **uv** (Astral's Rust-rewrite of pip+venv), but the skill's Python templates assume `python3.12 -m venv venv && pip install`. Running the trial as-is would create a parallel `venv/` alongside the target's existing `.venv/` — two Python environments side by side, both real, mutually confusing.

We could have done the trial anyway and let "uv conflict" be its central finding. We already know that's the finding. Running the trial with no uv support would produce a report that just confirms what we know, and the report would be the only deliverable — no skill improvements would land. **Sequencing**: add uv support first (this PR #6), then trial second (PR #7).

Why uv-as-default for greenfield Python in 2026:

1. **Speed difference is felt most by non-developers.** Pip's slowness is invisible to seasoned developers (they've built tolerance). For a non-developer running `pip install` for the first time and waiting 30–60s for an innocuous command, it feels broken. uv finishes in 1–3s.
2. **uv hides the venv-activate dance.** Non-developers don't have to learn "activate", "deactivate", `./venv/bin/python`. `uv run pytest` just works.
3. **`uv python install 3.12`** removes the single most fragile step in any 2026 Python workflow for non-developers (macOS's system `python3` is 3.9.x; users get blocked here).
4. **Lockfile-by-default.** `uv.lock` is generated automatically — same "works on my machine" protection that `package-lock.json` provides in npm-land.
5. **Astral is already in the stack.** The skill ships `ruff` (Astral). Adding uv keeps the toolchain coherent.
6. **Industry direction**: by mid-2025, uv was the de-facto default for new Python project templates. By 2026 (now), telling a non-developer "use pip+venv" feels like teaching Subversion in 2015.

Why we still support pip (not uv-only):

- **Adoption-into-existing**: many existing projects use pip. The skill must respect the existing convention rather than force migration.
- **Explicit opt-out**: corporate/exotic environments may require pip. `--package-manager=pip` is the escape hatch.

User-decided scope constraints (pre-loop decisions, before iter-1):

- **Default for greenfield is uv** (not "stay backwards-compatible with pip default"). Non-developers benefit most from the modern path; existing pip projects are protected via auto-detect.
- **Auto-detection during `--apply` on an existing target**: heuristic based on file presence (`uv.lock`, `[tool.uv]` / `uv_build` markers in `pyproject.toml`, presence of `requirements*.txt`). When ambiguous, default to uv with an advisory print; never silently pick pip without a positive marker.
- **No `--python-version` flag** — `python_version` stays hardcoded to "3.12" in `_build_context` for now. uv mode's `.python-version` file uses the same value. Future PR can add a flag.
- **uv pin policy**: uv itself moves fast (~weekly releases). We do NOT pin a uv version in CI; we use `astral-sh/setup-uv@v3` with the action's default (latest stable). Generated projects use whatever uv the user has installed. The `uv.lock` file is what guarantees reproducibility — not the uv binary version. (Mirrors how pip-mode currently doesn't pin pip itself.)
- **Existing project's `pyproject.toml` is the source of truth for deps** — skill never overwrites it in adoption mode. Skill's contribution = Makefile + CI + CLAUDE.md + hooks. Greenfield uv mode writes a new minimal pyproject.toml with `[dependency-groups] dev` populated.
- **requirements-dev.txt is NOT emitted in uv mode** — uv reads `pyproject.toml`'s `[dependency-groups]` directly. Generating both creates a drift risk.

## Scope

### IN scope

| # | Change | Where |
|---|---|---|
| 1 | New CLI flag `--package-manager={uv,pip}`, default `uv` for greenfield, **auto-detect** for adoption | `bootstrap_lib/_flags.py` |
| 2 | Detection helper `detect_package_manager(out_dir)` — heuristic on uv.lock + pyproject markers + requirements*.txt presence | `bootstrap_lib/detect.py` (extend) + new tests |
| 3 | Context resolution: `_build_context` picks effective package_manager (flag → detection → default-uv); context dict gains `"package_manager"` key | `bootstrap_lib/cli.py` |
| 4 | `PYTHON_TEMPLATE_MAP` becomes conditional — skip `requirements-dev.txt.tmpl` + `.pre-commit-config.yaml.tmpl` in uv mode; emit new `.python-version.tmpl` only in uv mode | `bootstrap_lib/render.py` |
| 5 | `languages/python/Makefile.tmpl` — Jinja branch on `package_manager`: uv mode uses `uv sync` / `uv run pytest` / `uv run ruff …`; pip mode unchanged | `languages/python/Makefile.tmpl` |
| 6 | `languages/python/ci.yml.tmpl` — Jinja branch: uv mode uses `astral-sh/setup-uv@v3` with `python-version`; pip mode unchanged | `languages/python/ci.yml.tmpl` |
| 7 | `languages/python/pyproject.toml.tmpl` — uv branch adds `[dependency-groups] dev` populated with ruff/pytest/pre-commit pins; `[build-system]` uses `uv_build` backend; pip branch unchanged. `dependencies = []` in both | `languages/python/pyproject.toml.tmpl` |
| 8 | NEW `languages/python/.python-version.tmpl` — single line `{{python_version}}` (uv mode only) | `languages/python/.python-version.tmpl` |
| 9 | Hook strategy in uv mode: KEEP `pre-commit` framework (same `.pre-commit-config.yaml`) but invocation goes through `uv run pre-commit`. The pre-push pytest entry's `entry:` value flips from `./venv/bin/python -m pytest` to `uv run python -m pytest` | `languages/python/.pre-commit-config.yaml.tmpl` (single Jinja branch on package_manager for the entry: line only) |
| 10 | Shared template Python-version section: branch on package_manager in CLAUDE.md.tmpl + CONTRIBUTING.md.tmpl (commands table stays `make X` — Makefile abstracts the difference; the Python-version paragraph and one-time-setup paragraph differ) | `shared/CLAUDE.md.tmpl`, `shared/CONTRIBUTING.md.tmpl` |
| 11 | Tests: detection unit tests; template-render tests for both modes; smoke-test for uv mode end-to-end (`uv sync` → `make check`) skipped locally if `uv` absent, fail-hard in CI | `tests/` |
| 12 | Skill-repo `Makefile` `doctor` target — add `uv` advisory check (advisory only; bootstrap engine doesn't require uv) | `Makefile` (skill repo) |
| 13 | Skill-repo `.github/workflows/ci.yml` — install `uv` via `astral-sh/setup-uv@v3` so the new uv smoke walk runs in CI | `.github/workflows/ci.yml` (skill repo) |
| 14 | Active-public-docs updates: README "Status" + "Build sequence"; SKILL.md `--package-manager` flag mention; docs/usage.md new "Python: uv vs pip" section + a non-developer-friendly explanation; BACKLOG add follow-ups (uv pin policy, multi-PM-Node parallel, etc.); the dogfood `.python-version` of the skill repo stays unchanged (skill is pip-mode itself) | `README.md`, `SKILL.md`, `docs/usage.md`, `BACKLOG.md` |
| 15 | LESSONS.md entry (writable session) for any new mistake-class surfaced by the impl PR | `LESSONS.md` |

### NOT in scope

- **No uv equivalent for Node-TS or Go.** Those have their own native package managers (`npm`, `go mod`). This PR is Python-specific.
- **No `--python-version` CLI flag.** Stays hardcoded to "3.12" in `_build_context`. Parked.
- **No uv pin policy.** CI uses `astral-sh/setup-uv@v3` with action default (latest stable). `uv.lock` provides per-project reproducibility.
- **No migration tool** (e.g. "convert this pip project to uv"). Adoption mode respects what the user has. Future PR.
- **No deprecation of pip mode.** Both modes are first-class for the foreseeable future.
- **No nodejs/go test parametrisation changes.** They remain single-toolchain.
- **No changes to PR #5's `make status` target.** Status output is package-manager-agnostic.
- **No real-project trial in this PR.** That's PR #7.

## Subsystem breakdown

### Bucket A — Engine extensions (additive, mirrors PR #3 Bucket A)

| File | Change |
|---|---|
| `bootstrap_lib/_flags.py` | Add `--package-manager` arg with `choices=["uv", "pip"]`, default `None` (so we can distinguish "user passed `pip`" from "user passed nothing → use default/detection"). Help text: `"Python package manager. Default 'uv' for greenfield; auto-detected when bootstrapping into an existing project. Use 'pip' to opt out. Ignored when --language != python."` |
| `bootstrap_lib/detect.py` | NEW or extended file. Add `detect_package_manager(out_dir: Path) -> str \| None`. Heuristic: (1) if `out_dir` doesn't exist → return None (greenfield). (2) if `out_dir/uv.lock` exists → return `"uv"`. (3) if `out_dir/pyproject.toml` exists AND contains `[tool.uv]` or `backend = "uv_build"` → return `"uv"`. (4) if `out_dir/requirements.txt` or `out_dir/requirements-dev.txt` exists (without uv markers) → return `"pip"`. (5) if `out_dir/pyproject.toml` exists with no uv/pip markers → return `"uv"` (modern default for ambiguous existing projects) + caller prints an advisory. (6) else → return None (treat as greenfield). |
| `bootstrap_lib/cli.py` | `_build_context` extended: when `language == "python"`, resolve `package_manager` via `args.package_manager or detect_package_manager(args.out) or "uv"`. When detection was used (`args.package_manager is None` and detection returned non-None), print one-line advisory to stderr: `"info: detected package_manager='uv' from existing files in <out>"` (or `'pip'`). When detection's "(5) ambiguous → uv" branch fires, advisory is more explicit: `"info: existing pyproject.toml has no uv/pip markers; defaulting package_manager='uv' (pass --package-manager=pip to override)"`. Context dict gains `"package_manager"` key. Validation: `--package-manager` set with `--language` not `python` → argparse error (raised in cli, not _flags, so help text stays clean). |
| `bootstrap_lib/render.py` | `PYTHON_TEMPLATE_MAP` stays static at the dict level; the **filtering happens in `render_all`** via a new branch parallel to the existing `_emit_in_mode` check. New helper `_emit_python_in_pm_mode(rel_out, package_manager)` returns False for `requirements-dev.txt` when `package_manager == "uv"` and False for `.python-version` when `package_manager == "pip"`. The `.python-version` template only exists in uv mode. Apply-success "next steps" hint extends: when `package_manager == "uv"`, hint says `cd <out> && make install && make install-hooks` (uv runs `uv sync`; same UX as pip mode); when `pip`, unchanged. |

**No changes** required to `bootstrap_lib/{io,paths,manifest}.py`. The new `.python-version` file is plain text mode 0644 — no executable-bit handling needed.

### Bucket B — Python template uv-mode branches (in-place Jinja edits)

| File | Change |
|---|---|
| `languages/python/Makefile.tmpl` | Jinja branch on `package_manager`. uv branch (illustrative; impl PR delivers the actual text — but it must satisfy every prose contract below): no `PYTHON ?= ` line; targets `install`, `install-hooks`, `test`, `lint`, `format`, `check`, `run` use `uv sync` / `uv run pre-commit install [--hook-type pre-push]` / `uv run pytest -v` / `uv run ruff check .` (+ `uv run ruff format --check .`) / `uv run ruff check --fix .` (+ `uv run ruff format .`) / `lint test` / `uv run python src/main.py`. **No `venv:` target** in uv mode (`uv sync` manages `.venv/` itself). `install-hooks` recipe uses `git rev-parse --is-inside-work-tree` (the worktree-safe guard — mirrors PR #3 iter-7 #1 lesson). pip branch is current text unchanged. `{% include 'Makefile.review.tmpl' %}` stays outside the branch. |
| `languages/python/ci.yml.tmpl` | Jinja branch. uv branch uses `astral-sh/setup-uv@v3` with `python-version: '{{python_version}}'` (the action sets up Python + uv in one step). pip branch unchanged. Step naming stays `make install` + `make check` so impl-detection is via setup-action lines, not subsequent steps. |
| `languages/python/pyproject.toml.tmpl` | Jinja branch. uv branch adds `[dependency-groups]` table with `dev = ["ruff==0.15.12", "pytest>=8.0,<9", "pre-commit>=3.7,<5"]` (same pins as pip mode's `requirements-dev.txt`), and `[build-system]` uses `requires = ["uv_build>=0.11,<0.12"]` + `build-backend = "uv_build"`. pip branch unchanged. **Note**: the existing `[tool.setuptools]` + `[tool.setuptools.packages.find]` sections in pip branch stay; uv branch omits them (uv_build doesn't need them). |
| `languages/python/.pre-commit-config.yaml.tmpl` | Jinja branch on the pre-push pytest entry's `entry:` line only. uv: `entry: uv run python -m pytest`. pip: `entry: ./venv/bin/python -m pytest` (current). Everything else (ruff hook config, repos block) is identical across branches. |
| NEW: `languages/python/.python-version.tmpl` | Single line: `{{python_version}}`. Emitted only when `package_manager == "uv"`. Used by uv (and pyenv, conda — all of them respect `.python-version`) to know which Python version this project pins. |

### Bucket C — Shared template package-manager-aware sections

| File | Change |
|---|---|
| `shared/CLAUDE.md.tmpl` | Python-version section (currently inside the `{% if language == 'python' %}` branch) gets a nested `{% if package_manager == 'uv' %}` branch: "**This project uses `uv`** for Python dependency + venv management. uv pins Python via `.python-version`. Run code with `uv run python …`; add deps with `uv add …`. The Makefile abstracts most of this — `make test`, `make lint`, `make run` work the same as in pip projects." vs. pip branch (current text: "Always use `python{{python_version}}`. Skill bootstraps a per-project `venv/`; `$(PYTHON)` is `./venv/bin/python`."). Commands table is **unchanged** — both modes use `make ...`. |
| `shared/CONTRIBUTING.md.tmpl` | One-time setup section (currently mentions `make install`): uv branch adds a prerequisite line: "First install uv: `brew install uv` (macOS) or `curl -LsSf https://astral.sh/uv/install.sh \| sh` (Linux/WSL) or `pipx install uv`. Then `make install`." pip branch unchanged. Same wording template loaded by both Makefile-using languages — gating must be inside `{% if language == 'python' %}` to avoid leaking into Node/Go. |
| `shared/AGENTS.md.tmpl` | No changes needed — AGENTS.md doesn't have package-manager-specific instructions (only language-conditional ones, and the language stays `python`). |
| `shared/BACKLOG.md.tmpl` | No changes (this is the *template* for new projects; the skill-repo's own `BACKLOG.md` is updated in Bucket E). |

### Bucket D — Tests

| File | Asserts |
|---|---|
| NEW: `tests/test_package_manager_detection.py` | Unit tests for `detect_package_manager`: (a) nonexistent dir → None; (b) empty dir → None; (c) dir with `uv.lock` only → "uv"; (d) dir with `pyproject.toml` containing `[tool.uv]` → "uv"; (e) dir with `pyproject.toml` containing `backend = "uv_build"` → "uv"; (f) dir with `requirements.txt` only → "pip"; (g) dir with `requirements-dev.txt` only → "pip"; (h) dir with `pyproject.toml` (no markers) + no requirements*.txt → "uv" (the modern-default branch); (i) dir with `pyproject.toml` (no markers) + `requirements.txt` → "pip" (positive pip marker wins); (j) dir with `uv.lock` AND `requirements.txt` → "uv" (positive uv marker wins — common during a migration); (k) dir with `pyproject.toml` containing both `[tool.uv]` AND `requirements.txt` → "uv" (positive uv marker wins). |
| NEW: `tests/test_python_uv_templates.py` | Per-template render-and-parse for uv context: `Makefile` `make help` lists expected targets (NO `venv` target); contains `uv sync`, `uv run pytest`, `uv run ruff` substrings; contains NO `./venv/bin/`, `pip install`, `python{{python_version}} -m venv` substrings. `ci.yml` uses `astral-sh/setup-uv@v3` with `python-version` input. `pyproject.toml` contains `[dependency-groups]` + `dev = [` + `uv_build` build backend + the same 3 pinned dev deps as pip mode (parameterised assertion sharing one canonical list with pip-mode tests so they don't drift). `.python-version` exists with content `{{python_version}}\n`. `.pre-commit-config.yaml`'s pytest entry contains `uv run python -m pytest`. **Negative coverage**: `requirements-dev.txt` is NOT rendered (assert `"requirements-dev.txt" not in planned_files` after `render_all`). |
| `tests/test_python_templates.py` (extended) | Existing pip-mode assertions stay; new explicit `package_manager="pip"` parameter passed to render contexts (default behaviour, same output). Asserts pip mode renders `requirements-dev.txt` AND `.pre-commit-config.yaml`'s pytest entry contains `./venv/bin/python -m pytest` AND `.python-version` is NOT rendered. |
| NEW: `tests/test_smoke_python_uv_generated.py` | Full bootstrap with `--package-manager=uv` → `uv` preflight check (`shutil.which("uv")`; skip locally if absent, fail hard when `CI=true`) → `git init` + user.name/email + initial commit → `make install` (runs `uv sync`) → assert `.venv/` was created by uv (not `venv/`) → `make install-hooks` → `make check` → `make run` → commit-fires-hook subtest: stage a dirty `.py` file, attempt commit, assert hook re-formats + blocks → re-stage + re-commit succeeds. Plus a no-HEAD-safe subtest (run `make install-hooks` BEFORE the initial commit, then commit the bootstrap output — assert the hook works on a clean tree). |
| `tests/test_smoke_python_generated.py` (extended) | Existing pip-mode smoke walk unchanged; add explicit `--package-manager=pip` to the invocation so future detection changes can't shift this test's mode. |
| `tests/test_bootstrap_cli.py` (extended) | New tests: `--package-manager=uv --language=nodejs` errors with a clear message ("--package-manager only applies to --language=python"); `--package-manager=uv` valid combinations across all 3 github-review modes; `--package-manager` absence with greenfield Python → context has `"uv"`; `--package-manager` absence with existing-uv-marker dir → context has `"uv"` + stderr contains the advisory line; `--package-manager` absence with existing-pip-marker dir → context has `"pip"` + advisory. |
| `tests/test_shared_templates.py` (extended) | New context parametrisation: for `language="python"`, run with both `package_manager="uv"` and `package_manager="pip"`. Assert CLAUDE.md uv-branch text mentions "uv" + "`.python-version`" + "`uv run`"; pip-branch unchanged. CONTRIBUTING.md uv-branch mentions "First install uv" prerequisite; pip-branch unchanged. Commands table is identical across modes (same `make X` strings). |
| `tests/test_shim_cli_help_consistency.py` (regression) | Existing byte-equal help-output assertion stays. Confirms `_flags.py`'s new `--package-manager` arg appears in both shim and full-CLI help identically. |

### Bucket E — Active public docs + skill-repo CI/doctor

| File | Change |
|---|---|
| `README.md` | "Status" updates: PR #5 ✅, PR #6 ✅ (after merge), PR #7 = real-project trial (was PR #6). "Build sequence" updates: PR #6 = uv support; PR #7 = real-project trial. One-line mention in feature list: "Python projects default to `uv` (Astral) for fast, modern dependency management; opt out via `--package-manager=pip`". |
| `SKILL.md` | Invocation block adds `[--package-manager {uv,pip}]`. New short paragraph: "Python only. Default `uv` for greenfield; auto-detect for adoption. Pass `--package-manager=pip` to opt out." |
| `docs/usage.md` | New "Python: uv vs pip" section (~1-page). Includes: (a) what uv is in plain language for the non-developer audience (Rust binary, ~10-100× faster than pip, manages `.venv/` for you, `uv.lock` reproducibility); (b) when each mode fires (greenfield → uv default; adoption → auto-detect; explicit → flag wins); (c) `--package-manager` flag table row; (d) install instructions for uv itself (brew / curl one-liner / pipx); (e) escape hatch ("if uv breaks for you, `--package-manager=pip` always works"). |
| `BACKLOG.md` | (a) Add new entry under "PR #6 follow-ups": "uv pin policy — currently `astral-sh/setup-uv@v3` default. Trigger to fix: first time the action's default-latest breaks a smoke walk OR a user reports CI non-determinism from uv version drift. Effort: ~30 min — add `version:` input + a docstring." (b) Add: "uv migration tool (`bootstrap.py --migrate-from=pip --to=uv`) — converts an existing pip project to uv. Out of scope for PR #6 (adoption mode respects existing tooling); pick up if a user asks." (c) Add: "Real-project trial on `~/Desktop/Code/Boxette/call-details/` — PR #7. Plan PR + Impl PR sequence; deliverables = trial plan + `docs/lessons.md` + any skill polish surfaced." |
| `.github/workflows/ci.yml` (the SKILL REPO's own CI) | Add `astral-sh/setup-uv@v3` step **after** `actions/setup-python` (so uv is on PATH for the new uv smoke walk). Step sequence: `checkout → setup-python (3.12) → setup-node (24) → setup-go (1.26) → setup-uv → make install → make check`. Without this, the uv smoke walk in `make check` would skip in CI (matches the PR #2 setup-node + PR #3 setup-go pattern). |
| `Makefile` (skill repo's `doctor` target) | Add `uv` to the advisory checks (alongside existing `node`/`npm`/`go` advisories): `command -v uv >/dev/null 2>&1 && echo "ok uv" \|\| echo "advisory uv not on PATH (only needed when bootstrapping --package-manager=uv OR running make check's uv smoke walk)"`. |
| `LESSONS.md` (skill repo's own) | Append entry (impl-session, after Tier-1 fold if any surfaces a new mistake-class). At minimum, the `pyproject.toml` build-backend section ([tool.setuptools] vs uv_build) is a likely source of a new lesson — won't pre-write it, will append based on what actually surfaces. |

**Active-surface consistency check** — grep sweep for PR #6 (extends PR #3's pattern):

```bash
grep -rnE --include='*.md' --include='*.tmpl' --include='*.py' --include='*.yml' \
  '\bruff\b|\bpytest\b|\bvenv\b|pre-commit|pyproject|requirements-dev|python_version|"python"|--language python\b|\bBiome\b|\bvitest\b|node_version|\bnpm\b|\bHusky\b|\.husky|package-lock|package\.json|tsconfig|node_modules|--language nodejs\b|\bgofumpt\b|\bgolangci-lint\b|go_version|"go"|--language go\b|\buv\b|uv\.lock|uv_build|\.python-version|astral-sh/setup-uv|dependency-groups|--package-manager' \
  README.md SKILL.md Makefile docs/ languages/ shared/ bootstrap.py bootstrap_lib/ .github/workflows/ 2>/dev/null
```

### Per-subsystem acceptance gates

| Subsystem | Gate | Reviewer can reject independently? |
|---|---|---|
| A. Engine extensions | All existing tests still pass; `--package-manager` accepted by CLI; detection unit tests pass; `--package-manager` advisory prints visible in stderr | ✅ |
| B. Python uv-mode templates | `tests/test_python_uv_templates.py` green; existing pip-mode template tests still pass | ✅ |
| C. Shared template branches | Shared-templates test green for both PM modes; CLAUDE.md/CONTRIBUTING.md render cleanly in both | ✅ |
| D. Tests | New uv smoke walk green (or skipped cleanly when uv absent locally); skill-repo `make check` green | ✅ |
| E. Active-docs update | Active-surface grep clean for both modes; README/SKILL/usage/BACKLOG reflect uv + pip | ✅ |

## Architecture decisions specific to uv

- **Package manager default**: `uv` for greenfield Python; **auto-detect** for adoption (file presence in `--out` dir); explicit flag overrides everything.
- **Detection priority**: positive uv marker (`uv.lock`, `[tool.uv]`, `uv_build` backend) > positive pip marker (`requirements*.txt`) > existing `pyproject.toml` with no markers → uv (modern default) > nothing → uv.
- **Advisory printing**: every detection result (other than "no existing dir → greenfield default") prints a one-line stderr advisory so the user can see which mode was picked. Non-fatal; just observable.
- **Hook framework**: stays **`pre-commit`** (the framework, not the git event) in both modes. uv mode invokes the framework via `uv run pre-commit` (so the framework's own deps live in `.venv/`). pip mode unchanged. Rejected alternative: switching uv mode to native-git-hooks (PR #3 pattern for Go) — would diverge from PR #1's Python pattern more than necessary; the pre-commit framework works fine via `uv run`.
- **`.venv/` vs `venv/`**: uv writes to `.venv/` by default (its convention). pip mode writes to `venv/`. Generated `.gitignore` already ignores both patterns in PR #1's template (verify in iter-1 fold; if not, fold).
- **`uv_build` backend**: greenfield uv mode uses `uv_build` (Astral's PEP 517 backend, ships with uv). Rejected alternative: setuptools — would be a needless dep + slower build. Risk: uv_build is younger than setuptools; pin `>=0.11,<0.12` to track current major and accept that we'll bump as uv evolves (mirrors how PR #3 pins gofumpt/golangci-lint).
- **No uv version pin in CI**: `astral-sh/setup-uv@v3` defaults to latest stable. `uv.lock` is what provides per-project reproducibility — not the uv binary version. (Mirrors how pip mode doesn't pin pip itself.) If this ever causes a flake, BACKLOG entry covers the fix.
- **`.python-version` file**: written in uv mode only. Used by `uv python install` (and by pyenv/conda — broad compatibility). Single line: `3.12`. Pin tied to `python_version` context var.
- **Adoption-mode pyproject.toml**: the skill **skips** `pyproject.toml` when the target already has one (standard safety contract from PR #1). User's deps are sacred. Skill's contribution = Makefile + CI + CLAUDE.md + AGENTS.md + CONTRIBUTING.md + BACKLOG.md + LESSONS.md + docs/plans/ + hooks. The `.python-version` template still gets written for uv adoption only when the target doesn't already have one.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| uv detection misfires on edge cases (e.g. project has both `uv.lock` and `requirements.txt` during a migration) | Detection prioritizes positive uv markers (covers migration "starting to use uv" direction). Tests (j) + (k) exercise both-markers cases explicitly. Advisory printing surfaces the choice so user can override. |
| `uv_build` backend is new (~v0.11); breaking changes possible | Pinned range `>=0.11,<0.12` keeps us on current major. Bump on uv major releases. BACKLOG entry to track. |
| `astral-sh/setup-uv@v3` action default-latest could break CI without a repo diff | Accepted trade-off per PR #3's gofumpt pin precedent: pinning churn vs floating-latest trade-off. BACKLOG entry tracks the fix when needed. Tests use `shutil.which("uv")` so local smoke still works without the action. |
| Existing pyproject.toml conflicts with skill's templated pyproject.toml in greenfield-but-not-quite case | Standard safety contract from PR #1 — existing file triggers skip (or `--overwrite-existing` required). Adoption mode tested via test (h)+(i)+(k) above. |
| User installs the skill but doesn't have uv on PATH | (a) Skill-repo's `make doctor` includes uv advisory check (PR #6 Bucket E). (b) Generated `make install` in uv mode fails with a uv-specific error message (escape hatch: re-run with `--package-manager=pip`). (c) `docs/usage.md` mentions the install one-liner for uv. |
| Tests pass locally but the uv smoke walk silently skips in CI when `uv` isn't on PATH | Mirror PR #3's `CI=true` pattern — `test_smoke_python_uv_generated.py` uses `pytest.skip(...)` locally but `pytest.fail(...)` when `CI=true`. Skill-repo CI explicitly installs `astral-sh/setup-uv@v3` so the fail-hard path never fires there. |
| Drift between uv-mode pin list and pip-mode pin list (ruff/pytest/pre-commit versions) | Template tests use a single canonical pin list (Python module-level constant or pytest fixture); both modes' tests assert against it. Drift fails the test. |
| Existing CLAUDE.md is a common adoption case (per call-details inspection); skill's CLAUDE.md.tmpl gets skipped, user loses the workflow guidance | Standard skip-if-exists; user gets `.new` via the safety contract (PR #1). Real-project trial in PR #7 will surface UX gaps in the merge experience and feed back into a future "CLAUDE.md merge tool" BACKLOG entry. NOT in scope for PR #6. |

## Verification (acceptance criteria for THIS plan PR)

### Phase 1 — pre-implementation evidence (this plan PR)

1. **Bidirectional plan-review loop** (under way — replace `ITERATION=N` with the current iteration each time):

   ```bash
   make review-plan-by-codex  PLAN_FILE=docs/plans/2026-05-18-skill-pr6-uv-support.md ITERATION=N
   make review-plan-by-claude PLAN_FILE=docs/plans/2026-05-18-skill-pr6-uv-support.md ITERATION=N
   ```

2. **Pre-next-iter consistency self-check** between every Codex/Claude iter:

   ```bash
   make review-plan-consistency-by-claude PLAN_FILE=docs/plans/2026-05-18-skill-pr6-uv-support.md ITERATION=<upcoming>
   ```

3. **Active-surface consistency check** — the expanded grep (see Bucket E).

4. **Mandatory human-approval gate** satisfied.

### Phase 2 — post-implementation gates

1. `make check` green in the skill repo (existing 200+ tests + ~20 new uv tests)
2. `make doctor` green (with `uv` advisory check passing on machines that have it; advisory-only — not a hard fail)
3. Generated-project smoke walks for **all four** combinations: python+pip (regression), python+uv (new), nodejs (regression), go (regression)
4. `make install-hooks` works in a generated python+uv project (pre-commit framework armed via `uv run pre-commit`)
5. Hook fires correctly on `git commit` in uv mode (ruff lint+format) and on `git push` (pytest via `uv run`)
6. Auto-detection on a fixture dir matching `call-details/` shape (uv.lock + uv_build pyproject) returns `"uv"` + prints advisory
7. claude[bot] auto-review fires on the implementation PR
8. Codex auto-review fires (or the BACKLOG'd ready-state-reliability fallback applies — `@codex review`)
9. Draft implementation PR opened from `feat/skill-pr6-uv-support` branch

## Iteration log (this plan)

| Iter | Findings | Verdict |
|---|---|---|
| 1 (codex) | TBD | TBD |

## Evidence table — what was folded and where

| Iter | Importance | Finding | Action |
|---|---|---|---|
| — | — | (filled in as iterations land) | — |

## What we are NOT doing in this PR

- **No `--python-version` CLI flag.** Hardcoded "3.12" stays.
- **No migration tool (pip → uv conversion).** Adoption respects existing tooling.
- **No deprecation of pip mode.** Both modes are first-class.
- **No real-project trial.** That's PR #7.
- **No uv equivalent for Node-TS or Go.** Their native managers (npm, go mod) are already optimal.
- **No uv pin in CI.** Floating `astral-sh/setup-uv@v3` default-latest. Trade-off documented.
- **No CLAUDE.md merge tooling.** Existing-file skip-and-write-`.new` is the contract. Merge experience is a PR #7 trial finding feeder.
- **No `pre-commit` framework removal in uv mode.** Stays. Just invocation changes.

## Critical files to read before each iter's review

For Codex / Claude:

- `docs/plans/2026-05-15-skill-pr3-go-language.md` — closest structural precedent (additive variant within an existing language pattern)
- `docs/plans/README.md` — workflow doc
- `bootstrap_lib/_flags.py` — exact place to add `--package-manager`
- `bootstrap_lib/cli.py` lines 97-109 — `_build_context` (where the resolution + advisory printing land)
- `bootstrap_lib/render.py` lines 1-100 — `PYTHON_TEMPLATE_MAP` + `_emit_in_mode` filtering pattern (uv-mode filtering joins this)
- `bootstrap_lib/detect.py` — current state (may be empty/minimal; the new helper joins here)
- `languages/python/Makefile.tmpl` — current pip-mode recipe (the uv branch mirrors structure)
- `languages/python/ci.yml.tmpl` — current setup-python recipe
- `languages/python/pyproject.toml.tmpl` — current setuptools backend (uv branch swaps to uv_build)
- `languages/python/requirements-dev.txt.tmpl` — current pin list (canonical source for both modes' deps)
- `languages/python/.pre-commit-config.yaml.tmpl` — current `entry:` line (single Jinja branch on pytest entry)
- `shared/CLAUDE.md.tmpl` Python-version section + `shared/CONTRIBUTING.md.tmpl` one-time setup section — places that need nested `{% if package_manager == 'uv' %}` branches
- `.github/workflows/ci.yml` (skill repo) — needs `astral-sh/setup-uv@v3` added (Bucket E)
- `Makefile` (skill repo) `doctor` target — needs `uv` advisory check
- Existing call-details target (`/Users/sandeep/Desktop/Code/Boxette/call-details/`) — the real-world example whose conflict shape motivated this PR; useful as a reality check on detection heuristics
