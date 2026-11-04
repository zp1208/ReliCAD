# -*- coding: utf-8 -*-
"""
MCP Bridge -- 草图操作
create_sketch：在指定构造平面（可带偏移，或由 ZYX 欧拉角+平移定义任意平面）上新建草图。
"""
import math
from .mcp_base import MCPBase

_MM = 0.1  # mm -> cm, Fusion 360 internal unit


def _zyx_rotation_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> list[list[float]]:
    """ZYX 欧拉角（偏航-俯仰-滚转，角度制）→ 3×3 旋转矩阵 R = Rz·Ry·Rx。"""
    rx = math.radians(rx_deg)
    ry = math.radians(ry_deg)
    rz = math.radians(rz_deg)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        [cz*cy,  cz*sy*sx - sz*cx,  cz*sy*cx + sz*sx],
        [sz*cy,  sz*sy*sx + cz*cx,  sz*sy*cx - cz*sx],
        [-sy,    cy*sx,              cy*cx            ],
    ]


class MCPSketch(MCPBase):
    """草图操作混入类。

    维护 _sketch_refs 列表，后续基元/约束/拉伸方法可通过
    self._sketch_refs[-1] 默认操作最新草图，也可通过 sketch_ref 参数显式指定。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sketch_refs: list[str] = []
        self._sketch_transforms: dict[str, dict] = {}

    def create_sketch(
        self,
        plane: str = "XY",
        offset: float = 0.0,
        *,
        euler_angles: tuple[float, float, float] | None = None,
        translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> str:
        """在指定构造平面上新建草图。

        用法一 — 标准构造平面（可带偏移）::

            create_sketch("XY")
            create_sketch("XZ", offset=2.5)

        用法二 — 任意平面（ZYX 欧拉角 + 平移）::

            create_sketch(euler_angles=(rx, ry, rz), translation=(tx, ty, tz))

        Args:
            plane:        标准构造平面，可选 "XY"、"XZ"、"YZ"（用法一专用）。
            offset:       沿平面法向的偏移距离，单位毫米（用法一专用）。
            euler_angles: (rx, ry, rz) ZYX 欧拉角，单位度。提供此参数时走用法二，
                          plane/offset 参数被忽略。
            translation:  (x, y, z) 平面原点坐标，单位毫米，默认 (0,0,0)。

        Returns:
            sketch_ref: str — execute_python 全局变量名（如 "sketch_0"），
                        供后续 add_line / add_circle / extrude 等方法引用。

        Raises:
            ValueError:   plane 参数不在可选范围内。
            RuntimeError: Fusion 360 执行失败。
            TimeoutError: Fusion 360 未在超时内响应。
        """
        store_key = self._next_ref("sketch")

        if euler_angles is not None:
            self._create_sketch_by_euler(store_key, euler_angles, translation)
            self._log_sketch(store_key, euler_angles=list(euler_angles),
                             translation=list(translation))
        else:
            self._create_sketch_by_plane(store_key, plane, offset)
            self._log_sketch(store_key, plane=plane, offset=offset)

        self._sketch_refs.append(store_key)
        return store_key

    # ── 内部实现 ──────────────────────────────────────────────────────────

    def _compute_expected_matrix(
        self, euler_angles: tuple[float, float, float], translation: tuple[float, float, float]
    ) -> list[list[float]]:
        """计算用户期望的 4×4 齐次变换矩阵。

        Args:
            euler_angles: (rx, ry, rz) ZYX 欧拉角，单位度
            translation: (x, y, z) 原点位置，单位毫米

        Returns:
            4×4 齐次变换矩阵 R_expected
        """
        R = _zyx_rotation_matrix(euler_angles[0], euler_angles[1], euler_angles[2])
        tx, ty, tz = translation[0] * _MM, translation[1] * _MM, translation[2] * _MM
        return [
            [R[0][0], R[0][1], R[0][2], tx],
            [R[1][0], R[1][1], R[1][2], ty],
            [R[2][0], R[2][1], R[2][2], tz],
            [0, 0, 0, 1],
        ]

    def _invert_homogeneous_matrix(self, M: list[list[float]]) -> list[list[float]]:
        """计算 4×4 齐次变换矩阵的逆。

        使用刚体变换的快速求逆公式：M = [R | t]，则 M^(-1) = [R^T | -R^T × t]

        Args:
            M: 4×4 齐次变换矩阵

        Returns:
            M^(-1)
        """
        R = [[M[i][j] for j in range(3)] for i in range(3)]
        t = [M[i][3] for i in range(3)]
        R_T = [[R[j][i] for j in range(3)] for i in range(3)]
        t_inv = [-sum(R_T[i][j] * t[j] for j in range(3)) for i in range(3)]
        return [
            [R_T[0][0], R_T[0][1], R_T[0][2], t_inv[0]],
            [R_T[1][0], R_T[1][1], R_T[1][2], t_inv[1]],
            [R_T[2][0], R_T[2][1], R_T[2][2], t_inv[2]],
            [0, 0, 0, 1],
        ]

    def _multiply_matrices(
        self, A: list[list[float]], B: list[list[float]]
    ) -> list[list[float]]:
        """计算两个 4×4 矩阵的乘积。

        Args:
            A: 4×4 矩阵
            B: 4×4 矩阵

        Returns:
            4×4 矩阵 A × B
        """
        result = [[0.0 for _ in range(4)] for _ in range(4)]
        for i in range(4):
            for j in range(4):
                result[i][j] = sum(A[i][k] * B[k][j] for k in range(4))
        return result

    
    def _create_sketch_by_euler(
        self,
        store_key: str,
        euler_angles: tuple[float, float, float],
        translation: tuple[float, float, float],
    ):
        """ZYX 欧拉角 + 平移 → 外旋三次 setByAngle → 草图。

        使用外旋（extrinsic rotation）方式，绕固定的全局轴旋转三次。
        平移由补偿矩阵 H 处理，创建平面时只处理旋转。

        算法：
        1. 依次绕全局 X、Y、Z 轴旋转（外旋）
        2. 在最终平面上创建草图（不做平移）
        3. 读取实际 transform 并计算补偿矩阵（包含平移）

        Args:
            store_key: 草图引用名
            euler_angles: (rx, ry, rz) ZYX 欧拉角，单位度
            translation: (x, y, z) 原点位置，单位毫米
        """

        # 计算用户期望的 4×4 齐次变换矩阵
        R_expected = self._compute_expected_matrix(euler_angles, translation)

        # 提取欧拉角
        rx, ry, rz = euler_angles

        # 外旋三次旋转并创建草图
        result = self.execute({
            "operation": "execute_python",
            "code": f"""
import adsk.core
import adsk.fusion
import math

app = adsk.core.Application.get()
design = adsk.fusion.Design.cast(app.activeProduct)
root = design.rootComponent

# 获取参考平面和标准轴
xy_plane = root.xYConstructionPlane
x_axis = root.xConstructionAxis
y_axis = root.yConstructionAxis
z_axis = root.zConstructionAxis

# 外旋三次: R = Rz(rz) · Ry(ry) · Rx(rx)
# 1. 绕全局 X 轴旋转 rx
rx_rad = math.radians({rx!r})
if abs(rx_rad) < 1e-6:
    plane1 = xy_plane
else:
    plane_input1 = root.constructionPlanes.createInput()
    angle_value1 = adsk.core.ValueInput.createByReal(rx_rad)
    plane_input1.setByAngle(x_axis, angle_value1, xy_plane)
    plane1 = root.constructionPlanes.add(plane_input1)

# 2. 绕全局 Y 轴旋转 ry
ry_rad = math.radians({ry!r})
# 检查平面法向量的 Y 分量，如果接近 ±1 说明垂直于 Y 轴，跳过旋转
if abs(ry_rad) < 1e-6 or abs(plane1.geometry.normal.y) > 0.999:
    plane2 = plane1
else:
    plane_input2 = root.constructionPlanes.createInput()
    angle_value2 = adsk.core.ValueInput.createByReal(ry_rad)
    plane_input2.setByAngle(y_axis, angle_value2, plane1)
    plane2 = root.constructionPlanes.add(plane_input2)

# 3. 绕全局 Z 轴旋转 rz
rz_rad = math.radians({rz!r})
# 检查平面法向量的 Z 分量，如果接近 ±1 说明垂直于 Z 轴，跳过旋转
if abs(rz_rad) < 1e-6 or abs(plane2.geometry.normal.z) > 0.999:
    construction_plane = plane2
else:
    plane_input3 = root.constructionPlanes.createInput()
    angle_value3 = adsk.core.ValueInput.createByReal(rz_rad)
    plane_input3.setByAngle(z_axis, angle_value3, plane2)
    construction_plane = root.constructionPlanes.add(plane_input3)

# 在最终平面上创建草图（不做平移，由补偿矩阵处理）
{store_key} = root.sketches.add(construction_plane)

# 读取草图的 transform 矩阵
t = {store_key}.transform
matrix = []
for i in range(4):
    row = [t.getCell(i, j) for j in range(4)]
    matrix.append(row)
print(matrix)
"""
        })

        # 解析 Fusion 360 返回的 transform 矩阵
        import ast
        data = result.get("data", {})
        stdout = data.get("stdout", "")
        lines = stdout.strip().split("\n")
        matrix_str = lines[-1] if lines else ""
        R_actual = ast.literal_eval(matrix_str.strip())

        # 计算最终变换矩阵：H = R_actual^(-1) × R_expected
        R_actual_inv = self._invert_homogeneous_matrix(R_actual)
        H = self._multiply_matrices(R_actual_inv, R_expected)

        # 存储齐次变换矩阵
        self._sketch_transforms[store_key] = {
            "homogeneous_matrix": H
        }

    def _create_sketch_by_plane(self, store_key: str, plane: str, offset: float):
        """通过标准构造平面 + 偏移量创建草图，维护变换矩阵 H。

        使用 Fusion 360 的标准构造平面（xYConstructionPlane 等）加上偏移量来创建草图，
        并计算补偿矩阵 H，使得草图坐标系统能够正确映射到世界坐标系统：
        - XY 平面: (x, y) → (x, y, 0)
        - XZ 平面: (x, y) → (x, 0, y)
        - YZ 平面: (x, y) → (0, x, y)

        Args:
            store_key: 草图引用名
            plane: 标准平面名称 ("XY", "XZ", "YZ")
            offset: 沿平面法向的偏移距离，单位毫米
        """
        p = plane.upper()
        if p not in ("XY", "XZ", "YZ"):
            raise ValueError(f"未知平面 {plane!r}，可选: XY, XZ, YZ")

        # 标准平面属性名
        plane_prop = {
            "XY": "xYConstructionPlane",
            "XZ": "xZConstructionPlane",
            "YZ": "yZConstructionPlane",
        }[p]

        # 使用标准平面 + offset 创建草图
        offset_cm = offset * _MM  # mm -> cm
        self.execute({
            "operation": "execute_python",
            "code": f"""
import adsk.core
import adsk.fusion

app = adsk.core.Application.get()
design = adsk.fusion.Design.cast(app.activeProduct)
root = design.rootComponent

# 获取标准构造平面
construction_plane = root.{plane_prop}

# 在平面上创建草图
{store_key} = root.sketches.add(construction_plane)
"""
        }) 
        if p == "XY":
            H = [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, offset_cm],
                [0, 0, 0, 1],
            ]
        elif p == "XZ":
            H = [
                [1.0,  0.0,  0.0, 0.0],
                [0.0, -1.0,  0.0, 0.0],
                [0.0,  0.0, -1.0, offset_cm],
                [0.0,  0.0,  0.0, 1.0],
            ]
        elif p == "YZ":
            H = [
                [0.0, -1.0, 0.0, 0.0],
                [1.0,  0.0, 0.0, 0.0],
                [0.0,  0.0, 1.0, offset_cm],
                [0.0,  0.0, 0.0, 1.0],
            ]

        self._sketch_transforms[store_key] = {
            "homogeneous_matrix": H
        }













    def _create_sketch_by_euler3(
        self,
        store_key: str,
        euler_angles: tuple[float, float, float],
        translation: tuple[float, float, float],
    ):
        """ZYX 欧拉角 + 平移 → Plane.createUsingDirections + setByPlane → 草图。

        算法：
        1. 计算 4×4 齐次变换矩阵（旋转 + 平移）
        2. 提取旋转矩阵的第一、二列作为 U/V 方向（草图局部 X/Y 轴）
        3. 用 Plane.createUsingDirections 创建几何平面
        4. 用 setByPlane 创建构造平面
        5. 在该平面上创建草图
        6. 读取实际 transform 并计算补偿矩阵
        """
        # 计算用户期望的 4×4 齐次变换矩阵
        R_expected = self._compute_expected_matrix(euler_angles, translation)
        M = R_expected

        # 提取旋转矩阵（3×3）和平移向量
        R = [[M[i][j] for j in range(3)] for i in range(3)]
        t = [M[i][3] for i in range(3)]

        # 计算平面原点和 U/V 方向（单位：厘米，t 已在 _compute_expected_matrix 中转换）
        # 原点：平移向量
        p0_x = t[0]
        p0_y = t[1]
        p0_z = t[2]
        # R 的第 1/2 列分别是草图局部 X/Y 轴在世界系中的方向
        ux, uy, uz = R[0][0], R[1][0], R[2][0]
        vx, vy, vz = R[0][1], R[1][1], R[2][1]

        # 创建草图并读取 transform（合并为一次调用以提高性能）
        result = self.execute({
            "operation": "execute_python",
            "code": f"""
import adsk.core
import adsk.fusion
app = adsk.core.Application.get()
design = adsk.fusion.Design.cast(app.activeProduct)
root = design.rootComponent
# 创建具有完整 U/V 方向的几何平面
_origin = adsk.core.Point3D.create({p0_x!r}, {p0_y!r}, {p0_z!r})
    _u = adsk.core.Vector3D.create({ux!r}, {uy!r}, {uz!r})
    _v = adsk.core.Vector3D.create({vx!r}, {vy!r}, {vz!r})
    _plane_geom = adsk.core.Plane.createUsingDirections(_origin, _u, _v)
    # 用几何平面创建构造平面
    _inp = root.constructionPlanes.createInput()
    _inp.setByPlane(_plane_geom)
    _plane = root.constructionPlanes.add(_inp)
    # 在该平面上创建草图
    {store_key} = root.sketches.add(_plane)
# 读取草图的 transform 矩阵
t = {store_key}.transform
matrix = []
for i in range(4):
    row = [t.getCell(i, j) for j in range(4)]
    matrix.append(row)
print(matrix)
"""
        })

        # 解析 Fusion 360 返回的 transform 矩阵
        import ast
        data = result.get("data", {})
        stdout = data.get("stdout", "")
        lines = stdout.strip().split("\n")
        matrix_str = lines[-1] if lines else ""
        R_actual = ast.literal_eval(matrix_str.strip())

        # 计算最终变换矩阵：H = R_actual^(-1) × R_expected
        R_actual_inv = self._invert_homogeneous_matrix(R_actual)
        H = self._multiply_matrices(R_actual_inv, R_expected)

        # 存储齐次变换矩阵
        self._sketch_transforms[store_key] = {
            "homogeneous_matrix": H
        }

    def _create_sketch_by_euler2(
        self,
        store_key: str,
        euler_angles: tuple[float, float, float],
        translation: tuple[float, float, float],
    ):
        """ZYX 欧拉角 + 平移 → setByThreePoints → 草图。

        算法：
        1. 计算 4×4 齐次变换矩阵（旋转 + 平移）
        2. 用变换矩阵计算三个点：
           - 原点 (0,0,0) → 平面原点
           - X轴点 (1,0,0) → 定义 X 方向
           - Y轴点 (0,1,0) → 定义 Y 方向
        3. 用 setByThreePoints 创建构造平面
        4. 在该平面上创建草图
        """
        # 计算用户期望的 4×4 齐次变换矩阵
        R_expected = self._compute_expected_matrix(euler_angles, translation)
        M = R_expected 

        # 提取旋转矩阵（3×3）和平移向量
        R = [[M[i][j] for j in range(3)] for i in range(3)]
        t = [M[i][3] for i in range(3)]

        # 计算三个点的位置（单位：厘米，t 已在 _compute_expected_matrix 中转换）
        # 原点：平移向量
        p0_x = t[0]
        p0_y = t[1]
        p0_z = t[2]

        # X轴方向点：原点 + 旋转矩阵第一列（表示沿旋转后 X 轴 1cm）
        p1_x = t[0] + R[0][0]
        p1_y = t[1] + R[1][0]
        p1_z = t[2] + R[2][0]

        # Y轴方向点：原点 + 旋转矩阵第二列（表示沿旋转后 Y 轴 1cm）
        p2_x = t[0] + R[0][1]
        p2_y = t[1] + R[1][1]
        p2_z = t[2] + R[2][1]

        # 创建草图并读取 transform（合并为一次调用以提高性能）
        result = self.execute({
            "operation": "execute_python",
            "code": f"""
import adsk.core
app = adsk.core.Application.get()
design = app.activeProduct
root = design.rootComponent
# 先在 XY 平面创建临时草图，用于添加三个草图点
_temp_sketch = root.sketches.add(root.xYConstructionPlane)
# 创建三个草图点
_pos0 = adsk.core.Point3D.create({p0_x!r}, {p0_y!r}, {p0_z!r})
_pos1 = adsk.core.Point3D.create({p1_x!r}, {p1_y!r}, {p1_z!r})
_pos2 = adsk.core.Point3D.create({p2_x!r}, {p2_y!r}, {p2_z!r})
_sp0 = _temp_sketch.sketchPoints.add(_pos0)
_sp1 = _temp_sketch.sketchPoints.add(_pos1)
_sp2 = _temp_sketch.sketchPoints.add(_pos2)
# 用三个草图点创建构造平面
_inp = root.constructionPlanes.createInput()
_inp.setByThreePoints(_sp0, _sp1, _sp2)
_plane = root.constructionPlanes.add(_inp)
# 在该平面上创建草图
{store_key} = root.sketches.add(_plane)
# 读取草图的 transform 矩阵
t = {store_key}.transform
matrix = []
for i in range(4):
    row = [t.getCell(i, j) for j in range(4)]
    matrix.append(row)
print(matrix)
"""
        })

        # 解析 Fusion 360 返回的 transform 矩阵
        import ast
        data = result.get("data", {})
        stdout = data.get("stdout", "")
        lines = stdout.strip().split("\n")
        matrix_str = lines[-1] if lines else ""
        R_actual = ast.literal_eval(matrix_str.strip())

        # 计算最终变换矩阵：H = R_actual^(-1) × R_expected
        R_actual_inv = self._invert_homogeneous_matrix(R_actual)
        H = self._multiply_matrices(R_actual_inv, R_expected)

        # 存储齐次变换矩阵
        self._sketch_transforms[store_key] = {
            "homogeneous_matrix": H
        }
