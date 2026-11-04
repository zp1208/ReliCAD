# MCP Bridge API Reference

MCP Bridge 是连接 Python 代码与 Fusion 360 的客户端库。通过 `CAD_MCP` 实例调用所有接口。

```python
from fusion360.mcp_bridge.CAD_MCP import CAD_MCP
cad = CAD_MCP()
```

**单位约定：** 所有长度参数及返回值单位为 **毫米 (mm)**，角度单位为 **度 (°)**。Fusion 360 内部使用 cm/rad，库自动转换。

---

## 快速索引

| 类别 | 方法 | 简介 |
|------|------|------|
| 连接 | `ping()` | 检查连接 |
| 连接 | `clear()` | 清空设计 |
| 连接 | `detach()` | 断开连接 |
| 草图 | `create_sketch(plane, offset)` | 创建草图平面 |
| 图元 | `add_line(start, end)` | 添加直线 |
| 图元 | `add_circle(center, radius)` | 添加圆 |
| 图元 | `add_arc(start, along, end)` | 添加三点弧 |
| 图元 | `add_ellipse(center, major, minor, angle)` | 添加椭圆 |
| 图元 | `add_elliptical_arc(start, end, major, minor, angle)` | 添加椭圆弧 |
| 图元 | `add_nurbs(degree, closed, controls)` | 添加 NURBS 曲线 |
| 图元 | `get_entity_info(ref)` | 查询图元几何属性 |
| 约束 | `add_constraint(type, entities, value)` | 添加几何/尺寸约束 |
| 约束 | `auto_close_loop(sketch_ref, tolerance)` | 自动闭合轮廓缺口 |
| 实体 | `extrude(distance, operation)` | 拉伸 |
| 实体 | `revolve(axis_point1, axis_point2, angle)` | 旋转体 |
| 实体 | `helix_sweep(axis, pitch, turns)` | 螺旋扫掠 |
| 边特征 | `query_edges(body_ref)` | 查询实体边 |
| 边特征 | `fillet(radius_mm, edge_indices)` | 圆角 |
| 边特征 | `chamfer(distance_mm, edge_indices)` | 倒角 |
| 导出 | `export_step(filepath)` | 导出 STEP 文件 |
| 导出 | `export_view(filepath, width, height, orientation)` | 导出渲染视图 |
| 验证 | `validate_step_file(filepath, min_bytes)` | 验证 STEP 文件 |

---

## 连接管理

### `ping() -> bool`
检查 Fusion 360 是否可达。返回 `True` 表示连接正常。

### `clear() -> bool`
清空当前设计中所有几何体、草图、构建几何。返回 `True` 表示成功。

### `detach() -> None`
断开 MCP 会话。下次操作时自动重连。等同于 `close()`。

### `close() -> None`
停止 reader 线程并关闭连接，与 `detach()` 等效。工作流结束时调用。

---

## 草图

### `create_sketch(plane="XY", offset=0.0, *, euler_angles=None, translation=(0,0,0)) -> str`

创建草图平面，返回草图引用名（如 `"sketch_0"`），后续操作传入此引用。

**标准平面模式：**
```python
sk = cad.create_sketch("XY")          # XY 平面
sk = cad.create_sketch("XZ", offset=10.0)  # XZ 平面，Z 方向偏移 10 mm
sk = cad.create_sketch("YZ")          # YZ 平面
```

**任意平面模式（ZYX 欧拉角 + 平移）：**
```python
sk = cad.create_sketch(euler_angles=(0.0, 0.0, 45.0), translation=(0.0, 0.0, 20.0))
```

参数说明：
- `plane`：标准构造平面，可选 `"XY"`、`"XZ"`、`"YZ"`（用法一专用）
- `offset`：偏移距离（**mm**，沿平面法向）；用法一专用
- `euler_angles`：`(rx, ry, rz)` ZYX 欧拉角（度）；提供此参数时走用法二，忽略 `plane`/`offset`
- `translation`：`(x, y, z)` 平面原点坐标（**mm**）；用法二专用，默认 `(0, 0, 0)`

---

## 草图图元

所有图元方法的 `sketch_ref` 参数省略时自动使用最近创建的草图。

### `add_line(start, end, sketch_ref=None) -> str`

添加直线段。坐标为 `(x, y)` 或 `(x, y, z)`，单位 mm。

```python
line = cad.add_line((0, 0), (20, 0), sk)
```

### `add_circle(center, radius: float, sketch_ref=None) -> str`

添加圆。`center` 为 `(x, y)` 坐标，`radius` 单位 mm。

```python
circle = cad.add_circle((10, 10), 5.0, sk)
```

### `add_arc(start, along, end, sketch_ref=None) -> str`

添加三点弧：起点 → 中间点 → 终点。

```python
arc = cad.add_arc((0, 30), (10, 40), (20, 30), sk)
```

### `add_ellipse(center, major: float, minor: float, angle: float, sketch_ref=None) -> str`

添加完整椭圆。`major`/`minor` 为半轴长（mm），`angle` 为主轴旋转角（°）。

```python
ellipse = cad.add_ellipse((40, 30), 10, 5, 30, sk)
```

### `add_elliptical_arc(start, end, major: float, minor: float, angle: float, large_arc=False, sweep=True, sketch_ref=None) -> str`

添加椭圆弧（SVG 参数风格）。

### `add_nurbs(degree: int, closed: bool, controls: list, weights=None, knots=None, sketch_ref=None) -> str`

添加 NURBS 样条曲线。`controls` 为控制点列表（mm），每个元素为 `(x, y)` 或 `(x, y, z)`。

> **注意：** `closed=True` 时必须显式提供 `knots`，否则抛出 `ValueError`。

```python
nurbs = cad.add_nurbs(
    degree=3,
    closed=False,
    controls=[(0, 0, 0), (5, 10, 0), (15, 10, 0), (20, 0, 0)],
    sketch_ref=sk,
)
```

### `get_entity_info(ref: str) -> dict`

查询草图图元几何属性。`ref` 为 `add_*` 方法返回的引用名。

返回字段（所有长度单位 mm，角度单位度）：

| type | 字段 |
|------|------|
| `"line"` | `start [x,y,z]`、`end [x,y,z]`、`mid [x,y,z]`、`point_on [x,y,z]`（=mid）、`length` |
| `"circle"` | `center [x,y,z]`、`radius`、`point_on [x,y,z]` |
| `"arc"` | `center [x,y,z]`、`radius`、`start_pt`、`end_pt`、`mid_pt`、`point_on`（=mid_pt）、`start_angle`、`end_angle` |
| `"ellipse"` | `center [x,y,z]`、`major_radius`、`minor_radius`、`major_axis [ux,uy,uz]`（单位向量）、`point_on`（椭圆上 45° 处，非长轴端点） |
| `"elliptical_arc"` | `center [x,y,z]`、`major_radius`、`minor_radius`、`major_axis [ux,uy,uz]`、`start_angle`、`end_angle`、`point_on`（弧中点） |
| `"nurbs"` | `degree`、`is_rational: bool`、`control_points [[x,y,z],…]`、`knots [float,…]`、`point_on`（曲线中点，失败为 `null`） |

---

## 约束

### `add_constraint(constraint_type: str, entities: list, value: float = None, text_point=None, is_driving: bool = True) -> bool`

添加几何约束或尺寸约束。返回 `True` 表示成功。

**几何约束（不需要 `value`）：**

| constraint_type | 含义 | entities 说明 |
|----------------|------|---------------|
| `"horizontal"` | 水平约束 | `[line_ref]` |
| `"vertical"` | 垂直约束 | `[line_ref]` |
| `"parallel"` | 平行约束 | `[line_ref1, line_ref2]` |
| `"perpendicular"` | 垂直约束 | `[line_ref1, line_ref2]` |
| `"equal"` | 等长/等径 | `[entity1, entity2]` |
| `"tangent"` | 相切约束 | `[curve1, curve2]` |
| `"normal"` | 垂直约束（line+line→垂直；line+曲线→曲线圆心重合到线上） | `[line, line]` 或 `[line, curve]` |
| `"coincident"` | 点重合 | `["line1.end", "line2.start"]` |
| `"concentric"` | 同心约束 | `[circle1, circle2]` |
| `"fixed"` / `"fix"` | 固定约束（两者等效） | `[entity]` |

**尺寸约束（需要 `value`）：**

| constraint_type | value 含义 | entities 说明 |
|----------------|-----------|---------------|
| `"distance"` | 距离（mm） | 1 个实体：`[line_ref]`（测量线段长度）；2 个实体：`[point1, point2]`（点-点距离）或 `[line, point]`（点到线距离） |
| `"angle"` | 角度（°） | `[line1, line2]` |
| `"radius"` | 半径（mm） | `[circle_ref]` |
| `"diameter"` | 直径（mm） | `[circle_ref]` |

**端点引用格式：**
- `"line_1.start"` — 直线起点
- `"line_1.end"` — 直线终点
- `"circle_1.center"` — 圆心点

```python
cad.add_constraint("horizontal", [h_line])
cad.add_constraint("coincident", ["line_1.end", "line_2.start"])
cad.add_constraint("distance", [dist_line], value=20.0)
cad.add_constraint("angle", [line1, line2], value=45.0)
```

### `auto_close_loop(sketch_ref=None, tolerance=None) -> dict`

自动检测草图端点缺口并添加重合约束闭合轮廓。

- `tolerance`：端点聚类容差，单位 **mm**，默认 `0.0001`。

返回：
```python
{
    "ok": True,
    "sketch_ref": str,
    "performed": bool,
    "tolerance_used": float,        # mm
    "pre_profile_count": int,
    "post_profile_count": int,
    "candidate_point_count": int,
    "cluster_count": int,
    "clusters": [...],
    "applied_count": int,
    "skipped_count": int,
}
```

```python
result = cad.auto_close_loop(sk)               # 使用默认 0.0001 mm
result = cad.auto_close_loop(sk, tolerance=0.5)  # 指定 0.5 mm
# result["ok"] == True 表示成功闭合
```

---

## 三维实体

### `extrude(distance: float, operation: str, sketch_ref=None) -> str`

将草图封闭轮廓沿法线方向拉伸生成实体。

- `distance`：拉伸距离（mm，正值沿草图法线）
- `operation`：`"NewBody"` / `"Join"` / `"Cut"` / `"Intersect"`

返回：`"extrude_0"`

```python
body_ref = cad.extrude(distance=10, operation="NewBody", sketch_ref=sk)  # 用于后续 query_edges、fillet 等操作
```

### `revolve(axis_point1, axis_point2, angle=360.0, sketch_ref=None, operation="NewBody", axis=None) -> str`

将草图轮廓绕轴旋转生成旋转体。

- `axis`：`"X"` / `"Y"` / `"Z"` 直接指定坐标轴（优先级高于两点定义）
- `axis_point1/2`：两点定义旋转轴（mm），`axis` 非 None 时忽略
- `angle`：旋转角度（°，默认 360）

返回：`"revolve_0"`

```python
# 使用命名轴
ref = cad.revolve(None, None, angle=360, sketch_ref=sk, axis="X")

# 使用两点定义轴
ref = cad.revolve((0, 0, 0), (0, 0, 10), angle=360, sketch_ref=sk)
```

### `helix_sweep(axis, pitch: float, turns: float, handedness="Right", sketch_ref=None, operation="NewBody") -> str`

沿螺旋路径扫掠草图轮廓，生成螺纹、弹簧等。

- `axis`：`[[ox, oy, oz], [dx, dy, dz]]`，原点坐标（mm）+ 方向向量（自动归一化）
- `pitch`：螺距（mm/圈，> 0）
- `turns`：圈数（> 0）
- `handedness`：`"Right"`（右旋）/ `"Left"`（左旋）

返回：`"helix_sweep_0"`

```python
ref = cad.helix_sweep(
    axis=[[0, 0, 0], [0, 0, 1]],
    pitch=5,
    turns=3,
    handedness="Right",
    sketch_ref=sk,
    operation="NewBody",
)
```

---

## 边特征（圆角 / 倒角）

### `query_edges(body_ref=None) -> dict`

查询实体的所有边信息，用于后续圆角/倒角选边。

返回：
```python
{
    "ok": True,
    "edges": [
        {
            "index": 0,
            "type": "line" | "arc" | "circle" | ...,
            "length_mm": float,
            "midpoint_mm": [x, y, z],
            "vertices_mm": [[x1,y1,z1], [x2,y2,z2]],
            "adjacent_face_normals": [...],
            "adjacent_face_types": [...]
        },
        ...
    ]
}
```

```python
edges_info = cad.query_edges(body_ref=body_ref)
# 通过 midpoint_mm 定位目标边的 index
edge_idx = edges_info["edges"][0]["index"]
```

### `fillet(radius_mm: float, edge_indices=None, edge_point=None, body_ref=None, is_tangent_chain=True) -> dict`

对指定边添加等半径圆角。

**选边方式（二选一）：**
- `edge_indices=[0, 1, ...]`：用 `query_edges` 返回的 index 选边
- `edge_point=(x, y, z)`：选取最近该点的边（mm）

返回：`{"ok": True, "ref": "fillet_0"}`

```python
result = cad.fillet(radius_mm=2.0, edge_indices=[edge_idx], body_ref=body_ref)
```

### `chamfer(distance_mm: float, edge_indices=None, edge_point=None, body_ref=None, is_tangent_chain=True) -> dict`

对指定边添加等距倒角。参数与 `fillet` 相同。

返回：`{"ok": True, "ref": "chamfer_0"}`

---

## 导出与验证

### `export_step(filepath: str) -> dict`

将当前设计导出为 STEP 文件。

- `filepath`：输出文件的绝对路径（支持 Windows 反斜杠路径）

返回：`{"success": True}`

```python
result = cad.export_step(r"d:\output\part.step")
```

### `validate_step_file(filepath: str, min_bytes: int = 1) -> dict`

检查 STEP 文件是否存在且满足最小文件大小要求。用于 `export_step` 后的完整性验证。

返回：
```python
{
    "ok": bool,          # 文件存在且 >= min_bytes
    "filepath": str,     # 绝对路径（os.path.abspath 解析后）
    "exists": bool,
    "size_bytes": int,
    "min_bytes": int
}
```

```python
result = cad.validate_step_file(r"d:\output\part.step", min_bytes=100)
if result["ok"]:
    print(f"STEP 文件有效，大小 {result['size_bytes']} 字节")
```

### `export_view(filepath: str, width: int = 512, height: int = 512, orientation: str = "iso", transparent_background: bool = False, anti_aliasing: bool = True) -> dict`

捕获当前设计的渲染视图并保存为图片。

- `filepath`：输出图片绝对路径（`.png`、`.jpg` 等）
- `width` / `height`：图片尺寸（像素，默认 512×512）
- `orientation`：视角方向
- `transparent_background`：是否使用透明背景（默认 `False`，**推荐使用白色背景以确保 LLM 正确识别孔洞和边缘**）
- `anti_aliasing`：是否启用抗锯齿（默认 `True`，使边缘更平滑）

**关于背景选择：**
- **白色背景（默认）**：确保孔洞、倒角等细节在任何环境下都清晰可见，推荐用于 LLM 视觉验证
- **透明背景**：适合需要后期合成的场景，但可能在不同环境中被渲染为黑色/灰色，影响细节识别

**支持的 orientation 值：**

| 值 | 视角 |
|----|------|
| `"iso"` | 等轴测（右上，默认） |
| `"iso_top_right"` | 等轴测右上 |
| `"iso_top_left"` | 等轴测左上 |
| `"iso_bottom_right"` | 等轴测右下 |
| `"iso_bottom_left"` | 等轴测左下 |
| `"front"` | 正面 |
| `"back"` | 背面 |
| `"left"` | 左视 |
| `"right"` | 右视 |
| `"top"` | 俯视 |
| `"bottom"` | 仰视 |

返回：`{"success": True}`

```python
# 默认白色背景（推荐用于 LLM 验证）
cad.export_view(r"d:\output\view.png", width=1024, height=768, orientation="front")

# 透明背景（用于图像合成）
cad.export_view(r"d:\output\view_transparent.png", width=1024, height=768,
                orientation="front", transparent_background=True)
```

---

## 完整工作流示例

```python
from fusion360.mcp_bridge.CAD_MCP import CAD_MCP

cad = CAD_MCP()

# 1. 清空设计
cad.clear()

# 2. 创建草图并绘制矩形
sk = cad.create_sketch("XY")
cad.add_line((0, 0), (20, 0), sk)
cad.add_line((20, 0), (20, 20), sk)
cad.add_line((20, 20), (0, 20), sk)
cad.add_line((0, 20), (0, 0), sk)

# 3. 拉伸为实体
body_ref = cad.extrude(distance=10, operation="NewBody", sketch_ref=sk)

# 4. 查询边并添加圆角
edges = cad.query_edges(body_ref=body_ref)
edge_idx = edges["edges"][0]["index"]
cad.fillet(radius_mm=2.0, edge_indices=[edge_idx], body_ref=body_ref)

# 5. 导出 STEP
cad.export_step(r"d:\output\part.step")
result = cad.validate_step_file(r"d:\output\part.step", min_bytes=100)
print("STEP 有效:", result["ok"])

# 6. 导出视图
cad.export_view(r"d:\output\view_iso.png", width=800, height=600, orientation="iso")
cad.export_view(r"d:\output\view_front.png", width=800, height=600, orientation="front")

cad.close()
```

---

## 错误处理

| 异常类型 | 触发条件 |
|---------|---------|
| `RuntimeError` | Fusion 360 执行失败（路径无效、无封闭轮廓等） |
| `ValueError` | 参数不合法（operation 不支持、axis 格式错误等） |
| `TimeoutError` | Fusion 360 未响应 |
| `KeyError` | 无效的图元引用 |
