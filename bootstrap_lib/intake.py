"""Interactive intake — a guided greenfield setup flow for the bootstrap skill.

`run_intake()` asks a non-coder a sequence of plain questions, runs a
greenfield check on the chosen output directory, prints a plain-language
summary, and returns an argv list that `cli.main()` re-parses through the
normal parser (or `None` if the user cancels). It is a thin front-end — it
never writes files itself.

Greenfield-only: a target folder that already holds a project (a file the
skill would write, or any recognised project manifest in any language) is
routed to adopt-mode rather than scaffolded over.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bootstrap_lib import _flags, render, stack_suggest


class IntakeAborted(Exception):
    """Raised when stdin hits EOF mid-flow (Ctrl-D, or an exhausted pipe)."""


# Project-manifest filenames that mark an *existing* project. Scanned regardless
# of the language chosen in intake — a Python `pyproject.toml` in a folder the
# user is trying to bootstrap as nodejs still means "existing project". Matched
# as files (a directory named `package.json` must not false-positive).
_MANIFEST_FILES = ("pyproject.toml", "setup.py", "uv.lock", "package.json", "go.mod")
_MANIFEST_GLOBS = ("requirements*.txt",)


def _readline(stdin) -> str:
    """Read one line from `stdin`. A truly empty return ("") is EOF —
    Ctrl-D or an exhausted pipe — and raises `IntakeAborted`. A blank line
    the user typed comes back as "\\n" and returns "" after stripping."""
    line = stdin.readline()
    if line == "":
        raise IntakeAborted()
    return line.strip()


def _ask_text(stdin, stdout, prompt: str) -> str:
    """Ask a free-text question; return the stripped answer (may be empty)."""
    stdout.write(prompt)
    stdout.flush()
    return _readline(stdin)


def _ask_required(stdin, stdout, prompt: str) -> str:
    """Ask a required free-text question; re-prompt until the answer is
    non-empty (these answers have no default — see `--out`, which does)."""
    while True:
        answer = _ask_text(stdin, stdout, prompt)
        if answer:
            return answer
        stdout.write("  (this can't be empty — please enter a value)\n")


def _ask_menu(stdin, stdout, prompt: str, choices: list[str], default: str | None = None) -> str:
    """Ask a numbered-menu question. Accepts the 1-based number OR the literal
    value; re-displays and re-asks on anything else (an out-of-range number,
    non-numeric text). A non-coder typing `5` or `python` instead of `1` must
    not crash or pass a silently-wrong value.

    When `default` is set (PR #9 — a pre-filled stack suggestion), a blank
    line accepts `default`. `default` must be one of `choices` — a fail-loud
    guard so a `stack_suggest` ↔ `_flags.LANGUAGES` drift surfaces here, not
    silently downstream. When `default` is `None` the behaviour is
    byte-identical to PR #8: a blank line re-prompts."""
    if default is not None and default not in choices:
        raise ValueError(f"_ask_menu default {default!r} is not in choices {choices!r}")
    while True:
        answer = _ask_text(stdin, stdout, prompt)
        if default is not None and answer == "":
            return default
        if answer in choices:
            return answer
        if answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        stdout.write("  (please enter a number from the list)\n")


def _language_menu_prompt(default: str | None) -> str:
    """Render the language-menu prompt string. With `default` set (a stack
    suggestion from the brief), the matching row gets a `← recommended`
    marker and the Choose line names the default. With `default` `None` the
    output is byte-identical to PR #8's hardcoded language prompt."""
    lines = ["Language:"]
    for i, language in enumerate(_flags.LANGUAGES, start=1):
        marker = "  ← recommended" if language == default else ""
        lines.append(f"  {i}) {language}{marker}")
    n = len(_flags.LANGUAGES)
    if default is not None:
        # Square-bracket `[default: …]` matches the output-dir prompt's style
        # so a non-coder sees one consistent "default" convention.
        lines.append(f"Choose [1-{n}] [default: {default}]: ")
    else:
        lines.append(f"Choose [1-{n}]: ")
    return "\n".join(lines)


def _ask_project_name(stdin, stdout) -> str:
    """Ask for the project name; re-ask until it matches the slug pattern."""
    while True:
        name = _ask_text(stdin, stdout, "Project name (lowercase, e.g. my-project): ")
        if name and _flags.PROJECT_NAME_RE.match(name):
            return name
        stdout.write(
            "  (must be lowercase letters, digits and dashes, starting with a "
            "letter — e.g. my-project)\n"
        )


def _planned_file_collision(
    out_path: Path, language, github_review, enable_smoke, package_manager
) -> bool:
    """True if any file the skill would write for this config already exists
    under `out_path`."""
    for rel in render.planned_paths(language, github_review, enable_smoke, package_manager):
        if (out_path / rel).exists():
            return True
    return False


def _existing_project_signal(out_path: Path) -> bool:
    """True if `out_path` already holds a recognised project manifest, in any
    supported language — the language-agnostic half of the greenfield check."""
    for name in _MANIFEST_FILES:
        if (out_path / name).is_file():
            return True
    if out_path.is_dir():
        for pattern in _MANIFEST_GLOBS:
            if any(p.is_file() for p in out_path.glob(pattern)):
                return True
    return False


def run_intake(stdin=None, stdout=None) -> list[str] | None:
    """Guided greenfield setup. Returns an argv list (ending `--apply`) on
    confirm, or `None` when the user chooses 'cancel'. Raises `IntakeAborted`
    on EOF. `stdin`/`stdout` default to `None` and are resolved to
    `sys.stdin`/`sys.stdout` here (not bound at import time)."""
    if stdin is None:
        stdin = sys.stdin
    if stdout is None:
        stdout = sys.stdout

    stdout.write("dev-project-setup — interactive setup\n")
    stdout.write("A few questions to bootstrap a new project. Press Ctrl-C to cancel.\n\n")

    project_name = _ask_project_name(stdin, stdout)

    # PR #9 — optional plain-English brief → a language suggestion that
    # pre-fills the language menu's default. Skipping (a blank line) or a
    # low-confidence brief leaves the language menu exactly as PR #8.
    brief = _ask_text(
        stdin,
        stdout,
        "Describe your project in a sentence or two, so I can suggest a "
        "language —\n  or just press Enter to skip: ",
    )
    suggestion = stack_suggest.suggest_stack(brief) if brief else None
    if suggestion is not None:
        stdout.write(
            "Based on that, I'd suggest "
            + suggestion.language
            + ": "
            + suggestion.rationale
            + ". You can still pick anything below.\n"
        )
    elif brief:
        stdout.write("I couldn't infer a language from that — pick below.\n")

    suggested_language = suggestion.language if suggestion is not None else None
    language = _ask_menu(
        stdin,
        stdout,
        _language_menu_prompt(suggested_language),
        _flags.LANGUAGES,
        default=suggested_language,
    )

    package_manager = None
    if language == "python":
        package_manager = _ask_menu(
            stdin,
            stdout,
            "Package manager:\n  1) uv (recommended)\n  2) pip\nChoose [1-2]: ",
            _flags.PACKAGE_MANAGERS,
        )

    github_review = _ask_menu(
        stdin,
        stdout,
        "GitHub auto-review:\n  1) none\n  2) claude\n  3) both-docs\n"
        "  (claude/both-docs need a GitHub repo + a one-time token/secret — "
        "the apply output prints the exact steps)\nChoose [1-3]: ",
        _flags.GITHUB_REVIEW_MODES,
    )

    github_owner = github_repo = None
    if github_review != "none":
        github_owner = _ask_required(stdin, stdout, "GitHub owner: ")
        github_repo = _ask_required(stdin, stdout, "GitHub repo: ")

    enable_smoke = (
        _ask_menu(
            stdin,
            stdout,
            "Add a smoke-test doc skeleton (docs/SMOKE.md)?\n  1) no\n  2) yes\nChoose [1-2]: ",
            ["no", "yes"],
        )
        == "yes"
    )

    # Output directory — asked last so the greenfield check (which follows
    # immediately) re-asks this exact question on a collision.
    default_out = "../" + project_name
    out = default_out
    while True:
        answer = _ask_text(
            stdin,
            stdout,
            "Output directory — a path for the new project folder (it will be "
            "created).\n  [default: " + default_out + "]: ",
        )
        out = answer or default_out
        out_path = Path(out)
        collision = _planned_file_collision(
            out_path, language, github_review, enable_smoke, package_manager
        )
        existing = _existing_project_signal(out_path)
        if not collision and not existing:
            break
        stdout.write(
            "\n  '" + out + "' already contains a project — the interactive "
            "setup only handles new projects.\n"
        )
        if language == "python":
            stdout.write(
                "  To add the workflow to an existing project, use adopt-mode:\n"
                "    bootstrap.py --apply --mode=adopt --language python "
                "--project-name " + project_name + " --out " + out + "\n"
            )
        else:
            stdout.write(
                "  Adoption for " + language + " projects is a planned "
                "follow-up; for now the guided setup handles new projects only.\n"
            )
        stdout.write("  Pick a different (new) folder, or press Ctrl-C to cancel.\n\n")

    # Confirm gate.
    summary = (
        "\nThis will bootstrap a new "
        + language
        + " project named '"
        + project_name
        + "' into '"
        + out
        + "'"
    )
    if github_review != "none":
        summary += ", with " + github_review + " GitHub review"
    summary += ".\n"
    stdout.write(summary)
    if github_review != "none":
        stdout.write(
            "Note: GitHub review needs a GitHub repo and a one-time "
            "token/secret — the apply output will print the exact steps.\n"
        )
    stdout.write("Any files already in that folder are left untouched.\n")

    choice = _ask_menu(
        stdin, stdout, "  1) apply\n  2) cancel\nChoose [1-2]: ", ["apply", "cancel"]
    )
    if choice == "cancel":
        stdout.write("cancelled\n")
        return None

    argv = [
        "--language",
        language,
        "--project-name",
        project_name,
        "--out",
        out,
        "--github-review",
        github_review,
    ]
    if package_manager is not None:
        argv += ["--package-manager", package_manager]
    if github_owner is not None:
        argv += ["--github-owner", github_owner, "--github-repo", github_repo]
    if enable_smoke:
        argv += ["--enable-smoke"]
    argv += ["--apply"]
    return argv
