"""Tests for `bootstrap_lib.cli._interactive_decide` and the per-file
allowed-actions matrix (PR #7 Bucket C / Scope #6).

stdin is injected via `io.StringIO` rather than PTY mock — closes Claude
iter-2 #8 + Codex iter-5 #1: heredoc/pipe stdin works portably across
macOS/Linux CI, PTY mocking does not.
"""

from __future__ import annotations

import io

import pytest

from bootstrap_lib.adopt import (
    AdoptionPlan,
    PlannedFileAnalysis,
    PolicyRecommendation,
    TargetMeta,
)
from bootstrap_lib.cli import (
    _AdoptionAbort,
    _allowed_actions_for,
    _interactive_decide,
)


def _meta(**overrides):
    defaults = dict(
        exists=True,
        size=42,
        sha256="abc",
        line_count=5,
        heading_count=None,
        has_dependency_groups=False,
        python_version_pin=None,
        ignored_by_git=None,
    )
    defaults.update(overrides)
    return TargetMeta(**defaults)


def _analysis(rel_path, *, policy, manual_review_needed, reason="test", confidence="medium"):
    return PlannedFileAnalysis(
        rel_path=rel_path,
        target_meta=_meta(),
        recommendation=PolicyRecommendation(
            policy=policy,
            reason=reason,
            confidence=confidence,
            manual_review_needed=manual_review_needed,
        ),
    )


def _plan(tmp_path, analyses):
    return AdoptionPlan(target_root=tmp_path, analyses=tuple(analyses))


def _decide(plan, planned_files, *, stdin_text="", non_interactive=False):
    stdin = io.StringIO(stdin_text)
    stdout = io.StringIO()
    new_plan = _interactive_decide(
        plan, planned_files, non_interactive=non_interactive, stdin=stdin, stdout=stdout
    )
    return new_plan, stdout.getvalue()


# ─── Per-file allowed-actions matrix (Scope #6 sub-rules a/b/c/d) ───


class TestAllowedActionsMatrix:
    def test_always_allowed_actions_present(self):
        actions = _allowed_actions_for("CLAUDE.md")
        # Per Scope #6 (a): r/s/d/?/q always available
        for a in ("r", "s", "d", "?", "q"):
            assert a in actions

    def test_write_new_always_available_for_manual_review_files(self):
        """Scope #6 (b): [n] (WRITE_NEW) available for any manual-review file."""
        for path in ("CLAUDE.md", "pyproject.toml", "Makefile", "AGENTS.md"):
            assert "n" in _allowed_actions_for(path)

    def test_append_merge_only_for_gitignore(self):
        """Scope #6 (c): [a] (APPEND_MERGE) ONLY available for .gitignore."""
        assert "a" in _allowed_actions_for(".gitignore")
        for path in ("CLAUDE.md", "pyproject.toml", "Makefile", "AGENTS.md"):
            assert "a" not in _allowed_actions_for(path), (
                f"[a] must not be offered for {path}; APPEND_MERGE is .gitignore-only"
            )

    def test_overwrite_always_in_matrix(self):
        """Scope #6 (d): [o] is always in the matrix (gated by typed confirmation)."""
        for path in ("CLAUDE.md", "pyproject.toml", ".gitignore"):
            assert "o" in _allowed_actions_for(path)


# ─── manual_review_needed=False passes through unchanged ───


class TestPassThrough:
    def test_no_manual_review_files_no_prompt(self, tmp_path):
        plan = _plan(
            tmp_path,
            [
                _analysis("a.txt", policy="WRITE", manual_review_needed=False),
                _analysis("b.txt", policy="SKIP", manual_review_needed=False),
            ],
        )
        new_plan, out = _decide(plan, {"a.txt": b"x", "b.txt": b"y"})
        # No prompts → empty stdout
        assert out == ""
        # Analyses unchanged
        assert new_plan.analyses == plan.analyses

    def test_mixed_plan_only_manual_review_prompts(self, tmp_path):
        """mr=False files pass through; mr=True files prompt."""
        plan = _plan(
            tmp_path,
            [
                _analysis("auto.txt", policy="WRITE", manual_review_needed=False),
                _analysis("manual.txt", policy="SKIP", manual_review_needed=True),
            ],
        )
        # User accepts recommendation (empty line = default = [r]ecommended)
        new_plan, out = _decide(plan, {"auto.txt": b"x", "manual.txt": b"y"}, stdin_text="\n")
        # Only the manual file appears in stdout
        assert "manual.txt" in out
        assert "auto.txt" not in out
        # Auto file recommendation preserved exactly
        assert new_plan.analyses[0] == plan.analyses[0]
        # Manual file accepted; SKIP preserved, manual_review now False
        assert new_plan.analyses[1].recommendation.policy == "SKIP"
        assert new_plan.analyses[1].recommendation.manual_review_needed is False


# ─── --non-interactive raises before any prompt ───


class TestNonInteractive:
    def test_non_interactive_with_manual_review_raises(self, tmp_path):
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        with pytest.raises(_AdoptionAbort, match="--non-interactive"):
            _decide(plan, {"CLAUDE.md": b"x"}, non_interactive=True)

    def test_non_interactive_with_only_auto_files_passes(self, tmp_path):
        """--non-interactive is fine when no manual_review_needed=True files exist."""
        plan = _plan(
            tmp_path,
            [_analysis("a.txt", policy="WRITE", manual_review_needed=False)],
        )
        new_plan, _out = _decide(plan, {"a.txt": b"x"}, non_interactive=True)
        assert new_plan.analyses == plan.analyses


# ─── Each action key ───


class TestActions:
    def test_default_blank_line_accepts_recommendation(self, tmp_path):
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        new_plan, _out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="\n")
        rec = new_plan.analyses[0].recommendation
        assert rec.policy == "WRITE_NEW"  # unchanged from recommendation
        assert rec.manual_review_needed is False
        assert "user accepted recommendation" in rec.reason

    def test_r_accepts_recommendation(self, tmp_path):
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        new_plan, _out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="r\n")
        assert new_plan.analyses[0].recommendation.policy == "WRITE_NEW"

    def test_s_skips(self, tmp_path):
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        new_plan, _out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="s\n")
        rec = new_plan.analyses[0].recommendation
        assert rec.policy == "SKIP"
        assert "user chose [s]kip" in rec.reason

    def test_n_writes_new(self, tmp_path):
        """User overrides a recommended SKIP into WRITE_NEW (e.g. rule (h) default)."""
        plan = _plan(
            tmp_path,
            [_analysis("custom.txt", policy="SKIP", manual_review_needed=True)],
        )
        new_plan, _out = _decide(plan, {"custom.txt": b"x"}, stdin_text="n\n")
        rec = new_plan.analyses[0].recommendation
        assert rec.policy == "WRITE_NEW"
        assert "[n]ew" in rec.reason

    def test_a_appends_for_gitignore(self, tmp_path):
        """User picks APPEND_MERGE for .gitignore (allowed)."""
        plan = _plan(
            tmp_path,
            [_analysis(".gitignore", policy="SKIP", manual_review_needed=True)],
        )
        new_plan, _out = _decide(plan, {".gitignore": b"venv/\n"}, stdin_text="a\n")
        rec = new_plan.analyses[0].recommendation
        assert rec.policy == "APPEND_MERGE"
        # Post-decision invariants — user-authored ⇒ no further review, full confidence.
        assert rec.manual_review_needed is False
        assert rec.confidence == "high"

    def test_a_rejected_for_non_gitignore_re_prompts(self, tmp_path):
        """[a] for CLAUDE.md is invalid; user re-prompted."""
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        # First "a" rejected, then "s" accepted
        new_plan, out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="a\ns\n")
        rec = new_plan.analyses[0].recommendation
        assert rec.policy == "SKIP"
        assert "only available for .gitignore" in out

    def test_o_requires_typed_OVERWRITE_uppercase(self, tmp_path):
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        # User picks [o], then types "OVERWRITE" exactly
        new_plan, _out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="o\nOVERWRITE\n")
        rec = new_plan.analyses[0].recommendation
        assert rec.policy == "OVERWRITE"
        assert "[o]verwrite" in rec.reason
        # Post-decision invariants — even the destructive [o] path goes
        # through _user_decision, so the invariants hold here too.
        assert rec.manual_review_needed is False
        assert rec.confidence == "high"

    def test_o_rejects_lowercase_overwrite_re_prompts(self, tmp_path):
        """Per Scope #6 (d): typed `OVERWRITE` is case-sensitive (uppercase)."""
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        # [o] → "overwrite" (lowercase, rejected) → re-prompt → [s]kip
        new_plan, out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="o\noverwrite\ns\n")
        rec = new_plan.analyses[0].recommendation
        # NOT overwritten (lowercase was rejected); ended up SKIP
        assert rec.policy == "SKIP"
        assert "cancelled" in out

    def test_o_rejects_partial_match_re_prompts(self, tmp_path):
        """Typing `OVER` (partial) must NOT confirm — stray-keystroke safety."""
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        new_plan, out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="o\nOVER\ns\n")
        assert new_plan.analyses[0].recommendation.policy == "SKIP"
        assert "cancelled" in out

    def test_o_eof_during_confirmation_raises(self, tmp_path):
        """EOF on stdin during OVERWRITE confirmation → _AdoptionAbort (no destructive default)."""
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        with pytest.raises(_AdoptionAbort, match="OVERWRITE confirmation"):
            _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="o\n")

    def test_q_quits(self, tmp_path):
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        with pytest.raises(_AdoptionAbort, match="user quit"):
            _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="q\n")

    def test_eof_during_decision_raises(self, tmp_path):
        """EOF on stdin BEFORE any choice → _AdoptionAbort."""
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        with pytest.raises(_AdoptionAbort, match="EOF on stdin"):
            _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="")

    def test_help_re_prompts(self, tmp_path):
        """[?] prints help + re-prompts (not a terminal action)."""
        plan = _plan(
            tmp_path,
            [_analysis(".gitignore", policy="WRITE_NEW", manual_review_needed=True)],
        )
        new_plan, out = _decide(plan, {".gitignore": b"venv/\n"}, stdin_text="?\nr\n")
        assert "[r]ecommended" in out
        assert "[s]kip" in out
        # .gitignore so [a] should appear in help
        assert "[a]ppend" in out
        # Final choice was [r] → recommendation preserved
        assert new_plan.analyses[0].recommendation.policy == "WRITE_NEW"

    def test_help_for_non_gitignore_omits_append(self, tmp_path):
        """[?] help for CLAUDE.md must NOT mention [a]ppend (not allowed)."""
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        _new_plan, out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="?\ns\n")
        # Help line for [a]ppend should be absent
        assert "[a]ppend" not in out

    def test_d_shows_unified_diff_then_re_prompts(self, tmp_path):
        """[d] shows the diff and re-prompts (not terminal)."""
        (tmp_path / "CLAUDE.md").write_text("# original\n")
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        new_plan, out = _decide(plan, {"CLAUDE.md": b"# skill template\n"}, stdin_text="d\ns\n")
        # Unified diff headers
        assert "--- a/CLAUDE.md" in out
        assert "+++ b/CLAUDE.md" in out
        assert "# original" in out
        assert "# skill template" in out
        # Choice resolved
        assert new_plan.analyses[0].recommendation.policy == "SKIP"

    def test_invalid_choice_re_prompts(self, tmp_path):
        """Unknown chars (e.g. 'x') print an error + re-prompt."""
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        _new_plan, out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text="x\ns\n")
        assert "invalid choice" in out

    def test_multiple_files_decided_in_order(self, tmp_path):
        """Plan with 3 mr=True files → 3 prompts in order."""
        plan = _plan(
            tmp_path,
            [
                _analysis("a.txt", policy="WRITE_NEW", manual_review_needed=True),
                _analysis("b.txt", policy="SKIP", manual_review_needed=True),
                _analysis("c.txt", policy="SKIP", manual_review_needed=True),
            ],
        )
        # a → recommended, b → skip, c → new
        new_plan, out = _decide(
            plan,
            {"a.txt": b"x", "b.txt": b"y", "c.txt": b"z"},
            stdin_text="r\ns\nn\n",
        )
        assert new_plan.analyses[0].recommendation.policy == "WRITE_NEW"
        assert new_plan.analyses[1].recommendation.policy == "SKIP"
        assert new_plan.analyses[2].recommendation.policy == "WRITE_NEW"
        # All 3 files appear in stdout
        for name in ("a.txt", "b.txt", "c.txt"):
            assert name in out


# ─── NEUTRALIZE consent (PR-2 Part 2A) ───


class TestNeutralizeConsent:
    """NEUTRALIZE mutates the owner's `.gitignore` AND overrides a `.claude/`
    ignore they set deliberately, so it ALWAYS needs explicit consent
    (manual_review_needed=True). This pins the GENERIC consent gating —
    `--non-interactive` exits 2, interactive still prompts (auto-accept does NOT
    bypass it: `_interactive_decide` only receives `non_interactive`). The
    NEUTRALIZE-specific action matrix (offer only r/s/d/?/q, reject n/o/a) lands
    with the builder/apply in a later commit."""

    _CMD = ".claude/commands/dev-review.md"

    def test_neutralize_non_interactive_aborts(self, tmp_path):
        plan = _plan(
            tmp_path,
            [_analysis(self._CMD, policy="NEUTRALIZE", manual_review_needed=True)],
        )
        with pytest.raises(_AdoptionAbort, match="--non-interactive"):
            _decide(plan, {self._CMD: b"# cmd\n"}, non_interactive=True)

    def test_neutralize_prompts_interactively(self, tmp_path):
        plan = _plan(
            tmp_path,
            [_analysis(self._CMD, policy="NEUTRALIZE", manual_review_needed=True)],
        )
        new_plan, out = _decide(plan, {self._CMD: b"# cmd\n"}, stdin_text="r\n")
        # the file is surfaced for a decision and the recommendation is shown
        assert self._CMD in out
        assert "NEUTRALIZE" in out
        # [r] accept preserves NEUTRALIZE and marks it reviewed
        rec = new_plan.analyses[0].recommendation
        assert rec.policy == "NEUTRALIZE"
        assert rec.manual_review_needed is False


# ─── Decided recommendations always set manual_review_needed=False ───


class TestPostDecisionInvariants:
    @pytest.mark.parametrize(
        ("choice", "expected_policy"),
        [
            ("\n", "WRITE_NEW"),  # default = recommended
            ("r\n", "WRITE_NEW"),
            ("s\n", "SKIP"),
            ("n\n", "WRITE_NEW"),
        ],
    )
    def test_post_decision_manual_review_needed_false(self, tmp_path, choice, expected_policy):
        plan = _plan(
            tmp_path,
            [_analysis("CLAUDE.md", policy="WRITE_NEW", manual_review_needed=True)],
        )
        new_plan, _out = _decide(plan, {"CLAUDE.md": b"x"}, stdin_text=choice)
        rec = new_plan.analyses[0].recommendation
        assert rec.policy == expected_policy
        # User has decided → no further review needed downstream
        assert rec.manual_review_needed is False
        # User decision wins → confidence is "high"
        assert rec.confidence == "high"
