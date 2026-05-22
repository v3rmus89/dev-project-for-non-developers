"""Tests for `bootstrap_lib.stack_suggest` (PR #9).

The **Brief acceptance matrix v1** (from the plan) is the objective success
criterion — it is parameterized one-row-per-test below. The signal sets in
`stack_suggest.py` must satisfy every row.
"""

from __future__ import annotations

import pytest

from bootstrap_lib import _flags, stack_suggest
from bootstrap_lib.stack_suggest import StackSuggestion, suggest_stack

# ── Brief acceptance matrix v1 — fixed in docs/plans/2026-05-22-skill-pr9-… ──
# (brief, expected language or None). Must not be weakened without a plan
# amendment; may be extended (every added signal needs a row — Tier-2 #2).
_MATRIX: list[tuple[str, str | None]] = [
    ("A script to scrape competitor prices into a spreadsheet", "python"),
    ("An automation that emails me a daily sales report", "python"),
    ("A REST API for my mobile app's backend", "python"),
    ("A machine learning model to predict customer churn", "python"),
    ("A data pipeline that loads orders into a warehouse", "python"),
    ("A landing page for my bakery", "nodejs"),
    ("A React dashboard showing live orders", "nodejs"),
    ("A website where customers book appointments", "nodejs"),
    ("A single page web app for tracking tasks", "nodejs"),
    ("A command line tool to rename files in bulk", "go"),
    ("A high performance microservice for image resizing", "go"),
    ("A small daemon that watches a folder and syncs files", "go"),
    ("A customer dashboard", None),
    ("A tool for tracking shipments", None),
    ("A machine learning model with a React interface", None),
    ("Something to help my business grow", None),
    ("A rapid prototype of an idea", None),
    ("A machine learning dashboard in the browser", "python"),
]


@pytest.mark.parametrize("brief, expected", _MATRIX)
def test_brief_acceptance_matrix(brief: str, expected: str | None) -> None:
    """Every Brief acceptance matrix v1 row resolves to its expected outcome."""
    result = suggest_stack(brief)
    if expected is None:
        assert result is None, f"expected None for {brief!r}, got {result!r}"
    else:
        assert result is not None, f"expected {expected!r} for {brief!r}, got None"
        assert result.language == expected, (
            f"expected {expected!r} for {brief!r}, got {result.language!r}"
        )


def test_matrix_has_all_eighteen_rows() -> None:
    """Guard against an accidental matrix truncation (plan: 18 fixed rows)."""
    assert len(_MATRIX) == 18


# ── Targeted unit tests ─────────────────────────────────────────────────────


def test_multi_word_phrase_signal_fires() -> None:
    """A multi-word signal ('machine learning') matches as a phrase — the
    Codex iter-1 #2 bug was that unigram tokenising could never match it."""
    assert suggest_stack("a machine learning project").language == "python"


def test_no_false_hit_inside_a_longer_word() -> None:
    """Space-bounded matching: the `api` signal must NOT fire inside `rapid`."""
    assert suggest_stack("a rapid prototype") is None


def test_hyphenated_brief_matches_hyphen_free_signal() -> None:
    """A hyphenated brief normalises so it matches the hyphen-free signal."""
    assert suggest_stack("a single-page web-app").language == "nodejs"
    assert suggest_stack("a command-line tool").language == "go"


def test_eligibility_floor_one_weak_signal_is_not_enough() -> None:
    """A single broad (weak) signal does not clear the confidence floor."""
    assert suggest_stack("a dashboard") is None  # 1 weak nodejs signal


def test_eligibility_floor_one_strong_signal_is_enough() -> None:
    """A single strong signal does clear the floor."""
    result = suggest_stack("a daemon")
    assert result is not None and result.language == "go"


def test_eligibility_floor_two_weak_signals_are_enough() -> None:
    """Two distinct weak signals clear the floor even with no strong signal."""
    result = suggest_stack("an automation that writes a report")
    assert result is not None and result.language == "python"


def test_strong_signal_outranks_two_weak_signals() -> None:
    """`score = 3*n_strong + n_weak` — one strong (3) beats two weak (2)."""
    result = suggest_stack("a machine learning dashboard in the browser")
    assert result is not None and result.language == "python"


def test_tie_between_eligible_languages_returns_none() -> None:
    """Two eligible languages with an equal max score → no unique winner."""
    assert suggest_stack("a machine learning model with a React interface") is None


def test_tie_reset_when_a_later_language_uniquely_outranks() -> None:
    """A two-language tie is correctly *overridden* by a later language with a
    strictly-higher unique score — exercises the `tied = False` reset branch
    (Bucket A Tier-1 imp-2: without this, dropping the reset still passes the
    rest of the suite)."""
    # python: "machine learning" (1 strong → score 3); nodejs: "react" (1
    # strong → 3) — these two tie; go: "command line tool" + "command line"
    # (2 strong → 6) then uniquely outranks both.
    result = suggest_stack(
        "A machine learning model behind a React app, shipped as a command line tool"
    )
    assert result is not None and result.language == "go"


def test_empty_and_signal_free_briefs_return_none() -> None:
    assert suggest_stack("") is None
    assert suggest_stack("something to help my business grow") is None


def test_rationale_is_the_fixed_per_language_string() -> None:
    """The rationale is the fixed per-language string. (The end-to-end no-echo
    guarantee — the brief never reflected back — is Bucket C's intake canary
    test; this pins the language→rationale mapping + a light no-echo smoke.)"""
    result = suggest_stack("a machine learning data pipeline")
    assert result is not None
    assert isinstance(result, StackSuggestion)
    assert result.rationale == stack_suggest._RATIONALES["python"]
    # light no-echo smoke: a distinctive brief word is absent from the rationale
    assert "pipeline" not in result.rationale


def test_signal_and_rationale_tables_keyed_on_flags_languages() -> None:
    """`_flags.LANGUAGES` is the single source of truth for the language list;
    the signal + rationale tables must be keyed exactly on it (Tier-2 / Codex
    iter-3 #3). The module also asserts this at import — this pins it in CI."""
    assert set(stack_suggest._SIGNALS) == set(_flags.LANGUAGES)
    assert set(stack_suggest._RATIONALES) == set(_flags.LANGUAGES)
