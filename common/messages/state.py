"""
CADState — LangGraph 工作流的类型化状态对象。

职责划分：
  - Ingest 上下文    : 由 ingest_input 节点写入一次，之后只读
  - failure_count    : 全局累计失败次数，跨节点追踪
  - 执行模块产出     : execution_* 扁平字段 + correction_mode
  - 编辑模式字段     : is_edit_mode / edit_command / previous_* / *_delta
"""
from __future__ import annotations

from typing import List, Optional


try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore


class CADState(TypedDict, total=False):

    # Ingest 上下文（由 ingest_input 节点写入，之后只读）
    user_request: str
    intent_understanding: list

    # 工作流全局状态
    failure_count: int
    save_dir: Optional[str]  # 当前运行的输出目录（时间戳文件夹路径）
    debug_snapshot_enabled: bool  # 是否启用调试快照（默认 True）

    # 节点产出
    plan: Optional[str]

    # ── 执行模块产出 ──────────────────────────────────────────────────────────
    correction_mode: bool               # True = 执行出错，进入修正模式
    execution_response_text: Optional[str]   # LLM 原始输出
    execution_code_path: Optional[str]       # 生成脚本快照路径
    execution_step_path: Optional[str]       # 预期 STEP 文件路径（成功时有值）
    execution_image_path: Optional[str]
    execution_evidence: Optional[dict]        # 运行时证据（建模序列真值，成功/失败均可有值）
    error_info: Optional[str]                 # 出错命令 + traceback（失败时有值，执行/验证模块共用）
    error_analysis_result: Optional[str]      # 错误分析节点输出的分析结论
    error_analysis_route: Optional[str]       # 错误分析后的路由方向: "ingest" | "planning" | "executable" | "fatal"
    error_history: List[dict]                 # 当前轮次的错误分析历史

    # ── 编辑模式：标识与输入 ──────────────────────────────────────────────────
    is_edit_mode: bool
    edit_command: Optional[str]
    source_code_path_input: Optional[str]

    # ── 编辑模式：历史快照 ────────────────────────────────────────────────────
    previous_intent: Optional[dict]
    previous_plan: Optional[str]
    previous_code: Optional[str]

    # ── 编辑模式：Delta 计算结果 ──────────────────────────────────────────────
    intent_delta: Optional[dict]
    plan_delta: Optional[dict]
