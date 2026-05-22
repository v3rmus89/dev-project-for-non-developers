"""Smart stack suggestion — PR #9.

`suggest_stack(brief)` maps a plain-English project description to a *language*
suggestion. It is a deterministic keyword **signal scorer** (no LLM, no network
— per the plan's AD-1, this keeps the "pure offline CLI, no `.env`" invariant
and stays fully CI-testable).

Mechanism (plan Bucket A):
  1. normalise the brief — lowercase, every run of non-alphanumerics (hyphens
     included) becomes a single space, wrapped in spaces;
  2. match each signal as a space-bounded substring (so `"api"` does not fire
     inside `"rapid"`, and multi-word phrases like `"machine learning"` work);
  3. score each language `3 * n_strong + n_weak` — a strong signal outranks
     two weak ones;
  4. a language is *eligible* only with `n_strong >= 1` or `n_weak >= 2` (a
     single broad word is not enough);
  5. the unique-max-score eligible language wins; a tie or no eligible
     language returns `None` (low confidence — the caller falls back to the
     plain menu).

The suggestion is language-only (a plain-English brief carries no uv-vs-pip
signal). It only ever pre-fills a menu *default*; the user still confirms.

This module is 3.12 (like `intake.py` / `cli.py`); it is never loaded by the
3.6-compatible `bootstrap.py` shim.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from bootstrap_lib import _flags


class StackSuggestion(NamedTuple):
    """A language suggestion + a fixed human-readable rationale.

    No `package_manager` field — the suggestion is language-only (plan AD-3).
    """

    language: str
    rationale: str


# Per-language signal sets — `strong` signals are highly language-specific
# (one match clears the eligibility floor); `weak` signals are broad (two are
# needed). All signals are hyphen-free: the brief is normalised with hyphens
# stripped, so a hyphenated brief ("single-page") still matches "single page".
#
# Sourcing (plan External-sources table): the nodejs/python web + back-end
# groupings are inspired by StackShare "Awesome Stacks" (CC0); the go set is
# repo-local product judgment — Go's commonly-understood strengths (CLI
# tooling, services, systems work) — not transcribed from any one source.
#
# Extension rule (plan Bucket A, Tier-2 #2): a signal may be added only with
# an accompanying new Brief-acceptance-matrix row in tests/test_stack_suggest.py
# — the matrix stays the complete coverage gate.
_SIGNALS: dict[str, dict[str, frozenset[str]]] = {
    "python": {
        "strong": frozenset(
            {
                "scrape",
                "scraper",
                "scraping",
                "machine learning",
                "data pipeline",
                "rest api",
                "etl",
            }
        ),
        "weak": frozenset(
            {
                "data",
                "script",
                "api",
                "backend",
                "automation",
                "ai",
                "bot",
                "report",
                "spreadsheet",
            }
        ),
    },
    "nodejs": {
        "strong": frozenset(
            {
                "website",
                "websites",
                "web site",
                "web app",
                "react",
                "single page",
                "landing page",
                "frontend",
                "front end",
            }
        ),
        "weak": frozenset({"ui", "dashboard", "browser"}),
    },
    "go": {
        "strong": frozenset(
            {
                "command line tool",
                "command line",
                "microservice",
                "daemon",
                "high performance",
            }
        ),
        "weak": frozenset({"cli", "tool", "systems", "concurrent"}),
    },
}

# Fixed, per-language rationale strings — reused verbatim in the intake's
# "lead with the recommendation" line. Never an echo of the user's words
# (deterministic + privacy-clean: the brief is never reflected back).
_RATIONALES: dict[str, str] = {
    "python": "data, automation, and API projects are Python's usual home",
    "nodejs": "websites and web apps are Node's home turf",
    "go": "command-line tools and services are Go's sweet spot",
}

# Single-source-of-truth guard (plan Tier-2 / Codex iter-3 #3): the signal and
# rationale tables must be keyed exactly on `_flags.LANGUAGES`. A typo or a
# future language addition that misses one of these tables fails loud at
# import — not silently downstream when `_ask_menu` gets an unknown default.
assert set(_SIGNALS) == set(_RATIONALES) == set(_flags.LANGUAGES), (
    "stack_suggest signal/rationale tables must be keyed on _flags.LANGUAGES"
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalise(brief: str) -> str:
    """Lowercase `brief`, collapse every non-alphanumeric run to one space, and
    wrap in single spaces so signals can be matched as space-bounded
    substrings."""
    return " " + _NON_ALNUM.sub(" ", brief.lower()).strip() + " "


def suggest_stack(brief: str) -> StackSuggestion | None:
    """Suggest a language for `brief`, or `None` when confidence is low.

    `None` is returned when no language is eligible (no language clears the
    `n_strong >= 1` / `n_weak >= 2` floor) or when two eligible languages tie
    for the maximum score. The caller treats `None` as "show the plain menu".
    """
    norm = _normalise(brief)

    best_lang: str | None = None
    best_score = 0
    tied = False

    for language in _flags.LANGUAGES:
        signals = _SIGNALS[language]
        n_strong = sum(1 for s in signals["strong"] if f" {s} " in norm)
        n_weak = sum(1 for s in signals["weak"] if f" {s} " in norm)

        # Eligibility floor: a single broad (weak) signal is not enough.
        if n_strong < 1 and n_weak < 2:
            continue

        score = 3 * n_strong + n_weak
        if score > best_score:
            best_score, best_lang, tied = score, language, False
        elif score == best_score:
            tied = True

    if best_lang is None or tied:
        return None
    return StackSuggestion(language=best_lang, rationale=_RATIONALES[best_lang])


__all__ = ["StackSuggestion", "suggest_stack"]
