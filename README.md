# dev-project-for-non-developers

> **Naming**: this is the **repo name** (audience-focused — describes who the skill is for). The **skill name** that shows up in Claude Code's registry, the Makefile target shipped to bootstrapped projects, and all internal references is **`dev-project-setup`** (action-focused — describes what the skill does). The two intentionally differ:
>
> - Repo: `dev-project-for-non-developers` — discoverable on GitHub by people looking for "I'm not a developer but I want a real dev workflow".
> - Skill: `dev-project-setup` — what `~/.claude/skills/dev-project-setup/` is symlinked to, what `bootstrap.py` identifies as, what the merged plan in Boxette references throughout.
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

## Status

**Plan stage.** The skill itself isn't built yet — only the plan exists. Read the plan in the Boxette repo (bootstrap exception — the plan was written there before this repo existed; future plans live in this repo's `docs/plans/` under the same convention the plan itself describes):

📋 [`docs/plans/2026-05-15-dev-project-setup-skill.md`](https://github.com/v3rmus89/boxette-tgbot/blob/main/docs/plans/2026-05-15-dev-project-setup-skill.md)

That plan converged through 3 Codex review iterations + an explicit human approval gate. It defines:

- Architecture (`bootstrap.py` + Jinja2 templates under `languages/<lang>/` and `shared/`)
- Bidirectional plan-review mechanism (`review-plan-by-codex` / `review-plan-by-claude` Makefile fragments)
- Adoption safety contract (`--dry-run` default, `--diff`, `--apply`, restore manifest, atomic per-file writes). PR #1 ships hook adoption via the generated project's `make install-hooks` target (scoped to the target project's venv); a direct `--install-hooks` bootstrap flag is parked as follow-up — see `BACKLOG.md`.
- `--github-review=none|claude|both-docs` mode flag (no orphan checklist text when GitHub auto-review isn't wired)
- Per-PR deliverables table with per-subsystem acceptance gates
- Tested-baseline CLI version strategy (Claude Code 2.1.139, codex-cli 0.130.0; `make preflight-review-tooling` for forward drift)

## Build sequence

Per the plan:

- **PR #1** — minimal working Python bootstrap + all `shared/` templates (including both `review-plan-by-*` Makefile fragments) + safety primitives + skill's own `make check` green + per-subsystem acceptance gates (A–F)
- **PR #2** — add `languages/nodejs/` (Biome + vitest)
- **PR #3** — add `languages/go/` (gofumpt + golangci-lint)
- **PR #4** — real-project trial + `docs/lessons.md`

Each PR uses the bidirectional plan-review loop on its own plan. PR #1 is the bootstrap exception: its plan is reviewed with Boxette's existing `make review-plan` (Codex direction only) since the skill doesn't self-host the loop yet.

## How this repo relates to Boxette

[Boxette UZ Telegram Bot](https://github.com/v3rmus89/boxette-tgbot) is where these patterns were developed iteratively across Phases 1, 2, 2.5, 2.6, 2.7. This skill extracts them into reusable templates so future projects don't reinvent the workflow.

## License

TBD (will be set before going public).
