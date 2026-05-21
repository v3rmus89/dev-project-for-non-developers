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
    # name, language=1(python), pm=1(uv), review=1(none), smoke=1(no), outdir, confirm=1(apply)
    result, _ = _run(["my-project", "1", "1", "1", "1", str(out), "1"])
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
    # nodejs: name, language=2, review=1(none), smoke=1(no), outdir, confirm=1 — NO pm question
    result, _ = _run(["nodeproj", "2", "1", "1", str(out), "1"])
    assert "--package-manager" not in result
    assert result[:4] == ["--language", "nodejs", "--project-name", "nodeproj"]


def test_intake_both_docs_collects_owner_repo(tmp_path):
    out = tmp_path / "b"
    # name, language=1, pm=1, review=3(both-docs), owner, repo, smoke=1, outdir, confirm=1
    result, _ = _run(["proj", "1", "1", "3", "acme", "myrepo", "1", str(out), "1"])
    assert result[result.index("--github-review") + 1] == "both-docs"
    assert result[result.index("--github-owner") + 1] == "acme"
    assert result[result.index("--github-repo") + 1] == "myrepo"


def test_intake_reprompts_on_bad_project_name(tmp_path):
    out = tmp_path / "p"
    # "Bad Name" is invalid (uppercase + space) → re-asked; "good-name" accepted
    result, _ = _run(["Bad Name", "good-name", "1", "1", "1", "1", str(out), "1"])
    assert result[result.index("--project-name") + 1] == "good-name"


def test_intake_reprompts_on_empty_required_answer(tmp_path):
    out = tmp_path / "e"
    # review=2(claude) → owner+repo required; empty answers are re-asked
    result, _ = _run(["proj", "1", "1", "2", "", "acme", "", "r", "1", str(out), "1"])
    assert result[result.index("--github-owner") + 1] == "acme"
    assert result[result.index("--github-repo") + 1] == "r"


def test_intake_reprompts_on_bad_menu_choice(tmp_path):
    out = tmp_path / "m"
    # language menu: "5" (out of range) and "xyz" (non-numeric) are re-asked;
    # the literal value "python" is accepted
    result, _ = _run(["proj", "5", "xyz", "python", "1", "1", "1", str(out), "1"])
    assert result[result.index("--language") + 1] == "python"


def test_intake_outdir_default_is_parent_project_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # so `../myproj` resolves to a clean, non-existent path
    # empty output-dir answer → accepts the default ../<project-name>
    result, _ = _run(["myproj", "1", "1", "1", "1", "", "1"])
    assert result[result.index("--out") + 1] == "../myproj"


def test_intake_cancel_returns_none(tmp_path):
    out = tmp_path / "c"
    # confirm=2(cancel)
    result, text = _run(["proj", "1", "1", "1", "1", str(out), "2"])
    assert result is None
    assert "cancelled" in text


def test_intake_eof_raises_intake_aborted():
    # empty stdin → first prompt hits EOF
    with pytest.raises(intake.IntakeAborted):
        intake.run_intake(stdin=io.StringIO(""), stdout=io.StringIO())


def test_intake_eof_midflow_raises_intake_aborted():
    # stdin exhausts after the language answer, mid-flow
    with pytest.raises(intake.IntakeAborted):
        intake.run_intake(stdin=io.StringIO("proj\n1\n"), stdout=io.StringIO())


def test_intake_colliding_outdir_python_routes_to_adopt(tmp_path):
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "Makefile").write_text("x\n")  # a file the skill writes → collision
    clean = tmp_path / "clean"
    # outdir: busy (collision → re-ask), then clean (greenfield)
    result, text = _run(["proj", "1", "1", "1", "1", str(busy), str(clean), "1"])
    assert result[result.index("--out") + 1] == str(clean)
    assert "already contains a project" in text
    assert "--mode=adopt" in text  # python → adopt-mode pointer


def test_intake_colliding_outdir_nodejs_no_adopt_pointer(tmp_path):
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "Makefile").write_text("x\n")
    clean = tmp_path / "clean"
    # nodejs: name, lang=2, review=1, smoke=1, outdir(busy→re-ask), outdir(clean), confirm=1
    result, text = _run(["proj", "2", "1", "1", str(busy), str(clean), "1"])
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
    result, text = _run(["proj", "2", "1", "1", str(busy), str(clean), "1"])
    assert result[result.index("--out") + 1] == str(clean)
    assert "already contains a project" in text


def test_intake_collision_on_review_gated_file(tmp_path):
    busy = tmp_path / "busy"
    (busy / "docs").mkdir(parents=True)
    (busy / "docs" / "SMOKE.md").write_text("x\n")
    clean = tmp_path / "clean"
    # smoke=2(yes) → docs/SMOKE.md enters the planned set → collision detected.
    # Proves the greenfield check runs AFTER the smoke question.
    result, text = _run(["proj", "1", "1", "1", "2", str(busy), str(clean), "1"])
    assert result[result.index("--out") + 1] == str(clean)
    assert "--enable-smoke" in result
    assert "already contains a project" in text


def test_intake_directory_named_package_json_is_greenfield(tmp_path):
    out = tmp_path / "proj"
    out.mkdir()
    (out / "package.json").mkdir()  # a DIRECTORY named like a manifest, not a manifest file
    # python run — the manifest scan uses is_file(), so a directory named
    # package.json must not false-positive as an existing project
    result, text = _run(["proj", "1", "1", "1", "1", str(out), "1"])
    assert result is not None
    assert "already contains a project" not in text


def test_intake_outdir_with_noncode_files_is_greenfield(tmp_path):
    out = tmp_path / "proj"
    out.mkdir()
    (out / "business-goals.md").write_text("goals\n")
    (out / "data").mkdir()
    (out / "data" / "raw.txt").write_text("rows\n")
    # non-skill, non-manifest files → still greenfield
    result, text = _run(["proj", "1", "1", "1", "1", str(out), "1"])
    assert result is not None
    assert result[result.index("--out") + 1] == str(out)
    assert "already contains a project" not in text
