import logging
import os


from validation.skills import run_edit_mode_validation, run_full_visual_check, run_spec_check

from debug.state_debugger import debug_snapshot

logger = logging.getLogger("CAD_Agent.validation")


@debug_snapshot("validation")
def validation_node(state, render_dir=r"result/render"):
    """
    验证节点
    流程：
    1. 检查 STEP 文件有效性
    2. 规约检查（比对 intent_understanding 与 execution_evidence）
    3. 全量视觉检查（基于渲染的四视图）
    4. 根据结果返回 correction_mode 和 error_info

    参数：
        state: CADState 字典
        render_dir: 渲染输出目录（如果state中有save_dir则忽略此参数）

    返回：
        {"correction_mode": bool, "error_info": str|None}
    """
    logger.info("--- [节点] 验证节点启动 ---")

    # 1. STEP 文件预检查
    execution_step_path = state.get("execution_step_path")
    step_file_error = None

    if execution_step_path is None:
        step_file_error = "execution_step_path 字段不存在于 state 中，出现无法处理的异常，请直接失败"
    elif not os.path.exists(execution_step_path):
        step_file_error = f"STEP 文件不存在，出现无法处理的异常，请直接失败"
    elif os.path.getsize(execution_step_path) == 0:
        step_file_error = f"生成的CAD模型为空"

    if step_file_error:
        logger.error("验证: STEP 文件检查失败 - %s", step_file_error)
        error_info = f"STEP 文件问题: {step_file_error}"

        return {
            "correction_mode": True,
            "error_info": error_info,
        }

    if state.get("is_edit_mode"):
        # 编辑模式有独立验证入口，避免继续执行创建模式的规约和视觉检查。
        logger.info("验证: 编辑模式")
        return run_edit_mode_validation(state)

    # 2. 规约检查（新增）
    logger.info("验证: 开始规约检查")
    intent_understanding = state.get("intent_understanding")
    execution_evidence = state.get("execution_evidence")

    spec_check_result = run_spec_check(intent_understanding, execution_evidence)
    logger.info("验证: 规约检查结果 - %s", spec_check_result["overall_status"])
    # 如果规约检查失败（完整模式：收集所有失败项后返回）

    failed_checks = [c for c in spec_check_result["checks"] if c["status"] == "fail"]
    pending_checks = [c for c in spec_check_result["checks"] if c["status"] == "pending"]
    if len(failed_checks) > 0:
        error_details = []
        for c in failed_checks:
            error_details.append(f"  • {c['spec_name']}: {c['detail']}")
        error_info = f"规约验证失败 ({len(failed_checks)}/{len(spec_check_result['checks'])} 条规约不匹配):\n" + "\n".join(error_details)
        logger.warning("验证: 规约检查失败，不再执行视觉检查")
        return {
            "correction_mode": True,
            "error_info": error_info,
        }
    # 如果是 partial（有 pending 项），继续视觉检查
    pending_info = None
    if len(pending_checks) > 0:
        pending_details = []
        for c in pending_checks:
            pending_details.append(f"  • {c['spec_name']}: {c['detail']}")
        pending_info = f"The following checks require priority visual verification:\n" + "\n".join(pending_details)
        logger.info("验证: %s", pending_info)


    # 3. 运行视觉检查
    logger.info("验证: 开始全量视觉检查")
    user_input = state.get("user_request")

    visual_result = run_full_visual_check(user_input, state.get("execution_image_path"), pending_info)


    # 4. 根据视觉结果返回
    if visual_result["status"] == "pass":
        logger.info("验证: 全量视觉检查通过，验证成功")

        # 保存成功标志文件
        save_dir = state.get("save_dir")
        result_file = os.path.join(save_dir, "result.txt")
        with open(result_file, "w", encoding="utf-8") as f:
            f.write("success")
        logger.info("验证: 成功标志已保存至 %s", result_file)

        return {
            "correction_mode": False,
            "error_info": None,
        }
    else:
        detail = visual_result.get('detail', '')
        logger.warning("验证: 全量视觉检查未通过 - %s", detail)
        return {
            "correction_mode": True,
            "error_info": f"视觉验证失败: {detail}",
        }
