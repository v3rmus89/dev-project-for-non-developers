"""Per-template render checks for shared/.

- StrictUndefined render success (Codex iter-11 finding #1)
- yaml parses
- No-private-domain-term scan (Codex iter-4 finding #3). The FORBIDDEN_TERMS
  literals are the real origin-project terms on purpose: they are the detector.
- Triage-rule presence in CLAUDE.md / AGENTS.md / docs-plans-README
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from bootstrap_lib import render

SKILL_ROOT = Path(__file__).resolve().parent.parent

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
]


@pytest.mark.parametrize("tmpl", SHARED_TEMPLATES_TO_SCAN)
def test_shared_template_renders_without_undefined_error(tmpl):
    rendered = _render(tmpl, _context())
    assert rendered, f"{tmpl} rendered empty"


@pytest.mark.parametrize("tmpl", SHARED_TEMPLATES_TO_SCAN)
def test_no_private_domain_terms_in_shared_templates(tmpl):
    rendered = _render(tmpl, _context())
    lower = rendered.lower()
    for term in FORBIDDEN_TERMS:
        assert not re.search(term, lower, re.IGNORECASE), f"forbidden term {term!r} found in {tmpl}"
    for literal in FORBIDDEN_LITERAL:
        # Allow `bot/` only inside legit URLs (none expected in our templates)
        assert literal not in lower, f"forbidden literal {literal!r} in {tmpl}"


@pytest.mark.parametrize("rel_out,src_rel", sorted(render.SHARED_VERBATIM_MAP.items()))
def test_no_private_domain_terms_in_verbatim_sources(rel_out, src_rel):
    """Tier-2 fold (PR #50 FN2): dropping the six scripts from
    SHARED_TEMPLATES_TO_SCAN removed the only genericity scan of their
    CONTENT — byte-equality guards drift, not project-specific leakage.
    Scan every verbatim source with the same forbidden-terms list the
    rendered templates get, so a future paste into a shipped script (or a
    Bucket B prompt file) fails loud."""
    text = (render.SKILL_ROOT / src_rel).read_text(encoding="utf-8").lower()
    for term in FORBIDDEN_TERMS:
        assert not re.search(term, text, re.IGNORECASE), (
            f"forbidden term {term!r} in verbatim source {src_rel}"
        )
    for literal in FORBIDDEN_LITERAL:
        assert literal not in text, f"forbidden literal {literal!r} in {src_rel}"


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


# ──────────────────────────────────────────────────────────────────────
# prompts/ files + render-review-prompt.py wiring (pre-expansion Bucket B).
# The five prompt texts left the Makefile recipes for prompts/*.txt; the
# recipes build PROMPT at runtime via scripts/render-review-prompt.py. These
# tests replace the retired tier1_prompt-macro tests:
#   - macro byte-identity across Makefile/CONTRIBUTING → single-source files
#     + test_contributing_references_prompt_files (no second copy exists);
#   - macro empty-string-equals-None → the recipe's `[ -n "$(PLAN_FILE)" ]`
#     branch, covered by the argv shim tests in test_makefile_review_targets;
#   - macro no-backticks shell-safety → test_prompt_files_are_shell_safe
#     over ALL five files (LESSONS.md 2026-06-09: cover EVERY prompt).
# ──────────────────────────────────────────────────────────────────────

# Registry tokens (mirrors scripts/render-review-prompt.py TOKEN_REGISTRY)
# each prompt file is allowed to carry — and the exact set each recipe must
# provide inside its command-substitution env prefix.
PROMPT_FILE_TOKENS = {
    "prompts/plan-review.txt": {"PLAN_FILE", "ITERATION", "KEY"},
    "prompts/commit-review-plan-bound.txt": {"COMMIT_REF", "PLAN_FILE"},
    "prompts/commit-review-unbound.txt": {"COMMIT_REF"},
    "prompts/plan-consistency.txt": {"PLAN_FILE"},
    "prompts/fact-check-interpret.txt": {"PLAN_FILE", "VERIFICATION_JSON"},
}

_TOKEN_REGISTRY = ("PLAN_FILE", "ITERATION", "KEY", "COMMIT_REF", "VERIFICATION_JSON")

# Which prompt file(s) each review recipe must build its PROMPT from. The
# commit targets carry two branches (plan-bound + unbound).
RECIPE_PROMPT_FILES = {
    "review-plan-by-codex": ["prompts/plan-review.txt"],
    "review-plan-by-claude": ["prompts/plan-review.txt"],
    "review-commit-by-codex": [
        "prompts/commit-review-plan-bound.txt",
        "prompts/commit-review-unbound.txt",
    ],
    "review-commit-by-claude": [
        "prompts/commit-review-plan-bound.txt",
        "prompts/commit-review-unbound.txt",
    ],
    "review-plan-consistency-by-claude": ["prompts/plan-consistency.txt"],
    "review-plan-fact-check-by-codex": ["prompts/fact-check-interpret.txt"],
    "review-plan-fact-check-by-claude": ["prompts/fact-check-interpret.txt"],
}

# The two recipe surfaces that must stay in lockstep (also byte-locked by
# tests/test_selftest_overlap.py; asserting both keeps THESE tests meaningful
# even if that lock is ever loosened).
_RECIPE_SURFACES = ["Makefile", "shared/Makefile.review.tmpl"]

# Lead phrases shared by the five prompt texts — after Bucket B none may
# remain INLINE in a recipe surface (iter-2 FN2: the narrow "no `Review …`
# form would miss a partial extraction of the consistency/fact-check texts).
_PROMPT_LEAD_PHRASES = [
    "Review the plan file",
    "Review commit HEAD",
    "Read the plan file",
    "Interpret these fact-check",
]


def _prompt_text(rel_path):
    return (SKILL_ROOT / rel_path).read_text(encoding="utf-8")


def _recipe_lines_invoking_helper(surface_text):
    return [line for line in surface_text.splitlines() if "render-review-prompt.py" in line]


@pytest.mark.parametrize("rel_path,expected_tokens", sorted(PROMPT_FILE_TOKENS.items()))
def test_prompt_file_exists_nonempty_with_exact_token_set(rel_path, expected_tokens):
    """Each prompt file exists, is non-empty, and carries EXACTLY the registry
    tokens its recipes provide — a missing token silently un-parameterizes the
    prompt; an extra one makes the fail-loud helper exit 2 on every run."""
    path = SKILL_ROOT / rel_path
    assert path.is_file(), f"{rel_path} missing"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"{rel_path} is empty"
    found = {m for m in re.findall(r"\{([A-Z_]+)\}", text) if m in _TOKEN_REGISTRY}
    assert found == expected_tokens, (
        f"{rel_path}: registry tokens {sorted(found)} != expected {sorted(expected_tokens)}"
    )


@pytest.mark.parametrize("rel_path", sorted(PROMPT_FILE_TOKENS))
def test_prompt_files_are_shell_safe(rel_path):
    """Every prompt file must stay shell-safe (LESSONS.md 2026-06-09, extended
    to ALL prompts): the resolved prompt is passed as a double-quoted shell
    arg, so no backticks, no `$(`, no literal double-quote. Command
    substitution makes these inert at runtime — this guards the source texts
    so a future edit cannot reintroduce the hazard class."""
    text = _prompt_text(rel_path)
    assert "`" not in text, f"{rel_path} contains a backtick"
    assert "$(" not in text, f"{rel_path} contains shell-substitution `$(`"
    assert '"' not in text, f"{rel_path} contains a literal double-quote"


@pytest.mark.parametrize("surface", _RECIPE_SURFACES)
def test_review_recipes_invoke_helper_with_exact_prompt_files(surface):
    """Each review target builds PROMPT from its exact prompt file via
    scripts/render-review-prompt.py (test-surgery item (b): recipe side)."""
    text = (SKILL_ROOT / surface).read_text(encoding="utf-8")
    for target, files in RECIPE_PROMPT_FILES.items():
        start = text.index(f"\n{target}:")
        # Recipe block ends at the next top-level target definition.
        next_defs = [
            m.start() for m in re.finditer(r"\n[A-Za-z][A-Za-z0-9_-]*:", text) if m.start() > start
        ]
        block = text[start : next_defs[0] if next_defs else len(text)]
        for rel_path in files:
            needle = f"$(CURDIR)/scripts/render-review-prompt.py $(CURDIR)/{rel_path})"
            assert needle in block, f"{surface}: {target} does not build PROMPT from {rel_path}"


@pytest.mark.parametrize("surface", _RECIPE_SURFACES)
def test_no_inline_prompt_lead_phrases_remain(surface):
    """No prompt text remains inline in a recipe surface — all four lead
    phrases shared by the five extracted texts are gone (iter-2 FN2)."""
    text = (SKILL_ROOT / surface).read_text(encoding="utf-8")
    for phrase in _PROMPT_LEAD_PHRASES:
        assert phrase not in text, f"{surface}: inline prompt text {phrase!r} still present"


@pytest.mark.parametrize("surface", _RECIPE_SURFACES)
def test_every_helper_call_carries_fail_loud_guard(surface):
    """Tier-2 codex P2: make's default shell has no -e and recipes are
    `;`-chained, so an unguarded `PROMPT="$$(helper …)"` would swallow the
    helper's exit-2 and invoke the CLI with an empty prompt. Every helper
    call must guard the substitution with `|| exit $$?` on the same line."""
    text = (SKILL_ROOT / surface).read_text(encoding="utf-8")
    lines = _recipe_lines_invoking_helper(text)
    # 9 call sites: 2 plan-review + 4 commit branches + 1 consistency + 2 fact-check
    assert len(lines) == 9, f"{surface}: expected 9 helper call sites, found {len(lines)}"
    for line in lines:
        assert "|| exit $$?" in line, f"{surface}: unguarded helper call: {line.strip()[:120]}"


@pytest.mark.parametrize("surface", _RECIPE_SURFACES)
def test_recipes_provide_every_token_their_prompt_file_needs(surface):
    """Placeholder-drift lock (risk table row 2): for each helper call, every
    registry token the referenced prompt file carries is provided INSIDE the
    command substitution (env `TOKEN=` or file-backed `TOKEN_FILE=`) — a
    same-line prefix outside the substitution never reaches the helper
    (Tier-2 codex P1)."""
    text = (SKILL_ROOT / surface).read_text(encoding="utf-8")
    lines = _recipe_lines_invoking_helper(text)
    assert lines, f"{surface}: no helper call sites found"
    for line in lines:
        m = re.search(r"render-review-prompt\.py \$\(CURDIR\)/(prompts/[a-z-]+\.txt)\)", line)
        assert m, f"{surface}: cannot parse prompt file from: {line.strip()[:120]}"
        rel_path = m.group(1)
        substitution = line[line.index('"$$(') : line.index(')" || exit')]
        for token in PROMPT_FILE_TOKENS[rel_path]:
            assert f'{token}="' in substitution or f'{token}_FILE="' in substitution, (
                f"{surface}: {rel_path} needs {{{token}}} but the substitution does not "
                f"provide {token}= or {token}_FILE=: {line.strip()[:160]}"
            )


def test_plan_review_prompt_contains_cross_section_instruction():
    """PR #4 idea-(a), retargeted from the rendered recipe to the prompt file:
    the plan-review prompt must include the 'where else in the plan'
    cross-section impact instruction."""
    text = _prompt_text("prompts/plan-review.txt")
    assert "OTHER sections of the same plan" in text, "idea-(a) prompt extension missing"


def test_plan_review_prompt_contains_calibration_and_json_fence_contract():
    """Test-surgery item (c): calibration wording + the machine-readable JSON
    footer contract, retargeted from rendered recipe strings to the file."""
    text = _prompt_text("prompts/plan-review.txt")
    assert "Calibrate importance strictly" in text, "imp-3 calibration sentence missing"
    assert "append a json code fence" in text, "JSON-fence footer contract missing"
    assert "key: '{KEY}'" in text, "JSON footer must carry the {KEY} token"


def test_simplify_merged_into_tier1_focus():
    """AD7 (user request 2026-07-05): the dormant optional `/simplify` pass is
    merged into Tier-1 — both commit-review prompt files carry the
    simplification focus item, and CONTRIBUTING's sub-bullet shrank to the
    one-liner (simplification is part of Tier-1's focus; `/simplify` stays an
    optional interactive extra). Replaces the retired gating-wording test."""
    for rel_path in (
        "prompts/commit-review-plan-bound.txt",
        "prompts/commit-review-unbound.txt",
    ):
        assert "reuse / dead code / cruft accumulated across fold rounds" in _prompt_text(
            rel_path
        ), f"{rel_path}: simplification focus item missing"

    rendered = _render("CONTRIBUTING.md.tmpl", _context())
    dogfood = (SKILL_ROOT / "CONTRIBUTING.md").read_text()
    for surface_name, text in (("rendered", rendered), ("dogfood", dogfood)):
        idx = text.index("/simplify")
        line = text[text.rfind("\n", 0, idx) : text.index("\n", idx + 1)]
        assert "part of Tier-1's focus" in line, (
            f"{surface_name} CONTRIBUTING /simplify bullet must say Tier-1 covers it: {line!r}"
        )
        assert "optional interactive extra" in line, (
            f"{surface_name} CONTRIBUTING /simplify bullet must keep the optional-extra note"
        )
        # The old gating machinery (>200 lines / multi-commit conditions) is gone.
        assert ">200 lines" not in line, f"{surface_name}: old /simplify gating wording remains"


def test_contributing_references_prompt_files():
    """iter-1 FN4: CONTRIBUTING (template AND dogfood) documents BOTH manual
    subagent variants by pointing at the prompt files with their substitution
    sets — replaces the retired macro byte-identity test (single-source files
    make cross-surface drift structurally impossible; what remains testable is
    that the doc actually references them)."""
    rendered = _render("CONTRIBUTING.md.tmpl", _context())
    dogfood = (SKILL_ROOT / "CONTRIBUTING.md").read_text()
    for surface_name, text in (("rendered", rendered), ("dogfood", dogfood)):
        assert "prompts/commit-review-plan-bound.txt" in text, (
            f"{surface_name} CONTRIBUTING must reference the plan-bound prompt file"
        )
        assert "prompts/commit-review-unbound.txt" in text, (
            f"{surface_name} CONTRIBUTING must reference the unbound prompt file"
        )
        assert "{COMMIT_REF}" in text, (
            f"{surface_name} CONTRIBUTING must name the {{COMMIT_REF}} substitution"
        )
        assert "{PLAN_FILE}" in text, (
            f"{surface_name} CONTRIBUTING must name the {{PLAN_FILE}} substitution"
        )


def test_tier1_prompt_files_contain_key_phrases():
    """Retargeted from the recipe-block slice (Tier-2 codex P1): the prompt
    BODY phrases the old test pinned now live in the prompt files."""
    for rel_path in (
        "prompts/commit-review-plan-bound.txt",
        "prompts/commit-review-unbound.txt",
    ):
        text = _prompt_text(rel_path)
        for phrase in [
            "tests that pass for the wrong reason",
            "Tier-1",
            "plan-impl drift",
            "Do NOT edit files",
        ]:
            assert phrase in text, f"{rel_path} missing phrase: {phrase!r}"


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


def test_claude_review_workflow_pins_model():
    """PR #51 regression lock: the @beta action's built-in default model
    (claude-sonnet-4-20250514) retired 2026-06-15 and 404'd every Tier-2 run;
    the explicit `model` input on the Run Claude review step is the fix's
    load-bearing invariant. Byte-identity alone would still pass if BOTH the
    dogfood workflow and the template lost the pin together - this asserts
    the pin exists and names the intended model."""
    rendered = _render("claude-review.yml.tmpl", _context(github_review_mode="claude"))
    data = yaml.safe_load(rendered)
    steps = data["jobs"]["claude-review"]["steps"]
    step = next(s for s in steps if s.get("name") == "Run Claude review")
    assert step["with"]["model"] == "claude-sonnet-5"
