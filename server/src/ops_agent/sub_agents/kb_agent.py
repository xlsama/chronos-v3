import re
from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from src.ops_agent.prompts.kb_agent import KB_AGENT_SYSTEM_PROMPT, KB_AGENT_WITH_DISCOVERY_PROMPT
from src.config import get_settings
from src.lib.logger import logger
from src.ops_agent.tools.knowledge_tools import (
    list_projects_for_matching as _list_projects,
    search_knowledge_base as _search_knowledge_base,
)

EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]

_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _build_tools_known_project(project_id: str):
    """Build tools when project_id is already known (original behavior)."""
    _last_sources: list[dict] = []

    @tool
    async def search_knowledge_base(query: str) -> str:
        """Search the project knowledge base for architecture docs, services, and connection info."""
        text, sources = await _search_knowledge_base(query=query, project_id=project_id)
        _last_sources.clear()
        _last_sources.extend(sources)
        return text

    return [search_knowledge_base], _last_sources


def _build_tools_discover_project():
    """Build tools when project_id needs to be discovered."""
    _last_sources: list[dict] = []

    @tool
    async def list_projects() -> str:
        """List all available projects with descriptions, services, and linked connections for matching."""
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


def _extract_project_id_from_text(text: str) -> str:
    """Extract project ID from the LLM's output text."""
    # Look for "Project ID: <uuid>" pattern
    match = re.search(r"Project\s*ID\s*[:：]\s*(" + _UUID_RE.pattern + r")", text, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: find any UUID in the text
    all_uuids = _UUID_RE.findall(text)
    if len(all_uuids) == 1:
        return all_uuids[0]
    return ""


async def run_kb_agent(
    description: str,
    project_id: str,
    event_callback: EventCallback,
) -> dict | str:
    """Run the KB sub agent to search project knowledge base.

    Returns:
        - dict with keys: summary, project_id, project_name, connections
          (when project discovery is involved)
        - str summary (when project_id was pre-set)
    """
    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )

    mode = "known_project" if project_id else "discover"
    if project_id:
        tools, kb_sources = _build_tools_known_project(project_id)
        system_prompt = KB_AGENT_SYSTEM_PROMPT
    else:
        tools, kb_sources = _build_tools_discover_project()
        system_prompt = KB_AGENT_WITH_DISCOVERY_PROMPT

    llm_with_tools = llm.bind_tools(tools)

    logger.info(f"\n[kb_agent] Started, description='{description[:50]}...', project_id={project_id}, mode={mode}")

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"当前事件描述: {description}"),
    ]

    # Track project info from list_projects calls
    projects_info: dict[str, dict] = {}  # project_id -> {name, connections}

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
        await event_callback("thinking_done", {})
        messages.append(full_response)

        logger.info(f"\n[kb_agent] LLM response (len={len(full_content)})")
        if full_content:
            logger.info(f"\n[kb_agent] LLM content:\n{full_content}\n")

        if not full_response.tool_calls:
            break

        for tc in full_response.tool_calls:
            tool_name = tc["name"]
            logger.info(f"\n[kb_agent] Tool call: {tool_name}({tc['args']})")
            await event_callback("tool_call", {
                "name": tool_name,
                "args": tc["args"],
            })

            # Find the matching tool and invoke it
            matching_tool = next(t for t in tools if t.name == tool_name)
            result = await matching_tool.ainvoke(tc["args"])

            result_str = str(result)
            logger.info(f"\n[kb_agent] Tool result: {len(result_str)} chars")

            event_data: dict[str, Any] = {
                "name": tool_name,
                "output": result_str,
            }
            if tool_name == "search_knowledge_base":
                event_data["sources"] = list(kb_sources)
            await event_callback("tool_result", event_data)

            # Parse project info from list_projects result
            if tool_name == "list_projects":
                _parse_projects_info(result_str, projects_info)

            messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))
    else:
        # Max iterations reached, get final response
        full_content = ""
        async for chunk in llm_with_tools.astream(messages):
            if chunk.content:
                full_content += chunk.content
                await event_callback("thinking", {"content": chunk.content})
        await event_callback("thinking_done", {})

    if not full_content:
        full_content = "项目知识库暂无相关信息"

    logger.info(f"[kb_agent] Completed, output_len={len(full_content)}")

    # Detect AGENTS.md empty and needs_human_input from LLM output
    agents_md_empty = "[空" in full_content or "未配置" in full_content or "Agents配置: [未配置]" in full_content
    needs_human_input = "是否需要用户补充: 是" in full_content or "当前没有可用项目" in full_content

    # If project_id was pre-set, return structured dict
    if project_id:
        return {
            "summary": full_content,
            "project_id": project_id,
            "project_name": "",
            "connections": [],
            "agents_md_empty": agents_md_empty,
            "needs_human_input": needs_human_input,
        }

    # Extract project_id from LLM output
    discovered_id = _extract_project_id_from_text(full_content)
    if discovered_id:
        logger.info(f"[kb_agent] Discovered project_id={discovered_id}")
    project_info = projects_info.get(discovered_id, {})

    return {
        "summary": full_content,
        "project_id": discovered_id,
        "project_name": project_info.get("name", ""),
        "connections": project_info.get("connections", []),
        "agents_md_empty": agents_md_empty,
        "needs_human_input": needs_human_input,
    }


def _parse_projects_info(text: str, info_dict: dict[str, dict]) -> None:
    """Parse the list_projects output and populate the info dict."""
    current_project_id = ""
    current_name = ""
    current_connections: list[dict] = []

    for line in text.split("\n"):
        line = line.strip()
        # Match "## 项目: xxx (ID: uuid)"
        project_match = re.match(r"##\s*项目[:：]\s*(.+?)\s*\(ID:\s*(" + _UUID_RE.pattern + r")\)", line)
        if project_match:
            # Save previous project
            if current_project_id:
                info_dict[current_project_id] = {
                    "name": current_name,
                    "connections": current_connections,
                }
            current_name = project_match.group(1)
            current_project_id = project_match.group(2)
            current_connections = []
            continue

        # Match connection lines "  - name (ID: uuid, type: xxx, host: yyy)"
        conn_match = re.match(
            r"\s*-\s*(.+?)\s*\(ID:\s*(" + _UUID_RE.pattern + r")",
            line,
        )
        if conn_match and current_project_id:
            current_connections.append({
                "id": conn_match.group(2),
                "name": conn_match.group(1),
            })

    # Save last project
    if current_project_id:
        info_dict[current_project_id] = {
            "name": current_name,
            "connections": current_connections,
        }
