import json
import logging
import os
import re
from functools import lru_cache

from openai import OpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger("CAD_Agent.LLM")

DEFAULT_BASE_URL = "https://api.nexrouter.ai/v1"
# API 密钥仅从环境变量读取，避免进入源码和 Git 历史。
DEFAULT_API_KEY = os.environ.get("CAD_AGENT_API_KEY", "")





def parse_llm_json(raw: str):
    """清理 LLM 返回文本，并解析其中的 JSON 对象。"""
    # 清理 markdown 代码块包装，兼容 ```json ... ``` 格式。
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    # 清理模型可能输出的 XML/思考标签，避免干扰 JSON 解析。
    raw = re.sub(r"<[^>]+>.*?</[^>]+>", "", raw, flags=re.DOTALL).strip()

    # 提取 JSON 对象片段，兼容前后带说明文本的 LLM 输出。
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(0).strip()

    return json.loads(raw)



def _collect_text_fragments(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        fragments = []
        for item in value:
            fragments.extend(_collect_text_fragments(item))
        return fragments
    if isinstance(value, dict):
        text_value = value.get("text")
        if isinstance(text_value, str) and text_value:
            return [text_value]

        for nested_key in ("content", "output"):
            nested_value = value.get(nested_key)
            if nested_value is not None:
                nested_fragments = _collect_text_fragments(nested_value)
                if nested_fragments:
                    return nested_fragments
    return []


def _coerce_llm_text(response) -> str:
    """Extract assistant text from strings, AIMessage objects, or raw response payloads."""
    if response is None:
        return ""
    if isinstance(response, str):
        return response

    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text
    if text is not None and type(text).__name__ == "TextAccessor":
        text_value = str(text)
        if text_value:
            return text_value

    content = getattr(response, "content", None)
    fragments = _collect_text_fragments(content)
    if fragments:
        return "\n".join(fragments)

    fragments = _collect_text_fragments(response)
    if fragments:
        return "\n".join(fragments)

    return str(content if content is not None else response)


@lru_cache(maxsize=16)
def _build_client(base_url: str, api_key: str) -> OpenAI:
    if not api_key:
        raise ValueError("请设置 CAD_AGENT_API_KEY 环境变量，勿将 API 密钥写入源码。")
    return OpenAI(api_key=api_key, base_url=base_url)


# 可重试的异常类型：网络错误、超时、服务端错误
from openai import APIConnectionError, APITimeoutError, RateLimitError, APIStatusError

_RETRYABLE_EXCEPTIONS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIStatusError,
    ConnectionError,
    TimeoutError,
)


def _convert_messages(messages) -> list[dict]:
    """将 langchain Message 对象或 dict 列表统一转为 OpenAI 格式。"""
    result = []
    for msg in messages:
        if isinstance(msg, dict):
            result.append(msg)
        elif isinstance(msg, SystemMessage):
            result.append({"role": "system", "content": msg.content})
        elif isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"role": "assistant", "content": msg.content})
        else:
            # 兜底：尝试取 role/content 属性
            role = getattr(msg, "type", "user")
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            result.append({"role": role, "content": getattr(msg, "content", str(msg))})
    return result


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def invoke_llm(
    messages,
    *,
    llm=None,
    model: str = "gpt-5.5",
    temperature: float = 0.0,
) -> str:
    """Invoke the configured gateway and return only normalized assistant text.

    Retries up to 3 times on transient network/server errors with exponential backoff.
    Also retries if the LLM returns an empty response.
    """
    if llm is not None:
        # 兼容旧调用方式：如果传入的是 langchain ChatOpenAI 对象，走旧路径
        response = llm.invoke(messages)
        return _coerce_llm_text(response)

    client = _build_client(DEFAULT_BASE_URL, DEFAULT_API_KEY)

    openai_messages = _convert_messages(messages)
    response = client.chat.completions.create(
        model=model,
        messages=openai_messages,
        temperature=temperature,
    )

    result = response.choices[0].message.content or ""

    # 检查空响应，触发重试
    if not result.strip():
        logger.warning("LLM returned empty response, will retry...")
        # 抛出 APIStatusError 触发重试机制
        raise APIStatusError(
            message="LLM returned empty response",
            response=None,
            body=None,
        )

    return result
