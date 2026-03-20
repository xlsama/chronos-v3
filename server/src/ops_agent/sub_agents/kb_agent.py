import re
import time
from collections.abc import Callable, Coroutine
from typing import Any

import orjson
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.ops_agent.prompts.kb_agent import KB_AGENT_SYSTEM_PROMPT
from src.env import get_settings
from src.lib.logger import logger
from src.ops_agent.tools.knowledge_tools import (
    list_projects_for_matching as _list_projects,
    search_knowledge_base as _search_knowledge_base,
)

EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


class KBAgentOutput(BaseModel):
    project_id: str = Field(default="", description="匹配项目的 UUID")
    project_name: str = Field(default="", description="项目名称")
    agents_md_content: str = Field(default="", description="AGENTS.md 完整原文")
    business_context: str = Field(default="", description="从知识库检索到的业务信息")
    agents_md_empty: bool = Field(default=False, description="AGENTS.md 是否为空")
    no_match: bool = Field(default=False, description="是否未匹配到任何项目")


def _build_tools():
    """Build tools for KB agent (discover mode only)."""
    _last_sources: list[dict] = []

    @tool
    async def list_projects() -> str:
        """List all available projects with descriptions and AGENTS.md preview. Returns JSON array."""
        return await _list_projects()

    @tool
    async def search_knowledge_base(query: str, project_id: str) -> str:
        """Search a specific project's knowledge base. Must call list_projects first to get valid project IDs.

        Args:
            query: The search query.
            project_id: The project UUID to search within.
        """
        text, sources = await _search_knowledge_base(query=query, project_id=project_id)
        _last_sources.clear()
        _last_sources.extend(sources)
        return text

    return [list_projects, search_knowledge_base], _last_sources


def _extract_agents_md_section(search_result: str) -> str:
    """从 search_knowledge_base 返回文本中提取 AGENTS.md 部分。"""
    # 格式: ### AGENTS.md\n{content}\n\n---\n\n### 相关文档
    match = re.search(
        r"### AGENTS\.md\n(.*?)(?:\n\n---\n\n### |$)",
        search_result,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return ""


def _extract_business_context(search_result: str) -> str:
    """从 search_knowledge_base 返回文本中提取相关文档部分。"""
    match = re.search(
        r"### 相关文档\n\n(.*?)$",
        search_result,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return ""


async def run_kb_agent(
    description: str,
    event_callback: EventCallback,
) -> KBAgentOutput:
    """Run the KB sub agent to search project knowledge base.

    Returns structured KBAgentOutput with project info and knowledge base content.
    """
    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )

    tools, kb_sources = _build_tools()
    llm_with_tools = llm.bind_tools(tools)

    logger.info(f"\n[kb_agent] Started, description='{description[:50]}...'")

    messages = [
        SystemMessage(content=KB_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=f"当前事件描述: {description}"),
    ]

    # Track tool results programmatically
    projects_json: list[dict] = []
    last_search_project_id: str = ""
    last_search_result: str = ""

    max_iterations = 5
    for i in range(max_iterations):
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

        logger.info(f"[kb_agent] [iter {i+1}] LLM responded in {llm_elapsed:.2f}s, content_len={len(full_content)}")
        if full_content:
            logger.info(f"\n[kb_agent] [iter {i+1}] LLM content:\n{full_content}\n")

        if not full_response.tool_calls:
            break

        for tc in full_response.tool_calls:
            tool_name = tc["name"]
            logger.info(f"[kb_agent] [iter {i+1}] Tool call: {tool_name}({tc['args']})")
            await event_callback("tool_call", {
                "name": tool_name,
                "args": tc["args"],
            })

            matching_tool = next(t for t in tools if t.name == tool_name)
            t_tool = time.monotonic()
            result = await matching_tool.ainvoke(tc["args"])
            tool_elapsed = time.monotonic() - t_tool
            result_str = str(result)

            logger.info(f"[kb_agent] [iter {i+1}] Tool result in {tool_elapsed:.2f}s: {len(result_str)} chars")

            event_data: dict[str, Any] = {
                "name": tool_name,
                "output": result_str,
            }
            if tool_name == "search_knowledge_base":
                event_data["sources"] = list(kb_sources)
            await event_callback("tool_result", event_data)

            # Programmatically track tool results
            if tool_name == "list_projects":
                try:
                    projects_json = orjson.loads(result_str)
                except (orjson.JSONDecodeError, TypeError):
                    projects_json = []

            elif tool_name == "search_knowledge_base":
                last_search_project_id = tc["args"].get("project_id", "")
                last_search_result = result_str

            messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))
    else:
        # Max iterations reached, get final response
        full_content = ""
        async for chunk in llm_with_tools.astream(messages):
            if chunk.content:
                full_content += chunk.content
                await event_callback("thinking", {"content": chunk.content})
        await event_callback("thinking_done", {})

    # Build structured output from tracked tool results
    project_info = next(
        (p for p in projects_json if p.get("project_id") == last_search_project_id),
        {},
    )
    agents_md_content = _extract_agents_md_section(last_search_result)
    business_context = _extract_business_context(last_search_result)

    output = KBAgentOutput(
        project_id=last_search_project_id,
        project_name=project_info.get("project_name", ""),
        agents_md_content=agents_md_content,
        business_context=business_context,
        agents_md_empty=not agents_md_content.strip() or "[空" in agents_md_content,
        no_match=not last_search_project_id,
    )

    logger.info(f"[kb_agent] Completed: project_id={output.project_id}, project_name={output.project_name}, "
                f"agents_md_empty={output.agents_md_empty}, no_match={output.no_match}")

    return output
