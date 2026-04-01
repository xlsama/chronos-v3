"""共享 LLM 工具函数 —— 消除各 Agent 节点中重复的 LLM 调用、响应清理、多模态处理。"""

import base64

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.env import get_settings
from src.lib.logger import get_logger

_RETRYABLE_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    OSError,
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
)


def create_llm(model: str = "main", streaming: bool = True) -> ChatOpenAI:
    """创建 ChatOpenAI 实例。

    model: "main" 用 settings.main_model, "mini" 用 settings.mini_model。
    """
    s = get_settings()
    model_name = s.main_model if model == "main" else s.mini_model
    return ChatOpenAI(
        model=model_name,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=streaming,
    )


def _make_retry_logger(component: str):
    """创建用于 tenacity before_sleep 的日志回调。"""

    def _log(retry_state):
        get_logger(component=component).warning(
            "LLM call failed, retrying",
            attempt=retry_state.attempt_number,
            error=str(retry_state.outcome.exception()),
        )

    return _log


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    before_sleep=_make_retry_logger("llm"),
)
async def invoke_with_retry(llm, messages) -> AIMessage:
    """带指数退避重试的 LLM 调用。"""
    return await llm.ainvoke(messages)


def sanitize_response(
    response: AIMessage,
    valid_tool_names: set[str],
    component: str = "llm",
) -> AIMessage:
    """清除 LLM 响应中幻觉的工具调用。"""
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    unknown = [tc for tc in tool_calls if str(tc.get("name", "")).strip() not in valid_tool_names]
    if not unknown:
        return response
    get_logger(component=component).warning(
        "Stripping unknown tool calls",
        tools=[tc.get("name") for tc in unknown],
    )
    return AIMessage(content=response.content or "")


# ═══════════════════════════════════════════
# 多模态辅助
# ═══════════════════════════════════════════


def parse_resume(user_response) -> tuple[str, list[dict]]:
    """从 LangGraph resume 值中提取文本和可选图片。

    resume 可以是:
    - str: 纯文本
    - dict: {"text": "...", "images": [{"filename", "bytes", "content_type"}]}
    """
    if isinstance(user_response, dict) and "text" in user_response:
        text = user_response["text"]
        images = user_response.get("images") or []
        return text, images
    return str(user_response), []


def build_multimodal_content(text: str, images: list[dict]) -> list[dict]:
    """构建 LangChain 多模态内容块。"""
    blocks: list[dict] = [{"type": "text", "text": text}]
    for img in images[:5]:
        b64 = base64.b64encode(img["bytes"]).decode()
        mime = img.get("content_type") or "image/png"
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )
    return blocks
