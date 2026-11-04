# -*- coding: utf-8 -*-
"""
MCP Bridge -- 通用基础操作
ping：连通性检测
clear：清空当前设计
detach：断开 MCP 会话
"""
from .mcp_base import MCPBase


class MCPCommon(MCPBase):
    """通用基础操作混入类。

    提供与 Fusion 360 连接状态管理相关的基础方法，
    以及坐标格式转换辅助函数（供所有子模块调用）。
    """

    def _pt(self, x, y, z=0.0) -> dict:
        """将坐标值转换为 Point3D 参数字典。

        Args:
            x, y, z: 坐标值（单位：厘米）

        Returns:
            {"type": "Point3D", "x": ..., "y": ..., "z": ...}
        """
        return {"type": "Point3D", "x": float(x), "y": float(y), "z": float(z)}

    def _pt_from(self, coord) -> dict:
        """将任意坐标格式统一转换为 Point3D 参数字典。

        Args:
            coord: (x, y)、(x, y, z) 元组/列表，或已是 Point3D dict。

        Returns:
            Point3D 字典，格式同 _pt() 返回值。
        """
        if isinstance(coord, dict):
            return coord
        if len(coord) == 2:
            return self._pt(coord[0], coord[1])
        return self._pt(coord[0], coord[1], coord[2])

    def ping(self) -> bool:
        """检测 Fusion 360 是否可通过 MCP 正常访问。

        Returns:
            True  — 连接正常
            False — 连接失败或超时
        """
        try:
            self.execute({
                "operation": "execute_python",
                "code": "import json; print(json.dumps({'component': design.rootComponent.name}))",
            })
            return True
        except Exception:
            if getattr(self, "_transport", "direct") == "direct":
                raise
            return False

    def clear(self) -> bool:
        """清空当前 Fusion 360 设计（删除所有实体、草图和构造几何）。

        内置构造几何（XY/XZ/YZ 平面、X/Y/Z 轴）由 deleteEntities 自动忽略。

        Raises:
            RuntimeError: Fusion 360 执行失败。
            TimeoutError: Fusion 360 未在超时内响应。
        """
        # Reset the active design by closing open documents, mirroring the
        # strong-isolation semantics of the server-side CADBase.clear().
        code = """\
import json, adsk.core, adsk.fusion
app = adsk.core.Application.get()
for i in range(app.documents.count - 1, -1, -1):
    app.documents.item(i).close(False)
# 创建新文档（关闭所有文档后 activeProduct 为 None）
app = adsk.core.Application.get()
doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
design = adsk.fusion.Design.cast(app.activeProduct)
root = design.rootComponent
print(json.dumps({
    "cleared": True,
    "body_count": root.bRepBodies.count,
    "sketch_count": root.sketches.count,
}))
"""
        self.execute({"operation": "execute_python", "code": code})
        if hasattr(self, "_sketch_refs"):
            self._sketch_refs.clear()
        if hasattr(self, "reset_capture"):
            self.reset_capture()

        return True

    def detach(self) -> None:
        """断开并关闭 MCP 会话连接。

        调用后如需再次操作，将重新建立连接（懒加载）。
        """
        self.close()
