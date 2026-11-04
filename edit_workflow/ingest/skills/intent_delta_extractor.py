import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from common.LLM import invoke_llm
from common.units import (
    ANGLE_UNITS_TO_DEG,
    LENGTH_UNITS_TO_MM,
    extract_numeric_with_unit,
    normalize_parameter_value,
)

logger = logging.getLogger("CAD_Agent.edit_ingest")

_SYSTEM_PROMPT = """
你是 CAD 编辑意图分析器。分析用户编辑指令，输出结构化 JSON。

输出格式（严格 JSON，不加解释）：
{
  "changes": [
    {"target": "feature.parameter", "operation": "set|add|remove|scale", "value": "原始值（原样输出，含单位）"}
  ],
  "topology_change": false,
  "description": "一句话描述"
}

约束：topology_change=true 仅当增删特征；单位由调用方规范化，此处原样输出。
""".strip()


def _normalize_value(value: str) -> "float | str":
    """规范化为数值（长度→mm，角度→deg）；无法识别单位则原样返回。"""
    _, unit = extract_numeric_with_unit(value)
    normalized = normalize_parameter_value(value)
    if not isinstance(normalized, float):
        return value
    if unit in LENGTH_UNITS_TO_MM:
        return normalized
    if unit in ANGLE_UNITS_TO_DEG:
        return normalized
    return value


def _normalize_changes(intent_delta: dict) -> dict:
    """对 changes[].value 做代码层单位规范化（set/add 操作才转换）。"""
    for change in intent_delta.get("changes", []):
        op = change.get("operation", "set")
        if op not in ("remove", "scale") and change.get("value") is not None:
            change["value"] = _normalize_value(str(change["value"]))
    return intent_delta


def extract_intent_delta(edit_command: str, previous_code: str) -> dict:
    code_snippet = "\n".join(previous_code.splitlines()[:80])
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"EDIT_COMMAND:\n{edit_command}\n\nEXISTING_CODE (excerpt):\n{code_snippet}"),
    ]
    raw = invoke_llm(messages, temperature=0)
    return _normalize_changes(_parse_json(raw))


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.warning("edit_ingest: 无法解析 LLM 输出为 JSON，返回空结构")
    return {"changes": [], "topology_change": False, "description": ""}
