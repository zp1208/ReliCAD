## 基元

### `add_ellipse`

- 输入：`centerPoint: list`，`major: float`，`minor: float`，`angle: 角度制`，`sketch_num: int = -1`
- 功能：在指定草图中创建椭圆。

### `add_elliptical_arc`

- 输入：`startPoint: list`，`endPoint: list`，`major: float`，`minor: float`，`angle: 角度制`，`large_arc: bool = False`，`sweep: bool = True`，`sketch_num: int = -1`
- 功能：根据端点、长短轴和旋转角创建椭圆弧。

### `add_nurbs`

- 输入：`degree: int`，`closed: bool`，`controls: list`，`weights: list | None = None`，`knots: list | None = None`，`sketch_num: int = -1`
- 功能：在指定草图中创建 NURBS 曲线。

### 所有add_*需要返回一个实体类，用于约束时的索引和获取基元的基本信息（至少要可以获得基元的中点）。
- 输出：
  返回结构化字典，包含：
  - entity_id: str （用于约束时索引）
  - entity_type: str
  - geometry: dict（起点、中点、终点、圆心、半径等）

## 约束

### `add_constraint`

- 输入：`type: str`，`entities: list`，`value = None`，`sketch_num: int = -1`，`text_point = None`，`is_driving: bool = True`，`extra = None`
- 输出：出现过约束时报错（需要具体的报错信息）；添加已有约束时自动跳过并警告
- 功能：为草图实体添加几何约束或尺寸约束。
- 垂直（Perpendicular）、平行（Parallel）、水平（Horizontal）、竖直（Vertical）、相等（Equal）、相切（Tangent）、法向（Normal）、重合（Coincident）、同心（Concentric）、固定（Fix/Fixed）、角度（Angle）、直径（Diameter）、半径（Radius）、距离（Distance）等

### `auto_close_loop`

- 输入：`sketch_num: int = -1`，`tolerance = None`
- 输出：添加约束的个数；是否存在异常
- 功能：自动分析草图开口端点并补充重合约束，帮助形成闭合轮廓（将草图中本身就重合的点自动加重合约束）。

## 旋转拉伸

### `revolve`

- 输入：`axisPoint1 = None`，`axisPoint2 = None`，`angle: float = 2*pi`，`sketch_num: int = -1`，`operation: str = "NewBody"`，`axis = None`，`start = None`，`end = None`，`target_body_index = None`
- 输出：成功响应，无固定 `data` 字段
- 功能：对草图轮廓执行旋转特征，可指定旋转轴、起止角和目标实体。

### `create_helix_sweep`

- 输入：`axis: list`，`pitch: float`，`turns: float`，`handedness: str = "Right"`，`sketch_num: int = -1`，`operation: str = "NewBody"`，`target_body_index = None`
- 输出：成功响应，无固定 `data` 字段
- 功能：将草图轮廓沿螺旋路径执行扫掠。


