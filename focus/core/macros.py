import hashlib
import random as _random
import re
from datetime import UTC, datetime

from focus.core.utils import MACRO_MAX_PASSES


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


_STRIP_CBS_PATTERNS = (
    (re.compile(r"\{\{\s*comment\s*:(.*?)\}\}", re.IGNORECASE), ""),
    (re.compile(r"\{\{\s*hidden_key\s*:(.*?)\}\}", re.IGNORECASE), ""),
)


def _strip_cbs_macros(text: str) -> str:
    """Remove ``{{comment:...}}`` and ``{{hidden_key:...}}`` from text."""
    for pat, repl in _STRIP_CBS_PATTERNS:
        text = pat.sub(repl, text)
    return text


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
}

SPECIAL_TOKENS: list[dict[str, str]] = [
    {"syntax": "{{getvar::key}}", "description": "Inject a variable or setvar value by key"},
    {"syntax": "{{setvar::key::value}}", "description": "Define a custom macro inline (consumed)"},
    {"syntax": "{{var::key::value}}", "description": "Alias for {{setvar::}}"},
    {"syntax": "{{trim}}", "description": "Remove this line and collapse excess blank lines"},
    {"syntax": "{{// comment}}", "description": "Comment — stripped from output entirely"},
    {"syntax": "{{media::x}}", "description": "Insert attachment at position x (1-based, left to right)"},
    {"syntax": "{{random:A,B,C}}", "description": "Random pick from comma-separated values"},
    {"syntax": "{{pick:A,B,C}}", "description": "Sticky random pick (deterministic per chat)"},
    {"syntax": "{{roll:N}}", "description": "Random number between 1 and N"},
    {"syntax": "{{reverse:A}}", "description": "Reverse the string A"},
    {"syntax": "{{comment: A}}", "description": "Inline comment (visible in UI, stripped from prompt)"},
    {"syntax": "{{hidden_key:A}}", "description": "Hidden comment (stripped from prompt)"},
]


def extract_setvars(text: str, macros: dict[str, str]) -> str:
    """
    Extracts {{setvar::key::value}} or {{var::key::value}} from text,
    updates the macros dict, and removes the declaration from the text.
    """
    pattern = r"\{\{(?:setvar|var)::(.*?)::(.*?)\}\}"

    def repl(match):
        key, val = match.groups()
        macros[key.strip()] = val.strip()
        return ""

    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


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

    * ``{{getvar::key}}``          — look up a macro value
    * ``{{setvar::key::value}}``   — define a custom macro inline (consumed)
    * ``{{var::key::value}}``      — alias for ``{{setvar::}}``
    * ``{{trim}}``                 — consume line and collapse blank lines
    * ``{{// ...}}``               — comment, stripped entirely
    * ``{{comment: ...}}``         — inline comment, stripped from prompt
    * ``{{hidden_key: ...}}``      — hidden comment, stripped from prompt
    * ``{{random:A,B,C}}``         — random pick from comma-separated values
    * ``{{pick:A,B,C}}``           — deterministic pick (same result per chat)
    * ``{{roll:N}}`` / ``{{roll:dN}}`` — random number 1…*N*
    * ``{{reverse:A}}``            — reverse the string *A*

    Unknown ``{{…}}`` tokens are preserved as-is.
    Iterates until text stabilises (handles chains like ``A→B→C``).
    """
    if not text:
        return text

    text = _strip_comment_macros(text)
    text = _strip_cbs_macros(text)

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

    def _resolve_cbs(full_key: str) -> str | None:
        """Resolve a built-in CBS, or return *None* to fall through to macro lookup."""
        lower = full_key.lower()

        if lower == "trim":
            return ""
        if lower.startswith("getvar::"):
            k = full_key[8:].strip()
            return str(macros.get(k, ""))

        if lower.startswith("random:"):
            body = full_key[7:]
            return _resolve_random(_split_cbs_values(body))

        if lower.startswith("pick:"):
            body = full_key[5:]
            return _resolve_pick(_split_cbs_values(body), _cbs_seed(chat_id, body))

        if lower.startswith("roll:"):
            body = full_key[5:]
            return _resolve_roll(body, _cbs_seed(chat_id, body))

        if lower.startswith("reverse:"):
            body = full_key[8:]
            return body[::-1]

        return None

    def get_repl_func(match):
        full_key = match.group(1).strip()
        resolved = _resolve_cbs(full_key)
        if resolved is not None:
            return resolved
        return str(macros.get(full_key, match.group(0)))

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
