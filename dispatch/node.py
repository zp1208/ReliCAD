"""
dispatch — 会话锚点节点。

职责：
  首轮·创建模式：读 user_request（已在 state），设 is_edit_mode=False，路由 → ingest_input
  首轮·编辑模式：读 source_code_path_input + edit_command，提取文件代码 → previous_code，
                设 is_edit_mode=True，路由 → executable
  后续轮次：① 快照本轮产出 → previous_*；
            ② 清空当轮产出字段（plan/execution_* 等置 None，failure_count 重置）；
            ③ interrupt() 等待用户指令；
            ④ 有 previous_code → 编辑模式（接收 edit_command）；
               无 previous_code（上轮失败）→ 回退创建模式（接收 user_request）
"""
from __future__ import annotations

import logging
import os
import textwrap

from langgraph.types import interrupt

from common.messages.state import CADState

logger = logging.getLogger("CAD_Agent.dispatch")

_SENTINEL_START = 'print("Sending atomic commands to Fusion 360...")'
_SENTINEL_END = "step_path"


def _extract_previous_code(file_path: str) -> str:
    """
    从 fusion_generated.py 中提取核心 API 调用段：
      - 开始：_SENTINEL_START 所在行的下一行
      - 结束：包含 _SENTINEL_END 的行（不含）
      - 过滤：移除所有包含 auto_close_loop 的行
      - 归一化：移除 wrapper 中的共同缩进，保留代码块内部相对缩进
    """
    abs_path = os.path.abspath(file_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"source_code_path 指向的文件不存在: {abs_path}")

    with open(abs_path, encoding="utf-8") as f:
        lines = f.readlines()

    capturing = False
    extracted: list[str] = []

    for line in lines:
        stripped = line.rstrip("\n")

        if not capturing:
            if _SENTINEL_START in stripped:
                capturing = True
            continue

        if _SENTINEL_END in stripped:
            break

        if "auto_close_loop" in stripped:
            continue

        extracted.append(stripped)

    if not extracted:
        raise ValueError(
            f"未能从文件中提取到有效的 API 调用段，请检查文件格式: {abs_path}"
        )

    return textwrap.dedent("\n".join(extracted)).strip("\n")


def _take_snapshot(state: CADState) -> dict:
    """
    将本轮产出复制到 previous_* 字段，供下一轮编辑时参考。
    在后续轮次 interrupt() 前调用。
    """
    snapshot = {}

    if state.get("plan"):
        snapshot["previous_plan"] = state["plan"]

    if state.get("intent_understanding"):
        snapshot["previous_intent"] = state["intent_understanding"]

    if state.get("execution_response_text"):
        snapshot["previous_code"] = state["execution_response_text"]

    return snapshot


def _build_clear_dict() -> dict:
    """清空当轮产出字段（成功轮次使用，保留 previous_*）。"""
    return {
        "intent_understanding": None,
        "plan": None,
        "last_execution": None,
        "execution_response_text": None,
        "execution_code_path": None,
        "execution_step_path": None,
        "failure_count": 0,             # 重置重试计数
        "error_info": None,
        "error_analysis_result": None,
        "error_analysis_route": None,
        "error_history": [],
        "intent_delta": None,
        "plan_delta": None,
    }


def _build_full_clear_dict() -> dict:
    """清空所有字段（失败轮次回退创建模式时使用，含 previous_*）。"""
    return {
        **_build_clear_dict(),
        "user_request": None,
        "edit_command": None,
        "previous_intent": None,
        "previous_plan": None,
        "previous_code": None,
    }



def dispatch_node(state: CADState) -> dict:
    """
    LangGraph 节点函数。

    后续轮次 resume 格式（直接传字符串）：
      编辑模式：Command(resume="把高度改成 15mm")
      创建模式：Command(resume="生成一个圆柱体")
    """
    if state.get("is_edit_mode", None) is not None:
        has_code = bool(state.get("execution_response_text") and not state.get("correction_mode", False))

        if has_code:
            snapshot = _take_snapshot(state)
            logger.info("dispatch: 本轮成功，快照 previous_*=%s", list(snapshot.keys()))
            user_data: str = interrupt({
                "status": "round_complete",
                "next_mode": "edit",
                "prompt": "请输入编辑指令",
            })
            edit_cmd = user_data.strip()
            logger.info("dispatch: 后续轮次编辑模式，指令=%s", edit_cmd)
            return {**snapshot, **_build_clear_dict(), "is_edit_mode": True, "edit_command": edit_cmd}
        else: #这块的逻辑后面可能还需要进行一定的修改，当上轮失败退出时应该怎么处理，应该输出什么
            logger.info("dispatch: 上轮未产出有效代码，清空全部字段，回退创建模式")
            user_data = interrupt({
                "status": "round_complete",
                "next_mode": "create",
                "prompt": "上轮未产出有效代码，请输入新的创建指令",
            })
            user_req = user_data.strip()
            logger.info("dispatch: 回退创建模式，user_request=%s", user_req)
            return {**_build_full_clear_dict(), "is_edit_mode": False, "user_request": user_req}

    # 首轮：从初始 state 读取
    source_code_path = state.get("source_code_path_input")
    if source_code_path:
        logger.info("dispatch: 首轮编辑模式，读取文件 %s", source_code_path)
        previous_code = _extract_previous_code(source_code_path)
        logger.info("dispatch: 提取代码 %d 行", previous_code.count("\n") + 1)
        return {
            "is_edit_mode": True,
            "previous_code": previous_code,
            "failure_count": 0
        }

    # 创建模式首次启动（user_request 已在 state 中，无需重写）
    logger.info("dispatch: 首轮创建模式，user_request=%s", state.get("user_request", ""))
    return {"is_edit_mode": False, "failure_count": 0}
