"""从快照恢复执行的 CLI 入口。

用法:
    python -m debug.resume_run --list result/20260505_143022
    python -m debug.resume_run --from result/.../002_planning.json --node executable
"""
import argparse
import logging
import sys
from pathlib import Path

# 添加 agent-master 到 sys.path（如果从 debug/ 内部运行）
sys.path.insert(0, str(Path(__file__).parent.parent))

from Agent import build_workflow
from debug.state_debugger import list_snapshots, resume_from_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def main():
    parser = argparse.ArgumentParser(description="从快照恢复 CAD Agent 工作流")
    parser.add_argument(
        "--list",
        metavar="DIR",
        help="列出指定目录下的所有快照",
    )
    parser.add_argument(
        "--from",
        dest="snapshot_path",
        metavar="PATH",
        help="快照文件路径",
    )
    parser.add_argument(
        "--node",
        metavar="NODE",
        help="从哪个节点继续执行",
    )
    parser.add_argument(
        "--thread-id",
        metavar="ID",
        help="可选线程 ID",
    )
    args = parser.parse_args()

    if args.list:
        # 列出快照
        snapshots = list_snapshots(args.list)
        if not snapshots:
            print(f"未找到快照: {args.list}")
            return
        print(f"找到 {len(snapshots)} 个快照:\n")
        for snap in snapshots:
            print(f"  [{snap['seq']}] {snap['node']}")
            print(f"      时间: {snap['timestamp']}")
            print(f"      路径: {snap['path']}\n")

    elif args.snapshot_path and args.node:
        # 恢复执行
        app = build_workflow()
        resume_from_snapshot(
            args.snapshot_path,
            app,
            args.node,
            thread_id=args.thread_id,
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

