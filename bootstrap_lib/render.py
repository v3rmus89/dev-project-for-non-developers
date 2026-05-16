from pathlib import Path

import jinja2

from bootstrap_lib.paths import validate_target_path

SKILL_ROOT = Path(__file__).resolve().parent.parent

SHARED_TEMPLATE_MAP = {
    "AGENTS.md": "AGENTS.md.tmpl",
    "CLAUDE.md": "CLAUDE.md.tmpl",
    "CONTRIBUTING.md": "CONTRIBUTING.md.tmpl",
    "BACKLOG.md": "BACKLOG.md.tmpl",
    ".github/pull_request_template.md": "pull_request_template.md.tmpl",
    ".github/workflows/claude-review.yml": "claude-review.yml.tmpl",
    "docs/plans/README.md": "docs-plans-README.md.tmpl",
    "docs/SMOKE.md": "docs-SMOKE.md.tmpl",
    "docs/codex-github-review-setup.md": "docs-codex-github-review-setup.md.tmpl",
    ".editorconfig": "editorconfig.tmpl",
    "scripts/run-with-clean-env.py": "scripts-run-with-clean-env.py.tmpl",
}

PYTHON_TEMPLATE_MAP = {
    "Makefile": "Makefile.tmpl",
    ".pre-commit-config.yaml": ".pre-commit-config.yaml.tmpl",
    "pyproject.toml": "pyproject.toml.tmpl",
    "requirements-dev.txt": "requirements-dev.txt.tmpl",
    "ruff.toml": "ruff.toml.tmpl",
    "pytest.ini": "pytest.ini.tmpl",
    ".gitignore": ".gitignore.tmpl",
    ".github/workflows/ci.yml": "ci.yml.tmpl",
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


def render_all(context, language="python"):
    env = build_env(language)
    mode = context.get("github_review_mode", "none")
    enable_smoke = bool(context.get("enable_smoke", False))

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
        output[rel_out] = env.get_template(tmpl_name).render(**context).encode("utf-8")

    # First-tier path-safety check: every rel_path stays inside a notional root
    # (cross-platform-safe — uses temp dir to absorb resolve() side-effects)
    import tempfile

    sandbox = Path(tempfile.gettempdir()) / "_dev-project-setup-path-validate"
    for rel_path in output:
        validate_target_path(sandbox, rel_path)

    return output
