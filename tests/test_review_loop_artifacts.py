"""Tests for plan-review loop integrity artifacts (Bucket B + C).

Closes:
- PR #10 V-3  (snapshot created before each integer iter)
- PR #10 V-4  (hash check aborts on UNACKNOWLEDGED external modification)
- PR #10 V-4.5 (legitimate fold + consistency-check + loop-ack succeeds)
- PR #10 V-5  (hash check skipped on ITERATION=1)
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_PY = SKILL_ROOT / "bootstrap.py"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _bootstrap_fixture(tmp_path):
    target = tmp_path / "proj"
    result = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_PY),
            "--apply",
            "--language",
            "python",
            "--project-name",
            "fixture",
            "--out",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return target


def _shim_dir(tmp_path):
    """Shims for codex and claude that write canned output and exit 0."""
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir()

    codex = shim_dir / "codex"
    codex.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import sys
            argv = sys.argv[1:]
            if "--version" in argv:
                print("codex-cli 0.130.0")
                sys.exit(0)
            out = None
            i = 0
            while i < len(argv):
                if argv[i] == "--output-last-message":
                    out = argv[i + 1]; i += 2; continue
                i += 1
            if out:
                with open(out, "w") as f:
                    f.write("CANNED CODEX OUTPUT\\n")
            """
        )
    )
    codex.chmod(0o755)

    claude = shim_dir / "claude"
    claude.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import sys
            argv = sys.argv[1:]
            if "--version" in argv:
                print("2.1.139 (Claude Code)")
                sys.exit(0)
            print("CANNED CLAUDE OUTPUT")
            """
        )
    )
    claude.chmod(0o755)
    return shim_dir


def _plan_file(target, slug="_loop_test_plan"):
    plan_dir = target / "docs" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / f"{slug}.md"
    plan_file.write_text("# loop test plan\nbody\n")
    return plan_file


def _compute_key(project_dir, plan_file):
    """Mirrors the Make KEY: sha256(realpath(CURDIR)+':'+realpath(PLAN_FILE))[:12]."""
    k = os.path.realpath(str(project_dir)) + ":" + os.path.realpath(str(plan_file))
    return hashlib.sha256(k.encode()).hexdigest()[:12]


def _artifact_paths(project_dir, plan_file):
    key = _compute_key(project_dir, plan_file)
    return (
        Path(f"/tmp/plan-review-{key}.hash"),
        Path(f"/tmp/plan-review-{key}.consistency"),
        Path(f"/tmp/plan-snapshots/{key}"),
    )


def _clean(hash_file, cons_file, snap_dir):
    hash_file.unlink(missing_ok=True)
    cons_file.unlink(missing_ok=True)
    shutil.rmtree(snap_dir, ignore_errors=True)


# ── V-5: hash check skipped on ITERATION=1 ───────────────────────────────────


def test_v5_hash_check_skipped_on_iter1(tmp_path):
    """V-5: no hash file → ITERATION=1 must succeed and create the hash file."""
    target = _bootstrap_fixture(tmp_path)
    plan = _plan_file(target, "v5_plan")
    shim_dir = _shim_dir(tmp_path)
    hash_file, cons_file, snap_dir = _artifact_paths(target, plan)
    _clean(hash_file, cons_file, snap_dir)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out_file = tmp_path / "out-v5.md"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1",
            f"PLAN_REVIEW_OUT_CODEX={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"iter1 should succeed with no hash file:\n{result.stderr}"
    assert hash_file.exists(), "hash file should be written after iter1"

    _clean(hash_file, cons_file, snap_dir)


# ── V-3: snapshot created before each integer iter ───────────────────────────


def test_v3_snapshot_created_before_iter(tmp_path):
    """V-3: snapshot dir/iter1.bak must exist and match the plan after iter1."""
    target = _bootstrap_fixture(tmp_path)
    plan = _plan_file(target, "v3_plan")
    shim_dir = _shim_dir(tmp_path)
    hash_file, cons_file, snap_dir = _artifact_paths(target, plan)
    _clean(hash_file, cons_file, snap_dir)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out_file = tmp_path / "out-v3.md"

    result = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1",
            f"PLAN_REVIEW_OUT_CODEX={out_file}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"iter1 failed:\n{result.stderr}"

    snap_path = snap_dir / "iter1.bak"
    assert snap_path.exists(), f"snapshot not created at {snap_path}"
    assert snap_path.read_text() == plan.read_text(), "snapshot content differs from plan"

    _clean(hash_file, cons_file, snap_dir)


# ── V-4: hash check aborts on unacknowledged external modification ────────────


def test_v4_hash_check_aborts_on_unacknowledged_edit(tmp_path):
    """V-4: edit plan after iter1 WITHOUT loop-ack → iter2 must exit 2."""
    target = _bootstrap_fixture(tmp_path)
    plan = _plan_file(target, "v4_plan")
    shim_dir = _shim_dir(tmp_path)
    hash_file, cons_file, snap_dir = _artifact_paths(target, plan)
    _clean(hash_file, cons_file, snap_dir)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out1 = tmp_path / "out-v4-iter1.md"
    out2 = tmp_path / "out-v4-iter2.md"

    # iter 1 — succeeds
    r1 = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1",
            f"PLAN_REVIEW_OUT_CODEX={out1}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0, f"iter1 failed:\n{r1.stderr}"

    # Unacknowledged edit
    plan.write_text("# loop test plan\nbody\nUNACKNOWLEDGED EDIT\n")

    # iter 2 — must abort with exit 2
    r2 = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=2",
            f"PLAN_REVIEW_OUT_CODEX={out2}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    # hash-check uses `exit 2`; Make wraps recipe failures as exit 2 of its own,
    # and prints "Error 2" in stderr confirming the recipe's specific exit code.
    assert r2.returncode != 0, (
        f"iter2 should fail on hash mismatch; got returncode {r2.returncode}"
    )
    assert "Error 2" in r2.stderr, (
        f"expected 'Error 2' in stderr (recipe exit 2); got {r2.stderr!r}"
    )
    assert "loop-ack" in r2.stdout, "abort message must mention loop-ack"

    _clean(hash_file, cons_file, snap_dir)


# ── V-4.5: legitimate fold + consistency + loop-ack succeeds ─────────────────


def test_v4_5_legitimate_fold_with_consistency_and_ack(tmp_path):
    """V-4.5: fold → consistency → loop-ack → iter2 succeeds.
    Also asserts that skipping consistency makes loop-ack exit 3.
    """
    target = _bootstrap_fixture(tmp_path)
    plan = _plan_file(target, "v45_plan")
    shim_dir = _shim_dir(tmp_path)
    hash_file, cons_file, snap_dir = _artifact_paths(target, plan)
    _clean(hash_file, cons_file, snap_dir)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    out1 = tmp_path / "out-v45-iter1.md"
    out2 = tmp_path / "out-v45-iter2.md"
    cons_out = tmp_path / "out-v45-cons.md"

    # iter 1
    r1 = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1",
            f"PLAN_REVIEW_OUT_CODEX={out1}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0, f"iter1 failed:\n{r1.stderr}"

    # Simulate a legitimate fold
    plan.write_text("# loop test plan\nbody\nFOLDED CONTENT\n")

    # Attempt loop-ack WITHOUT consistency → must fail with "Error 3" (no marker)
    r_ack_no_cons = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "loop-ack",
            f"PLAN_FILE={plan.relative_to(target)}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    # Make wraps recipe exit codes into Make's own exit 2; check stderr for "Error 3"
    assert r_ack_no_cons.returncode != 0, (
        "loop-ack without consistency marker should fail"
    )
    assert "Error 3" in r_ack_no_cons.stderr, (
        f"expected 'Error 3' in stderr (recipe exit 3); got {r_ack_no_cons.stderr!r}"
    )
    assert "consistency" in r_ack_no_cons.stdout.lower(), (
        "error message should reference running the consistency check"
    )

    # Run consistency-by-claude (writes CONS_FILE)
    r_cons = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-consistency-by-claude",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=1.5",
            f"PLAN_CONSISTENCY_OUT={cons_out}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r_cons.returncode == 0, f"consistency check failed:\n{r_cons.stderr}"
    assert cons_file.exists(), "CONS_FILE should be written after consistency check"

    # loop-ack should now succeed
    r_ack = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "loop-ack",
            f"PLAN_FILE={plan.relative_to(target)}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r_ack.returncode == 0, (
        f"loop-ack should succeed after consistency check; got {r_ack.returncode}.\n"
        f"stdout={r_ack.stdout!r}"
    )

    # HASH_FILE should contain sha256 of the folded plan
    shasum = subprocess.run(
        ["shasum", "-a", "256", str(plan)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()[0]
    assert hash_file.read_text().strip() == shasum, (
        "HASH_FILE content must equal sha256 of the post-fold plan"
    )

    # iter 2 should succeed (hash matches)
    r2 = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "review-plan-by-codex",
            f"PLAN_FILE={plan.relative_to(target)}",
            "ITERATION=2",
            f"PLAN_REVIEW_OUT_CODEX={out2}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0, f"iter2 should succeed after loop-ack:\n{r2.stderr}"

    # Edit plan AGAIN without running consistency → loop-ack must exit 3 (stale marker)
    plan.write_text("# loop test plan\nbody\nFOLDED CONTENT\nEDIT AFTER ACK\n")
    r_ack_stale = subprocess.run(
        [
            "make",
            "-C",
            str(target),
            "loop-ack",
            f"PLAN_FILE={plan.relative_to(target)}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r_ack_stale.returncode != 0, (
        "loop-ack with stale marker should fail"
    )
    assert "Error 3" in r_ack_stale.stderr, (
        f"expected 'Error 3' in stderr (recipe exit 3); got {r_ack_stale.stderr!r}"
    )
    assert "consistency" in r_ack_stale.stdout.lower(), (
        "stale-marker message should reference running consistency check"
    )

    _clean(hash_file, cons_file, snap_dir)
