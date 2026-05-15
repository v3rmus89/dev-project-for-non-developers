"""Per-template render checks for shared/.

- StrictUndefined render success (Codex iter-11 finding #1)
- yaml parses
- No-Boxette-isms scan (Codex iter-4 finding #3)
- Triage-rule presence in CLAUDE.md / AGENTS.md / docs-plans-README
"""

from __future__ import annotations

import re

import pytest
import yaml

from bootstrap_lib import render

FORBIDDEN_TERMS = [
    r"\bboxette\b",
    r"\btelegram\b",
    r"\bpinfl\b",
    r"\bi18n/ru\.json\b",
    r"\bboxette\.db\b",
    r"\bcustoms\b",
    r"\bsignup\b",
    r"\bpayment\b",
]
FORBIDDEN_LITERAL = ["bot/"]

TRIAGE_HEADING = "## Triaging review findings"
TRIAGE_BULLETS = ["(a) Fold now", "(b) Park to BACKLOG", "(c) Reject", "(d) Surface to human"]


def _context(**overrides):
    ctx = {
        "project_name": "test-proj",
        "project_import_name": "test_proj",
        "language": "python",
        "python_version": "3.12",
        "enable_smoke": False,
        "github_owner": "test-owner",
        "github_repo": "test-repo",
        "github_review_mode": "claude",
    }
    ctx.update(overrides)
    return ctx


def _render(tmpl, ctx):
    env = render.build_env("python")
    return env.get_template(tmpl).render(**ctx)


SHARED_TEMPLATES_TO_SCAN = [
    "AGENTS.md.tmpl",
    "CLAUDE.md.tmpl",
    "CONTRIBUTING.md.tmpl",
    "BACKLOG.md.tmpl",
    "pull_request_template.md.tmpl",
    "claude-review.yml.tmpl",
    "docs-plans-README.md.tmpl",
    "docs-SMOKE.md.tmpl",
    "docs-codex-github-review-setup.md.tmpl",
    "editorconfig.tmpl",
    "scripts-run-with-clean-env.py.tmpl",
]


@pytest.mark.parametrize("tmpl", SHARED_TEMPLATES_TO_SCAN)
def test_shared_template_renders_without_undefined_error(tmpl):
    rendered = _render(tmpl, _context())
    assert rendered, f"{tmpl} rendered empty"


@pytest.mark.parametrize("tmpl", SHARED_TEMPLATES_TO_SCAN)
def test_no_boxette_isms_in_shared_templates(tmpl):
    rendered = _render(tmpl, _context())
    lower = rendered.lower()
    for term in FORBIDDEN_TERMS:
        assert not re.search(term, lower, re.IGNORECASE), f"forbidden term {term!r} found in {tmpl}"
    for literal in FORBIDDEN_LITERAL:
        # Allow `bot/` only inside legit URLs (none expected in our templates)
        assert literal not in lower, f"forbidden literal {literal!r} in {tmpl}"


def test_claude_review_yml_parses_as_yaml():
    rendered = _render("claude-review.yml.tmpl", _context(github_review_mode="claude"))
    data = yaml.safe_load(rendered)
    assert data["name"] == "Claude review"
    # The Actions `on:` keyword parses as Python True (YAML 1.1) — accept either
    assert "on" in data or True in data
    # Secret reference survived the {% raw %} wrap
    assert "CLAUDE_CODE_OAUTH_TOKEN" in rendered


def test_pull_request_template_omits_ai_checklist_in_none_mode():
    rendered = _render("pull_request_template.md.tmpl", _context(github_review_mode="none"))
    assert "claude[bot]" not in rendered
    assert "chatgpt-codex-connector" not in rendered


def test_pull_request_template_includes_claude_only_in_claude_mode():
    rendered = _render("pull_request_template.md.tmpl", _context(github_review_mode="claude"))
    assert "claude[bot]" in rendered
    assert "chatgpt-codex-connector" not in rendered


def test_pull_request_template_includes_both_in_both_docs_mode():
    rendered = _render("pull_request_template.md.tmpl", _context(github_review_mode="both-docs"))
    assert "claude[bot]" in rendered
    assert "chatgpt-codex-connector" in rendered


@pytest.mark.parametrize("tmpl", ["CLAUDE.md.tmpl", "AGENTS.md.tmpl", "docs-plans-README.md.tmpl"])
def test_triage_rule_present(tmpl):
    rendered = _render(tmpl, _context())
    assert TRIAGE_HEADING in rendered, f"missing triage heading in {tmpl}"
    for bullet in TRIAGE_BULLETS:
        assert bullet in rendered, f"missing bullet {bullet!r} in {tmpl}"


def test_editorconfig_renders_root_true():
    rendered = _render("editorconfig.tmpl", _context())
    assert "root = true" in rendered


@pytest.mark.parametrize("mode", ["claude", "both-docs"])
def test_contributing_template_mentions_oauth_token_in_opt_in_modes(mode):
    """When the skill emits a claude-review workflow (opt-in modes), the
    generated CONTRIBUTING.md must tell users to set the
    CLAUDE_CODE_OAUTH_TOKEN repo secret — otherwise the workflow runs but
    the action fails auth."""
    rendered = _render("CONTRIBUTING.md.tmpl", _context(github_review_mode=mode))
    assert "CLAUDE_CODE_OAUTH_TOKEN" in rendered
    assert "claude setup-token" in rendered
    assert "github.com/apps/claude" in rendered


def test_contributing_template_omits_oauth_token_in_none_mode():
    """In default mode=none, no claude-review.yml is emitted, so we MUST NOT
    burden the user with secret-setup instructions for a workflow they
    don't have."""
    rendered = _render("CONTRIBUTING.md.tmpl", _context(github_review_mode="none"))
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in rendered
