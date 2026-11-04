# 坐标转换最终实现方案

## 问题总结

当前 `euler_angles` 参数创建的非标准平面，无法控制草图的完整坐标系方向（X/Y 轴方向不确定），导致用户输入的局部坐标映射到世界坐标时方向错误。

## 解决方案

**核心思路**：始终在 XY 平面创建草图，在添加基元时将用户坐标转换为世界坐标（3D）。

### 关键发现

1. Fusion 360 的 Point3D 接受 3D 坐标，即使在 2D 草图中
2. Fusion 360 会自动检测几何实际所在的平面
3. Fusion 360 会自动计算正确的拉伸/旋转/扫掠方向
4. 无需手动指定操作方向

### 转换公式

```
P_world = R * [x_user, y_user, 0]^T + T
```

其中：
- `R` = ZYX 欧拉角旋转矩阵（由 euler_angles 计算）
- `T` = 平移向量（translation 参数）
- `[x_user, y_user, 0]` = 用户输入的局部坐标（z=0）

## 实现步骤

### 步骤 1：修改 MCPSketch 类

**文件**：`fusion360/mcp_bridge/mcp_sketch.py`

#### 1.1 添加变换矩阵存储

```python
class MCPSketch(MCPBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sketch_refs: list[str] = []
        self._sketch_transforms: dict[str, dict] = {}  # 新增
```

#### 1.2 修改 create_sketch 方法

```python
def create_sketch(self, plane=None, euler_angles=None, translation=None):
    # ... 参数验证 ...
    
    if euler_angles is not None:
        # 始终在 XY 平面创建草图
        store_key = self._create_sketch_on_xy_plane()
        
        # 计算并存储变换矩阵
        R = _zyx_rotation_matrix(*euler_angles)
        T = translation if translation else (0, 0, 0)
        
        self._sketch_transforms[store_key] = {
            "rotation": R,      # 3x3 旋转矩阵
            "translation": T,   # 3D 平移向量
        }
    else:
        # 标准平面，不需要变换
        store_key = self._create_sketch_on_standard_plane(plane)
    
    return store_key
```

#### 1.3 添加辅助方法

```python
def _create_sketch_on_xy_plane(self):
    """在 XY 平面创建草图"""
    store_key = f"sketch_{len(self._sketch_refs)}"
    code = f"""
{store_key} = rootComp.sketches.add(rootComp.xYConstructionPlane)
"""
    self.execute({"operation": "execute_python", "code": code})
    self._sketch_refs.append(store_key)
    return store_key
```

### 步骤 2：修改 MCPPrimitives 类

**文件**：`fusion360/mcp_bridge/mcp_primitives.py`

#### 2.1 添加坐标转换方法

```python
def _transform_point(self, point: tuple, sketch_ref: str) -> tuple:
    """
    将用户局部坐标转换为世界坐标
    
    Args:
        point: (x, y) 或 (x, y, z) 用户坐标
        sketch_ref: 草图引用
    
    Returns:
        (x, y, z) 世界坐标
    """
    if sketch_ref not in self._sketch_transforms:
        # 标准平面，不需要转换
        # 但需要确保返回 3D 坐标
        if len(point) == 2:
            return (point[0], point[1], 0)
        return point
    
    transform = self._sketch_transforms[sketch_ref]
    R = transform["rotation"]
    T = transform["translation"]
    
    # 提取用户坐标
    x_user = point[0]
    y_user = point[1]
    z_user = 0  # 用户坐标始终在局部 XY 平面上
    
    # 应用旋转：P_rotated = R * [x, y, 0]^T
    x_world = R[0][0] * x_user + R[0][1] * y_user + R[0][2] * z_user
    y_world = R[1][0] * x_user + R[1][1] * y_user + R[1][2] * z_user
    z_world = R[2][0] * x_user + R[2][1] * y_user + R[2][2] * z_user
    
    # 应用平移：P_world = P_rotated + T
    x_world += T[0]
    y_world += T[1]
    z_world += T[2]
    
    return (x_world, y_world, z_world)
```

#### 2.2 修改所有 add_* 方法

需要修改的方法列表：
- `add_line(start, end, ...)`
- `add_circle(center, radius, ...)`
- `add_arc(center, start, end, ...)`
- `add_ellipse(center, major_axis, minor_axis, ...)`
- `add_elliptical_arc(...)`
- `add_nurbs(points, ...)`

**示例：add_line**

```python
def add_line(self, start, end, sketch_ref=None):
    sketch_ref = sketch_ref or self._sketch_refs[-1]
    
    # 转换坐标
    start_3d = self._transform_point(start, sketch_ref)
    end_3d = self._transform_point(end, sketch_ref)
    
    # 转换为 cm
    start_cm = self._to_cm(start_3d)
    end_cm = self._to_cm(end_3d)
    
    # 创建线
    store_key = f"line_{self._get_next_id()}"
    code = f"""
{store_key} = {sketch_ref}.sketchCurves.sketchLines.addByTwoPoints(
    adsk.core.Point3D.create({start_cm[0]}, {start_cm[1]}, {start_cm[2]}),
    adsk.core.Point3D.create({end_cm[0]}, {end_cm[1]}, {end_cm[2]})
)
"""
    self.execute({"operation": "execute_python", "code": code})
    return store_key
```

**示例：add_circle**

```python
def add_circle(self, center, radius, sketch_ref=None):
    sketch_ref = sketch_ref or self._sketch_refs[-1]
    
    # 转换中心点坐标
    center_3d = self._transform_point(center, sketch_ref)
    center_cm = self._to_cm(center_3d)
    radius_cm = self._to_cm(radius)
    
    store_key = f"circle_{self._get_next_id()}"
    code = f"""
{store_key} = {sketch_ref}.sketchCurves.sketchCircles.addByCenterRadius(
    adsk.core.Point3D.create({center_cm[0]}, {center_cm[1]}, {center_cm[2]}),
    {radius_cm}
)
"""
    self.execute({"operation": "execute_python", "code": code})
    return store_key
```

### 步骤 3：验证测试

**文件**：`result/test_coordinate_transform_validation.py`

测试用例：
1. 测试不同 euler_angles 组合
2. 在草图上绘制已知几何（如矩形）
3. 拉伸后读取边界框
4. 验证世界坐标是否符合预期

```python
test_cases = [
    # (euler_angles, translation, expected_bbox)
    ((0, 0, 0), (0, 0, 0), {...}),      # 无旋转
    ((90, 0, 0), (0, 0, 0), {...}),     # 绕 X 轴旋转 90°
    ((0, 90, 0), (0, 0, 0), {...}),     # 绕 Y 轴旋转 90°
    ((0, 0, 90), (0, 0, 0), {...}),     # 绕 Z 轴旋转 90°
    ((30, 60, 45), (10, 20, 30), {...}),# 复杂旋转 + 平移
]
```

## 需要修改的文件清单

1. `fusion360/mcp_bridge/mcp_sketch.py`
   - 添加 `_sketch_transforms` 字典
   - 修改 `create_sketch()` 方法
   - 添加 `_create_sketch_on_xy_plane()` 方法

2. `fusion360/mcp_bridge/mcp_primitives.py`
   - 添加 `_transform_point()` 方法
   - 修改 `add_line()` 方法
   - 修改 `add_circle()` 方法
   - 修改 `add_arc()` 方法
   - 修改 `add_ellipse()` 方法
   - 修改 `add_elliptical_arc()` 方法
   - 修改 `add_nurbs()` 方法

3. `result/test_coordinate_transform_validation.py`（新建）
   - 创建验证测试

4. `fusion360/docs/tool_spec.md`
   - 更新 `create_sketch` 的 `euler_angles` 参数说明

## 实现优先级

1. **高优先级**（核心功能）
   - MCPSketch 的变换矩阵存储
   - MCPPrimitives 的 _transform_point() 方法
   - add_line() 和 add_circle() 的修改

2. **中优先级**（常用功能）
   - add_arc() 的修改
   - add_ellipse() 的修改

3. **低优先级**（不常用）
   - add_elliptical_arc() 的修改
   - add_nurbs() 的修改

## 预期效果

实现后：
- ✅ 用户使用 `euler_angles` 参数时，输入的局部坐标会正确映射到世界坐标
- ✅ 拉伸/旋转/扫掠方向自动正确（由 Fusion 360 自动计算）
- ✅ 对外接口保持不变
- ✅ 标准平面（XY/XZ/YZ）不受影响

## 注意事项

1. **单位转换**：`_to_cm()` 方法需要支持 3D 坐标
2. **向后兼容**：标准平面创建的草图不应受影响
3. **错误处理**：如果 sketch_ref 不存在于 _sketch_transforms，应使用默认行为
4. **性能**：矩阵运算开销很小，不需要特别优化
