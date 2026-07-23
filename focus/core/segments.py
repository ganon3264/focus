from __future__ import annotations

from focus.core.message_render import _escape_html


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
    reasoning_idx = 0
    prev_t = 0
    prev_r = 0

    for i in range(len(text_slices)):
        t_end = text_slices[i]
        r_end = reasoning_slices[i]

        if r_end > prev_r:
            r_text = "".join(final_reasoning[prev_r:r_end]).strip()
            if r_text:
                segments.append({
                    "type": "reasoning",
                    "html": _escape_html(r_text),
                    "index": reasoning_idx,
                })
                reasoning_idx += 1

        if t_end > prev_t:
            t_text = "".join(final_text[prev_t:t_end]).strip()
            if t_text:
                segments.append({"type": "text", "content": t_text})

        if i < len(text_slices) - 1:
            seg: dict = {"type": "tool_boundary"}
            if tool_call_groups and i < len(tool_call_groups):
                seg["tool_calls"] = tool_call_groups[i]
            segments.append(seg)

        prev_t = t_end
        prev_r = r_end

    return segments
