from __future__ import annotations

import json
import logging
from typing import Any

from focus.tools import (
    MAX_TOOL_ITERATIONS,
    ToolCall,
    ToolResult,
    ToolSpec,
    active_tools,
    build_tool_result,
)
from focus.tools.provider_adapter import (
    to_provider_tool_results,
    to_provider_tools,
)

logger = logging.getLogger("focus.tools.loop")


async def _maybe_await(handler: Any, **kwargs: Any) -> Any:
    result = handler(**kwargs)
    if hasattr(result, "__await__"):
        result = await result
    return result


async def run_with_tools(
    messages: list[dict],
    provider: Any,
    all_tools: list[ToolSpec],
    read_only: bool,
    max_iterations: int = MAX_TOOL_ITERATIONS,
) -> str:
    """Provider-agnostic tool execution loop.

    Calls provider.stream_complete() iteratively, executing any tool calls
    that appear in responses. Returns the final text once no more tool calls
    are made.

    The caller is responsible for passing tools=to_provider_tools(...) in
    the kwargs to stream_complete.
    """
    tools = active_tools(all_tools, read_only)
    tools_by_name = {t.name: t for t in tools}
    tools_payload = to_provider_tools(tools)

    for iteration in range(max_iterations):
        text_parts: list[str] = []
        response_tool_calls: list[ToolCall] | None = None

        logger.debug("Tool loop iteration %d/%d", iteration + 1, max_iterations)
        async for event in provider.stream_complete(
            messages,
            tools=tools_payload,
            tool_choice="auto",
        ):
            if event["type"] == "token":
                text_parts.append(event["text"])
            elif event["type"] == "tool_calls":
                response_tool_calls = event["calls"]
                break
            elif event["type"] == "done":
                response_tool_calls = None
                break

        if not response_tool_calls:
            return "".join(text_parts)

        full_text = "".join(text_parts)

        # Append the assistant message (with tool_calls) to history
        asst_msg: dict[str, Any] = {"role": "assistant", "content": full_text or None}
        asst_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in response_tool_calls
        ]
        messages.append(asst_msg)

        # Execute each tool
        results: list[ToolResult] = []
        for call in response_tool_calls:
            tool = tools_by_name.get(call.name)
            if tool is None or (read_only and tool.writes):
                msg = "tool unavailable in read-only mode" if read_only else f"unknown tool: {call.name}"
                results.append(ToolResult(call.id, msg, is_error=True))
                logger.warning("Tool call blocked: %s (%s)", call.name, msg)
                continue
            try:
                logger.debug("Executing tool: %s args=%s", call.name, call.arguments)
                output = await _maybe_await(tool.handler, **call.arguments)
                results.append(build_tool_result(call.id, call.name, output))
            except Exception as e:
                logger.exception("Tool execution failed: %s", call.name)
                results.append(ToolResult(call.id, f"error: {e}", is_error=True))

        # Append tool result messages
        messages.extend(to_provider_tool_results(results))

        # Append any extra messages (e.g. read_image's synthetic user message)
        for r in results:
            if r.extra_message is not None:
                messages.append(r.extra_message)

        # Rebuild tools payload in case active_tools changed (defensive)
        tools_by_name = {t.name: t for t in tools}

    logger.warning("Tool call loop exceeded max iterations (%d)", max_iterations)
    return "[stopped: tool call loop exceeded max iterations]"
