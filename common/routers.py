"""
LangGraph router functions for the CAD Agent workflow.

Reads typed CADState fields (correction_mode, error_analysis_route) instead of
parsing message strings, eliminating fragile regex/string matching.
"""
import logging

from common.messages.state import CADState

logger = logging.getLogger("CAD_Agent.routers")


def execution_router(state: CADState) -> str:
    if state.get("correction_mode", False):
        logger.warning("路由: 代码执行出错，转至错误分析节点")
        return "error_analysis"
    logger.info("路由: 代码执行成功，转至验证节点")
    return "validation"


def dispatch_router(state: CADState) -> str:
    """Routes from dispatch to the appropriate ingest branch based on is_edit_mode."""
    if state.get("is_edit_mode"):
        logger.info("路由: 编辑模式，进入编辑意图提取节点")
        return "edit_ingest"
    logger.info("路由: 创建模式，进入需求提取节点")
    return "ingest_input"


def error_analysis_router(state: CADState) -> str:
    route = state.get("error_analysis_route", "executable")
    if state.get("is_edit_mode") and route == "planning":
        logger.info("路由: 编辑模式错误分析 → edit_planning")
        return "edit_planning"
    logger.info("路由: 错误分析 → %s", route)
    return route


def post_validation_router(state: CADState) -> str:
    """
    验证节点路由器

    路由逻辑：
    - correction_mode 为 False → end（验证通过，结束流程）
    - correction_mode 为 True → error_analysis（需要修正）
    """
    if state.get("correction_mode", False):
        logger.warning("路由: 验证检测到错误，转至错误分析节点")
        return "error_analysis"

    logger.info("路由: 验证通过，流程结束")
    return "end"
