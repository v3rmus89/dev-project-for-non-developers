#!/usr/bin/env python3
"""Pure helpers for the continue-thread A/B SCREEN (see
`docs/plans/archive/2026-06-01-continue-thread-ab-measurement.md`).

Two responsibilities, both pure + unit-tested in `make check` (the live runner
`scripts/ab-replay.py` is operator-run and NOT in `make check`):

1. **Metric math** over `codex exec --json` streams. The screen's primary metric
   is the *uncached-input ratio* `sum(uncached, continue) / sum(uncached, fresh)`,
   where `uncached = input_tokens - cached_input_tokens`. `cached_input_tokens` is
   a SUBSET of `input_tokens`, so cached tokens are never counted as a token-count
   "saving" -- caching is a price discount, surfaced via `est_cost`,
   not a reduction in input.

2. **Safe-argv builders** for the codex calls. Resume defaults to workspace-WRITE
   unless `-c sandbox_mode=read-only` is passed, so the screen pins read-only argv
   for every call. All calls are wrapped in
   `scripts/run-with-clean-env.py` -- the same prefix-aware env scrubber the
   Makefile's review targets use -- and run with stdin closed (`codex --json`
   hangs on an open stdin; memory `codex-json-resume-behavior`).

This module is import-safe (underscore name); the live runner imports it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
from collections import namedtuple
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _SCRIPTS_DIR.parent

# ── Shared plan-review prompt (one source for ALL consumers) ──────────────────

# The SAME file the Makefile's review-plan-by-{codex,claude} recipes render via
# scripts/render-review-prompt.py -- there is no ab-replay-private prompt copy.
PLAN_REVIEW_PROMPT_FILE = _SKILL_ROOT / "prompts" / "plan-review.txt"

# Import the substitution helper's known-token ruleset from its working copy
# (the file name is not a valid module name, hence the spec dance). One
# ruleset for every consumer: registry-only substitution, never str.format --
# the prompt carries literal JSON-fence braces that must pass through raw.
_spec = importlib.util.spec_from_file_location(
    "_render_review_prompt", _SCRIPTS_DIR / "render-review-prompt.py"
)
_render_review_prompt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_render_review_prompt)


def compute_plan_review_key(repo_abspath: str, plan_path: str) -> str:
    """The Makefile's KEY for a (repo, plan) pair -- must stay formula-identical.

    Mirrors the `KEY = $(shell python3 -c ...)` definition in the Makefile
    review block: sha256 of `realpath(repo) + ':' + realpath(plan)`, first
    12 hex chars. `plan_path` must already be resolvable from the current
    process (pass an absolute or repo-joined path; the Makefile's realpath
    runs with make's cwd == the repo).
    """
    k = os.path.realpath(str(repo_abspath)) + ":" + os.path.realpath(str(plan_path))
    return hashlib.sha256(k.encode()).hexdigest()[:12]


def build_plan_review_prompt(repo_abspath: str, plan: str, iteration: int) -> str:
    """Resolve prompts/plan-review.txt exactly as the Makefile recipes do.

    Supplies every registry token the shared file carries: {PLAN_FILE} is the
    plan path as given (codex resolves it against -C <repo>, mirroring make's
    repo cwd), {ITERATION} the iteration number, and {KEY} computed from the
    repo-joined plan path via `compute_plan_review_key`. The trailing newline
    is stripped to match what the recipes' command substitution produces.
    """
    plan_for_key = plan if os.path.isabs(plan) else os.path.join(repo_abspath, plan)
    values = {
        "PLAN_FILE": plan,
        "ITERATION": str(iteration),
        "KEY": compute_plan_review_key(repo_abspath, plan_for_key),
    }

    def _resolve(name: str) -> str:
        try:
            return values[name]
        except KeyError:
            raise _render_review_prompt.UnresolvedTokenError(
                name, f"ab-replay supplies no value for {{{name}}}"
            ) from None

    text = PLAN_REVIEW_PROMPT_FILE.read_text(encoding="utf-8")
    return _render_review_prompt.render_prompt(text, _resolve).rstrip("\n")


# ── Safe-argv builders ─────────────────────────────────────────────────────────

# The env scrubber every codex call is routed through, relative to the repo root.
CLEAN_ENV_WRAPPER = "scripts/run-with-clean-env.py"

# A built codex invocation: the argv list + the subprocess kwargs the runner must
# use. `run_kwargs["stdin"]` is DEVNULL because `codex --json` hangs on open stdin.
CodexCall = namedtuple("CodexCall", ["argv", "run_kwargs"])


def codex_run_kwargs() -> dict:
    """subprocess kwargs every codex call must use: stdin CLOSED + captured output.

    The `/tmp`-only JSONL is `result.stdout`; nothing is written to a repo path.
    """
    return {"stdin": subprocess.DEVNULL, "capture_output": True, "text": True}


def build_fresh_call(repo_abspath: str, prompt: str, wrapper: str = CLEAN_ENV_WRAPPER) -> CodexCall:
    """A fresh / seed codex review call (new session), pinned read-only.

    Mirrors [Makefile:206](../Makefile) (the continue-seed argv) with `--json` on
    so `turn.completed.usage` is captured. `-C <repo>` + `--sandbox read-only`
    bound it to the repo in read-only mode.
    """
    argv = [
        wrapper,
        "--",
        "codex",
        "exec",
        "--json",
        "-C",
        repo_abspath,
        "--sandbox",
        "read-only",
        "--color",
        "never",
        prompt,
    ]
    return CodexCall(argv=argv, run_kwargs=codex_run_kwargs())


def build_resume_call(thread_id: str, prompt: str, wrapper: str = CLEAN_ENV_WRAPPER) -> CodexCall:
    """A resume codex review call (continue the thread), pinned read-only.

    Mirrors [Makefile:191](../Makefile). Resume defaults to workspace-WRITE
    WITHOUT `-c sandbox_mode=read-only`, and it does NOT take `-C` / `--sandbox`
    (memory `codex-json-resume-behavior`) -- so read-only is pinned via `-c`.
    """
    argv = [
        wrapper,
        "--",
        "codex",
        "exec",
        "resume",
        thread_id,
        "-c",
        "sandbox_mode=read-only",
        "--json",
        prompt,
    ]
    return CodexCall(argv=argv, run_kwargs=codex_run_kwargs())


# Tokens that would (re-)enable writes; a resume/fresh argv must never carry them.
WRITE_ENABLING_TOKENS = (
    "workspace-write",
    "danger-full-access",
    "sandbox_mode=workspace-write",
    "sandbox_mode=danger-full-access",
    "--full-auto",
    "--dangerously-bypass-approvals-and-sandbox",
)


def is_read_only_argv(argv: list[str]) -> bool:
    """True iff `argv` carries a POSITIVE read-only pin and no known write-enabling token.

    The real safety guarantee is the positive pin (fresh: adjacent `--sandbox
    read-only`; resume: adjacent `-c sandbox_mode=read-only`) -- an argv with
    neither returns False. `WRITE_ENABLING_TOKENS` is a defense-in-depth denylist,
    NOT exhaustive: it cannot catch an unknown future write-enabling flag, so the
    positive pin is what the V-1 safety assertion ultimately rests on.
    """
    joined = " ".join(argv)
    if any(tok in joined for tok in WRITE_ENABLING_TOKENS):
        return False
    # Identify the codex subcommand by POSITION (the token after `exec`), not by
    # membership -- a fresh call whose PROMPT happened to equal "resume" must not
    # be misrouted into the resume branch and wrongly reported unsafe.
    exec_i = argv.index("exec") if "exec" in argv else -1
    is_resume = exec_i != -1 and exec_i + 1 < len(argv) and argv[exec_i + 1] == "resume"
    if is_resume:
        # Adjacent `-c sandbox_mode=read-only` pair.
        return any(
            argv[i] == "-c" and argv[i + 1] == "sandbox_mode=read-only"
            for i in range(len(argv) - 1)
        )
    # Fresh / seed: adjacent `--sandbox read-only` pair.
    return any(argv[i] == "--sandbox" and argv[i + 1] == "read-only" for i in range(len(argv) - 1))


# ── Metric math (uncached-input, not raw token count) ──────────────────────────


def parse_turn_usages(jsonl_text: str) -> list[dict]:
    """Every `turn.completed.usage` dict in a `codex exec --json` stream.

    Blank / non-JSON lines are skipped (a partial stream still yields the usages
    it contains). Non-dict `usage` values are ignored.
    """
    usages: list[dict] = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "turn.completed":
            usage = event.get("usage")
            if isinstance(usage, dict):
                usages.append(usage)
    return usages


def _int_field(usage: dict, key: str) -> int:
    """A usage field as a non-negative int; missing / None / non-int -> 0."""
    val = usage.get(key)
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return 0
    val = int(val)
    return val if val > 0 else 0


def cached_input(usage: dict) -> int:
    """`cached_input_tokens`, clamped to [0, input_tokens].

    Caching is a SUBSET of input; the clamp defends against malformed data that
    would otherwise let cached exceed input and turn `uncached` negative.
    """
    return min(_int_field(usage, "cached_input_tokens"), _int_field(usage, "input_tokens"))


def uncached_input(usage: dict) -> int:
    """`input_tokens - cached_input_tokens` (>= 0). The screen's per-call unit.

    Never negative: cached is clamped to a subset of input. Cached tokens are a
    price discount, surfaced via `est_cost`, NOT a token-count saving.
    """
    return _int_field(usage, "input_tokens") - cached_input(usage)


def aggregate(usages: list[dict]) -> dict:
    """Per-mode totals + cache share + the per-call uncached list (warmup check)."""
    total_input = sum(_int_field(u, "input_tokens") for u in usages)
    total_cached = sum(cached_input(u) for u in usages)
    total_uncached = sum(uncached_input(u) for u in usages)
    total_output = sum(_int_field(u, "output_tokens") for u in usages)
    return {
        "calls": len(usages),
        "total_input": total_input,
        "total_cached_input": total_cached,
        "total_uncached_input": total_uncached,
        "total_output": total_output,
        "cache_share": (total_cached / total_input) if total_input else 0.0,
        # Per-call uncached, in call order: the warmup-confound detector.
        "per_call_uncached": [uncached_input(u) for u in usages],
    }


def uncached_input_ratio(continue_usages: list[dict], fresh_usages: list[dict]) -> float | None:
    """`sum(uncached, continue) / sum(uncached, fresh)` -- the primary screen metric.

    Returns None when the fresh uncached total is 0 (ratio undefined) -> the
    caller treats None as inconclusive.
    """
    fresh_uncached = sum(uncached_input(u) for u in fresh_usages)
    if fresh_uncached == 0:
        return None
    cont_uncached = sum(uncached_input(u) for u in continue_usages)
    return cont_uncached / fresh_uncached


# Rough USD-per-1M-token PLACEHOLDER prices for codex 0.130 / gpt-5.5. These are
# NOT authoritative -- the plan labels est_cost a rough estimate (deviation 2).
# The operator MUST set real rates in the design note before reading est_cost as
# anything but illustrative; the test pins the MATH, not these numbers.
PLACEHOLDER_PRICES_USD_PER_MTOK = {
    "uncached_input": 1.25,
    "cached_input": 0.125,
    "output": 10.0,
}


def est_cost(usage: dict, prices: dict = PLACEHOLDER_PRICES_USD_PER_MTOK) -> float:
    """Rough USD cost estimate for one call: uncached + cached + output, priced
    separately (cached is discounted). LABELLED ESTIMATE -- see prices note."""
    unc = uncached_input(usage)
    cached = cached_input(usage)
    out = _int_field(usage, "output_tokens")
    return (
        unc * prices["uncached_input"] + cached * prices["cached_input"] + out * prices["output"]
    ) / 1_000_000


def est_cost_ratio(
    continue_usages: list[dict],
    fresh_usages: list[dict],
    prices: dict = PLACEHOLDER_PRICES_USD_PER_MTOK,
) -> float | None:
    """`sum(est_cost, continue) / sum(est_cost, fresh)`; None if fresh cost is 0."""
    fresh_cost = sum(est_cost(u, prices) for u in fresh_usages)
    if fresh_cost == 0:
        return None
    cont_cost = sum(est_cost(u, prices) for u in continue_usages)
    return cont_cost / fresh_cost


# ── Screen verdict (NEVER flips) ───────────────────────────────────────────────

# The screen's pre-registered bar. Verdicts are {stay-fresh, escalate-to-full-rigor,
# inconclusive} -- there is NO flip verdict: a best-case + N=3 + order-biased screen
# cannot justify flipping the default; a flip needs the full-rigor BACKLOG measurement.
SCREEN_BAR = 0.90


def screen_verdict(
    ratio: float | None,
    quality_equivalent: bool,
    warmup_confounded: bool,
    bar: float = SCREEN_BAR,
) -> str:
    """Map the measured ratio + qualitative flags to a screen verdict.

    Decision order (stay-fresh takes precedence by design):
      - ratio is None (undefined) -> inconclusive.
      - ratio > bar -> stay-fresh. No payoff even in the best case; and because the
        pre-registered run order is fresh-FIRST, the server prefix cache was warmed
        for continue, biasing TOWARD continue looking cheap. Continue still didn't
        win, so stay-fresh is robust to the order confound -- quality is moot
        (we're not adopting).
      - ratio <= bar (continue looks cheaper): the apparent payoff must survive the
        confound + quality checks before it can even motivate escalation:
          - warmup_confounded -> inconclusive (payoff may be the order artifact).
          - not quality_equivalent -> inconclusive (continue may have gone lazy).
          - else -> escalate-to-full-rigor (promising; a flip still needs full rigor).
    """
    if ratio is None:
        return "inconclusive"
    if ratio > bar:
        return "stay-fresh"
    if warmup_confounded:
        return "inconclusive"
    if not quality_equivalent:
        return "inconclusive"
    return "escalate-to-full-rigor"
