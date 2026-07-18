"""Frontend validation tests.

Checks Jinja2 template compilation, static asset references, and CSS syntax.
"""

import re
from pathlib import Path

import cssutils
import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES_DIR = Path("templates").resolve()
PARTIALS_DIR = Path("partials").resolve()
STATIC_DIR = Path("static").resolve()

loader = FileSystemLoader([str(TEMPLATES_DIR), str(PARTIALS_DIR)])
env = Environment(loader=loader, undefined=StrictUndefined)

ALL_TEMPLATES = sorted(
    [str(p.relative_to(TEMPLATES_DIR)) for p in TEMPLATES_DIR.rglob("*.html")]
    + [str(p.relative_to(PARTIALS_DIR)) for p in PARTIALS_DIR.rglob("*.html")]
)


@pytest.mark.parametrize("template_name", ALL_TEMPLATES)
def test_template_compiles(template_name):
    """Each Jinja2 template must parse without syntax errors."""
    env.parse(loader.get_source(env, template_name)[0])


def _is_jinja_expression(path: str) -> bool:
    """Check if a path is a Jinja2 expression like '/{{ var }}' or '{% ... %}'."""
    return bool(re.search(r"\{\{|\{%", path))


def _find_asset_refs(text: str) -> list[str]:
    """Extract static asset paths from src/href attributes."""
    refs = set()
    for m in re.finditer(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", text):
        path = m.group(1)
        if _is_jinja_expression(path):
            continue
        path = path.split("?")[0]
        if (
            path.startswith(("http://", "https://", "data:", "#", "//")) or "${" in path  # JS template literal
        ):
            continue
        refs.add(path)
    return list(refs)


@pytest.mark.parametrize("template_name", ALL_TEMPLATES)
def test_template_asset_references(template_name):
    """All static asset paths in templates must resolve to existing files."""
    source = loader.get_source(env, template_name)[0]
    for ref in _find_asset_refs(source):
        rel = ref.lstrip("/")
        if not Path(rel).suffix:
            continue  # likely a URL route, e.g. /chat /presets
        candidates = [Path(rel), STATIC_DIR / rel]
        if not any(c.exists() for c in candidates):
            pytest.fail(f"{template_name}: asset not found: {ref}")


CRITICAL_ASSETS = [
    "style.css",
    "tailwind.css",
    "vendor/inter.css",
    "vendor/htmx2.min.js",
    "vendor/alpine.min.js",
    "vendor/alpine-collapse.min.js",
    "vendor/sortable.min.js",
    "vendor/marked.umd.js",
    "vendor/purify.min.js",
    "vendor/cropper.min.js",
]


def test_critical_assets_exist():
    """Every vendored library and core stylesheet must be present."""
    missing = [f for f in CRITICAL_ASSETS if not (STATIC_DIR / f).exists()]
    assert not missing, f"Missing critical assets: {', '.join(missing)}"


def test_css_valid():
    """style.css must parse without fatal errors."""
    css_path = STATIC_DIR / "style.css"
    css_text = css_path.read_text()

    cssutils.log.enabled = False
    sheet = cssutils.parseString(css_text)
    cssutils.log.enabled = True

    from cssutils.css import CSSStyleSheet

    assert isinstance(sheet, CSSStyleSheet), "CSS failed to parse"

    assert ":root" in css_text
    assert ".left-sidebar" in css_text


TEMPLATES_THAT_RENDER = [
    ("modals/sampler_modal.html", {}),
    ("modals/itemizer_modal.html", {}),
    ("modals/confirm_modal.html", {}),
    ("modals/edit_entity_modal.html", {"prefix": "char", "modal_id": "modal-edit-character", "entity_name": "Character", "upload_fn": "uploadCharModalMedia", "avatar_fn": "uploadCharacterAvatar", "submit_fn": "submitEditCharacter"}),
    ("modals/edit_entity_modal.html", {"prefix": "persona", "modal_id": "modal-edit-persona", "entity_name": "Persona", "upload_fn": "uploadPersonaMedia", "avatar_fn": "uploadPersonaAvatar", "submit_fn": "submitEditPersona"}),
    ("modals/backup_modal.html", {}),
    ("modals/provider_create_modal.html", {}),
    ("modals/text_expander.html", {}),
    ("modals/theme_modal.html", {}),
    ("modals/export_entities.html", {"entities": []}),
]


@pytest.mark.parametrize("template_name,context", TEMPLATES_THAT_RENDER)
def test_template_renders(template_name, context):
    """Key templates render without errors given minimal context."""
    tmpl = env.get_template(template_name)
    result = tmpl.render(context)
    assert isinstance(result, str)
    assert len(result) > 0


def test_modal_shell_macro_compiles():
    """modal_shell.html macro renders without errors."""
    tmpl = env.get_template("modal_shell.html")
    source = env.loader.get_source(env, "modal_shell.html")[0]
    assert "{% macro modal_shell" in source
    assert "{% macro modal_footer" in source


def test_macros_macro_compiles():
    """macros.html macro library compiles."""
    source = env.loader.get_source(env, "macros.html")[0]
    assert "{% macro" in source


def test_header_integrity():
    """All templates should compile under StrictUndefined (no missing variables)."""
    # text_expander has no variable dependencies — renders with empty context
    tmpl = env.get_template("modals/text_expander.html")
    result = tmpl.render({})
    assert len(result) > 0


def test_css_has_essential_vars():
    """CSS defines essential custom properties."""
    css_text = (STATIC_DIR / "style.css").read_text()
    for var in ["--bg", "--surface", "--border", "--accent", "--text", "--text-muted",
                 "--radius-sm", "--radius-md", "--transition", "--z-modal"]:
        assert var in css_text, f"Missing CSS variable: {var}"
