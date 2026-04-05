"""意图分类节点 —— 用 mini_model 快速判断用户输入是 incident/question/task。"""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.state import MainState

INTENT_CLASSIFY_PROMPT = """\
你是运维系统的意图分类器。根据用户输入判断类型：
- "incident": 故障报告、错误告警、服务异常、性能问题、系统宕机（需要假设驱动排查）
- "question": 知识咨询、操作指南、配置查询、概念解释（需要直接回答）
- "task": 明确的执行任务如"重启 X 服务"、"查看 X 状态"（需要直接操作）

只输出 JSON，不要输出其他内容: {"intent": "incident"} 或 {"intent": "question"} 或 {"intent": "task"}"""


def _log_retry(retry_state):
    get_logger(component="intent_classify").warning(
        "Intent classify LLM failed, retrying",
        attempt=retry_state.attempt_number,
        error=str(retry_state.outcome.exception()),
    )


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(
        (
            TimeoutError,
            ConnectionError,
            OSError,
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
        )
    ),
    before_sleep=_log_retry,
)
async def _classify_intent(llm, messages) -> str:
    response = await llm.ainvoke(messages)
    content = response.content if hasattr(response, "content") else ""
    # 解析 JSON
    try:
        data = json.loads(content.strip())
        intent = data.get("intent", "incident")
        if intent in ("incident", "question", "task"):
            return intent
    except (json.JSONDecodeError, AttributeError):
        pass
    # fallback: 从文本中提取
    content_lower = content.lower()
    if '"question"' in content_lower:
        return "question"
    if '"task"' in content_lower:
        return "task"
    return "incident"


async def intent_classify_node(state: MainState) -> dict:
    """用 mini_model 快速分类用户意图。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="intent_classify", sid=sid)

    s = get_settings()
    llm = ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=False,
        extra_body={"enable_thinking": False},
    )

    messages = [
        SystemMessage(content=INTENT_CLASSIFY_PROMPT),
        HumanMessage(content=state["description"]),
    ]

    try:
        intent = await _classify_intent(llm, messages)
    except Exception as e:
        log.warning("Intent classification failed, defaulting to incident", error=str(e))
        intent = "incident"

    log.info("Intent classified", intent=intent)
    return {"intent": intent}
