import argparse
import difflib
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from bootstrap_lib import detect, io, manifest, paths, render
from bootstrap_lib._flags import add_flags

PROJECT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


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
        # --github-review has a default of 'none'; only flag it if user passed
        # a non-default — but we can't tell from args alone. Skip.
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

    if args.github_review != "none" and (not args.github_owner or not args.github_repo):
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
        "project_import_name": args.project_name.replace("-", "_"),
        "language": args.language,
        "python_version": "3.12",
        "node_version": "24",
        "go_version": "1.26",
        "package_manager": package_manager,
        "enable_smoke": bool(args.enable_smoke),
        "github_owner": args.github_owner or "",
        "github_repo": args.github_repo or "",
        "github_review_mode": args.github_review,
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


# ─── --mode=adopt interactive decide-phase UX (PR #7 Bucket C / Scope #6) ─────


class _AdoptionAbort(Exception):
    """User chose [q]uit OR EOF on stdin during a required decision OR
    `--non-interactive` set with a manual_review_needed=True file.

    `main()` catches and exits with code 2 (the fail-loud CI contract).
    """


# Per-file allowed-actions matrix (Scope #6):
#   always-allowed: r/s/d/?/q
#   [n] (WRITE_NEW): any manual-review file
#   [a] (APPEND_MERGE): ONLY .gitignore (rule (d) line-level idempotent merge)
#   [o] (OVERWRITE): always-allowed but requires typed `OVERWRITE` (uppercase)
_ALWAYS_ACTIONS = ("r", "s", "n", "o", "d", "?", "q")


def _allowed_actions_for(rel_path):
    """Return the ordered list of allowed action keys for this file's prompt."""
    name = Path(rel_path).name
    actions = list(_ALWAYS_ACTIONS)
    if name == ".gitignore":
        # [a] only for .gitignore (Architecture decision: APPEND_MERGE
        # only for .gitignore). Insert before [o] to group mutating actions.
        actions.insert(actions.index("o"), "a")
    return actions


_ACTION_HELP = {
    "r": "[r]ecommended  apply the recommended policy (default — just press Enter)",
    "s": "[s]kip         leave the target alone; no write, no manifest entry",
    "n": "[n]ew          write a .new file alongside the original; original untouched",
    "a": "[a]ppend       append-only line-level merge (.gitignore only)",
    "o": "[o]verwrite    OVERWRITE the target — requires typed `OVERWRITE` (uppercase) to confirm",
    "d": "[d]iff         show a unified diff between target and the skill template",
    "?": "[?]help        this help text",
    "q": "[q]uit         abort the entire adopt run (no files modified yet)",
}


def _print_action_help(allowed, stdout):
    for a in allowed:
        if a in _ACTION_HELP:
            stdout.write("  " + _ACTION_HELP[a] + "\n")


def _show_decide_diff(rel_path, target_root, planned_files, stdout):
    """Print a unified diff for the file under decision (read-only preview).

    Same shape as `_print_diff`'s per-file logic but scoped to one file."""
    target_path = Path(target_root) / rel_path
    new_text = planned_files[rel_path].decode("utf-8", errors="replace").splitlines(keepends=True)
    if target_path.exists():
        old_text = target_path.read_text(encoding="utf-8", errors="replace").splitlines(
            keepends=True
        )
    else:
        old_text = []
    diff = difflib.unified_diff(
        old_text, new_text, fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}", n=3
    )
    for line in diff:
        stdout.write(line)


def _user_decision(rec, policy, reason):
    """Build a PolicyRecommendation from a user decision.

    User-authored decisions set `manual_review_needed=False` (they ARE the
    review) and `confidence="high"` (user is the authority on their target)."""
    return rec._replace(
        policy=policy,
        reason=reason,
        confidence="high",
        manual_review_needed=False,
    )


def _prompt_one_file(analysis, planned_files, target_root, stdin, stdout):
    """Prompt the user for one file's decision; return the new PolicyRecommendation.

    Loops until the user gives a valid terminal action ([r]/[s]/[n]/[a]/[o]/[q]).
    [d] and [?] re-display info and re-prompt. [o] requires typed `OVERWRITE`."""
    rec = analysis.recommendation
    rel_path = analysis.rel_path
    allowed = _allowed_actions_for(rel_path)

    stdout.write(f"\n=== {rel_path} ===\n")
    stdout.write(f"  recommended: {rec.policy}\n")
    stdout.write(f"  reason: {rec.reason}\n")

    while True:
        prompt = "  decide: " + "/".join(f"[{a}]" for a in allowed) + " (default [r]) > "
        stdout.write(prompt)
        stdout.flush()
        line = stdin.readline()
        if not line:
            raise _AdoptionAbort(f"EOF on stdin while deciding {rel_path}; aborting adopt run")
        choice = line.strip().lower()
        if choice == "":
            choice = "r"

        if choice == "q":
            raise _AdoptionAbort(f"user quit at {rel_path}; no files modified")
        if choice == "?":
            _print_action_help(allowed, stdout)
            continue
        if choice == "d":
            _show_decide_diff(rel_path, target_root, planned_files, stdout)
            continue
        if choice == "r":
            # Accept the recommendation as-is, but mark reviewed.
            return _user_decision(rec, rec.policy, f"user accepted recommendation: {rec.reason}")
        if choice == "s":
            return _user_decision(rec, "SKIP", "user chose [s]kip")
        if choice == "n":
            return _user_decision(rec, "WRITE_NEW", "user chose [n]ew (.new alongside original)")
        if choice == "a":
            if "a" in allowed:
                return _user_decision(rec, "APPEND_MERGE", "user chose [a]ppend (line-level merge)")
            stdout.write(
                f"  [a]ppend is only available for .gitignore (got {rel_path}); "
                "type [?] for valid actions\n"
            )
            continue
        if choice == "o":
            stdout.write(
                '  type "OVERWRITE" (uppercase, exactly) to confirm destructive overwrite: '
            )
            stdout.flush()
            confirm_line = stdin.readline()
            if not confirm_line:
                raise _AdoptionAbort(
                    f"EOF on stdin during OVERWRITE confirmation for {rel_path}; aborting"
                )
            # Case-sensitive: lowercase "overwrite" or partial matches must NOT
            # confirm (non-developer-audience safety against stray keystrokes).
            if confirm_line.strip() == "OVERWRITE":
                return _user_decision(rec, "OVERWRITE", "user confirmed destructive [o]verwrite")
            stdout.write("  cancelled — no overwrite (re-pick an action)\n")
            continue

        stdout.write(f"  invalid choice {choice!r}; type [?] for help\n")


def _interactive_decide(plan, planned_files, *, non_interactive=False, stdin=None, stdout=None):
    """Per-file decide-phase UX (Bucket C / Scope #6 single-matrix contract).

    Only files with `manual_review_needed=True` trigger a prompt. Files with
    `manual_review_needed=False` pass through unchanged (their recommendation
    is the canonical action; the user already saw it in the report shown
    upstream by `format_recommendation_report`).

    Under `--non-interactive`, encountering a manual_review_needed=True file
    raises `_AdoptionAbort` BEFORE any prompt — the natural CI contract:
    everything safe applies, anything needing review fails the run.

    EOF on stdin before a required decision also raises `_AdoptionAbort`
    (per Codex iter-5 #1 fold: heredoc / piped input works, but running out
    mid-decision is fail-loud).

    Returns a new `AdoptionPlan` with each prompted analysis's recommendation
    replaced by the user's choice; un-prompted analyses are unchanged.
    """
    if stdin is None:
        stdin = sys.stdin
    if stdout is None:
        stdout = sys.stdout

    new_analyses = []
    for analysis in plan.analyses:
        if not analysis.recommendation.manual_review_needed:
            new_analyses.append(analysis)
            continue
        if non_interactive:
            raise _AdoptionAbort(
                f"--non-interactive set but {analysis.rel_path} needs a decision "
                f"(recommended {analysis.recommendation.policy}); exit 2"
            )
        new_rec = _prompt_one_file(analysis, planned_files, plan.target_root, stdin, stdout)
        new_analyses.append(analysis._replace(recommendation=new_rec))

    return plan._replace(analyses=tuple(new_analyses))


def _format_restore_hint(manifest_path):
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(BOOTSTRAP_PY.resolve()))} --restore {shlex.quote(str(manifest_path))}"


def _maybe_pause_after_first_write():
    sentinel = os.environ.get("DEV_PROJECT_SETUP_PAUSE_AFTER_FIRST_WRITE")
    if not sentinel:
        return
    with open(sentinel, "w") as f:
        f.write("paused\n")
    while True:
        time.sleep(60)


def _cli_layer_path_safety(target_root, planned_files):
    """Second-tier path-safety check, run AFTER render.render_all.

    Uses the real target_root (which may not exist yet) so symlink escapes are
    caught. Closes Codex iter-8 finding #2.
    """
    root = Path(target_root)
    # For a not-yet-existing target_root, resolve the parent for symlink
    # discipline; .resolve() is non-strict in 3.6+, so we can resolve a
    # non-existent path safely.
    for rel_path in planned_files:
        paths.validate_target_path(root, rel_path)


def _prepare_apply(target_root, planned_files, args):
    """Plan entries, build + fsync the manifest. Returns (root, entries,
    manifest_path). Separated from the write phase so `main()` keeps the
    manifest path available even if writes fail mid-apply — closes Codex
    iter-22 P1 (restore hint must still print on partial-apply failure).

    Does NOT create `target_root` here — closes Codex iter-24 P1: mkdir
    before manifest_write would leave a partial side effect (orphan
    target dir) with no rollback path. `atomic_write` lazily creates
    parent dirs per file, so target_root is implicitly created on the
    first write — AFTER the manifest is durable.
    """
    root = Path(target_root)
    entries, created_directories = manifest.plan_entries(root, planned_files)
    m = manifest.Manifest(
        target_root=str(root.resolve()),
        github_review_mode=args.github_review,
        entries=entries,
        created_directories=created_directories,
    )
    manifest_p = manifest.write_manifest(m)
    return root, entries, manifest_p


def _apply_writes(root, planned_files, entries):
    """Do the actual atomic writes. May raise mid-way; the caller is
    responsible for preserving the manifest path so the failure path can
    print a working restore hint."""
    io.install_signal_handlers()

    entry_by_path = {e["path"]: e for e in entries}
    first = True
    for rel_path in sorted(planned_files):
        target = root / rel_path
        io.atomic_write(target, planned_files[rel_path])
        os.chmod(target, entry_by_path[rel_path]["mode_after"])
        if first:
            _maybe_pause_after_first_write()
            first = False


def _apply_adoption_writes(root, planned_files, adoption_plan, entries):
    """Apply v2 entries per Scope #7's per-policy write contract.

    Replaces the plain `_apply_writes` flow when `--mode=adopt`. SKIP entries
    are NOT in the manifest (mutation-only contract), so the loop never sees
    them. Each remaining policy uses `io.atomic_write` (tmp + os.replace) for
    crash-safety — closes Codex iter-21 P1 contract carried into v2.

      WRITE         atomic_write(rel_path, skill_content) + chmod
      OVERWRITE     atomic_write(rel_path, skill_content) + chmod
                    (manifest's content_before_b64 + mode_before snapshot
                     was captured at plan-time by plan_adoption_entries)
      WRITE_NEW     re-check `.new` doesn't exist (defense-in-depth against
                    TOCTOU between plan and apply) → atomic_write `.new`
      APPEND_MERGE  re-read current target + compute_append_merge_bytes
                    against skill → atomic_write merged content. Re-merging
                    at apply time keeps the contract: the skill template is
                    the canonical source, and append is idempotent.

    Raises `AdoptionCollisionError` if a `.new` file appeared between plan
    and apply (TOCTOU); the caller catches + converts to exit 2 + restore
    hint (the v2 manifest is already on disk so restore can rollback the
    entries written before the collision).
    """
    # Local import to avoid an at-import-time cycle (cli → adopt → ...).
    from bootstrap_lib.adopt import (
        AdoptionCollisionError,
        compute_append_merge_bytes,
    )

    io.install_signal_handlers()
    root_path = Path(root)
    _ = adoption_plan  # held for future signal-handler logging hooks
    first = True

    for entry in entries:
        policy = entry["policy"]
        rel_path = entry["path"]
        target_full = root_path / entry["target_path"]

        if policy in ("WRITE", "OVERWRITE"):
            # Both are atomic full-content writes. WRITE creates; OVERWRITE
            # replaces (the v1-style content_before_b64 snapshot was captured
            # at plan-time by plan_adoption_entries for restore).
            io.atomic_write(target_full, planned_files[rel_path])
            os.chmod(target_full, entry["mode_after"])
        elif policy == "WRITE_NEW":
            # Defense-in-depth: re-verify `.new` didn't appear between plan-
            # time and apply-time. plan_adoption_entries already raised on
            # collision but a concurrent process could race in between.
            if target_full.exists():
                raise AdoptionCollisionError(
                    f"{entry['target_path']} appeared between plan-time and apply-time "
                    "— bootstrap will NOT overwrite an existing .new file"
                )
            io.atomic_write(target_full, planned_files[rel_path])
            os.chmod(target_full, entry["mode_after"])
        elif policy == "APPEND_MERGE":
            # Re-merge at apply time against current target bytes. The skill
            # template is the canonical source; append is line-level idempotent
            # so a TOCTOU edit that added new patterns to the target won't
            # double-append them.
            current_target = target_full.read_bytes()
            merged = compute_append_merge_bytes(current_target, planned_files[rel_path])
            io.atomic_write(target_full, merged)
            os.chmod(target_full, entry["mode_after"])
        else:
            raise ValueError(
                f"unknown policy {policy!r} in v2 entry for {rel_path!r}; "
                "expected WRITE/OVERWRITE/WRITE_NEW/APPEND_MERGE "
                "(SKIP entries should NOT appear in v2 manifests)"
            )
        if first:
            _maybe_pause_after_first_write()
            first = False


def _main_apply_adopt(args, target_root, planned_files):
    """`--apply --mode=adopt` orchestrator. Pipeline:

      1. analyze_target(target_root, planned_files) → AdoptionPlan
      2. format_recommendation_report(plan) → printed to stdout
      3. _interactive_decide(plan, planned_files, non_interactive=...)
         → AdoptionPlan with user decisions (may raise _AdoptionAbort)
      4. manifest.plan_adoption_entries(...) → v2 entries + created_dirs
         (may raise AdoptionCollisionError on `.new` collision)
      5. Build + write v2 manifest BEFORE any filesystem mutation, so
         restore can roll back partial-apply (carries the iter-22 P1
         contract into adopt-mode).
      6. _apply_adoption_writes(...) → atomic writes per policy.

    Returns the exit code. _AdoptionAbort / AdoptionCollisionError both
    map to exit 2 (fail-loud CI contract); mid-write exceptions map to
    exit 1 with a restore hint.
    """
    # Local import to avoid top-level cycles (cli → adopt is fine; adopt
    # never imports cli).
    from bootstrap_lib import adopt

    try:
        adoption_plan = adopt.analyze_target(target_root, planned_files)
    except Exception as e:
        sys.stderr.write(f"adopt-mode analyze failed: {e}\n")
        return 1

    # Show the recommendation report BEFORE prompting so the user sees the
    # full per-file picture in one pass.
    sys.stdout.write(adopt.format_recommendation_report(adoption_plan))

    try:
        decided_plan = _interactive_decide(
            adoption_plan,
            planned_files,
            non_interactive=args.non_interactive,
        )
    except _AdoptionAbort as e:
        sys.stderr.write(f"{e}\n")
        return 2

    try:
        entries, created_dirs = manifest.plan_adoption_entries(
            target_root, planned_files, decided_plan
        )
    except adopt.AdoptionCollisionError as e:
        sys.stderr.write(f"{e}\n")
        return 2

    if not entries:
        # All-SKIP outcome: every file was either recommended SKIP and
        # accepted, or user explicitly chose SKIP. Nothing to write, no
        # manifest needed (manifests are mutation-only).
        sys.stdout.write(
            "adopt-mode: all entries SKIPPED — no manifest written, no files modified.\n"
        )
        return 0

    m = manifest.Manifest(
        # Resolve to absolute path — mirrors v1's _prepare_apply contract so
        # `bootstrap.py --restore <manifest>` works from any cwd. Without
        # `.resolve()`, a manifest written from cwd A with `--out ./target`
        # would record `target_root="target"` and silently fail to find
        # anything when restored from a different cwd (no files removed,
        # exit 0, user thinks rollback worked).
        target_root=str(Path(target_root).resolve()),
        github_review_mode=args.github_review,
        entries=entries,
        created_directories=created_dirs,
        format_version=manifest.MANIFEST_FORMAT_V2,
    )
    try:
        manifest_p = manifest.write_manifest(m)
    except Exception as e:
        sys.stderr.write(f"adopt-mode failed before manifest write: {e}\n")
        return 1

    try:
        _apply_adoption_writes(target_root, planned_files, decided_plan, entries)
    except adopt.AdoptionCollisionError as e:
        # TOCTOU `.new` collision during apply. Manifest is on disk — partial
        # writes can be rolled back via restore.
        sys.stderr.write(f"{e}\n")
        sys.stderr.write(f"restore manifest: {manifest_p}\n")
        sys.stderr.write(f"to rollback: {_format_restore_hint(manifest_p)}\n")
        return 2
    except Exception as e:
        sys.stderr.write(f"adopt-mode apply failed mid-write: {e}\n")
        sys.stderr.write(
            "target tree may be in a partial state. To roll back the writes\n"
            "that did complete, run the restore command below.\n"
        )
        sys.stderr.write(f"restore manifest: {manifest_p}\n")
        sys.stderr.write(f"to rollback: {_format_restore_hint(manifest_p)}\n")
        return 1

    n_mutated = len(entries)
    print(f"adopt-mode apply: {n_mutated} mutating entries written to {target_root}")
    print(f"restore manifest: {manifest_p}")
    print(f"to rollback: {_format_restore_hint(manifest_p)}")
    return 0


def main(argv):
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        mode = _resolve_mode(args)
    except CLIError as e:
        sys.stderr.write(e.message + "\n")
        return e.exit_code

    if mode == "restore":
        m = manifest.load_manifest(args.restore)
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
        return _main_apply_adopt(args, target_root, planned_files)

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
        return 1

    try:
        _apply_writes(root, planned_files, entries)
    except Exception as e:
        sys.stderr.write(f"apply failed mid-write: {e}\n")
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
    if args.language in ("python", "nodejs", "go"):
        print("next steps:")
        print(f"  cd {target_root} && make install")
        print("  make install-hooks  # registers git hooks, requires .git/")
    if args.github_review != "none":
        # gh-repo-create hint. Two detection states: (a) no `.git` at all →
        # the target needs `git init` first; (b) `.git` exists but no remote
        # → only remote creation is needed. Use `git -C ... remote`
        # (subprocess, not the gh CLI — gh is an optional prereq, git is
        # required). Detection fails open: any error → no hint, apply still
        # succeeds.
        git_dir = target_root / ".git"
        # `.exists()`, not `.is_dir()` — a linked `git worktree` (and a
        # `--separate-git-dir` layout) stores `.git` as a FILE, not a
        # directory. `git -C ... remote` below resolves the real gitdir
        # correctly in both cases; treating a worktree as "no git" would
        # wrongly tell the user to `git init` inside an existing repo.
        has_git = git_dir.exists()
        has_remote = False
        if has_git:
            try:
                result = subprocess.run(
                    ["git", "-C", str(target_root), "remote"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=5,
                )
                has_remote = result.returncode == 0 and bool(result.stdout.strip())
            except (OSError, subprocess.SubprocessError):
                # FileNotFoundError is a subclass of OSError; SubprocessError
                # covers TimeoutExpired (which does NOT subclass OSError).
                has_remote = False

        if not has_remote:
            # Safe-pattern hint: `git status` + explicit `git add <path>` —
            # never bulk-add (`git add -A` / `git add .`), which can stage
            # secrets or throwaway files (LESSONS.md). Visibility is shown as
            # two explicit alternatives (no shell-metacharacter placeholder).
            print("")
            if not has_git:
                print("create the GitHub repo + push:")
                print(f"  cd {target_root}")
                print("  git init")
                print("  git status --short                 # review what's about to be staged")
                print(
                    "  git add <path1> <path2> ...        # stage explicitly per `git status` output"
                )
                print("  git commit -m 'initial bootstrap'")
                print("  # choose ONE — copy the line for the visibility you want:")
                print(
                    f"  gh repo create {args.github_owner}/{args.github_repo} "
                    "--source=. --push --private    # private (recommended for new code with secrets)"
                )
                print(
                    f"  gh repo create {args.github_owner}/{args.github_repo} "
                    "--source=. --push --public     # public (anyone can see)"
                )
            else:
                print("your repo isn't on GitHub yet — create the remote + push:")
                print(f"  cd {target_root}")
                print("  git status --short                 # review uncommitted changes first")
                print("  git add <path1> <path2> ...        # stage explicitly")
                print("  git commit -m 'initial bootstrap'  # only if there are pending changes")
                print("  # choose ONE — copy the line for the visibility you want:")
                print(
                    f"  gh repo create {args.github_owner}/{args.github_repo} "
                    "--source=. --push --private    # private (recommended for new code with secrets)"
                )
                print(
                    f"  gh repo create {args.github_owner}/{args.github_repo} "
                    "--source=. --push --public     # public (anyone can see)"
                )
            print("  (requires `gh` CLI authenticated; no default — pick deliberately)")

        if args.github_review == "both-docs":
            # Codex GitHub review is a one-time web-UI step, orthogonal to
            # repo creation — print it whenever both-docs, whether or not the
            # target already has a remote.
            print("")
            print("  enable Codex GitHub review for this repo (one-time, web-UI):")
            print(f"    see {target_root}/docs/codex-github-review-setup.md")

        # Surface the required-secret step right where the user sees the
        # other next-steps — most discoverable spot before they push to
        # GitHub. Without this secret, the emitted claude-review workflow
        # runs but the action fails auth and no review is posted.
        print("")
        print("after pushing to GitHub, set the CLAUDE_CODE_OAUTH_TOKEN repo secret:")
        print("  1. install https://github.com/apps/claude on your account")
        print("  2. run `claude setup-token` (one-time per user)")
        print(
            "  3. add the token as repo secret CLAUDE_CODE_OAUTH_TOKEN "
            "via Settings → Secrets and variables → Actions"
        )
        print("  (same token works across multiple repos; see CONTRIBUTING.md for details)")
    return 0
