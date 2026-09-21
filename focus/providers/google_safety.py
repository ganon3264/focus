"""Google/Gemini safety settings, as shared data.

The native Google adapters build ``types.SafetySetting`` objects from these
category tuples; the OpenRouter passthrough sends the same categories as raw
JSON. Keeping the lists here is what lets both paths share one source.

OpenRouter's Google passthrough only validates the AI Studio category set
(``AI_STUDIO_HARM_CATEGORIES``) for the models tested; Vertex's extra image /
civic / jailbreak categories are rejected (HTTP 400). So passthrough uses the
AI Studio set, which is accepted on both OpenRouter upstreams.
"""

from __future__ import annotations

VERTEX_HARM_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
    "HARM_CATEGORY_CIVIC_INTEGRITY",
    "HARM_CATEGORY_IMAGE_HATE",
    "HARM_CATEGORY_IMAGE_DANGEROUS_CONTENT",
    "HARM_CATEGORY_IMAGE_HARASSMENT",
    "HARM_CATEGORY_IMAGE_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_JAILBREAK",
)

AI_STUDIO_HARM_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)

# Category set accepted by OpenRouter's Google passthrough.
PASSTHROUGH_HARM_CATEGORIES = AI_STUDIO_HARM_CATEGORIES

def safety_settings_json(
    categories: tuple[str, ...] = PASSTHROUGH_HARM_CATEGORIES,
    threshold: str = "OFF",
) -> list[dict]:
    """Plain-JSON safety_settings payload (Gemini REST shape)."""
    return [{"category": c, "threshold": threshold} for c in categories]
