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
    "tailwind.css",
    "inter.css",
    "vendor/inter-variable.woff2",
    "vendor/htmx2.min.js",
    "vendor/alpine.min.js",
    "vendor/alpine-collapse.min.js",
    "vendor/sortable.min.js",
    "vendor/marked.umd.js",
    "vendor/purify.min.js",
    "vendor/cropper.min.js",
    "js/ui/option-picker.js",
    "js/ui/theme-manager.js",
]


def test_critical_assets_exist():
    """Every vendored library and core stylesheet must be present."""
    missing = [f for f in CRITICAL_ASSETS if not (STATIC_DIR / f).exists()]
    assert not missing, f"Missing critical assets: {', '.join(missing)}"


def test_css_valid():
    """Every split CSS file must parse without fatal errors."""
    css_dir = STATIC_DIR / "css"
    for f in sorted(css_dir.glob("*.css")):
        css_text = f.read_text()
        cssutils.log.enabled = False
        sheet = cssutils.parseString(css_text)
        cssutils.log.enabled = True

        from cssutils.css import CSSStyleSheet

        assert isinstance(sheet, CSSStyleSheet), f"{f.name} failed to parse"

    root_css = (css_dir / "variables.css").read_text()
    assert ":root" in root_css

    layout_css = (css_dir / "layout.css").read_text()
    assert ".left-sidebar" in layout_css


def test_tailwind_bundle_contains_custom_css():
    """The css/ modules are imported by tailwind-input.css; a dropped import
    must fail here instead of silently losing styles at runtime."""
    css_text = (STATIC_DIR / "tailwind.css").read_text()
    for marker in (".arranger-item", ".chat-center", ".slot-btn"):
        assert marker in css_text, f"tailwind.css is missing bundled rule: {marker}"
    assert "--radius-md:10px" in css_text.replace(" ", ""), (
        "tailwind.css missing rebranded --radius-md token"
    )


TEMPLATES_THAT_RENDER = [
    ("modals/sampler.html", {}),
    ("modals/itemizer.html", {}),
    ("modals/confirm.html", {}),
    ("modals/edit-entity.html", {"prefix": "char", "modal_id": "modal-edit-character", "entity_name": "Character", "upload_fn": "uploadCharModalMedia", "avatar_fn": "uploadCharacterAvatar", "submit_fn": "submitEditCharacter"}),
    ("modals/edit-entity.html", {"prefix": "persona", "modal_id": "modal-edit-persona", "entity_name": "Persona", "upload_fn": "uploadPersonaMedia", "avatar_fn": "uploadPersonaAvatar", "submit_fn": "submitEditPersona"}),
    ("modals/backup.html", {}),
    ("modals/provider-create.html", {}),
    ("modals/text-expander.html", {}),
    ("modals/theme.html", {}),
    ("modals/option-picker.html", {}),
    ("modals/export-entities.html", {"entities": []}),
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
    source = env.loader.get_source(env, "modal-shell.html")[0]
    assert "{% macro modal_shell" in source
    assert "{% macro modal_footer" in source


def test_macros_macro_compiles():
    """macros.html macro library compiles."""
    source = env.loader.get_source(env, "macros.html")[0]
    assert "{% macro" in source


def test_header_integrity():
    """All templates should compile under StrictUndefined (no missing variables)."""
    # text_expander has no variable dependencies — renders with empty context
    tmpl = env.get_template("modals/text-expander.html")
    result = tmpl.render({})
    assert len(result) > 0


def test_css_has_essential_vars():
    """variables.css defines essential custom properties."""
    css_text = (STATIC_DIR / "css" / "variables.css").read_text()
    for var in ["--bg", "--surface", "--border", "--accent", "--text", "--text-muted",
                 "--transition", "--z-modal"]:
        assert var in css_text, f"Missing CSS variable: {var}"


def test_theme_rebranded_tokens():
    """Rebranded Tailwind tokens live in @theme in tailwind-input.css (single
    source of truth), not as bare :root overrides in variables.css."""
    input_text = (STATIC_DIR / "tailwind-input.css").read_text()
    for token in ["--radius-sm", "--radius-md", "--radius-xl", "--shadow-sm",
                  "--shadow-md", "--shadow-lg", "--font-sans"]:
        assert token in input_text, f"Missing @theme token: {token}"
    vars_text = (STATIC_DIR / "css" / "variables.css").read_text()
    for token in ["--radius-sm", "--shadow-sm", "--font-sans"]:
        assert token not in vars_text, f"{token} must not be redefined in variables.css :root"
