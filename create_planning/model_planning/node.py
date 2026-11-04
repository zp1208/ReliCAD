import json
import logging
from typing import TYPE_CHECKING

from create_planning.model_planning.skills.plan_builder import build_plan
from debug.state_debugger import debug_snapshot

if TYPE_CHECKING:
    from common.messages.state import CADState

logger = logging.getLogger("CAD_Agent.planning")


def _build_replan_spec(state: "CADState") -> str:
    """Combine the original spec with error feedback for replanning."""
    intent_understanding = state.get("intent_understanding", {})
    previous_plan = str(state.get("plan") or "").strip()
    error_info = str(state.get("error_info") or "").strip()
    error_analysis_result = str(state.get("error_analysis_result") or "").strip()

    lines = [
        "Structured_Requirement:",
        json.dumps(intent_understanding, ensure_ascii=False, indent=2),
    ]
    if previous_plan:
        lines += ["", "PREVIOUS_PLAN:", previous_plan]
    if error_info:
        lines += ["", "ERROR_INFO:", error_info]
    if error_analysis_result:
        lines += ["", "ERROR_ANALYSIS:", error_analysis_result]
    return "\n".join(lines).strip()


@debug_snapshot("planning")
def planning_node(state: "CADState"):
    logger.info("--- 运行中: 模型规划节点 ---")

    intent_understanding = state.get("intent_understanding", {})
    is_replan = state.get("correction_mode", False)

    if is_replan:
        logger.info("规划: 检测到 replan")
        spec_input = _build_replan_spec(state)
    else:
        logger.info("规划: 首次规划")
        spec_input = "Structured_Requirement:\n" + json.dumps(intent_understanding, ensure_ascii=False, indent=2)

    final_content = build_plan(spec_content=spec_input, is_replan=is_replan)
    logger.info("规划: 完成，规划结果=\n%s", final_content)

    return {
        "correction_mode": False,
        "plan": final_content,
    }
