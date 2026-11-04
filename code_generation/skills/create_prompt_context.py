import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common.messages.state import CADState


MD_DOC_PATH = Path(__file__).resolve().parents[2] / "fusion360" / "docs" / "tool_spec.md"
PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "prompts" / "code_generation_protocol.txt"
STRICT_RULES_PATH = Path(__file__).resolve().parents[1] / "prompts" / "strict_code_rules.txt"

with open(MD_DOC_PATH, "r", encoding="utf-8") as file_obj:
    API_CONTEXT = file_obj.read()
_PROTOCOL = PROTOCOL_PATH.read_text(encoding="utf-8").strip()
_STRICT_RULES = STRICT_RULES_PATH.read_text(encoding="utf-8").strip()

def build_system_prompt(state: "CADState") -> str:
    """根据 correction_mode 调度 repair 或 execution system prompt。"""
    correction_mode = state.get("correction_mode", False)
    if correction_mode:
        return build_repair_system_prompt(API_CONTEXT)
    return build_execution_system_prompt(API_CONTEXT)


def build_execution_system_prompt(api_context: str) -> str:
    return f"""
You are a constrained code generation agent.
You will receive a structured requirement specification and an ordered modeling plan.
Your only task is to output executable code using only the provided API reference.
Output the complete script wrapped in a single ```python fenced code block.

CORE API REFERENCE:
{api_context}

{_PROTOCOL}

{_STRICT_RULES}
""".strip()


def build_repair_system_prompt(api_context: str) -> str:
    return f"""
You are a constrained code-repair agent.
You will receive a failed script and its error detail.
Your only task is to diagnose the failure and output the corrected executable code using only the provided API reference.

CORE API REFERENCE:
{api_context}

REPAIR PROTOCOL — follow this procedure to fix the failed script:

  STEP 1 — DIAGNOSE
    Read ERROR_INFO and ERROR_ANALYSIS carefully:
      - ERROR_INFO: describes what went wrong and where (from execution or validation)
      - ERROR_ANALYSIS: the root-cause diagnosis and suggested fix direction
      - Use both to understand WHY the code failed, then locate the corresponding section in FAILED_CODE

  STEP 2 — LOCATE AND FIX
    Find the failing section in FAILED_CODE and apply the minimal change
    needed to resolve the error. Preserve all correct sections unchanged.

  STEP 3 — OUTPUT
    Output the COMPLETE corrected script — the entire program, not just the changed lines.
    Change only the code necessary to resolve the error; preserve everything else unchanged.
    Wrap the full script in a single ```python fenced code block.

{_STRICT_RULES}
""".strip()


def _append_context_section(parts, title: str, body: str):
    if not body:
        return
    parts.append(f"{title}:\n{body.strip()}")


def build_execution_prompt_context(state: "CADState") -> str:
    """Build the human-turn prompt for create/repair mode."""
    correction_mode = state.get("correction_mode", False)
    user_request = state.get("user_request", "")
    normalized_spec = json.dumps(state.get("intent_understanding", {}), ensure_ascii=False, indent=2)
    plan = state.get("plan")
    modeling_plan = plan if plan is not None else ""

    if correction_mode:
        task_directive = "Fix the previous executable CAD script. Preserve the established modeling intent and change only the code required to resolve the reported failure."
    else:
        task_directive = "Generate the initial executable Fusion 360 API calls from the compiled requirement and plan."

    parts = [
        f"TASK_DIRECTIVE:\n{task_directive}",
    ]
    _append_context_section(parts, "USER_REQUEST", user_request)
    _append_context_section(parts, "NORMALIZED_SPEC", normalized_spec)
    _append_context_section(parts, "MODELING_PLAN", modeling_plan)

    if correction_mode:
        failed_code = state.get("execution_response_text", "")
        error_info = state.get("error_info", "")
        error_analysis = state.get("error_analysis_result", "")
        _append_context_section(parts, "FAILED_CODE", failed_code)
        _append_context_section(parts, "ERROR_INFO", error_info)
        _append_context_section(parts, "ERROR_ANALYSIS", error_analysis)

    return "\n\n".join(parts).strip()
