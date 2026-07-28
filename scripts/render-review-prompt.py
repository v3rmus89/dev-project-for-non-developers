#!/usr/bin/env python3
"""Render a review-prompt file by substituting known registry tokens.

Usage:
    render-review-prompt.py <prompt-file>

The Makefile review recipes (and scripts/ab_replay_lib.py, via import) build
their AI prompts from the prompts/*.txt files through this helper instead of
inlining the text in shell. Substitution is a KNOWN-TOKEN REGISTRY pass --
never str.format and never blind brace parsing: the prompt texts contain
literal JSON-fence braces (for example a '{verdict: ...}' example fence) that
must pass through untouched. Only the registry spellings below are ever
replaced; every other brace is inert data.

Each registry token found in the prompt file resolves, in order:
  1. environment variable NAME (an empty value counts as UNSET -- an unset
     make var expands to an empty string, and that drift must fail loud,
     not ship a silently broken prompt);
  2. the content of the file named by environment variable NAME_FILE, with
     trailing newlines stripped (mirrors what shell command substitution
     did when the recipes inlined the value) -- this is how the fact-check
     recipes pass the verification JSON;
  3. neither -> exit 2, naming the token.

Output is the substituted prompt on stdout. The recipes wrap the call in
PROMPT="$(...)" -- command-substitution output is never re-parsed as shell
syntax, so backticks / dollar-parens / quotes inside prompt files are inert
data (the LESSONS.md 2026-06-09 hazard class is structurally eliminated).

Exit codes:
    0 -- prompt rendered to stdout
    2 -- usage error, unreadable prompt file, or unresolved registry token
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

TOKEN_REGISTRY = (
    "PLAN_FILE",
    "ITERATION",
    "KEY",
    "COMMIT_REF",
    "VERIFICATION_JSON",
)

_TOKEN_RE = re.compile(r"\{(" + "|".join(TOKEN_REGISTRY) + r")\}")


class UnresolvedTokenError(Exception):
    """A registry token appears in the prompt but no value is available."""

    def __init__(self, token: str, reason: str):
        self.token = token
        super().__init__(reason)


def render_prompt(text: str, resolve) -> str:
    """Substitute registry tokens in a single pass over the original text.

    ``resolve(name)`` returns the replacement string for a registry token
    name, or raises UnresolvedTokenError. Every registry token present in
    ``text`` is resolved BEFORE any substitution happens (fail-loud precedes
    partial output), then replaced in one pass -- inserted values are never
    re-scanned, so a value that happens to contain a registry spelling
    cannot trigger a second substitution.
    """
    values = {}
    for name in sorted(set(_TOKEN_RE.findall(text))):
        values[name] = resolve(name)
    return _TOKEN_RE.sub(lambda m: values[m.group(1)], text)


def resolve_from_env(name: str, environ=os.environ) -> str:
    """Resolve one registry token from env NAME, else file at NAME_FILE."""
    value = environ.get(name)
    if value:
        return value
    file_var = name + "_FILE"
    file_path = environ.get(file_var)
    if file_path:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise UnresolvedTokenError(
                name, f"token {{{name}}}: cannot read {file_var}={file_path}: {exc}"
            ) from None
        return content.rstrip("\n")
    raise UnresolvedTokenError(
        name,
        f"unresolved token {{{name}}}: set environment variable {name} (non-empty) or {file_var}",
    )


def main(argv) -> int:
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    prompt_path = Path(argv[0])
    try:
        text = prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read prompt file {prompt_path}: {exc}", file=sys.stderr)
        return 2
    try:
        rendered = render_prompt(text, resolve_from_env)
    except UnresolvedTokenError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
