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
	if command -v go >/dev/null 2>&1; then \
	  go_ver=$$(go version 2>/dev/null | awk '{print $$3}' | sed 's/^go//'); \
	  go_major=$$(echo "$$go_ver" | cut -d. -f1); \
	  go_minor=$$(echo "$$go_ver" | cut -d. -f2); \
	  if [ -n "$$go_major" ] && [ -n "$$go_minor" ] && { [ "$$go_major" -gt 1 ] || { [ "$$go_major" -eq 1 ] && [ "$$go_minor" -ge 26 ]; }; }; then \
	    echo "  ok       go ($$go_ver)"; \
	  else \
	    echo "  advisory go $$go_ver is older than the pinned 1.26 (generated go.mod requires 1.26+; older toolchains either auto-download or fail under GOTOOLCHAIN=local)"; \
	  fi; \
	else \
	  echo "  advisory go not on PATH (only needed when bootstrapping --language go OR running make check's go smoke walk)"; \
	fi; \
	command -v uv >/dev/null 2>&1 \
	  && echo "  ok       uv" \
	  || echo "  advisory uv not on PATH (only needed when bootstrapping --package-manager=uv OR running make check's uv smoke walk)"; \
	command -v claude >/dev/null 2>&1 \
	  && echo "  ok       claude" \
	  || echo "  advisory claude CLI not on PATH (needed for make review-{plan,commit,plan-consistency}-by-claude)"; \
	command -v codex >/dev/null 2>&1 \
	  && echo "  ok       codex" \
	  || echo "  advisory codex CLI not on PATH (needed for make review-{plan,commit}-by-codex)"; \
	if [ $$missing -ne 0 ]; then echo ""; echo "missing core prereqs — see README.md"; exit 1; fi

# ── Plan-review automation ──────────────────────────────────────────────────
# Hand-written in PR #1 to be byte-identical to what
# shared/Makefile.review.tmpl renders for this repo's own context. The
# review-section block below (between the two sentinel comments) is the
# overlap target for tests/test_selftest_overlap.py — if it drifts from
# the rendered template, the selftest fails.

# SELFTEST-OVERLAP-BEGIN: shared/Makefile.review.tmpl
PLAN_FILE                ?=
ITERATION                ?= 1
PLAN_REVIEW_OUT_CODEX    ?= /tmp/plan-review-$(notdir $(basename $(PLAN_FILE)))-by-codex-iter-$(ITERATION).md
PLAN_REVIEW_OUT_CLAUDE   ?= /tmp/plan-review-$(notdir $(basename $(PLAN_FILE)))-by-claude-iter-$(ITERATION).md
REVIEW_COMMIT_SHA        ?= $(shell git -C $(CURDIR) rev-parse --short HEAD 2>/dev/null || echo nogit)
REVIEW_COMMIT_OUT_CODEX  ?= /tmp/review-commit-$(REVIEW_COMMIT_SHA)-by-codex.md
REVIEW_COMMIT_OUT_CLAUDE ?= /tmp/review-commit-$(REVIEW_COMMIT_SHA)-by-claude.md
PLAN_CONSISTENCY_OUT     ?= /tmp/review-plan-consistency-$(notdir $(basename $(PLAN_FILE)))-iter-$(ITERATION).md
KEY = $(shell python3 -c "import hashlib,os; k = os.path.realpath('$(CURDIR)') + ':' + os.path.realpath('$(PLAN_FILE)'); print(hashlib.sha256(k.encode()).hexdigest()[:12])")
HASH_FILE = /tmp/plan-review-$(KEY).hash
CONS_FILE = /tmp/plan-review-$(KEY).consistency
SNAP_DIR  = /tmp/plan-snapshots/$(KEY)
# Bucket F (opt-in; default fresh): Codex thread-continuation state. THREAD_FILE
# holds the resumable session ID; THREAD_JSONL_FILE is the seed call's --json
# capture, deleted after extraction unless KEEP_THREAD_JSONL=1.
THREAD_MODE       ?= fresh
THREAD_FILE       = /tmp/plan-review-$(KEY).thread
THREAD_JSONL_FILE = /tmp/plan-review-$(KEY).session.jsonl
FACT_CHECK_FACTS_OUT  ?= /tmp/plan-fact-check-$(KEY).facts.json
FACT_CHECK_VERIFY_OUT ?= /tmp/plan-fact-check-$(KEY).verify.json
PLAN_FACT_CHECK_OUT_CODEX  ?= /tmp/plan-fact-check-$(notdir $(basename $(PLAN_FILE)))-by-codex.md
PLAN_FACT_CHECK_OUT_CLAUDE ?= /tmp/plan-fact-check-$(notdir $(basename $(PLAN_FILE)))-by-claude.md
# `make review` dispatcher (MODE={plan,commit} ACTOR={claude,codex}). ACTOR
# precedence: an explicit ACTOR= on the command line wins; else $(REVIEWER)
# (a terminal `export REVIEWER=...` convenience — a Claude/Codex per-tool-call
# export does NOT persist to a later make, so the slash command / AGENTS.md
# pass ACTOR inline); else unset -> NEEDS-ASK. REVIEW_RESOLVE=1 prints the
# resolved target and exits 0 WITHOUT invoking codex/claude (test hook).
MODE           ?=
REVIEWER       ?=
ACTOR          ?= $(REVIEWER)
REVIEW_RESOLVE ?=
# Sanitize MODE/ACTOR to a fixed allowlist with $(filter) (a MAKE function —
# no shell). This guards the RECIPE-SHELL resolution: a quote-breaking value
# (e.g. ACTOR=x"; rm -rf ~; echo ") filters to empty -> NEEDS-ASK, so the
# recipe's `case`/`$$TARGET` never sees raw input. It does NOT (and cannot, at
# the make level) stop a `$(shell ...)` embedded in the RAW value from running
# when make expands $(ACTOR) — that is inherent to GNU make (it affects every
# $(VAR)) and the values here come only from /dev-review's fixed literals or
# the user's own shell (no untrusted-input boundary). Repo-wide make-expansion
# hardening (incl. PLAN_FILE/ITERATION) is parked in BACKLOG.
_REVIEW_MODE  = $(and $(filter 1,$(words $(MODE))),$(filter plan commit,$(MODE)))
_REVIEW_ACTOR = $(and $(filter 1,$(words $(ACTOR))),$(filter claude codex,$(ACTOR)))

.PHONY: review review-plan-by-codex review-plan-by-claude \
        review-commit-by-codex review-commit-by-claude \
        review-plan-consistency-by-claude \
        review-plan-fact-check-by-codex review-plan-fact-check-by-claude \
        loop-ack loop-reset loop-status \
        preflight-review-tooling \
        status

review:	## dispatch a review to the right target: MODE={plan,commit} ACTOR={claude,codex} [PLAN_FILE=... ITERATION=...] (plan = cross-direction, commit = same-AI)
	@ACTOR="$(_REVIEW_ACTOR)"; MODE="$(_REVIEW_MODE)"; \
	if [ -z "$$ACTOR" ]; then \
	  TARGET="NEEDS-ASK"; \
	else \
	  case "$$MODE:$$ACTOR" in \
	    plan:claude)   TARGET="review-plan-by-codex" ;; \
	    plan:codex)    TARGET="review-plan-by-claude" ;; \
	    commit:claude) TARGET="review-commit-by-claude" ;; \
	    commit:codex)  TARGET="review-commit-by-codex" ;; \
	    *)             TARGET="NEEDS-ASK" ;; \
	  esac; \
	fi; \
	if [ "$(REVIEW_RESOLVE)" = "1" ]; then \
	  echo "$$TARGET"; \
	  exit 0; \
	fi; \
	if [ "$$TARGET" = "NEEDS-ASK" ]; then \
	  echo "NEEDS-ASK"; \
	  echo "make review needs MODE={plan,commit} and ACTOR={claude,codex}." >&2; \
	  echo "  plan review is cross-direction (claude->codex, codex->claude); commit review is same-AI." >&2; \
	  echo "  Claude: run /dev-review.  Codex/terminal: pass ACTOR=codex (or set REVIEWER) inline." >&2; \
	  exit 2; \
	fi; \
	case "$$MODE" in \
	  plan)   $(MAKE) "$$TARGET" PLAN_FILE="$(PLAN_FILE)" ITERATION="$(ITERATION)" ;; \
	  commit) $(MAKE) "$$TARGET" PLAN_FILE="$(PLAN_FILE)" ;; \
	esac

review-plan-by-codex:	## Codex skeptical review of a plan file (PLAN_FILE=docs/plans/foo.md [ITERATION=N])
	@test -n "$(PLAN_FILE)" || \
	  { echo "Usage: make review-plan-by-codex PLAN_FILE=docs/plans/<file>.md [ITERATION=N]"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	@command -v codex >/dev/null 2>&1 || \
	  { echo "codex CLI not found. Install + log in first (see CONTRIBUTING.md)."; exit 1; }
	@CURR_HASH=$$(shasum -a 256 "$(PLAN_FILE)" | awk '{print $$1}'); \
	  if [ -f "$(HASH_FILE)" ]; then \
	    PREV_HASH=$$(cat "$(HASH_FILE)"); \
	    if [ "$$CURR_HASH" != "$$PREV_HASH" ] && [ "$(ITERATION)" -gt 1 ]; then \
	      echo "Plan hash changed since iter $$(( $(ITERATION) - 1 )) — external edit or unacknowledged fold detected."; \
	      echo "Expected: $$PREV_HASH"; \
	      echo "Got:      $$CURR_HASH"; \
	      echo "If this was a legitimate fold:"; \
	      echo "  1) make review-plan-consistency-by-claude PLAN_FILE=$(PLAN_FILE) ITERATION=N.5"; \
	      echo "  2) fold any drift the consistency check finds"; \
	      echo "  3) make loop-ack PLAN_FILE=$(PLAN_FILE)"; \
	      echo "  4) re-run this review target."; \
	      echo "If you want to discard the loop and start over: make loop-reset PLAN_FILE=$(PLAN_FILE) (deletes hash/cons/snapshot state)."; \
	      echo "Snapshots remain in $(SNAP_DIR)/."; \
	      exit 2; \
	    fi; \
	  fi
	@mkdir -p "$(SNAP_DIR)"; \
	  cp "$(PLAN_FILE)" "$(SNAP_DIR)/iter$(ITERATION).bak"; \
	  echo "Snapshot: $(SNAP_DIR)/iter$(ITERATION).bak"
	@PROMPT="$$(PLAN_FILE="$(PLAN_FILE)" ITERATION="$(ITERATION)" KEY="$(KEY)" $(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/prompts/plan-review.txt)" || exit $$?; \
	if [ "$(THREAD_MODE)" = "continue" ]; then \
	  if [ -f "$(THREAD_FILE)" ]; then \
	    SESSION_ID=$$(cat "$(THREAD_FILE)"); \
	    echo "THREAD_MODE=continue: resuming Codex session $$SESSION_ID"; \
	    if OUT=$$($(CURDIR)/scripts/run-with-clean-env.py -- codex exec resume "$$SESSION_ID" -c sandbox_mode=read-only --output-last-message "$(PLAN_REVIEW_OUT_CODEX)" "$$PROMPT" < /dev/null 2>&1); then \
	      echo "$$OUT"; \
	    else \
	      rc=$$?; \
	      echo "$$OUT" >&2; \
	      if printf '%s' "$$OUT" | grep -q 'no rollout found for thread id'; then \
	        echo "WARN: stale Codex session — clearing thread state, falling back to a one-shot fresh exec for this call" >&2; \
	        rm -f "$(THREAD_FILE)" "$(THREAD_JSONL_FILE)"; \
	        $(CURDIR)/scripts/run-with-clean-env.py -- codex exec -C "$(CURDIR)" --sandbox read-only --color never --output-last-message "$(PLAN_REVIEW_OUT_CODEX)" "$$PROMPT" < /dev/null; \
	      else \
	        exit $$rc; \
	      fi; \
	    fi; \
	  else \
	    echo "THREAD_MODE=continue: seeding a new Codex session (no THREAD_FILE yet)"; \
	    $(CURDIR)/scripts/run-with-clean-env.py -- codex exec --json -C "$(CURDIR)" --sandbox read-only --color never --output-last-message "$(PLAN_REVIEW_OUT_CODEX)" "$$PROMPT" < /dev/null > "$(THREAD_JSONL_FILE)" \
	      && $(CURDIR)/scripts/extract-codex-session-id.py "$(THREAD_JSONL_FILE)" > "$(THREAD_FILE).tmp" \
	      && grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$$' "$(THREAD_FILE).tmp" \
	      && mv "$(THREAD_FILE).tmp" "$(THREAD_FILE)" \
	      || { rm -f "$(THREAD_FILE).tmp" "$(THREAD_FILE)" "$(THREAD_JSONL_FILE)"; echo "ERROR: codex exec or session ID extraction failed" >&2; exit 1; }; \
	    [ "$${KEEP_THREAD_JSONL:-}" = "1" ] || rm -f "$(THREAD_JSONL_FILE)"; \
	  fi; \
	else \
	    $(CURDIR)/scripts/run-with-clean-env.py -- codex exec -C "$(CURDIR)" --sandbox read-only --color never --output-last-message "$(PLAN_REVIEW_OUT_CODEX)" "$$PROMPT" < /dev/null; \
	fi
	@shasum -a 256 "$(PLAN_FILE)" | awk '{print $$1}' > "$(HASH_FILE)"
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
	@CURR_HASH=$$(shasum -a 256 "$(PLAN_FILE)" | awk '{print $$1}'); \
	  if [ -f "$(HASH_FILE)" ]; then \
	    PREV_HASH=$$(cat "$(HASH_FILE)"); \
	    if [ "$$CURR_HASH" != "$$PREV_HASH" ] && [ "$(ITERATION)" -gt 1 ]; then \
	      echo "Plan hash changed since iter $$(( $(ITERATION) - 1 )) — external edit or unacknowledged fold detected."; \
	      echo "Expected: $$PREV_HASH"; \
	      echo "Got:      $$CURR_HASH"; \
	      echo "If this was a legitimate fold:"; \
	      echo "  1) make review-plan-consistency-by-claude PLAN_FILE=$(PLAN_FILE) ITERATION=N.5"; \
	      echo "  2) fold any drift the consistency check finds"; \
	      echo "  3) make loop-ack PLAN_FILE=$(PLAN_FILE)"; \
	      echo "  4) re-run this review target."; \
	      echo "If you want to discard the loop and start over: make loop-reset PLAN_FILE=$(PLAN_FILE) (deletes hash/cons/snapshot state)."; \
	      echo "Snapshots remain in $(SNAP_DIR)/."; \
	      exit 2; \
	    fi; \
	  fi
	@mkdir -p "$(SNAP_DIR)"; \
	  cp "$(PLAN_FILE)" "$(SNAP_DIR)/iter$(ITERATION).bak"; \
	  echo "Snapshot: $(SNAP_DIR)/iter$(ITERATION).bak"
	@PROMPT="$$(PLAN_FILE="$(PLAN_FILE)" ITERATION="$(ITERATION)" KEY="$(KEY)" $(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/prompts/plan-review.txt)" || exit $$?; \
	$(CURDIR)/scripts/run-with-clean-env.py -- \
	  claude \
	    --print \
	    --add-dir "$(CURDIR)" \
	    --output-format text \
	    "$$PROMPT" \
	  > "$(PLAN_REVIEW_OUT_CLAUDE)"
	@shasum -a 256 "$(PLAN_FILE)" | awk '{print $$1}' > "$(HASH_FILE)"
	@echo "──────────────────────────────────────────"
	@echo "Claude review written to: $(PLAN_REVIEW_OUT_CLAUDE)"
	@echo "──────────────────────────────────────────"
	@cat "$(PLAN_REVIEW_OUT_CLAUDE)"

review-commit-by-codex:	## Codex review of the most recent commit (Tier-1). PLAN_FILE=docs/plans/<active>.md to bind plan-drift check.
	@if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  echo "skipping: not a git repo"; exit 0; \
	fi; \
	if ! git rev-parse --verify HEAD >/dev/null 2>&1; then \
	  echo "skipping: no commits yet — Tier-1 reviews a specific commit; make one first"; exit 0; \
	fi; \
	if ! command -v codex >/dev/null 2>&1; then \
	  echo "codex CLI not found. Install + log in first (see CONTRIBUTING.md)."; exit 1; \
	fi; \
	if ! git diff --quiet || ! git diff --cached --quiet; then \
	  echo "WARN: worktree has uncommitted changes; reviewer will see the dirty state, not just HEAD" >&2; \
	fi; \
	if [ -n "$(PLAN_FILE)" ]; then \
	  if [ ! -f "$(PLAN_FILE)" ]; then \
	    echo "PLAN_FILE not found: $(PLAN_FILE)"; exit 1; \
	  fi; \
	  PROMPT="$$(COMMIT_REF="HEAD" PLAN_FILE="$(PLAN_FILE)" $(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/prompts/commit-review-plan-bound.txt)" || exit $$?; \
	  $(CURDIR)/scripts/run-with-clean-env.py -- \
	    codex exec \
	      -C "$(CURDIR)" \
	      --sandbox read-only \
	      --color never \
	      --output-last-message "$(REVIEW_COMMIT_OUT_CODEX)" \
	      "$$PROMPT" \
	    && cat "$(REVIEW_COMMIT_OUT_CODEX)"; \
	else \
	  PROMPT="$$(COMMIT_REF="HEAD" $(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/prompts/commit-review-unbound.txt)" || exit $$?; \
	  $(CURDIR)/scripts/run-with-clean-env.py -- \
	    codex exec \
	      -C "$(CURDIR)" \
	      --sandbox read-only \
	      --color never \
	      --output-last-message "$(REVIEW_COMMIT_OUT_CODEX)" \
	      "$$PROMPT" \
	    && cat "$(REVIEW_COMMIT_OUT_CODEX)"; \
	fi

review-commit-by-claude:	## Claude review of the most recent commit (Tier-1). PLAN_FILE=docs/plans/<active>.md to bind plan-drift check.
	@if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  echo "skipping: not a git repo"; exit 0; \
	fi; \
	if ! git rev-parse --verify HEAD >/dev/null 2>&1; then \
	  echo "skipping: no commits yet — Tier-1 reviews a specific commit; make one first"; exit 0; \
	fi; \
	if ! command -v claude >/dev/null 2>&1; then \
	  echo "claude CLI not found. Install + log in first (see CONTRIBUTING.md)."; exit 1; \
	fi; \
	if ! git diff --quiet || ! git diff --cached --quiet; then \
	  echo "WARN: worktree has uncommitted changes; reviewer will see the dirty state, not just HEAD" >&2; \
	fi; \
	if [ -n "$(PLAN_FILE)" ]; then \
	  if [ ! -f "$(PLAN_FILE)" ]; then \
	    echo "PLAN_FILE not found: $(PLAN_FILE)"; exit 1; \
	  fi; \
	  PROMPT="$$(COMMIT_REF="HEAD" PLAN_FILE="$(PLAN_FILE)" $(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/prompts/commit-review-plan-bound.txt)" || exit $$?; \
	  $(CURDIR)/scripts/run-with-clean-env.py -- \
	    claude --print --add-dir "$(CURDIR)" \
	      --output-format text \
	      "$$PROMPT" \
	    > "$(REVIEW_COMMIT_OUT_CLAUDE)" \
	    && cat "$(REVIEW_COMMIT_OUT_CLAUDE)"; \
	else \
	  PROMPT="$$(COMMIT_REF="HEAD" $(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/prompts/commit-review-unbound.txt)" || exit $$?; \
	  $(CURDIR)/scripts/run-with-clean-env.py -- \
	    claude --print --add-dir "$(CURDIR)" \
	      --output-format text \
	      "$$PROMPT" \
	    > "$(REVIEW_COMMIT_OUT_CLAUDE)" \
	    && cat "$(REVIEW_COMMIT_OUT_CLAUDE)"; \
	fi

review-plan-consistency-by-claude:	## Self-check: scan plan for self-contradictions after a fold (PLAN_FILE=... [ITERATION=N])
	@test -n "$(PLAN_FILE)" || \
	  { echo "Usage: make review-plan-consistency-by-claude PLAN_FILE=docs/plans/<file>.md [ITERATION=N]"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	@command -v claude >/dev/null 2>&1 || \
	  { echo "claude CLI not found."; exit 1; }
	@PROMPT="$$(PLAN_FILE="$(PLAN_FILE)" $(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/prompts/plan-consistency.txt)" || exit $$?; \
	$(CURDIR)/scripts/run-with-clean-env.py -- \
	  claude --print --add-dir "$(CURDIR)" \
	    --output-format text \
	    "$$PROMPT" \
	  > "$(PLAN_CONSISTENCY_OUT)" \
	  && cat "$(PLAN_CONSISTENCY_OUT)"
	@shasum -a 256 "$(PLAN_FILE)" | awk '{print $$1}' > "$(CONS_FILE)"

loop-ack:	## Acknowledge a legitimate fold: re-stamp the integrity hash (requires consistency check first)
	@test -n "$(PLAN_FILE)" || { echo "Usage: make loop-ack PLAN_FILE=docs/plans/<file>.md"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	@CURR_HASH=$$(shasum -a 256 "$(PLAN_FILE)" | awk '{print $$1}'); \
	  if [ ! -f "$(CONS_FILE)" ]; then \
	    echo "No consistency marker found at $(CONS_FILE)."; \
	    echo 'Run `make review-plan-consistency-by-claude PLAN_FILE=$(PLAN_FILE) ITERATION=N.5` before acking.'; \
	    exit 3; \
	  fi; \
	  CONS_HASH=$$(cat "$(CONS_FILE)"); \
	  if [ "$$CURR_HASH" != "$$CONS_HASH" ]; then \
	    echo "Plan has changed since last consistency check (cons=$$CONS_HASH, curr=$$CURR_HASH)."; \
	    echo 'Run `make review-plan-consistency-by-claude PLAN_FILE=$(PLAN_FILE) ITERATION=N.5` before acking.'; \
	    exit 3; \
	  fi; \
	  echo "$$CURR_HASH" > "$(HASH_FILE)"; \
	  echo "Acknowledged. Hash file: $(HASH_FILE) → $$CURR_HASH"

loop-reset:	## Reset loop state: remove hash/consistency/snapshot artifacts for this plan
	@test -n "$(PLAN_FILE)" || { echo "Usage: make loop-reset PLAN_FILE=docs/plans/<file>.md"; exit 1; }
	@rm -f "$(HASH_FILE)" "$(CONS_FILE)" "$(THREAD_FILE)" "$(THREAD_JSONL_FILE)"
	@rm -rf "$(SNAP_DIR)"
	@echo "Loop state reset. Hash/consistency/snapshot artifacts removed for this plan."
	@echo "Next plan-review will start at iter 1 with no baseline."

loop-status:	## Show convergence status of the plan-review loop (PLAN_FILE=docs/plans/foo.md)
	@test -n "$(PLAN_FILE)" || \
	  { echo "Usage: make loop-status PLAN_FILE=docs/plans/<file>.md"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	$(CURDIR)/scripts/loop-status.py "$(KEY)" /tmp "$(notdir $(basename $(PLAN_FILE)))"

status:	## Synthesize current project state (recovery for new sessions / post-compaction). PLAN_FILE=<path> to override plan-detect; otherwise mtime-sorted with README filtered
	@echo "── Current branch activity ──"
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  branch=$$(git rev-parse --abbrev-ref HEAD 2>/dev/null); \
	  if git rev-parse --verify HEAD >/dev/null 2>&1; then \
	    echo "(branch: $$branch)"; \
	    git log --oneline -10 HEAD; \
	  else echo "(branch: $$branch; no commits yet)"; fi; \
	else echo "(not a git repo)"; fi
	@echo ""
	@echo "── Recent main activity ──"
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  ref=""; \
	  if git rev-parse --verify origin/main >/dev/null 2>&1; then ref="origin/main"; \
	  elif git rev-parse --verify main >/dev/null 2>&1; then ref="main"; \
	  elif git rev-parse --verify HEAD >/dev/null 2>&1; then ref="HEAD"; \
	  fi; \
	  if [ -n "$$ref" ]; then \
	    echo "(ref: $$ref)"; \
	    git log --oneline -10 "$$ref"; \
	  else echo "(no commits yet)"; fi; \
	else echo "(not a git repo)"; fi
	@echo ""
	@echo "── Open PRs ──"
	@if command -v gh >/dev/null 2>&1; then \
	  out=$$(gh pr list --state open --json number,title,headRefName,isDraft --jq '.[] | "#\(.number)  [\(if .isDraft then "draft" else "ready" end)]  \(.title)"' 2>/dev/null); \
	  rc=$$?; \
	  if [ "$$rc" -ne 0 ]; then echo "(gh CLI unauthed or repo not on github)"; \
	  elif [ -z "$$out" ]; then echo "(no open PRs)"; \
	  else echo "$$out"; fi; \
	else echo "(gh CLI not available)"; fi
	@echo ""
	@echo "── Active plan ──"
	@if [ -n "$(PLAN_FILE)" ] && [ ! -f "$(PLAN_FILE)" ]; then \
	  echo "(PLAN_FILE not found: $(PLAN_FILE))"; \
	elif [ -n "$(PLAN_FILE)" ]; then \
	  echo "$(PLAN_FILE) (PLAN_FILE override)"; \
	  awk 'BEGIN{p=0} /^```/{f=!f; next} /^## Iteration log/ && !f {p=1; print; next} /^## / && p && !f {exit} p && !f {print}' "$(PLAN_FILE)" | tail -20 || true; \
	  echo ""; \
	  echo "  (Implementation log tail:)"; \
	  impl_log=$$(awk 'BEGIN{p=0} /^```/{f=!f; next} /^## Implementation log/ && !f {p=1; print; next} /^## / && p && !f {exit} p && !f {print}' "$(PLAN_FILE)"); \
	  if [ -z "$$impl_log" ]; then echo "  (no Implementation log section yet)"; else echo "$$impl_log" | tail -20; fi; \
	else \
	  if ls docs/plans/*.md >/dev/null 2>&1; then \
	    candidates=$$(ls -t docs/plans/*.md | grep -vE 'README\.md$$'); \
	    if [ -z "$$candidates" ]; then \
	      echo "(no plan files)"; \
	    else \
	      count=$$(echo "$$candidates" | wc -l | tr -d ' '); \
	      latest=$$(echo "$$candidates" | head -1); \
	      echo "$$latest (auto-detected by mtime; pass PLAN_FILE=... to override)"; \
	      if [ "$$count" -gt 1 ]; then \
	        echo "!!! WARN: $$count PLAN FILES PRESENT — top 3 by mtime (pass PLAN_FILE=... to override):"; \
	        echo "$$candidates" | head -3 | sed 's|^|  - |'; \
	      fi; \
	      awk 'BEGIN{p=0} /^```/{f=!f; next} /^## Iteration log/ && !f {p=1; print; next} /^## / && p && !f {exit} p && !f {print}' "$$latest" | tail -20 || true; \
	      echo ""; \
	      echo "  (Implementation log tail:)"; \
	      impl_log2=$$(awk 'BEGIN{p=0} /^```/{f=!f; next} /^## Implementation log/ && !f {p=1; print; next} /^## / && p && !f {exit} p && !f {print}' "$$latest"); \
	      if [ -z "$$impl_log2" ]; then echo "  (no Implementation log section yet)"; else echo "$$impl_log2" | tail -20; fi; \
	    fi; \
	  else echo "(no plan files)"; fi; \
	fi
	@echo ""
	@echo "── Active lessons ──"
	@if [ -f LESSONS.md ]; then awk 'BEGIN{p=0} /^## Active[[:space:]]*$$/{p=1; next} /^## Archived[[:space:]]*$$/{exit} p' LESSONS.md | head -50; else echo "(no LESSONS.md)"; fi
	@echo ""
	@echo "── Local repo state ──"
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  out=$$(git status --short); \
	  if [ -z "$$out" ]; then echo "(clean)"; else echo "$$out"; fi; \
	else echo "(not a git repo)"; fi
	@echo ""
	@echo "── Health checks ──"
	@for tool in git gh claude codex; do \
	  if command -v $$tool >/dev/null 2>&1; then echo "  ok       $$tool"; \
	  else echo "  advisory $$tool not on PATH"; fi; \
	done

review-plan-fact-check-by-codex:	## Pre-pass: fact-check active plan sections against declared fact roots (PLAN_FILE=...)
	@test -n "$(PLAN_FILE)" || \
	  { echo "Usage: make review-plan-fact-check-by-codex PLAN_FILE=docs/plans/<file>.md"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	@command -v codex >/dev/null 2>&1 || \
	  { echo "codex CLI not found. Install + log in first (see CONTRIBUTING.md)."; exit 1; }
	@$(CURDIR)/scripts/extract-plan-facts.py "$(PLAN_FILE)" > "$(FACT_CHECK_FACTS_OUT)"
	@$(CURDIR)/scripts/verify-plan-facts.py "$(FACT_CHECK_FACTS_OUT)" "$(CURDIR)" > "$(FACT_CHECK_VERIFY_OUT)"
	@PROMPT="$$(PLAN_FILE="$(PLAN_FILE)" VERIFICATION_JSON_FILE="$(FACT_CHECK_VERIFY_OUT)" $(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/prompts/fact-check-interpret.txt)" || exit $$?; \
	$(CURDIR)/scripts/run-with-clean-env.py -- \
	  codex exec \
	    -C "$(CURDIR)" \
	    --sandbox read-only \
	    --color never \
	    --output-last-message "$(PLAN_FACT_CHECK_OUT_CODEX)" \
	    "$$PROMPT"
	@echo "──────────────────────────────────────────"
	@echo "Fact-check report written to: $(PLAN_FACT_CHECK_OUT_CODEX)"
	@echo "──────────────────────────────────────────"
	@cat "$(PLAN_FACT_CHECK_OUT_CODEX)"

review-plan-fact-check-by-claude:	## Pre-pass: fact-check active plan sections against declared fact roots (PLAN_FILE=...)
	@test -n "$(PLAN_FILE)" || \
	  { echo "Usage: make review-plan-fact-check-by-claude PLAN_FILE=docs/plans/<file>.md"; exit 1; }
	@test -f "$(PLAN_FILE)" || { echo "Plan file not found: $(PLAN_FILE)"; exit 1; }
	@command -v claude >/dev/null 2>&1 || \
	  { echo "claude CLI not found. Install + log in first (see CONTRIBUTING.md)."; exit 1; }
	@$(CURDIR)/scripts/extract-plan-facts.py "$(PLAN_FILE)" > "$(FACT_CHECK_FACTS_OUT)"
	@$(CURDIR)/scripts/verify-plan-facts.py "$(FACT_CHECK_FACTS_OUT)" "$(CURDIR)" > "$(FACT_CHECK_VERIFY_OUT)"
	@PROMPT="$$(PLAN_FILE="$(PLAN_FILE)" VERIFICATION_JSON_FILE="$(FACT_CHECK_VERIFY_OUT)" $(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/prompts/fact-check-interpret.txt)" || exit $$?; \
	$(CURDIR)/scripts/run-with-clean-env.py -- \
	  claude \
	    --print \
	    --add-dir "$(CURDIR)" \
	    --output-format text \
	    "$$PROMPT" \
	  > "$(PLAN_FACT_CHECK_OUT_CLAUDE)"
	@echo "──────────────────────────────────────────"
	@echo "Fact-check report written to: $(PLAN_FACT_CHECK_OUT_CLAUDE)"
	@echo "──────────────────────────────────────────"
	@cat "$(PLAN_FACT_CHECK_OUT_CLAUDE)"

preflight-review-tooling:	## verify claude+codex CLIs work with the flag shape review targets expect
	@command -v codex >/dev/null 2>&1 || { echo "codex CLI not found"; exit 1; }
	@command -v claude >/dev/null 2>&1 || { echo "claude CLI not found"; exit 1; }
	@$(CURDIR)/scripts/run-with-clean-env.py -- \
	    codex exec -C "$(CURDIR)" --sandbox read-only --color never \
	    --output-last-message /tmp/preflight-codex.txt \
	    "Reply with the single word: ok" >/dev/null 2>&1 \
	    || { echo "codex flag smoke failed — see merged plan risk table"; exit 1; }
	@$(CURDIR)/scripts/run-with-clean-env.py -- \
	    claude --print --add-dir "$(CURDIR)" \
	    --output-format text \
	    "Reply with the single word: ok" >/dev/null 2>&1 \
	    || { echo "claude flag smoke failed — see merged plan risk table"; exit 1; }
	@codex --version | grep -q "0\.130\." \
	    || echo "WARN: tested baseline is codex-cli 0.130.0; you have $$(codex --version)"
	@claude --version | grep -q "2\.1\.139" \
	    || echo "WARN: tested baseline is Claude Code 2.1.139; you have $$(claude --version)"
	@echo "✓ preflight ok"
# SELFTEST-OVERLAP-END: shared/Makefile.review.tmpl
