from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from src.agent.prompts.kb_agent import KB_AGENT_SYSTEM_PROMPT
from src.config import get_settings
from src.tools.knowledge_tools import search_knowledge_base

EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


def _build_search_tool(project_id: str):
    @tool
    async def search_knowledge_base_tool(query: str) -> str:
        """Search the project knowledge base for architecture docs, services, and infrastructure info."""
        return await search_knowledge_base(query=query, project_id=project_id)

    return search_knowledge_base_tool


async def run_kb_agent(
    title: str,
    description: str,
    project_id: str,
    event_callback: EventCallback,
) -> str:
    """Run the KB sub agent to search project knowledge base.

    Returns a summary string of KB context (or "项目知识库暂无相关信息").
    """
    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )

    search_tool = _build_search_tool(project_id)
    llm_with_tools = llm.bind_tools([search_tool])

    messages = [
        SystemMessage(content=KB_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=f"当前事件标题: {title}\n当前事件描述: {description}"),
    ]

    max_iterations = 5
    for _ in range(max_iterations):
        full_content = ""
        full_response: AIMessage | None = None

        async for chunk in llm_with_tools.astream(messages):
            if chunk.content:
                full_content += chunk.content
                await event_callback("thinking", {"content": chunk.content})
            full_response = chunk if full_response is None else full_response + chunk

        assert full_response is not None
        messages.append(full_response)

        if not full_response.tool_calls:
            return full_content

        for tc in full_response.tool_calls:
            await event_callback("tool_call", {
                "name": "search_knowledge_base",
                "args": tc["args"],
            })

            result = await search_tool.ainvoke(tc["args"])

            await event_callback("tool_result", {
                "name": "search_knowledge_base",
                "output": str(result),
            })

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    # Final response after tool use
    full_content = ""
    async for chunk in llm_with_tools.astream(messages):
        if chunk.content:
            full_content += chunk.content
            await event_callback("thinking", {"content": chunk.content})

    return full_content or "项目知识库暂无相关信息"
