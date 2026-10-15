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


_SCOPED_SETVAR = re.compile(
    r"\{\{\s*(?P<flag>#)?\s*(?:setvar|var)\s+(?P<key>[^{}]+?)\s*\}\}"
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

    pattern_get = r"\{\{(.*?)\}\}"

    def get_repl_func(match):
        full_key = match.group(1).strip()
        resolved = _resolve_cbs(full_key, macros, chat_id)
        if resolved is not None:
            return resolved
        if full_key in macros:
            return str(macros[full_key])
        logger.warning("Unknown macro '{{%s}}' stripped from prompt", full_key)
        return ""

    prev = None
    for _ in range(max_passes):
        text = extract_setvars(text, macros)
        text = re.sub(pattern_get, get_repl_func, text)
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
