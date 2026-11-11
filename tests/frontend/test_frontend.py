"""Template / asset / CSS lints.

These are checks over the whole tree, not one behaviour each: every lint walks
its collection and reports every offender in one failure. Parametrizing them
per template inflated the suite to 268 near-identical cases without adding
information.
"""

import re
from pathlib import Path

import cssutils
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from focus.providers.schema import provider_schema, provider_type_options

TEMPLATES_DIR = Path("templates").resolve()
PARTIALS_DIR = Path("partials").resolve()
STATIC_DIR = Path("static").resolve()

loader = FileSystemLoader([str(TEMPLATES_DIR), str(PARTIALS_DIR)])
env = Environment(loader=loader, undefined=StrictUndefined)

# Mirror the globals registered by focus/routers/pages.py so templates that
# call them can render in tests.
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
        if rendered.count("<div") != rendered.count("</div>"):
            unbalanced.append(f"{name}: {rendered.count('<div')} open / {rendered.count('</div>')} close")
    assert checked, "no template could be rendered without context"
    assert not unbalanced, "unbalanced <div> tags:\n" + "\n".join(unbalanced)


def test_partials_have_one_inline_script():
    """One <script> per partial. A second one is a copy-paste artefact: the
    browser parses the first block up to the stray tag, the rest never runs, and
    the page keeps rendering while its wiring is gone."""
    offenders = [
        name for name in ALL_TEMPLATES
        if name.startswith("partials/") and _source(name).count("<script") > 1
    ]
    assert not offenders, f"partials with more than one script block: {offenders}"


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


CRITICAL_ASSETS = [
    "tailwind.css",
    "fonts.css",
    "fonts/ronzino-regular.woff2",
    "fonts/necto-mono-regular.woff2",
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


def test_base_loads_shared_scripts_after_content():
    """base.html must render page content before the shared app script block.

    Modules like generation-ui/input-bar/chat-controls bind to the page DOM at
    load, so the shared block must run after the content block."""
    src = _source("base.html")
    content = src.index("{% block content %}")
    first_shared = src.index("/static/js/ui/media-utils.js")
    last_shared = src.index("/static/js/ui/chat-controls.js")
    scripts_block = src.index("{% block scripts %}")
    assert content < first_shared, "shared scripts must load after the content block"
    assert last_shared < scripts_block, "page scripts block must come after shared scripts"


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


def test_tailwind_bundle_contains_custom_css():
    """The css/ modules are imported by tailwind-input.css; a dropped import must
    fail here instead of silently losing styles at runtime."""
    css_text = (STATIC_DIR / "tailwind.css").read_text()
    missing = [m for m in (".arranger-item", ".chat-center", ".modal-panel") if m not in css_text]
    assert not missing, f"tailwind.css is missing bundled rules: {missing}"


def test_theme_tokens_are_declared_once():
    """Rebranded Tailwind tokens live in @theme in css/tokens.css (single source
    of truth), not as bare :root overrides in variables.css."""
    tokens_text = (STATIC_DIR / "css" / "tokens.css").read_text()
    vars_text = (STATIC_DIR / "css" / "variables.css").read_text()
    missing = [t for t in ("--radius-sm", "--radius-md", "--shadow-sm", "--font-sans") if t not in tokens_text]
    assert not missing, f"missing @theme tokens: {missing}"
    duplicated = [t for t in ("--radius-sm", "--shadow-sm", "--font-sans") if t in vars_text]
    assert not duplicated, f"tokens redefined in variables.css: {duplicated}"


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

    char_html = tmpl.render({**base, **EDIT_ENTITY_CONTEXTS["char"]})
    assert 'name="greetings_json"' in char_html
    assert 'hx-post="/partials/character-greeting/' in char_html

    persona_html = tmpl.render({**base, **EDIT_ENTITY_CONTEXTS["persona"]})
    assert "greeting" not in persona_html.lower()


def test_edit_entity_dirty_fields_are_evaluated():
    """data-dirty-fields must render evaluated, not as raw Jinja.

    Regression: those values are passed to the modal_shell macro as string
    literals, where Jinja does not evaluate embedded {{ }} / {% %} tags."""
    tmpl = env.get_template("modals/edit-entity.html")
    html = tmpl.render({**EDIT_ENTITY_CONTEXTS["char"], "show_theme": True})

    attrs = re.search(r'data-dirty-fields="([^"]*)"', html)
    assert attrs, "the character editor declares no dirty fields"
    fields = [f.lstrip("#") for f in attrs.group(1).split(",")]

    for required in ("name", "desc", "group", "theme-id", "personality", "scenario", "mes-example"):
        assert f"edit-char-{required}" in fields, f"{required} is not dirty-tracked"
    assert "{%" not in attrs.group(1) and "{{" not in attrs.group(1)


def test_greeting_section_renders_the_active_variant():
    """The greeting partial shows the active variant, its position, and disables
    the verbs that would step outside the list."""
    tmpl = env.get_template("modals/greeting-section.html")

    def render(greetings, idx, **extra):
        return tmpl.render({"prefix": "char", "char_id": "c1", "greetings": greetings,
                            "greeting_idx": idx, "entity_name": "Character", **extra})

    middle = render(["Hi", "Hello", "Howdy"], 1)
    assert "Hello" in middle
    assert "2/3" in middle
    assert 'name="greeting_idx" value="1"' in middle
    assert not re.findall(r"(?m)^\s*disabled\s*$", middle), "a middle variant enables every verb"

    only = render(["Hi"], 0)
    assert "1/1" in only

    empty = render([], 0)
    assert "0/0" in empty
    assert len(re.findall(r"(?m)^\s*disabled\s*$", empty)) == 3, "an empty list disables every verb"


def test_character_card_does_not_embed_greetings():
    """The card no longer carries the greetings list — the editor fetches it."""
    rendered = env.get_template("modals/character-card.html").render(
        char={
            "id": "c1", "name": "Test", "image_path": None, "created_at": "2026-01-01",
            "theme_id": None, "card": {"first_mes": "Hi", "alternate_greetings": ["A", "B"]},
            "images": [],
        },
        current_character_id="",
    )
    assert "data-char-greetings" not in rendered
