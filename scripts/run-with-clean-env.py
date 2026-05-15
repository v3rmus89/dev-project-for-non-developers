#!/usr/bin/env python3
"""Prefix-aware env-var scrubber for plan-review Makefile targets.

`make`'s built-in `env -u VAR` is exact-name-only. The bidirectional review
targets need to strip any env var starting with `CLAUDE_CODE_` or `CODEX_`
(plus a few Make-internal vars) to keep nested invocations clean. This
helper rebuilds os.environ minus the matching keys, then os.execvp's into
the requested command.

Usage:
    scripts/run-with-clean-env.py [--keep-claude-code] [--keep-codex] -- <cmd> <args...>
"""

from __future__ import annotations

import os
import sys

PREFIX_CLAUDE = "CLAUDE_CODE_"
PREFIX_CODEX = "CODEX_"
EXACT_DROP = {
    "MAKEFLAGS",
    "MAKELEVEL",
    "MAKEOVERRIDES",
    "MFLAGS",
    "PLAN_FILE",
    "ITERATION",
    "PLAN_REVIEW_OUT",
    "PLAN_REVIEW_OUT_CODEX",
    "PLAN_REVIEW_OUT_CLAUDE",
}


def _parse_args(argv: list[str]) -> tuple[bool, bool, list[str]]:
    keep_claude = False
    keep_codex = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--keep-claude-code":
            keep_claude = True
            i += 1
        elif arg == "--keep-codex":
            keep_codex = True
            i += 1
        elif arg == "--":
            return keep_claude, keep_codex, argv[i + 1 :]
        else:
            sys.stderr.write(
                f"run-with-clean-env: unknown arg or missing '--' separator: {arg!r}\n"
            )
            sys.exit(2)
    sys.stderr.write("run-with-clean-env: missing '--' separator before command\n")
    sys.exit(2)


def main(argv: list[str]) -> int:
    keep_claude, keep_codex, cmd = _parse_args(argv)
    if not cmd:
        sys.stderr.write("run-with-clean-env: no command after '--'\n")
        return 2

    new_env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in EXACT_DROP:
            continue
        if not keep_claude and key.startswith(PREFIX_CLAUDE):
            continue
        if not keep_codex and key.startswith(PREFIX_CODEX):
            continue
        new_env[key] = value

    os.execvpe(cmd[0], cmd, new_env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
