from __future__ import annotations

import asyncio
import json
from typing import Any

from ag_ui.core import RunAgentInput, UserMessage
from copilotkit.copilotkit_lg_middleware import CopilotKitMiddleware
from copilotkit.langgraph_agui_agent import LangGraphAGUIAgent
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from pydantic import Field
from typing_extensions import TypedDict

PREFIX = "PROOFDIFF_PROBE="


class RecordingToolAwareChatModel(BaseChatModel):
    bound_tools: list[Any] = Field(default_factory=list)
    last_messages: list[BaseMessage] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "proofdiff-recording-tool-aware-chat-model"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        self.bound_tools = list(tools)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        self.last_messages = list(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])


class ParentState(TypedDict):
    messages: list[Any]


class ParentContext(TypedDict, total=False):
    copilotkit: dict[str, Any]


def _input(run_id: str) -> RunAgentInput:
    return RunAgentInput(
        thread_id=f"thread-{run_id}",
        run_id=run_id,
        state={},
        messages=[UserMessage(id=f"message-{run_id}", content="hi")],
        tools=[{"name": "frontend_lookup", "description": "frontend tool"}],
        context=[{"description": "viewer role", "value": "admin"}],
        forwarded_props={},
    )


async def _consume(agent: LangGraphAGUIAgent, run_id: str) -> None:
    async for _ in agent.run(_input(run_id)):
        pass


def _observed(model: RecordingToolAwareChatModel) -> dict[str, Any]:
    tool_names = [
        item.get("name")
        for item in model.bound_tools
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    system_contents = [
        str(message.content)
        for message in model.last_messages
        if isinstance(message, SystemMessage)
    ]
    return {
        "tool_names": tool_names,
        "frontend_tool_present": "frontend_lookup" in tool_names,
        "app_context_present": any(
            "App Context:" in content and "admin" in content for content in system_contents
        ),
        "model_invoked": bool(model.last_messages),
    }


async def _top_level() -> dict[str, Any]:
    model = RecordingToolAwareChatModel()
    middleware = CopilotKitMiddleware()
    graph = create_agent(
        model=model,
        tools=[],
        middleware=[middleware],
        context_schema=ParentContext,
        checkpointer=MemorySaver(),
    )
    agent = LangGraphAGUIAgent(name="top-level", graph=graph)
    await _consume(agent, "top")
    return _observed(model)


async def _subgraph() -> dict[str, Any]:
    model = RecordingToolAwareChatModel()
    middleware = CopilotKitMiddleware()
    child_agent = create_agent(
        model=model,
        tools=[],
        middleware=[middleware],
        context_schema=ParentContext,
    )
    parent = StateGraph(ParentState, context_schema=ParentContext)
    parent.add_node("child", child_agent)
    parent.add_edge(START, "child")
    parent.add_edge("child", END)
    agent = LangGraphAGUIAgent(
        name="parent",
        graph=parent.compile(checkpointer=MemorySaver()),
    )
    await _consume(agent, "subgraph")
    return _observed(model)


async def _run() -> dict[str, Any]:
    payload: dict[str, Any] = {}
    try:
        payload["top_level"] = await _top_level()
    except Exception as exc:
        payload["top_level"] = {
            "frontend_tool_present": False,
            "app_context_present": False,
            "model_invoked": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    try:
        payload["subgraph"] = await _subgraph()
    except Exception as exc:
        payload["subgraph"] = {
            "frontend_tool_present": False,
            "app_context_present": False,
            "model_invoked": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return payload


def main() -> int:
    payload = asyncio.run(_run())
    print(PREFIX + json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
