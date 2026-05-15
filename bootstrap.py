#!/usr/bin/env python3
# Shim — MUST be Python 3.6 compatible. The version-check fires BEFORE
# bootstrap_lib's 3.12-syntax modules are imported, so this file cannot use
# walrus operators, match statements, or `str | None` union syntax.

from __future__ import print_function

import os
import sys


def _skill_root():
    return os.path.dirname(os.path.abspath(__file__))


def _print_help_and_exit():
    # The --help path must not touch jinja2 — closes Codex iter-12 finding #4.
    # Shim and full CLI consume the same flag-definition module
    # (bootstrap_lib/_flags.py) so help output stays byte-equal — closes
    # Codex iter-16 finding #2.
    import argparse

    from bootstrap_lib._flags import add_flags

    parser = argparse.ArgumentParser(
        prog="bootstrap.py",
        description=("dev-project-setup skill — bootstrap a dev workflow into a target project."),
    )
    add_flags(parser)
    parser.parse_args(["--help"])  # argparse prints + sys.exit(0)
    sys.exit(0)


def _main(argv):
    for a in argv:
        if a in ("-h", "--help"):
            _print_help_and_exit()

    if sys.version_info < (3, 12):
        sys.stderr.write(
            "this skill requires Python 3.12+; you have {0}.\n"
            "Re-run via `./venv/bin/python bootstrap.py ...` after `make install`.\n".format(
                ".".join(str(x) for x in sys.version_info[:3])
            )
        )
        return 2

    try:
        import jinja2  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "missing dep `jinja2`: re-run 'make install' in {0}\n".format(_skill_root())
        )
        return 2

    from bootstrap_lib.cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
