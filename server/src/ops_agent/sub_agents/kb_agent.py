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
from src.lib.logger import get_logger
from src.ops_agent.tools.knowledge_tools import (
    get_agents_md as _get_agents_md,
    list_projects_for_matching as _list_projects,
    search_knowledge_base as _search_knowledge_base,
)

EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


class KBProjectInfo(BaseModel):
    project_id: str = Field(default="", description="项目 UUID")
    project_name: str = Field(default="", description="项目名称")
    project_description: str = Field(default="", description="项目描述")
    agents_md_content: str = Field(default="", description="AGENTS.md 完整原文")
    agents_md_empty: bool = Field(default=False, description="AGENTS.md 是否为空")
    business_context: str = Field(default="", description="该项目下检索到的相关文档片段")


class KBAgentOutput(BaseModel):
    projects: list[KBProjectInfo] = Field(default_factory=list, description="匹配到的项目列表")


def _build_tools():
    """Build tools for KB agent."""
    _last_sources: list[dict] = []

    @tool
    async def list_projects() -> str:
        """List all available projects with descriptions and AGENTS.md preview. Returns JSON array."""
        return await _list_projects()

    @tool
    async def search_knowledge_base(query: str) -> str:
        """Search across all projects' knowledge base. Returns results grouped by project with project metadata.

        Args:
            query: The search query.
        """
        text, sources = await _search_knowledge_base(query=query)
        _last_sources.clear()
        _last_sources.extend(sources)
        return text

    @tool
    async def get_agents_md(project_ids: list[str]) -> str:
        """Batch read AGENTS.md for multiple projects.

        Args:
            project_ids: List of project UUIDs to read AGENTS.md from.
        """
        return await _get_agents_md(project_ids=project_ids)

    return [list_projects, search_knowledge_base, get_agents_md], _last_sources


def _parse_search_results_by_project(search_result: str) -> dict[str, dict]:
    """Parse search results into per-project info.

    Returns dict: project_id -> {"project_name": ..., "project_description": ..., "business_context": ...}
    """
    result: dict[str, dict] = {}
    # Split by project sections: ## 项目: xxx (ID: uuid)
    parts = re.split(r'\n*---\n*', search_result)
    for part in parts:
        match = re.match(
            r'## 项目:\s*(.+?)\s*\(ID:\s*([0-9a-f-]+)\)',
            part.strip(),
        )
        if not match:
            continue
        project_name = match.group(1)
        project_id = match.group(2)

        # Extract description if present
        desc_match = re.search(r'^描述:\s*(.+)$', part, re.MULTILINE)
        project_description = desc_match.group(1).strip() if desc_match else ""

        # The rest after header/description is the business context (chunk content)
        # Remove the header line and description line
        lines = part.strip().split('\n')
        context_lines = []
        skip_header = True
        for line in lines:
            if skip_header:
                if line.startswith('## 项目:') or line.startswith('描述:'):
                    continue
                skip_header = False
            context_lines.append(line)
        business_context = '\n'.join(context_lines).strip()

        result[project_id] = {
            "project_name": project_name,
            "project_description": project_description,
            "business_context": business_context,
        }
    return result


def _parse_agents_md_result(agents_md_text: str) -> dict[str, dict]:
    """Parse get_agents_md result into per-project info.

    Returns dict: project_id -> {"project_name": ..., "agents_md_content": ..., "agents_md_empty": bool}
    """
    result: dict[str, dict] = {}
    parts = re.split(r'\n*---\n*', agents_md_text)
    for part in parts:
        match = re.match(
            r'## 项目:\s*(.+?)\s*\(ID:\s*([0-9a-f-]+)\)',
            part.strip(),
        )
        if not match:
            continue
        project_name = match.group(1)
        project_id = match.group(2)

        # Extract AGENTS.md content (after ### AGENTS.md header)
        md_match = re.search(r'### AGENTS\.md\n(.*)', part, re.DOTALL)
        agents_md_content = md_match.group(1).strip() if md_match else ""
        agents_md_empty = not agents_md_content or "[空" in agents_md_content

        result[project_id] = {
            "project_name": project_name,
            "agents_md_content": agents_md_content,
            "agents_md_empty": agents_md_empty,
        }
    return result


async def run_kb_agent(
    description: str,
    event_callback: EventCallback,
) -> KBAgentOutput:
    """Run the KB sub agent to search project knowledge base.

    Returns structured KBAgentOutput with multi-project info and knowledge base content.
    """
    log = get_logger(component="kb_agent")
    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )

    tools, kb_sources = _build_tools()
    llm_with_tools = llm.bind_tools(tools)

    log.info("Started", description_len=len(description))
    log.debug("Started", description=description)

    messages = [
        SystemMessage(content=KB_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=f"当前事件描述: {description}"),
    ]

    agents_md_results: dict[str, dict] = {}  # project_id -> parsed agents_md info
    search_results_by_project: dict[str, dict] = {}  # project_id -> parsed search info

    max_iterations = 10
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
            break

        for tc in full_response.tool_calls:
            tool_name = tc["name"]
            iter_log.info("Tool call", tool=tool_name, args=tc["args"])
            await event_callback("tool_call", {
                "name": tool_name,
                "args": tc["args"],
            })

            matching_tool = next(t for t in tools if t.name == tool_name)
            t_tool = time.monotonic()
            result = await matching_tool.ainvoke(tc["args"])
            tool_elapsed = time.monotonic() - t_tool
            result_str = str(result)

            iter_log.info("Tool result", elapsed=f"{tool_elapsed:.2f}s", chars=len(result_str))

            event_data: dict[str, Any] = {
                "name": tool_name,
                "output": result_str,
            }
            if tool_name == "search_knowledge_base":
                event_data["sources"] = list(kb_sources)
            await event_callback("tool_result", event_data)

            if tool_name == "search_knowledge_base":
                search_results_by_project = _parse_search_results_by_project(result_str)
                iter_log.info(
                    "search_knowledge_base parsed",
                    project_count=len(search_results_by_project),
                    projects=[
                        {
                            "project_id": pid,
                            "project_name": info.get("project_name"),
                            "business_context_len": len(info.get("business_context", "")),
                        }
                        for pid, info in search_results_by_project.items()
                    ],
                )

            elif tool_name == "list_projects":
                try:
                    parsed_projects = orjson.loads(result_str)
                    iter_log.info(
                        "list_projects parsed",
                        project_count=len(parsed_projects),
                        project_names=[p.get("project_name") for p in parsed_projects],
                    )
                except Exception:
                    iter_log.info("list_projects result (non-JSON)", chars=len(result_str))

            elif tool_name == "get_agents_md":
                agents_md_results = _parse_agents_md_result(result_str)
                iter_log.info(
                    "get_agents_md parsed",
                    project_count=len(agents_md_results),
                    projects=[
                        {
                            "project_id": pid,
                            "project_name": info.get("project_name"),
                            "agents_md_len": len(info.get("agents_md_content", "")),
                            "agents_md_empty": info.get("agents_md_empty"),
                        }
                        for pid, info in agents_md_results.items()
                    ],
                )

            messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))
    else:
        full_content = ""
        async for chunk in llm_with_tools.astream(messages):
            if chunk.content:
                full_content += chunk.content
                await event_callback("thinking", {"content": chunk.content})
        await event_callback("thinking_done", {})

    # Build output: merge search results and agents_md results
    all_project_ids = set(search_results_by_project.keys()) | set(agents_md_results.keys())
    project_infos: list[KBProjectInfo] = []

    for pid in all_project_ids:
        search_info = search_results_by_project.get(pid, {})
        agents_info = agents_md_results.get(pid, {})

        project_name = agents_info.get("project_name") or search_info.get("project_name", "")
        agents_md_content = agents_info.get("agents_md_content", "")
        agents_md_empty = agents_info.get("agents_md_empty", True)
        business_context = search_info.get("business_context", "")
        project_description = search_info.get("project_description", "")

        project_infos.append(KBProjectInfo(
            project_id=pid,
            project_name=project_name,
            project_description=project_description,
            agents_md_content=agents_md_content,
            agents_md_empty=agents_md_empty,
            business_context=business_context,
        ))

    output = KBAgentOutput(projects=project_infos)

    for p in output.projects:
        log.info(
            "KBProjectInfo",
            project_id=p.project_id,
            project_name=p.project_name,
            agents_md_len=len(p.agents_md_content),
            agents_md_empty=p.agents_md_empty,
            business_context_len=len(p.business_context),
        )

    log.info(
        "Completed",
        project_count=len(output.projects),
        project_ids=[p.project_id for p in output.projects],
    )
    log.debug("KBAgentOutput full", output=output.model_dump_json())

    return output
