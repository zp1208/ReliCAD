import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from common.LLM import invoke_llm, parse_llm_json
from debug.state_debugger import debug_snapshot

if TYPE_CHECKING:
    from common.messages.state import CADState

logger = logging.getLogger("CAD_Agent.error_analysis")

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "error_analysis_prompt.txt").read_text(encoding="utf-8").strip()
_EDIT_MODE_SYSTEM_PROMPT = (
    Path(__file__).parent / "prompts" / "edit_mode_error_analysis_prompt.txt"
).read_text(encoding="utf-8").strip()

_VALID_ROUTES = {"ingest", "planning", "executable", "fatal"}
_EDIT_MODE_VALID_ROUTES = {"planning", "executable"}


def _format_recent_error_history(state: "CADState") -> str:
    error_history = state.get("error_history") or []
    recent_history = error_history[-2:]
    if not recent_history:
        return ""
    return json.dumps(recent_history, ensure_ascii=False, indent=2)


def _build_user_message(state: "CADState") -> str:
    parts = []
    intent = state.get("intent_understanding")
    if intent:
        parts.append("USER_INTENT:\n" + json.dumps(intent, ensure_ascii=False, indent=2))
    plan = state.get("plan")
    if plan:
        parts.append("MODELING_PLAN:\n" + plan.strip())
    code = state.get("execution_response_text")
    if code:
        parts.append("FAILED_CODE:\n" + code.strip())
    evidence = state.get("execution_evidence")
    if evidence:
        parts.append("RUNTIME_EVIDENCE:\n" + json.dumps(evidence, ensure_ascii=False, indent=2))
    recent_history = _format_recent_error_history(state)
    if recent_history:
        parts.append("RECENT_ERROR_HISTORY:\n" + recent_history)
    error = state.get("error_info")
    if error:
        parts.append("ERROR_INFO:\n" + error.strip())
    return "\n\n".join(parts)


def _format_context_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value).strip()


def _build_edit_mode_user_message(state: "CADState") -> str:
    # 编辑模式只传编辑链路上下文，避免把创建模式的 intent/plan 误导给错误分析。
    parts = []
    edit_command = state.get("edit_command")
    if edit_command:
        parts.append("EDIT_COMMAND:\n" + _format_context_value(edit_command))
    previous_code = state.get("previous_code")
    if previous_code:
        parts.append("PREVIOUS_CODE:\n" + _format_context_value(previous_code))
    plan_delta = state.get("plan_delta")
    if plan_delta:
        parts.append("PLAN_DELTA:\n" + _format_context_value(plan_delta))
    code = state.get("execution_response_text")
    if code:
        parts.append("FAILED_CODE:\n" + _format_context_value(code))
    evidence = state.get("execution_evidence")
    if evidence:
        parts.append("RUNTIME_EVIDENCE:\n" + _format_context_value(evidence))
    recent_history = _format_recent_error_history(state)
    if recent_history:
        parts.append("RECENT_ERROR_HISTORY:\n" + recent_history)
    error = state.get("error_info")
    if error:
        parts.append("ERROR_INFO:\n" + _format_context_value(error))
    return "\n\n".join(parts)


_MAX_FAILURES = 4  # 累计失败次数上限，达到后强制 fatal


@debug_snapshot("error_analysis")
def error_analysis_node(state: "CADState") -> dict:
    logger.info("--- 运行中: 错误分析节点 ---")

    # 递增 failure_count
    failure_count = (state.get("failure_count") or 0) + 1
    logger.info("错误分析: failure_count=%d / %d", failure_count, _MAX_FAILURES)

    # 达到上限，强制 fatal
    if failure_count >= _MAX_FAILURES:
        logger.error("错误分析: 累计失败 %d 次，强制终止工作流", failure_count)
        analysis = f"已连续失败 {failure_count} 次，超过最大重试上限，强制终止。"
        error_history = list(state.get("error_history") or [])
        error_history.append({
            "error_info": str(state.get("error_info") or "").strip(),
            "analysis": analysis,
            "route": "fatal",
        })

        # 保存失败标志文件
        save_dir = state.get("save_dir")
        result_file = os.path.join(save_dir, "result.txt")
        with open(result_file, "w", encoding="utf-8") as f:
            f.write("fail")
        logger.info("错误分析: 失败标志已保存至 %s", result_file)

        return {
            "failure_count": failure_count,
            "error_analysis_result": analysis,
            "error_analysis_route": "fatal",
            "error_history": error_history,
        }

    is_edit_mode = bool(state.get("is_edit_mode"))
    valid_routes = _EDIT_MODE_VALID_ROUTES if is_edit_mode else _VALID_ROUTES
    system_prompt = _EDIT_MODE_SYSTEM_PROMPT if is_edit_mode else _SYSTEM_PROMPT
    user_message = _build_edit_mode_user_message(state) if is_edit_mode else _build_user_message(state)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    raw = invoke_llm(messages)
    logger.debug("错误分析原始输出: %s", raw)

    try:
        result = parse_llm_json(raw)
        analysis = str(result.get("analysis", "")).strip()
        route = str(result.get("route", "executable")).strip()
    except (json.JSONDecodeError, AttributeError):
        logger.warning("错误分析输出解析失败，原始内容: %s", raw)
        analysis = raw.strip()
        route = "executable"
    if route not in valid_routes:
        logger.warning("无效路由值 '%s'，回退到 'executable'", route)
        route = "executable"
    logger.warning("错误分析完成: route=%s | analysis=%s", route, analysis)
    error_history = list(state.get("error_history") or [])
    error_history.append({
        "error_info": str(state.get("error_info") or "").strip(),
        "analysis": analysis,
        "route": route,
    })
    return {
        "failure_count": failure_count,
        "error_analysis_result": analysis,
        "error_analysis_route": route,
        "error_history": error_history,
    }
