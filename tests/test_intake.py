"""Tests for bootstrap_lib.intake — the interactive intake flow (skill PR #8).

Each test feeds scripted answers via an in-memory stdin and asserts the argv
`run_intake` builds (or `None` on cancel, or `IntakeAborted` on EOF). No real
TTY is needed — `run_intake` reads from the injected `stdin`.
"""

from __future__ import annotations

import io

import pytest

from bootstrap_lib import intake


def _run(answers):
    """Run run_intake with `answers` (a list of line strings) as stdin.
    Returns (result, stdout_text)."""
    stdin = io.StringIO("\n".join(answers) + "\n")
    stdout = io.StringIO()
    result = intake.run_intake(stdin=stdin, stdout=stdout)
    return result, stdout.getvalue()


def test_intake_python_greenfield_maps_to_argv(tmp_path):
    out = tmp_path / "newproj"  # does not exist → greenfield
    # name, brief(skip), language=1(python), pm=1(uv), review=1(none),
    # smoke=1(no), outdir, confirm=1(apply)
    result, _ = _run(["my-project", "", "1", "1", "1", "1", str(out), "1"])
    assert result == [
        "--language",
        "python",
        "--project-name",
        "my-project",
        "--out",
        str(out),
        "--github-review",
        "none",
        "--package-manager",
        "uv",
        "--apply",
    ]


def test_intake_nodejs_skips_package_manager_question(tmp_path):
    out = tmp_path / "n"
    # nodejs: name, brief(skip), language=2, review=1(none), smoke=1(no),
    # outdir, confirm=1 — NO pm question
    result, _ = _run(["nodeproj", "", "2", "1", "1", str(out), "1"])
    assert "--package-manager" not in result
    assert result[:4] == ["--language", "nodejs", "--project-name", "nodeproj"]


def test_intake_both_docs_collects_owner_repo(tmp_path):
    out = tmp_path / "b"
    # name, brief(skip), language=1, pm=1, review=3(both-docs), owner, repo,
    # smoke=1, outdir, confirm=1
    result, _ = _run(["proj", "", "1", "1", "3", "acme", "myrepo", "1", str(out), "1"])
    assert result[result.index("--github-review") + 1] == "both-docs"
    assert result[result.index("--github-owner") + 1] == "acme"
    assert result[result.index("--github-repo") + 1] == "myrepo"


def test_intake_reprompts_on_bad_project_name(tmp_path):
    out = tmp_path / "p"
    # "Bad Name" is invalid (uppercase + space) → re-asked; "good-name" accepted;
    # the blank brief follows the *accepted* name
    result, _ = _run(["Bad Name", "good-name", "", "1", "1", "1", "1", str(out), "1"])
    assert result[result.index("--project-name") + 1] == "good-name"


def test_intake_reprompts_on_empty_required_answer(tmp_path):
    out = tmp_path / "e"
    # review=2(claude) → owner+repo required; empty answers are re-asked
    result, _ = _run(["proj", "", "1", "1", "2", "", "acme", "", "r", "1", str(out), "1"])
    assert result[result.index("--github-owner") + 1] == "acme"
    assert result[result.index("--github-repo") + 1] == "r"


def test_intake_reprompts_on_bad_menu_choice(tmp_path):
    out = tmp_path / "m"
    # blank brief, then language menu: "5" (out of range) and "xyz"
    # (non-numeric) are re-asked; the literal value "python" is accepted
    result, _ = _run(["proj", "", "5", "xyz", "python", "1", "1", "1", str(out), "1"])
    assert result[result.index("--language") + 1] == "python"


def test_intake_outdir_default_is_parent_project_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # so `../myproj` resolves to a clean, non-existent path
    # empty output-dir answer → accepts the default ../<project-name>
    result, _ = _run(["myproj", "", "1", "1", "1", "1", "", "1"])
    assert result[result.index("--out") + 1] == "../myproj"


def test_intake_cancel_returns_none(tmp_path):
    out = tmp_path / "c"
    # confirm=2(cancel)
    result, text = _run(["proj", "", "1", "1", "1", "1", str(out), "2"])
    assert result is None
    assert "cancelled" in text


def test_intake_eof_raises_intake_aborted():
    # empty stdin → first prompt hits EOF
    with pytest.raises(intake.IntakeAborted):
        intake.run_intake(stdin=io.StringIO(""), stdout=io.StringIO())


def test_intake_eof_midflow_raises_intake_aborted():
    # stdin exhausts after the language answer, mid-flow: name, blank brief,
    # language="1", then the package-manager prompt hits EOF
    with pytest.raises(intake.IntakeAborted):
        intake.run_intake(stdin=io.StringIO("proj\n\n1\n"), stdout=io.StringIO())


def test_intake_colliding_outdir_python_routes_to_adopt(tmp_path):
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "Makefile").write_text("x\n")  # a file the skill writes → collision
    clean = tmp_path / "clean"
    # outdir: busy (collision → re-ask), then clean (greenfield)
    result, text = _run(["proj", "", "1", "1", "1", "1", str(busy), str(clean), "1"])
    assert result[result.index("--out") + 1] == str(clean)
    assert "already contains a project" in text
    assert "--mode=adopt" in text  # python → adopt-mode pointer


def test_intake_colliding_outdir_nodejs_no_adopt_pointer(tmp_path):
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "Makefile").write_text("x\n")
    clean = tmp_path / "clean"
    # nodejs: name, lang=2, review=1, smoke=1, outdir(busy→re-ask), outdir(clean), confirm=1
    result, text = _run(["proj", "", "2", "1", "1", str(busy), str(clean), "1"])
    assert result[result.index("--out") + 1] == str(clean)
    assert "already contains a project" in text
    assert "--mode=adopt" not in text  # nodejs → NO adopt-mode pointer
    assert "planned follow-up" in text


def test_intake_cross_language_manifest_routes_to_existing(tmp_path):
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "pyproject.toml").write_text("[project]\n")  # a Python manifest
    clean = tmp_path / "clean"
    # nodejs run — a pyproject.toml is NOT in the nodejs planned-file set, so only
    # the language-agnostic manifest scan catches it
    result, text = _run(["proj", "", "2", "1", "1", str(busy), str(clean), "1"])
    assert result[result.index("--out") + 1] == str(clean)
    assert "already contains a project" in text


def test_intake_collision_on_review_gated_file(tmp_path):
    busy = tmp_path / "busy"
    (busy / "docs").mkdir(parents=True)
    (busy / "docs" / "SMOKE.md").write_text("x\n")
    clean = tmp_path / "clean"
    # smoke=2(yes) → docs/SMOKE.md enters the planned set → collision detected.
    # Proves the greenfield check runs AFTER the smoke question.
    result, text = _run(["proj", "", "1", "1", "1", "2", str(busy), str(clean), "1"])
    assert result[result.index("--out") + 1] == str(clean)
    assert "--enable-smoke" in result
    assert "already contains a project" in text


def test_intake_directory_named_package_json_is_greenfield(tmp_path):
    out = tmp_path / "proj"
    out.mkdir()
    (out / "package.json").mkdir()  # a DIRECTORY named like a manifest, not a manifest file
    # python run — the manifest scan uses is_file(), so a directory named
    # package.json must not false-positive as an existing project
    result, text = _run(["proj", "", "1", "1", "1", "1", str(out), "1"])
    assert result is not None
    assert "already contains a project" not in text


def test_intake_outdir_with_noncode_files_is_greenfield(tmp_path):
    out = tmp_path / "proj"
    out.mkdir()
    (out / "business-goals.md").write_text("goals\n")
    (out / "data").mkdir()
    (out / "data" / "raw.txt").write_text("rows\n")
    # non-skill, non-manifest files → still greenfield
    result, text = _run(["proj", "", "1", "1", "1", "1", str(out), "1"])
    assert result is not None
    assert result[result.index("--out") + 1] == str(out)
    assert "already contains a project" not in text


# ── PR #9 — stack-suggestion intake tests ───────────────────────────────────


def test_intake_brief_confident_prefills_language(tmp_path):
    """A confident brief pre-fills the language menu; a blank answer accepts
    the suggested default."""
    out = tmp_path / "p"
    # name, brief(→python), language(blank=accept default), pm, review, smoke,
    # outdir, confirm
    result, text = _run(
        ["proj", "a data pipeline with automation scripts", "", "1", "1", "1", str(out), "1"]
    )
    assert result[result.index("--language") + 1] == "python"
    assert "I'd suggest python" in text
    assert "← recommended" in text
    assert "[default: python" in text  # the language-menu default hint


def test_intake_skip_brief_yields_pr8_argv(tmp_path):
    """Regression lock: skipping the brief produces argv byte-identical to the
    equivalent PR #8 flow — PR #9 is purely additive."""
    out = tmp_path / "p"
    result, _ = _run(["proj", "", "1", "1", "1", "1", str(out), "1"])
    assert result == [
        "--language",
        "python",
        "--project-name",
        "proj",
        "--out",
        str(out),
        "--github-review",
        "none",
        "--package-manager",
        "uv",
        "--apply",
    ]


def test_intake_brief_override_user_picks_a_different_language(tmp_path):
    """A suggestion only sets the default — the user can still pick anything;
    an explicit choice wins over the suggestion."""
    out = tmp_path / "p"
    # brief → python; user explicitly picks 2 (nodejs); nodejs skips the pm question
    result, _ = _run(["proj", "an automation script for data", "2", "1", "1", str(out), "1"])
    assert result[result.index("--language") + 1] == "nodejs"


def test_intake_brief_low_confidence_no_prefill(tmp_path):
    """A low-confidence brief makes no suggestion: the language menu has no
    default, so a blank answer re-prompts (PR #8 behaviour)."""
    out = tmp_path / "p"
    # nonsense brief → None; language menu un-prefilled → "" re-prompts, then "1"
    result, text = _run(["proj", "qqzzx nonsense gibberish", "", "1", "1", "1", "1", str(out), "1"])
    assert result[result.index("--language") + 1] == "python"
    assert "couldn't infer a language" in text
    assert "← recommended" not in text


def test_intake_brief_is_not_echoed_back(tmp_path):
    """Privacy: a canary token in the brief never appears in stdout or argv —
    only the fixed per-language rationale is shown."""
    out = tmp_path / "p"
    canary = "ZZSECRETCANARYZZ"
    result, text = _run(
        ["proj", f"a data pipeline {canary} automation", "", "1", "1", "1", str(out), "1"]
    )
    assert canary not in text
    assert canary not in " ".join(result)
    # the fixed rationale still rendered
    assert "Python's usual home" in text


def test_intake_visible_marker_absent_when_brief_skipped(tmp_path):
    """Skipping the brief shows no `← recommended` marker — that marker is the
    unique signal of a pre-filled suggestion. (The default-hint string is the
    other half of the marker; the no-default language prompt is pinned
    byte-for-byte by `test_language_menu_prompt_no_default_is_pr8_identical`.)"""
    out = tmp_path / "p"
    _, text = _run(["proj", "", "1", "1", "1", "1", str(out), "1"])
    assert "← recommended" not in text


def test_language_menu_prompt_no_default_is_pr8_identical():
    """The no-suggestion language-menu prompt is byte-identical to PR #8's
    hardcoded string — the pre-PR-9 on-screen experience is unchanged."""
    assert intake._language_menu_prompt(None) == (
        "Language:\n  1) python\n  2) nodejs\n  3) go\nChoose [1-3]: "
    )


def test_ask_menu_default_branch_accepts_blank():
    """`_ask_menu` with `default` set: a blank line returns the default."""
    stdin = io.StringIO("\n")  # one blank line
    chosen = intake._ask_menu(stdin, io.StringIO(), "pick: ", ["a", "b", "c"], default="b")
    assert chosen == "b"


def test_ask_menu_no_default_blank_reprompts():
    """`_ask_menu` with no `default` (PR #8 behaviour): a blank line
    re-prompts; a real choice on the next line is taken."""
    stdin = io.StringIO("\n2\n")  # blank (re-prompt), then "2"
    chosen = intake._ask_menu(stdin, io.StringIO(), "pick: ", ["a", "b", "c"])
    assert chosen == "b"


def test_ask_menu_default_not_in_choices_raises():
    """`_ask_menu` fails loud if `default` is not one of `choices` — guards a
    stack_suggest ↔ _flags.LANGUAGES drift."""
    with pytest.raises(ValueError, match="not in choices"):
        intake._ask_menu(io.StringIO("\n"), io.StringIO(), "pick: ", ["a", "b"], default="z")
