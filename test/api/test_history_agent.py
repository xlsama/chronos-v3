"""History Sub-Agent 完整流程测试"""

import pytest

pytestmark = pytest.mark.api
QUERY = "数据库连接池耗尽"


@pytest.mark.asyncio
async def test_history_agent(event_callback):
    """History Agent 返回字符串结果"""
    from src.ops_agent.sub_agents.history_agent import run_history_agent

    print(f"Query: {QUERY}")
    result = await run_history_agent(description=QUERY, event_callback=event_callback)
    print(f"Result length: {len(result)} chars")
    print(f"Events captured: {len(event_callback.events)}")
    for et, data in event_callback.events:
        if et == "tool_call":
            print(f"  Tool call: {data.get('name')}")
    assert isinstance(result, str)
    assert len(result) > 0
    print(f"Result preview: {result[:200]}")
