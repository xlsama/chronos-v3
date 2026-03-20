import time
from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from src.ops_agent.prompts.history_agent import HISTORY_AGENT_SYSTEM_PROMPT
from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.tools.history_tools import search_incident_history as _search_incident_history

EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


def _build_search_tool():
    _last_sources: list[dict] = []

    @tool
    async def search_incident_history(query: str) -> str:
        """Search historical incident records for similar past events."""
        text, sources = await _search_incident_history(query=query)
        _last_sources.clear()
        _last_sources.extend(sources)
        return text

    return search_incident_history, _last_sources


async def run_history_agent(
    description: str,
    event_callback: EventCallback,
) -> str:
    """Run the history sub agent to find similar past incidents.

    Returns a summary string of historical context (or "暂无相似历史事件").
    """
    log = get_logger(component="history_agent")
    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )

    search_tool, last_sources = _build_search_tool()
    llm_with_tools = llm.bind_tools([search_tool])

    log.info("Started", description=description[:50])

    messages = [
        SystemMessage(content=HISTORY_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=f"当前事件描述: {description}"),
    ]

    max_iterations = 5
    for i in range(max_iterations):
        iter_log = log.bind(iteration=i + 1)
        full_content = ""
        full_response: AIMessage | None = None

        t_llm = time.monotonic()
        async for chunk in llm_with_tools.astream(messages):
            if chunk.content:
                full_content += chunk.content
                await event_callback("thinking", {"content": chunk.content})
            full_response = chunk if full_response is None else full_response + chunk
        llm_elapsed = time.monotonic() - t_llm

        assert full_response is not None
        await event_callback("thinking_done", {})
        messages.append(full_response)

        iter_log.info("LLM responded", elapsed=f"{llm_elapsed:.2f}s", content_len=len(full_content))
        if full_content:
            iter_log.info("LLM content", content=full_content)

        if not full_response.tool_calls:
            iter_log.info("Completed", output_len=len(full_content))
            return full_content

        for tc in full_response.tool_calls:
            iter_log.info("Tool call: search_incident_history", query=tc["args"].get("query", ""))
            await event_callback("tool_call", {
                "name": "search_incident_history",
                "args": tc["args"],
            })

            t_tool = time.monotonic()
            result = await search_tool.ainvoke(tc["args"])
            tool_elapsed = time.monotonic() - t_tool

            result_str = str(result)
            iter_log.info("Tool result", elapsed=f"{tool_elapsed:.2f}s", chars=len(result_str), sources=len(last_sources))

            await event_callback("tool_result", {
                "name": "search_incident_history",
                "output": result_str,
                "sources": list(last_sources),
            })

            from langchain_core.messages import ToolMessage
            messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))

    full_content = ""
    t_llm = time.monotonic()
    async for chunk in llm_with_tools.astream(messages):
        if chunk.content:
            full_content += chunk.content
            await event_callback("thinking", {"content": chunk.content})
    llm_elapsed = time.monotonic() - t_llm

    await event_callback("thinking_done", {})
    log.info("Final LLM response", elapsed=f"{llm_elapsed:.2f}s", output_len=len(full_content))
    return full_content or "暂无相似历史事件"
