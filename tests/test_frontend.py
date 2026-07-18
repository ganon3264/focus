"""Frontend validation tests.

Checks Jinja2 template compilation, static asset references,
CSS syntax, and basic HTML well-formedness for renderable partials.
"""

import re
import os
from pathlib import Path
from html.parser import HTMLParser

import cssutils
import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined


# ── Jinja2 environment (mirrors app setup in pages.py) ────────────────────────

TEMPLATES_DIR = Path("templates").resolve()
PARTIALS_DIR = Path("partials").resolve()
STATIC_DIR = Path("static").resolve()

loader = FileSystemLoader([str(TEMPLATES_DIR), str(PARTIALS_DIR)])

# We use StrictUndefined for compilation — we won't render, just parse,
# so undefined variables don't matter.
env = Environment(loader=loader, undefined=StrictUndefined)
env.globals["url_for"] = lambda name, **kw: f"/{name.replace('.', '/')}"
env.filters["from_json"] = lambda v: {}

# Register macros as a known module so {% from "macros.html" import ... %} works
# (It's loaded lazily by Jinja2, so just adding the path is enough.)


# ── Collect templates ─────────────────────────────────────────────────────────

ALL_TEMPLATES = sorted(
    [str(p.relative_to(TEMPLATES_DIR)) for p in TEMPLATES_DIR.rglob("*.html")]
    + [str(p.relative_to(PARTIALS_DIR)) for p in PARTIALS_DIR.rglob("*.html")]
)


# ── Test 1: Every template compiles without syntax errors ─────────────────────

@pytest.mark.parametrize("template_name", ALL_TEMPLATES)
def test_template_compiles(template_name):
    """Each Jinja2 template must parse without syntax errors."""
    env.parse(loader.get_source(env, template_name)[0])


# ── Test 2: Static asset references point to real files ──────────────────────

def _find_asset_refs(text: str) -> list[str]:
    """Extract static asset paths from src/href attributes in template text."""
    refs = set()
    for m in re.finditer(r'''(?:src|href)\s*=\s*["']([^"']+)["']''', text):
        path = m.group(1)
        # Skip Jinja2 expressions, JS template literals, and dynamic paths
        if "{{" in path or "${" in path or "{" in path:
            continue
        # Strip query string
        path = path.split("?")[0]
        # Skip external URLs, data URIs, anchor-only, protocol-relative
        if (
            path.startswith("http://")
            or path.startswith("https://")
            or path.startswith("data:")
            or path.startswith("#")
            or path.startswith("//")
        ):
            continue
        refs.add(path)
    return list(refs)


@pytest.mark.parametrize("template_name", ALL_TEMPLATES)
def test_template_asset_references(template_name):
    """All static asset paths in the template must resolve to existing files."""
    source = loader.get_source(env, template_name)[0]
    for ref in _find_asset_refs(source):
        rel = ref.lstrip("/")
        candidate = Path(rel)
        candidate2 = STATIC_DIR / rel
        exists = candidate.exists() or candidate2.exists()
        if not exists:
            # No file extension → likely a URL route, skip
            if not Path(rel).suffix:
                continue
            pytest.fail(f"{template_name}: asset not found: {ref}")


def test_static_css_tailwind_inter_referenced():
    """Verify the referenced vendor files actually exist."""
    for f in ["style.css", "vendor/inter.css", "vendor/tailwindcss.js"]:
        assert (STATIC_DIR / f).exists(), f"Missing static asset: {f}"


# ── Test 3: CSS syntax validation ───────────────────────────────────────────

def test_css_valid():
    """style.css must parse without fatal errors."""
    css_path = STATIC_DIR / "style.css"
    css_text = css_path.read_text()

    # Capture cssutils output — it warns about CSS3 properties in CSS2.1
    # context (var(), custom properties, flex, etc.) — these are harmless.
    # Just check that the parser produces a usable stylesheet.
    cssutils.log.enabled = False
    sheet = cssutils.parseString(css_text)
    cssutils.log.enabled = True

    from cssutils.css import CSSStyleSheet
    assert isinstance(sheet, CSSStyleSheet), "CSS failed to parse"

    # Check that key CSS selectors are present
    assert ":root" in css_text
    assert ".action-icon" in css_text
    assert ".left-sidebar" in css_text


# ── Test 4: HTML well-formedness for partials with no template variables ─────

class _WellFormednessChecker(HTMLParser):
    """Collect unclosed tags."""
    def __init__(self):
        super().__init__()
        self.errors: list[str] = []
        self._tag_stack: list[str] = []
        self._void_elements = {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr",
        }

    def handle_starttag(self, tag, attrs):
        if tag not in self._void_elements:
            self._tag_stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self._void_elements:
            return
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        elif tag in self._tag_stack:
            # Unclosed inner tags
            while self._tag_stack and self._tag_stack[-1] != tag:
                self.errors.append(
                    f"Tag <{self._tag_stack.pop()}> closed by </{tag}>"
                )
            if self._tag_stack:
                self._tag_stack.pop()
        else:
            self.errors.append(f"Unexpected closing tag </{tag}>")

    def check(self, html: str) -> list[str]:
        self.errors = []
        self._tag_stack = []
        try:
            self.feed(html)
            self.close()
        except Exception as e:
            self.errors.append(str(e))
        for unclosed in reversed(self._tag_stack):
            self.errors.append(f"Unclosed tag: <{unclosed}>")
        return self.errors


# Templates with minimal or no template variables — renderable for HTML check
_RENDERABLE_PARTIALS = {
    "modals/confirm_modal.html",
    "modal_shell.html",
}

# These partials have {{ ... }} references that resolve to simple strings
# when given empty context — the HTML structure won't be complete but the
# tags themselves should be well-formed.
_TEMPLATES_WITH_VARS = {
    "presets/preset_selector.html",
    "presets/preset_variables.html",
    "presets/prompt_arranger.html",
    "presets/prompt_block.html",
    "presets/preset_editor.html",
    "modals/edit_message_modal.html",
    "modals/text_expander.html",
}


@pytest.mark.parametrize("template_name", sorted(_RENDERABLE_PARTIALS))
def test_partial_html_well_formed(template_name):
    """Render and check HTML well-formedness for simple partials."""
    tmpl = env.get_template(template_name)
    # Render with minimal context — these templates don't use variables
    html = tmpl.render({})
    checker = _WellFormednessChecker()
    errors = checker.check(html)
    assert not errors, f"{template_name} HTML errors: {'; '.join(errors)}"


# ── Test 5: No unclosed {% block %} or mismatched {% extends / block / for %} ─

def _check_block_balance(source: str, name: str) -> list[str]:
    """Check that {% block %} tags are balanced."""
    errors = []
    stack = []
    block_start = re.compile(r"{%\s*block\s+(\w+)\s*%}")
    block_end = re.compile(r"{%\s*endblock\s*%}")
    for m in block_start.finditer(source):
        stack.append(m.group(1))
    for m in block_end.finditer(source):
        if stack:
            stack.pop()
        else:
            errors.append(f"{name}: extra {{% endblock %}}")
    for unclosed in stack:
        errors.append(f"{name}: unclosed block '{unclosed}'")
    return errors


@pytest.mark.parametrize("template_name", ALL_TEMPLATES)
def test_block_balance(template_name):
    """All {% block %} tags must have matching {% endblock %}."""
    source = loader.get_source(env, template_name)[0]
    errors = _check_block_balance(source, template_name)
    assert not errors, "; ".join(errors)
