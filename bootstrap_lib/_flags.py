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
    # PR #7 Bucket A: --mode=adopt is a SINGLE-VALUE adoption modifier of
    # --apply, NOT a 5th mode in the mutually-exclusive group above. choices
    # is intentionally [adopt] only — that's the one modifier we ship today.
    # Validation lives in cli.py:_resolve_mode (requires --apply, Python-only,
    # rejected in restore mode, rejected with --overwrite-existing).
    parser.add_argument(
        "--mode",
        choices=["adopt"],
        default=None,
        help=(
            "Adoption modifier. Requires --apply. Enables per-file "
            "analyze-then-decide-with-owner UX for safe adoption into "
            "existing projects (see docs/usage.md). Invalid with --dry-run, "
            "--diff, --restore. For read-only inspection, use --diff."
        ),
    )
    parser.add_argument(
        "--auto-accept-recommendations",
        dest="auto_accept_recommendations",
        action="store_true",
        help=(
            "With --mode=adopt: accept every policy recommendation whose "
            "manual_review_needed=False without prompting. "
            "manual_review_needed=True files still need a decision."
        ),
    )
    parser.add_argument(
        "--non-interactive",
        dest="non_interactive",
        action="store_true",
        help=(
            "With --mode=adopt: turn any required prompt into a fail-loud "
            "exit 2 instead of reading stdin. Combine with "
            "--auto-accept-recommendations for a 'accept everything safe, "
            "fail on anything needing review' CI contract."
        ),
    )
