# MCP Bridge — CORE API REFERENCE

所有长度 **mm**，所有角度 **度**。
如果一个草图平面需要沿两个方向拉伸，则应该偏移草图平面使其单向拉伸。
---

## 草图

### `create_sketch(plane="XY", offset=0.0, *, euler_angles=None, translation=(0,0,0)) → str`
创建草图平面，返回草图 ref（如 `"sketch_0"`）。返回的 ref 会自动追踪，后续 `add_*` / `extrude` 等操作可省略 `sketch_ref` 参数，默认使用最近创建的草图。

两种互斥模式：

**基准平面模式**（默认，优先使用）：
- `plane`：`"XY"` / `"XZ"` / `"YZ"`
- `offset`：沿法向偏移，mm
- 草图局部坐标 → 全局坐标映射：
  - `XY`：U → 全局 X，V → 全局 Y，法向 → +Z
  - `XZ`：U → 全局 X，V → 全局 Z，法向 → +Y
  - `YZ`：U → 全局 Y，V → 全局 Z，法向 → +X
- **跨平面建模注意**：XZ/YZ 平面的 `offset` 参数沿法向偏移（XZ 沿 Y 轴，YZ 沿 X 轴）。在已有几何体上叠加新草图时，需根据已有几何的边界位置计算正确的 offset 值，避免平面落在几何体中间导致错位。

**任意朝向模式**（仅在需要斜面时使用）：
- `euler_angles=(rx, ry, rz)`：XYZ 外旋（等价于 ZYX 内旋，旋转矩阵 R = Rz·Ry·Rx），即先绕全局 X 轴转 rx°，再绕全局 Y 轴转 ry°，最后绕全局 Z 轴转 rz°
- `translation=(x, y, z)`：草图原点在全局坐标系中的位置，mm
- 此时 `plane` / `offset` 被忽略
- 草图局部坐标 → 全局坐标映射：U = R·[1,0,0]，V = R·[0,1,0]，法向 = R·[0,0,1]；草图内坐标 (u, v) 对应全局位置 = translation + u·U + v·V

---

## 草图图元
- 所有 add_* 方法中，若未显式提供 sketch_ref，则默认作用于最近创建的草图。
- 点坐标采用 (x, y) 格式，表示草图局部坐标系下的位置（单位：mm）。
- 所有方法直接返回对应几何实体的字符串引用（str），例如 "line_0"

### `add_line(start, end, sketch_ref=None) → str`
添加直线段，返回 ref（如 `"line_0"`）。
- `start / end: tuple` — 端点坐标，mm

### `add_circle(center, radius: float, sketch_ref=None) → str`
添加圆，返回 ref（如 `"circle_0"`）。
- `center: tuple` — 圆心坐标，mm
- `radius: float` — 半径，mm，`> 0`

### `add_arc(start, along, end, sketch_ref=None) → str`
添加三点圆弧（起点 → 弧上中间点 → 终点），返回 ref（如 `"arc_0"`）。
- `start / along / end: tuple` — 坐标，mm

### `add_ellipse(center, major: float, minor: float, angle: float, sketch_ref=None) → str`
添加完整椭圆，返回 ref（如 `"ellipse_0"`）。
- `major / minor: float` — 半轴长，mm，`> 0`
- `angle: float` — 长轴相对草图 X 轴的旋转角，度

### `add_elliptical_arc(start, end, major: float, minor: float, angle: float, large_arc=False, sweep=True, sketch_ref=None) → str`
添加椭圆弧（SVG 参数风格），返回 ref（如 `"elliptical_arc_0"`）。
- `major / minor: float` — 半轴长，mm，`> 0`
- `angle: float` — 长轴旋转角，度
- `large_arc: bool` — `True` 取大弧（> 180°）
- `sweep: bool` — `True` 为逆时针

### `add_nurbs(degree: int, closed: bool, controls: list, weights=None, knots=None, sketch_ref=None) → str`
添加 NURBS 样条，返回 ref（如 `"nurbs_0"`）。
- `degree: int` — `>= 1`
- `controls: list` — 控制点列表，每项 `(x, y)` 或 `(x, y, z)`，mm；数量 `>= degree + 1`
- `weights: list` — 权重列表，长度等于控制点数；省略为非有理曲线
- `knots: list` — 节点向量，长度 `= len(controls) + degree + 1`

⚠️ `closed=True` 时必须显式传入 `knots`，否则抛出 `ValueError`。

### `get_entity_info(ref: str) → dict`
查询图元几何属性，返回 dict，所有长度 mm、角度度。

| `type` | 返回字段 |
|--------|---------|
| `"line"` | `start [x,y,z]`、`end [x,y,z]`、`mid [x,y,z]`、`length` |
| `"circle"` | `center [x,y,z]`、`radius`、`point_on [x,y,z]` |
| `"arc"` | `center`、`radius`、`start_pt`、`end_pt`、`mid_pt`、`start_angle`、`end_angle` |
| `"ellipse"` | `center`、`major_radius`、`minor_radius`、`major_axis [ux,uy,uz]`、`point_on` |
| `"elliptical_arc"` | `center`、`major_radius`、`minor_radius`、`major_axis`、`start_angle`、`end_angle`、`point_on` |
| `"nurbs"` | `degree`、`is_rational`、`control_points`、`knots`、`point_on` |

---

## 约束

### `add_constraint(constraint_type: str, entities: list, value: float = None, text_point=None, is_driving: bool = True) → bool`
`entities` 只能放已有 ref 字符串，不能构造未知字面量。
添加几何约束或尺寸约束，成功返回 `True`。

**几何约束（不需要 `value`）：**

| `constraint_type` | `entities` | 说明 |
|-------------------|------------|------|
| `"horizontal"` | `[line_ref]` 或 `[pt_ref, pt_ref]` | 线水平；或两点水平对齐 |
| `"vertical"` | `[line_ref]` 或 `[pt_ref, pt_ref]` | 线竖直；或两点竖直对齐 |
| `"parallel"` | `[line_ref, ...]` | 多线平行（anchor-first） |
| `"perpendicular"` | `[line_ref, line_ref]` | 两线垂直 |
| `"equal"` | `[curve_ref, ...]` | 等长或等半径（anchor-first） |
| `"tangent"` | `[curve_ref, curve_ref]` | 两曲线相切 |
| `"normal"` | `[line_ref, line_ref]` 或 `[line_ref, curve_ref]` | 两线垂直；或将曲线圆心约束到线上 |
| `"coincident"` | `[pt_ref, pt_ref, ...]` | 点重合（anchor-first） |
| `"concentric"` | `[curve_ref, curve_ref]` | 同心 |
| `"fixed"` / `"fix"` | `[entity_ref]` | 固定实体位置 |

**尺寸约束（需要 `value`）：**

| `constraint_type` | `entities` | `value` 单位 | 说明 |
|-------------------|------------|-------------|------|
| `"distance"` | `[line_ref]` | mm | 约束线段长度 |
| `"distance"` | `[entity_a, entity_b]` | mm | 点-点距离或点/线偏移距离 |
| `"angle"` | `[line_ref, line_ref]` | 度 | 两线夹角 |
| `"radius"` | `[circle/arc_ref]` | mm | 圆或弧半径 |
| `"diameter"` | `[circle/arc_ref]` | mm | 圆或弧直径 |

点引用示例：`line_ref + ".start"` / `line_ref + ".end"` / `circle_ref + ".center"`

## 三维实体
axis表示定义在**全局坐标系（world coordinate system）**下旋转轴
### `extrude(distance: float, operation: str, sketch_ref=None) → str`
拉伸封闭轮廓生成实体。
- `distance: float` — 拉伸距离，mm；正值沿草图法线，负值反向
- `operation: str` — `"NewBody"` / `"Join"` / `"Cut"` / `"Intersect"`

返回：`"extrude_0"`

### `revolve(axis=None, axis_point1 = None, axis_point2 = None, angle: float = 360.0, sketch_ref=None, operation: str = "NewBody",) → str`
旋转轮廓生成旋转体。
- `axis: str` — `"X"` / `"Y"` / `"Z"`，优先级高于两点定义
- `axis_point1 / axis_point2: tuple` — 旋转轴两点坐标，mm；`axis` 非 `None` 时忽略
- `angle: float` — 旋转角度，度，默认 360
- `operation: str` — `"NewBody"` / `"Join"` / `"Cut"` / `"Intersect"`

返回：`"revolve_0"`

### `helix_sweep(axis, pitch: float, turns: float, handedness: str = "Right", sketch_ref=None, operation: str = "NewBody") → str`
沿螺旋路径扫掠轮廓，生成弹簧等。
- `axis: list` — `[[x1,y1,z1], [x2,y2,z2]]`，两点定义轴（mm）；
- `pitch: float` — 螺距，mm/圈，`> 0`
- `turns: float` — 圈数，`> 0`
- `handedness: str` — `Right` 沿 p1→p2 方向上升，`Left` 反向

返回：`"helix_sweep_0"`

---

## 边特征
### `fillet(radius_mm: float, edge_point=None,) → dict`
- `radius_mm: float` — 圆角半径（mm）
- `edge_point: tuple` — `(x, y, z)` mm，全局坐标系下的点；该点必须严格落在目标边的曲线上。当使用 edge_point 选边时，应优先选择目标边的midpoint，避免使用圆心、顶点、边端点或仅靠近边但不在边上的点
- 一次调用只会作用于一条边；如果需要对多条边做圆角，必须分别调用多次。
### `chamfer(distance_mm: float, edge_point=None) → dict`
- `distance_mm: float` — 倒角距离（mm）
- `edge_point: tuple` — `(x, y, z)` mm，全局坐标系下的点；该点必须严格落在目标边的曲线上。当使用 edge_point 选边时，应优先选择目标边的midpoint，避免使用圆心、顶点、边端点或仅靠近边但不在边上的点
- 一次调用只会作用于一条边；如果需要对多条边做圆角，必须分别调用多次。

## 螺纹

### `add_thread(is_internal, designation=None, handedness="Right", full_length=True, thread_length=None, thread_offset=0.0, thread_location="start", body_ref=None, face_point=None, num=1) → str`
对圆柱面施加螺纹，如果螺纹和圆角倒角同时出现，螺纹通常在其之后添加。支持一次调用给多个孔加螺纹。
- `is_internal: bool` — True=内螺纹（选最小半径圆柱面），False=外螺纹（选最大面积圆柱面）
- `designation: str` — ISO 公制规格如 `"M10x1.5"`；None 时根据圆柱直径自动推断
- `handedness: str` — `"Right"` / `"Left"`
- `full_length: bool` — True=整段起牙；False=部分螺纹，需配合 thread_length
- `thread_length: float` — 螺纹长度 mm；仅 full_length=False 时有效
- `thread_offset: float` — 螺纹起点距端面偏移 mm，默认 0
- `thread_location: str` — `"start"` / `"end"`，偏移从哪端量
- `body_ref` — None=最后一个实体；`"extrude_0"`=特征第一个实体
- `face_point` — 单个坐标 `(x,y,z)` 或坐标列表 `[(x1,y1,z1), (x2,y2,z2), ...]`，指定目标圆柱面位置（mm）；None 时按半径/面积自动选择。**face_point 和 num 只有一个起效果，face_point 优先**
- `num: int` — 自动选择的圆柱面数量（仅 face_point=None 时有效），默认 1。内螺纹选半径最小的 num 个，外螺纹选面积最大的 num 个

返回：`"thread_0"`

**示例**：
```python
# 示例 1：单孔，自动推断规格，全长右旋螺纹（最常用）
cad.add_thread(is_internal=True)

# 示例 2：4 个孔自动选择，指定规格和旋向
cad.add_thread(is_internal=True, designation="M5x0.8", handedness="Left", num=4)

# 示例 3：精确指定多个孔位置，部分螺纹（从起点偏移 2mm，长度 10mm）
cad.add_thread(is_internal=True, designation="M8x1.25",
               face_point=[(22,12,15), (-22,12,15), (-22,-12,15), (22,-12,15)],
               full_length=False, thread_length=10.0, thread_offset=2.0, thread_location="start")

# 示例 4：外螺纹，指定实体，从末端测量
cad.add_thread(is_internal=False, designation="M10x1.5", body_ref="extrude_0",
               full_length=False, thread_length=15.0, thread_location="end")
```

---

## 代码样板

### 圆柱体
```python
sk = cad.create_sketch("XY")
c = cad.add_circle((0, 0), 5.0, sk)
cad.add_constraint("diameter", [c], value=10.0)
cad.extrude(distance=15.0, operation="NewBody", sketch_ref=sk)
```

### 矩形板（带等长约束和尺寸约束）
```python
sk = cad.create_sketch("XY")
l1 = cad.add_line((-10, -10), (10, -10))
l2 = cad.add_line((10, -10), (10, 10))
l3 = cad.add_line((10, 10), (-10, 10))
l4 = cad.add_line((-10, 10), (-10, -10))
cad.add_constraint("horizontal", [l1, l3])
cad.add_constraint("vertical", [l2, l4])
cad.add_constraint("equal", [l1, l2, l3, l4])
cad.add_constraint("distance", [l1], value=20.0)
cad.extrude(distance=5.0, operation="NewBody", sketch_ref=sk)
```

### 旋转体（轮廓绕 Y 轴整圈旋转）
```python
sk = cad.create_sketch("XY")
l1 = cad.add_line((0, 0), (5, 0), sk)
l2 = cad.add_line((5, 0), (8, 20), sk)
l3 = cad.add_line((8, 20), (0, 20), sk)
l4 = cad.add_line((0, 20), (0, 0), sk)
cad.auto_close_loop(sk)
cad.revolve(None, None, angle=360, sketch_ref=sk, axis="Y", operation="NewBody")
```

### 内螺纹（六角螺母 φ6 孔，M6x1）
```python
# 先建六角体，再 Cut 孔，最后加内螺纹
# ... 建体和 Cut 步骤 ...
cad.add_thread(is_internal=True, designation="M6x1")
```
