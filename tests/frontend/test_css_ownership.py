"""CSS ownership guard.

`static/css/primitives.css` is the only file allowed to author the look of a
control (see the contract at the top of that file). A surface may set layout on
its own container; it may not restyle a primitive — that is how the same
component ends up authored twice, which is what this branch removed.

1. Outside `primitives.css`, a selector whose *subject* (the rightmost compound)
   carries a primitive class may not declare a look property (background / color
   / box-shadow / border* / font* / text-transform / letter-spacing).
2. `:not(` is banned in every stylesheet — the ladder it invites is how
   primitives grow per-surface exceptions instead of getting a modifier.
"""

import re
from pathlib import Path

import pytest

CSS_DIR = Path(__file__).resolve().parents[2] / "static" / "css"
PRIMITIVES = CSS_DIR / "primitives.css"

# Shapes from the primitives.css contract. Modifiers (.sm, .primary, .danger)
# and states (.active, .hidden) are deliberately absent: a surface's own class
# may carry an intent of its own without being a primitive.
SHAPES = {
    "btn", "key", "nav", "link", "chip", "tab", "pager",
    "field", "check", "switch",
    "rail", "row", "well", "frame", "panel", "card", "divider", "disclosure",
    "grip", "caret-mark",
    "toast", "tooltip", "spinner", "empty", "note", "tag", "avatar",
}

LOOK_PROPERTY = re.compile(r"^(background|color|box-shadow|border|font|text-transform|letter-spacing)")

GROUP_AT_RULES = re.compile(r"^@(media|supports|layer|container)\b")


def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _rules(css):
    """Yield (prelude, body) for every style rule, descending into group at-rules."""
    prelude = ""
    i = 0
    while i < len(css):
        char = css[i]
        if char == "{":
            depth, j = 1, i + 1
            while j < len(css) and depth:
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            body = css[i + 1 : j - 1]
            selector = prelude.strip()
            if GROUP_AT_RULES.match(selector):
                yield from _rules(body)
            elif not selector.startswith("@"):
                yield selector, body
            prelude = ""
            i = j
        elif char == "}":
            prelude = ""
            i += 1
        else:
            prelude += char
            i += 1


def _subject(selector):
    """The rightmost compound of each selector in a comma list."""
    out = []
    for part in selector.split(","):
        compound = re.split(r"[\s>+~]+", part.strip())[-1]
        # Drop a pseudo-element / pseudo-class tail: `.field:hover` styles .field.
        compound = re.sub(r"::?[a-zA-Z-]+(\([^)]*\))?$", "", compound)
        out.append(compound)
    return out


def _classes(compound):
    return set(re.findall(r"\.(-?[A-Za-z0-9_-]+)", compound))


def _violations(css, name):
    found = []
    text = _strip_comments(css)
    for selector, body in _rules(text):
        look = [p for p in re.findall(r"([-a-zA-Z]+)\s*:", body) if LOOK_PROPERTY.match(p)]
        if not look:
            continue
        for compound in _subject(selector):
            hit = SHAPES & _classes(compound)
            if hit:
                found.append(f"{name}: `{selector.strip()}` sets {', '.join(look)} on .{hit.pop()}")
                break
    return found


def _not_ladders(css, name):
    text = _strip_comments(css)
    return [
        f"{name}:{text.count(chr(10), 0, m.start()) + 1}: `:not(` is not allowed"
        for m in re.finditer(r":not\(", text)
    ]


def _surface_files():
    return [p for p in sorted(CSS_DIR.rglob("*.css")) if p != PRIMITIVES]


def test_parser_catches_what_it_claims_to():
    """The guard is only worth its green: prove both rules fail on a violation."""
    bad = ".foo .row { font-size: 11px; }\n.field:hover { color: red; }\n.bar:not(.x) { padding: 0; }\n"
    assert len(_violations(bad, "fake.css")) == 2
    assert len(_not_ladders(bad, "fake.css")) == 1
    # Layout on its own container stays legal, as does a surface's own class.
    assert _violations(".foo .row { min-height: 4px; }\n.mine.danger { color: red; }\n", "ok.css") == []
    assert _not_ladders("/* no :not() in a comment */\n.a > .b { color: red; }\n", "ok.css") == []


def test_guard_scans_the_real_surfaces():
    """A parser regression (silently yielding nothing) must not look like a pass."""
    total = sum(len(list(_rules(_strip_comments(p.read_text())))) for p in _surface_files())
    assert total > 100, f"only {total} style rules parsed from static/css — parser is broken"


@pytest.mark.parametrize("path", _surface_files(), ids=lambda p: p.name)
def test_no_surface_restyles_a_primitive(path):
    found = _violations(path.read_text(), path.name)
    assert not found, "surfaces may not own a primitive's look:\n" + "\n".join(found)


def test_no_not_ladders_anywhere():
    """A `:not()` ladder is how a primitive grows per-surface exceptions."""
    found = []
    for path in sorted(CSS_DIR.rglob("*.css")):
        found += _not_ladders(path.read_text(), path.name)
    assert not found, "\n".join(found)
