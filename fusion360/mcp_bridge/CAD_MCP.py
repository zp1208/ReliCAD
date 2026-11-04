# -*- coding: utf-8 -*-
"""
MCP Bridge -- 入口文件
仅需导入此文件；它通过多重继承聚合所有功能模块。

使用示例：
    from fusion360.mcp_bridge.CAD_MCP import CAD_MCP

    cad = CAD_MCP()
    s = cad.create_sketch("XY")
    cad.add_line((0, 0, 0), (10, 0, 0), s["sketch_ref"])
    cad.extrude(5.0, s["sketch_ref"])
    cad.export_step("/tmp/part.step")
    cad.close()
"""
# 各功能模块混入类
from .mcp_base import MCPBase              # 连接层：MCP 连接、底层调用辅助
from .mcp_common import MCPCommon          # 通用操作：ping、clear、detach
from .mcp_sketch import MCPSketch          # 草图操作：新建草图、验证、闭合
from .mcp_primitives import MCPPrimitives  # 图元操作：线、圆、弧、椭圆、NURBS
from .mcp_constraints import MCPConstraints  # 约束与参数操作
from .mcp_extrude import MCPExtrude        # 三维实体操作：拉伸、旋转、螺旋扫掠
from .mcp_chamfer_fillet import MCPChamferFillet  # 倒角与圆角操作
from .mcp_thread import MCPThread                # 螺纹操作
from .mcp_validation import MCPValidation  # 验证与导出操作
from .mcp_evidence import MCPEvidence      # 运行时证据捕获器


class CAD_MCP(
    MCPCommon,
    MCPSketch,
    MCPPrimitives,
    MCPConstraints,
    MCPExtrude,
    MCPChamferFillet,
    MCPThread,
    MCPValidation,
    MCPEvidence,  # 放最后，确保 get_entity_info 可用
):
    """统一的 CAD API，通过 MCP 协议与 Fusion 360 通信。

    所有方法委托给对应的功能混入模块实现。
    仅 MCPBase.__init__ 会执行初始化逻辑：
      - 通过原生消息协议发现 AuraFriday 服务器 URL
      - SSE 连接在首次调用时懒加载建立（非 __init__ 时）

    MRO（方法解析顺序）遵循 Python 标准 C3 线性化，
    MCPBase 位于最后确保其 __init__ 只执行一次。
    """

    def __init__(
        self,
        server_url: str | None = None,
        auth_token: str | None = None,
        *,
        transport: str = "direct",
        direct_url: str | None = None,
    ):
        super().__init__(
            server_url=server_url,
            auth_token=auth_token,
            transport=transport,
            direct_url=direct_url,
        )
