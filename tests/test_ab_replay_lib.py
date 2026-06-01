"""V-1 unit tests for scripts/ab_replay_lib.py (the continue-thread A/B SCREEN).

Two halves, both pure (zero live codex calls):
  (i)  metric math -- uncached-input, ratio, est_cost, the cached-is-not-a-saving
       invariant, and the missing/None/bad-field guards (iter-1 FN1).
  (ii) safe-argv builders -- fresh/seed and resume argv carry the read-only pins
       and never a write-enabling token; stdin is closed (iter-3 FN2). Mirrors the
       argv-assertion style of tests/test_makefile_review_targets.py, but against
       the pure builders (no subprocess shim needed -- the builders ARE the boundary).

The screen NEVER flips: screen_verdict returns only {stay-fresh,
escalate-to-full-rigor, inconclusive} (iter-3 FN1).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ab_replay_lib as lib  # noqa: E402


def _turn(input_tokens, cached, output=0):
    return {
        "type": "turn.completed",
        "usage": {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "output_tokens": output,
            "total_tokens": input_tokens + output,
        },
    }


def _stream(*turns):
    import json

    return "\n".join(json.dumps(t) for t in turns) + "\n"


# ── (i) metric math ────────────────────────────────────────────────────────────


def test_parse_turn_usages_extracts_only_completed_usage():
    text = _stream(
        {"type": "thread.started", "thread_id": "x"},
        {"type": "turn.started"},
        _turn(1000, 400, 10),
    )
    usages = lib.parse_turn_usages(text)
    assert len(usages) == 1
    assert usages[0]["input_tokens"] == 1000


def test_parse_skips_blank_and_garbage_lines():
    text = "\n\nnot json\n" + _stream(_turn(100, 0))
    usages = lib.parse_turn_usages(text)
    assert len(usages) == 1


def test_uncached_input_is_input_minus_cached():
    assert lib.uncached_input({"input_tokens": 1000, "cached_input_tokens": 400}) == 600


def test_cached_is_never_counted_as_a_token_saving():
    """cached is a SUBSET of input -> uncached + cached == input, always.
    Cached can never make `uncached` smaller than (input - input) == 0."""
    usage = {"input_tokens": 1000, "cached_input_tokens": 999}
    assert lib.uncached_input(usage) + lib.cached_input(usage) == usage["input_tokens"]
    assert lib.uncached_input(usage) == 1


def test_cached_clamped_to_input_never_negative_uncached():
    # Malformed: cached > input. Clamp -> uncached == 0, not negative.
    usage = {"input_tokens": 500, "cached_input_tokens": 9999}
    assert lib.cached_input(usage) == 500
    assert lib.uncached_input(usage) == 0


def test_missing_and_none_fields_guard_to_zero():
    assert lib.uncached_input({}) == 0
    assert lib.uncached_input({"input_tokens": None, "cached_input_tokens": None}) == 0
    assert lib.uncached_input({"input_tokens": 300}) == 300  # cached missing -> 0
    # bool is not a token count
    assert lib.uncached_input({"input_tokens": True, "cached_input_tokens": True}) == 0


def test_aggregate_totals_and_cache_share_and_per_call():
    usages = [
        {"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 10},
        {"input_tokens": 1000, "cached_input_tokens": 800, "output_tokens": 5},
    ]
    agg = lib.aggregate(usages)
    assert agg["calls"] == 2
    assert agg["total_input"] == 2000
    assert agg["total_cached_input"] == 800
    assert agg["total_uncached_input"] == 1200
    assert agg["total_output"] == 15
    assert agg["cache_share"] == 800 / 2000
    assert agg["per_call_uncached"] == [1000, 200]


def test_aggregate_empty_is_safe():
    agg = lib.aggregate([])
    assert agg["calls"] == 0
    assert agg["cache_share"] == 0.0
    assert agg["per_call_uncached"] == []


def test_uncached_input_ratio_basic():
    fresh = [{"input_tokens": 1000, "cached_input_tokens": 0}] * 3  # 3000 uncached
    cont = [
        {"input_tokens": 1000, "cached_input_tokens": 0},  # 1000
        {"input_tokens": 1000, "cached_input_tokens": 800},  # 200
        {"input_tokens": 1000, "cached_input_tokens": 800},  # 200
    ]  # 1400 uncached
    assert lib.uncached_input_ratio(cont, fresh) == 1400 / 3000


def test_uncached_input_ratio_none_when_fresh_zero():
    assert lib.uncached_input_ratio([{"input_tokens": 100, "cached_input_tokens": 0}], []) is None
    assert lib.uncached_input_ratio([], [{"input_tokens": 0, "cached_input_tokens": 0}]) is None


def test_est_cost_prices_components_separately():
    # 1000 uncached @1.25 + 0 cached + 0 output = 1250 / 1e6
    usage = {"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 0}
    assert lib.est_cost(usage) == 1000 * 1.25 / 1_000_000
    # cached is discounted, not free
    usage2 = {"input_tokens": 1000, "cached_input_tokens": 1000, "output_tokens": 0}
    assert lib.est_cost(usage2) == 1000 * 0.125 / 1_000_000


def test_est_cost_ratio_none_when_fresh_zero():
    assert lib.est_cost_ratio([{"input_tokens": 5, "cached_input_tokens": 0}], []) is None


# ── screen verdict (NEVER flips) ─────────────────────────────────────────────────


def test_screen_verdict_no_payoff_is_stay_fresh():
    # ratio > bar: continue isn't cheaper even in the best case.
    assert (
        lib.screen_verdict(0.95, quality_equivalent=True, warmup_confounded=False) == "stay-fresh"
    )


def test_screen_verdict_stay_fresh_robust_to_confound_and_quality():
    # ratio > bar wins regardless of confound/quality -- we are not adopting.
    assert (
        lib.screen_verdict(1.10, quality_equivalent=False, warmup_confounded=True) == "stay-fresh"
    )


def test_screen_verdict_payoff_clean_is_escalate_not_flip():
    v = lib.screen_verdict(0.70, quality_equivalent=True, warmup_confounded=False)
    assert v == "escalate-to-full-rigor"


def test_screen_verdict_payoff_but_confounded_is_inconclusive():
    assert (
        lib.screen_verdict(0.70, quality_equivalent=True, warmup_confounded=True) == "inconclusive"
    )


def test_screen_verdict_payoff_but_quality_degraded_is_inconclusive():
    assert (
        lib.screen_verdict(0.70, quality_equivalent=False, warmup_confounded=False)
        == "inconclusive"
    )


def test_screen_verdict_none_ratio_is_inconclusive():
    assert (
        lib.screen_verdict(None, quality_equivalent=True, warmup_confounded=False) == "inconclusive"
    )


def test_screen_verdict_never_returns_flip():
    for ratio in (None, 0.0, 0.5, 0.90, 0.91, 1.0, 2.0):
        for q in (True, False):
            for w in (True, False):
                assert lib.screen_verdict(ratio, q, w) in {
                    "stay-fresh",
                    "escalate-to-full-rigor",
                    "inconclusive",
                }


# ── (ii) safe-argv builders (iter-3 FN2) ─────────────────────────────────────────


def test_fresh_call_pins_read_only_repo_and_json():
    call = lib.build_fresh_call("/abs/repo", "REVIEW PROMPT")
    argv = call.argv
    assert argv[0] == lib.CLEAN_ENV_WRAPPER
    assert "--" in argv and argv[argv.index("--") + 1] == "codex"
    assert "exec" in argv
    assert "--json" in argv
    # -C <repo> adjacency
    assert argv[argv.index("-C") + 1] == "/abs/repo"
    # --sandbox read-only adjacency
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--color" in argv and argv[argv.index("--color") + 1] == "never"
    assert argv[-1] == "REVIEW PROMPT"
    assert lib.is_read_only_argv(argv)


def test_resume_call_pins_read_only_via_config_no_sandbox_flag():
    call = lib.build_resume_call("00000000-0000-7000-8000-000000000001", "REVIEW PROMPT")
    argv = call.argv
    assert argv[0] == lib.CLEAN_ENV_WRAPPER
    assert "resume" in argv
    assert argv[argv.index("resume") + 1] == "00000000-0000-7000-8000-000000000001"
    # read-only is pinned via `-c sandbox_mode=read-only` (resume ignores -C/--sandbox)
    assert argv[argv.index("-c") + 1] == "sandbox_mode=read-only"
    assert "-C" not in argv
    assert "--sandbox" not in argv
    assert "--json" in argv
    assert argv[-1] == "REVIEW PROMPT"
    assert lib.is_read_only_argv(argv)


def test_both_calls_close_stdin():
    """codex --json hangs on open stdin -> every call runs with stdin DEVNULL."""
    for call in (
        lib.build_fresh_call("/r", "p"),
        lib.build_resume_call("tid", "p"),
    ):
        assert call.run_kwargs["stdin"] is subprocess.DEVNULL
        assert call.run_kwargs["capture_output"] is True


def test_is_read_only_argv_rejects_write_enabling_tokens():
    # A resume argv that somehow carried workspace-write must be rejected.
    bad = [
        "w",
        "--",
        "codex",
        "exec",
        "resume",
        "tid",
        "-c",
        "sandbox_mode=workspace-write",
        "--json",
        "p",
    ]
    assert not lib.is_read_only_argv(bad)
    bad2 = [*lib.build_fresh_call("/r", "p").argv, "--dangerously-bypass-approvals-and-sandbox"]
    assert not lib.is_read_only_argv(bad2)
    bad3 = ["w", "--", "codex", "exec", "--json", "-C", "/r", "--full-auto", "p"]
    assert not lib.is_read_only_argv(bad3)


def test_is_read_only_argv_resume_without_pin_is_rejected():
    # Resume WITHOUT `-c sandbox_mode=read-only` defaults to workspace-WRITE -> unsafe.
    unsafe = ["w", "--", "codex", "exec", "resume", "tid", "--json", "p"]
    assert not lib.is_read_only_argv(unsafe)


def test_is_read_only_argv_fresh_without_sandbox_pin_is_rejected():
    unsafe = ["w", "--", "codex", "exec", "--json", "-C", "/r", "p"]
    assert not lib.is_read_only_argv(unsafe)
