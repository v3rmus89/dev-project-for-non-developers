"""Tests for scripts/propagate-shared-rules.py and bootstrap_lib/section_extract.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from bootstrap_lib.section_extract import extract_heading_section

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "propagate-shared-rules.py"


def _load_script_module():
    """Load the script as a module so we can call its extract_heading_section directly."""
    spec = importlib.util.spec_from_file_location("propagate_shared_rules", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HEADING = "## Test section"
OTHER_HEADING = "## Other section"
SECTION_BODY = "Body line one.\nBody line two."
OTHER_BODY = "Other content."


def _make_doc(heading: str, body: str, suffix: str = "") -> str:
    parts = [f"# Preamble\n\n{heading}\n\n{body}\n"]
    if suffix:
        parts.append(f"\n{OTHER_HEADING}\n\n{suffix}\n")
    return "".join(parts)


# ── cross-check: script inline logic must match bootstrap_lib module ─────────


@pytest.mark.parametrize(
    "text, heading",
    [
        # mid-file section with a following section
        (
            _make_doc(HEADING, SECTION_BODY, suffix=OTHER_BODY),
            HEADING,
        ),
        # trailing section (no following ## )
        (
            _make_doc(HEADING, SECTION_BODY, suffix=OTHER_BODY),
            OTHER_HEADING,
        ),
        # heading at start of file (no preamble)
        (
            f"{HEADING}\n\n{SECTION_BODY}\n",
            HEADING,
        ),
    ],
)
def test_script_inline_extraction_matches_module(text, heading):
    """The inline extract_heading_section in the script must produce the same output
    as bootstrap_lib.section_extract.extract_heading_section for identical inputs.
    This prevents the two copies from drifting silently."""
    script_mod = _load_script_module()
    assert script_mod.extract_heading_section(text, heading) == extract_heading_section(
        text, heading
    )


def test_script_inline_error_on_missing_matches_module():
    script_mod = _load_script_module()
    text = "# Preamble\nSome text."
    with pytest.raises(ValueError):
        script_mod.extract_heading_section(text, HEADING)
    with pytest.raises(ValueError):
        extract_heading_section(text, HEADING)


def test_script_inline_error_on_duplicate_matches_module():
    script_mod = _load_script_module()
    text = _make_doc(HEADING, SECTION_BODY) + _make_doc(HEADING, "second copy")
    with pytest.raises(ValueError):
        script_mod.extract_heading_section(text, HEADING)
    with pytest.raises(ValueError):
        extract_heading_section(text, HEADING)


# ── regression: inline prose mention of the heading text (Tier-2 codex P2) ────


def _doc_with_inline_mention(heading: str, body: str, suffix: str = "") -> str:
    """A doc where `heading`'s text appears BOTH in prose (inline, not a real
    heading line) AND as the actual `## ` heading line. The old substring
    `text.count()` saw 2 and raised "found 2 times"; line-anchored sees 1."""
    parts = [
        "# Preamble\n\n",
        f"See the {heading} section below for the rules.\n\n",  # inline mention
        f"{heading}\n\n{body}\n",  # the real heading line
    ]
    if suffix:
        parts.append(f"\n{OTHER_HEADING}\n\n{suffix}\n")
    return "".join(parts)


def test_inline_mention_not_counted_as_duplicate_both_copies():
    """The inline mention must NOT trip the duplicate guard; both copies extract
    the real section's body."""
    script_mod = _load_script_module()
    text = _doc_with_inline_mention(HEADING, SECTION_BODY)
    assert extract_heading_section(text, HEADING) == SECTION_BODY
    assert script_mod.extract_heading_section(text, HEADING) == SECTION_BODY


def test_replace_section_ignores_inline_mention():
    """_replace_section must also line-anchor: an inline mention is preserved
    verbatim, and only the REAL section's body is replaced."""
    script_mod = _load_script_module()
    text = _doc_with_inline_mention(HEADING, "old body", suffix="tail")
    out = script_mod._replace_section(text, HEADING, "new body")
    assert f"See the {HEADING} section below for the rules." in out, (
        "the inline prose mention must be preserved, not rewritten"
    )
    assert script_mod.extract_heading_section(out, HEADING) == "new body"
    assert script_mod.extract_heading_section(out, OTHER_HEADING) == "tail"
    assert "old body" not in out


# ── extract_heading_section unit tests ────────────────────────────────────────


def test_extract_finds_section():
    text = _make_doc(HEADING, SECTION_BODY)
    assert extract_heading_section(text, HEADING) == SECTION_BODY


def test_extract_stops_at_next_section():
    text = _make_doc(HEADING, SECTION_BODY, suffix=OTHER_BODY)
    assert extract_heading_section(text, HEADING) == SECTION_BODY
    assert extract_heading_section(text, OTHER_HEADING) == OTHER_BODY


def test_extract_missing_heading_raises():
    with pytest.raises(ValueError, match="not found"):
        extract_heading_section("# Preamble\nSome text.", HEADING)


def test_extract_duplicate_heading_raises():
    text = _make_doc(HEADING, SECTION_BODY) + _make_doc(HEADING, "second copy")
    with pytest.raises(ValueError, match="2 times"):
        extract_heading_section(text, HEADING)


# ── propagate-shared-rules.py integration tests ──────────────────────────────


def _run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_dry_run_already_in_sync(tmp_path):
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    content = _make_doc(HEADING, SECTION_BODY)
    source.write_text(content)
    target.write_text(content)

    result = _run_script("--section", HEADING, "--source", str(source), str(target))
    assert result.returncode == 0
    assert "already in sync" in result.stdout
    assert target.read_text() == content


def test_dry_run_shows_diff_without_writing(tmp_path):
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    source.write_text(_make_doc(HEADING, "New body."))
    original_target = _make_doc(HEADING, "Old body.")
    target.write_text(original_target)

    result = _run_script("--section", HEADING, "--source", str(source), str(target))
    assert result.returncode == 1
    assert "-Old body." in result.stdout
    assert "+New body." in result.stdout
    assert target.read_text() == original_target, "dry-run must not write"


def test_apply_writes_change(tmp_path):
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    source.write_text(_make_doc(HEADING, "New body."))
    target.write_text(_make_doc(HEADING, "Old body."))

    result = _run_script("--apply", "--section", HEADING, "--source", str(source), str(target))
    assert result.returncode == 0
    assert extract_heading_section(target.read_text(), HEADING) == "New body."


def test_apply_preserves_other_sections(tmp_path):
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    source.write_text(_make_doc(HEADING, "New body."))
    target.write_text(_make_doc(HEADING, "Old body.", suffix=OTHER_BODY))

    _run_script("--apply", "--section", HEADING, "--source", str(source), str(target))
    updated = target.read_text()
    assert extract_heading_section(updated, HEADING) == "New body."
    assert extract_heading_section(updated, OTHER_HEADING) == OTHER_BODY


def test_missing_heading_in_target_exits_2(tmp_path):
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    source.write_text(_make_doc(HEADING, "Body."))
    target.write_text("# Preamble\n\nNo managed section here.\n")

    result = _run_script("--section", HEADING, "--source", str(source), str(target))
    assert result.returncode == 2
    assert "not found" in result.stderr


def test_duplicate_heading_in_target_exits_2(tmp_path):
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    source.write_text(_make_doc(HEADING, "Body."))
    dup = _make_doc(HEADING, "First.") + _make_doc(HEADING, "Second.")
    target.write_text(dup)

    result = _run_script("--section", HEADING, "--source", str(source), str(target))
    assert result.returncode == 2
    assert "2 times" in result.stderr


def test_missing_target_file_exits_2(tmp_path):
    source = tmp_path / "source.md"
    source.write_text(_make_doc(HEADING, "Body."))

    result = _run_script(
        "--section", HEADING, "--source", str(source), str(tmp_path / "missing.md")
    )
    assert result.returncode == 2
