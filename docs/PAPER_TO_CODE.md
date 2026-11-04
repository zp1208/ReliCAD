# ReliCAD：论文与代码对应关系

论文：[ReliCAD: From Uncertain LLM Generation to Reliable Parametric CAD Modeling](https://arxiv.org/abs/2609.22325)，arXiv:2609.22325v1，2026 年 9 月 16 日。以下章节编号以该版本为准。

本页依据论文的方法章节和仓库当前实现建立对应关系，便于从论文定位代码。仓库中的 `CAD_Agent` 日志名称以及 `Agent.py` 文件名属于实现命名，论文与仓库展示名称为 **ReliCAD**。

## 方法对应表

| 论文位置 | 代码入口 | 当前实现的职责 |
| --- | --- | --- |
| III-C1：Design-Intent Specification，式 (4) | [requirements_clarification/node.py](../create_planning/requirements_clarification/node.py)，[intent_extraction.py](../create_planning/requirements_clarification/skills/intent_extraction.py)，[ambiguity_resolver.py](../create_planning/requirements_clarification/skills/ambiguity_resolver.py) | 提取需求并消解歧义，将规格写入 `intent_understanding`。 |
| III-C2：Modeling Plan Generation，式 (5) | [model_planning/node.py](../create_planning/model_planning/node.py)，[plan_builder.py](../create_planning/model_planning/skills/plan_builder.py) | 根据规格生成创建计划，并接收重新规划所需的错误上下文。 |
| III-C2：编辑计划分支，式 (5) | [dispatch/node.py](../dispatch/node.py)，[edit_workflow/planning/node.py](../edit_workflow/planning/node.py)，[plan_delta_builder.py](../edit_workflow/planning/skills/plan_delta_builder.py) | 读取既有建模脚本和编辑指令，构建修改计划及修复计划。 |
| III-D1：Agent-ready API，式 (6) | [CAD_MCP.py](../fusion360/mcp_bridge/CAD_MCP.py)，[mcp_bridge/](../fusion360/mcp_bridge/)，[tool_spec.md](../fusion360/docs/tool_spec.md) | 提供草图、约束、特征、局部修饰、几何查询等 Fusion 操作封装。 |
| III-D2：Parametric Instruction Generation，式 (7) | [ExecutableNode.py](../code_generation/ExecutableNode.py)，[create_prompt_context.py](../code_generation/skills/create_prompt_context.py)，[edit_prompt_context.py](../code_generation/skills/edit_prompt_context.py) | 组合规格、计划、API 文档和修复上下文，生成创建或编辑代码。 |
| III-D3：Execution and Evidence Recording，式 (8) | [script_runtime.py](../code_generation/skills/script_runtime.py)，[mcp_base.py](../fusion360/mcp_bridge/mcp_base.py)，[mcp_evidence.py](../fusion360/mcp_bridge/mcp_evidence.py) | 执行生成脚本、调用 Fusion、导出 STEP，并在成功或失败时保存运行证据。 |
| III-E1：Evidence-Driven Validation，式 (9) | [ValidationNode.py](../validation/ValidationNode.py)，[spec_check.py](../validation/skills/spec_check.py)，[visual_check.py](../validation/skills/visual_check.py)，[edit_mode_validation.py](../validation/skills/edit_mode_validation.py) | 组织执行结果、规格一致性和视图验证；编辑任务使用对应验证入口。 |
| III-E2：Closed-Loop Repair，式 (10) | [error_analysis/node.py](../error_analysis/node.py)，[common/routers.py](../common/routers.py)，[Agent.py](../Agent.py) | 记录错误历史、选择修复阶段，并通过图路由返回需求解析、规划或执行阶段。 |

## 阅读代码的顺序

1. 从 [Agent.py](../Agent.py) 的 `build_workflow()` 查看实际注册的节点和边。
2. 从 [dispatch/node.py](../dispatch/node.py) 查看创建与编辑任务的分流。
3. 查看需求解析、创建规划和编辑规划如何生成共享状态。
4. 查看 [ExecutableNode.py](../code_generation/ExecutableNode.py) 的提示词组装、子进程执行与错误返回。
5. 查看 [mcp_evidence.py](../fusion360/mcp_bridge/mcp_evidence.py) 和 [ValidationNode.py](../validation/ValidationNode.py) 如何记录并使用证据。
6. 最后查看错误分析与路由，理解失败后的重试与终止。

## Implementation scope

当前跟踪的实现以 **Autodesk Fusion** 为执行后端。论文还讨论了其他内核映射；POWER 后端、SDK 与运行环境没有包含在本仓库中。

当前 `Agent.py` 的编辑入口由 `dispatch` 直接进入 `edit_planning`；`edit_workflow/ingest/` 虽然保留在源码中，但未作为活动节点注册。类似地，`create_planning/checklist_generation/` 仍在目录中，但当前需求解析节点没有调用其清单生成入口。阅读目录时，应以实际工作流和调用关系为准。

`debug/` 由主流程的节点装饰器直接引用，因此属于当前运行依赖。独立测试、批处理脚本、示例目录、日志、备份和生成结果未纳入本次仓库发布范围。

## 论文实验与复现材料

论文报告的生成与编辑实验使用特定数据、评价协议及模型配置。当前仓库包含主流程实现，但不包含论文数据集、测试集划分、评测脚本或完整实验结果文件。

因此，本仓库目前提供的是方法实现与交互运行入口。复现论文表格还需要补齐相应实验材料，并核对模型、API 服务、Fusion 版本及修复预算。当前模型默认值位于 [common/LLM.py](../common/LLM.py)，图步数限制位于 [Agent.py](../Agent.py)，累计失败上限位于 [error_analysis/node.py](../error_analysis/node.py)；这些概念不应混为同一个重试次数。

引用信息见 [CITATION.cff](../CITATION.cff) 和 [README 的引用段落](../README.md#citation)。
