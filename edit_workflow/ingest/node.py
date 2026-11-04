import logging
from typing import TYPE_CHECKING

from edit_workflow.ingest.skills.intent_delta_extractor import extract_intent_delta

if TYPE_CHECKING:
    from common.messages.state import CADState

logger = logging.getLogger("CAD_Agent.edit_ingest")


def edit_ingest_node(state: "CADState") -> dict:
    logger.info("--- 运行中: 编辑意图提取节点 ---")
    edit_command = state.get("edit_command", "")
    previous_code = state.get("previous_code", "")
    logger.info("编辑意图提取: 指令=%s", edit_command)

    intent_delta = extract_intent_delta(edit_command, previous_code)
    logger.info(
        "编辑意图提取: topology_change=%s changes=%d 项",
        intent_delta.get("topology_change"),
        len(intent_delta.get("changes", [])),
    )
    return {"intent_delta": intent_delta}
