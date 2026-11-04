import logging
import os
import re
import json
import subprocess
import sys
import time
import filelock
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from code_generation.skills import code_filter, create_prompt_context, script_runtime
from code_generation.skills.edit_prompt_context import build_edit_prompt_context, build_edit_system_prompt
from common.LLM import invoke_llm
from common.messages.state import CADState
from debug.state_debugger import debug_snapshot
from fusion360.mcp_bridge.CAD_MCP import CAD_MCP
from validation.skills import render_all_views


logger = logging.getLogger("CAD_Agent.executable")



def _extract_statement(file_lines: list, lineno: int) -> str:
    idx = lineno - 1
    if idx >= len(file_lines):
        return ""
    collected = []
    depth = 0
    for line in file_lines[idx:]:
        collected.append(line.rstrip())
        depth += line.count('(') - line.count(')')
        depth += line.count('[') - line.count(']')
        depth += line.count('{') - line.count('}')
        if depth <= 0 and not line.rstrip().endswith('\\'):
            break
    return '\n'.join(collected).strip()


def _build_error_info(stderr_val: str, script_path: Path) -> str:
    lines = stderr_val.splitlines()

    # 从最后一行往前找第一个含 Error 的行作为错误信息
    error_msg = next((l for l in reversed(lines) if "Error" in l), lines[-1] if lines else "")

    # 找 script_path 文件名对应的最后一条 traceback 条目，取其下一行作为错误命令起始行
    script_name = re.escape(script_path.name)
    pattern = rf'File "[^"]*{script_name}", line (\d+)'
    matches = list(re.finditer(pattern, stderr_val))
    if not matches:
        return error_msg

    last_match = matches[-1]
    lineno = int(last_match.group(1))

    # traceback 中 File "..." 行的下一行是代码片段，但我们直接从文件读取完整语句
    try:
        file_lines = script_path.read_text(encoding="utf-8").splitlines()
        failed_stmt = _extract_statement(file_lines, lineno)
        if failed_stmt:
            return f"出错命令: {failed_stmt}\n错误信息: {error_msg}"
    except Exception:
        pass

    return error_msg


def _load_evidence(evidence_path: Path):
    """读取运行时证据文件（成功/失败均可能存在）。读不到返回 None。"""
    if not evidence_path.exists():
        return None
    try:
        return json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception as ex:
        logger.warning("读取运行时证据失败 %s: %s", evidence_path, ex)
        return None


@debug_snapshot("executable")
def executable_node(state: "CADState"):
    logger.info("--- 运行中: 代码生成节点 ---")

    correction_mode = state.get("correction_mode", False)
    is_edit_mode = state.get("is_edit_mode", False)
    save_dir = state.get("save_dir")

    logger.info("代码生成: correction_mode=%s, is_edit_mode=%s", correction_mode, is_edit_mode)

    if is_edit_mode:
        base_prompt = build_edit_system_prompt(
            create_prompt_context.API_CONTEXT,
            correction_mode=correction_mode,
        )
        compiled_context = build_edit_prompt_context(state)
    else:
        base_prompt = create_prompt_context.build_system_prompt(state)
        compiled_context = create_prompt_context.build_execution_prompt_context(state)

    messages = [
        SystemMessage(content=base_prompt),
        HumanMessage(content=compiled_context),
    ]
    response_text = invoke_llm(messages, temperature=0)
    logger.info("代码生成: LLM 原始响应全文开始\n%s\n代码生成: LLM 原始响应全文结束", response_text)

    indented_code = code_filter.extract_valid_calls(response_text)
    indented_code = code_filter.inject_auto_close_calls(indented_code)


    # 确定输出路径
    output_dir = Path(save_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_script_path = output_dir / f"{timestamp}.py"
    step_path = output_dir / f"{timestamp}.step"
    evidence_path = output_dir / f"{timestamp}.evidence.json"


    # 构建脚本并保存
    full_script = script_runtime.build_script(
        indented_code, str(step_path), str(evidence_path)
    )
    output_script_path.parent.mkdir(parents=True, exist_ok=True)
    output_script_path.write_text(full_script, encoding="utf-8")
    logger.info("代码生成: 脚本已保存至 %s", output_script_path)

    # 获取project_root用于执行环境
    project_root = Path(__file__).resolve().parents[1]
    _env = os.environ.copy()
    _existing = _env.get("PYTHONPATH", "")
    _env["PYTHONPATH"] = str(project_root) + (os.pathsep + _existing if _existing else "")

    try:
        process = subprocess.run(
            [sys.executable, str(output_script_path)],
            capture_output=True,
            timeout=600,
            cwd=str(project_root),
            env=_env,
        )
        stderr_val = process.stderr.decode("utf-8", errors="replace").strip() if process.stderr else ""

        if process.returncode == 0:
            logger.info("代码执行成功，STEP文件: %s", step_path)

            # 确定渲染目录

            # 使用save_dir，在其中创建时间戳文件夹用于渲染
            render_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            render_dir = os.path.join(save_dir, f"render_{render_timestamp}")


            os.makedirs(render_dir, exist_ok=True)
            render_dir = os.path.abspath(render_dir)
            logger.info("代码执行: 渲染目录 - %s", render_dir)

            # 初始化 MCP 客户端
            cad = CAD_MCP()

            # 渲染所有视图
            logger.info("代码执行: 开始渲染视图（TOP, FRONT, RIGHT, ISO）")
            image_path = render_all_views(render_dir, cad)

            return {
                "correction_mode": False,
                "execution_response_text": response_text,
                "execution_code_path": str(output_script_path),
                "execution_step_path": str(step_path),
                "execution_evidence": _load_evidence(evidence_path),
                "error_info": None,
                "execution_image_path": str(image_path),

            }

        error_info = _build_error_info(stderr_val, output_script_path)
        logger.info("代码执行出现错误，错误信息：\n%s", error_info)
        return {
            "correction_mode": True,
            "execution_response_text": response_text,
            "execution_code_path": str(output_script_path),
            "execution_step_path": None,
            "execution_evidence": _load_evidence(evidence_path),
            "error_info": error_info,
        }

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"脚本执行超时，脚本路径: {output_script_path}")

    except Exception as ex:
        raise RuntimeError(f"执行环境异常: {ex}，脚本路径: {output_script_path}") from ex



# if __name__ == "__main__":
#     project_root = Path(__file__).resolve().parents[1]
#     process = subprocess.run(
#             [sys.executable, "-m", "result.fusion_generated"],
#             capture_output=True,
#             timeout=90,
#             cwd=str(project_root),
#         )
#     stdout_val = process.stdout.decode("utf-8", errors="replace").strip() if process.stdout else ""
#     stderr_val = process.stderr.decode("utf-8", errors="replace").strip() if process.stderr else "" 
#     a = _build_error_info(stderr_val, Path(r"D:\python_project\CAD_Agent\agent-master\result\fusion_generated.py"))
#     print(a)
#     pass
