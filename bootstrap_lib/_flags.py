# Shared flag definitions between bootstrap.py shim and bootstrap_lib.cli.
#
# Python 3.6 compatible: no third-party imports, no 3.10+ syntax,
# no f-strings in body (the shim loads this BEFORE the version check).
# Stays as a thin function that mutates a passed-in argparse.ArgumentParser.


def add_flags(parser):
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="print planned writes; no filesystem changes (default mode)",
    )
    mode.add_argument(
        "--diff",
        action="store_true",
        help="print a unified diff against existing files; no filesystem changes",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="actually write files (writes a restore manifest to TMPDIR before any write)",
    )
    mode.add_argument(
        "--restore",
        metavar="MANIFEST",
        default=None,
        help="restore filesystem from a previously written manifest (rolls back an apply)",
    )

    parser.add_argument(
        "--language",
        choices=["python", "nodejs", "go"],
        help="target language (python, nodejs, or go)",
    )
    parser.add_argument(
        "--project-name",
        dest="project_name",
        help="project slug; must match ^[a-z][a-z0-9-]*$",
    )
    parser.add_argument(
        "--out",
        help="target directory; created only during --apply",
    )
    parser.add_argument(
        "--github-review",
        dest="github_review",
        choices=["none", "claude", "both-docs"],
        default="none",
        help=(
            "emit Claude / Codex GitHub auto-review files. "
            "Default 'none' avoids hidden OAuth-secret dependencies"
        ),
    )
    parser.add_argument(
        "--github-owner",
        dest="github_owner",
        help=(
            "GitHub owner (required when --github-review != none; "
            "also used as the Go module-path prefix when --language=go)"
        ),
    )
    parser.add_argument(
        "--github-repo",
        dest="github_repo",
        help=(
            "GitHub repo (required when --github-review != none; "
            "also used as the Go module-path suffix when --language=go)"
        ),
    )
    parser.add_argument(
        "--package-manager",
        dest="package_manager",
        choices=["uv", "pip"],
        default=None,
        help=(
            "Python package manager. Default 'uv' for greenfield; "
            "auto-detected when bootstrapping into an existing project. "
            "Use 'pip' to opt out. Only valid with --language=python."
        ),
    )
    parser.add_argument(
        "--overwrite-existing",
        dest="overwrite_existing",
        action="store_true",
        help="consent to overwrite pre-existing target files during --apply",
    )
    parser.add_argument(
        "--enable-smoke",
        dest="enable_smoke",
        action="store_true",
        help="emit docs/SMOKE.md skeleton",
    )
