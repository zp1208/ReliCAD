import json
import logging
from typing import TYPE_CHECKING

# from create_planning.checklist_generation import generate_checklist  # DISABLED: checklist temporarily skipped
from create_planning.requirements_clarification.skills.ambiguity_resolver import resolve_ambiguity
from create_planning.requirements_clarification.skills.intent_extraction import extract_intent
from debug.state_debugger import debug_snapshot

if TYPE_CHECKING:
    from common.messages.state import CADState

logger = logging.getLogger("CAD_Agent.ingest")



@debug_snapshot("ingest")
def ingest_input(state: "CADState") -> dict:
    # Prefer the typed field; fall back to last message for backward compatibility.
    user_input = state.get("user_request")
    logger.info("需求提取: 收到用户输入: %s", user_input)

    logger.info("需求提取: 第一步 - 提取用户意图")
    intent = extract_intent(user_input)
    logger.info("需求提取: 意图理解结果=\n%s", json.dumps(intent, indent=2, ensure_ascii=False))

    logger.info("需求提取: 第二步 - 解决歧义")
    specification = resolve_ambiguity(intent)

    return {
        "correction_mode": False,
        "intent_understanding": specification,
    }
