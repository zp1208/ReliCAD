"""编辑模式验证框架。"""

import logging


logger = logging.getLogger("CAD_Agent.edit_mode_validation")


def run_edit_mode_validation(state: dict) -> dict:
    """
    处理编辑模式的验证入口。

    具体检查规则后续补充；当前只提供稳定返回结构，并阻止编辑模式继续走创建模式的规约/视觉检查流程。
    """
    logger.info("编辑模式验证: 已进入专用处理框架")
    return {
        "correction_mode": False,
        "error_info": None,
    }
