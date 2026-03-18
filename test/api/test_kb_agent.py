"""KB Sub-Agent 完整流程测试"""

import pytest

pytestmark = pytest.mark.api
QUERY = "Nginx 502 报错"


@pytest.mark.asyncio
async def test_kb_agent_known_project(project_id, event_callback):
    """KB Agent 已知项目模式返回结构化结果"""
    from src.ops_agent.sub_agents.kb_agent import run_kb_agent

    print(f"Query: {QUERY}, project_id: {project_id}")
    result = await run_kb_agent(description=QUERY, project_id=project_id, event_callback=event_callback)
    print(f"Result type: {type(result).__name__}")
    print(f"Events captured: {len(event_callback.events)}")
    for et, data in event_callback.events:
        if et == "tool_call":
            print(f"  Tool call: {data.get('name')}")
    assert isinstance(result, dict)
    assert "summary" in result
    assert len(result["summary"]) > 0
    print(f"Summary length: {len(result['summary'])} chars")


@pytest.mark.asyncio
async def test_kb_agent_discover_mode(event_callback):
    """KB Agent 发现模式（空 project_id）"""
    from src.ops_agent.sub_agents.kb_agent import run_kb_agent

    result = await run_kb_agent(description=QUERY, project_id="", event_callback=event_callback)
    assert isinstance(result, dict)
    assert "project_id" in result
