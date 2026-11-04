import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from common.LLM import invoke_llm
from create_planning.checklist_generation.skills.primitives import _coerce_text


_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "checklist_prompt.txt"


def _load_prompt() -> str:
    """Load the checklist candidate prompt from disk."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _param_to_dict(param):
    """Serialize an intent parameter object into a JSON-safe dictionary."""
    return {
        "value": getattr(param, "value", None),
        "description": _coerce_text(getattr(param, "description", "")),
        "source": _coerce_text(getattr(param, "source", "")),
        "confidence": getattr(param, "confidence", None),
    }


def _intent_to_dict(intent):
    """Serialize structured intent for the checklist candidate LLM prompt."""
    if intent is None:
        return {}

    payload = {
        "component_type": _coerce_text(getattr(intent, "component_type", "")),
        "operation": _coerce_text(getattr(intent, "operation", "")),
        "raw_input": _coerce_text(getattr(intent, "raw_input", "")),
    }

    for field in ("explicit_params", "inferred_params", "default_params"):
        raw = getattr(intent, field, {}) or {}
        if isinstance(raw, dict):
            payload[field] = {str(key): _param_to_dict(param) for key, param in raw.items()}
        else:
            payload[field] = {}
    return payload


def _parse_json_payload(raw_text: str):
    """Parse the LLM response into the candidate checklist array."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    payload = json.loads(cleaned.strip())
    if isinstance(payload, dict) and isinstance(payload.get("checks"), list):
        return payload["checks"]
    if isinstance(payload, list):
        return payload
    raise ValueError("LLM checklist payload must be a list or {'checks': [...]} object")


def generate_candidate_checks(*, intent, decision, user_input: str = ""):
    """Ask the LLM for checklist candidates derived from structured intent."""
    system_prompt = _load_prompt()
    prompt_payload = {
        "user_input": _coerce_text(user_input),
        "intent": _intent_to_dict(intent),
        "decision": decision or {},
    }
    response_text = invoke_llm(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(prompt_payload, ensure_ascii=False, indent=2)),
        ],
        temperature=0,
    )
    return _parse_json_payload(response_text)
