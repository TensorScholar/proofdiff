from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import Mock

from langchain_core.messages import AIMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt import ToolNode
from langgraph.runtime import ExecutionInfo

PREFIX = "PROOFDIFF_PROBE="


def _runtime() -> Mock:
    runtime = Mock()
    runtime.store = None
    runtime.context = None
    runtime.stream_writer = lambda *args, **kwargs: None
    runtime.execution_info = ExecutionInfo(
        checkpoint_id="proofdiff",
        checkpoint_ns="",
        task_id="probe",
    )
    runtime.server_info = None
    return runtime


def _config() -> RunnableConfig:
    return {"configurable": {"__pregel_runtime": _runtime()}}


def tool_interrupt(some_val: int) -> None:
    """Raise graph control flow for the probe."""
    raise GraphBubbleUp("approval-required")


def tool_ok(some_val: int) -> str:
    """Return an ordinary successful tool result."""
    return f"ok:{some_val}"


def _input(tool_name: str) -> dict[str, list[AIMessage]]:
    return {
        "messages": [
            AIMessage(
                "probe",
                tool_calls=[
                    {
                        "name": tool_name,
                        "args": {"some_val": 1},
                        "id": "probe-call",
                    }
                ],
            )
        ]
    }


def _sync_interrupt_with_wrapper() -> bool:
    def wrapper(request, execute):
        return execute(request)

    node = ToolNode(
        [tool_interrupt],
        wrap_tool_call=wrapper,
        handle_tool_errors=lambda exc: f"handled:{type(exc).__name__}",
    )
    try:
        node.invoke(_input("tool_interrupt"), config=_config())
    except GraphBubbleUp:
        return True
    return False


async def _async_interrupt_with_wrapper() -> bool:
    async def wrapper(request, execute):
        return await execute(request)

    node = ToolNode(
        [tool_interrupt],
        awrap_tool_call=wrapper,
        handle_tool_errors=lambda exc: f"handled:{type(exc).__name__}",
    )
    try:
        await node.ainvoke(_input("tool_interrupt"), config=_config())
    except GraphBubbleUp:
        return True
    return False


def _direct_interrupt_propagates() -> bool:
    node = ToolNode(
        [tool_interrupt],
        handle_tool_errors=lambda exc: f"handled:{type(exc).__name__}",
    )
    try:
        node.invoke(_input("tool_interrupt"), config=_config())
    except GraphBubbleUp:
        return True
    return False


def _ordinary_wrapped_tool_succeeds() -> bool:
    def wrapper(request, execute):
        return execute(request)

    node = ToolNode([tool_ok], wrap_tool_call=wrapper, handle_tool_errors=True)
    result: Any = node.invoke(_input("tool_ok"), config=_config())
    return "ok:1" in str(result)


async def _run() -> dict[str, bool]:
    return {
        "sync_wrapper_propagates_interrupt": _sync_interrupt_with_wrapper(),
        "async_wrapper_propagates_interrupt": await _async_interrupt_with_wrapper(),
        "direct_interrupt_propagates": _direct_interrupt_propagates(),
        "ordinary_wrapped_tool_succeeds": _ordinary_wrapped_tool_succeeds(),
    }


def main() -> int:
    payload = asyncio.run(_run())
    print(PREFIX + json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
