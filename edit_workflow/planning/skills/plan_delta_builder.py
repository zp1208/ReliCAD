import json
import logging
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from common.LLM import invoke_llm, parse_llm_json

logger = logging.getLogger("CAD_Agent.edit_planning")

_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
_SYSTEM_PROMPT = (_PROMPT_DIR / "plan_delta_builder_system_prompt.txt").read_text(
    encoding="utf-8"
).strip()
_REPLAN_SYSTEM_PROMPT = (_PROMPT_DIR / "plan_delta_replan_system_prompt.txt").read_text(
    encoding="utf-8"
).strip()


def build_plan_delta(
    edit_command: str,
    previous_code: str,
    *,
    error_info: str | None = None,
    error_analysis_result: str | None = None,
) -> dict:
    user_parts = [f"USER_INPUT: {edit_command}"]
    if error_info:
        user_parts.append("ERROR_INFO:\n" + error_info.strip())
    if error_analysis_result:
        user_parts.append("ERROR_ANALYSIS_RESULT:\n" + error_analysis_result.strip())
    user_parts.append("EXISTING_CODE:\n" + previous_code)
    system_prompt = _REPLAN_SYSTEM_PROMPT if error_info or error_analysis_result else _SYSTEM_PROMPT

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="\n\n".join(user_parts)),
    ]
    raw = invoke_llm(messages, temperature=0)
    return parse_llm_json(raw)
