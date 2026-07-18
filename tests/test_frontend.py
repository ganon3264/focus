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
