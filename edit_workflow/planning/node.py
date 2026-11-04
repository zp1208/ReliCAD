import logging
from typing import TYPE_CHECKING

from edit_workflow.planning.skills.plan_delta_builder import build_plan_delta

if TYPE_CHECKING:
    from common.messages.state import CADState

logger = logging.getLogger("CAD_Agent.edit_planning")


def edit_planning_node(state: "CADState") -> dict:
    logger.info("--- 运行中: 编辑规划节点 ---")
    # intent_delta = state.get("intent_delta") or {}
    edit_command = state.get("edit_command", "")
    previous_code = state.get("previous_code", "")

    error_kwargs = {}
    if state.get("is_edit_mode"):
        error_kwargs = {
            "error_info": state.get("error_info"),
            "error_analysis_result": state.get("error_analysis_result"),
        }

    plan_delta = build_plan_delta(edit_command, previous_code, **error_kwargs)
    logger.info("编辑规划: 产出 %d 个修改步骤", len(plan_delta.get("steps", [])))
    return {"plan_delta": plan_delta, "correction_mode": False}
