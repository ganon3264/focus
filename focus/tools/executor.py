from __future__ import annotations

import json
import logging
import uuid

import aiosqlite

from focus.core.utils import now_iso
from focus.crud import db_conn
from focus.tools import ToolResult, build_tool_result

logger = logging.getLogger("focus.tools.executor")


async def apply_tool_round(
    loop_messages: list,
    tool_calls_list: list,
    tools_by_name: dict,
    read_only: bool,
    chat_id: str,
    asst_msg_id: str,
    variant_id: str,
    iter_collected: list[str],
    iter_reasoning: list[str] | None = None,
    disable_multimodal: bool = False,
    db: aiosqlite.Connection | None = None,
) -> list:
    """Build assistant message with tool_calls, execute tools, append results
    to loop_messages. Returns the ToolResult list so callers can yield SSE events."""
    asst_text = "".join(iter_collected).strip()
    asst_msg: dict = {"role": "assistant", "content": asst_text or None}
    if iter_reasoning:
        reasoning_text = "".join(iter_reasoning).strip()
        if reasoning_text:
            asst_msg["reasoning"] = reasoning_text
    asst_msg["tool_calls"] = [
        {"id": tc.id, "type": "function",
         "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
        for tc in tool_calls_list
    ]
    loop_messages.append(asst_msg)

    results = await execute_tool_round(
        tool_calls_list, tools_by_name, read_only,
        chat_id, asst_msg_id, variant_id, db=db,
    )
    for r in results:
        loop_messages.append({"role": "tool", "tool_call_id": r.call_id, "content": r.content})
        if r.extra_message is not None:
            em = r.extra_message
            if disable_multimodal:
                content = em.get("content", [])
                if isinstance(content, list):
                    content = [p for p in content if p.get("type") == "text"]
                    if len(content) == 1:
                        em = {"role": "user", "content": content[0].get("text", "")}
                    else:
                        em = {"role": "user", "content": content}
            loop_messages.append(em)

    return results


async def execute_tool_round(
    tool_calls_list: list,
    tools_by_name: dict,
    read_only: bool,
    chat_id: str,
    asst_msg_id: str,
    variant_id: str | None,
    db: aiosqlite.Connection | None = None,
) -> list:
    """Execute a list of ToolCall objects and return ToolResult list.

    Also persists each call to the tool_calls table.
    """
    results: list = []

    for call in tool_calls_list:
        tool = tools_by_name.get(call.name)
        if tool is None or (read_only and tool.writes):
            msg = "tool unavailable in read-only mode" if read_only else f"unknown tool: {call.name}"
            result = ToolResult(call.id, msg, is_error=True)
            results.append(result)
            logger.warning("Tool call blocked: %s (%s)", call.name, msg)
            continue
        try:
            logger.debug("Executing tool: %s args=%s", call.name, call.arguments)
            output = tool.handler(**call.arguments)
            if hasattr(output, "__await__"):
                output = await output
            result = build_tool_result(call.id, call.name, output, multimodal=tool.multimodal)
            results.append(result)
        except Exception as e:
            logger.exception("Tool execution failed: %s", call.name)
            results.append(ToolResult(call.id, f"error: {e}", is_error=True))

    # Persist to tool_calls table
    if results:
        save_now = now_iso()
        async with db_conn(db) as conn:
            for call, result in zip(tool_calls_list, results):
                extra_msg = json.dumps(result.extra_message) if result.extra_message else None
                await conn.execute(
                    """INSERT INTO tool_calls
                       (id, chat_id, message_id, variant_id, tool_name, arguments, result, is_error, extra_message_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        chat_id,
                        asst_msg_id,
                        variant_id,
                        call.name,
                        json.dumps(call.arguments),
                        result.content,
                        int(result.is_error),
                        extra_msg,
                        save_now,
                    ),
                )
            await conn.commit()

    return results
