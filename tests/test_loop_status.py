"""Tests for Bucket D/E: verdict-footer parsing (V-6/7/8) and the
loop-status stop classifier (V-9/V-10/V-11/V-12/V-16/V-16.5).

V-6:    well-formed json-verdict footer  → parse returns expected dict
V-7:    malformed JSON in footer block   → returns {"status": "malformed"}
V-8:    no footer block at all           → returns {"status": "footer-missing"}
V-9:    converged-with-polish            → last has verdict=converged + imp-2>0
V-10:   oscillating                     → fingerprint reappears at iter N vs N-2
V-11:   stuck                           → fingerprints identical at N-1 and N
V-12:   regressed                       → imp-3 count grew between iters
V-16:   exit codes                      → 0 on converged/converged-with-polish/
                                          needs-iter/no-iters; 1 on malformed[-latest]
V-16.5: key filtering                   → wrong-key file is ignored
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# ── Import from scripts/loop-status.py ──────────────────────────────────────

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop-status.py"
_spec = importlib.util.spec_from_file_location("loop_status", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_parse_footer = _mod._parse_footer
classify = _mod.classify
_load_iters = _mod._load_iters
_latest_file_for_stem = _mod._latest_file_for_stem
main = _mod.main


# ── Helpers ──────────────────────────────────────────────────────────────────


def _footer(
    verdict: str,
    severity_counts: dict,
    findings: list | None = None,
    key: str = "testkey000000",
) -> dict:
    return {
        "verdict": verdict,
        "severity_counts": severity_counts,
        "key": key,
        "findings": findings or [],
    }


def _finding(fingerprint: str, importance: int = 2) -> dict:
    return {
        "id": "F1",
        "importance": importance,
        "section_or_line": "## Test",
        "title": "test finding",
        "fingerprint": fingerprint,
    }


def _write_review(tmp_path: Path, name: str, footer: dict) -> Path:
    content = f"Prose.\n\n```json\n{json.dumps(footer, indent=2)}\n```\n"
    p = tmp_path / name
    p.write_text(content)
    return p


# ── V-6: well-formed footer ──────────────────────────────────────────────────


def test_v6_well_formed_footer():
    """V-6: a valid json-verdict fence is parsed into the expected dict."""
    review_text = """\
## Findings

**F1 (importance 3):** something is wrong.

**F2 (importance 1):** minor polish item.

```json
{
  "verdict": "needs-iter",
  "severity_counts": {"3": 1, "2": 0, "1": 1},
  "key": "abc123456789",
  "findings": [
    {
      "id": "F1",
      "importance": 3,
      "section_or_line": "## Implementation",
      "title": "something is wrong",
      "fingerprint": "implementation:something-is-wrong"
    },
    {
      "id": "F2",
      "importance": 1,
      "section_or_line": "## Scope",
      "title": "minor polish item",
      "fingerprint": "scope:minor-polish-item"
    }
  ]
}
```
"""
    result = _parse_footer(review_text)
    assert result["verdict"] == "needs-iter"
    assert result["severity_counts"]["3"] == 1
    assert result["severity_counts"]["1"] == 1
    assert result["key"] == "abc123456789"
    assert len(result["findings"]) == 2
    assert result["findings"][0]["id"] == "F1"
    assert result["findings"][0]["fingerprint"] == "implementation:something-is-wrong"


def test_v6_converged_verdict():
    """V-6 variant: converged verdict parses correctly."""
    review_text = """\
No important findings.

```json
{"verdict": "converged", "severity_counts": {"3": 0, "2": 0, "1": 0}, "key": "xyz987", "findings": []}
```
"""
    result = _parse_footer(review_text)
    assert result["verdict"] == "converged"
    assert result["findings"] == []


def test_v6_last_fence_wins():
    """V-6 variant: when multiple ```json fences exist, the last one is the verdict."""
    review_text = """\
Here is an example JSON snippet in the prose:

```json
{"example": "this is not the verdict"}
```

Now the actual verdict footer:

```json
{"verdict": "converged", "severity_counts": {"3": 0, "2": 1, "1": 0}, "key": "aaa111", "findings": []}
```
"""
    result = _parse_footer(review_text)
    assert result["verdict"] == "converged"
    assert result.get("example") is None


# ── V-7: malformed JSON ──────────────────────────────────────────────────────


def test_v7_malformed_json_returns_malformed():
    """V-7: a ```json fence with invalid JSON → {"status": "malformed"}."""
    review_text = """\
Some prose findings.

```json
{this is not valid json
  "verdict": "needs-iter",
}
```
"""
    result = _parse_footer(review_text)
    assert result == {"status": "malformed"}


def test_v7_truncated_json():
    """V-7 variant: truncated JSON object → {"status": "malformed"}."""
    review_text = '```json\n{"verdict": "needs-iter", "findings": [\n```\n'
    result = _parse_footer(review_text)
    assert result == {"status": "malformed"}


def test_v7_json_array_returns_malformed():
    """V-7 variant: a ```json fence containing a JSON array → {"status": "malformed"}."""
    review_text = "```json\n[1, 2, 3]\n```\n"
    result = _parse_footer(review_text)
    assert result == {"status": "malformed"}


# ── V-8: missing footer ──────────────────────────────────────────────────────


def test_v8_no_footer_returns_footer_missing():
    """V-8: review text with no ```json fence → {"status": "footer-missing"}."""
    review_text = """\
## Findings

**F1 (importance 2):** something could be improved.

Overall: needs another iteration.
"""
    result = _parse_footer(review_text)
    assert result == {"status": "footer-missing"}


def test_v8_only_non_json_fences():
    """V-8 variant: ```python or plain ``` fences don't count as the footer."""
    review_text = """\
Here is some code:

```python
x = 1
```

And a plain fence:

```
not json
```
"""
    result = _parse_footer(review_text)
    assert result == {"status": "footer-missing"}


def test_v8_empty_string():
    """V-8 variant: empty input → {"status": "footer-missing"}."""
    assert _parse_footer("") == {"status": "footer-missing"}


# ── V-9: converged-with-polish ───────────────────────────────────────────────


def test_v9_converged_with_polish():
    """V-9: last iter verdict=converged but imp-2 > 0 → converged-with-polish."""
    iters = [
        _footer("needs-iter", {"3": 1, "2": 1, "1": 0}),
        _footer("needs-iter", {"3": 0, "2": 2, "1": 0}),
        _footer("converged", {"3": 0, "2": 2, "1": 0}),
    ]
    status, rationale = classify(iters)
    assert status == "converged-with-polish"
    assert "fold" in rationale.lower() or "park" in rationale.lower()


def test_v9_converged_clean():
    """V-9 variant: last iter verdict=converged with ALL counts zero → converged."""
    iters = [
        _footer("needs-iter", {"3": 1, "2": 0, "1": 0}),
        _footer("converged", {"3": 0, "2": 0, "1": 0}),
    ]
    status, _ = classify(iters)
    assert status == "converged"


# ── V-10: oscillating ────────────────────────────────────────────────────────


def test_v10_oscillating():
    """V-10: fingerprint X at N-2, gone at N-1, back at N → oscillating."""
    fp_x = "section-a:some-issue"
    iters = [
        _footer("needs-iter", {"3": 1}, [_finding(fp_x, 3)]),  # N-2
        _footer("needs-iter", {"3": 0}, []),  # N-1: X gone
        _footer("needs-iter", {"3": 1}, [_finding(fp_x, 3)]),  # N: X back
    ]
    status, rationale = classify(iters)
    assert status == "oscillating"
    assert fp_x in rationale


def test_v10_not_oscillating_when_different_fp():
    """V-10 variant: different fingerprint at N vs N-2 → not oscillating."""
    iters = [
        _footer("needs-iter", {"3": 1}, [_finding("fp-a", 3)]),
        _footer("needs-iter", {"3": 0}, []),
        _footer("needs-iter", {"3": 1}, [_finding("fp-b", 3)]),
    ]
    status, _ = classify(iters)
    assert status != "oscillating"


def test_v10_partial_oscillation_is_detected():
    """V-10 variant: N-2={A,B}, N-1={B,C}, N={A,B,D} → oscillating (A reappears)."""
    iters = [
        _footer("needs-iter", {"3": 2}, [_finding("fp-a", 3), _finding("fp-b", 3)]),
        _footer("needs-iter", {"3": 2}, [_finding("fp-b", 3), _finding("fp-c", 3)]),
        _footer(
            "needs-iter", {"3": 3}, [_finding("fp-a", 3), _finding("fp-b", 3), _finding("fp-d", 3)]
        ),
    ]
    status, rationale = classify(iters)
    assert status == "oscillating"
    assert "fp-a" in rationale


# ── V-11: stuck ──────────────────────────────────────────────────────────────


def test_v11_stuck():
    """V-11: fingerprints identical at N-1 and N → stuck."""
    fp = "section-b:repeated-issue"
    finding = _finding(fp, 3)
    iters = [
        _footer("needs-iter", {"3": 1}, [finding]),
        _footer("needs-iter", {"3": 1}, [finding]),
    ]
    status, rationale = classify(iters)
    assert status == "stuck"
    assert fp in rationale


def test_v11_not_stuck_when_different():
    """V-11 variant: different fingerprints at N-1 and N → not stuck."""
    iters = [
        _footer("needs-iter", {"3": 1}, [_finding("fp-old", 3)]),
        _footer("needs-iter", {"3": 1}, [_finding("fp-new", 3)]),
    ]
    status, _ = classify(iters)
    assert status != "stuck"


# ── V-12: regressed ──────────────────────────────────────────────────────────


def test_v12_regressed():
    """V-12: imp-3 count grew between iters → regressed."""
    iters = [
        _footer("needs-iter", {"3": 1, "2": 0, "1": 0}),
        _footer("needs-iter", {"3": 2, "2": 0, "1": 0}),
    ]
    status, rationale = classify(iters)
    assert status == "regressed"
    assert "1" in rationale and "2" in rationale


def test_v_f2_missing_fingerprint_returns_malformed():
    """F2 fold: a finding in the last iter with no fingerprint → malformed."""
    iters = [
        _footer(
            "needs-iter",
            {"3": 1},
            [{"id": "F1", "importance": 3, "section_or_line": "## Test", "title": "x"}],
        )
    ]
    status, rationale = classify(iters)
    assert status == "malformed"
    assert "fingerprint" in rationale


def test_v_f3_needs_iter_with_zero_imp3_is_converged_with_polish():
    """F3 fold: verdict=needs-iter + c3=0 + c2>0 → converged-with-polish."""
    iters = [
        _footer("needs-iter", {"3": 0, "2": 2, "1": 0}),
    ]
    status, rationale = classify(iters)
    assert status == "converged-with-polish"
    assert "0" in rationale or "no imp-3" in rationale.lower()


def test_v12_not_regressed_when_stable():
    """V-12 variant: same imp-3 count → not regressed (is needs-iter or stuck)."""
    iters = [
        _footer("needs-iter", {"3": 2}),
        _footer("needs-iter", {"3": 2}),
    ]
    status, _ = classify(iters)
    assert status != "regressed"


# ── V-16: exit codes ─────────────────────────────────────────────────────────


def test_v16_exit_0_on_converged(tmp_path):
    """V-16: converged → main returns 0."""
    key = "exitcode0conv"
    _write_review(
        tmp_path,
        "plan-review-test-by-codex-iter-1.md",
        _footer("converged", {"3": 0, "2": 0, "1": 0}, key=key),
    )
    rc = main([key, str(tmp_path)])
    assert rc == 0


def test_v16_exit_0_on_converged_with_polish(tmp_path):
    """V-16: converged-with-polish → main returns 0."""
    key = "exitcode0cwp"
    _write_review(
        tmp_path,
        "plan-review-test-by-codex-iter-1.md",
        _footer("converged", {"3": 0, "2": 1, "1": 0}, key=key),
    )
    rc = main([key, str(tmp_path)])
    assert rc == 0


def test_v16_exit_0_on_needs_iter(tmp_path):
    """V-16: needs-iter → main returns 0 (advisory, not blocking)."""
    key = "exitcode0nit"
    _write_review(
        tmp_path,
        "plan-review-test-by-codex-iter-1.md",
        _footer("needs-iter", {"3": 1, "2": 0, "1": 0}, key=key),
    )
    rc = main([key, str(tmp_path)])
    assert rc == 0


def test_v16_malformed_footer_classifies_malformed():
    """V-16: classify() returns 'malformed' for a malformed last footer. (Direct
    classify contract test — _load_iters filters malformed footers out, so the
    reachable malformed exit-1 path in main() is malformed-latest, below.)"""
    status, _rationale = classify([{"status": "malformed"}])
    assert status == "malformed"


def test_v16_no_stem_malformed_latest_is_no_iters_exit_0(tmp_path):
    """V-16 back-compat (2-arg, no stem): a malformed NEWEST review is dropped by
    _load_iters, so without a plan stem main() reports no-iters and exits 0 —
    loop-status stays advisory (D-5: exit 0 for every non-error state)."""
    key = "mallatest000"
    (tmp_path / "plan-review-myplan-by-codex-iter-1.md").write_text("```json\n{bad}\n```\n")
    assert main([key, str(tmp_path)]) == 0  # no stem -> back-compat no-iters


def test_v16_malformed_latest_with_stem_exit_1(tmp_path, capsys):
    """V-16 malformed-latest follow-up: WITH the plan stem, a malformed NEWEST
    review for THIS plan is surfaced distinctly (status malformed-latest, exit 1,
    names the file) instead of collapsing to a misleading no-iters. Removing the
    bad file returns to no-iters / exit 0."""
    key = "mallatest000"
    stem = "myplan"
    bad = tmp_path / f"plan-review-{stem}-by-codex-iter-1.md"
    bad.write_text("```json\n{bad}\n```\n")
    rc = main([key, str(tmp_path), stem])
    out = capsys.readouterr().out
    assert rc == 1
    assert "malformed-latest" in out
    assert bad.name in out  # names the offending file
    bad.unlink()
    assert main([key, str(tmp_path), stem]) == 0  # cleanup -> no-iters -> 0


def test_v16_valid_latest_with_stem_unaffected(tmp_path):
    """The stem arg must not perturb the happy path: a well-formed latest review
    for the stem still classifies normally (needs-iter, exit 0)."""
    key = "validlatest0"
    stem = "myplan"
    _write_review(
        tmp_path,
        f"plan-review-{stem}-by-codex-iter-1.md",
        _footer("needs-iter", {"3": 1}, key=key),
    )
    assert main([key, str(tmp_path), stem]) == 0


def test_v16_malformed_latest_masked_by_older_valid_iter(tmp_path, capsys):
    """Codex P1 (review of PR #45): a malformed NEWEST review (iter-2) must surface
    as malformed-latest even when an OLDER iter (iter-1) still parses. _load_iters
    drops the bad iter-2, so classify() would otherwise report iter-1's stale
    status; the stem check must not be gated on no-iters."""
    key = "maskediter00"
    stem = "myplan"
    _write_review(
        tmp_path,
        f"plan-review-{stem}-by-codex-iter-1.md",
        _footer("converged", {"3": 0, "2": 0, "1": 0}, key=key),
    )
    (tmp_path / f"plan-review-{stem}-by-codex-iter-2.md").write_text("```json\n{bad}\n```\n")
    rc = main([key, str(tmp_path), stem])
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "malformed-latest" in out
    assert "iter-2" in out  # names the newest (bad) file, not the stale iter-1


def test_latest_file_for_stem_picks_highest_iter(tmp_path):
    """_latest_file_for_stem returns the numerically-highest iter file for the
    stem (so a malformed iter-10 is not masked by a valid iter-9), or None."""
    stem = "myplan"
    for n in (1, 2, 10):
        (tmp_path / f"plan-review-{stem}-by-codex-iter-{n}.md").write_text("x")
    latest = _latest_file_for_stem(stem, tmp_path)
    assert latest is not None
    assert latest.name == f"plan-review-{stem}-by-codex-iter-10.md"
    assert _latest_file_for_stem("nosuchstem", tmp_path) is None


def test_v16_ignores_consistency_and_commit_files(tmp_path):
    """V-16: loop-status only globs plan-review-*-by-*-iter-*.md files."""
    key = "filterk000000"
    # Drop a consistency file and a commit-review file that should NOT be read
    (tmp_path / "review-plan-consistency-foo-iter-1.5.md").write_text(
        f"```json\n{json.dumps({'verdict': 'converged', 'key': key, 'severity_counts': {'3': 0}, 'findings': []})}\n```\n"
    )
    (tmp_path / "review-commit-abc1234-by-codex.md").write_text(
        f"```json\n{json.dumps({'verdict': 'converged', 'key': key, 'severity_counts': {'3': 0}, 'findings': []})}\n```\n"
    )
    # Only a plan-review file counts
    _write_review(
        tmp_path,
        "plan-review-my-plan-by-codex-iter-1.md",
        _footer("needs-iter", {"3": 1}, key=key),
    )
    iters = _load_iters(key, tmp_path)
    assert len(iters) == 1
    status, _ = classify(iters)
    assert status == "needs-iter"


# ── V-16.5: key filtering ────────────────────────────────────────────────────


def test_v16_5_wrong_key_file_is_ignored(tmp_path):
    """V-16.5: a plan-review file from a different repo (wrong key) is filtered out."""
    right_key = "rightkey0000"
    wrong_key = "wrongkey0000"

    # Write a file for another repo with the wrong key
    _write_review(
        tmp_path,
        "plan-review-my-plan-by-codex-iter-1.md",
        _footer("converged", {"3": 0, "2": 0, "1": 0}, key=wrong_key),
    )
    # Write a file for THIS repo with the right key
    _write_review(
        tmp_path,
        "plan-review-my-plan-by-codex-iter-2.md",
        _footer("needs-iter", {"3": 1}, key=right_key),
    )

    iters = _load_iters(right_key, tmp_path)
    assert len(iters) == 1, "wrong-key file must be excluded"
    assert iters[0]["verdict"] == "needs-iter"
    status, _ = classify(iters)
    assert status == "needs-iter"


# ── numeric iteration ordering ───────────────────────────────────────────────


def test_v16_numeric_iteration_order(tmp_path):
    """Regression (Tier-1, C4 B+C): iter files load in NUMERIC order, so iter-9 <
    iter-10 < iter-11. A lexical filename sort orders iter-10/iter-11 BEFORE iter-2
    and makes iter-9 the 'last' footer in a double-digit loop — exactly the
    long-loop case loop-status exists to guard."""
    key = "numordr000000"
    # Use the imp-3 count as a per-iter marker so the load order is observable.
    for n in (9, 10, 11):
        _write_review(
            tmp_path,
            f"plan-review-p-by-codex-iter-{n}.md",
            _footer("needs-iter", {"3": n}, key=key),
        )
    iters = _load_iters(key, tmp_path)
    order = [it["severity_counts"]["3"] for it in iters]
    assert order == [9, 10, 11], f"iters must load in numeric order, got {order}"
    assert iters[-1]["severity_counts"]["3"] == 11, "last footer must be iter-11, not iter-9"
