"""--github-review mode behaviour: none / claude / both-docs."""

from __future__ import annotations

import io as io_module
import sys

import pytest

from bootstrap_lib import cli


def run_apply(argv):
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = io_module.StringIO()
    sys.stderr = io_module.StringIO()
    try:
        rc = cli.main(list(argv))
    except SystemExit as e:
        rc = e.code
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return rc


@pytest.mark.parametrize(
    "mode,expected_workflow_exists,expected_extra_doc_exists,expected_pr_mentions",
    [
        ("none", False, False, []),
        ("claude", True, False, ["claude[bot]"]),
        ("both-docs", True, True, ["claude[bot]", "chatgpt-codex-connector"]),
    ],
)
def test_github_review_mode(
    tmp_path,
    mode,
    expected_workflow_exists,
    expected_extra_doc_exists,
    expected_pr_mentions,
):
    args = [
        "--apply",
        "--language",
        "python",
        "--project-name",
        "test",
        "--out",
        str(tmp_path / "out"),
        "--github-review",
        mode,
    ]
    if mode != "none":
        args += ["--github-owner", "test-owner", "--github-repo", "test-repo"]
    rc = run_apply(args)
    assert rc == 0
    out = tmp_path / "out"
    workflow = out / ".github" / "workflows" / "claude-review.yml"
    extra_doc = out / "docs" / "codex-github-review-setup.md"
    pr_template = (out / ".github" / "pull_request_template.md").read_text()

    assert workflow.exists() == expected_workflow_exists
    assert extra_doc.exists() == expected_extra_doc_exists
    for mention in expected_pr_mentions:
        assert mention in pr_template, f"missing {mention} in PR template"
    # No-orphan-checklist: reviewer mention implies the matching file exists
    if "claude[bot]" in pr_template:
        assert workflow.exists()
    if "chatgpt-codex-connector" in pr_template:
        assert extra_doc.exists()


def test_default_mode_is_none(tmp_path):
    """Codex iter-1 finding #4."""
    rc = run_apply(
        [
            "--apply",
            "--language",
            "python",
            "--project-name",
            "test",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 0
    out = tmp_path / "out"
    assert not (out / ".github" / "workflows" / "claude-review.yml").exists()
    pr_template = (out / ".github" / "pull_request_template.md").read_text()
    assert "claude[bot]" not in pr_template
    assert "chatgpt-codex-connector" not in pr_template
