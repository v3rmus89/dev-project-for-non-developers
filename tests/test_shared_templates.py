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
        "node_version": "24",
        "go_version": "1.26",
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


def test_claude_md_nodejs_render_mentions_node_not_python_tooling():
    """Closes Codex iter-1 #4 / iter-2 #4 / Claude iter-4: language-conditional
    sections in shared templates must produce language-appropriate content."""
    rendered = _render("CLAUDE.md.tmpl", _context(language="nodejs"))
    # Node-specific phrases must appear
    assert "Biome" in rendered or "biome" in rendered
    assert "vitest" in rendered
    assert "npm" in rendered or "Husky" in rendered
    # Python-specific phrases must NOT appear in the Commands table area
    # (they may appear elsewhere in the doc that's still language-neutral)
    # Specifically: the commands table should NOT mention ruff/pytest
    commands_section_start = rendered.index("## Commands")
    commands_section_end = rendered.index("## ", commands_section_start + 1)
    commands_section = rendered[commands_section_start:commands_section_end]
    assert "ruff" not in commands_section, (
        f"Node CLAUDE.md should not mention ruff in Commands:\n{commands_section}"
    )
    assert "pytest" not in commands_section, (
        f"Node CLAUDE.md should not mention pytest in Commands:\n{commands_section}"
    )


def test_claude_md_python_render_mentions_python_not_node_tooling():
    rendered = _render("CLAUDE.md.tmpl", _context(language="python"))
    commands_section_start = rendered.index("## Commands")
    commands_section_end = rendered.index("## ", commands_section_start + 1)
    commands_section = rendered[commands_section_start:commands_section_end]
    assert "ruff" in commands_section
    assert "pytest" in commands_section
    assert "Biome" not in commands_section
    assert "vitest" not in commands_section


@pytest.mark.parametrize("language", ["python", "nodejs", "go"])
def test_agents_md_format_tool_is_language_appropriate(language):
    rendered = _render("AGENTS.md.tmpl", _context(language=language))
    expected = {"python": "ruff", "nodejs": "Biome", "go": "gofumpt"}
    expected_tool = expected[language]
    other_tools = [t for lang, t in expected.items() if lang != language]
    assert f"`make format` ({expected_tool})" in rendered, (
        f"AGENTS.md.tmpl should mention {expected_tool}"
    )
    for other_tool in other_tools:
        assert f"`make format` ({other_tool})" not in rendered


def test_claude_md_go_render_mentions_go_not_other_tooling():
    """Closes Codex iter-5 #5 verification: Go render shouldn't leak
    Python or Node tooling terms in commands/setup/hook sections."""
    rendered = _render("CLAUDE.md.tmpl", _context(language="go"))
    commands_section_start = rendered.index("## Commands")
    commands_section_end = rendered.index("## ", commands_section_start + 1)
    commands_section = rendered[commands_section_start:commands_section_end]
    # Go-specific phrases must appear
    assert "gofumpt" in commands_section or "golangci-lint" in commands_section
    assert "go test" in commands_section.lower() or "Go" in commands_section
    # Python tooling must NOT appear
    assert "ruff" not in commands_section
    assert "pytest" not in commands_section
    assert "venv" not in commands_section.lower()
    # Node tooling must NOT appear
    assert "Biome" not in commands_section
    assert "vitest" not in commands_section
    assert "npm " not in commands_section


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


def test_makefile_review_renders_new_targets():
    """PR #4 adds 3 new Makefile targets and 4 new variables to
    shared/Makefile.review.tmpl."""
    rendered = _render("Makefile.review.tmpl", _context())
    for target in [
        "review-commit-by-codex:",
        "review-commit-by-claude:",
        "review-plan-consistency-by-claude:",
    ]:
        assert target in rendered, f"missing target {target!r}"
    for var in [
        "REVIEW_COMMIT_SHA",
        "REVIEW_COMMIT_OUT_CODEX",
        "REVIEW_COMMIT_OUT_CLAUDE",
        "PLAN_CONSISTENCY_OUT",
    ]:
        assert var in rendered, f"missing variable {var!r}"
    # .PHONY must include all new targets
    assert ".PHONY:" in rendered
    phony_line_start = rendered.index(".PHONY:")
    # Match until first blank line after PHONY
    phony_end = rendered.index("\n\n", phony_line_start)
    phony_block = rendered[phony_line_start:phony_end]
    for target_name in [
        "review-commit-by-codex",
        "review-commit-by-claude",
        "review-plan-consistency-by-claude",
    ]:
        assert target_name in phony_block, f"{target_name} not declared phony"


def test_makefile_review_plan_prompt_contains_cross_section_instruction():
    """PR #4 idea-(a): both review-plan-by-{codex,claude} prompts must include
    the 'where else in the plan' cross-section impact instruction."""
    rendered = _render("Makefile.review.tmpl", _context())
    assert "OTHER sections of the same plan" in rendered, "idea-(a) prompt extension missing"


def test_makefile_tier1_prompt_byte_identical_between_makefile_and_contributing():
    """PR #4 idea-(b) macro design: the Tier-1 prompt must be byte-identical
    between the Makefile recipe's rendered prompt (commit_ref=HEAD) and the
    CONTRIBUTING.md template's subagent prompt (commit_ref=<SHA>).
    Macro construction makes drift impossible, but this test locks it down."""
    makefile = _render("Makefile.review.tmpl", _context())
    contributing = _render("CONTRIBUTING.md.tmpl", _context())

    # Extract the prompt from the Makefile (look for the review-commit-by-codex recipe)
    # The prompt starts after `--output-last-message "$(REVIEW_COMMIT_OUT_CODEX)" \` and
    # is on a line beginning with whitespace+quote.
    rec_start = makefile.index("review-commit-by-codex:")
    rec_end = makefile.index("review-commit-by-claude:")
    rec_block = makefile[rec_start:rec_end]
    # Extract prompt string between first `"Review commit HEAD` ... up to closing `\"`
    p_start = rec_block.index('"Review commit HEAD')
    # The prompt is a single line; find the closing quote at end of that line
    line_end = rec_block.index("\n", p_start)
    makefile_prompt = rec_block[p_start + 1 : line_end].rstrip('"').rstrip(" \\").rstrip('"')

    # Extract from CONTRIBUTING.md the prompt with <SHA>
    p_start_c = contributing.index('"Review commit <SHA>')
    # The prompt is everything until the closing `"` at end of paragraph
    line_end_c = contributing.index('"\n', p_start_c)
    contributing_prompt = contributing[p_start_c + 1 : line_end_c]

    # Normalize: substitute commit_ref placeholder both ways
    normalized_makefile = makefile_prompt.replace("HEAD", "<COMMIT>")
    normalized_contributing = contributing_prompt.replace("<SHA>", "<COMMIT>")
    assert normalized_makefile == normalized_contributing, (
        f"Tier-1 prompt drift between Makefile recipe and CONTRIBUTING.md:\n"
        f"Makefile:    {normalized_makefile!r}\n"
        f"CONTRIBUTING: {normalized_contributing!r}"
    )


def test_makefile_tier1_prompt_contains_key_phrases():
    """Defensive smoke check: known-good phrases must appear in the rendered
    Tier-1 prompt regardless of macro construction."""
    rendered = _render("Makefile.review.tmpl", _context())
    rec_start = rendered.index("review-commit-by-codex:")
    rec_end = rendered.index("review-commit-by-claude:")
    rec_block = rendered[rec_start:rec_end]
    for phrase in [
        "tests that pass for the wrong reason",
        "Tier-1",
        "plan-impl drift",
        "Do NOT edit files",
    ]:
        assert phrase in rec_block, f"Tier-1 prompt missing phrase: {phrase!r}"


@pytest.mark.parametrize(
    "mode,expected_present,expected_absent",
    [
        (
            "claude",
            ["claude[bot]", "@claude review", "BOTH tiers"],
            ["@codex review", "chatgpt-codex-connector"],
        ),
        (
            "both-docs",
            ["claude[bot]", "@codex review", "BOTH tiers"],
            [],
        ),
        (
            "none",
            ["Tier-1"],
            # Closes Codex iter-1 Tier-2 #1: none-mode must NOT say "BOTH tiers"
            # (contradicts the conditional Tier-2-not-configured line that follows)
            ["claude[bot]", "@codex review", "chatgpt-codex-connector", "BOTH tiers"],
        ),
    ],
)
def test_claude_md_two_tier_section_variants(mode, expected_present, expected_absent):
    """The CLAUDE.md Two-tier section has 3 Jinja variants — assert each renders
    with the appropriate bot/non-bot mentions."""
    rendered = _render("CLAUDE.md.tmpl", _context(github_review_mode=mode))
    two_tier_start = rendered.index("## Two-tier code review")
    # Find the end of the section (next ## heading)
    section_end_idx = rendered.index("\n## ", two_tier_start + 1)
    section = rendered[two_tier_start:section_end_idx]
    for phrase in expected_present:
        assert phrase in section, f"Two-tier section in mode={mode!r} should mention {phrase!r}"
    for phrase in expected_absent:
        assert phrase not in section, (
            f"Two-tier section in mode={mode!r} should NOT mention {phrase!r}"
        )


def test_contributing_template_omits_oauth_token_in_none_mode():
    """In default mode=none, no claude-review.yml is emitted, so we MUST NOT
    burden the user with secret-setup instructions for a workflow they
    don't have."""
    rendered = _render("CONTRIBUTING.md.tmpl", _context(github_review_mode="none"))
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in rendered
