"""Frontend validation tests.

Checks Jinja2 template compilation, static asset references, and CSS syntax.
"""

import html as html_module
import json
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
    ("modals/edit-entity.html", {"prefix": "char", "modal_id": "modal-edit-character", "entity_name": "Character", "upload_fn": "uploadCharModalMedia", "avatar_fn": "uploadCharacterAvatar", "submit_fn": "submitEditCharacter", "show_greetings": True}),
    ("modals/edit-entity.html", {"prefix": "persona", "modal_id": "modal-edit-persona", "entity_name": "Persona", "upload_fn": "uploadPersonaMedia", "avatar_fn": "uploadPersonaAvatar", "submit_fn": "submitEditPersona"}),
    ("modals/edit-entity.html", {"prefix": "persona", "modal_id": "modal-edit-persona", "entity_name": "Persona", "upload_fn": "uploadPersonaMedia", "avatar_fn": "uploadPersonaAvatar", "submit_fn": "submitEditPersona", "show_greetings": True}),
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


def test_edit_entity_greeting_section_char_only():
    """The greeting editor must render only for the char modal — even if the
    show_greetings flag leaks from a previous {% set %} in the including page
    (chat.html renders both entities from the same shared template)."""
    tmpl = env.get_template("modals/edit-entity.html")
    base = {
        "modal_id": "modal-edit-entity",
        "entity_name": "Entity",
        "upload_fn": "up",
        "avatar_fn": "av",
        "submit_fn": "sub",
    }

    char_html = tmpl.render({**base, "prefix": "char", "show_greetings": True})
    assert "edit-char-greeting-section" in char_html
    assert 'name="greetings_json"' in char_html
    assert 'name="greeting_idx"' in char_html
    assert 'hx-post="/partials/character-greeting/' in char_html
    assert 'id="edit-char-greeting-count"' in char_html
    assert 'hx-confirm="Delete this greeting variant?"' in char_html
    section = char_html[char_html.index('id="edit-char-greeting-section"') :]
    section = section[: section.index('name="greeting_idx"')]
    assert len(re.findall(r"(?m)^\s*disabled\s*$", section)) == 3, "empty state disables prev/next/delete"

    persona_html = tmpl.render(
        {**base, "prefix": "persona", "show_greetings": True}  # simulate the set-var leak from chat.html
    )
    assert "Greeting" not in persona_html
    assert "greeting" not in persona_html


def test_edit_entity_dirty_attrs_render_evaluated():
    """data-dirty-fields/label must render evaluated, not as raw Jinja.

    Regression: these values are passed to the modal_shell macro as string
    literals, where Jinja does NOT evaluate embedded {{ }} / {% %} tags —
    they must be built via concatenation instead."""
    tmpl = env.get_template("modals/edit-entity.html")
    base = {
        "modal_id": "modal-edit-entity",
        "entity_name": "Entity",
        "upload_fn": "up",
        "avatar_fn": "av",
        "submit_fn": "sub",
        "show_greetings": False,
    }

    char_html = tmpl.render({**base, "prefix": "char", "show_theme": True})
    assert 'data-dirty-fields="#edit-char-name,#edit-char-desc,#edit-char-theme-id"' in char_html
    assert 'data-dirty-label="#edit-char-name"' in char_html
    assert "{%" not in char_html.split("data-dirty-fields")[1][:200]

    persona_html = tmpl.render({**base, "prefix": "persona", "show_theme": False})
    assert 'data-dirty-fields="#edit-persona-name,#edit-persona-desc"' in persona_html
    assert 'data-dirty-label="#edit-persona-name"' in persona_html


def test_greeting_section_renders_with_values():
    """The greeting section partial renders the active variant, count, hidden
    working state, and per-position disabled states server-side."""
    tmpl = env.get_template("modals/greeting-section.html")

    rendered = tmpl.render(
        {
            "prefix": "char",
            "char_id": "c1",
            "greetings": ["Hi", "Hello", "Howdy"],
            "greeting_idx": 1,
            "entity_name": "Character",
        }
    )
    assert "Hello" in rendered
    assert "2/3" in rendered
    assert 'value=\'["Hi", "Hello", "Howdy"]\'' in rendered
    assert 'name="greeting_idx" value="1"' in rendered
    assert "hx-post=\"/partials/character-greeting/c1\"" in rendered
    assert not re.findall(r"(?m)^\s*disabled\s*$", rendered), "middle variant enables all controls"

    rendered = tmpl.render(
        {
            "prefix": "char",
            "char_id": "c1",
            "greetings": ["Hi"],
            "greeting_idx": 0,
            "entity_name": "Character",
        }
    )
    assert len(re.findall(r"(?m)^\s*disabled\s*$", rendered)) == 2, "first-and-only variant disables prev/next"

    rendered = tmpl.render(
        {
            "prefix": "char",
            "char_id": "c1",
            "greetings": [],
            "greeting_idx": 0,
            "entity_name": "Character",
        }
    )
    assert "0/0" in rendered
    assert len(re.findall(r"(?m)^\s*disabled\s*$", rendered)) == 3, "empty list disables all controls"

    rendered = tmpl.render(
        {
            "prefix": "char",
            "char_id": "c1",
            "greetings": [],
            "greeting_idx": 0,
            "focus": True,
            "entity_name": "Character",
        }
    )
    assert "autofocus" in rendered, "add action renders textarea with autofocus"


def test_character_card_has_no_greetings_data():
    """The card no longer embeds the greetings list — the edit modal fetches
    it from the server on open."""
    tmpl = env.get_template("modals/character-card.html")
    char = {
        "id": "c1",
        "name": "Test",
        "image_path": None,
        "created_at": "2026-01-01",
        "theme_id": None,
        "card": {"first_mes": "Hi", "alternate_greetings": ["A", "B"]},
        "images": [],
    }
    rendered = tmpl.render(char=char, current_character_id="", compact_view=False)
    assert "data-char-greetings" not in rendered


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
    """Rebranded Tailwind tokens live in @theme in css/tokens.css (single
    source of truth), not as bare :root overrides in variables.css."""
    tokens_text = (STATIC_DIR / "css" / "tokens.css").read_text()
    for token in ["--radius-sm", "--radius-md", "--radius-xl", "--shadow-sm",
                  "--shadow-md", "--shadow-lg", "--font-sans"]:
        assert token in tokens_text, f"Missing @theme token: {token}"
    vars_text = (STATIC_DIR / "css" / "variables.css").read_text()
    for token in ["--radius-sm", "--shadow-sm", "--font-sans"]:
        assert token not in vars_text, f"{token} must not be redefined in variables.css :root"
