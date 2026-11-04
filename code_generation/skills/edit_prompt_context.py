import json as _json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common.messages.state import CADState


STRICT_RULES_PATH = Path(__file__).resolve().parents[1] / "prompts" / "strict_code_rules.txt"
_STRICT_RULES = STRICT_RULES_PATH.read_text(encoding="utf-8").strip()


def build_edit_system_prompt(api_context: str, *, correction_mode: bool = False) -> str:
    if correction_mode:
        return build_edit_repair_system_prompt(api_context)
    return f"""
You are a constrained code-edit agent.
You will receive editing commands, a structured modification plan, and the code requiring edits.
Your only task is to output the edited code using only the provided API reference.

CORE API REFERENCE:
{api_context}

EDIT PROTOCOL — follow this procedure to apply targeted changes:

  STEP 1 — READ THE PLAN
    MODIFICATION_PLAN contains a list of steps. Each step has:
      - action: "modify" | "add" | "delete"
      - target_code: the exact lines to locate in EXISTING_CODE
      - instruction: what change to apply

  STEP 2 — APPLY EACH STEP
    For each step in MODIFICATION_PLAN:
      - Apply the instruction

  STEP 3 — OUTPUT COMPLETE CODE
    Output the full modified script.
    All code not mentioned in MODIFICATION_PLAN MUST remain unchanged.

{_STRICT_RULES}
""".strip()


def build_edit_repair_system_prompt(api_context: str) -> str:
    return f"""
You are a constrained code-repair agent for CAD edit mode.
You will receive the original edit request, the modification plan, the original code, the failed edited code, and the failure diagnosis.
Your only task is to output the corrected edited code using only the provided API reference.

CORE API REFERENCE:
{api_context}

EDIT REPAIR PROTOCOL - follow this procedure:

  STEP 1 - DIAGNOSE
    Read ERROR_INFO and ERROR_ANALYSIS carefully:
      - ERROR_INFO: describes what went wrong and where
      - ERROR_ANALYSIS: the root-cause diagnosis and suggested fix direction
      - Use EDIT_COMMAND and MODIFICATION_PLAN to preserve the intended edit
      - Use EXISTING_CODE as the original working baseline
      - Use FAILED_CODE as the code version that must be repaired

  STEP 2 - REPAIR
    Fix FAILED_CODE with the minimal change needed to satisfy EDIT_COMMAND and resolve ERROR_INFO.
    Preserve correct edited logic from FAILED_CODE. Do not restart from scratch unless the failed code is unusable.

  STEP 3 - OUTPUT COMPLETE CODE
    Output the full corrected script.

{_STRICT_RULES}
""".strip()


def _append(parts, title: str, body: str):
    if not body:
        return
    parts.append(f"{title}:\n{body.strip()}")


def build_edit_prompt_context(state: "CADState") -> str:
    correction_mode = state.get("correction_mode", False)
    task_directive = (
        "Repair the failed edited code. Preserve the requested edit and change only the code required to resolve the reported failure."
        if correction_mode
        else "Apply targeted changes to the existing code based on the modification plan. Preserve all unchanged logic."
    )
    parts = [
        f"TASK_DIRECTIVE:\n{task_directive}",
    ]
    _append(parts, "EDIT_COMMAND",      state.get("edit_command", ""))
    _append(parts, "MODIFICATION_PLAN", _json.dumps(state.get("plan_delta") or {}, ensure_ascii=False, indent=2))
    _append(parts, "EXISTING_CODE",     state.get("previous_code", ""))
    if correction_mode:
        _append(parts, "FAILED_CODE", state.get("execution_response_text", ""))
        _append(parts, "ERROR_INFO", state.get("error_info", ""))
        _append(parts, "ERROR_ANALYSIS", state.get("error_analysis_result", ""))
    return "\n\n".join(parts).strip()
