import argparse
import io
import logging
import os
import sys
from datetime import datetime

# Force UTF-8 stdout/stderr on Windows to prevent garbled Chinese output
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END

from common.messages.state import CADState
from common.routers import dispatch_router, error_analysis_router, execution_router, post_validation_router
from code_generation.ExecutableNode import executable_node
from dispatch.node import dispatch_node
from create_planning.model_planning.node import planning_node
from create_planning.requirements_clarification.node import ingest_input
from edit_workflow.ingest.node import edit_ingest_node
from edit_workflow.planning.node import edit_planning_node
from error_analysis.node import error_analysis_node
from validation.ValidationNode import validation_node


def build_workflow():
    """构建并编译LangGraph工作流。

    Returns:
        编译后的工作流应用实例
    """
    workflow = StateGraph(CADState)

    # 添加节点
    workflow.add_node("dispatch", dispatch_node)
    workflow.add_node("ingest", ingest_input)
    workflow.add_node("planning", planning_node)
    # workflow.add_node("edit_ingest", edit_ingest_node)
    workflow.add_node("edit_planning", edit_planning_node)
    workflow.add_node("executable", executable_node)
    workflow.add_node("error_analysis", error_analysis_node)
    workflow.add_node("validation", validation_node)

    # 设置入口点
    workflow.set_entry_point("dispatch")

    # 添加边
    workflow.add_conditional_edges(
        "dispatch",
        dispatch_router,
        {
            "ingest_input": "ingest",
            "edit_ingest": "edit_planning",
        },
    )
    # workflow.add_edge("edit_ingest", "edit_planning")
    workflow.add_edge("edit_planning", "executable")
    workflow.add_edge("ingest", "planning")
    workflow.add_edge("planning", "executable")
    workflow.add_conditional_edges(
        "executable",
        execution_router,
        {
            "error_analysis": "error_analysis",
            "validation": "validation",
        },
    )
    workflow.add_conditional_edges(
        "error_analysis",
        error_analysis_router,
        {
            "ingest": "ingest",
            "planning": "planning",
            "edit_planning": "edit_planning",
            "executable": "executable",
            "fatal": END,
        },
    )
    workflow.add_conditional_edges(
        "validation",
        post_validation_router,
        {
            "end": END,
            "error_analysis": "error_analysis",
        },
    )

    # 编译工作流
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CAD Agent workflow.")
    parser.add_argument(
        "-u",
        "--user-input",
        # default="生成一个复杂的U形钣金支架",
        # default="该零件为线径 5 mm、平均直径 32 mm、自由高度 56 mm 的右旋圆柱压缩弹簧，共 10 圈，中部 8 圈采用 5.1 mm 等节距排列，上下各设 1 圈闭口磨平支撑圈。",
        # default="T-shaped prismatic plate 12 mm thick in Z, with plan outline spanning X0–45 and Y0–25: a 45 × 5 horizontal bar from Y20–25 and a 5 mm wide central leg from X20–25 down to Y0. Include a Ø3.5 mm through hole normal to X through the central leg, centered at Y10, Z6 on the X25 face, and a Ø3.5 mm through hole normal to Y through the left bar, centered at X10, Z6. On the Y25 face of the right bar, add four Ø2 mm through holes normal to Y in a 2 × 2 rectangular array at X31.5 and 41.5, Z3.5 and 8.5, spaced 10 mm horizontally and 5 mm vertically.",
        # default="Create a miniature spiral staircase with a central column, base disk, and 20 rising wedge treads. Add a one-revolution helical handrail and vertical balusters at the tread outer ends.",
        # default="生成一个推拉门模型",
        # default="生成一个运动水壶",
        # default="生成一个气杆连接块",
        # default="生成一个半圆形房顶的积木房子",
        # default="生成一个平型铰链",
        # default="生成一个带螺纹的六角形螺母",
        # default="生成一个氮气弹簧安装块",
        # default="将六边形外轮廓整体放大10%",
        # default="给瓶口和盖子加上螺纹",
        default="生成一个开放式离心叶轮",
        # default="将叶片数量修改为 8 个，并保持圆周均匀分布",
        help="创建指令（创建模式）或编辑指令（编辑模式）。",
    )
    parser.add_argument(
        "--source-code-path",
        # default = r"D:\python_project\CAD_Agent\agent-master\result\20260717_205840\20260717_210039.py",
        default=None,
        # help="已有 Fusion 360 Python 文件路径。提供此参数则进入编辑模式，跳过创建阶段。",
    )
    parser.add_argument(
        "--save-dir",
        default=r"D:\python_project\CAD_Agent\agent-master\result",
        help="输出根目录，将在此目录下创建时间戳文件夹（默认: outputs）。",
    )
    parser.add_argument(
        "--recursion-limit",
        type=int,
        default=40,
        help="LangGraph recursion limit (default: 40).",
    )
    parser.add_argument(
        "--disable-snapshot",
        action="store_true",
        help="禁用调试快照保存（默认启用）。",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Optional fixed thread id. If omitted, timestamp will be used.",
    )
    args = parser.parse_args()

    # 创建时间戳文件夹
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_output_dir = os.path.join(args.save_dir, timestamp)
    os.makedirs(run_output_dir, exist_ok=True)

    # 配置日志到时间戳文件夹
    log_filename = os.path.join(run_output_dir, "cad_agent.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_filename, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logger = logging.getLogger("CAD_Agent")

    logger.info("=== CAD Agent 启动 ===")

    if args.source_code_path:
        # 编辑模式：dispatch 节点负责读取文件并设置 previous_code
        inputs = {
            "source_code_path_input": args.source_code_path,
            "edit_command": args.user_input,
            "save_dir": run_output_dir,
            "debug_snapshot_enabled": not args.disable_snapshot,
        }
        logger.info("启动模式: 编辑  文件=%s  指令=%s", args.source_code_path, args.user_input)
    else:
        # 创建模式
        inputs = {
            "user_request": args.user_input,
            "save_dir": run_output_dir,
            "debug_snapshot_enabled": not args.disable_snapshot,
        }
        logger.info("启动模式: 创建  指令=%s", args.user_input)

    logger.info("输出目录: %s", run_output_dir)

    thread_id = args.thread_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    config = {"recursion_limit": args.recursion_limit, "configurable": {"thread_id": thread_id}}
    logger.info("线程 ID: %s", thread_id)

    # 构建工作流
    app = build_workflow()

    try:
        for _ in app.stream(inputs, config=config):
            pass
    except KeyboardInterrupt:
        logger.info("工作流被用户中断")
    except Exception as ex:
        logger.error("工作流异常崩溃: %s", str(ex), exc_info=True)
    finally:
        logger.info("=== 工作流结束，日志文件: %s ===", log_filename)
