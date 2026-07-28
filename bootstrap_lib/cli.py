import argparse
import difflib
import json
import os
import sys
import traceback
from pathlib import Path

from bootstrap_lib import detect, manifest, paths, render
from bootstrap_lib._flags import PROJECT_NAME_RE, add_flags
from bootstrap_lib.apply_pipeline import (
    _apply_writes,
    _cli_layer_path_safety,
    _main_apply_adopt,
    _prepare_apply,
)
from bootstrap_lib.guidance import _format_restore_hint, _print_post_apply_guidance


class CLIError(Exception):
    def __init__(self, exit_code, message):
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="bootstrap.py",
        description=("dev-project-setup skill — bootstrap a dev workflow into a target project."),
    )
    add_flags(parser)
    return parser


def _resolve_mode(args):
    if args.restore is not None:
        bad = []
        if args.language:
            bad.append("--language")
        if args.project_name:
            bad.append("--project-name")
        if args.out:
            bad.append("--out")
        if args.apply:
            bad.append("--apply")
        if args.diff:
            bad.append("--diff")
        if args.dry_run:
            bad.append("--dry-run")
        if args.overwrite_existing:
            bad.append("--overwrite-existing")
        if args.enable_smoke:
            bad.append("--enable-smoke")
        if args.github_owner:
            bad.append("--github-owner")
        if args.github_repo:
            bad.append("--github-repo")
        if args.package_manager is not None:
            bad.append("--package-manager")
        # PR #7 Bucket A: --mode / --auto-accept-recommendations /
        # --non-interactive are adopt-mode-only modifiers; rejected in
        # restore mode.
        if args.mode is not None:
            bad.append("--mode")
        if args.auto_accept_recommendations:
            bad.append("--auto-accept-recommendations")
        if args.non_interactive:
            bad.append("--non-interactive")
        # default=None so we can detect an explicit user-supplied value.
        if args.github_review is not None:
            bad.append("--github-review")
        if bad:
            raise CLIError(
                2,
                "these flags are not valid in restore mode: {}".format(", ".join(bad)),
            )
        return "restore"

    missing = []
    if not args.language:
        missing.append("--language")
    if not args.project_name:
        missing.append("--project-name")
    if not args.out:
        missing.append("--out")
    if missing:
        raise CLIError(2, "missing required args: {}".format(", ".join(missing)))

    if not PROJECT_NAME_RE.match(args.project_name):
        raise CLIError(
            2,
            "invalid project name: must match ^[a-z][a-z0-9-]*$ — e.g. 'my-project', 'foo123'",
        )

    if args.github_review not in (None, "none") and (not args.github_owner or not args.github_repo):
        raise CLIError(
            2,
            f"--github-review={args.github_review} requires --github-owner and --github-repo "
            "(no implicit git-remote discovery — greenfield projects often "
            "have no origin yet)",
        )

    if args.package_manager is not None and args.language != "python":
        raise CLIError(
            2,
            f"--package-manager only valid with --language=python (got --language={args.language})",
        )

    # PR #7 Bucket A: --mode=adopt validations.
    if args.mode == "adopt":
        if not args.apply:
            raise CLIError(
                2,
                "--mode=adopt requires --apply "
                "(for read-only inspection, use plain `--diff --language python`)",
            )
        if args.language != "python":
            raise CLIError(
                2,
                "--mode=adopt is Python-only "
                f"(got --language={args.language}; "
                "adoption-mode for Node / Go is parked for a follow-up PR)",
            )
        if args.overwrite_existing:
            raise CLIError(
                2,
                "--mode=adopt cannot be combined with --overwrite-existing — "
                "adopt mode's per-file consent IS the consent model; "
                "--overwrite-existing is the nuclear escape hatch for plain --apply",
            )
    else:
        # --auto-accept-recommendations / --non-interactive only make sense
        # under --mode=adopt; fail loud if used outside (silent no-op would
        # mask a user's misunderstanding).
        if args.auto_accept_recommendations:
            raise CLIError(
                2,
                "--auto-accept-recommendations only valid with --mode=adopt",
            )
        if args.non_interactive:
            raise CLIError(
                2,
                "--non-interactive only valid with --mode=adopt",
            )

    if args.apply:
        return "apply"
    if args.diff:
        return "diff"
    return "dry_run"


def _build_context(args, package_manager=None):
    """Build the Jinja render context dict.

    Stays a pure dict-construction function — no filesystem I/O (closes
    Claude iter-2 #6). Detection + advisory printing live in `main()`
    upstream; the resolved `package_manager` value flows in as a kwarg.

    `package_manager` is the effective value: explicit flag > detection >
    `"uv"` default for `--language=python` > `None` for other languages.
    """
    return {
        "project_name": args.project_name,
        "language": args.language,
        "python_version": "3.12",
        "node_version": "24",
        "go_version": "1.26",
        "package_manager": package_manager,
        "enable_smoke": bool(args.enable_smoke),
        "github_owner": args.github_owner or "",
        "github_repo": args.github_repo or "",
        "github_review_mode": args.github_review or "none",
    }


def _resolve_package_manager(args):
    """Resolve the effective `package_manager` for this invocation.

    Returns `(effective_pm, detection_result_or_None)`. Detection runs only
    for `--language=python`; for other languages, returns `(None, None)`.

    The CLI applies the `"uv"` default for `--language=python` when neither
    the explicit flag nor detection produces a manager — closes Claude
    iter-2 #1 (rule 6 returns `(None, "ambiguous: ...")` so the override
    hint advisory can fire; CLI is what defaults to uv).
    """
    if args.language != "python":
        return None, None
    detected = detect.detect_package_manager(args.out)
    if args.package_manager is not None:
        return args.package_manager, detected
    if detected.manager is not None:
        return detected.manager, detected
    # Manager-None paths (greenfield / ambiguous / malformed) — CLI default.
    return "uv", detected


def _maybe_print_advisory(args, detected, effective_pm):
    """Print a one-line stderr advisory about the resolved package manager.

    Rules (closes Claude iter-2 #1, Codex iter-3 #2):
    - User passed `--package-manager` explicitly → no advisory.
    - Positive marker fired in detection (rules 2-5) → succinct info line.
    - Ambiguous (rule 6 → manager=None, reason starts "ambiguous") AND
      CLI defaulted to uv → explicit override-hint advisory.
    - Greenfield / malformed paths (rule 1/7/8) → no advisory.
    """
    if args.package_manager is not None:
        return
    if detected is None:
        return
    if detected.manager is not None:
        sys.stderr.write(f"info: detected package_manager='{effective_pm}' ({detected.reason})\n")
        return
    if detected.reason.startswith("ambiguous") and effective_pm == "uv":
        sys.stderr.write(
            "info: existing pyproject.toml has no uv/pip markers; "
            "defaulting package_manager='uv' "
            "(pass --package-manager=pip to override)\n"
        )


def _print_dry_run(planned_files, inspection):
    print(f"dry-run: would write {len(planned_files)} files")
    for entry in inspection:
        marker = "MODIFY" if entry["exists"] else "CREATE"
        print("  {} {}".format(marker, entry["path"]))


def _print_diff(target_root, planned_files):
    root = Path(target_root)
    for rel_path in sorted(planned_files):
        target = root / rel_path
        new_text = (
            planned_files[rel_path].decode("utf-8", errors="replace").splitlines(keepends=True)
        )
        if target.exists():
            old_text = target.read_text(encoding="utf-8", errors="replace").splitlines(
                keepends=True
            )
        else:
            old_text = []
        diff = list(
            difflib.unified_diff(
                old_text,
                new_text,
                fromfile="a/" + rel_path,
                tofile="b/" + rel_path,
                n=3,
            )
        )
        if diff:
            sys.stdout.writelines(diff)


def _should_run_intake(argv, args):
    """True when the interactive intake should run: `--interactive` was
    passed, OR `bootstrap.py` was invoked with zero arguments on a terminal.

    `sys.stdin` can be `None` in a detached process — guard before
    `.isatty()` so that case falls through cleanly (to today's
    missing-args error) rather than raising `AttributeError`.
    """
    if args.interactive:
        return True
    return not argv and sys.stdin is not None and sys.stdin.isatty()


def main(argv):
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --interactive is standalone-only: any other argv token is rejected here,
    # before mode resolution, so a load-bearing mode (e.g. --restore) can never
    # be re-routed into the interactive question flow. A raw token count is
    # deliberate — any other flag adds at least one token.
    if args.interactive and len(argv) > 1:
        sys.stderr.write("--interactive must be used on its own (no other flags) in this version\n")
        return 2
    if _should_run_intake(argv, args):
        # `sys.stdin` can be None in a detached process. `_should_run_intake`'s
        # auto-trigger branch already guards this, but the explicit
        # `--interactive` branch does not — without this guard `run_intake`
        # would dereference `None.readline()` and raise an uncaught
        # AttributeError. Fail loud instead.
        if sys.stdin is None:
            sys.stderr.write("interactive mode needs an interactive terminal or piped answers\n")
            return 2
        # Lazy import — mirrors the adopt-mode lazy import below; lets
        # intake.py import _flags/render with no at-import cycle.
        from bootstrap_lib import intake

        try:
            intake_argv = intake.run_intake()
        except intake.IntakeAborted:
            # EOF mid-flow: Ctrl-D on a terminal → treat as cancel; an
            # exhausted/empty non-TTY pipe → fail loud.
            if sys.stdin is not None and sys.stdin.isatty():
                return 0
            sys.stderr.write("interactive mode needs an interactive terminal or piped answers\n")
            return 2
        except KeyboardInterrupt:
            # Ctrl-C → clean cancel, not a raw traceback.
            sys.stderr.write("\ncancelled\n")
            return 0
        if intake_argv is None:  # user chose 'cancel'
            return 0
        # Re-parse the intake-built argv through the SAME parser — intake gets
        # every existing validation for free; this is a backstop, not the
        # primary check.
        args = parser.parse_args(intake_argv)

    try:
        mode = _resolve_mode(args)
    except CLIError as e:
        sys.stderr.write(e.message + "\n")
        return e.exit_code

    if mode == "restore":
        try:
            m = manifest.load_manifest(args.restore)
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            sys.stderr.write(f"cannot read manifest {args.restore}: {e}\n")
            return 1
        # Codex iter-22 P2: surface the rejected count as a non-zero exit so
        # scripted rollback flows don't silently report success when the
        # manifest contained a path-safety violation and no work was done.
        _r, _rm, _sk, n_rj = manifest.restore_from_manifest(m)
        return 1 if n_rj > 0 else 0

    # Resolve package_manager (Python-only) BEFORE _build_context so
    # _build_context stays a pure dict-construction function (closes
    # Claude iter-2 #6).
    effective_pm, detected = _resolve_package_manager(args)
    _maybe_print_advisory(args, detected, effective_pm)

    context = _build_context(args, package_manager=effective_pm)
    try:
        planned_files = render.render_all(context, language=args.language)
    except paths.PathSafetyError as e:
        sys.stderr.write(f"path-safety (renderer): {e}\n")
        return 2

    try:
        _cli_layer_path_safety(args.out, planned_files)
    except paths.PathSafetyError as e:
        sys.stderr.write(f"path-safety: {e}\n")
        return 2

    target_root = Path(args.out)
    inspection = detect.inspect_target(target_root, planned_files)

    if mode == "dry_run":
        _print_dry_run(planned_files, inspection)
        return 0

    if mode == "diff":
        _print_diff(target_root, planned_files)
        return 0

    # apply
    # PR #7: --mode=adopt has its own apply pipeline that supersedes the
    # plain-apply collision-abort contract. Per-file consent via
    # _interactive_decide IS the consent model; no --overwrite-existing
    # needed (it's actually rejected by _resolve_mode for adopt-mode).
    if args.mode == "adopt":
        return _main_apply_adopt(args, target_root, planned_files, context)

    if detect.has_collisions(inspection) and not args.overwrite_existing:
        sys.stderr.write(
            "collision detected — re-run with `--overwrite-existing` to consent, "
            "or use `--diff` first to see what would change\n"
        )
        for entry in inspection:
            if entry["exists"]:
                sys.stderr.write("  EXISTS: {}\n".format(entry["path"]))
        return 2

    # Split prepare from writes so the manifest path is preserved if a write
    # raises mid-apply (closes Codex iter-22 P1).
    try:
        root, entries, manifest_p = _prepare_apply(target_root, planned_files, args)
    except Exception as e:
        sys.stderr.write(f"apply failed before manifest write: {e}\n")
        if os.environ.get("DEV_PROJECT_SETUP_TRACEBACK"):
            traceback.print_exc()
        return 1

    try:
        _apply_writes(root, planned_files, entries)
    except Exception as e:
        sys.stderr.write(f"apply failed mid-write: {e}\n")
        if os.environ.get("DEV_PROJECT_SETUP_TRACEBACK"):
            traceback.print_exc()
        sys.stderr.write(
            "target tree may be in a partial state. To roll back the writes\n"
            "that did complete, run the restore command below.\n"
        )
        sys.stderr.write(f"restore manifest: {manifest_p}\n")
        sys.stderr.write(f"to rollback: {_format_restore_hint(manifest_p)}\n")
        return 1

    print(f"apply successful: wrote {len(planned_files)} files to {target_root}")
    print(f"restore manifest: {manifest_p}")
    print(f"to rollback: {_format_restore_hint(manifest_p)}")
    _print_post_apply_guidance(args, target_root, adopt=False)
    return 0
