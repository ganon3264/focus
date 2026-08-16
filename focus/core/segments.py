from __future__ import annotations

from focus.core.message_render import escape_html


def build_segments(
    text_slices: list[int],
    reasoning_slices: list[int],
    final_text: list[str],
    final_reasoning: list[str],
    tool_call_groups: list[list[dict]] | None = None,
) -> list[dict]:
    """Build segment list from per-iteration text/reasoning ranges.

    When tool_call_groups are provided, each ``tool_boundary`` segment
    carries its own ``tool_calls`` list so the template can render calls
    per iteration instead of dumping all calls at the first boundary.

    Returns a flat list of segment dicts matching
    ``render_message_segments()`` output format:
      {"type": "text", "content": str}
      {"type": "reasoning", "html": str, "index": int}
      {"type": "tool_boundary"}           (legacy, no tool_calls)
      {"type": "tool_boundary", "tool_calls": [...]}  (new)
    """
    segments: list[dict] = []
    reasoning_ordinal = 0
    has_preceding = False
    prev_t = 0
    prev_r = 0

    for i in range(len(text_slices)):
        t_end = text_slices[i]
        r_end = reasoning_slices[i]

        if r_end > prev_r:
            r_text = "".join(final_reasoning[prev_r:r_end]).strip()
            if r_text:
                # index 0 is reserved for reasoning that arrived before any
                # text or tool call (header-controlled). Reasoning that follows
                # a tool boundary or text gets an inline toggle (index >= 1).
                if reasoning_ordinal == 0 and not has_preceding:
                    index = 0
                else:
                    index = reasoning_ordinal + 1
                segments.append({
                    "type": "reasoning",
                    "html": escape_html(r_text),
                    "index": index,
                })
                reasoning_ordinal += 1

        if t_end > prev_t:
            t_text = "".join(final_text[prev_t:t_end]).strip()
            if t_text:
                segments.append({"type": "text", "content": t_text})
                has_preceding = True

        if i < len(text_slices) - 1:
            seg: dict = {"type": "tool_boundary"}
            if tool_call_groups and i < len(tool_call_groups):
                seg["tool_calls"] = tool_call_groups[i]
            segments.append(seg)
            has_preceding = True

        prev_t = t_end
        prev_r = r_end

    return segments
