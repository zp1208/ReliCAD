# CAD Agent 使用手册

## 项目简介

CAD Agent 是一个基于 AI 的自动化 3D 建模系统，可以将自然语言描述的零件需求自动转换为 Fusion 360 的 3D 模型。

**核心能力：**
- 自然语言理解：补全模糊的零件描述
- 自动规划：生成合理的建模步骤
- 代码生成：自动生成 Fusion 360 API 调用
- 视觉验证：多视角渲染 + AI 质检
- 自动纠错：执行失败时自动修复代码

---

## 环境准备

### 1. 安装 Conda 环境

```bash
# 创建环境（已完成）
conda create -n CAD_agent python=3.10 -y

# 激活环境
conda activate CAD_agent

# 安装依赖
pip install -r requirements.txt
pip install cadquery  # 必须单独安装
```

### 2. 启动 Fusion 360 Server

**这是运行 Agent 的必要前提！**

1. 打开 Fusion 360
2. 顶部菜单 → `工具` → `脚本和加载项`（或按 `Shift+S`）
3. 点击 `脚本` 标签 → `添加`
4. 选择路径：`D:\python_project\CAD_Agent\agent-master\fusion360\fusion360_tools\server`
5. 找到 `fusion360_server` 脚本，点击 `运行`

**验证 Server 是否启动：**
```bash
curl -X POST http://127.0.0.1:8080 -H "Content-Type: application/json" -d '{"command":"ping"}'
# 应返回：{"status": 200, "message": "Success processing ping command"}
```

---

## 基本使用

### 快速开始

```bash
# 1. 激活环境
conda activate CAD_agent

# 2. 确保 Fusion 360 Server 已启动

# 3. 运行 Agent（使用 UTF-8 编码避免中文乱码）
PYTHONIOENCODING=utf-8 python Agent.py
```

### 修改输入需求

编辑 `Agent.py` 第 89 行：

```python
# 默认示例
user_input = ("A technical 3D CAD model of a circular hubbed flange.")

# 修改为你的需求，例如：
user_input = "设计一个带 4 个螺栓孔的法兰，外径 100mm，厚度 10mm"
user_input = "Create a rectangular plate with a central hole"
user_input = "一个圆柱体，直径 50mm，高度 100mm，顶部有倒角"
```

**支持的特征类型：**
- 拉伸体（圆柱、矩形块）
- 旋转体（法兰、轴类零件）
- 孔（通孔、盲孔）
- 圆角（fillet）
- 倒角（chamfer）

**暂不支持：**
- 扫掠、放样
- 镜像、阵列（API 未提供）
- 多体布尔运算

---

## 输出文件说明

运行成功后会生成以下文件：

```
result/
├── fusion_generated.py        # 生成的 Fusion 360 API 调用代码
├── fusion_generated.step      # 导出的 3D 模型（STEP 格式）
└── render/                    # 4 视角渲染图
    ├── top.png               # 俯视图
    ├── front.png             # 正视图
    ├── right.png             # 右视图
    └── iso.png               # 等轴测图

logs/
└── cad_agent_YYYYMMDD_HHMMSS.log  # 完整运行日志
```

### 查看生成的代码

```bash
cat result/fusion_generated.py
```

示例输出：
```python
from fusion360.fusion360_tools.client.gym_env import GymEnv

def run_model():
    env = GymEnv(host="127.0.0.1", port=8080)
    env.client.clear()

    # 创建草图
    env.client.create_sketch(plane_type="xy", offset=0.0)
    env.client.add_circle(centerPoint=[0.0, 0.0], radius=50.0)

    # 拉伸
    env.client.create_extrude(distance=10.0, operation="new")

    # 导出
    env.client.export_step("result/fusion_generated.step")
```

---

## 工作流程详解

```
用户输入
   ↓
[1. ingest] 需求澄清
   ↓ 补全缺失参数、推断默认值
[2. planning] 建模规划
   ↓ 生成有序的建模步骤
[3. executable] 代码生成 + 执行
   ↓ 调用 Fusion 360 API
   ├─ 成功 → [4. val_success] 视觉验证
   │           ↓ 渲染 4 视角 + AI 质检
   │           ├─ 通过 → 结束 ✅
   │           └─ 不通过 → 回到 [2. planning]
   │
   └─ 失败 → [4. val_error] 错误修复
               ↓ 分析错误 + 生成修复指令
               回到 [3. executable]
```

**关键特性：**
- 最多循环 10 次（`recursion_limit=10`）
- 每个节点的输出都会保存到 `logs/` 目录
- 支持断点恢复（通过 `thread_id`）

---

## 配置说明

### LLM API 配置

通过环境变量 `CAD_AGENT_API_KEY` 配置密钥，不要把真实密钥写入源码或提交到 Git。修改环境变量后，请重新启动程序。

PowerShell 示例：

```powershell
$env:CAD_AGENT_API_KEY = "替换为轮换后的新密钥"
python Agent.py
```

API 地址由 `common/LLM.py` 中的 `DEFAULT_BASE_URL` 指定。密钥缺失时，程序会在创建 API 客户端之前提示配置错误。

**使用的模型：**
- 所有节点统一使用 `gemini-3-flash-preview`
- `temperature=0` 确保输出稳定

### 修改建模规则

编辑对应节点的 Prompt：

- **需求澄清规则**：`planning/RequirementsClarificationNode.py` 第 5-41 行
- **规划策略**：`planning/PlanningNode.py` 第 5-19 行
- **代码生成规则**：`code_generation/ExecutableNode.py` 第 60-77 行
- **视觉验证标准**：`validation/ValidationNode.py` 第 111-126 行

---

## 常见问题

### 1. 运行时出现 `UnicodeEncodeError`

**原因：** Windows 默认使用 GBK 编码，无法处理 emoji 字符

**解决：**
```bash
PYTHONIOENCODING=utf-8 python Agent.py
```

### 2. 提示 `ConnectionError` 或 `Fusion360 Server NOT running`

**原因：** Fusion 360 Server 未启动

**解决：**
1. 打开 Fusion 360
2. 按 `Shift+S` 打开脚本面板
3. 运行 `fusion360_server` 脚本
4. 验证：`curl http://127.0.0.1:8080`

### 3. 生成的模型不符合预期

**可能原因：**
- 输入描述过于模糊
- API 不支持某些特征（如阵列）
- 视觉验证标准过于宽松

**解决：**
1. 查看 `logs/` 目录下的日志，找到具体错误
2. 查看 `result/fusion_generated.py` 检查生成的代码
3. 修改输入描述，增加具体尺寸和约束
4. 调整 `ValidationNode.py` 中的验证 Prompt

### 4. 代码执行失败，一直循环修复

**原因：** 生成的代码有语法错误或参数不合法

**解决：**
1. 查看日志中的 `PYTHON_ERROR` 信息
2. 手动检查 `result/fusion_generated.py`
3. 常见错误：
   - 负数半径
   - 坐标重叠
   - 草图未闭合

### 5. `ModuleNotFoundError: No module named 'cadquery'`

**原因：** cadquery 未安装

**解决：**
```bash
conda activate CAD_agent
pip install cadquery
```

---

## 高级用法

### 1. 断点恢复

如果流程中断，可以通过 `thread_id` 恢复：

```python
# 在 Agent.py 中修改
thread_id = "20260227_144100"  # 使用之前的 thread_id
config = {"recursion_limit": 10, "configurable": {"thread_id": thread_id}}
```

### 2. 调整循环次数

```python
# Agent.py 第 95 行
config = {"recursion_limit": 20, ...}  # 增加到 20 次
```

### 3. 只运行前两个节点（测试 LLM）

修改 `Agent.py`，注释掉 executable 节点：

```python
# workflow.add_edge("planning", "executable")
workflow.add_edge("planning", END)  # 直接结束
```

### 4. 导出其他格式

修改 `code_generation/ExecutableNode.py` 第 116-117 行：

```python
# 添加其他导出格式
env.client.export_step(step_path)
# env.client.export_view("result/preview.png", view_orientation="iso")
```

---

## API 参考

详见 `fusion360/fusion360_tools/docs/Fusion360_API.md`

**核心 API：**
- `create_sketch(plane_type, offset)` - 创建草图
- `add_circle(centerPoint, radius)` - 画圆
- `add_line(startPoint, endPoint)` - 画直线
- `create_extrude(distance, operation)` - 拉伸
- `revolve(axis1, axis2, angle)` - 旋转
- `create_fillet(point, radius)` - 圆角
- `create_chamfer(point, distance)` - 倒角
- `export_step(filepath)` - 导出 STEP

---

## 技术支持

- **项目路径：** `D:\python_project\CAD_Agent\agent-master`
- **日志位置：** `logs/cad_agent_*.log`
- **测试用例：** 修改 `Agent.py` 第 89 行的 `user_input`

**调试技巧：**
1. 先用简单的几何体测试（如圆柱、立方体）
2. 查看日志中每个节点的输出
3. 手动运行 `result/fusion_generated.py` 验证代码
4. 使用 `curl` 测试 Fusion 360 Server 连接

---

## 示例用例

### 示例 1：简单圆柱

```python
user_input = "一个圆柱体，直径 50mm，高度 100mm"
```

### 示例 2：带孔的法兰

```python
user_input = "A circular flange with 4 bolt holes, outer diameter 150mm, thickness 20mm"
```

### 示例 3：倒角立方体

```python
user_input = "Create a 100x100x50mm rectangular block with 5mm chamfer on all edges"
```

---

**最后更新：** 2026-02-27
**测试环境：** Windows 11, Python 3.10, Fusion 360
