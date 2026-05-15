PYTHON ?= ./venv/bin/python

.PHONY: help venv install install-hooks test lint format check doctor \
        review-plan-by-codex review-plan-by-claude preflight-review-tooling

help:	## list all targets with descriptions
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-28s %s\n", $$1, $$2}'

venv:	## create venv with python3.12
	@test -d venv || python3.12 -m venv venv

install: venv	## install dev deps into venv (does NOT register hooks — see install-hooks)
	$(PYTHON) -m pip install -r requirements-dev.txt
	@echo "next step: 'make install-hooks' if this is a git repo"

install-hooks:	## install pre-commit hooks (requires .git/; safe to skip in non-git tempdirs)
	@test -d .git || { echo "skipping: not a git repo"; exit 0; }
	./venv/bin/pre-commit install
	./venv/bin/pre-commit install --hook-type pre-push

test:	## run pytest via venv
	$(PYTHON) -m pytest -v

lint:	## ruff check + format-check via venv
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:	## auto-fix lint + apply format via venv
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

check: lint test	## CI-equivalent — all tool invocations go through $(PYTHON)

doctor:	## check local prereqs (python3.12, git required; claude, codex advisory)
	@missing=0; \
	command -v python3.12 >/dev/null 2>&1 \
	  && echo "  ok       python3.12" \
	  || { echo "  MISSING  python3.12 (required — install via https://www.python.org/)"; missing=1; }; \
	command -v git >/dev/null 2>&1 \
	  && echo "  ok       git" \
	  || { echo "  MISSING  git (required)"; missing=1; }; \
	command -v node >/dev/null 2>&1 \
	  && echo "  ok       node" \
	  || echo "  advisory node not on PATH (only needed when bootstrapping --language nodejs OR running make check's nodejs smoke walk)"; \
	command -v npm >/dev/null 2>&1 \
	  && echo "  ok       npm" \
	  || echo "  advisory npm not on PATH (only needed when bootstrapping --language nodejs)"; \
	command -v go >/dev/null 2>&1 \
	  && echo "  ok       go" \
	  || echo "  advisory go not on PATH (only needed when bootstrapping --language go OR running make check's go smoke walk)"; \
	command -v claude >/dev/null 2>&1 \
	  && echo "  ok       claude" \
	  || echo "  advisory claude CLI not on PATH (only needed for make review-plan-by-claude)"; \
	command -v codex >/dev/null 2>&1 \
	  && echo "  ok       codex" \
	  || echo "  advisory codex CLI not on PATH (only needed for make review-plan-by-codex)"; \
	if [ $$missing -ne 0 ]; then echo ""; echo "missing core prereqs — see README.md"; exit 1; fi

# ── Plan-review automation ──────────────────────────────────────────────────
# Hand-written in PR #1 to be byte-identical to what
# shared/Makefile.review.tmpl renders for this repo's own context. The
# review-section block below (between the two sentinel comments) is the
# overlap target for tests/test_selftest_overlap.py — if it drifts from
# the rendered template, the selftest fails.

# SELFTEST-OVERLAP-BEGIN: shared/Makefile.review.tmpl
PLAN_FILE              ?=
ITERATION              ?= 1
PLAN_REVIEW_OUT_CODEX  ?= /tmp/plan-review-$(notdir $(basename $(PLAN_FILE)))-by-codex-iter-$(ITERATION).md
PLAN_REVIEW_OUT_CLAUDE ?= /tmp/plan-review-$(notdir $(basename $(PLAN_FILE)))-by-claude-iter-$(ITERATION).md

review-plan-by-codex:	## Codex skeptical review of a plan file (PLAN_FILE=docs/plans/foo.md [ITERATION=N])
	@test -n "$(PLAN_FILE)" || \
	  { echo "Usage: make review-plan-by-codex PLAN_FILE=docs/plans/<file>.md [ITERATION=N]"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	@command -v codex >/dev/null 2>&1 || \
	  { echo "codex CLI not found. Install + log in first (see CONTRIBUTING.md)."; exit 1; }
	$(CURDIR)/scripts/run-with-clean-env.py -- \
	  codex exec \
	    -C "$(CURDIR)" \
	    --sandbox read-only \
	    --color never \
	    --output-last-message "$(PLAN_REVIEW_OUT_CODEX)" \
	    "Review the plan file at $(PLAN_FILE). This is iteration $(ITERATION). Be skeptical and critical (not approving). Inspect the repository as needed to verify the plan's assumptions. Do NOT edit any files. Focus on: unsafe sequencing, hidden assumptions, missing verification, missing rollback / adoption path, phases that are too large, vague ownership / unclear acceptance criteria, places where manual copy-paste could be automated, hidden dependency on subscriptions / API keys / GitHub permissions / local tools, contradictions between the plan and current repository state, and places where the plan says 'later' but the dependency is actually needed earlier. Return findings ordered by importance (3 = blocker, 2 = improvement, 1 = polish). For each finding give: importance, what is wrong, why it matters, concrete suggested change. End with a stop/go verdict: 'ready after minor edits' / 'needs another iteration' / 'do not implement yet'. If there are no importance-3 findings, say that explicitly."
	@echo "──────────────────────────────────────────"
	@echo "Codex review written to: $(PLAN_REVIEW_OUT_CODEX)"
	@echo "──────────────────────────────────────────"
	@cat "$(PLAN_REVIEW_OUT_CODEX)"

review-plan-by-claude:	## Claude skeptical review of a plan file (PLAN_FILE=docs/plans/foo.md [ITERATION=N])
	@test -n "$(PLAN_FILE)" || \
	  { echo "Usage: make review-plan-by-claude PLAN_FILE=docs/plans/<file>.md [ITERATION=N]"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	@command -v claude >/dev/null 2>&1 || \
	  { echo "claude CLI not found. Install + log in first (see CONTRIBUTING.md)."; exit 1; }
	$(CURDIR)/scripts/run-with-clean-env.py -- \
	  claude \
	    --print \
	    --permission-mode plan \
	    --add-dir "$(CURDIR)" \
	    --output-format text \
	    "Review the plan file at $(PLAN_FILE). This is iteration $(ITERATION). Be skeptical and critical (not approving). Inspect the repository as needed to verify the plan's assumptions. Do NOT edit any files. Focus on: unsafe sequencing, hidden assumptions, missing verification, missing rollback / adoption path, phases that are too large, vague ownership / unclear acceptance criteria, places where manual copy-paste could be automated, hidden dependency on subscriptions / API keys / GitHub permissions / local tools, contradictions between the plan and current repository state, and places where the plan says 'later' but the dependency is actually needed earlier. Return findings ordered by importance (3 = blocker, 2 = improvement, 1 = polish). For each finding give: importance, what is wrong, why it matters, concrete suggested change. End with a stop/go verdict: 'ready after minor edits' / 'needs another iteration' / 'do not implement yet'. If there are no importance-3 findings, say that explicitly." \
	  > "$(PLAN_REVIEW_OUT_CLAUDE)"
	@echo "──────────────────────────────────────────"
	@echo "Claude review written to: $(PLAN_REVIEW_OUT_CLAUDE)"
	@echo "──────────────────────────────────────────"
	@cat "$(PLAN_REVIEW_OUT_CLAUDE)"

preflight-review-tooling:	## verify claude+codex CLIs work with the flag shape review targets expect
	@command -v codex >/dev/null 2>&1 || { echo "codex CLI not found"; exit 1; }
	@command -v claude >/dev/null 2>&1 || { echo "claude CLI not found"; exit 1; }
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
	@codex --version | grep -q "0\.130\." \
	    || echo "WARN: tested baseline is codex-cli 0.130.0; you have $$(codex --version)"
	@claude --version | grep -q "2\.1\.139" \
	    || echo "WARN: tested baseline is Claude Code 2.1.139; you have $$(claude --version)"
	@echo "✓ preflight ok"
# SELFTEST-OVERLAP-END: shared/Makefile.review.tmpl
