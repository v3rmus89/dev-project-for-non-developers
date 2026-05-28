from pathlib import Path

import jinja2

from bootstrap_lib.paths import validate_target_path

SKILL_ROOT = Path(__file__).resolve().parent.parent

SHARED_TEMPLATE_MAP = {
    "AGENTS.md": "AGENTS.md.tmpl",
    "CLAUDE.md": "CLAUDE.md.tmpl",
    "CONTRIBUTING.md": "CONTRIBUTING.md.tmpl",
    "BACKLOG.md": "BACKLOG.md.tmpl",
    "LESSONS.md": "LESSONS.md.tmpl",
    ".github/pull_request_template.md": "pull_request_template.md.tmpl",
    ".github/workflows/claude-review.yml": "claude-review.yml.tmpl",
    "docs/plans/README.md": "docs-plans-README.md.tmpl",
    "docs/SMOKE.md": "docs-SMOKE.md.tmpl",
    "docs/codex-github-review-setup.md": "docs-codex-github-review-setup.md.tmpl",
    ".editorconfig": "editorconfig.tmpl",
    "scripts/run-with-clean-env.py": "scripts-run-with-clean-env.py.tmpl",
    "scripts/loop-status.py": "scripts-loop-status.py.tmpl",
    "scripts/extract-plan-facts.py": "scripts-extract-plan-facts.py.tmpl",
    "scripts/verify-plan-facts.py": "scripts-verify-plan-facts.py.tmpl",
}

PYTHON_TEMPLATE_MAP = {
    "Makefile": "Makefile.tmpl",
    ".pre-commit-config.yaml": ".pre-commit-config.yaml.tmpl",
    "pyproject.toml": "pyproject.toml.tmpl",
    "requirements-dev.txt": "requirements-dev.txt.tmpl",
    ".gitignore": ".gitignore.tmpl",
    ".github/workflows/ci.yml": "ci.yml.tmpl",
    ".python-version": ".python-version.tmpl",
    "tests/test_smoke.py": "tests-test_smoke.py.tmpl",
    "src/main.py": "src-main.py.tmpl",
}

NODEJS_TEMPLATE_MAP = {
    "Makefile": "Makefile.tmpl",
    "package.json": "package.json.tmpl",
    "tsconfig.json": "tsconfig.json.tmpl",
    "biome.json": "biome.json.tmpl",
    "vitest.config.ts": "vitest.config.ts.tmpl",
    ".gitignore": ".gitignore.tmpl",
    ".github/workflows/ci.yml": "ci.yml.tmpl",
    ".husky/pre-commit": ".husky-pre-commit.tmpl",
    ".husky/pre-push": ".husky-pre-push.tmpl",
    "tests/test_smoke.test.ts": "tests-test_smoke.test.ts.tmpl",
    "src/main.ts": "src-main.ts.tmpl",
}

GO_TEMPLATE_MAP = {
    "Makefile": "Makefile.tmpl",
    "go.mod": "go.mod.tmpl",
    ".golangci.yml": ".golangci.yml.tmpl",
    ".gitignore": ".gitignore.tmpl",
    ".github/workflows/ci.yml": "ci.yml.tmpl",
    "hooks/pre-commit": "hooks-pre-commit.tmpl",
    "hooks/pre-push": "hooks-pre-push.tmpl",
    "main.go": "main.go.tmpl",
    "main_test.go": "main_test.go.tmpl",
}

LANGUAGE_TEMPLATE_MAPS = {
    "python": PYTHON_TEMPLATE_MAP,
    "nodejs": NODEJS_TEMPLATE_MAP,
    "go": GO_TEMPLATE_MAP,
}


def build_env(language):
    loader = jinja2.FileSystemLoader(
        [
            str(SKILL_ROOT / "languages" / language),
            str(SKILL_ROOT / "shared"),
        ]
    )
    return jinja2.Environment(
        loader=loader,
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )


def _emit_in_mode(rel_out, mode, enable_smoke):
    if rel_out == ".github/workflows/claude-review.yml" and mode == "none":
        return False
    if rel_out == "docs/codex-github-review-setup.md" and mode != "both-docs":
        return False
    return not (rel_out == "docs/SMOKE.md" and not enable_smoke)


def _emit_python_in_pm_mode(rel_out, package_manager):
    """Filter Python-language template entries by package_manager mode.

    Closes Codex Tier-2 #6: normalize `None`/missing values to `"pip"` as
    the first line. Without normalization, a non-aware caller that omits
    `"package_manager"` from the context dict would pass `None` here, and
    neither `None == "uv"` nor `None == "pip"` would match — both
    `requirements-dev.txt` AND `.python-version` would render,
    contradicting the shared-templates `|default("pip")` safety convention.

    Defaulting to `"pip"` preserves pre-PR-#6 rendering for non-aware
    callers (existing tests that construct context dicts manually).

    Real CLI flow resolves `package_manager` to a non-None string via
    `bootstrap_lib.cli._resolve_package_manager` BEFORE context build;
    the normalization here defends only against direct `render_all`
    callers (tests, future programmatic consumers).
    """
    pm = package_manager or "pip"
    if rel_out == "requirements-dev.txt" and pm == "uv":
        return False
    return not (rel_out == ".python-version" and pm == "pip")


def planned_paths(language, github_review_mode="none", enable_smoke=False, package_manager=None):
    """Return the set of output paths `render_all` would write for a config.

    Mirrors `render_all`'s key selection exactly — applies the same
    `_emit_in_mode` / `_emit_python_in_pm_mode` filters to the template-map
    keys — but renders nothing (no Jinja, no context dict). The interactive
    intake (`bootstrap_lib.intake`) uses this for its greenfield
    collision check.

    `package_manager=None` is normalized to `"pip"` by `_emit_python_in_pm_mode`
    exactly as in `render_all`, so the returned path set stays identical to
    `set(render_all(...).keys())` for the same config — a property locked by
    `tests/test_render.py::test_planned_paths_equals_render_all_keys`.
    """
    paths = set()
    for rel_out in SHARED_TEMPLATE_MAP:
        if _emit_in_mode(rel_out, github_review_mode, enable_smoke):
            paths.add(rel_out)
    try:
        lang_map = LANGUAGE_TEMPLATE_MAPS[language]
    except KeyError:
        raise ValueError(f"unsupported language: {language!r}") from None
    for rel_out in lang_map:
        if language == "python" and not _emit_python_in_pm_mode(rel_out, package_manager):
            continue
        paths.add(rel_out)
    return paths


def render_all(context, language="python"):
    env = build_env(language)
    mode = context.get("github_review_mode", "none")
    enable_smoke = bool(context.get("enable_smoke", False))
    package_manager = context.get("package_manager")

    output = {}

    for rel_out, tmpl_name in SHARED_TEMPLATE_MAP.items():
        if not _emit_in_mode(rel_out, mode, enable_smoke):
            continue
        output[rel_out] = env.get_template(tmpl_name).render(**context).encode("utf-8")

    try:
        lang_map = LANGUAGE_TEMPLATE_MAPS[language]
    except KeyError:
        raise ValueError(f"unsupported language: {language!r}") from None

    for rel_out, tmpl_name in lang_map.items():
        # Python-specific package-manager filtering. For non-python
        # languages, _emit_python_in_pm_mode is a no-op (no entries match
        # the filenames it checks).
        if language == "python" and not _emit_python_in_pm_mode(rel_out, package_manager):
            continue
        output[rel_out] = env.get_template(tmpl_name).render(**context).encode("utf-8")

    # First-tier path-safety check: every rel_path stays inside a notional root
    # (cross-platform-safe — uses temp dir to absorb resolve() side-effects)
    import tempfile

    sandbox = Path(tempfile.gettempdir()) / "_dev-project-setup-path-validate"
    for rel_path in output:
        validate_target_path(sandbox, rel_path)

    return output
