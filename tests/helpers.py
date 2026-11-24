import os
from html.parser import HTMLParser

VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class Element:
    """One parsed HTML element: attributes, child elements and its own text."""

    __slots__ = ("tag", "attrs", "parent", "children", "text")

    def __init__(self, tag, attrs, parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []
        self.text = []

    def __repr__(self):
        return f"<{self.tag} {self.attrs}>"

    @property
    def classes(self):
        return set(self.attrs.get("class", "").split())

    @property
    def content(self):
        """Text of this subtree, whitespace preserved."""
        return "".join(self.text) + "".join(c.content for c in self.children)

    def get(self, name, default=None):
        return self.attrs.get(name, default)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def find_all(self, tag=None, **attrs):
        """Descendants matching `tag` and every attribute.

        An attribute value matches as a set of whitespace-separated tokens, so
        `class` works as a subset test and multi-token hooks like
        `data-ui="message-content markdown-content"` are addressable.
        """
        return [
            el
            for el in self.walk()
            if (tag is None or el.tag == tag)
            and all(set(v.split()) <= set(el.attrs.get(k, "").split()) for k, v in attrs.items())
        ]

    def find(self, tag=None, **attrs):
        found = self.find_all(tag, **attrs)
        return found[0] if found else None


def parse_html(html: str) -> Element:
    """Parse rendered markup into an Element tree (the document is the root)."""

    class _Tree(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.root = Element("#document", {})
            self.stack = [self.root]

        def handle_starttag(self, tag, attrs):
            el = Element(tag, attrs, self.stack[-1])
            self.stack[-1].children.append(el)
            if tag not in VOID_TAGS:
                self.stack.append(el)

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            if tag not in VOID_TAGS:
                self.stack.pop()

        def handle_endtag(self, tag):
            for i in range(len(self.stack) - 1, 0, -1):
                if self.stack[i].tag == tag:
                    del self.stack[i:]
                    return

        def handle_data(self, data):
            self.stack[-1].text.append(data)

    parser = _Tree()
    parser.feed(html)
    parser.close()
    return parser.root


def element_classes(html: str, element_id: str) -> set[str]:
    """Class list of the element carrying `id=element_id`.

    Raises rather than returning an empty set, so a missing element cannot make
    a `not in classes` assertion pass.
    """
    el = next((e for e in parse_html(html).walk() if e.get("id") == element_id), None)
    assert el is not None, f"no element with id={element_id!r}"
    return el.classes


def require_assets_sandbox():
    """Require the test sandbox env var to be set.

    Tests that do destructive filesystem operations MUST call this
    before touching real paths. It prevents accidental destruction of
    real asset data when test files are run directly (outside pytest's
    conftest.py redirect) or when the sandbox hasn't been set up.
    """
    if os.environ.get("_FOCUS_ASSETS_SANDBOX") != "1":
        raise RuntimeError(
            "_FOCUS_ASSETS_SANDBOX is not set to '1'. "
            "Run tests through pytest so conftest.py can redirect "
            "assets to an isolated temp directory."
        )


async def create_character(client, name="Test Char", **overrides):
    body = {
        "name": name,
        "description": "Desc",
        "personality": "Neutral",
        "scenario": "Test",
        **overrides,
    }
    resp = await client.post("/api/characters/", json=body)
    assert resp.status_code == 201
    return resp.json()


async def create_persona(client, name="Test Persona", **overrides):
    body = {"name": name, "description": "A persona", **overrides}
    resp = await client.post("/api/personas/", json=body)
    assert resp.status_code == 201
    return resp.json()


async def create_preset(client, name="Test Preset"):
    resp = await client.post("/api/presets/", data={"name": name})
    assert resp.status_code == 201
    return resp.json()


async def create_chat(client, character_id=None, persona_id=None, preset_id=None):
    body = {}
    if character_id:
        body["character_id"] = character_id
    if persona_id:
        body["persona_id"] = persona_id
    if preset_id:
        body["preset_id"] = preset_id
    resp = await client.post("/api/chats/", json=body)
    assert resp.status_code == 201
    return resp.json()
