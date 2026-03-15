from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.agent.prompts.summarize import SUMMARIZE_SYSTEM_PROMPT
from src.agent.state import OpsState
from src.config import get_settings


async def summarize_node(state: OpsState) -> dict:
    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
    )

    messages = [
        SystemMessage(content=SUMMARIZE_SYSTEM_PROMPT),
        HumanMessage(
            content=f"请根据以下对话历史生成排查报告：\n\n事件标题: {state['title']}\n事件描述: {state['description']}\n\n"
            + "\n".join(str(m) for m in state["messages"][-20:])
        ),
    ]

    response = await llm.ainvoke(messages)

    return {
        "summary_md": response.content,
        "is_complete": True,
    }
