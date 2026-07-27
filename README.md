# dev-project-for-non-developers

> **Naming**: this is the **repo name** (audience-focused — describes who the skill is for). The **skill name** that shows up in Claude Code's registry, the Makefile target shipped to bootstrapped projects, and all internal references is **`dev-project-setup`** (action-focused — describes what the skill does). The two intentionally differ:
>
> - Repo: `dev-project-for-non-developers` — discoverable on GitHub by people looking for "I'm not a developer but I want a real dev workflow".
> - Skill: `dev-project-setup` — what `~/.claude/skills/dev-project-setup/` is symlinked to, what `bootstrap.py` identifies as, what the merged plan in Acme references throughout.
>
> If you fork this repo and rename, the skill name stays `dev-project-setup`; only the repo URL changes.

Bootstrap a working dev workflow into Python / Node-TS / Go projects:

- CI on GitHub Actions (`make check`-equivalent)
- Pre-commit (lint + format) + pre-push (tests) git hooks
- AI PR review (`claude[bot]` via workflow + `chatgpt-codex-connector[bot]` via Codex web-UI integration)
- **Bidirectional substantive-plan review loop** — Codex reviews Claude plans (`make review-plan-by-codex`) AND Claude reviews Codex plans (`make review-plan-by-claude`)
- Coherent doc set: `AGENTS.md` (reviewer guidance), `CLAUDE.md` (project memory), `CONTRIBUTING.md` (per-change workflow), `BACKLOG.md` (parked decisions), `docs/plans/` directory convention
- Sensible `.gitignore` and `.editorconfig`

Designed for non-developers using LLM-assisted workflows (Claude Code, Codex CLI) who want to start a new project with the guardrails of a mature codebase already in place — no recurring decision fatigue about CI, hooks, conventions, or how to do plan-then-implement properly.

**New project?** Run `bootstrap.py` with no arguments for a guided, interactive setup — it asks plain questions instead of requiring the CLI flags, and can even suggest a language from a plain-English description of your project. See [docs/usage.md](docs/usage.md).

## Status

**Python (uv + pip) + Node-TS + Go shipped; adoption-mode landed for Python.** PR #1 (merged) added the bootstrap engine + safety primitives + Python language templates + shared templates + bidirectional plan-review fragments. PR #2 added Node-TS (Biome + vitest + TypeScript + Husky). PR #3 added Go (gofumpt + golangci-lint + native git hooks). PR #6 added uv support for Python — **greenfield Python projects now default to `uv` (Astral)** for fast, modern dependency management; pip stays first-class for adoption-into-existing-pip-projects (auto-detected) + explicit opt-out via `--package-manager=pip`. PR #7 ships `--mode=adopt` — a **per-file analyze-then-decide-with-owner UX** for safely adopting the skill into existing Python projects (Node/Go adoption-mode parked for follow-up). All three v1 languages now supported. The master plan still lives in the Acme repo (bootstrap exception):

📋 `docs/plans/2026-05-15-dev-project-setup-skill.md` (private repo)

That plan converged through 3 Codex review iterations + an explicit human approval gate. It defines:

- Architecture (`bootstrap.py` + Jinja2 templates under `languages/<lang>/` and `shared/`)
- Bidirectional plan-review mechanism (`review-plan-by-codex` / `review-plan-by-claude` Makefile fragments)
- Adoption safety contract (`--dry-run` default, `--diff`, `--apply`, restore manifest, atomic per-file writes). PR #1 ships hook adoption via the generated project's `make install-hooks` target (scoped to the target project's venv); a direct `--install-hooks` bootstrap flag is parked as follow-up — see `BACKLOG.md`.
- `--github-review=none|claude|both-docs` mode flag (no orphan checklist text when GitHub auto-review isn't wired)
- Per-PR deliverables table with per-subsystem acceptance gates
- Tested-baseline CLI version strategy (Claude Code 2.1.139, codex-cli 0.130.0; `make preflight-review-tooling` for forward drift)

## Build sequence

Per the plan:

- **PR #1** ✅ minimal working Python bootstrap + all `shared/` templates (including both `review-plan-by-*` Makefile fragments) + safety primitives + skill's own `make check` green + per-subsystem acceptance gates (A–F)
- **PR #2** ✅ add `languages/nodejs/` (Biome + vitest + TypeScript + Husky)
- **PR #3** ✅ add `languages/go/` (gofumpt + golangci-lint + native git hooks)
- **PR #4** ✅ two-tier code review + plan-loop improvements (Tier-1 `make review-commit-by-*` targets, plan-review prompt cross-section instruction, `make review-plan-consistency-by-claude` self-check target, four-questions triage extension)
- **PR #5** ✅ observability + self-improvement layer (`make status` for cross-session/post-compaction recovery; `LESSONS.md` append-only log with writable-session-only rule; plan-file Implementation log convention + Tier-1 `PLAN_FILE=` binding; `/simplify` as optional Tier-1 step). Shipped across 3 sequential impl PRs (#5a foundation, #5b Tier-1+impl-log, #5c `/simplify`+docs+BACKLOG)
- **PR #6** ✅ uv support for Python — `--package-manager={uv,pip}` flag, default `uv` for greenfield, auto-detect for adoption. Non-package mode for greenfield uv (no `[build-system]`); `astral-sh/setup-uv@v8.1.0` in generated CI; `uv sync --locked` strict-lock enforcement; pre-commit framework stays the hook engine in both modes. Co-landed the `--permission-mode plan` bug fix across all 5 Claude review targets — `review-plan-by-claude`, `review-plan-consistency-by-claude`, both `review-commit-by-claude` invocations (with/without PLAN_FILE), and `preflight-review-tooling`'s claude smoke (BACKLOG f).
- **PR #7** ✅ hybrid real-project trial + adoption-mode redesign on `~/code/downstream-app/`. Ships the **analyze-then-decide-with-owner adoption-mode UX** (`--mode=adopt`) — per-file Scope #5 heuristics (rules a0/a..h) recommend `SKIP` / `WRITE` / `OVERWRITE` / `WRITE_NEW` / `APPEND_MERGE` policies; the user decides on flagged files via stdin prompts (`[r]ecommended` / `[s]kip` / `[d]iff` / `[n]ew` / `[a]ppend` (`.gitignore` only) / `[o]verwrite` with typed `OVERWRITE` confirmation / `[?]help` / `[q]uit`); writes flow through a v2 manifest (`format_version=2`) so `--restore` can roll back per-policy. **Safety floor**: rule (h) defaults unknown existing files to `SKIP` (never destructive `WRITE`); WRITE_NEW writes `<path>.new` alongside the original, never touching the original; APPEND_MERGE is `.gitignore`-only (line-level idempotent). The full pipeline is gated by `--apply --mode=adopt --language=python`. `--auto-accept-recommendations` + `--non-interactive` enable the CI contract ("accept everything safe, fail loud on anything needing review").

Each PR uses the bidirectional plan-review loop on its own plan. PR #1 is the bootstrap exception: its plan is reviewed with Acme's existing `make review-plan` (Codex direction only) since the skill doesn't self-host the loop yet.

## How this repo relates to Acme

> **Placeholder names.** This skill was extracted from private work. Throughout
> this repo, **`Acme`** stands in for the origin project and **`downstream-app`**
> for the real-world project used as the adoption/dogfood target. They are not
> public repos; the names are placeholders so the history reads coherently
> without publishing someone else's project layout.

Acme, a private project, is where these patterns were developed iteratively across Phases 1, 2, 2.5, 2.6, 2.7. This skill extracts them into reusable templates so future projects don't reinvent the workflow.

## License

[MIT](LICENSE) — use, modify and redistribute freely, including in commercial
work; just keep the copyright notice.

Note on generated output: files rendered from the Jinja templates are yours to
treat as your own. A few helper scripts are shipped **verbatim** (see
`SHARED_VERBATIM_MAP` in `bootstrap_lib/render.py`); those are substantial
portions of this work, so MIT's notice requirement travels with them.
