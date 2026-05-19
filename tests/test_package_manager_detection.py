"""Unit tests for `bootstrap_lib.detect.detect_package_manager`.

The plan's Bucket D row enumerates cases (a) through (n) plus extras for
the Codex Tier-2 folds (e', g', g'', l'). All test names mirror the
plan's letter-code so evidence-table cross-references stay legible.
"""

import textwrap

import pytest

from bootstrap_lib.detect import DetectionResult, detect_package_manager


# ──────────────────────────────────────────────────────────────────────
# (a) (b) (m) (n) — input contract: greenfield + str/None accepted
# ──────────────────────────────────────────────────────────────────────


def test_case_a_nonexistent_dir(tmp_path):
    """(a) Path that doesn't exist → greenfield."""
    result = detect_package_manager(tmp_path / "does-not-exist")
    assert result.manager is None
    assert result.reason.startswith("greenfield")


def test_case_b_empty_existing_dir(tmp_path):
    """(b) Existing-but-empty dir → greenfield."""
    result = detect_package_manager(tmp_path)
    assert result.manager is None
    assert result.reason.startswith("greenfield")


def test_case_m_out_dir_none():
    """(m) Caller passes `None` (dry-run / diff mode) → greenfield."""
    result = detect_package_manager(None)
    assert result.manager is None
    assert result.reason.startswith("greenfield")


def test_case_n_out_dir_as_str(tmp_path):
    """(n) Caller passes `str` (argparse passes str, not Path) → same as Path."""
    (tmp_path / "uv.lock").write_text("")
    via_str = detect_package_manager(str(tmp_path))
    via_path = detect_package_manager(tmp_path)
    assert via_str == via_path
    assert via_str.manager == "uv"


# ──────────────────────────────────────────────────────────────────────
# (c) (d) (e) (e') — positive uv markers
# ──────────────────────────────────────────────────────────────────────


def test_case_c_uv_lock_only(tmp_path):
    """(c) uv.lock alone → uv (highest-priority marker)."""
    (tmp_path / "uv.lock").write_text("")
    result = detect_package_manager(tmp_path)
    assert result.manager == "uv"
    assert result.reason == "marker: uv.lock"


def test_case_d_tool_uv_table(tmp_path):
    """(d) pyproject.toml with [tool.uv] table → uv."""
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""
            [project]
            name = "x"
            version = "0.1.0"
            [tool.uv]
            dev-dependencies = []
        """).lstrip()
    )
    result = detect_package_manager(tmp_path)
    assert result.manager == "uv"
    assert "[tool.uv]" in result.reason


def test_case_e_uv_build_backend_kebab_case(tmp_path):
    """(e) [build-system] build-backend = "uv_build" (PEP 517 kebab-case key) → uv.

    Closes Codex Tier-2 #3: the canonical PEP 517 key is `build-backend`
    (kebab-case), not `backend`. Existing uv projects use this exact key
    in their pyproject.toml.
    """
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""
            [project]
            name = "x"
            version = "0.1.0"
            [build-system]
            requires = ["uv_build>=0.11,<0.12"]
            build-backend = "uv_build"
        """).lstrip()
    )
    result = detect_package_manager(tmp_path)
    assert result.manager == "uv"
    assert "uv_build" in result.reason


def test_case_e_prime_wrong_key_does_not_match(tmp_path):
    """(e') Negative — pyproject with the wrong key `backend = "uv_build"` does NOT match.

    Closes Codex Tier-2 #3: prevents the implementer from accidentally
    accepting either the kebab-case or snake-case form. The PEP 517
    standard is `build-backend` only; `backend` is not a recognized key.
    Without this test, an impl PR that checks `["backend"]` could ship
    silently and miss real uv adoption cases (since uv writes the
    standards-compliant kebab-case key).
    """
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""
            [project]
            name = "x"
            version = "0.1.0"
            [build-system]
            requires = ["uv_build>=0.11,<0.12"]
            backend = "uv_build"
        """).lstrip()
    )
    result = detect_package_manager(tmp_path)
    # Falls through to ambiguous (pyproject parses but has no uv/pip markers).
    assert result.manager is None
    assert result.reason.startswith("ambiguous")


# ──────────────────────────────────────────────────────────────────────
# (f) (g) (g') (g'') — positive pip markers (wildcard glob)
# ──────────────────────────────────────────────────────────────────────


def test_case_f_requirements_txt(tmp_path):
    """(f) requirements.txt alone → pip."""
    (tmp_path / "requirements.txt").write_text("")
    result = detect_package_manager(tmp_path)
    assert result.manager == "pip"
    assert "requirements.txt" in result.reason


def test_case_g_requirements_dev_txt(tmp_path):
    """(g) requirements-dev.txt alone → pip."""
    (tmp_path / "requirements-dev.txt").write_text("")
    result = detect_package_manager(tmp_path)
    assert result.manager == "pip"
    assert "requirements-dev.txt" in result.reason


def test_case_g_prime_requirements_test_txt(tmp_path):
    """(g') requirements-test.txt alone → pip.

    Closes Codex Tier-2 #4: Scope #2 promised `requirements*.txt`
    wildcard but the original rule only covered two specific names.
    This test locks in the glob contract for non-standard names.
    """
    (tmp_path / "requirements-test.txt").write_text("")
    result = detect_package_manager(tmp_path)
    assert result.manager == "pip"
    assert "requirements-test.txt" in result.reason


def test_case_g_double_prime_requirements_prod_txt(tmp_path):
    """(g'') requirements-prod.txt alone → pip.

    Closes Codex Tier-2 #4: same glob coverage, different filename.
    """
    (tmp_path / "requirements-prod.txt").write_text("")
    result = detect_package_manager(tmp_path)
    assert result.manager == "pip"
    assert "requirements-prod.txt" in result.reason


# ──────────────────────────────────────────────────────────────────────
# (h) (i) (j) (k) — priority ordering across marker combinations
# ──────────────────────────────────────────────────────────────────────


def test_case_h_pyproject_no_markers(tmp_path):
    """(h) pyproject with no PM markers, no requirements*.txt → ambiguous (manager=None).

    Closes Claude iter-2 #1: earlier draft returned manager="uv" here,
    which made the CLI ambiguous-advisory branch dead code. The CLI now
    applies the "uv" default itself.
    """
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""
            [project]
            name = "x"
            version = "0.1.0"
        """).lstrip()
    )
    result = detect_package_manager(tmp_path)
    assert result.manager is None
    assert result.reason.startswith("ambiguous")


def test_case_i_pyproject_no_markers_plus_requirements(tmp_path):
    """(i) pyproject (no markers) + requirements.txt → pip (positive pip marker beats ambiguous)."""
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""
            [project]
            name = "x"
            version = "0.1.0"
        """).lstrip()
    )
    (tmp_path / "requirements.txt").write_text("")
    result = detect_package_manager(tmp_path)
    assert result.manager == "pip"
    assert "requirements.txt" in result.reason


def test_case_j_uv_lock_plus_requirements(tmp_path):
    """(j) uv.lock + requirements.txt → uv (positive uv marker wins; common mid-migration)."""
    (tmp_path / "uv.lock").write_text("")
    (tmp_path / "requirements.txt").write_text("")
    result = detect_package_manager(tmp_path)
    assert result.manager == "uv"
    assert result.reason == "marker: uv.lock"


def test_case_k_tool_uv_plus_requirements(tmp_path):
    """(k) pyproject with [tool.uv] + requirements.txt → uv (positive uv marker beats positive pip)."""
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""
            [project]
            name = "x"
            version = "0.1.0"
            [tool.uv]
            dev-dependencies = []
        """).lstrip()
    )
    (tmp_path / "requirements.txt").write_text("")
    result = detect_package_manager(tmp_path)
    assert result.manager == "uv"
    assert "[tool.uv]" in result.reason


# ──────────────────────────────────────────────────────────────────────
# (l) (l') — malformed-pyproject graceful degrade + pip-marker preservation
# ──────────────────────────────────────────────────────────────────────


def test_case_l_malformed_pyproject_alone(tmp_path):
    """(l) malformed pyproject.toml (invalid TOML), no requirements*.txt → malformed (manager=None).

    Closes Claude iter-2 #4: detection must degrade gracefully on TOML
    parse errors rather than raising.
    """
    (tmp_path / "pyproject.toml").write_text("this is not [valid toml")
    result = detect_package_manager(tmp_path)
    assert result.manager is None
    assert result.reason.startswith("malformed")


def test_case_l_prime_malformed_pyproject_plus_requirements(tmp_path):
    """(l') malformed pyproject.toml + requirements.txt → pip (positive marker preserved).

    Closes Codex Tier-2 #5: without rule ordering (positive pip check
    BEFORE malformed-pyproject), the pip marker would be dropped and
    the project would default to uv. Real pip users with a temporarily
    broken pyproject would be mis-classified.
    """
    (tmp_path / "pyproject.toml").write_text("this is not [valid toml")
    (tmp_path / "requirements.txt").write_text("")
    result = detect_package_manager(tmp_path)
    assert result.manager == "pip"
    assert "requirements.txt" in result.reason


# ──────────────────────────────────────────────────────────────────────
# Table-shape + file-vs-directory robustness (Tier-1 Codex review folds)
# ──────────────────────────────────────────────────────────────────────


def test_scalar_tool_does_not_false_positive(tmp_path):
    """Scalar `tool = "uv"` (instead of `[tool] uv = {...}`) must NOT match rule 3.

    Closes Tier-1 Codex #1: without the `isinstance(..., dict)` guard,
    `"uv" in "uv"` (substring check on the string) would falsely return
    True, classifying a non-uv project as uv.
    """
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""
            [project]
            name = "x"
            version = "0.1.0"
            tool = "uv"
        """).lstrip()
    )
    result = detect_package_manager(tmp_path)
    # Falls through to ambiguous (pyproject parses but no PM markers).
    assert result.manager is None
    assert result.reason.startswith("ambiguous")


def test_scalar_tool_uv_does_not_false_positive(tmp_path):
    """Scalar `[tool] uv = "not-a-table"` (instead of `[tool.uv] ...`) must NOT match rule 3.

    Closes Tier-1 Codex #1: requires `tool.uv` itself to be a dict, not
    a string. Otherwise `"uv" in {"uv": "x"}` matches the key-presence
    check but `[tool.uv]` is supposed to mean "uv table is present".
    """
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""
            [project]
            name = "x"
            version = "0.1.0"
            [tool]
            uv = "not-a-table"
        """).lstrip()
    )
    result = detect_package_manager(tmp_path)
    assert result.manager is None
    assert result.reason.startswith("ambiguous")


def test_scalar_build_system_does_not_crash(tmp_path):
    """Scalar `build-system = "x"` (invalid PEP 517) must NOT crash rule 4.

    Closes Tier-1 Codex #1: without the `isinstance(..., dict)` guard,
    `"x".get("build-backend")` would raise AttributeError before the
    CLI default/advisory logic runs.
    """
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""
            [project]
            name = "x"
            version = "0.1.0"
            build-system = "x"
        """).lstrip()
    )
    # Should not raise.
    result = detect_package_manager(tmp_path)
    assert result.manager is None
    assert result.reason.startswith("ambiguous")


def test_uv_lock_as_directory_does_not_false_positive(tmp_path):
    """A directory named `uv.lock` must NOT match the file-marker check.

    Closes Tier-1 Codex #2: `.is_file()` (not `.exists()`) enforces the
    file-marker contract.
    """
    (tmp_path / "uv.lock").mkdir()
    result = detect_package_manager(tmp_path)
    # Greenfield because no other files exist either.
    assert result.manager is None
    assert result.reason.startswith("greenfield")


def test_requirements_as_directory_does_not_false_positive(tmp_path):
    """A directory named `requirements-test.txt` must NOT match the file-marker glob.

    Closes Tier-1 Codex #2: glob results filtered to `.is_file()`.
    """
    (tmp_path / "requirements-test.txt").mkdir()
    result = detect_package_manager(tmp_path)
    assert result.manager is None
    assert result.reason.startswith("greenfield")


# ──────────────────────────────────────────────────────────────────────
# Return-type contract: DetectionResult is a NamedTuple with two fields
# ──────────────────────────────────────────────────────────────────────


def test_detection_result_is_named_tuple(tmp_path):
    """The return type is a `DetectionResult` NamedTuple (class syntax form)."""
    result = detect_package_manager(tmp_path)
    assert isinstance(result, DetectionResult)
    assert hasattr(result, "manager")
    assert hasattr(result, "reason")
    # Tuple unpacking also works.
    manager, reason = result
    assert manager == result.manager
    assert reason == result.reason


@pytest.mark.parametrize(
    "out_dir_factory",
    [
        lambda tp: None,  # explicit None
        lambda tp: tp / "missing",  # nonexistent
        lambda tp: tp,  # empty existing
    ],
)
def test_greenfield_paths_all_return_none_manager(tmp_path, out_dir_factory):
    """Every greenfield-shape input returns manager=None with a 'greenfield'-prefixed reason."""
    result = detect_package_manager(out_dir_factory(tmp_path))
    assert result.manager is None
    assert result.reason.startswith("greenfield")
