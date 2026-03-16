from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from src.agent.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from src.agent.state import OpsState
from src.config import get_settings
from src.tools.exec_tools import exec_read, exec_write, list_connections
from src.tools.http_tools import http_request
from src.tools.monitoring_tools import query_logs, query_metrics


def build_tools(has_prometheus: bool = False, has_loki: bool = False):
    from langchain_core.tools import tool

    @tool
    async def exec_read_tool(connection_id: str, command: str) -> dict:
        """Execute a read-only command on the target connection.
        Use this for diagnostic commands like: df -h, free -m, ps aux, cat, etc.
        Works for both SSH servers and Kubernetes clusters.
        """
        return await exec_read(connection_id=connection_id, command=command)

    @tool
    async def exec_write_tool(
        connection_id: str,
        command: str,
        explanation: str,
        risk_level: str,
        risk_detail: str,
    ) -> dict:
        """Execute a write command on the target connection.
        This requires human approval.
        - explanation: 操作说明（为什么需要执行这个命令）
        - risk_level: LOW / MEDIUM / HIGH
        - risk_detail: 风险说明（可能的影响）
        """
        return await exec_write(connection_id=connection_id, command=command)

    @tool
    async def http_request_tool(
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
    ) -> dict:
        """Execute an HTTP request to test APIs, health endpoints, or external services.
        - method: GET, POST, PUT, DELETE, PATCH, HEAD
        - url: Full URL (e.g. http://localhost:8080/health)
        - headers: Optional JSON string, e.g. '{"Authorization": "Bearer xxx"}'
        - body: Optional request body
        """
        return await http_request(method=method, url=url, headers=headers, body=body)

    @tool
    async def list_connections_tool(project_id: str = "") -> list[dict]:
        """List available connections. Returns id, name, type, host, status, project_id.
        Use this to discover target connection when no connection_id is specified.
        Optionally filter by project_id.
        """
        return await list_connections(project_id=project_id)

    @tool
    def ask_human(question: str) -> str:
        """当你缺少关键信息无法继续排查时，向用户提问。
        例如：不确定事件涉及哪个服务、哪个连接、需要额外上下文等。
        """
        return question

    @tool
    def complete(summary: str) -> str:
        """Call this when the investigation is complete. Provide a brief summary."""
        return summary

    tools = [
        exec_read_tool,
        exec_write_tool,
        list_connections_tool,
        http_request_tool,
        ask_human,
        complete,
    ]

    if has_prometheus:
        @tool
        async def query_metrics_tool(
            project_id: str,
            query: str,
            start: str | None = None,
            end: str | None = None,
            step: str = "60s",
        ) -> dict:
            """Query Prometheus metrics using PromQL.
            - project_id: The project ID to find the Prometheus data source
            - query: PromQL expression (e.g. 'rate(http_requests_total[5m])')
            - start/end: RFC3339 timestamps for range query. Omit for instant query.
            - step: Query resolution step (default '60s')
            """
            return await query_metrics(
                project_id=project_id, query=query, start=start, end=end, step=step
            )

        tools.append(query_metrics_tool)

    if has_loki:
        @tool
        async def query_logs_tool(
            project_id: str,
            query: str,
            start: str | None = None,
            end: str | None = None,
            limit: int = 100,
        ) -> dict:
            """Query logs using LogQL (Loki).
            - project_id: The project ID to find the Loki data source
            - query: LogQL expression (e.g. '{app="myapp"} |= "error"')
            - start/end: RFC3339 timestamps for the query range
            - limit: Max number of log lines (default 100)
            """
            return await query_logs(
                project_id=project_id, query=query, start=start, end=end, limit=limit
            )

        tools.append(query_logs_tool)

    return tools


def build_all_tools():
    """Build all tools including conditional ones (for ToolNode registration)."""
    return build_tools(has_prometheus=True, has_loki=True)


def get_llm():
    s = get_settings()
    return ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )


async def main_agent_node(state: OpsState) -> dict:
    has_prometheus = state.get("has_prometheus", False)
    has_loki = state.get("has_loki", False)
    tools = build_tools(has_prometheus=has_prometheus, has_loki=has_loki)
    llm = get_llm().bind_tools(tools)

    history_summary = state.get("incident_history_summary")
    if history_summary:
        history_context = f"## 历史事件参考\n以下是与当前事件相似的历史事件供参考：\n\n{history_summary}"
    else:
        history_context = ""

    kb_summary = state.get("kb_summary")
    if kb_summary:
        kb_context = f"## 项目知识库上下文\n{kb_summary}"
    else:
        kb_context = ""

    # Build conditional tool docs
    extra_tools_doc = ""
    if has_prometheus:
        extra_tools_doc += "- **query_metrics**: 查询 Prometheus 指标（PromQL）\n"
    if has_loki:
        extra_tools_doc += "- **query_logs**: 查询 Loki 日志（LogQL）\n"

    conn_id = state["connection_id"]
    if conn_id:
        connection_context = f"已指定连接 ID: {conn_id}，优先使用此连接执行命令。"
    else:
        connection_context = "未指定连接，请先使用 list_connections 工具查找可用的连接，然后根据事件描述选择合适的目标。"

    system_prompt = MAIN_AGENT_SYSTEM_PROMPT.format(
        title=state["title"],
        description=state["description"],
        severity=state["severity"],
        connection_context=connection_context,
        project_id=state.get("project_id", ""),
        incident_history_context=history_context,
        kb_context=kb_context,
        extra_tools_doc=extra_tools_doc,
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    response = await llm.ainvoke(messages)

    return {"messages": [response]}


def route_decision(state: OpsState) -> str:
    last_message = state["messages"][-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        # No tool calls — agent is sharing analysis or asking for context.
        # Interrupt so the user can see the response and reply.
        return "ask_human"

    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "complete":
            return "complete"
        if tool_call["name"] == "exec_write_tool":
            return "need_approval"
        if tool_call["name"] == "ask_human":
            return "ask_human"

    return "continue"
