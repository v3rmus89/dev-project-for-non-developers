"""Apply-phase pipeline for plain `--apply` and `--apply --mode=adopt`.

Sits between `cli` and the base layer: imports `adopt_ui` + `guidance` (the
decide-phase UX and the post-apply guidance `_main_apply_adopt` orchestrates)
plus the base layer — never `cli`.
"""

import os
import sys
import time
import traceback
from pathlib import Path

from bootstrap_lib import adopt, io, manifest, paths, render
from bootstrap_lib.adopt import AdoptionCollisionError, compute_append_merge_bytes
from bootstrap_lib.adopt_ui import _AdoptionAbort, _interactive_decide
from bootstrap_lib.guidance import (
    _compute_colliding_targets,
    _format_restore_hint,
    _makefile_has_review_machinery,
    _print_post_apply_guidance,
)


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
    caught.
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
    manifest path available even if writes fail mid-apply
    (the restore hint must still print on partial-apply failure).

    Does NOT create `target_root` here: mkdir
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
    """Apply v2 entries per the per-policy write contract.

    Replaces the plain `_apply_writes` flow when `--mode=adopt`. SKIP entries
    are NOT in the manifest (mutation-only contract), so the loop never sees
    them. Each remaining policy uses `io.atomic_write` (tmp + os.replace) for
    crash-safety — the v1 crash-safety contract carried into v2.

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
            # a stray `.gitignore`.
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
         restore can roll back partial-apply (the manifest-before-writes
         contract carried into adopt-mode).
      6. _apply_adoption_writes(...) → atomic writes per policy.

    Returns the exit code. _AdoptionAbort / AdoptionCollisionError both
    map to exit 2 (fail-loud CI contract); mid-write exceptions map to
    exit 1 with a restore hint.
    """
    # Adopt brings the skill into a project that ALREADY has its own
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

    # The plan-review machinery (the `make review` dispatcher,
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

    # Standalone-Makefile.review prune, pass 1 — recommendation-keyed; pass 2
    # below re-checks against the owner's actual decision. Keep the
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
    # previously bootstrapped by — the skill already carries the fragment inline,
    # so a standalone would be redundant and the include hint
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

    # Standalone-Makefile.review prune, pass 2. Pass 1 keyed on the Makefile
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

    # Emitted flag — ground-truth from the FINAL entries.
    # We "emitted" a standalone Makefile.review only if we actually
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
    # Whether the skill's Makefile (which defines `install-hooks`) actually
    # landed — gates the `make install-hooks` next-step so adopt never advertises
    # a target absent from the owner's own Makefile.
    base_makefile_written = any(
        e["path"] == "Makefile" and e["policy"] in ("WRITE", "OVERWRITE") for e in entries
    )

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
    # Give the adopt success path the same next-steps / gh-repo / token
    # guidance the v1 path prints.
    # When a standalone Makefile.review was emitted (the target owns a
    # Makefile), the helper also prints the `include Makefile.review` hint naming
    # the computed colliding_targets.
    _print_post_apply_guidance(
        args,
        target_root,
        adopt=True,
        makefile_review_emitted=makefile_review_emitted,
        colliding_targets=colliding_targets,
        base_makefile_written=base_makefile_written,
    )
    return 0
