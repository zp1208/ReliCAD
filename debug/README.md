# CADState 调试快照功能

## 功能概述

调试快照功能允许你在工作流运行过程中自动保存各节点的状态，并在需要时从任意快照恢复执行，跳过前面的节点。这在调试时可以大幅节省时间，避免每次都从头运行整个流程。

## 快照自动保存

### 默认行为

运行 Agent.py 时，快照会自动保存到输出目录下的 `debug_states/` 文件夹：

```bash
python Agent.py -u "生成一个六角形螺母"
```

生成的目录结构：
```
result/20260505_150400/
├── cad_agent.log
├── 20260505_150431.py
├── 20260505_150431.step
└── debug_states/
    ├── 001_ingest.json
    ├── 002_planning.json
    ├── 003_executable.json
    └── 004_validation.json
```

### 保存的节点

快照会在以下节点执行完成后自动保存：
- `ingest` — 需求提取节点
- `planning` — 模型规划节点
- `executable` — 代码生成节点
- `error_analysis` — 错误分析节点（出错时）
- `validation` — 验证节点

## 查看快照列表

使用 `--list` 参数查看指定运行的所有快照：

```bash
python -m debug.resume_run --list result/20260505_150400
```

输出示例：
```
找到 4 个快照:

  [001] ingest
      时间: 2026-05-05T15:04:17.676081
      路径: result\20260505_150400\debug_states\001_ingest.json

  [002] planning
      时间: 2026-05-05T15:04:23.707229
      路径: result\20260505_150400\debug_states\002_planning.json

  [003] executable
      ...

  [004] validation
      ...
```

## 从快照恢复执行

使用 `--from` 指定快照文件，`--node` 指定从哪个节点继续执行：

```bash
python -m debug.resume_run --from D:\python_project\CAD_Agent\agent-master\result\20260505_155035\debug_states\002_planning.json --node planning
```

这会跳过 ingest、planning、executable 节点，直接从 validation 开始执行。

### 节点恢复前置条件

恢复时会自动校验快照中是否包含目标节点所需的字段：

| 恢复节点 | 必须存在的字段 |
|---------|--------------|
| `ingest` | `user_request` |
| `planning` | `user_request`, `intent_understanding` |
| `executable` | `plan` |
| `error_analysis` | `error_info` |
| `validation` | `execution_step_path` |

如果缺少必要字段，会抛出 `ValueError` 并提示缺失的字段名。

### 典型使用场景

1. 调试代码生成：从 planning 快照恢复到 executable 节点
2. 调试验证逻辑：从 executable 快照恢复到 validation 节点
3. 调试错误分析：手动修改快照中的 `error_info` 字段后恢复

## 禁用快照

不需要保存快照时，使用 `--disable-snapshot` 参数：

```bash
python Agent.py -u "生成一个六角形螺母" --disable-snapshot
```

## 编程接口

也可以在代码中直接调用：

```python
from debug import (
    save_state_snapshot,
    load_state_snapshot,
    list_snapshots,
    resume_from_snapshot,
)
from Agent import build_workflow

# 加载快照
state = load_state_snapshot("result/.../debug_states/002_planning.json")

# 恢复执行
app = build_workflow()
resume_from_snapshot(
    "result/.../debug_states/002_planning.json",
    app,
    resume_node="executable",
)
```

## 注意事项

- 快照文件中的路径（如 `execution_step_path`）是绝对路径，恢复时需确保对应文件仍然存在
- 恢复执行时会创建新的 LangGraph 线程，不会影响原始运行的状态
- 快照仅在 `save_dir` 存在且 `debug_snapshot_enabled` 为 True 时保存
