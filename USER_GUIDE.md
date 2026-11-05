# ReliCAD 使用说明

本仓库对应论文 [ReliCAD: From Uncertain LLM Generation to Reliable Parametric CAD Modeling](https://arxiv.org/abs/2609.22325)。英文项目首页见 [README](README.md)，方法与实现的定位关系见 [论文代码对应表](docs/PAPER_TO_CODE.md)。

Fusion 端执行服务作为外部依赖，不随仓库分发；需要单独取得相应使用授权并配置兼容服务。以下记录当前实现的环境与连接要求，不构成第三方软件授权。

## Python 环境

当前核对的本地环境是 Windows、Python 3.10.19。主要运行库版本记录在 [requirements.txt](requirements.txt)，该文件不是完整的系统环境锁定文件。

```powershell
git clone https://github.com/zp1208/ReliCAD.git
cd ReliCAD
conda create -n relicad python=3.10 -y
conda activate relicad
python -m pip install -r requirements.txt
```

已有本地目录时，直接进入包含 `Agent.py` 的目录即可，不需要重命名本地文件夹。

## Fusion 连接

主流程需要正在运行的 Autodesk Fusion，以及与本项目桥接协议兼容、具备相应使用授权的 Fusion 端执行服务。

当前 [MCPBase](fusion360/mcp_bridge/mcp_base.py) 默认使用 `direct` 传输：

| 项目 | 当前值 |
| --- | --- |
| 地址 | `http://127.0.0.1:8765/execute` |
| 客户端默认位置 | `fusion360/mcp_bridge/mcp_base.py` |
| 服务端 | 外部依赖，需单独配置，不随本仓库分发 |
| Fusion Python API | 由 Fusion 自带的 `adsk` 提供，不通过 pip 安装 |

在已有授权的环境中启动服务后，可以先检查端口：

```powershell
Test-NetConnection 127.0.0.1 -Port 8765
```

端口可达仅表示服务正在监听，不能代替一次完整建模验证。此前旧文档中的 `fusion360_tools/server` 和 8080 端口不是当前主流程的连接方式。

现有本地环境中的服务端基于 [AuraFriday/Fusion-360-MCP-Server](https://github.com/AuraFriday/Fusion-360-MCP-Server)。该目录已从 Git 发布内容中排除；已有本地副本会保留，新克隆仓库不包含它。使用该组件前请确认上游 [LICENSE](https://github.com/AuraFriday/Fusion-360-MCP-Server/blob/main/LICENSE) 与 [EULA](https://github.com/AuraFriday/Fusion-360-MCP-Server/blob/main/EULA.md) 的授权条件；替代服务也必须兼容上述接口及本项目的命令协议。

## LLM 配置

程序从 `CAD_AGENT_API_KEY` 环境变量读取密钥：

```powershell
$env:CAD_AGENT_API_KEY = "替换为你的有效密钥"
$env:PYTHONIOENCODING = "utf-8"
```

[common/LLM.py](common/LLM.py) 当前配置的网关是 `https://api.nexrouter.ai/v1`，默认模型为 `gpt-5.5`，温度为 `0`。请使用与该网关匹配的密钥，并确认服务支持所需模型及视觉请求。程序不会自动读取 `.env` 文件。

不要把真实密钥写入源码、提示词、文档或 Git。缺少密钥时，程序会在创建 API 客户端前报出配置错误。

## 创建模型

先打开一个可以修改的空白 Fusion 设计，再从仓库根目录运行：

```powershell
python Agent.py --user-input "创建一个直径 80 mm、厚度 8 mm 的圆形板。" --save-dir "./result"
```

生成流程会调用 LLM 服务，并在 Fusion 中执行建模操作。默认输出目录曾包含开发机的绝对路径，因此示例显式传入 `--save-dir "./result"`。

当前生成脚本根据输出目录层级定位仓库。为匹配现有实现，请保持从仓库根目录运行并使用仓库内的 `result/`。

## 编辑模型

编辑入口接收已有的 **Python 建模脚本**，不是直接接收 STEP 文件。将占位符替换成此前生成的实际脚本路径：

```powershell
python Agent.py --source-code-path "<已有建模脚本.py的路径>" --user-input "保持直径不变，将板厚改为 12 mm。" --save-dir "./result"
```

编辑流程会读取原始代码、规划修改、生成并执行新的建模脚本，再进行验证。

## 常用命令行参数

| 参数 | 作用 |
| --- | --- |
| `-u` / `--user-input` | 创建需求或编辑指令 |
| `--source-code-path` | 提供既有建模脚本，进入编辑流程 |
| `--save-dir` | 输出根目录，建议显式使用 `./result` |
| `--recursion-limit` | LangGraph 的图步数限制，当前默认 40 |
| `--disable-snapshot` | 关闭调试状态快照 |
| `--thread-id` | 指定当前工作流使用的线程标识 |

```powershell
python Agent.py --help
```

图步数限制与修复次数不同。错误分析节点还单独记录累计失败次数；参数定义以当前源码为准。

## 输出与调试

每次运行会在 `result/` 下创建时间戳目录，保存本次运行的日志、生成脚本、STEP 文件、运行证据和视图。启用快照时，节点状态保存在 `debug_states/` 子目录中。

`debug/` 是主流程直接引用的运行依赖，相关说明见 [debug/README.md](debug/README.md)。无需快照时可添加 `--disable-snapshot`。

运行结果、日志、备份、本地凭据、独立测试与辅助脚本由 `.gitignore` 排除；不要使用强制添加将这些文件重新纳入仓库。

## 当前发布范围

仓库提供 Fusion 360 主流程及其必要资源。论文中的数据集、评测脚本、POWER 后端和实验结果文件尚未包含在此快照中。论文结果的复现范围与限制见 [论文代码对应表](docs/PAPER_TO_CODE.md#论文实验与复现材料)。
