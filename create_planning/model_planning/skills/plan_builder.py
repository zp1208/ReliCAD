import re
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage
from common.LLM import invoke_llm

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "planning_prompt.txt"
_REPLAN_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "replan_prompt.txt"


def _load_prompt(is_replan: bool = False) -> str:
    path = _REPLAN_PROMPT_PATH if is_replan else _PROMPT_PATH
    return path.read_text(encoding="utf-8")


def _extract_steps(raw_text: str) -> list[str]:
    if not raw_text:
        return []

    text = raw_text.replace("```", "").strip()
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    # 尝试提取编号列表，缩进续行合并到上一个步骤
    numbered = []
    for line in lines:
        match = re.match(r"^\s*(\d+)[\.)]\s*(.+)$", line)
        if match:
            numbered.append(match.group(2).strip())
        elif numbered and line.startswith((" ", "\t")):
            numbered[-1] += " " + line.strip()
        # 非编号且非缩进的行（废话）直接丢弃
    if numbered:
        return numbered

    # 尝试提取 bullet 列表，缩进续行合并
    bullets = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ")):
            bullets.append(stripped[2:].strip())
        elif bullets and line.startswith((" ", "\t")):
            bullets[-1] += " " + stripped

    return bullets if bullets else [line.strip() for line in lines]


def _format_numbered_steps(steps: list[str]) -> str:
    cleaned = [s for s in (step.strip() for step in steps) if s]
    return "\n".join(f"{idx}. {step}" for idx, step in enumerate(cleaned, 1))


def build_plan(spec_content: str, is_replan: bool = False, llm=None) -> str:
    messages = [
        SystemMessage(content=_load_prompt(is_replan)),
        HumanMessage(content=spec_content),
    ]
    steps = _extract_steps(invoke_llm(messages, llm=llm, temperature=0))
    if not steps:
        raise ValueError("planning LLM did not return any executable planning steps")
    return _format_numbered_steps(steps)
