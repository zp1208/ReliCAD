"""CADState 调试快照核心功能。"""
import functools
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from common.messages.state import CADState

logger = logging.getLogger(__name__)

# 节点恢复前置条件映射
NODE_REQUIRED_FIELDS = {
    "ingest": ["user_request"],
    "planning": ["user_request", "intent_understanding"],
    "executable": ["plan"],
    "error_analysis": ["error_info"],
    "validation": ["execution_step_path"],
}


def serialize_state(state: CADState) -> dict:
    """将 CADState 序列化为 dict（所有字段都是基本类型，直接返回）。"""
    return dict(state)


def deserialize_state(data: dict) -> CADState:
    """从 dict 反序列化为 CADState。"""
    return CADState(**data)


def save_state_snapshot(
    state: CADState,
    node_name: str,
    save_dir: str,
    *,
    suffix: str = "",
) -> Path:
    """保存 CADState 快照到磁盘。

    Args:
        state: 当前状态
        node_name: 节点名称
        save_dir: 输出根目录（时间戳文件夹）
        suffix: 可选后缀（如 "_fail"）

    Returns:
        快照文件路径
    """
    debug_dir = Path(save_dir) / "debug_states"
    debug_dir.mkdir(parents=True, exist_ok=True)

    # 生成序号前缀（按现有文件数量递增）
    existing = sorted(debug_dir.glob("*.json"))
    seq = len([f for f in existing if f.name != "index.json"]) + 1
    filename = f"{seq:03d}_{node_name}{suffix}.json"
    snapshot_path = debug_dir / filename

    # 序列化并保存
    data = serialize_state(state)
    data["_snapshot_meta"] = {
        "node": node_name,
        "timestamp": datetime.now().isoformat(),
    }
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"快照已保存: {snapshot_path}")
    return snapshot_path


def load_state_snapshot(path: str | Path) -> CADState:
    """从快照文件加载 CADState。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 移除元数据
    data.pop("_snapshot_meta", None)
    return deserialize_state(data)


def list_snapshots(save_dir: str | Path) -> list[dict]:
    """列出指定目录下的所有快照。

    Returns:
        快照信息列表，每项包含: path, node, timestamp, seq
    """
    debug_dir = Path(save_dir) / "debug_states"
    if not debug_dir.exists():
        return []

    snapshots = []
    for p in sorted(debug_dir.glob("*.json")):
        if p.name == "index.json":
            continue
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("_snapshot_meta", {})
        snapshots.append({
            "path": str(p),
            "node": meta.get("node", "unknown"),
            "timestamp": meta.get("timestamp", ""),
            "seq": p.stem.split("_")[0],
        })
    return snapshots


def validate_state_for_node(state: CADState, node_name: str) -> None:
    """验证 state 是否满足指定节点的前置条件。

    Raises:
        ValueError: 缺少必要字段时抛出
    """
    required = NODE_REQUIRED_FIELDS.get(node_name, [])
    missing = [f for f in required if not state.get(f)]
    if missing:
        raise ValueError(
            f"节点 '{node_name}' 缺少必要字段: {missing}"
        )


def resume_from_snapshot(
    path: str | Path,
    app,
    resume_node: str,
    thread_id: Optional[str] = None,
) -> None:
    """从快照恢复并继续执行工作流。

    Args:
        path: 快照文件路径
        app: 编译后的 LangGraph 应用
        resume_node: 从哪个节点继续执行
        thread_id: 可选线程 ID（默认使用时间戳）
    """
    state = load_state_snapshot(path)
    validate_state_for_node(state, resume_node)

    thread_id = thread_id or datetime.now().strftime("%Y%m%d_%H%M%S_resume")
    config = {"configurable": {"thread_id": thread_id}}

    logger.info(f"从快照恢复: {path}, 节点: {resume_node}, 线程: {thread_id}")

    # 注入状态并继续执行
    app.update_state(config, state, as_node=resume_node)
    for _ in app.stream(None, config):
        pass
    logger.info("恢复执行完成")


def debug_snapshot(node_name: str) -> Callable:
    """装饰器：在节点执行后自动保存快照。

    仅当 save_dir 存在且 debug_snapshot_enabled 为 True 时保存。

    Usage:
        @debug_snapshot("executable")
        def executable_node(state: CADState) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(state: CADState) -> dict:
            result = func(state)

            # 检查是否启用快照
            save_dir = state.get("save_dir")
            enabled = state.get("debug_snapshot_enabled", True)

            if save_dir and enabled:
                # 合并 state + result 作为完整快照
                merged = {**state, **result}
                try:
                    save_state_snapshot(
                        merged,
                        node_name,
                        save_dir,
                    )
                except Exception as e:
                    logger.warning(f"保存快照失败: {e}")

            return result
        return wrapper
    return decorator

