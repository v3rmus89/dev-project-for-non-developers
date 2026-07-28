"""Post-apply guidance: next-steps, restore hint, Makefile-overlap helpers.

Leaf orchestration module: imports only stdlib (and, when it needs them, the
base layer) — never `apply_pipeline`, never `adopt_ui`, never `cli`.
"""

import re
import shlex
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


def _format_restore_hint(manifest_path):
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(BOOTSTRAP_PY.resolve()))} --restore {shlex.quote(str(manifest_path))}"


def _print_post_apply_guidance(
    args,
    target_root,
    *,
    adopt,
    makefile_review_emitted=False,
    colliding_targets=(),
    base_makefile_written=False,
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
      - `make install-hooks` is gated on `base_makefile_written` in adopt mode:
        that target lives in the skill's Makefile, which only lands when we
        WRITE/OVERWRITE it; when the target owns its Makefile (SKIP) the target
        has no such recipe, so advertising it would fail (Tier-2 codex round-4);
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
        steps = []
        if not adopt:
            # Greenfield writes the language Makefile; adopt targets have their
            # own install flow, so the skill must not imply it created one.
            steps.append(f"  cd {target_root} && make install")
        if not adopt or base_makefile_written:
            # `make install-hooks` is defined by the skill's Makefile — only
            # advertise it when that Makefile actually landed (greenfield always;
            # adopt only when the base Makefile was WRITE/OVERWRITE). Advertising
            # it for an owned-Makefile SKIP would name a non-existent target
            # (Tier-2 codex round-4). In adopt the `cd … && make install` line
            # above is gated off, so the hooks step carries its own `cd` —
            # bootstrap is usually run from outside the target (Tier-2 codex
            # round-5). Greenfield keeps the bare form (the install line above
            # already cd'd in) so its output stays byte-identical.
            if adopt:
                steps.append(
                    f"  cd {target_root} && make install-hooks  "
                    "# registers git hooks, requires .git/"
                )
            else:
                steps.append("  make install-hooks  # registers git hooks, requires .git/")
        if steps:
            print("next steps:")
            for step in steps:
                print(step)

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
