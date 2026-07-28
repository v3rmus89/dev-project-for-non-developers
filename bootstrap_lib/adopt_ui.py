"""Interactive decide-phase UX for `--mode=adopt`.

Leaf orchestration module: imports only stdlib (and, when it needs them, the
base layer) — never `apply_pipeline`, never `guidance`, never `cli`.
"""

import difflib
import sys
from pathlib import Path

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
