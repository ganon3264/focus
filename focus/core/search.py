"""Message search: the query the search box speaks and the snippet a hit shows.

Matching is FTS5 (`message_fts`, porter + unicode61): tokens, stemming,
AND by default, bm25 ranking. The index holds the stored Markdown verbatim —
it is synced by triggers on `message_variants`, so nothing else has to know it
exists — which is why a snippet arrives as markup with match markers and has to
be turned back into one line of text.
"""

import html
import re

MAX_RESULTS = 40

# Not `<mark>`/`</mark>` directly: the raw snippet still carries tags, and the
# markers have to survive the strip that removes them.
MARK_OPEN = "\x02"
MARK_CLOSE = "\x03"

SNIPPET_TOKENS = 20
SNIPPET_CHARS = 240

_TAG_RE = re.compile(r"<[^>]*>")
_SEPARATORS = re.compile(r"[^0-9A-Za-z_'’]+")
_WORD_CHAR_RE = re.compile(r"[0-9A-Za-z]+")


def match_query(term: str) -> str:
    """The FTS5 MATCH expression for a user's box.

    Every token is a quoted prefix, ANDed: `rain rust` wants both words, a
    half-typed `rusty` still hits `rust`, and FTS5 operators in the input are
    neutered by the quoting rather than reaching the parser.
    """
    # Only tokens the tokenizer will find something in: a lone `_` or `'` is a
    # phrase of no terms, which matches nothing and is not worth a query.
    tokens = [t for t in _SEPARATORS.split(term or "") if t and _WORD_CHAR_RE.search(t)]
    return " ".join(f'"{t}"*' for t in tokens)


def render_snippet(raw: str) -> str:
    """One escaped line of text with `<mark>` around each match.

    Tags are stripped (a hit should read as the line you remember, not as its
    markup), the line is flattened and capped, and only then are the match
    markers turned into HTML — so the text itself is escaped and the marks are
    the only markup the browser sees.
    """
    text = " ".join(_TAG_RE.sub("", raw or "").split())
    if len(text) > SNIPPET_CHARS:
        text = text[:SNIPPET_CHARS].rstrip()
        if text.count(MARK_OPEN) > text.count(MARK_CLOSE):
            text += MARK_CLOSE
        text += "…"
    text = html.escape(text, quote=False)
    return text.replace(MARK_OPEN, "<mark>").replace(MARK_CLOSE, "</mark>")
