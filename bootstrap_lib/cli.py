import argparse
import difflib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import traceback
from pathlib import Path

from bootstrap_lib import detect, io, manifest, paths, render
from bootstrap_lib._flags import PROJECT_NAME_RE, add_flags

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


def _allowed_actions_for(rel_path, policy=None):
    """Return the ordered list of allowed action keys for this file's prompt."""
    if policy == "NEUTRALIZE":
        # NEUTRALIZE is a two-entry mutation (append the `.gitignore` un-ignore
        # block + WRITE the command file). The generic mutating actions are all
        # UNSAFE here (iter-4 FN1): [n]ew would write an ignored `.new`,
        # [o]verwrite assumes the target file already exists, [a]ppend is
        # `.gitignore`-only. Offer ONLY recommended/skip/diff/help/quit.
        return ["r", "s", "d", "?", "q"]
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
    allowed = _allowed_actions_for(rel_path, rec.policy)

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
            if "n" in allowed:
                return _user_decision(
                    rec, "WRITE_NEW", "user chose [n]ew (.new alongside original)"
                )
            stdout.write(
                f"  [n]ew is not available for a {rec.policy} target (got {rel_path}); "
                "type [?] for valid actions\n"
            )
            continue
        if choice == "a":
            if "a" in allowed:
                return _user_decision(rec, "APPEND_MERGE", "user chose [a]ppend (line-level merge)")
            stdout.write(
                f"  [a]ppend is only available for .gitignore (got {rel_path}); "
                "type [?] for valid actions\n"
            )
            continue
        if choice == "o":
            if "o" not in allowed:
                stdout.write(
                    f"  [o]verwrite is not available for a {rec.policy} target (got {rel_path}); "
                    "type [?] for valid actions\n"
                )
                continue
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
        github_review_mode=args.github_review or "none",
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
        elif policy == "NEUTRALIZE":
            # TOCTOU re-check (mirrors WRITE_NEW's apply-time guard): analyze
            # validated `.gitignore` exists and lacks the sentinel, but it could
            # have changed in the apply window (incl. the interactive prompt). If
            # it vanished, or someone added the block, FAIL LOUD rather than
            # recreate-from-empty / no-op while the manifest still records the
            # block — either would make `--restore` remove user content or leave
            # a stray `.gitignore` (Tier-2 codex P2 on PR #35).
            if not target_full.exists():
                raise AdoptionCollisionError(
                    f"{entry['target_path']} disappeared between plan-time and apply-time; "
                    "bootstrap will NOT recreate it for NEUTRALIZE"
                )
            current_target = target_full.read_bytes()
            if manifest.NEUTRALIZE_SENTINEL.encode() in current_target:
                raise AdoptionCollisionError(
                    f"{entry['target_path']} gained the un-ignore block between plan-time and "
                    "apply-time; aborting so restore cannot reverse a block bootstrap did not add"
                )
            # Append the managed un-ignore block (NOT planned-file content).
            # `compute_neutralize_apply_bytes` preserves the trailing-newline
            # structure so the sentinel restore is byte-exact. Runs at tier 1 —
            # after any tier-0 APPEND_MERGE on the same `.gitignore` — so its
            # block is the last thing in the file.
            neutralized = manifest.compute_neutralize_apply_bytes(
                current_target, entry["neutralize_block"]
            )
            io.atomic_write(target_full, neutralized)
            # PRESERVE the original `.gitignore` mode (atomic_write makes a new
            # file) — never loosen a private ignore file to 0644. Fall back to
            # mode_after for legacy entries lacking mode_before.
            os.chmod(target_full, entry.get("mode_before") or entry["mode_after"])
        else:
            raise ValueError(
                f"unknown policy {policy!r} in v2 entry for {rel_path!r}; "
                "expected WRITE/OVERWRITE/WRITE_NEW/APPEND_MERGE/NEUTRALIZE "
                "(SKIP entries should NOT appear in v2 manifests)"
            )
        if first:
            _maybe_pause_after_first_write()
            first = False


def _print_post_apply_guidance(
    args,
    target_root,
    *,
    adopt,
    makefile_review_emitted=False,
    colliding_targets=(),
):
    """Print the shared post-apply guidance: next-steps + gh-repo-create hint +
    both-docs Codex hint + the CLAUDE_CODE_OAUTH_TOKEN secret step.

    Called from BOTH the v1 `--apply` success path and `_main_apply_adopt`
    (Bucket C / AD3) — a single source of truth so the two paths cannot drift
    (that drift is exactly what created the parked "mirror the gh-repo-create
    hint into adopt" BACKLOG item this folds).

    For `adopt=False` the output is byte-identical to the pre-extraction v1
    block (the v1 guidance tests in test_bootstrap_cli.py are the regression
    guard). Adopt adaptations:
      - the greenfield `cd … && make install` next-step is gated off — an adopt
        target already has its own install flow; the skill must not imply it
        created one;
      - when `makefile_review_emitted` is True, print the Bucket B
        `include Makefile.review` hint and name `colliding_targets` (the
        computed fragment-vs-target Makefile target overlap) as the ones to
        remove, so the advice is correct for ANY existing Makefile rather than
        hard-coded to the bot's `review`.

    `makefile_review_emitted` / `colliding_targets` are explicit because the
    helper cannot otherwise tell an emitted `Makefile.review` from a
    pre-existing or dropped one (iter-1 FN6) nor recompute the overlap
    (iter-2 FN2); both are values the caller already computed.
    """
    if args.language in ("python", "nodejs", "go"):
        print("next steps:")
        if not adopt:
            print(f"  cd {target_root} && make install")
        print("  make install-hooks  # registers git hooks, requires .git/")

    if makefile_review_emitted:
        # Bucket B: a standalone Makefile.review carries the plan-review
        # machinery into a target that owns its own Makefile (which adopt
        # SKIPs, so the inline `{% include %}` never lands). Tell the owner to
        # wire it in and which of their targets the fragment redefines — GNU
        # Make silently uses the last recipe (with an override warning).
        print("")
        print("plan-review machinery: a standalone Makefile.review was written.")
        print(f"  wire it in — add this line to {target_root}/Makefile:")
        print("    include Makefile.review")
        if colliding_targets:
            names = ", ".join(colliding_targets)
            print(
                f"  first remove your existing {names} target(s) — Makefile.review "
                "defines the same name(s), so GNU Make would override yours (with a warning)"
            )
        else:
            print(
                "  if your Makefile already defines review or review-plan targets, "
                "remove them — the fragment supersedes them"
            )
        print(
            "  note: Makefile.review's review-plan-by-codex / review-plan-by-claude "
            "supersede any older single-direction review-plan target you may have"
        )

    if args.github_review not in (None, "none"):
        # gh-repo-create hint. Two detection states: (a) the target is not in
        # a git work tree → it needs `git init` first; (b) it IS in one but
        # has no remote → only remote creation is needed.
        #
        # `has_git` is derived from `git rev-parse --is-inside-work-tree`, not
        # a filesystem `.git` check. Only git itself is authoritative: a
        # `.git` path check misclassifies linked worktrees / `--separate-git-dir`
        # layouts (`.git` is a FILE), a subdirectory of an existing parent
        # repo (no local `.git` — would wrongly suggest a nested `git init`),
        # and a stray non-gitlink file named `.git`. git is a hard prereq;
        # gh is optional, so this never shells out to gh. Detection fails
        # open: any error → treat as "no git" and print the full hint; apply
        # still succeeds.
        has_git = False
        has_remote = False
        try:
            inside = subprocess.run(
                ["git", "-C", str(target_root), "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            has_git = inside.returncode == 0 and inside.stdout.strip() == "true"
        except (OSError, subprocess.SubprocessError):
            # FileNotFoundError (git missing) is a subclass of OSError;
            # SubprocessError covers TimeoutExpired (not an OSError subclass).
            has_git = False
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


# Match a Makefile target definition: a target name at column 0 followed by a
# `:` that is NOT an assignment operator (`:=` / `::=`). This excludes variable
# assignments (`VAR := …`, `VAR ?= …` — the latter has no leading colon at all)
# and leading-`.` directives (`.PHONY`, `.DEFAULT_GOAL`) via the `[A-Za-z_]`
# first-char class. Recipe lines start with a tab, so they never match at ^.
_MAKE_TARGET_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\s*:(?![:=])", re.MULTILINE)


def _makefile_target_names(text):
    """Return the set of target names defined in Makefile `text`."""
    return set(_MAKE_TARGET_RE.findall(text))


def _compute_colliding_targets(target_root, review_fragment_bytes):
    """Return the sorted tuple of target names defined in BOTH the standalone
    `Makefile.review` fragment and the target's existing `Makefile` (R-B1 /
    iter-2 FN2).

    These are the names the owner must remove before `include Makefile.review`:
    GNU Make warns ("overriding recipe for target …") and silently keeps the
    LAST recipe for a redefined target, so a stale same-named target would
    shadow the fragment's. Computing the REAL overlap (rather than hard-coding
    the bot's `review`) keeps the include hint correct for ANY existing Makefile.
    Returns `()` when the target has no Makefile or nothing overlaps.
    """
    target_makefile = Path(target_root) / "Makefile"
    try:
        target_text = target_makefile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    fragment_text = review_fragment_bytes.decode("utf-8", errors="replace")
    overlap = _makefile_target_names(fragment_text) & _makefile_target_names(target_text)
    return tuple(sorted(overlap))


# The plan-review fragment carries this sentinel comment (it delimits the
# SELFTEST-OVERLAP block that tests/test_selftest_overlap.py guards, so it cannot
# silently disappear). Its presence in a target's Makefile means that Makefile
# already inlines the review machinery — e.g. a project previously bootstrapped
# greenfield by this skill — so a standalone Makefile.review + its include hint
# would be redundant and duplicate the inline targets.
_REVIEW_MACHINERY_SENTINEL = "SELFTEST-OVERLAP-BEGIN: shared/Makefile.review.tmpl"


def _makefile_has_review_machinery(target_root):
    """True if the target's existing Makefile already inlines the plan-review
    fragment (detected via the fragment's stable SELFTEST-OVERLAP sentinel)."""
    try:
        text = (Path(target_root) / "Makefile").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return _REVIEW_MACHINERY_SENTINEL in text


def _drop_planned_file(rel_path, planned_files, plan):
    """Remove `rel_path` from BOTH the planned_files dict AND the plan's
    `analyses` tuple, returning the new `(planned_files, plan)` pair.

    `manifest.plan_adoption_entries` requires every non-SKIP analysis to have a
    matching planned_files entry (it raises `ValueError` otherwise) and only
    writes paths present in the analyses — so the two MUST be pruned together.
    Centralising the drop here makes that synchronisation structural: the two
    prune sites in `_main_apply_adopt` (recommendation-keyed pass 1, and the
    post-decision pass 2) cannot desync the two structures.
    """
    new_planned = {k: v for k, v in planned_files.items() if k != rel_path}
    new_plan = plan._replace(analyses=tuple(a for a in plan.analyses if a.rel_path != rel_path))
    return new_planned, new_plan


def _main_apply_adopt(args, target_root, planned_files, context):
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

    # Bucket A: adopt brings the skill into a project that ALREADY has its own
    # source + tests, so the greenfield-only entrypoint/smoke placeholders
    # (python: src/main.py, tests/test_smoke.py) are never wanted — suppress
    # them from the planned set BEFORE analyze so they never become a rule-(a)
    # WRITE into production code. Greenfield `--apply` keeps them (this filter
    # is adopt-path-only). Adopt is Python-only today; the constant lists the
    # node/go stub names too, so this is already correct when their adopt ships.
    placeholders = render.GREENFIELD_ONLY_PLACEHOLDERS.get(args.language, frozenset())
    if placeholders:
        planned_files = {
            rel: content for rel, content in planned_files.items() if rel not in placeholders
        }

    # Bucket B: the plan-review machinery (the `make review` dispatcher,
    # review-plan/commit targets, loop helpers) lives inline inside the generated
    # Makefile via `{% include 'Makefile.review.tmpl' %}`. When the target OWNS a
    # Makefile, adopt SKIPs it (rule h) — so none of those targets land, yet the
    # six scripts they call DO (rule a). Provisionally render the fragment as a
    # standalone `Makefile.review` and add it to the planned set; analyze
    # classifies it rule-(a) WRITE (the target lacks it). The two-phase prune
    # after analyze drops it again when the target has no Makefile of its own
    # (the base Makefile is then itself written — inline include and all).
    MAKEFILE_REVIEW = "Makefile.review"
    # This planned file is injected AFTER render_all + the CLI-layer path-safety
    # sweep in main(), so validate it here too: the skill's two-layer path-safety
    # invariant requires every planned-file write to pass the CLI-layer check. The
    # name is a constant today (always safe), but the check keeps the invariant
    # intact and future-proofs it if the name ever derives from something else.
    paths.validate_target_path(target_root, MAKEFILE_REVIEW)
    review_fragment = render.render_makefile_review(context, language=args.language)
    planned_files = {**planned_files, MAKEFILE_REVIEW: review_fragment}

    try:
        adoption_plan = adopt.analyze_target(target_root, planned_files)
    except Exception as e:
        sys.stderr.write(f"adopt-mode analyze failed: {e}\n")
        if os.environ.get("DEV_PROJECT_SETUP_TRACEBACK"):
            traceback.print_exc()
        return 1

    # Bucket B prune, pass 1 — recommendation-keyed (iter-2 FN1); pass 2 below
    # re-checks against the owner's actual decision (codex P2). Keep the
    # standalone Makefile.review ONLY when the target's own Makefile is SKIPped
    # (it owns one — the fragment's targets otherwise never arrive). When the
    # base Makefile is itself written (rule-(a) WRITE for a missing Makefile,
    # rule-(b) OVERWRITE for an empty one), that written Makefile ALREADY inlines
    # the fragment, so the standalone copy is redundant — drop it from BOTH
    # planned_files AND the analyses tuple (manifest.plan_adoption_entries raises
    # ValueError for an analysis whose rel_path is absent from planned_files, and
    # silently omits a planned_files entry absent from the analyses).
    colliding_targets: tuple[str, ...] = ()
    base_makefile_skipped = any(
        a.rel_path == "Makefile" and a.recommendation.policy == "SKIP"
        for a in adoption_plan.analyses
    )
    # Keep the standalone ONLY when the target owns a Makefile (SKIP) that does
    # NOT already inline the review machinery. A Makefile byte-identical to — or
    # previously bootstrapped by — the skill already carries the fragment inline
    # (codex round-3 P2), so a standalone would be redundant and the include hint
    # would duplicate those targets; drop it in that case too. (The broader
    # re-adopt / upgrade-delta feature stays parked — this is just the stateless
    # "active Makefile already has the machinery" check, not prior-state tracking.)
    if base_makefile_skipped and not _makefile_has_review_machinery(target_root):
        colliding_targets = _compute_colliding_targets(target_root, review_fragment)
    else:
        planned_files, adoption_plan = _drop_planned_file(
            MAKEFILE_REVIEW, planned_files, adoption_plan
        )

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

    # Bucket B prune, pass 2 (codex P2). Pass 1 keyed on the Makefile
    # RECOMMENDATION, but the owner is prompted on their own Makefile and can
    # turn a SKIP into [o]verwrite (or [n]ew). If they OVERWRITE/WRITE the active
    # Makefile with the skill's — which inlines the fragment via `{% include %}` —
    # a standalone Makefile.review is redundant AND the include hint would create
    # duplicate `review` targets. Re-decide on the FINAL Makefile action: drop the
    # standalone iff the skill's Makefile became the active one. [n]ew leaves the
    # owner's Makefile active (skill → Makefile.new), so the standalone stays.
    if MAKEFILE_REVIEW in planned_files:
        final_makefile_policy = next(
            (a.recommendation.policy for a in decided_plan.analyses if a.rel_path == "Makefile"),
            None,
        )
        if final_makefile_policy in ("WRITE", "OVERWRITE"):
            colliding_targets = ()
            planned_files, decided_plan = _drop_planned_file(
                MAKEFILE_REVIEW, planned_files, decided_plan
            )

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

    # Bucket B emitted flag — ground-truth from the FINAL entries (codex round-2
    # P2). We "emitted" a standalone Makefile.review only if we actually
    # WRITE/OVERWRITE it: a target that already owns a Makefile.review can SKIP it
    # (keep theirs) or take [n]ew, leaving no fresh standalone — so the include
    # hint must not fire. (Pass 2 above separately prevents WRITING a redundant
    # standalone when the owner overwrites their Makefile.) Keying off the
    # base-Makefile recommendation alone left this true in the owns-both case.
    makefile_review_emitted = any(
        e["path"] == MAKEFILE_REVIEW and e["policy"] in ("WRITE", "OVERWRITE") for e in entries
    )
    if not makefile_review_emitted:
        colliding_targets = ()

    m = manifest.Manifest(
        # Resolve to absolute path — mirrors v1's _prepare_apply contract so
        # `bootstrap.py --restore <manifest>` works from any cwd. Without
        # `.resolve()`, a manifest written from cwd A with `--out ./target`
        # would record `target_root="target"` and silently fail to find
        # anything when restored from a different cwd (no files removed,
        # exit 0, user thinks rollback worked).
        target_root=str(Path(target_root).resolve()),
        github_review_mode=args.github_review or "none",
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
        if os.environ.get("DEV_PROJECT_SETUP_TRACEBACK"):
            traceback.print_exc()
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
    # Bucket C: give the adopt success path the same next-steps / gh-repo / token
    # guidance the v1 path prints (folds the parked gh-repo-create mirror item).
    # Bucket B: when a standalone Makefile.review was emitted (the target owns a
    # Makefile), the helper also prints the `include Makefile.review` hint naming
    # the computed colliding_targets.
    _print_post_apply_guidance(
        args,
        target_root,
        adopt=True,
        makefile_review_emitted=makefile_review_emitted,
        colliding_targets=colliding_targets,
    )
    return 0


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
