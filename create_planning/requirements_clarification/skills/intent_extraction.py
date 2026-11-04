"""
Intent Extraction Skill - 从用户自然语言输入中提取结构化CAD意图
"""
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage
from common.LLM import invoke_llm, parse_llm_json
from common.units import normalize_intent_units
from create_planning.requirements_clarification.schemas.cad_intent import CADIntent, CADParameter

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "intent_prompt.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def extract_intent(user_input: str):
    """从用户输入中提取结构化CAD意图。"""


    system_prompt = _load_prompt()

    raw = invoke_llm([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ], temperature=0).strip()

    return parse_llm_json(raw)
