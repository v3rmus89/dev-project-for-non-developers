#!/usr/bin/env python3
"""Live A/B SCREEN runner for the continue-thread hypothesis.

OPERATOR-RUN, NOT in `make check` (it makes live, paid `codex` calls -- like
`scripts/verify-v13-5.py`). The pure metric + argv logic it uses lives in
`scripts/ab_replay_lib.py` and IS unit-tested in `make check`.

What it does (see `docs/plans/2026-06-01-continue-thread-ab-measurement.md`):
reviews ONE real checked-in plan at iterations 1/2/3 twice -- once FRESH (a new
codex session per iteration) and once CONTINUE (seed iter 1, then resume iters
2/3 on one thread) -- and reports the uncached-input ratio that screens whether
resume caches enough to be worth a full-rigor measurement.

The screen NEVER flips the default. Verdict in {stay-fresh,
escalate-to-full-rigor, inconclusive} -- computed by `lib.screen_verdict` after
the operator supplies the manual quality + warmup judgement.

Safety / rigor controls baked in:
- **Pre-registered run order**: FRESH block first (3 calls), then CONTINUE
  (seed + 2 resume). Fresh-first warms the server prefix cache for continue,
  biasing TOWARD continue looking cheap -- so a stay-fresh verdict is robust
  (iter-3 FN3).
- **Pinned read-only argv** for every call, via `lib.build_fresh_call` /
  `lib.build_resume_call` (both wrap codex in `run-with-clean-env.py` + close
  stdin) (iter-3 FN2).
- **Raw JSONL -> a /tmp dir ONLY, never committed** (iter-2 FN2). Only
  aggregate numbers + per-call uncached are printed / written to the summary.
- **Dry-run by default**: prints the exact planned argv and exits. `--execute`
  is required to make live calls (a safety gate on top of the V-4 preflight).
- **Wall-clock cap** (default 30 min) across all calls.

Usage:
    python3.12 scripts/ab-replay.py [--plan PATH] [--repo ABSPATH] [--out-dir DIR]
                                    [--max-seconds N] [--execute]

Run with python3.12 -- the script needs >= 3.11 for `datetime.UTC`; the bare
`./scripts/ab-replay.py` shebang may pick a system python 3.9 on macOS.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ab_replay_lib as lib  # noqa: E402

EXTRACTOR = SCRIPTS_DIR / "extract-codex-session-id.py"
DEFAULT_PLAN = "docs/plans/2026-05-31-skill-pr2-bucket-a-skill-wrapper.md"
ITERATIONS = (1, 2, 3)
DEFAULT_MAX_SECONDS = 1800  # 30 min total wall-clock cap across all calls
PER_CALL_MAX_SECONDS = 900  # a single call may not run away past 15 min (plan:157)

# The prompt is the SHARED prompts/plan-review.txt -- the same file the
# Makefile recipes render via scripts/render-review-prompt.py. ab-replay
# supplies every token the file carries ({PLAN_FILE}, {ITERATION}, {KEY});
# `lib.build_plan_review_prompt` computes {KEY} with the Makefile's formula.


def build_prompt(repo_abspath: str, plan_path: str, iteration: int) -> str:
    return lib.build_plan_review_prompt(repo_abspath, plan_path, iteration)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def codex_version() -> str:
    try:
        out = subprocess.run(
            ["codex", "--version"], capture_output=True, text=True, stdin=subprocess.DEVNULL
        )
        return (out.stdout or out.stderr).strip()
    except FileNotFoundError:
        return "codex: NOT FOUND on PATH"


def run_call(call: lib.CodexCall, out_path: Path, timeout: float) -> dict:
    """Execute one pinned codex call; raw stream -> out_path (/tmp). Returns a
    record with timing + the parsed usages (NO raw text retained in the record)."""
    if not lib.is_read_only_argv(call.argv):
        raise SystemExit(f"REFUSING non-read-only argv: {call.argv!r}")
    started = _utcnow()
    t0 = time.monotonic()
    try:
        # cwd=SKILL_ROOT so the relative wrapper (scripts/run-with-clean-env.py)
        # resolves no matter where the operator launches the runner from.
        result = subprocess.run(call.argv, timeout=timeout, cwd=str(SKILL_ROOT), **call.run_kwargs)
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"call exceeded its time budget ({timeout:.0f}s); aborting -- see {out_path}"
        ) from None
    elapsed = time.monotonic() - t0
    out_path.write_text(result.stdout or "", encoding="utf-8")
    if result.returncode != 0:
        sys.stderr.write(result.stderr or "")
        raise SystemExit(f"codex call failed (rc={result.returncode}); see {out_path}")
    return {
        "started_utc": started,
        "elapsed_s": round(elapsed, 1),
        "usages": lib.parse_turn_usages(result.stdout or ""),
        "jsonl": str(out_path),
    }


def _print_planned(repo: str, plan: str) -> None:
    print("DRY RUN -- planned calls (pre-registered order: FRESH x3, then CONTINUE):\n")
    print("  [fresh/seed argv]")
    print(
        "   ",
        " ".join(lib.build_fresh_call(repo, build_prompt(repo, plan, 1)).argv[:-1]),
        "<PROMPT>",
    )
    print("  [resume argv]")
    print(
        "   ",
        " ".join(lib.build_resume_call("<THREAD_ID>", build_prompt(repo, plan, 2)).argv[:-1]),
        "<PROMPT>",
    )
    print("\n  stdin: /dev/null on every call; raw JSONL -> the --out-dir (/tmp), never committed.")
    print("  Re-run with --execute to make the live calls.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Continue-thread A/B SCREEN (operator-run).")
    parser.add_argument("--plan", default=DEFAULT_PLAN, help="checked-in plan to replay")
    parser.add_argument("--repo", default=str(SKILL_ROOT), help="repo abspath (codex -C)")
    parser.add_argument("--out-dir", default=None, help="dir for raw JSONL (default: a /tmp dir)")
    parser.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS)
    parser.add_argument("--execute", action="store_true", help="make live paid calls")
    args = parser.parse_args(argv)

    if not args.execute:
        _print_planned(args.repo, args.plan)
        return 0

    # Codex Tier-2 C2: fail BEFORE any paid call if --plan is a typo / stale path.
    # codex resolves the plan relative to the repo (-C), so check it there. A
    # missing path would otherwise spend all 6 calls reviewing nothing.
    plan_full = Path(args.plan) if Path(args.plan).is_absolute() else Path(args.repo) / args.plan
    if not plan_full.is_file():
        raise SystemExit(
            f"--plan not found: {plan_full} -- refusing to spend paid calls on a missing/typo'd plan"
        )

    # Codex Tier-2 C1: the raw JSONL must never land in the repo (the plan's
    # "never committed" contract). Enforce repo-exclusion by construction rather
    # than trusting the operator's --out-dir. (Repo-exclusion, not literal /tmp:
    # tempfile.gettempdir() is /var/folders/... on macOS, so a literal-/tmp check
    # would wrongly reject the default temp dir there.)
    out_dir = (
        Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="ab-screen-"))
    ).resolve()
    # Exclude BOTH the skill repo AND the reviewed checkout (--repo) -- raw JSONL
    # must never land in either (the plan's never-committed contract). They are the
    # same by default but differ when --repo replays a different checkout (codex C1
    # re-review). resolve() so a symlinked/relative --repo is compared canonically.
    for root in {SKILL_ROOT.resolve(), Path(args.repo).resolve()}:
        if out_dir == root or root in out_dir.parents:
            raise SystemExit(
                f"--out-dir must be OUTSIDE the repo (raw JSONL is never committed); "
                f"got {out_dir} inside {root}"
            )
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"codex version: {codex_version()}")
    print(f"raw JSONL dir (NOT committed): {out_dir}\n")

    deadline = time.monotonic() + args.max_seconds

    def remaining() -> float:
        rem = deadline - time.monotonic()
        if rem <= 0:
            raise SystemExit("wall-clock cap exceeded -- aborting before the next call")
        return rem

    def call_timeout() -> float:
        # Bound BOTH the total budget (remaining()) AND a single runaway call
        # (PER_CALL_MAX_SECONDS) -- the plan's cap is "total > 30 min OR a single
        # call runs away" (plan:157).
        return min(remaining(), PER_CALL_MAX_SECONDS)

    # --- FRESH block first (pre-registered order; warms cache for continue) ---
    fresh_records = []
    for it in ITERATIONS:
        call = lib.build_fresh_call(args.repo, build_prompt(args.repo, args.plan, it))
        rec = run_call(call, out_dir / f"fresh-iter{it}.jsonl", call_timeout())
        fresh_records.append(rec)
        print(f"fresh iter{it}: {rec['elapsed_s']}s, uncached={_uncached(rec)}")

    # --- CONTINUE block: seed iter 1, resume iters 2/3 on one thread ---
    seed_call = lib.build_fresh_call(args.repo, build_prompt(args.repo, args.plan, 1))
    seed_jsonl = out_dir / "continue-seed-iter1.jsonl"
    seed_rec = run_call(seed_call, seed_jsonl, call_timeout())
    tid = _extract_thread_id(seed_jsonl)
    print(
        f"continue seed iter1: {seed_rec['elapsed_s']}s, uncached={_uncached(seed_rec)}, tid={tid}"
    )
    continue_records = [seed_rec]
    for it in (2, 3):
        call = lib.build_resume_call(tid, build_prompt(args.repo, args.plan, it))
        rec = run_call(call, out_dir / f"continue-resume-iter{it}.jsonl", call_timeout())
        continue_records.append(rec)
        print(f"continue resume iter{it}: {rec['elapsed_s']}s, uncached={_uncached(rec)}")

    _report(fresh_records, continue_records, out_dir)
    return 0


def _uncached(rec: dict) -> int:
    return sum(lib.uncached_input(u) for u in rec["usages"])


def _extract_thread_id(seed_jsonl: Path) -> str:
    out = subprocess.run(
        [sys.executable, str(EXTRACTOR), str(seed_jsonl)],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    tid = out.stdout.strip()
    if not tid:
        raise SystemExit(f"could not extract thread id from {seed_jsonl}: {out.stderr.strip()}")
    return tid


def _report(fresh_records: list, continue_records: list, out_dir: Path) -> None:
    fresh_usages = [u for r in fresh_records for u in r["usages"]]
    cont_usages = [u for r in continue_records for u in r["usages"]]
    fresh_agg = lib.aggregate(fresh_usages)
    cont_agg = lib.aggregate(cont_usages)
    ratio = lib.uncached_input_ratio(cont_usages, fresh_usages)
    cost_ratio = lib.est_cost_ratio(cont_usages, fresh_usages)

    print("\n=== AGGREGATES (paste into the design note; NO raw JSONL) ===")
    for name, agg in (("fresh", fresh_agg), ("continue", cont_agg)):
        print(
            f"{name:9s} input={agg['total_input']} cached={agg['total_cached_input']} "
            f"uncached={agg['total_uncached_input']} output={agg['total_output']} "
            f"cache_share={agg['cache_share']:.3f} per_call_uncached={agg['per_call_uncached']}"
        )
    print(f"\nuncached_input_ratio (continue/fresh): {ratio}")
    print(f"est_cost_ratio (rough, PLACEHOLDER prices -- set real rates): {cost_ratio}")
    print(f"\nscreen bar = {lib.SCREEN_BAR}: ratio>{lib.SCREEN_BAR} -> stay-fresh;")
    print("  ratio<=bar + quality-equivalent + not-warmup-confounded -> escalate-to-full-rigor;")
    print("  else -> inconclusive. (Operator supplies quality + warmup judgement.)")
    print("\nWARMUP CHECK: if fresh's OWN per_call_uncached 2/3 are already much lower than")
    print("  call 1, the server prefix cache warmed within the fresh block -> confounded.")
    print(f"\nraw JSONL (NOT committed): {out_dir}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
