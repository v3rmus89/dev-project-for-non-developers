"""Adoption-mode analyze + recommend engine for `--mode=adopt`.

Per the merged Plan PR #7 (`docs/plans/2026-05-19-skill-pr7-hybrid-trial-adoption-mode.md`),
this module ships the per-file analyze-then-decide-with-owner UX:

    1. analyze_target(target_root, planned_files) -> AdoptionPlan
    2. recommend_policy(rel_path, target_path, skill_content, target_meta)
       -> PolicyRecommendation
    3. format_recommendation_report(plan) -> str  (user-facing report)

The decide phase lives in `bootstrap_lib/cli.py` (`_interactive_decide`); the
apply phase lives in `manifest.plan_adoption_entries` +
`cli._apply_adoption_writes`. This module is the analyze + recommend layer.

All data classes are NamedTuple via class-syntax per PR #6 Claude iter-2 #2
lesson (functional NamedTuple stores annotations as strings; class-syntax does
not — matters for `Literal[...]` types).
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Literal, NamedTuple

Policy = Literal["WRITE", "SKIP", "OVERWRITE", "WRITE_NEW", "APPEND_MERGE"]
Confidence = Literal["high", "medium", "low"]

# Files we treat as markdown for heading-count purposes.
_MARKDOWN_EXTS = frozenset({".md", ".markdown"})

# Regex for a markdown heading line (start of line, 1-6 '#', then space or EOL).
# Used by `_compute_target_meta` to *count* headings.
_MD_HEADING_RE = re.compile(rb"^#{1,6}(?:\s|$)", re.MULTILINE)

# Regex for the *full* heading line (with text) — used by `recommend_policy`
# rule (f) to compare heading SETS between target and skill template.
_MD_HEADING_LINE_RE = re.compile(rb"^#{1,6}\s+.+?\s*$", re.MULTILINE)

# Domain-rich markdown files governed by Scope #5 rule (f) — these files'
# non-trivial existing content gets WRITE_NEW with manual_review_needed=True
# (preserve target's domain content; emit .new for manual merge).
_DOMAIN_MD_FILES = frozenset(
    {"CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "BACKLOG.md", "LESSONS.md"}
)


class TargetMeta(NamedTuple):
    """Derived metadata about a target file.

    Per Scope #11 privacy boundary: NO raw target content fields. Only
    derived markers (line count, heading count, structural flags, hashes).
    The user-facing recommendation report MUST NOT contain raw target text.
    """

    exists: bool
    size: int
    sha256: str | None  # None when file doesn't exist
    line_count: int | None  # None when not a text file or doesn't exist
    heading_count: int | None  # markdown only; count of '^#' lines
    has_dependency_groups: bool  # pyproject.toml; True if [dependency-groups]
    python_version_pin: str | None  # .python-version's pinned version, or None
    # `git check-ignore` source+line reference (e.g. `.gitignore:48`); None if
    # not ignored. The matching PATTERN itself is intentionally NOT captured —
    # patterns can be path-revealing (`secrets/client-acme/`) and would leak
    # into the user-facing report. Source+line is enough for the user to look
    # up the rule manually (`sed -n '48p' .gitignore`) without exposure here.
    ignored_by_git: str | None


class PolicyRecommendation(NamedTuple):
    """A per-file recommendation produced by `recommend_policy`.

    Per Scope #6 single-matrix consent contract:
      - `manual_review_needed=False`: `--auto-accept-recommendations` auto-applies
        without a prompt; under `--non-interactive`, still auto-applies.
      - `manual_review_needed=True`: always needs an interactive prompt; under
        `--non-interactive` becomes exit-2.
    """

    policy: Policy
    reason: str
    confidence: Confidence
    manual_review_needed: bool


class PlannedFileAnalysis(NamedTuple):
    """The analyze-phase product for a single planned file.

    Pairs the per-file `TargetMeta` with the `PolicyRecommendation` derived from
    Scope #5 rules. AdoptionPlan is a sequence of these.
    """

    rel_path: str
    target_meta: TargetMeta
    recommendation: PolicyRecommendation


class AdoptionPlan(NamedTuple):
    """The full analyze-phase product across all planned files.

    Consumed by `format_recommendation_report` (user-facing report) and by
    `manifest.plan_adoption_entries` (apply-phase wiring).
    """

    target_root: Path
    analyses: tuple[PlannedFileAnalysis, ...]


def _check_ignored_by_git(target_root: Path, rel_path: str) -> str | None:
    """Run `git check-ignore -v -- <rel_path>` in target_root.

    Returns just the `<source>:<line>` reference (e.g. `.gitignore:48`) if the
    path is ignored — NOT the matching pattern itself. The pattern is dropped
    here to honour Scope #11's privacy boundary: patterns can be path-revealing
    (`secrets/client-acme/`, `*-customer-token-*`) and would leak verbatim into
    the user-facing recommendation report via rule (a0)'s shape line + reason.
    Source+line is sufficient for the user to look up the rule manually
    (`sed -n '48p' .gitignore`) if they want to see why the file is ignored.

    Returns None for non-git directories or any subprocess failure (defensive:
    missing git, permissions, etc.).

    Per plan rule (a0): a planned CREATE that is ignored by git → recommended
    SKIP with manual_review_needed=True (silent SKIP loses planned file, silent
    WRITE writes invisible-to-git file — owner MUST decide).
    """
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-v", "--", rel_path],
            cwd=str(target_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        # git not installed, target_root not a directory, etc.
        return None
    # Exit 0 = ignored; output is "<source>:<line>:<pattern>\t<path>".
    # Exit 1 = not ignored. Exit 128 = not a git repo.
    if result.returncode == 0 and result.stdout:
        first_line = result.stdout.splitlines()[0]
        # Drop the tab-suffixed path, then drop the pattern field (after the
        # second colon) to keep only `<source>:<line>` — privacy-safe.
        ref = first_line.split("\t", 1)[0] if "\t" in first_line else first_line
        parts = ref.split(":", 2)
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}"
        return ref
    return None


def _python_version_pin(content_bytes: bytes) -> str | None:
    """Extract the Python version pin from `.python-version` contents.

    The file convention is a single trimmed version string like `3.12` or
    `3.12.7`. Returns None for empty/whitespace-only files.
    """
    text = content_bytes.decode("utf-8", errors="replace").strip()
    return text if text else None


def _has_dependency_groups_table(content_bytes: bytes) -> bool:
    """Return True if `pyproject.toml` content has a `[dependency-groups]` table.

    Used by rule (g): non-trivial pyproject.toml (with deps, tool config, or
    dependency-groups) → SKIP with manual_review_needed=True.

    Defensive: malformed TOML returns False (callers fall through to rule (h)
    SKIP with manual_review_needed=True anyway, which is the safe default).
    """
    try:
        data = tomllib.loads(content_bytes.decode("utf-8", errors="replace"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return False
    return "dependency-groups" in data and isinstance(data["dependency-groups"], dict)


def _compute_target_meta(target_root: Path, rel_path: str) -> TargetMeta:
    """Inspect a single target file and produce its TargetMeta.

    All fields are derived — NO raw target content is stored (per Scope #11
    privacy boundary). Hashes, counts, structural flags only.

    `ignored_by_git` is populated only when the file doesn't exist (the rule
    (a0) precondition is "planned CREATE that is ignored"). For existing files
    the value is None — rule (a0) doesn't apply.
    """
    full_path = target_root / rel_path
    exists = full_path.is_file()

    if not exists:
        return TargetMeta(
            exists=False,
            size=0,
            sha256=None,
            line_count=None,
            heading_count=None,
            has_dependency_groups=False,
            python_version_pin=None,
            ignored_by_git=_check_ignored_by_git(target_root, rel_path),
        )

    content = full_path.read_bytes()
    size = len(content)
    sha256 = hashlib.sha256(content).hexdigest()

    # Line count: count of newlines + 1 if last line has content
    # (handles both newline-terminated and not-terminated files).
    if size == 0:
        line_count: int | None = 0
    else:
        line_count = content.count(b"\n") + (0 if content.endswith(b"\n") else 1)

    ext = full_path.suffix.lower()
    is_markdown = ext in _MARKDOWN_EXTS
    heading_count: int | None = len(_MD_HEADING_RE.findall(content)) if is_markdown else None

    has_dependency_groups = False
    python_version_pin: str | None = None
    if full_path.name == "pyproject.toml":
        has_dependency_groups = _has_dependency_groups_table(content)
    elif full_path.name == ".python-version":
        python_version_pin = _python_version_pin(content)

    return TargetMeta(
        exists=True,
        size=size,
        sha256=sha256,
        line_count=line_count,
        heading_count=heading_count,
        has_dependency_groups=has_dependency_groups,
        python_version_pin=python_version_pin,
        ignored_by_git=None,  # only populated for missing files; existing files don't apply rule (a0)
    )


class AdoptionCollisionError(Exception):
    """Raised when apply-time invariants for adoption-mode are violated.

    The current trigger is the Scope #7 `.new` collision rule: if
    `<original>.new` already exists at apply time, fail-loud rather than
    overwrite a file the user may have authored or already-merged.
    `cli.py` catches this and converts to `CLIError(exit_code=2)`.
    """


def compute_append_merge_bytes(target_content: bytes, skill_content: bytes) -> bytes:
    """Return the post-merge bytes for an APPEND_MERGE apply.

    Line-level idempotent merge: for each meaningful (non-empty, non-comment)
    line in skill_content, append it ONLY if its stripped form is not already
    present in target_content. Comments + blank lines are skipped (they're
    not patterns). Running twice on the same inputs produces the same result.

    Operates in bytes throughout — no UTF-8 round-trip — so the post-apply
    content is exactly what gets written to disk and what `sha256_after_*`
    will hash. Both rule (d)'s `recommend_policy` heuristic and apply-time
    write must agree on the post-merge bytes; this is the single source of
    truth for both.
    """
    target_lines: set[bytes] = set()
    for raw_line in target_content.split(b"\n"):
        stripped = raw_line.strip()
        if stripped and not stripped.startswith(b"#"):
            target_lines.add(stripped)

    appended: list[bytes] = []
    for raw_line in skill_content.split(b"\n"):
        stripped = raw_line.strip()
        if stripped and not stripped.startswith(b"#") and stripped not in target_lines:
            appended.append(raw_line)
            target_lines.add(stripped)  # de-dupe within skill content itself

    if not appended:
        return target_content  # idempotent: nothing new to add

    suffix = b"\n".join(appended) + b"\n"
    if target_content and not target_content.endswith(b"\n"):
        return target_content + b"\n" + suffix
    return target_content + suffix


def _normalize_gitignore_lines(content_bytes: bytes) -> set[str]:
    """Return the set of meaningful (non-empty, non-comment) `.gitignore` lines.

    Used by rule (d) for line-level idempotent-merge analysis. Comments and
    blank lines aren't patterns, so they don't participate in the membership
    check. Trailing/leading whitespace on a pattern is stripped (gitignore
    treats `venv/` and `venv/ ` identically in practice; we match exact lines
    after strip).
    """
    result: set[str] = set()
    for line in content_bytes.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            result.add(stripped)
    return result


def _md_heading_lines(content_bytes: bytes) -> set[bytes]:
    """Return the set of full markdown heading lines (e.g. b'## Section').

    Used by rule (f) to detect "custom section headings not in skill template".
    A heading is `^#{1,6}\\s+<text>$`. Setext-style (`====`) headings are not
    counted — heuristic is good-enough for the file shapes this rule targets
    (CLAUDE.md, AGENTS.md, etc., which use ATX-style headings).
    """
    return {m.group(0).rstrip() for m in _MD_HEADING_LINE_RE.finditer(content_bytes)}


def _is_nontrivial_markdown(
    target_content: bytes, skill_content: bytes, target_meta: TargetMeta
) -> bool:
    """Rule (f) non-trivial test: >20 lines OR headings not in skill template.

    Either branch alone is sufficient: a 100-line target with identical
    headings is non-trivial (lots of prose); a 5-line target with a "## My
    Custom Section" not in skill is non-trivial (small but domain-bearing).
    """
    if target_meta.line_count is not None and target_meta.line_count > 20:
        return True
    target_headings = _md_heading_lines(target_content)
    skill_headings = _md_heading_lines(skill_content)
    return bool(target_headings - skill_headings)


def _is_nontrivial_pyproject(content_bytes: bytes, target_meta: TargetMeta) -> bool:
    """Rule (g) non-trivial test: [project] deps, [tool.*], or [dependency-groups].

    `has_dependency_groups` is already on TargetMeta (populated by
    `_compute_target_meta`); we re-parse here to check `[project].dependencies`
    and `[tool.*]` since those signals aren't part of TargetMeta's privacy-safe
    shape markers. Malformed TOML → returns False; rule (h) default-SKIP/
    manual_review still gives a safe outcome for the unknown shape.
    """
    if target_meta.has_dependency_groups:
        return True
    try:
        data = tomllib.loads(content_bytes.decode("utf-8", errors="replace"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return False
    if isinstance(data.get("tool"), dict) and data["tool"]:
        return True
    project = data.get("project")
    return bool(isinstance(project, dict) and project.get("dependencies"))


def recommend_policy(
    rel_path: str,
    target_path: Path,
    skill_content: bytes,
    target_meta: TargetMeta,
) -> PolicyRecommendation:
    """Apply Scope #5 rules (a0/a..h) in order; first match wins.

    The per-rule semantics are EXACTLY as the plan specifies (manual_review_needed
    values match Bucket D test fixture expectations + the v2 restore matrix in
    Bucket B):

      (a0) missing + ignored_by_git → SKIP, manual_review_needed=True ALWAYS
      (a)  missing + not ignored    → WRITE,  manual_review_needed=False
      (b)  empty / whitespace-only  → OVERWRITE, manual_review_needed=False
      (c)  byte-for-byte match      → SKIP,  manual_review_needed=False
      (d)  .gitignore: missing pats → APPEND_MERGE, manual_review_needed=False
           .gitignore: all present  → SKIP,  manual_review_needed=False
      (e)  .python-version: match   → SKIP,  manual_review_needed=False
           .python-version: differ  → SKIP,  manual_review_needed=False
      (f)  domain .md + non-trivial → WRITE_NEW, manual_review_needed=True
      (g)  pyproject.toml + non-triv→ SKIP,  manual_review_needed=True
      (h)  DEFAULT (existing, no match) → SKIP, manual_review_needed=True

    Rule (h) is the core safety guarantee: any existing non-empty file that
    doesn't match a recognized adoption pattern gets SKIP with manual_review.
    Codex iter-1 #3: rule (h) must NEVER recommend WRITE on an existing file
    — that would let `--restore` silently delete user files (WRITE's restore
    semantics delete the path per Bucket B v2 restore matrix row (a)).
    """
    name = Path(rel_path).name

    # Rule (a0): planned CREATE is ignored by git.
    # Silent SKIP loses the planned file; silent WRITE writes invisible-to-git
    # output. Both unacceptable. ALWAYS manual_review_needed=True so the
    # interactive prompt asks the owner (SKIP-confirm vs WRITE_NEW).
    if not target_meta.exists and target_meta.ignored_by_git is not None:
        return PolicyRecommendation(
            policy="SKIP",
            reason=(
                f"target gitignores this path ({target_meta.ignored_by_git}); "
                "owner must decide SKIP-confirm vs WRITE_NEW"
            ),
            confidence="high",
            manual_review_needed=True,
        )

    # Rule (a): missing AND not ignored → safe to create.
    if not target_meta.exists:
        return PolicyRecommendation(
            policy="WRITE",
            reason="target file does not exist; safe to create",
            confidence="high",
            manual_review_needed=False,
        )

    # All remaining rules need target content (rules b/d/f/g operate on bytes).
    # We re-read here rather than threading content through TargetMeta because
    # TargetMeta is deliberately content-free per Scope #11 privacy boundary —
    # only derived markers/hashes live there.
    target_content = target_path.read_bytes()

    # Rule (b): empty or whitespace-only → OVERWRITE.
    # `.strip() == b""` catches both size-0 files and whitespace-only files.
    if target_content.strip() == b"":
        return PolicyRecommendation(
            policy="OVERWRITE",
            reason="target file is empty / whitespace-only; safe to fill",
            confidence="high",
            manual_review_needed=False,
        )

    # Rule (c): byte-for-byte match → SKIP (semantically honest no-op).
    # SHA comparison is sufficient — equal SHA implies equal bytes (collision
    # negligible). `target_meta.sha256` is the canonical hash source.
    skill_sha = hashlib.sha256(skill_content).hexdigest()
    if target_meta.sha256 == skill_sha:
        return PolicyRecommendation(
            policy="SKIP",
            reason="target content matches skill template byte-for-byte; no-op",
            confidence="high",
            manual_review_needed=False,
        )

    # Rule (d): .gitignore — line-level idempotent merge OR no-op if covered.
    if name == ".gitignore":
        target_lines = _normalize_gitignore_lines(target_content)
        skill_lines = _normalize_gitignore_lines(skill_content)
        missing = skill_lines - target_lines
        if not missing:
            return PolicyRecommendation(
                policy="SKIP",
                reason="all skill .gitignore patterns already present in target",
                confidence="high",
                manual_review_needed=False,
            )
        return PolicyRecommendation(
            policy="APPEND_MERGE",
            reason=(
                f"{len(missing)} skill .gitignore pattern(s) missing from target; "
                "append-only line-level merge"
            ),
            confidence="high",
            manual_review_needed=False,
        )

    # Rule (e): .python-version — SKIP either way; never overwrite a pin.
    if name == ".python-version":
        skill_pin = _python_version_pin(skill_content)
        target_pin = target_meta.python_version_pin
        if target_pin == skill_pin:
            return PolicyRecommendation(
                policy="SKIP",
                reason=f"target pins same Python version ({target_pin}); no-op",
                confidence="high",
                manual_review_needed=False,
            )
        return PolicyRecommendation(
            policy="SKIP",
            reason=(
                f"target pins a different Python version "
                f"({target_pin!r} vs skill's {skill_pin!r}); leave target alone"
            ),
            confidence="high",
            manual_review_needed=False,
        )

    # Rule (f): domain markdown files non-trivial → WRITE_NEW.
    if name in _DOMAIN_MD_FILES and _is_nontrivial_markdown(
        target_content, skill_content, target_meta
    ):
        return PolicyRecommendation(
            policy="WRITE_NEW",
            reason=(
                f"target {name} has domain content (>20 lines or custom headings); "
                "preserve original and write .new for manual merge"
            ),
            confidence="medium",
            manual_review_needed=True,
        )

    # Rule (g): pyproject.toml non-trivial → SKIP with manual_review.
    if name == "pyproject.toml" and _is_nontrivial_pyproject(target_content, target_meta):
        return PolicyRecommendation(
            policy="SKIP",
            reason=(
                "target pyproject.toml has [project] deps, [tool.*], or "
                "[dependency-groups]; review the diff manually with --diff"
            ),
            confidence="medium",
            manual_review_needed=True,
        )

    # Rule (h): DEFAULT — existing non-empty file with no recognized pattern.
    # This is the core safety guarantee: never silently WRITE over an unknown
    # existing file (Codex iter-1 #3 closed). Owner must decide.
    return PolicyRecommendation(
        policy="SKIP",
        reason=(
            "existing file does not match any recognized adoption pattern; "
            "default SKIP for safety — owner decides"
        ),
        confidence="low",
        manual_review_needed=True,
    )


def _format_target_shape(meta: TargetMeta) -> str:
    """Render the per-file "target: ..." shape line for the report.

    Per Scope #11 privacy boundary: only derived markers — sha256 (first 8 hex
    chars), counts (lines, headings, size), structural flags (deps groups),
    version pin, gitignore match line. NO raw file bytes anywhere.
    """
    if not meta.exists:
        if meta.ignored_by_git:
            return f"target: missing (gitignored: {meta.ignored_by_git})"
        return "target: missing"

    parts: list[str] = []
    if meta.line_count is not None:
        parts.append("1 line" if meta.line_count == 1 else f"{meta.line_count} lines")
    else:
        parts.append(f"{meta.size} bytes")
    if meta.heading_count is not None and meta.heading_count > 0:
        parts.append("1 heading" if meta.heading_count == 1 else f"{meta.heading_count} headings")
    if meta.python_version_pin is not None:
        parts.append(f"pin={meta.python_version_pin}")
    if meta.has_dependency_groups:
        parts.append("[dependency-groups]")
    if meta.sha256:
        parts.append(f"sha256:{meta.sha256[:8]}")
    return f"target: {', '.join(parts)}"


def _format_recommendation_row(analysis: PlannedFileAnalysis) -> list[str]:
    """Three lines per file: header (policy + rel_path), target shape, reason."""
    rec = analysis.recommendation
    return [
        f"  {rec.policy:13} {analysis.rel_path}",
        f"                {_format_target_shape(analysis.target_meta)}",
        f"                reason: {rec.reason}",
    ]


def format_recommendation_report(plan: AdoptionPlan) -> str:
    """Render the user-facing recommendation report shown before the interactive
    decide phase.

    Layout: header + sections grouped by `manual_review_needed`
    (automatic vs manual-review) + summary line with per-policy counts.

    Privacy (Bucket B test row contract): the output contains NO raw target
    content. Only filenames, derived markers (counts/hashes/structural flags),
    and policy decisions/reasons appear. Tests assert this empirically by
    seeding target files with a marker string and verifying the marker does
    not appear in the rendered report.
    """
    lines: list[str] = [
        f"adoption recommendation: {len(plan.analyses)} file(s) analyzed at {plan.target_root}"
    ]

    if not plan.analyses:
        lines.append("")
        lines.append("(empty plan — nothing to do)")
        return "\n".join(lines) + "\n"

    auto = [a for a in plan.analyses if not a.recommendation.manual_review_needed]
    manual = [a for a in plan.analyses if a.recommendation.manual_review_needed]

    if auto:
        lines.append("")
        lines.append(f"automatic ({len(auto)}):")
        for analysis in auto:
            lines.append("")
            lines.extend(_format_recommendation_row(analysis))

    if manual:
        lines.append("")
        lines.append(f"manual review needed ({len(manual)}):")
        for analysis in manual:
            lines.append("")
            lines.extend(_format_recommendation_row(analysis))

    counts: dict[str, int] = {}
    for analysis in plan.analyses:
        counts[analysis.recommendation.policy] = counts.get(analysis.recommendation.policy, 0) + 1
    summary = " ".join(f"{policy}={counts[policy]}" for policy in sorted(counts))
    tail = f"{len(manual)} need your decision" if manual else "all automatic — no decisions needed"
    lines.append("")
    lines.append(f"summary: {summary}  ({tail})")

    return "\n".join(lines) + "\n"


def analyze_target(target_root: Path, planned_files: dict[str, bytes]) -> AdoptionPlan:
    """Walk every planned file; compute TargetMeta + PolicyRecommendation for each.

    The orchestrator that produces the full AdoptionPlan consumed by
    `format_recommendation_report` (user-facing) and `plan_adoption_entries`
    (apply-phase wiring per Bucket A `cli.py` row).

    Stable ordering: planned_files keys are sorted lexicographically so the
    user-facing report and downstream manifest entries are deterministic
    across runs (matches the existing `--dry-run` / `--diff` ordering contract).

    The function reads target files (via `_compute_target_meta` +
    `recommend_policy`) but writes NOTHING — the analyze phase is pure
    inspection per Architecture decision "Analyze phase reads target files but
    writes NOTHING."

    Caller contract: the caller (`cli.py`) is responsible for validating that
    `target_root` is an existing directory AND that every `planned_files` key
    is CLI-layer path-safe (no absolute paths, no `..` segments). Path-safety
    enforcement lives in `cli.py` + `render.py` per Architecture decisions;
    this engine assumes pre-validated inputs.
    """
    analyses: list[PlannedFileAnalysis] = []
    for rel_path in sorted(planned_files):
        skill_content = planned_files[rel_path]
        target_meta = _compute_target_meta(target_root, rel_path)
        target_path = target_root / rel_path
        recommendation = recommend_policy(rel_path, target_path, skill_content, target_meta)
        analyses.append(
            PlannedFileAnalysis(
                rel_path=rel_path,
                target_meta=target_meta,
                recommendation=recommendation,
            )
        )
    return AdoptionPlan(target_root=target_root, analyses=tuple(analyses))


__all__ = [
    "AdoptionCollisionError",
    "AdoptionPlan",
    "Confidence",
    "PlannedFileAnalysis",
    "Policy",
    "PolicyRecommendation",
    "TargetMeta",
    "_compute_target_meta",  # exported for tests
    "analyze_target",
    "compute_append_merge_bytes",
    "format_recommendation_report",
    "recommend_policy",
]
