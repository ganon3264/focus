import hashlib
import html
import logging
import random as _random
import re
from collections.abc import Callable
from datetime import UTC, datetime

from focus.core.utils import MACRO_MAX_PASSES

logger = logging.getLogger("focus.macros")


def _resolve_random(values: list[str]) -> str:
    """Pick a random value from *values*."""
    return _random.choice(values) if values else ""


def _resolve_pick(values: list[str], seed: int | None = None) -> str:
    """Deterministic pick from *values* using an optional seed.

    When *seed* is provided the same input always returns the same choice;
    when *seed* is ``None`` a random choice is made (equivalent to
    ``_resolve_random``).
    """
    if not values:
        return ""
    if seed is not None:
        rng = _random.Random(seed)
        return rng.choice(values)
    return _random.choice(values)


def _resolve_roll(expr: str, seed: int | None = None) -> str:
    """Evaluate ``{{roll:N}}`` or ``{{roll:dN}}``."""
    n_str = expr.lstrip("dD").strip()
    try:
        n = int(n_str)
    except (ValueError, TypeError):
        return ""
    if n < 1:
        return ""
    if seed is not None:
        rng = _random.Random(seed)
        return str(rng.randint(1, n))
    return str(_random.randint(1, n))


def _split_cbs_values(text: str) -> list[str]:
    """Split comma-separated values respecting ``\\,`` escapes."""
    parts: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] == ",":
            current.append(",")
            i += 2
        elif text[i] == ",":
            parts.append("".join(current))
            current = []
            i += 1
        else:
            current.append(text[i])
            i += 1
    parts.append("".join(current))
    return parts


def _cbs_seed(chat_id: str | None, body: str) -> int | None:
    """Return a deterministic seed from *chat_id* + *body*, or ``None``."""
    if chat_id is None:
        return None
    key = f"{chat_id}:{body}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16)


_CBS_HANDLERS: list[tuple[str, Callable[[str, dict, str | None], str | None]]] = [
    ("getvar::",  lambda k, m, c: str(m.get(k[8:].strip(), ""))),
    ("random:",   lambda k, m, c: _resolve_random(_split_cbs_values(k[7:]))),
    ("pick:",     lambda k, m, c: _resolve_pick(_split_cbs_values(k[5:]), _cbs_seed(c, k[5:]))),
    ("roll:",     lambda k, m, c: _resolve_roll(k[5:], _cbs_seed(c, k[5:]))),
    ("reverse:",  lambda k, m, c: k[8:][::-1]),
    ("media:",    lambda k, m, c: "{{" + k + "}}"),
]

_CBS_EXACT: dict[str, Callable[[], str]] = {
    "trim": lambda: "",
}


def _resolve_cbs(full_key: str, macros: dict, chat_id: str | None) -> str | None:
    """Resolve a built-in CBS, or return *None* to fall through to macro lookup."""
    lower = full_key.lower()
    if lower in _CBS_EXACT:
        return _CBS_EXACT[lower]()
    for prefix, handler in _CBS_HANDLERS:
        if lower.startswith(prefix):
            return handler(full_key, macros, chat_id)
    return None


def build_base_macros(card: dict, persona: dict | None = None) -> dict[str, str]:
    now = datetime.now(UTC)

    hour = now.hour
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    macros = {
        "char": card.get("nickname") or card.get("name", "Assistant"),
        "user": persona["name"] if persona else "User",
        "persona": persona["description"] if persona else "",
        "persona_id": persona["id"] if persona else "",
        "description": card.get("description", ""),
        "personality": card.get("personality", ""),
        "scenario": card.get("scenario", ""),
        "mes_example": card.get("mes_example", ""),
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A"),
        "time_of_day": time_of_day,
        "summary": "",
        "summary_pins": "",
        "summary_messages": "",
        "summary_media": "",
    }
    return macros


MACRO_DEFINITIONS: dict[str, dict[str, str]] = {
    "char": {"description": "Character name (or nickname if set)", "source": "character card"},
    "user": {"description": "User/persona name", "source": "persona"},
    "persona": {"description": "Persona description text", "source": "persona"},
    "persona_id": {"description": "Persona unique ID", "source": "persona"},
    "description": {"description": "Character description", "source": "character card"},
    "personality": {"description": "Character personality", "source": "character card"},
    "scenario": {"description": "Scenario text", "source": "character card"},
    "mes_example": {"description": "Example messages", "source": "character card"},
    "time": {"description": "Current time (HH:MM)", "source": "system"},
    "date": {"description": "Current date (YYYY-MM-DD)", "source": "system"},
    "weekday": {"description": "Day of week", "source": "system"},
    "time_of_day": {"description": "Time period (morning/afternoon/evening/night)", "source": "system"},
    "summary": {"description": "Accumulated summary text (forked chats only)", "source": "summary"},
    "summary_pins": {"description": "User-pinned messages carried verbatim into a fork", "source": "summary"},
    "summary_messages": {"description": "Recent parent turns carried into a fork", "source": "summary"},
    "summary_media": {"description": "Older media-bearing turns carried into a fork", "source": "summary"},
}

SPECIAL_TOKENS: list[dict[str, str]] = [
    {"syntax": "{{getvar::key}}", "description": "Inject a variable or setvar value by key"},
    {"syntax": "{{setvar::key::value}}", "description": "Define a custom macro inline (consumed)"},
    {"syntax": "{{var::key::value}}", "description": "Alias for {{setvar::}}"},
    {"syntax": "{{setvar key}}...{{/setvar}}", "description": "Scoped multiline value (trimmed/dedented; prefix # to preserve whitespace)"},
    {"syntax": "{{trim}}", "description": "Remove this line and collapse excess blank lines"},
    {"syntax": "{{// comment}}", "description": "Comment — stripped from output entirely"},
    {"syntax": "{{media:x}}", "description": "Insert attachment at position x (1-based, left to right)"},
    {"syntax": "{{random:A,B,C}}", "description": "Random pick from comma-separated values"},
    {"syntax": "{{pick:A,B,C}}", "description": "Sticky random pick (deterministic per chat)"},
    {"syntax": "{{roll:N}}", "description": "Random number between 1 and N"},
    {"syntax": "{{reverse:A}}", "description": "Reverse the string A"},
]


def _scoped_value(body: str) -> str:
    """Trim a scoped macro body and remove the first line's indentation from
    every line (mirrors SillyTavern's default scoped content trimming)."""
    body = body.strip("\n")
    lines = body.split("\n")
    if lines and lines[0]:
        indent = re.match(r"[ \t]*", lines[0]).group(0)
        if indent:
            lines = [
                line[len(indent):] if line.startswith(indent) else line
                for line in lines
            ]
    return "\n".join(lines).strip()


# SillyTavern spells the scoped form `{{setvar::key}}...{{/setvar}}`; the space
# form is ours. The key refuses `:` so a colon separator can never swallow an
# inline `{{setvar::key::value}}` that happens to share the text.
_SCOPED_SETVAR = re.compile(
    r"\{\{\s*(?P<flag>#)?\s*(?:setvar|var)(?:\s+|::)(?P<key>[^{}:]+?)\s*\}\}"
    r"(?P<body>.*?)"
    r"\{\{\s*/\s*(?:setvar|var)\s*\}\}",
    re.DOTALL | re.IGNORECASE,
)


_INLINE_SETVAR_OPEN = re.compile(r"\{\{\s*(?:setvar|var)::", re.IGNORECASE)


def _extract_inline_setvars(text: str, macros: dict[str, str]) -> str:
    """Extract ``{{setvar::key::value}}`` while respecting nested macros.

    Scans for the closing ``}}`` by brace depth so a value containing macros
    such as ``{{user}}`` is not truncated at their closing braces.
    """
    result: list[str] = []
    i = 0
    while True:
        m = _INLINE_SETVAR_OPEN.search(text, i)
        if not m:
            result.append(text[i:])
            break
        j = m.end()
        depth = 1
        end = None
        while j < len(text):
            if text[j : j + 2] == "{{":
                depth += 1
                j += 2
            elif text[j : j + 2] == "}}":
                depth -= 1
                j += 2
                if depth == 0:
                    end = j
                    break
            else:
                j += 1
        if end is None:
            result.append(text[i:])
            break
        inner = text[m.end() : end - 2]
        if "::" in inner:
            key, val = inner.split("::", 1)
            macros[key.strip()] = val.strip()
            result.append(text[i : m.start()])
        else:
            result.append(text[i:end])
        i = end
    return "".join(result)


def extract_setvars(text: str, macros: dict[str, str]) -> str:
    """
    Extracts ``{{setvar::key::value}}`` / ``{{var::key::value}}`` and the
    scoped ``{{setvar key}}...{{/setvar}}`` form, updates the macros dict, and
    removes the declaration from the text.
    """

    def scoped_repl(match):
        key = match.group("key").strip()
        if key:
            body = match.group("body")
            macros[key] = body if match.group("flag") else _scoped_value(body)
        return ""

    text = _SCOPED_SETVAR.sub(scoped_repl, text)
    return _extract_inline_setvars(text, macros)


# `{{#if}}` is ST's whitespace-preserving flag (and coincidentally what
# Handlebars authors write); it parses as the same block.
_IF_OPEN = re.compile(r"\{\{\s*(?P<flag>#)?\s*if\s+", re.IGNORECASE)
_IF_CLOSE = re.compile(r"\{\{\s*/\s*if\s*\}\}", re.IGNORECASE)
_IF_ELSE = re.compile(r"\{\{\s*else\s*\}\}", re.IGNORECASE)
# ST's falsy list, verbatim: a flag stored as "0"/"off"/"no" must not
# read as true the way a non-empty string would.
_FALSY = {"", "false", "0", "off", "no"}


def _token_end(text: str, start: int) -> int | None:
    """Index just past the ``}}`` closing the token opened at *start*.

    A condition carries macros (``{{if {{getvar::x}}}}``), so the braces nest;
    a non-greedy ``{{(.*?)}}`` would stop at the inner token and leave ``}}``
    behind in the prompt.
    """
    depth = 1
    j = start + 2
    while j < len(text):
        if text.startswith("{{", j):
            depth += 1
            j += 2
        elif text.startswith("}}", j):
            depth -= 1
            j += 2
            if depth == 0:
                return j
        else:
            j += 1
    return None


def _scan_if_block(text: str, start: int) -> tuple | None:
    """Span of the ``{{/if}}`` matching an opener whose token ends at *start*.

    Returns ``(else_span, close_start, close_end)`` where *else_span* is the
    top-level ``{{else}}`` (or ``None``), or ``None`` without a closing tag.
    """
    depth = 0
    else_span = None
    i = start
    while True:
        found = [m for m in (_IF_OPEN.search(text, i), _IF_CLOSE.search(text, i), _IF_ELSE.search(text, i)) if m]
        if not found:
            return None
        m = min(found, key=lambda x: x.start())
        if m.re is _IF_OPEN:
            depth += 1
        elif m.re is _IF_CLOSE:
            if depth:
                depth -= 1
            else:
                return else_span, m.start(), m.end()
        elif depth == 0 and else_span is None:
            else_span = (m.start(), m.end())
        i = m.end()


def _eval_condition(cond: str, macros: dict, chat_id: str | None) -> bool:
    """Truthiness of an ``{{if}}`` condition.

    Accepts a nested macro (``{{if {{getvar::x}}}}``) or a bare zero-arg macro
    name (``{{if description}}`` — ST resolves those automatically), preceded by
    an optional ``!``. Anything else is literal text. The falsy set is ST's
    five strings, not Python truthiness: a flag stored as ``"0"``/"off"/"no"
    must not read as true.
    """
    cond = cond.strip()
    negate = cond.startswith("!")
    if negate:
        cond = cond[1:].strip()
    token = re.fullmatch(r"\{\{\s*(.*?)\s*\}\}", cond, re.DOTALL)
    key = token.group(1).strip() if token else cond
    resolved = _resolve_cbs(key, macros, chat_id)
    if resolved is not None:
        value = resolved
    elif key in macros:
        value = str(macros[key])
    else:
        value = "" if token else cond
    truthy = value.strip().lower() not in _FALSY
    return not truthy if negate else truthy


def _walk(
    text: str,
    macros: dict,
    chat_id: str | None,
    warned: set[str],
    substitute: bool = True,
) -> str:
    """One document-order pass over a prompt.

    Setvars apply where they appear, an ``{{if}}`` is decided with the values in
    force at that point, and **only the winning branch is walked** — a dropped
    branch must not contribute its ``setvar``/``random`` side effects. With
    *substitute* off, plain ``{{…}}`` tokens are left verbatim (conditions only).
    """
    out: list[str] = []
    i = 0
    while i < len(text):
        j = text.find("{{", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])

        m_if = _IF_OPEN.match(text, j)
        if m_if:
            token_end = _token_end(text, j)
            if token_end is None:
                out.append(text[j:])
                break
            found = _scan_if_block(text, token_end)
            if found is None:
                if "unclosed" not in warned:
                    warned.add("unclosed")
                    logger.warning("Unclosed '{{if}}' stripped from prompt")
                i = token_end
                continue
            else_span, close_start, close_end = found
            body_end = else_span[0] if else_span else close_start
            alt_start = else_span[1] if else_span else close_start
            cond = text[m_if.end() : token_end - 2]
            if _eval_condition(cond, macros, chat_id):
                branch = text[token_end:body_end]
            else:
                branch = text[alt_start:close_start]
            if not m_if.group("flag"):
                branch = _scoped_value(branch)
            out.append(_walk(branch, macros, chat_id, warned, substitute))
            i = close_end
            continue

        m_scoped = _SCOPED_SETVAR.match(text, j)
        if m_scoped:
            key = m_scoped.group("key").strip()
            if key:
                body = m_scoped.group("body")
                macros[key] = body if m_scoped.group("flag") else _scoped_value(body)
            i = m_scoped.end()
            continue

        m_inline = _INLINE_SETVAR_OPEN.match(text, j)
        if m_inline:
            token_end = _token_end(text, j)
            if token_end is None:
                out.append(text[j:])
                break
            inner = text[m_inline.end() : token_end - 2]
            if "::" in inner:
                key, value = inner.split("::", 1)
                macros[key.strip()] = value.strip()
                i = token_end
                continue
            i = token_end
            out.append(_walk_unknown(text[j:token_end], warned, substitute))
            continue

        token_end = _token_end(text, j)
        if token_end is None:
            out.append(text[j:])
            break
        if substitute:
            out.append(_resolve_token(text[j:token_end], macros, chat_id, warned))
        else:
            out.append(text[j:token_end])
        i = token_end
    return "".join(out)


def _walk_unknown(token: str, warned: set[str], substitute: bool) -> str:
    """A `{{setvar::key}}` opener with no value: not an assignment, not a
    scoped block — leave it to the unknown-macro path."""
    return "" if substitute else token


def _resolve_token(token: str, macros: dict, chat_id: str | None, warned: set[str]) -> str:
    key = token[2:-2].strip()
    resolved = _resolve_cbs(key, macros, chat_id)
    if resolved is not None:
        return resolved
    if key in macros:
        return str(macros[key])
    # An imported ST preset repeats the same foreign macro dozens of times; one
    # line per key is the whole story.
    if key not in warned:
        warned.add(key)
        logger.warning("Unknown macro '{{%s}}' stripped from prompt", key)
    return ""


_COMMENT_START = re.compile(r"\{\{\s*//")


def _strip_comment_macros(text: str) -> str:
    result = []
    i = 0
    while i < len(text):
        m = _COMMENT_START.search(text, i)
        if not m:
            result.append(text[i:])
            break
        result.append(text[i : m.start()])
        j = m.end()
        depth = 1
        while j < len(text) and depth > 0:
            if text[j : j + 2] == "{{":
                depth += 1
                j += 2
            elif text[j : j + 2] == "}}":
                depth -= 1
                j += 2
            else:
                j += 1
        i = j
    return "".join(result)


def apply_macros(text: str, macros: dict[str, str], max_passes: int = MACRO_MAX_PASSES) -> str:
    """
    Applies ``{{key}}`` and built-in curley-brace syntaxes using the macros dict.
    Supported CBS (see ``SPECIAL_TOKENS`` for the full list):
    Unknown ``{{…}}`` tokens are stripped from output with a warning.
    Iterates until text stabilises (handles chains like ``A→B→C``).
    """
    if not text:
        return text

    text = _strip_comment_macros(text)

    chat_id = macros.get("_chat_id") if isinstance(macros.get("_chat_id"), str) else None

    # Detect {{trim}} — consumed as a special token, not a macro lookup
    needs_trim = bool(re.search(r"\{\{trim\}\}", text, re.IGNORECASE))
    # Strip {{trim}} along with surrounding whitespace/newlines so it
    # doesn't leave a dangling blank line when on its own line.
    text = re.sub(
        r"[ \t]*\n?[ \t]*\{\{trim\}\}[ \t]*\n?[ \t]*",
        lambda m: "\n" if "\n" in m.group(0) else "",
        text,
        flags=re.IGNORECASE,
    )

    warned: set[str] = set()

    prev = None
    for _ in range(max_passes):
        text = _walk(text, macros, chat_id, warned)
        if text == prev:
            break
        prev = text

    if needs_trim:
        # Collapse runs of 3+ blank lines into 1 blank line (preserves paragraphs),
        # then strip leading/trailing whitespace.
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

    return text


_TEMPLATE_MUSTACHE = re.compile(r"\{\{\{(.*?)\}\}\}|\{\{(.*?)\}\}", re.DOTALL)


def resolve_template_macros(text: str, macros: dict[str, str]) -> str:
    """Resolve recognised macros in a text that also carries Handlebars.

    Unlike :func:`apply_macros`, tokens that are not macros (Handlebars paths,
    block helpers, partials, …) are left verbatim so the template still
    compiles. Triple braces insert the value raw, double braces HTML-escape it,
    mirroring Handlebars escaping.
    """
    if not text:
        return text

    text = _strip_comment_macros(text)
    chat_id = macros.get("_chat_id") if isinstance(macros.get("_chat_id"), str) else None

    def repl(match: re.Match) -> str:
        triple = match.group(1) is not None
        key = (match.group(1) if triple else match.group(2)).strip()
        resolved = _resolve_cbs(key, macros, chat_id)
        if resolved is None:
            if key not in macros:
                return match.group(0)
            resolved = str(macros[key])
        return resolved if triple else html.escape(resolved, quote=True)

    prev = None
    for _ in range(MACRO_MAX_PASSES):
        text = extract_setvars(text, macros)
        text = _TEMPLATE_MUSTACHE.sub(repl, text)
        if text == prev:
            break
        prev = text
    return text
