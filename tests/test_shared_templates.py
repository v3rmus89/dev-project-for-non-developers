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
    "scripts-loop-status.py.tmpl",
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


def _extract_prompts_between_quotes(text: str, start_marker: str, count: int) -> list[str]:
    """Extract `count` quoted prompts from `text`, each starting with `start_marker`."""
    prompts: list[str] = []
    cursor = 0
    for _ in range(count):
        idx = text.index(start_marker, cursor)
        # The prompt is a single line; find the closing quote at end of that line
        line_end = text.index("\n", idx)
        quoted = text[idx + 1 : line_end].rstrip('"').rstrip(" \\").rstrip('"')
        prompts.append(quoted)
        cursor = line_end
    return prompts


def test_makefile_tier1_prompt_byte_identical_between_makefile_and_contributing():
    """PR #4 idea-(b) macro design + PR #5b dual-variant: the Tier-1 prompts
    must be byte-identical between Makefile recipe's rendered prompts and
    CONTRIBUTING.md template's two subagent variants. After PR #5b the macro
    has TWO branches (with vs without plan_file); both must round-trip
    identically across the two surfaces."""
    makefile = _render("Makefile.review.tmpl", _context())
    contributing = _render("CONTRIBUTING.md.tmpl", _context())

    # Extract from review-commit-by-codex (two prompts: with-plan, without-plan)
    rec_start = makefile.index("review-commit-by-codex:")
    rec_end = makefile.index("review-commit-by-claude:")
    rec_block = makefile[rec_start:rec_end]
    makefile_prompts = _extract_prompts_between_quotes(rec_block, '"Review commit HEAD', count=2)
    assert len(makefile_prompts) == 2, (
        "Makefile recipe should have 2 prompts (with + without plan_file)"
    )
    # By order in the recipe: first is the `if [ -n "$(PLAN_FILE)" ]` branch (with plan), second is else (without)
    makefile_with_plan, makefile_without_plan = makefile_prompts

    # Extract from CONTRIBUTING.md (two prompts: Variant A with-plan, Variant B without)
    contributing_prompts = _extract_prompts_between_quotes(
        contributing, '"Review commit <SHA>', count=2
    )
    assert len(contributing_prompts) == 2, "CONTRIBUTING.md should have 2 prompt variants"
    contributing_with_plan, contributing_without_plan = contributing_prompts

    # Normalize placeholders: HEAD <-> <SHA>, $(PLAN_FILE) <-> <PLAN_FILE>
    def normalize(p: str) -> str:
        return (
            p.replace("HEAD", "<COMMIT>")
            .replace("<SHA>", "<COMMIT>")
            .replace("$(PLAN_FILE)", "<PLAN>")
            .replace("<PLAN_FILE>", "<PLAN>")
        )

    assert normalize(makefile_with_plan) == normalize(contributing_with_plan), (
        f"with-plan prompt drift between Makefile + CONTRIBUTING:\n"
        f"Makefile:     {normalize(makefile_with_plan)!r}\n"
        f"CONTRIBUTING: {normalize(contributing_with_plan)!r}"
    )
    assert normalize(makefile_without_plan) == normalize(contributing_without_plan), (
        f"without-plan prompt drift between Makefile + CONTRIBUTING:\n"
        f"Makefile:     {normalize(makefile_without_plan)!r}\n"
        f"CONTRIBUTING: {normalize(contributing_without_plan)!r}"
    )


def test_tier1_prompt_macro_empty_string_equivalent_to_none():
    """PR #5 Codex Tier-2 lesson: empty-string plan_file must trigger the
    same unbound prompt as None (not the with-plan branch with literal
    empty path)."""
    env = render.build_env("python")
    # Render the macro directly via a tiny test template that imports it
    test_tmpl_source = (
        "{% from 'Makefile.review.tmpl' import tier1_prompt %}"
        "NONE:{{ tier1_prompt('HEAD') }}\n"
        "EMPTY:{{ tier1_prompt('HEAD', '') }}\n"
        "BOUND:{{ tier1_prompt('HEAD', 'docs/plans/x.md') }}\n"
    )
    rendered = env.from_string(test_tmpl_source).render()
    none_line = rendered.split("\n")[0].removeprefix("NONE:")
    empty_line = rendered.split("\n")[1].removeprefix("EMPTY:")
    bound_line = rendered.split("\n")[2].removeprefix("BOUND:")
    assert none_line == empty_line, (
        f"None and '' should produce identical prompts (unbound branch);\n"
        f"None:  {none_line!r}\nEmpty: {empty_line!r}"
    )
    assert none_line != bound_line, "bound prompt should differ from unbound"
    assert "No plan binding" in none_line, "unbound prompt should contain canonical phrase"
    assert "docs/plans/x.md" in bound_line, "bound prompt should mention the plan file path"


def test_tier1_prompt_has_no_backticks_or_shell_metachars():
    """PR #5 Tier-2 lesson: prompt must not contain backticks or `$(` —
    those trigger shell command substitution when the rendered prompt is
    passed as a double-quoted shell arg."""
    env = render.build_env("python")
    test_tmpl_source = (
        "{% from 'Makefile.review.tmpl' import tier1_prompt %}"
        "{{ tier1_prompt('HEAD') }}\n"
        "{{ tier1_prompt('HEAD', 'docs/plans/x.md') }}\n"
    )
    rendered = env.from_string(test_tmpl_source).render()
    assert "`" not in rendered, (
        "Tier-1 prompt must not contain backticks (shell-substitution class); "
        "PR #5 iter-5 fold required plain text only"
    )
    assert "$(" not in rendered, (
        "Tier-1 prompt must not contain `$(` (shell-substitution); "
        "the only $(...) allowed is the Make-level $(PLAN_FILE) in the recipe wrapper, "
        "NOT in the macro-rendered prompt body"
    )


def test_simplify_pass_has_gating_wording():
    """PR #5c Bucket F test (d): `/simplify` sub-bullet must gate the step
    for Claude-Code-only sessions — substrings 'Claude Code' + 'skip' +
    'optional' present in both rendered template AND skill-repo dogfood
    CONTRIBUTING.md. Closes Tier-1 P1 (Codex caught this in self-review:
    plan required the assertion but it was missed in initial commit)."""
    rendered = _render("CONTRIBUTING.md.tmpl", _context())
    # Extract the /simplify bullet line (and a few surrounding chars for safety)
    idx = rendered.index("/simplify")
    line_start = rendered.rfind("\n", 0, idx)
    # Read forward to end of bullet (next bullet or blank line)
    line_end = rendered.index("\n", idx + 1)
    simplify_line = rendered[line_start:line_end]
    for needle in ("Claude Code", "skip", "optional"):
        assert needle.lower() in simplify_line.lower(), (
            f"/simplify rendered template missing gating substring {needle!r}: {simplify_line!r}"
        )

    # Same check on dogfood
    from pathlib import Path as _P

    SKILL_ROOT = _P(__file__).resolve().parent.parent
    dogfood = (SKILL_ROOT / "CONTRIBUTING.md").read_text()
    idx_d = dogfood.index("/simplify")
    line_start_d = dogfood.rfind("\n", 0, idx_d)
    line_end_d = dogfood.index("\n", idx_d + 1)
    dogfood_line = dogfood[line_start_d:line_end_d]
    for needle in ("Claude Code", "skip", "optional"):
        assert needle.lower() in dogfood_line.lower(), (
            f"/simplify dogfood CONTRIBUTING.md missing gating substring {needle!r}: "
            f"{dogfood_line!r}"
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


# ──────────────────────────────────────────────────────────────────────
# package_manager branching in shared templates (PR #6 Bucket C)
# ──────────────────────────────────────────────────────────────────────


def test_shared_claude_md_uv_branch_renders_uv_specific_content():
    """uv-mode CLAUDE.md.tmpl renders uv-specific Python-version + Commands content.

    Closes Codex iter-4 #3 + iter-6 #4: shared docs must not have pip-era
    wording dangling in uv-rendered output.
    """
    rendered = _render("CLAUDE.md.tmpl", _context(package_manager="uv"))
    # uv-specific content present:
    assert "Install dev deps via uv sync" in rendered  # Commands table
    assert "uv run python" in rendered  # Python-version section
    assert "`.python-version`" in rendered  # Python-version section
    # pip-era wording absent:
    assert "Install dev deps into venv" not in rendered
    assert "./venv/bin/python" not in rendered
    assert "python -m venv" not in rendered
    assert "per-project `venv/`" not in rendered


def test_shared_claude_md_pip_branch_renders_pip_content_unchanged():
    """pip-mode CLAUDE.md.tmpl renders the pre-PR-#6 pip content (no drift)."""
    rendered = _render("CLAUDE.md.tmpl", _context(package_manager="pip"))
    assert "Install dev deps into venv" in rendered
    assert "./venv/bin/python" in rendered
    assert "per-project `venv/`" in rendered
    # And NOT the uv branch:
    assert "uv run python" not in rendered
    assert "Install dev deps via uv sync" not in rendered


def test_shared_claude_md_commands_table_uses_make_in_both_modes():
    """The Commands table uses `make X` identically across modes — only the
    row's *description* differs (uv: 'Install dev deps via uv sync' vs pip:
    'Install dev deps into venv'). The user's muscle memory stays the same."""
    for pm in ["uv", "pip"]:
        rendered = _render("CLAUDE.md.tmpl", _context(package_manager=pm))
        # Commands table rows mention `make install` (same in both)
        assert "`make install`" in rendered, f"pm={pm}"
        assert "`make test`" in rendered, f"pm={pm}"
        assert "`make lint`" in rendered, f"pm={pm}"
        assert "`make install-hooks`" in rendered, f"pm={pm}"


def test_shared_claude_md_missing_package_manager_key_renders_pip_mode():
    """Closes Codex iter-5 #1: `render.py:79` uses `StrictUndefined`. Existing
    test contexts construct context dicts manually without `package_manager`.
    The shared templates' `|default("pip")` filter must handle the missing
    key gracefully (NO `UndefinedError`) and render pip-mode equivalent.
    """
    ctx = _context()  # no package_manager key
    assert "package_manager" not in ctx
    # Must not raise UndefinedError:
    rendered = _render("CLAUDE.md.tmpl", ctx)
    # Pip-mode equivalent output:
    assert "Install dev deps into venv" in rendered
    assert "uv run python" not in rendered
    assert "Install dev deps via uv sync" not in rendered


def test_shared_contributing_md_uv_branch_includes_install_uv_prerequisite():
    """uv-mode CONTRIBUTING.md.tmpl one-time-setup section adds the
    'First install uv' prerequisite (brew / curl / pipx)."""
    rendered = _render("CONTRIBUTING.md.tmpl", _context(package_manager="uv"))
    assert "First, install `uv`" in rendered
    assert "brew install uv" in rendered
    assert "astral.sh/uv/install.sh" in rendered
    assert "pipx install uv" in rendered
    # And the make-install comment is uv-specific:
    assert "uv sync" in rendered
    # pip-era "creates venv if missing" NOT in uv-rendered output:
    assert "creates venv if missing" not in rendered


def test_shared_contributing_md_pip_branch_unchanged():
    """pip-mode CONTRIBUTING.md.tmpl one-time-setup section keeps current
    'creates venv if missing' wording; no uv prerequisite."""
    rendered = _render("CONTRIBUTING.md.tmpl", _context(package_manager="pip"))
    assert "creates venv if missing" in rendered
    assert "First, install `uv`" not in rendered
    assert "brew install uv" not in rendered


def test_shared_contributing_md_missing_package_manager_key_renders_pip_mode():
    """Same StrictUndefined safety check for CONTRIBUTING.md."""
    ctx = _context()
    assert "package_manager" not in ctx
    rendered = _render("CONTRIBUTING.md.tmpl", ctx)
    assert "creates venv if missing" in rendered
    assert "First, install `uv`" not in rendered


def test_shared_claude_md_non_python_languages_unaffected_by_package_manager():
    """`package_manager` branching is gated inside `{% if language == 'python' %}`
    — Node and Go renders must not show any uv/pip-specific content. Test ALL
    three pm settings (uv, pip, missing-key) for non-python languages to catch
    a future regression where someone hoists `package_manager`-conditional
    outside the language guard. Closes Tier-1 F1 (one-sided coverage)."""
    for lang in ["nodejs", "go"]:
        for pm_kwargs in [
            {"package_manager": "uv"},
            {"package_manager": "pip"},
            {},  # missing-key (StrictUndefined safety check)
        ]:
            ctx = _context(language=lang, **pm_kwargs)
            # Must not raise UndefinedError even with missing key:
            rendered = _render("CLAUDE.md.tmpl", ctx)
            # uv-mode python wording must NOT leak into non-python renders:
            assert "Install dev deps via uv sync" not in rendered, f"language={lang} pm={pm_kwargs}"
            assert "uv run python" not in rendered, f"language={lang} pm={pm_kwargs}"
            # pip-mode python wording must NOT leak either:
            assert "Install dev deps into venv" not in rendered, f"language={lang} pm={pm_kwargs}"
