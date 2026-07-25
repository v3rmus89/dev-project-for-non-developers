"""Unit tests for scripts/render-review-prompt.py (pre-expansion Bucket B).

The helper is the single substitution ruleset for every prompt consumer (the
Makefile review recipes exec it; scripts/ab_replay_lib.py imports it). Two
halves:

  (i)  pure rules — known-token registry only, literal JSON-fence braces
       inert, single-pass substitution (inserted values never re-scanned),
       fail-loud on an unresolvable registry token;
  (ii) CLI contract — env NAME, else file at NAME_FILE (trailing newlines
       stripped, mirroring shell command substitution), else exit 2 naming
       the token; stdout carries the rendered prompt byte-for-byte.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
HELPER = SKILL_ROOT / "scripts" / "render-review-prompt.py"

_spec = importlib.util.spec_from_file_location("render_review_prompt", HELPER)
helper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helper)


# ── (i) pure substitution rules ────────────────────────────────────────────────


def test_registry_tokens_substituted():
    out = helper.render_prompt(
        "plan={PLAN_FILE} iter={ITERATION} key={KEY}",
        {"PLAN_FILE": "docs/p.md", "ITERATION": "2", "KEY": "abc"}.__getitem__,
    )
    assert out == "plan=docs/p.md iter=2 key=abc"


def test_non_registry_braces_are_inert():
    """The prompts carry literal JSON-fence braces — {verdict: …}, {3: N},
    lowercase names — none may be parsed or altered (the str.format hazard
    scripts/ab-replay.py:66 used to document)."""
    text = "x {verdict: needs-iter} {3: N, 2: N} {id: FN} {plan_file} {UNKNOWN_NAME} y"
    out = helper.render_prompt(text, lambda name: pytest.fail(f"resolved {name}"))
    assert out == text


def test_substitution_is_single_pass_over_original_text():
    """A VALUE containing a registry spelling must not be re-substituted."""
    out = helper.render_prompt(
        "a {PLAN_FILE} b {KEY} c",
        {"PLAN_FILE": "evil-{KEY}-value", "KEY": "k123"}.__getitem__,
    )
    assert out == "a evil-{KEY}-value b k123 c"


def test_unresolvable_registry_token_raises_before_any_output():
    with pytest.raises(helper.UnresolvedTokenError) as exc_info:
        helper.render_prompt(
            "{PLAN_FILE} {ITERATION}",
            lambda name: (_ for _ in ()).throw(
                helper.UnresolvedTokenError(name, f"no value for {name}")
            ),
        )
    assert exc_info.value.token in ("PLAN_FILE", "ITERATION")


def test_resolve_from_env_empty_value_counts_as_unset():
    """An unset make var expands to an empty string — that drift must fail
    loud, not silently ship a prompt with an empty path."""
    with pytest.raises(helper.UnresolvedTokenError):
        helper.resolve_from_env("PLAN_FILE", environ={"PLAN_FILE": ""})


def test_resolve_from_env_file_backed_value_strips_trailing_newlines(tmp_path):
    value_file = tmp_path / "verify.json"
    value_file.write_text('{"results": []}\n')
    got = helper.resolve_from_env(
        "VERIFICATION_JSON", environ={"VERIFICATION_JSON_FILE": str(value_file)}
    )
    assert got == '{"results": []}'


def test_resolve_from_env_prefers_direct_env_over_file(tmp_path):
    value_file = tmp_path / "v.txt"
    value_file.write_text("from-file")
    got = helper.resolve_from_env("KEY", environ={"KEY": "from-env", "KEY_FILE": str(value_file)})
    assert got == "from-env"


def test_resolve_from_env_unreadable_file_fails_loud(tmp_path):
    with pytest.raises(helper.UnresolvedTokenError):
        helper.resolve_from_env(
            "VERIFICATION_JSON",
            environ={"VERIFICATION_JSON_FILE": str(tmp_path / "missing.json")},
        )


# ── (ii) CLI contract (subprocess, real exec bit) ──────────────────────────────


def _run_helper(prompt_file, env_extra):
    import os

    env = os.environ.copy()
    # Scrub registry names so an exported PLAN_FILE etc. in the developer's
    # shell cannot leak into the fail-loud assertions.
    for name in helper.TOKEN_REGISTRY:
        env.pop(name, None)
        env.pop(name + "_FILE", None)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HELPER), str(prompt_file)],
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_renders_to_stdout(tmp_path):
    prompt_file = tmp_path / "p.txt"
    prompt_file.write_text("review {PLAN_FILE} at iter {ITERATION} {verdict: x}\n")
    result = _run_helper(prompt_file, {"PLAN_FILE": "docs/a.md", "ITERATION": "3"})
    assert result.returncode == 0, result.stderr
    assert result.stdout == "review docs/a.md at iter 3 {verdict: x}\n"


def test_cli_exit_2_names_missing_token(tmp_path):
    prompt_file = tmp_path / "p.txt"
    prompt_file.write_text("needs {KEY}\n")
    result = _run_helper(prompt_file, {})
    assert result.returncode == 2
    assert "{KEY}" in result.stderr, f"stderr must name the token: {result.stderr!r}"
    assert result.stdout == "", "no partial output on failure"


def test_cli_exit_2_on_missing_prompt_file(tmp_path):
    result = _run_helper(tmp_path / "nope.txt", {})
    assert result.returncode == 2
    assert "nope.txt" in result.stderr


def test_cli_file_backed_token_end_to_end(tmp_path):
    prompt_file = tmp_path / "p.txt"
    prompt_file.write_text("JSON: {VERIFICATION_JSON}\n")
    value_file = tmp_path / "verify.json"
    value_file.write_text('{"ok": true}\n')
    result = _run_helper(prompt_file, {"VERIFICATION_JSON_FILE": str(value_file)})
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'JSON: {"ok": true}\n'


def test_helper_runs_via_exec_bit_like_the_recipes(tmp_path):
    """The recipes exec $(CURDIR)/scripts/render-review-prompt.py directly —
    prove the committed file's shebang + exec bit work without an explicit
    interpreter (the repo-level half of the dual exec-bit requirement)."""
    prompt_file = tmp_path / "p.txt"
    prompt_file.write_text("ref {COMMIT_REF}\n")
    import os

    env = os.environ.copy()
    env["COMMIT_REF"] = "HEAD"
    result = subprocess.run(
        [str(HELPER), str(prompt_file)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ref HEAD\n"


# ── real prompt files render under the real recipes' token sets ────────────────


@pytest.mark.parametrize(
    "rel_path,tokens",
    [
        ("prompts/plan-review.txt", {"PLAN_FILE": "d/p.md", "ITERATION": "1", "KEY": "a" * 12}),
        ("prompts/commit-review-plan-bound.txt", {"COMMIT_REF": "HEAD", "PLAN_FILE": "d/p.md"}),
        ("prompts/commit-review-unbound.txt", {"COMMIT_REF": "HEAD"}),
        ("prompts/plan-consistency.txt", {"PLAN_FILE": "d/p.md"}),
        ("prompts/fact-check-interpret.txt", {"PLAN_FILE": "d/p.md", "VERIFICATION_JSON": "{}"}),
    ],
)
def test_each_real_prompt_file_renders_with_its_recipe_token_set(rel_path, tokens):
    """Every committed prompt file must render cleanly given exactly the token
    set its recipe provides — no unresolved-registry-token failure, no
    registry spelling left in the output."""
    text = (SKILL_ROOT / rel_path).read_text(encoding="utf-8")
    out = helper.render_prompt(text, tokens.__getitem__)
    for name in helper.TOKEN_REGISTRY:
        assert ("{" + name + "}") not in out, f"{rel_path}: {{{name}}} left unresolved"
