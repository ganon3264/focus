"""Template / asset / CSS lints.

These are checks over the whole tree, not one behaviour each: every lint walks
its collection and reports every offender in one failure. Parametrizing them
per template inflated the suite to 268 near-identical cases without adding
information.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import cssutils
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from focus.core.media import asset_url
from focus.providers.schema import provider_schema, provider_type_options
from tests.helpers import parse_html

TEMPLATES_DIR = Path("templates").resolve()
PARTIALS_DIR = Path("partials").resolve()
STATIC_DIR = Path("static").resolve()

loader = FileSystemLoader([str(TEMPLATES_DIR), str(PARTIALS_DIR)])
env = Environment(loader=loader, undefined=StrictUndefined)

# Mirror the globals registered by focus/routers/pages.py so templates that
# call them can render in tests.
env.globals["asset_url"] = asset_url
env.globals["provider_schema"] = provider_schema
env.globals["provider_type_options"] = provider_type_options

ALL_TEMPLATES = sorted(
    [str(p.relative_to(TEMPLATES_DIR)) for p in TEMPLATES_DIR.rglob("*.html")]
    + [str(p.relative_to(PARTIALS_DIR)) for p in PARTIALS_DIR.rglob("*.html")]
)


def _source(name: str) -> str:
    return loader.get_source(env, name)[0]


def test_templates_compile():
    """Every template must parse."""
    broken = []
    for name in ALL_TEMPLATES:
        try:
            env.parse(_source(name))
        except Exception as exc:
            broken.append(f"{name}: {exc}")
    assert not broken, "templates that do not parse:\n" + "\n".join(broken)


def _is_jinja_expression(path: str) -> bool:
    return bool(re.search(r"\{\{|\{%", path))


def _find_asset_refs(text: str) -> list[str]:
    """Static asset paths from src/href attributes.

    The lookbehind keeps dynamic Alpine bindings (``:src``, ``x-bind:href``) and
    prefixed attributes (``data-src``) from being mistaken for static assets.
    """
    refs = set()
    for m in re.finditer(r"""(?<![\w:-])(?:src|href)\s*=\s*["']([^"']+)["']""", text):
        path = m.group(1)
        if _is_jinja_expression(path):
            continue
        path = path.split("?")[0]
        if path.startswith(("http://", "https://", "data:", "#", "//")) or "${" in path:
            continue
        refs.add(path)
    return list(refs)


def test_template_asset_references_resolve():
    """Every static asset path in a template must exist on disk."""
    missing = []
    for name in ALL_TEMPLATES:
        for ref in _find_asset_refs(_source(name)):
            rel = ref.lstrip("/")
            if not Path(rel).suffix:
                continue  # a URL route, e.g. /chat or /presets
            if not any(c.exists() for c in (Path(rel), STATIC_DIR / rel)):
                missing.append(f"{name}: {ref}")
    assert not missing, "asset references with no file:\n" + "\n".join(missing)


class _DivBalance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.open = 0
        self.stray = 0

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            self.open += 1

    def handle_endtag(self, tag):
        if tag != "div":
            return
        if self.open:
            self.open -= 1
        else:
            self.stray += 1


def test_renderable_templates_have_balanced_divs():
    """A stray closing tag silently pushes the rest of the markup out of its
    container (e.g. a modal's Save button). Templates needing context cannot be
    checked this way and are skipped."""
    unbalanced = []
    checked = 0
    for name in ALL_TEMPLATES:
        try:
            rendered = env.get_template(name).render()
        except Exception:
            continue
        checked += 1
        parser = _DivBalance()
        parser.feed(rendered)
        parser.close()
        if parser.open or parser.stray:
            unbalanced.append(f"{name}: {parser.open} unclosed / {parser.stray} stray")
    assert checked, "no template could be rendered without context"
    assert not unbalanced, "unbalanced <div> tags:\n" + "\n".join(unbalanced)


STATE_CLASSES = {
    "hidden", "active", "collapsed", "expanded", "disabled", "disabled-row",
    "copied", "ready", "drag-over", "selected",
}
CLASS_LOOKUP_RE = re.compile(r"(?:querySelector(?:All)?|closest|matches)\(\s*['\"]\.([\w-]+)")


def test_no_class_based_dom_lookups():
    """Markup is looked up through `data-ui` hooks, never through classes.

    Classes stay presentational (and carry state like `hidden`/`active`); a
    rename or a Tailwind pass must never be able to break a querySelector."""
    offenders = []
    for name in ALL_TEMPLATES:
        for m in CLASS_LOOKUP_RE.finditer(_source(name)):
            if m.group(1) not in STATE_CLASSES:
                offenders.append(f"{name}: {m.group(0)}")
    assert not offenders, "class-based DOM lookups (use data-ui):\n" + "\n".join(offenders)


def test_programmatic_htmx_ajax_only_in_queue():
    """All programmatic partial reloads must go through hxGet/hxPost so they are
    serialized by the hx queue and never dropped by htmx's per-source queue."""
    allowed = {Path("static/js/core/hx-queue.js").resolve()}
    offenders = []
    for root in (STATIC_DIR, PARTIALS_DIR, TEMPLATES_DIR):
        for p in root.rglob("*"):
            if p.suffix not in (".js", ".html") or p.resolve() in allowed:
                continue
            if "htmx.ajax(" in p.read_text(errors="ignore"):
                offenders.append(str(p.relative_to(Path(".").resolve())))
    assert not offenders, f"direct htmx.ajax() found (use hxGet/hxPost): {offenders}"


def test_page_scripts_live_in_scripts_block():
    """Page-specific scripts must sit in the page scripts block, not the content
    block, so content stays markup-only and load order is explicit."""
    src = _source("chat.html")
    scripts_block = src.index("{% block scripts %}")
    early = [m.group(0) for m in re.finditer(r"<script\b[^>]*\bsrc=", src) if m.start() < scripts_block]
    assert not early, f"chat.html: <script src> before the page scripts block: {early}"


def test_css_valid():
    """Every split CSS file must parse."""
    css_dir = STATIC_DIR / "css"
    broken = []
    for f in sorted(list(css_dir.glob("*.css")) + list((css_dir / "surfaces").glob("*.css"))):
        cssutils.log.enabled = False
        try:
            cssutils.parseString(f.read_text())
        except Exception as exc:
            broken.append(f"{f.name}: {exc}")
        finally:
            cssutils.log.enabled = True
    assert not broken, "CSS files that failed to parse:\n" + "\n".join(broken)


COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
CUSTOM_PROPERTY_RE = re.compile(r"(--[\w-]+)\s*:")


def _custom_properties(css_text: str) -> set[str]:
    """Custom property names declared in a chunk of CSS (comments stripped)."""
    return set(CUSTOM_PROPERTY_RE.findall(COMMENT_RE.sub("", css_text)))


def test_theme_tokens_are_declared_once():
    """Tailwind-generating tokens are declared in @theme in css/tokens.css and
    nowhere else, so a rebrand moves one number, not two files."""
    tokens_text = (STATIC_DIR / "css" / "tokens.css").read_text()
    vars_text = (STATIC_DIR / "css" / "variables.css").read_text()

    cssutils.log.enabled = False
    try:
        sheet = cssutils.parseString(tokens_text)
    finally:
        cssutils.log.enabled = True
    theme_blocks = [r for r in sheet if getattr(r, "atkeyword", None) == "@theme"]
    assert theme_blocks, "css/tokens.css declares no @theme block"

    tokens = set()
    for block in theme_blocks:
        tokens |= _custom_properties(block.cssText)
    assert tokens, "@theme declares no tokens"

    redeclared = tokens & _custom_properties(vars_text)
    assert not redeclared, (
        "tokens redefined outside @theme (a second source of truth): "
        f"{sorted(redeclared)}"
    )


TEMPLATES_THAT_RENDER = [
    ("modals/sampler.html", {}),
    ("modals/itemizer.html", {}),
    ("modals/confirm.html", {}),
    ("modals/backup.html", {}),
    ("modals/provider-create.html", {}),
    ("modals/text-expander.html", {}),
    ("modals/theme.html", {}),
    ("modals/option-picker.html", {}),
    ("modals/export-entities.html", {"entities": []}),
    (
        "modals/regex-item.html",
        {
            "script": {
                "id": "s1",
                "scope": "global",
                "name": "Strip slop",
                "pattern": r"A beat\.",
                "replacement": "",
                "flags": "i",
                "placement": "ai",
                "apply_prompt": True,
                "apply_display": True,
                "as_block": False,
                "enabled": True,
                "min_depth": 0,
                "max_depth": -1,
            }
        },
    ),
    (
        "modals/regex-list.html",
        {"global_scripts": [], "preset_scripts": [], "preset_id": None, "preset_name": ""},
    ),
    (
        "modals/presets.html",
        {
            "presets": [{"id": "p1", "name": "General", "blocks": [{"block_type": "text"}]}],
            "current_preset_id": "p1",
        },
    ),
]

EDIT_ENTITY_CONTEXTS = {
    "char": {"prefix": "char", "modal_id": "modal-edit-character", "entity_name": "Character",
             "upload_fn": "up", "avatar_fn": "av", "submit_fn": "sub", "show_greetings": True},
    "persona": {"prefix": "persona", "modal_id": "modal-edit-persona", "entity_name": "Persona",
                "upload_fn": "up", "avatar_fn": "av", "submit_fn": "sub", "show_greetings": False},
}


def test_key_templates_render():
    """Templates with known context render without raising."""
    broken = []
    for name, context in TEMPLATES_THAT_RENDER:
        try:
            assert env.get_template(name).render(context)
        except Exception as exc:
            broken.append(f"{name}: {exc}")
    for prefix, context in EDIT_ENTITY_CONTEXTS.items():
        try:
            assert env.get_template("modals/edit-entity.html").render(context)
        except Exception as exc:
            broken.append(f"edit-entity[{prefix}]: {exc}")
    assert not broken, "templates that failed to render:\n" + "\n".join(broken)


def test_edit_entity_greeting_section_char_only():
    """The greeting editor renders only for the character modal, even when a
    `show_greetings` set-var leaks in from the including page."""
    tmpl = env.get_template("modals/edit-entity.html")
    base = {"modal_id": "modal-edit-entity", "entity_name": "Entity",
            "upload_fn": "up", "avatar_fn": "av", "submit_fn": "sub"}

    char_tree = parse_html(tmpl.render({**base, **EDIT_ENTITY_CONTEXTS["char"]}))
    section = char_tree.find(id="edit-char-greeting-section")
    assert section, "the character editor must render the greeting section"
    assert section.find("textarea", name="greeting"), section
    assert section.find(**{"name": "greetings_json"}), section
    assert section.find(**{"hx-post": "/partials/character-greeting/"}), section

    persona_tree = parse_html(tmpl.render({**base, **EDIT_ENTITY_CONTEXTS["persona"]}))
    assert persona_tree.find(**{"name": "greetings_json"}) is None
    assert not [el for el in persona_tree.walk() if (el.get("id") or "").endswith("-greeting-section")]


EDITABLE_FIELD_NAMES = {
    "name", "description", "group_name", "theme_id",
    "personality", "scenario", "mes_example",
}


def _form_field_ids(tree, form) -> set[str]:
    """Ids of the form's saved fields, read off the rendered inputs themselves."""
    return {
        el.get("id") for el in form.walk()
        if el.get("name") in EDITABLE_FIELD_NAMES and el.get("id")
    }


def test_edit_entity_dirty_fields_are_evaluated():
    """data-dirty-fields must render evaluated, not as raw Jinja, and must cover
    every field the form saves.

    Regression: those values are passed to the modal_shell macro as string
    literals, where Jinja does not evaluate embedded {{ }} / {% %} tags."""
    html = env.get_template("modals/edit-entity.html").render(
        {**EDIT_ENTITY_CONTEXTS["char"], "show_theme": True}
    )
    tree = parse_html(html)

    holder = next((el for el in tree.walk() if "data-dirty-fields" in el.attrs), None)
    assert holder, "the character editor declares no dirty fields"
    raw = holder.get("data-dirty-fields")
    assert "{{" not in raw and "{%" not in raw, f"unevaluated Jinja reached the DOM: {raw}"
    dirty = {f.strip().lstrip("#") for f in raw.split(",") if f.strip()}

    form = tree.find("form", id="edit-char-form")
    assert form, "the editor renders no form"
    editable = _form_field_ids(tree, form)
    assert {"edit-char-name", "edit-char-desc"} <= editable, editable
    assert editable <= dirty, f"fields that save but are not dirty-tracked: {sorted(editable - dirty)}"

    # Every tracked id must address a real element, or the guard never fires.
    rendered = {el.get("id") for el in tree.walk() if el.get("id")}
    assert dirty <= rendered, f"dirty selectors with no element: {sorted(dirty - rendered)}"


def test_greeting_section_renders_the_active_variant():
    """The greeting partial shows the active variant, its position, and disables
    the verbs that would step outside the list."""
    tmpl = env.get_template("modals/greeting-section.html")

    def render(greetings, idx, **extra):
        return parse_html(tmpl.render({"prefix": "char", "char_id": "c1", "greetings": greetings,
                                       "greeting_idx": idx, "entity_name": "Character", **extra}))

    def count(tree):
        return tree.find(id="edit-char-greeting-count").content.strip()

    def blocked(tree):
        return {
            verb for verb in ("prev", "next", "delete")
            if "disabled" in tree.find(id=f"edit-char-greeting-{verb}").attrs
        }

    middle = render(["Hi", "Hello", "Howdy"], 1)
    assert middle.find(id="edit-char-greeting-section"), "the section keeps its swap target"
    assert middle.find("textarea", name="greeting").content.strip() == "Hello"
    assert count(middle) == "2/3"
    assert middle.find(**{"name": "greeting_idx"}).get("value") == "1"
    assert blocked(middle) == set(), "a middle variant enables every verb"

    only = render(["Hi"], 0)
    assert count(only) == "1/1"
    assert blocked(only) == {"prev", "next"}

    empty = render([], 0)
    assert count(empty) == "0/0"
    assert blocked(empty) == {"prev", "next", "delete"}, "an empty list disables every verb"
