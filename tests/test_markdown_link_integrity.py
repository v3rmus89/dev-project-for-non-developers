"""General in-repo markdown link-existence gate (Bucket D).

Every markdown-link-form reference to an in-repo path, in every TRACKED
markdown file, must resolve to something that exists relative to the linking
file's directory. Moving `docs/plans/*.md` into `docs/plans/archive/` is what
motivated this, but the gate is deliberately general: it locks the whole
link-rot class, so any future file move that orphans an in-tree link turns
`make check` red instead of rotting silently.

Two exemptions are structural, not a denylist:

  - **Inline-code spans and fenced code blocks are not links.** A backticked
    `` `[Makefile](Makefile)` `` is documentation OF link syntax — the active
    plan file shows exactly that — and a naive `\\[..\\]\\(..\\)` regex would
    flag it. Code spans are masked and fenced blocks skipped before matching.
  - **External URLs and intra-page anchors** (`https://…`, `mailto:`, `#section`)
    have no in-repo path to check.

Nothing else is exempt: pre-existing breakage was NORMALIZED by the same commit
that introduced this test rather than allowlisted, so the gate has no
grandfathered exceptions to erode.

Fence tracking reuses `scripts/extract-plan-facts.py::_FenceTracker` — the
CommonMark-correct implementation this repo already ships and tests — rather
than adding a fourth hand-rolled toggle.

Covered link forms: inline (`[text](target)`), reference-style definitions
(`[label]: target`), and either with an angle-bracket target (`[t](<path>)`).
Raw HTML anchors are NOT covered — none exist in this corpus, and adding an
HTML parser to catch a form nothing uses would be cost without coverage.

A bare target ends at the first `)`, so a filename containing parentheses
(`[g](guide(v2).md)`) must use the angle-bracket form (`[g](<guide(v2).md>)`),
which this gate resolves correctly. Balanced-paren parsing is parked in
BACKLOG.md rather than built: no such filename exists here (plan files are
dated slugs), and the workaround is one character at each end.

Scope note: this gate covers markdown LINK form only. Backticked path
citations (`` `docs/plans/foo.md` ``) are prose, not links, and stay unchecked;
the two `DEFAULT_PLAN` script constants get their own existence assertions in
tests/test_ab_replay_lib.py and tests/test_verify_v13_5.py. Intra-page anchors
are exempt as paths, and their slugs are not resolved against the target file's
headings either — parked in BACKLOG.md as `markdown-anchor-resolution`.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent

# `[text](target)` / `![alt](target)`, with an optional "title" after the target.
# A bare target stops at whitespace or `)`; an angle-bracket target may contain
# spaces. Escaped `\[` does not open a link.
_LINK_RE = re.compile(
    r"(?<!\\)\[(?P<text>[^\]]*)\]\(\s*"
    r"(?:<(?P<angle>[^>\n]*)>|(?P<bare>[^)\s]*))"
    r"(?:\s+\"[^\"]*\")?\s*\)"
)
# Reference-style definition: `[label]: target "optional title"`, up to 3 spaces
# of indent (CommonMark). The label is resolved elsewhere in the doc, but the
# TARGET is a path like any other and rots the same way.
_REF_DEF_RE = re.compile(r"^ {0,3}\[(?P<label>[^\]]+)\]:\s+(?:<(?P<angle>[^>\n]*)>|(?P<bare>\S+))")
_BACKTICK_RUN_RE = re.compile(r"`+")
# RFC 3986 scheme: letter, then letters/digits/`+`/`-`/`.`, then `:`. A relative
# path cannot match it — `docs/foo:bar.md` has a `/` before the colon, and `/`
# is not in the scheme character set.
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


def _load_fence_tracker():
    spec = importlib.util.spec_from_file_location(
        "extract_plan_facts", SKILL_ROOT / "scripts" / "extract-plan-facts.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._FenceTracker


_FenceTracker = _load_fence_tracker()


def _mask_code_spans(line: str) -> str:
    """Blank out inline-code span CONTENTS, preserving line length.

    Offsets stay stable so a caller can still slice the original line; a link
    inside backticks simply stops matching.
    """
    out = list(line)
    i, n = 0, len(line)
    while i < n:
        m = _BACKTICK_RUN_RE.match(line, i)
        if not m:
            i += 1
            continue
        # A backslash-escaped backtick is a literal character, not a delimiter:
        # in `\`[x](nope.md)\`` CommonMark leaves the link ACTIVE. Masking it
        # would hide a broken target — a silent pass, the failure this gate
        # exists to prevent.
        if (len(line[: m.start()]) - len(line[: m.start()].rstrip("\\"))) % 2 == 1:
            i = m.start() + 1
            continue
        ticks = m.group(0)
        close = line.find(ticks, m.end())
        if close == -1:  # unterminated run: not a span, keep scanning after it
            i = m.end()
            continue
        for j in range(m.start(), close + len(ticks)):
            out[j] = " "
        i = close + len(ticks)
    return "".join(out)


def _is_checkable(target: str) -> bool:
    """False for targets with no in-repo path to resolve.

    Externality is decided by URI SCHEME, not by the presence of `://`: `tel:`,
    `sms:`, and `data:` are perfectly valid targets with no `//` in them, and
    treating them as repo-relative paths would fail `make check` on a document
    that is entirely correct. `//host/path` (protocol-relative) is external for
    the same reason — and would otherwise be read as a root-relative path.
    """
    if not target or target.startswith(("#", "<", "//")):
        return False
    return not _URI_SCHEME_RE.match(target)


def _target_of(m: re.Match) -> str:
    """The path from either target form; angle brackets are delimiters, not path."""
    angle = m.group("angle")
    return angle if angle is not None else m.group("bare")


def iter_links(text: str):
    """Yield (lineno, target) for every real (un-backticked, un-fenced) link.

    Covers both inline links and reference-style definitions, in bare and
    angle-bracket target form. A fence opener/closer line is skipped whole, so a
    link sharing that line is not checked — per CommonMark the text after an
    opener is the info string, and a closer may hold nothing but the fence, so
    there is no real link to miss there.
    """
    fences = _FenceTracker()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        boundary = fences.feed(raw)
        if boundary or fences.in_fence:
            continue
        masked = _mask_code_spans(raw)
        for m in _LINK_RE.finditer(masked):
            yield lineno, _target_of(m)
        ref = _REF_DEF_RE.match(masked)
        if ref:
            yield lineno, _target_of(ref)


def _is_tracked(resolved: Path, root: Path, tracked: set[str]) -> bool:
    """A file must be in the index; a directory must contain something that is."""
    rel = str(resolved.relative_to(root.resolve()))
    return rel in tracked or any(k.startswith(rel + "/") for k in tracked)


def broken_links(
    path: Path, root: Path = SKILL_ROOT, tracked: set[str] | None = None
) -> list[tuple[int, str]]:
    """Every in-repo link in *path* that does not resolve.

    Targets resolve from the linking file's directory, EXCEPT root-relative ones
    (`/docs/foo.md`), which GitHub resolves against the repo root. Without that
    case, `Path.parent / "/docs/foo.md"` would resolve against the filesystem
    root and report a perfectly good link as broken — a false failure, which is
    the one way a gate like this loses its authority.
    """
    broken = []
    for lineno, target in iter_links(path.read_text(encoding="utf-8")):
        if not _is_checkable(target):
            continue
        bare = target.split("#", 1)[0].split("?", 1)[0]
        if not bare:
            continue
        base = root if bare.startswith("/") else path.parent
        # `[g](a%20b.md)` is how a link to `a b.md` is written; GitHub decodes
        # it, so asking the filesystem for the literal `%20` name would fail a
        # correct link.
        resolved = (base / unquote(bare.lstrip("/"))).resolve()
        # Containment, not just existence: `../../etc/passwd` exists on most
        # machines and would pass an exists()-only check, but it is not an
        # in-repo target and 404s for every reader on GitHub. A link that only
        # works on the author's filesystem is broken.
        if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
            broken.append((lineno, target))
        elif tracked is not None and not _is_tracked(resolved, root, tracked):
            # Existing-but-untracked is a 404 for every reader after push: the
            # file is on this machine and not in the commit. Same silent-pass
            # class as the traversal case above.
            broken.append((lineno, target))
    return broken


def _tracked_markdown() -> list[str]:
    # -z: NUL-separated and never quote-escaped, so a path containing a space
    # stays one path instead of splitting into two nonexistent ones.
    r = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(p for p in r.stdout.split("\0") if p)


def _tracked_files() -> set[str]:
    r = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {p for p in r.stdout.split("\0") if p}


TRACKED_MARKDOWN = _tracked_markdown()
TRACKED_FILES = _tracked_files()


# ── the gate ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rel_path", TRACKED_MARKDOWN)
def test_in_repo_links_resolve(rel_path):
    path = SKILL_ROOT / rel_path
    broken = broken_links(path, tracked=TRACKED_FILES)
    assert not broken, "\n".join(
        [f"{rel_path} has in-repo links that do not resolve:"]
        + [f"  line {lineno}: ({target})" for lineno, target in broken]
    )


# ── the gate is not vacuous ────────────────────────────────────────────────


def test_tracked_markdown_set_is_populated():
    """A `git ls-files` that returned nothing would make every case above pass."""
    assert len(TRACKED_MARKDOWN) >= 20, (
        f"expected the repo's markdown corpus, found {len(TRACKED_MARKDOWN)} files"
    )
    assert "docs/plans/README.md" in TRACKED_MARKDOWN


def test_scan_finds_a_substantial_number_of_links():
    """A regex that silently stopped matching would green the whole gate."""
    found = sum(
        1
        for rel in TRACKED_MARKDOWN
        for _lineno, target in iter_links((SKILL_ROOT / rel).read_text(encoding="utf-8"))
        if _is_checkable(target)
    )
    assert found >= 30, f"only {found} in-repo links found across the corpus — parser broken?"


def test_a_real_break_is_detected(tmp_path):
    """The detector must actually fail on a broken link (not just never fire)."""
    doc = tmp_path / "doc.md"
    doc.write_text("See [the thing](does-not-exist.md).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == [(1, "does-not-exist.md")]


def test_a_resolving_link_is_accepted(tmp_path):
    (tmp_path / "target.md").write_text("hi\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("See [the thing](target.md#anchor).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


# ── exemptions ─────────────────────────────────────────────────────────────


def test_code_span_link_is_exempt(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("Link syntax looks like `[Makefile](Makefile)` in prose.\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_double_backtick_span_link_is_exempt(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("A span holding a backtick: `` [x](nope.md) `` here.\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_fenced_block_link_is_exempt(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("```\n[x](nope.md)\n```\n\ntext\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_nested_fence_does_not_reopen_the_scan(tmp_path):
    """A 3-backtick line inside a 4-backtick block is content, not a boundary —
    the naive toggle would treat it as a close and start checking links again."""
    doc = tmp_path / "doc.md"
    doc.write_text("````\n```\n[x](nope.md)\n```\n````\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_external_and_anchor_targets_are_exempt(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(
        "[a](https://example.com/x.md) [b](#section) [c](mailto:x@example.com)\n",
        encoding="utf-8",
    )
    assert broken_links(doc, root=tmp_path) == []


def test_link_after_a_closed_fence_is_still_checked(tmp_path):
    """The fence must close: a break in prose following a code block is real."""
    doc = tmp_path / "doc.md"
    doc.write_text("```\ncode\n```\n\n[x](nope.md)\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == [(5, "nope.md")]


# ── link forms beyond the plain inline one ─────────────────────────────────


def test_reference_style_definition_is_checked(tmp_path):
    """`[label]: target` is a link form and rots exactly like an inline one."""
    doc = tmp_path / "doc.md"
    doc.write_text("See [the thing][t].\n\n[t]: does-not-exist.md\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == [(3, "does-not-exist.md")]


def test_reference_style_definition_that_resolves_is_accepted(tmp_path):
    (tmp_path / "target.md").write_text("hi\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text('[t]: target.md "A title"\n', encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_reference_style_definition_in_fence_is_exempt(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("```\n[t]: nope.md\n```\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_angle_bracket_target_is_checked(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("See [x](<does-not-exist.md>).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == [(1, "does-not-exist.md")]


def test_angle_bracket_target_with_a_space_is_checked(tmp_path):
    """The form exists precisely to allow spaces, which the bare form cannot."""
    doc = tmp_path / "doc.md"
    doc.write_text("See [x](<no such file.md>).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == [(1, "no such file.md")]


def test_angle_bracket_target_that_resolves_is_accepted(tmp_path):
    (tmp_path / "a target.md").write_text("hi\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("See [x](<a target.md>).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_root_relative_target_resolves_against_the_repo_root(tmp_path):
    """`[x](/docs/foo.md)` is valid GitHub markdown; naive joining would resolve
    it against the FILESYSTEM root and report a good link as broken."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "foo.md").write_text("hi\n", encoding="utf-8")
    doc = tmp_path / "sub" / "doc.md"
    doc.parent.mkdir()
    doc.write_text("See [x](/docs/foo.md).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_root_relative_target_that_is_missing_is_still_caught(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("See [x](/docs/nope.md).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == [(1, "/docs/nope.md")]


def test_scheme_targets_without_a_double_slash_are_exempt(tmp_path):
    """`tel:`/`sms:`/`data:` have no `://`; treating them as paths false-fails."""
    doc = tmp_path / "doc.md"
    doc.write_text(
        "[a](tel:+15551212) [b](sms:+15551212) [c](data:image/png;base64,AAA)\n",
        encoding="utf-8",
    )
    assert broken_links(doc, root=tmp_path) == []


def test_protocol_relative_url_is_exempt(tmp_path):
    """`//host/path` is external — and would otherwise read as root-relative."""
    doc = tmp_path / "doc.md"
    doc.write_text("See [x](//example.com/foo.md).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_a_colon_in_a_relative_path_is_not_a_scheme(tmp_path):
    """`docs/foo:bar.md` is a path, not a URI — the `/` precedes the colon."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "foo:bar.md").write_text("hi\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("See [x](docs/foo:bar.md).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_target_escaping_the_repo_is_broken_even_when_it_exists(tmp_path):
    """A link that resolves only on the author's filesystem 404s for readers."""
    outside = tmp_path / "outside.md"
    outside.write_text("hi\n", encoding="utf-8")
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    doc = repo / "docs" / "doc.md"
    doc.write_text("See [x](../../outside.md).\n", encoding="utf-8")
    assert outside.exists(), "fixture must exist, or the test proves nothing"
    assert broken_links(doc, root=repo) == [(1, "../../outside.md")]


def test_escaped_backticks_do_not_mask_a_live_link(tmp_path):
    r"""`\`[x](nope.md)\`` — escaped backticks are literal, so the link is ACTIVE.
    Treating them as code-span delimiters would hide a broken target."""
    doc = tmp_path / "doc.md"
    doc.write_text("A literal backtick pair: \\`[x](nope.md)\\` here.\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == [(1, "nope.md")]


def test_unescaped_backticks_still_mask(tmp_path):
    """The escape handling must not break the ordinary code-span case."""
    doc = tmp_path / "doc.md"
    doc.write_text("Ordinary span: `[x](nope.md)` here.\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_percent_encoded_target_is_decoded(tmp_path):
    """`[g](a%20b.md)` is how a link to `a b.md` is written; GitHub decodes it."""
    (tmp_path / "a b.md").write_text("hi\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("See [g](a%20b.md).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path) == []


def test_untracked_target_is_broken_even_though_it_exists(tmp_path):
    """A file on disk but not in the commit 404s for every reader after push."""
    (tmp_path / "scratch.md").write_text("hi\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("See [x](scratch.md).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path, tracked=set()) == [(1, "scratch.md")]
    assert broken_links(doc, root=tmp_path, tracked={"scratch.md"}) == []


def test_directory_target_counts_as_tracked_when_it_holds_a_tracked_file(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("hi\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("See [d](docs).\n", encoding="utf-8")
    assert broken_links(doc, root=tmp_path, tracked={"docs/a.md"}) == []
