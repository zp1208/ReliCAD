# -*- coding: utf-8 -*-
"""
MCP Bridge -- 验证与导出操作
export_step：        导出 STEP 文件
validate_step_file： 检查 STEP 文件是否存在且非空
export_view：        渲染当前视图并保存为图片
"""
import json as _json

from .mcp_base import MCPBase


class MCPValidation(MCPBase):
    """验证与导出操作混入类。

    所有方法均通过 execute_python 直接调用 Fusion 360 原生 API（adsk.*、design、app），
    结果以 JSON 形式从 stdout 返回后在 Python 侧解析。
    """

    def export_step(self, filepath: str) -> dict:
        """将当前设计导出为 STEP 文件。

        Args:
            filepath: 输出 .step 文件的绝对路径（支持 Windows 反斜杠路径）

        Returns:
            {"success": True}

        Raises:
            RuntimeError: Fusion 360 执行失败（路径无效、导出权限不足等）
        """
        code = (
            f"import json\n"
            f"_exportMgr = design.exportManager\n"
            f"_stepOpts = _exportMgr.createSTEPExportOptions(r'{filepath}')\n"
            f"_exportMgr.execute(_stepOpts)\n"
            f"print(json.dumps({{'success': True}}))\n"
        )
        r = self.execute({"operation": "execute_python", "code": code})
        return _json.loads(r["data"]["stdout"])

    def export_view(
        self,
        filepath: str,
        width: int = 512,
        height: int = 512,
        orientation: str = "iso",
        transparent_background: bool = True,
        anti_aliasing: bool = True,
    ) -> dict:
        """捕获当前设计的渲染视图并保存为图片文件。

        Args:
            filepath:    输出图片文件的绝对路径（支持 .png、.jpg 等格式）
            width:       图片宽度（像素），默认 512
            height:      图片高度（像素），默认 512
            orientation: 视角方向，支持：
                         "iso"（等轴测，默认）、"iso_top_right"、"iso_top_left"、
                         "iso_bottom_right"、"iso_bottom_left"、
                         "front"、"back"、"left"、"right"、"top"、"bottom"
            transparent_background: 是否使用透明背景，默认 True（可避免网格显示）
            anti_aliasing: 是否启用抗锯齿，默认 True（更平滑的边缘）

        Returns:
            {"success": True}

        Raises:
            RuntimeError: Fusion 360 执行失败
        """
        code = (
            f"import adsk.core, json\n"
            f"_view_map = {{\n"
            f"    'front':            adsk.core.ViewOrientations.FrontViewOrientation,\n"
            f"    'back':             adsk.core.ViewOrientations.BackViewOrientation,\n"
            f"    'left':             adsk.core.ViewOrientations.LeftViewOrientation,\n"
            f"    'right':            adsk.core.ViewOrientations.RightViewOrientation,\n"
            f"    'top':              adsk.core.ViewOrientations.TopViewOrientation,\n"
            f"    'bottom':           adsk.core.ViewOrientations.BottomViewOrientation,\n"
            f"    'iso':              adsk.core.ViewOrientations.IsoTopRightViewOrientation,\n"
            f"    'iso_top_right':    adsk.core.ViewOrientations.IsoTopRightViewOrientation,\n"
            f"    'iso_top_left':     adsk.core.ViewOrientations.IsoTopLeftViewOrientation,\n"
            f"    'iso_bottom_right': adsk.core.ViewOrientations.IsoBottomRightViewOrientation,\n"
            f"    'iso_bottom_left':  adsk.core.ViewOrientations.IsoBottomLeftViewOrientation,\n"
            f"}}\n"
            f"_orient = _view_map.get({orientation!r}, adsk.core.ViewOrientations.IsoTopRightViewOrientation)\n"
            f"_viewport = app.activeViewport\n"
            f"_cam = _viewport.camera\n"
            f"_cam.viewOrientation = _orient\n"
            f"_cam.isPerspective = False\n"
            f"_cam.isFitView = True\n"
            f"_viewport.camera = _cam\n"
            f"_viewport.refresh()\n"
            f"\n"
            f"# 使用 SaveImageFileOptions 以支持透明背景和抗锯齿\n"
            f"_options = adsk.core.SaveImageFileOptions.create(r'{filepath}')\n"
            f"_options.width = {int(width)}\n"
            f"_options.height = {int(height)}\n"
            f"_options.isBackgroundTransparent = {str(transparent_background)}\n"
            f"_options.isAntiAliased = {str(anti_aliasing)}\n"
            f"_viewport.saveAsImageFileWithOptions(_options)\n"
            f"\n"
            f"print(json.dumps({{'success': True}}))\n"
        )
        r = self.execute({"operation": "execute_python", "code": code})
        return _json.loads(r["data"]["stdout"])
