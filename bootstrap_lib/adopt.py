"""Adoption-mode analyze + recommend engine for `--mode=adopt`.

Per the merged Plan PR #7 (`docs/plans/2026-05-19-skill-pr7-hybrid-trial-adoption-mode.md`),
this module ships the per-file analyze-then-decide-with-owner UX:

    1. analyze_target(target_root, planned_files) -> AdoptionPlan
    2. recommend_policy(rel_path, target_path, skill_content, target_meta)
       -> PolicyRecommendation
    3. format_recommendation_report(plan) -> str  (user-facing report)

The decide phase lives in `bootstrap_lib/adopt_ui.py` (`_interactive_decide`);
the apply phase lives in `manifest.plan_adoption_entries` +
`apply_pipeline._apply_adoption_writes`. This module is the analyze + recommend layer.

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

Policy = Literal["WRITE", "SKIP", "OVERWRITE", "WRITE_NEW", "APPEND_MERGE", "NEUTRALIZE"]
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

# Standalone tool-config files that, when owned by the target, shadow the
# skill's pyproject.toml [tool.*] tables: ruff reads ruff.toml / .ruff.toml in
# preference to [tool.ruff], and pytest reads pytest.ini in preference to
# [tool.pytest.ini_options]. Used by the B1 shadow scan (config-shadowing fix
# plan). Top-level scan only — nested monorepo configs are out of scope.
_SHADOWING_CONFIG_FILES = ("ruff.toml", ".ruff.toml", "pytest.ini")


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
    # Derived (privacy-safe) boolean: True when a planned-CREATE's ignore is
    # cleanly NEUTRALIZE-able — i.e. the managed un-ignore block can both apply
    # and restore without surprises. Computed in `_check_ignored_by_git` (which
    # discards the raw pattern). Requires ALL of: (a) the matched winning pattern
    # is `.claude/`-class, (b) the ignore is sourced from the target's ROOT
    # `.gitignore` (NOT `.git/info/exclude` / a global excludesfile — else apply
    # would create a `.gitignore` and restore would leave a stray empty one), and
    # (c) that `.gitignore` does NOT already contain the NEUTRALIZE sentinel (a
    # prior/partial block — else apply no-ops and restore over-reaches). Anything
    # else (broad `*.md` ignore, exclude-sourced, sentinel already present) leaves
    # it False → rule (a0) falls back to a conservative SKIP+manual.
    neutralize_eligible: bool = False


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
    # B1 shadow scan result (config-shadowing fix plan): target-owned
    # standalone tool-config filenames that would shadow pyproject.toml's
    # [tool.*] tables. Computed once by `analyze_target`; consumed by both the
    # escalation post-step and `format_recommendation_report` — never
    # rescanned, so escalation and advisory cannot drift. Empty tuple when no
    # shadow exists (adoption mode is Python-only — `scan_shadowing_configs`
    # itself is language-agnostic, but the scan only ever runs for Python
    # targets because adoption mode is rejected for Node/Go upstream).
    shadowing_configs: tuple[str, ...] = ()


def scan_shadowing_configs(target_root: Path) -> tuple[str, ...]:
    """Return target-owned standalone tool-config filenames present at the top
    level of `target_root` that would shadow the skill's pyproject.toml
    [tool.*] tables.

    ruff reads a `ruff.toml` / `.ruff.toml` in preference to `[tool.ruff]`;
    pytest reads a `pytest.ini` in preference to `[tool.pytest.ini_options]`.
    The skill ships its config inside `pyproject.toml`, so any of these
    target-owned files silently wins. Top-level (`target_root`) only — not
    recursive; nested monorepo configs are out of scope (config-shadowing fix
    plan, Bucket E BACKLOG entry).
    """
    return tuple(name for name in _SHADOWING_CONFIG_FILES if (target_root / name).is_file())


def _is_dotclaude_class_pattern(pattern: str) -> bool:
    """True if a gitignore pattern is `.claude/`-class — i.e. the managed
    un-ignore block (NEUTRALIZE) can actually restore git-visibility for a
    `.claude/`-nested file.

    A BROAD pattern that merely happens to match the file (e.g. `*.md`) is NOT
    `.claude/`-class: the un-ignore block wouldn't fix it, so rule (a0) must stay
    a conservative SKIP for it (design-note AC4 / iter-1 FN5).

    Normalize first: strip a leading `!` (negation) + surrounding space, then an
    optional leading `/` (root-anchored `/.claude/`, `/.claude/**` are normal
    gitignore forms — iter-3 FN4). Then match `.claude`, `.claude/`, `.claude/**`,
    or any `.claude/`-prefixed pattern. The raw pattern is consumed here and
    never stored on TargetMeta (Scope #11 privacy boundary)."""
    p = pattern.strip()
    if p.startswith("!"):
        p = p[1:].strip()
    if p.startswith("/"):
        p = p[1:]
    return p in (".claude", ".claude/", ".claude/**") or p.startswith(".claude/")


def _gitignore_has_neutralize_sentinel(target_root: Path) -> bool:
    """True if the target's ROOT `.gitignore` already contains the NEUTRALIZE
    sentinel line (a prior or partial un-ignore block).

    When present, NEUTRALIZE is NOT cleanly applicable: apply would no-op on the
    sentinel (so a partial/broken block leaves the command git-hidden — silent
    failure), and restore would remove lines apply did not add (clobbering
    pre-existing user content). The trigger falls back to SKIP+manual instead
    (Tier-2 codex P2 on PR #35 — findings B + D)."""
    from bootstrap_lib.manifest import NEUTRALIZE_SENTINEL

    try:
        text = (target_root / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return False
    return NEUTRALIZE_SENTINEL in text


def _check_ignored_by_git(target_root: Path, rel_path: str) -> tuple[str | None, bool]:
    """Run `git check-ignore -v -- <rel_path>` in target_root.

    Returns `(ref, neutralize_eligible)`:

      - `ref`: the `<source>:<line>` reference (e.g. `.gitignore:48`) if the path
        is ignored, else None. NOT the matching pattern itself — patterns can be
        path-revealing (`secrets/client-acme/`, `*-customer-token-*`) and would
        leak verbatim into the user-facing report via rule (a0)'s reason. Source+
        line is enough to look the rule up manually (`sed -n '48p' .gitignore`).
      - `neutralize_eligible`: True only when NEUTRALIZE can cleanly apply AND
        restore — see the `TargetMeta.neutralize_eligible` field doc for the
        three required conditions. Derived from the raw pattern + source, which
        are then discarded — never stored.

    Returns `(None, False)` for non-git directories or any subprocess failure
    (defensive: missing git, permissions, etc.).

    Per plan rule (a0): a planned CREATE that is ignored by git → NEUTRALIZE when
    cleanly eligible (manual_review), else a conservative SKIP (manual_review) —
    silent SKIP loses the planned file, silent WRITE writes an invisible-to-git
    file, so the owner MUST decide either way.
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
        return None, False
    # Exit 0 = a pattern MATCHED; output is "<source>:<line>:<pattern>\t<path>".
    # Exit 1 = no match. Exit 128 = not a git repo.
    if result.returncode == 0 and result.stdout:
        first_line = result.stdout.splitlines()[0]
        # Drop the tab-suffixed path, then split off the pattern field (after the
        # second colon). `<source>:<line>` is kept (privacy-safe); the pattern +
        # source are used only to derive `neutralize_eligible`, then discarded.
        ref = first_line.split("\t", 1)[0] if "\t" in first_line else first_line
        parts = ref.split(":", 2)
        source = parts[0]
        pattern = parts[2] if len(parts) >= 3 else ""
        # `git check-ignore -v` reports rc 0 AND the WINNING pattern even when
        # that pattern is a NEGATION (`!…`) that RE-INCLUDES the path — i.e. the
        # path is NOT actually ignored (`git check-ignore -q` exits 1 for it).
        # Treat a negated winning match as not-ignored; otherwise a target that
        # has already un-ignored the command (manual setup, or an interrupted
        # prior adopt that appended the block but never wrote the file) would be
        # mis-classified NEUTRALIZE instead of a plain rule-(a) WRITE — and
        # `--non-interactive` would abort on it (Tier-2 codex P2 on PR #35).
        if pattern.lstrip().startswith("!"):
            return None, False
        ref_short = f"{parts[0]}:{parts[1]}" if len(parts) >= 2 else ref
        # NEUTRALIZE is cleanly applicable ONLY when the winning pattern is
        # `.claude/`-class AND the ignore is sourced from the target's ROOT
        # `.gitignore` (so the un-ignore block edits the SAME file, which must
        # exist — no created-then-stray-on-restore artifact) AND that `.gitignore`
        # has no pre-existing sentinel. Else → conservative SKIP (PR #35 codex
        # findings A/B/D + design-note AC4 / iter-1 FN5 broad-pattern SKIP).
        neutralize_eligible = (
            bool(pattern)
            and _is_dotclaude_class_pattern(pattern)
            and source == ".gitignore"
            and not _gitignore_has_neutralize_sentinel(target_root)
        )
        return ref_short, neutralize_eligible
    return None, False


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
        ignored_ref, neutralize_eligible = _check_ignored_by_git(target_root, rel_path)
        return TargetMeta(
            exists=False,
            size=0,
            sha256=None,
            line_count=None,
            heading_count=None,
            has_dependency_groups=False,
            python_version_pin=None,
            ignored_by_git=ignored_ref,
            neutralize_eligible=neutralize_eligible,
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
        neutralize_eligible=False,  # only meaningful for ignored missing files
    )


class AdoptionCollisionError(Exception):
    """Raised when apply-time invariants for adoption-mode are violated.

    The current trigger is the Scope #7 `.new` collision rule: if
    `<original>.new` already exists at apply time, fail-loud rather than
    overwrite a file the user may have authored or already-merged.
    `apply_pipeline.py` catches this and converts to `CLIError(exit_code=2)`.
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

      (a0) missing + ignored_by_git, .claude/-class → NEUTRALIZE, manual_review=True
           missing + ignored_by_git, broad pattern  → SKIP,       manual_review=True
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
    # interactive prompt asks the owner.
    if not target_meta.exists and target_meta.ignored_by_git is not None:
        if target_meta.neutralize_eligible:
            # Cleanly NEUTRALIZE-able (`.claude/`-class + root-`.gitignore`-sourced
            # + no pre-existing sentinel). The managed un-ignore block restores
            # git-visibility; it mutates the owner's `.gitignore` AND overrides a
            # `.claude/` ignore they set deliberately, so it ALWAYS needs explicit
            # consent (manual_review_needed=True).
            return PolicyRecommendation(
                policy="NEUTRALIZE",
                reason=(
                    f"target gitignores this path under a .claude/-class rule "
                    f"({target_meta.ignored_by_git}); the managed un-ignore block can "
                    "restore git-visibility — owner must consent (mutates .gitignore)"
                ),
                confidence="high",
                manual_review_needed=True,
            )
        # Ignored, but NOT cleanly NEUTRALIZE-able — a broad pattern the block
        # can't fix (e.g. `*.md`), an ignore sourced from `.git/info/exclude` / a
        # global excludesfile, or a `.gitignore` that already carries the sentinel
        # block. Stay a conservative SKIP (design-note AC4 / iter-1 FN5 + PR #35
        # codex A/B/D); owner decides SKIP-confirm vs WRITE_NEW.
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


def _format_shadow_advisory(shadowing_configs: tuple[str, ...]) -> list[str]:
    """B1 advisory block — emitted whenever the shadow scan found a
    target-owned standalone config. Names each file and the [tool.*] table it
    overrides. Contains only filenames + table names — no raw target content
    (Scope #11 privacy boundary)."""
    lines = ["", "config-shadowing advisory:"]
    for name in shadowing_configs:
        table = "[tool.pytest.ini_options]" if name == "pytest.ini" else "[tool.ruff]"
        lines.append(f"  target owns {name} — it overrides {table} in pyproject.toml")
    lines.append("  ruff/pytest read the standalone file in preference to pyproject.toml; the")
    lines.append("  skill did NOT modify it. Reconcile before relying on the skill's tool config.")
    return lines


def _pyproject_skip_advisory(target_root: Path) -> list[str]:
    """B2 advisory lines for a SKIPped target-owned `pyproject.toml`.

    Three branches keyed off the target file's parse state (only the
    classification leaves this function — no raw content, per Scope #11):
      - malformed TOML → tell the owner to fix it before adding config;
      - has `[tool.*]` / `[project]` deps / `[dependency-groups]` → compare and
        merge via `--diff`, copying ONLY the `[tool.ruff*]` /
        `[tool.pytest.ini_options]` tables, never `[project]` / deps;
      - parses + trivial → the owner may add the skill's tables.
    """
    path = target_root / "pyproject.toml"
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    try:
        data = tomllib.loads(raw.decode("utf-8", errors="replace"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return [
            "note: the target pyproject.toml did not parse as valid TOML; the skill",
            "  left it untouched. Fix the malformed pyproject.toml before adding any",
            "  [tool.ruff] / [tool.pytest.ini_options] config.",
        ]
    has_tool = isinstance(data.get("tool"), dict) and bool(data["tool"])
    project = data.get("project")
    has_deps = bool(isinstance(project, dict) and project.get("dependencies"))
    # isinstance(..., dict) mirrors `_has_dependency_groups_table` / rule (g)'s
    # `_is_nontrivial_pyproject` so the advisory classifier agrees with the
    # policy classifier (a stray `dependency-groups = "foo"` is not a table).
    has_dep_groups = isinstance(data.get("dependency-groups"), dict)
    if has_tool or has_deps or has_dep_groups:
        return [
            "note: the target pyproject.toml was left untouched (SKIP); the skill's",
            "  [tool.ruff] / [tool.pytest.ini_options] config was NOT applied. To adopt",
            "  it, inspect the rendered output with --diff and copy ONLY the [tool.ruff],",
            "  [tool.ruff.lint], [tool.ruff.format] and [tool.pytest.ini_options] tables",
            "  into your pyproject.toml — merge, never replace, and leave your [project]",
            "  and dependency sections alone.",
            "  If a standalone ruff.toml / .ruff.toml / pytest.ini was flagged in the",
            "  config-shadowing advisory above, that file overrides these tables —",
            "  reconcile it first, or copying them into pyproject.toml has no effect.",
        ]
    return [
        "note: the target pyproject.toml was left untouched (SKIP); it has no tool",
        "  config. You may add the skill's [tool.ruff] / [tool.pytest.ini_options]",
        "  tables from the rendered output (inspect with --diff).",
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

    # B1 — always name target-owned standalone configs that shadow pyproject.toml.
    if plan.shadowing_configs:
        lines.extend(_format_shadow_advisory(plan.shadowing_configs))

    # B2 — when the target's own pyproject.toml is SKIPped (rule (g)/(h), i.e.
    # manual-review SKIP — not a byte-identical rule (c) no-op), explain that
    # the skill's [tool.*] config was not applied and how to adopt it safely.
    if any(
        a.rel_path == "pyproject.toml"
        and a.recommendation.policy == "SKIP"
        and a.recommendation.manual_review_needed
        for a in plan.analyses
    ):
        b2 = _pyproject_skip_advisory(plan.target_root)
        if b2:
            lines.append("")
            lines.extend(b2)

    return "\n".join(lines) + "\n"


# pyproject.toml policies that mean "the skill is about to put its [tool.*]
# tables into pyproject.toml": rule (a) WRITE (target has no pyproject.toml)
# and rule (b) OVERWRITE (target's pyproject.toml is empty/whitespace-only).
# Both are manual_review_needed=False by default, so both must be escalated —
# otherwise `--non-interactive` adoption could go green with a pyproject.toml
# whose [tool.*] tables are dead under a target-owned standalone config.
_ESCALATABLE_PYPROJECT_POLICIES = ("WRITE", "OVERWRITE")


def _escalate_pyproject_for_shadow(
    analyses: list[PlannedFileAnalysis], shadowing_configs: tuple[str, ...]
) -> list[PlannedFileAnalysis]:
    """Escalate a skill-written `pyproject.toml` to manual review when a
    target-owned standalone config would shadow its [tool.*] tables.

    Escalated when the `pyproject.toml` recommendation is rule (a) WRITE
    (target has no `pyproject.toml`) or rule (b) OVERWRITE (target's
    `pyproject.toml` is empty/whitespace-only) — both cases write the skill's
    `[tool.ruff]` / `[tool.pytest.ini_options]` into `pyproject.toml`, where
    the target-owned standalone file would silently override them. `policy`
    stays WRITE/OVERWRITE (the project genuinely needs a populated
    `pyproject.toml`; SKIP would break the skill's Makefile/render contract) —
    only `manual_review_needed` flips True, so interactive adoption prompts the
    owner and `--non-interactive` exits 2 instead of going green with dead
    config.

    A target that already HAS a non-empty `pyproject.toml` routes through rule
    (g)/(h) SKIP and is already `manual_review_needed=True` — no escalation
    needed; the always-on B1 report advisory still names the shadowing file(s).
    """
    files = ", ".join(shadowing_configs)
    escalated: list[PlannedFileAnalysis] = []
    for analysis in analyses:
        rec = analysis.recommendation
        if analysis.rel_path == "pyproject.toml" and rec.policy in _ESCALATABLE_PYPROJECT_POLICIES:
            escalated.append(
                analysis._replace(
                    recommendation=rec._replace(
                        manual_review_needed=True,
                        reason=(
                            f"target owns standalone config ({files}) that would "
                            f"shadow the [tool.*] tables the skill writes into "
                            f"pyproject.toml (ruff/pytest read the standalone file "
                            f"in preference to pyproject.toml); owner must review"
                        ),
                    )
                )
            )
        else:
            escalated.append(analysis)
    return escalated


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

    Caller contract: the caller (`apply_pipeline.py`) is responsible for validating that
    `target_root` is an existing directory AND that every `planned_files` key
    is CLI-layer path-safe (no absolute paths, no `..` segments). Path-safety
    enforcement lives in `apply_pipeline.py` + `render.py` per Architecture decisions;
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

    # B1 shadow scan (config-shadowing fix plan, Bucket B). Run ONCE here; the
    # result is stored on the plan and consumed by both the escalation below
    # and `format_recommendation_report` — never rescanned, so the escalation
    # decision and the report advisory cannot drift apart.
    shadowing_configs = scan_shadowing_configs(target_root)
    if shadowing_configs:
        analyses = _escalate_pyproject_for_shadow(analyses, shadowing_configs)

    return AdoptionPlan(
        target_root=target_root,
        analyses=tuple(analyses),
        shadowing_configs=shadowing_configs,
    )


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
    "scan_shadowing_configs",
]
