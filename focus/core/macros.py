import re
from datetime import UTC, datetime

from focus.core.utils import MACRO_MAX_PASSES


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
        "char": card.get("name", "Assistant"),
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
    "char": {"description": "Character name", "source": "character card"},
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
    Applies {{key}} or {{getvar::key}} using the macros dict.
    Iterates until text stabilises (handles chains like A→B→C).
    {{trim}} tokens are consumed and trigger blank-line collapse after resolution.
    {{//...}} comment tokens are stripped before macro resolution (depth-aware).
    """
    if not text:
        return text

    text = _strip_comment_macros(text)

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
        if full_key.lower() == "trim":
            return ""
        if full_key.lower().startswith("getvar::"):
            k = full_key[8:].strip()
            return str(macros.get(k, ""))
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
