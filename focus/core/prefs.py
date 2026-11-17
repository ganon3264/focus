"""Display and input preferences.

One blob in the settings table, so every knob is a key here and nothing is
scattered into localStorage. Values are display-only on purpose: anything that
changes what gets sent to a provider belongs to the chat or the preset, not to a
global preference.
"""

from __future__ import annotations

DEFAULTS = {
    "send_key": "enter",
    "follow_stream": "pinned",
    "reasoning_open": "off",
    "clock": "24h",
    "chat_width": 800,
    "text_size": "medium",
    "prune_messages": True,
}

CHOICES = {
    "send_key": ("enter", "ctrl_enter"),
    "follow_stream": ("pinned", "always", "disabled"),
    "reasoning_open": ("off", "stream", "keep"),
    "clock": ("24h", "12h", "hidden"),
    "text_size": ("small", "medium", "large"),
}

WIDTH_MIN = 480
WIDTH_MAX = 1600


def normalize(raw: object) -> dict:
    prefs = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return prefs

    for key, allowed in CHOICES.items():
        if raw.get(key) in allowed:
            prefs[key] = raw[key]

    if isinstance(raw.get("prune_messages"), bool):
        prefs["prune_messages"] = raw["prune_messages"]

    width = raw.get("chat_width")
    if isinstance(width, (int, float)) and not isinstance(width, bool):
        prefs["chat_width"] = max(WIDTH_MIN, min(WIDTH_MAX, int(width)))

    return prefs
