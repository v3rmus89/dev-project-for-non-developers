"""First test coverage for scripts/migrate-selftest-block.py (iter-2 FN3).

Bucket B extended the script to carry prompts/*.txt + the substitution helper
alongside the sentinel-block re-sync (a migrated Makefile without them would
reference prompt files the downstream does not have). Fixture-driven:

  1. dry-run — diff shows the stale block line AND names the prompt files +
     helper; nothing is written; exit 1 (changes pending).
  2. --apply — block restored byte-equal to the skill repo's, files copied,
     helper landed 0755; exit 0.
  3. end-to-end — the migrated fixture's `make review` resolves its target
     under REVIEW_RESOLVE=1 (no real CLI), proving the wired path works.
  4. already-in-sync — exit 0 and no-op.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from bootstrap_lib import render

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"
MIGRATE = SKILL_ROOT / "scripts" / "migrate-selftest-block.py"

# The files the migration must carry (derived here from the shipped-inventory
# map so the script's glob-based set cannot silently drift from what ships).
PROMPT_RELS = sorted(rel for rel in render.SHARED_VERBATIM_MAP if rel.startswith("prompts/"))
HELPER_REL = "scripts/render-review-prompt.py"


def _bootstrap_fixture(tmp_path):
    target = tmp_path / "downstream"
    result = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--project-name",
            "downstream",
            "--out",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return target


def _make_stale_downstream(tmp_path):
    """A downstream project whose sentinel block is stale and which lacks the
    prompt files + helper (the pre-Bucket-B downstream state the migration
    exists to fix)."""
    target = _bootstrap_fixture(tmp_path)
    makefile = target / "Makefile"
    text = makefile.read_text()
    stale_marker = "# STALE-DOWNSTREAM-LINE (pre-migration state)"
    needle = "PLAN_FILE                ?="
    assert needle in text
    makefile.write_text(text.replace(needle, f"{stale_marker}\n{needle}", 1))
    shutil.rmtree(target / "prompts")
    (target / HELPER_REL).unlink()
    return target, stale_marker


def _run_migrate(target_makefile, *extra):
    return subprocess.run(
        [sys.executable, str(MIGRATE), "--target", str(target_makefile), *extra],
        capture_output=True,
        text=True,
    )


def _skill_block(text):
    lines = text.splitlines()
    begin = next(i for i, line in enumerate(lines) if "SELFTEST-OVERLAP-BEGIN" in line)
    end = next(i for i, line in enumerate(lines) if "SELFTEST-OVERLAP-END" in line)
    return "\n".join(lines[begin : end + 1])


def test_dry_run_names_changes_and_writes_nothing(tmp_path):
    target, stale_marker = _make_stale_downstream(tmp_path)
    makefile = target / "Makefile"
    before = makefile.read_text()

    result = _run_migrate(makefile)
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    # The block diff shows the stale line leaving.
    assert f"-{stale_marker}" in result.stdout, result.stdout
    # Every prompt file + the helper is named as a pending copy.
    for rel in [*PROMPT_RELS, HELPER_REL]:
        assert f"{rel} (new)" in result.stdout, f"dry-run must name {rel}: {result.stdout}"
    # Nothing was written.
    assert makefile.read_text() == before, "dry-run must not modify the Makefile"
    assert not (target / "prompts").exists(), "dry-run must not copy prompt files"
    assert not (target / HELPER_REL).exists(), "dry-run must not copy the helper"


def test_apply_lands_block_files_and_helper_exec_bit(tmp_path):
    target, stale_marker = _make_stale_downstream(tmp_path)
    makefile = target / "Makefile"

    result = _run_migrate(makefile, "--apply")
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)

    migrated = makefile.read_text()
    assert stale_marker not in migrated, "stale block line must be replaced"
    assert _skill_block(migrated) == _skill_block((SKILL_ROOT / "Makefile").read_text()), (
        "migrated sentinel block must be byte-equal to the skill repo's"
    )
    for rel in PROMPT_RELS:
        assert (target / rel).read_bytes() == (SKILL_ROOT / rel).read_bytes(), (
            f"{rel} must be copied byte-equal"
        )
    helper = target / HELPER_REL
    assert helper.read_bytes() == (SKILL_ROOT / HELPER_REL).read_bytes()
    assert os.access(helper, os.X_OK), "helper must land executable (0755)"
    assert (helper.stat().st_mode & 0o777) == 0o755


def test_apply_then_review_resolves_end_to_end(tmp_path):
    """The wired path proven end-to-end: after migration, the fixture's own
    `make review` dispatcher resolves its target under REVIEW_RESOLVE=1 —
    target resolution without invoking a real CLI (iter-2 FN3)."""
    target, _stale_marker = _make_stale_downstream(tmp_path)
    assert _run_migrate(target / "Makefile", "--apply").returncode == 0

    env = os.environ.copy()
    env.pop("REVIEWER", None)
    env.pop("ACTOR", None)
    result = subprocess.run(
        ["make", "-C", str(target), "review", "MODE=plan", "ACTOR=claude", "REVIEW_RESOLVE=1"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    resolved = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert "review-plan-by-codex" in resolved, resolved


def test_symlinked_prompts_dir_escape_is_refused(tmp_path):
    """Tier-2 codex P1 (PR #52): a downstream whose prompts/ is a symlink
    pointing OUTSIDE the project must be refused loudly (exit 2) in BOTH
    modes — --apply would otherwise write through it to an unrelated path,
    and even dry-run reads through it."""
    target, _stale_marker = _make_stale_downstream(tmp_path)
    outside = tmp_path / "outside-project"
    outside.mkdir()
    (target / "prompts").symlink_to(outside, target_is_directory=True)

    for extra in ([], ["--apply"]):
        result = _run_migrate(target / "Makefile", *extra)
        assert result.returncode == 2, (extra, result.returncode, result.stdout, result.stderr)
        assert "refusing" in result.stderr, result.stderr
        assert list(outside.iterdir()) == [], f"escape wrote outside the project ({extra})"


def test_symlinked_helper_file_escape_is_refused(tmp_path):
    """Same class, file form: scripts/render-review-prompt.py as a symlink to
    a file outside the project must be refused, and the pointee untouched."""
    target, _stale_marker = _make_stale_downstream(tmp_path)
    pointee = tmp_path / "outside-file.py"
    pointee.write_text("ORIGINAL OUTSIDE CONTENT")
    (target / HELPER_REL).symlink_to(pointee)

    result = _run_migrate(target / "Makefile", "--apply")
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "refusing" in result.stderr, result.stderr
    assert pointee.read_text() == "ORIGINAL OUTSIDE CONTENT", "pointee was overwritten"


def test_helper_mode_only_drift_is_detected_and_repaired(tmp_path):
    """Tier-2 codex P2 (PR #52): a byte-identical helper that lost its exec
    bit breaks every rewired recipe (permission denied), so mode drift IS
    drift — dry-run names it, --apply repairs to 0755."""
    target = _bootstrap_fixture(tmp_path)
    helper = target / HELPER_REL
    helper.chmod(0o644)

    dry = _run_migrate(target / "Makefile")
    assert dry.returncode == 1, (dry.returncode, dry.stdout, dry.stderr)
    assert f"{HELPER_REL} (mode)" in dry.stdout, dry.stdout
    assert (helper.stat().st_mode & 0o777) == 0o644, "dry-run must not chmod"

    applied = _run_migrate(target / "Makefile", "--apply")
    assert applied.returncode == 0, (applied.returncode, applied.stdout, applied.stderr)
    assert (helper.stat().st_mode & 0o777) == 0o755
    assert _run_migrate(target / "Makefile").returncode == 0, "must be in sync after repair"


def test_in_sync_target_is_a_noop_exit_0(tmp_path):
    """A freshly bootstrapped project already matches the skill repo (block +
    files) — the migration must report in-sync and exit 0."""
    target = _bootstrap_fixture(tmp_path)
    result = _run_migrate(target / "Makefile")
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert "already in sync" in result.stdout


def test_migration_set_matches_shipped_inventory():
    """Drift guard: the script's glob-derived carry set must equal the
    prompts/ entries of SHARED_VERBATIM_MAP plus the helper — a prompt file
    added to the inventory but not picked up by the migration (or vice versa)
    fails here, not in a downstream repo."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("migrate_selftest_block", MIGRATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._files_to_carry() == [*PROMPT_RELS, HELPER_REL]


def test_symlinked_target_does_not_reroot_the_migration(tmp_path):
    """Tier-2 P2 (PR #52): `--target` pointing at a SYMLINKED Makefile must not
    move the migration to the symlink's real directory.

    The old `args.target.resolve().parent` followed the link, so every carried
    file landed next to the pointee instead of in the project the operator
    named — the same escape class already guarded for a symlinked `prompts/`
    dir and helper file, just on the `--target` argument. Codex claimed this
    was fixed in commit `ddcfbed`; that object does not exist in this repo, so
    the fix is landed and tested here instead.
    """
    target, _stale_marker = _make_stale_downstream(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    real_makefile = elsewhere / "Makefile"
    real_makefile.write_text((target / "Makefile").read_text())

    link = target / "Makefile.link"
    link.symlink_to(real_makefile)

    result = _run_migrate(link, "--apply")
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)

    # Carried files belong beside the symlink the operator named...
    assert (target / HELPER_REL).is_file(), "helper did not land in the named project"
    # ...and must NOT have been rerouted next to the pointee.
    assert not (elsewhere / HELPER_REL).exists(), (
        "migration followed the symlinked --target and wrote outside the named project"
    )
    for rel in PROMPT_RELS:
        assert not (elsewhere / rel).exists(), f"{rel} was rerouted to the pointee's directory"


def test_failed_copy_leaves_makefile_unmodified(tmp_path):
    """Tier-2 P1 (PR #52): a mid-apply copy failure must not leave the Makefile
    rewritten to reference files that were never installed.

    The Makefile edit is what points the recipes at prompts/ and the helper, so
    writing it before the copies meant any failure in the copy loop produced a
    broken target with the sentinel block already consumed and no restore path.
    Copies now run first. Simulated by making the destination prompts/ directory
    read-only so the copy loop raises partway through.
    """
    target, stale_marker = _make_stale_downstream(tmp_path)
    before = (target / "Makefile").read_text()
    assert stale_marker in before, "fixture should start stale"

    prompts_dir = target / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.chmod(0o500)  # readable/traversable, not writable
    try:
        result = _run_migrate(target / "Makefile", "--apply")
    finally:
        prompts_dir.chmod(0o755)

    assert result.returncode != 0, (
        f"a failed copy must not report success: {result.returncode}\n{result.stdout}"
    )
    assert (target / "Makefile").read_text() == before, (
        "Makefile was rewritten despite the copy loop failing — it now references "
        "prompt files that were never installed"
    )
