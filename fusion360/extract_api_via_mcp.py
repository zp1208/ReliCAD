#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通过 MCP 批量提取 Fusion 360 API 文档（文件传输版）

原理：
  1. execute_python 在 Fusion 360 进程内运行，可直接 import adsk 做反射
  2. Fusion 与 agent 在同一台机器，文件系统互通
  3. 反射脚本在 Fusion 端直接把结果写到磁盘（避免大 JSON 走 stdout 被截断）
  4. 本地直接读取生成的文件

用法：
  python extract_api_via_mcp.py
"""

import io
import json
import sys
from pathlib import Path

# Windows 控制台默认 GBK，强制 stdout/stderr 为 UTF-8，避免输出非 ASCII 时崩溃
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from fusion360.mcp_bridge.CAD_MCP import CAD_MCP


# 反射提取脚本所在路径与输出路径（绝对路径，Fusion 端可直接访问）
EXTRACT_SCRIPT = Path(__file__).parent / "extract_all_api_docs.py"
OUTPUT_JSON = (project_root / "fusion360_api_registry.json").resolve()


def extract_api_docs_via_mcp():
    """通过 MCP 在 Fusion 端提取 API 文档并写盘，本地读取结果。"""

    print("连接到 Fusion 360...")
    cad = CAD_MCP()

    # 读取反射脚本源码
    extract_source = EXTRACT_SCRIPT.read_text(encoding="utf-8")

    # 在 Fusion 端执行：定义所有函数 → 提取 → 直接写文件到 OUTPUT_JSON
    output_path_literal = json.dumps(str(OUTPUT_JSON))  # 安全转义路径
    code = (
        extract_source
        + "\n\n"
        + "# ── MCP 注入：提取并写盘 ──\n"
        + "registry = extract_all_api_registry()\n"
        + f"save_registry(registry, {output_path_literal})\n"
        + "print('STATS:' + json.dumps(registry['statistics']))\n"
    )

    print("正在 Fusion 端提取 API（反射遍历 adsk，几秒钟）...")
    print("=" * 60)

    try:
        result = cad.execute(
            {"operation": "execute_python", "code": code},
            timeout=120.0,  # 反射全部 API 可能稍久
        )

        data = result.get("data", {})
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")

        if stderr:
            print("⚠️  Fusion 端 stderr:")
            print(stderr)

        # 从 stdout 解析统计信息
        stats = None
        for line in stdout.splitlines():
            if line.startswith("STATS:"):
                stats = json.loads(line[len("STATS:"):])
                break

        # 本地读取 Fusion 端写出的文件
        if OUTPUT_JSON.exists():
            print(f"\n✅ API 清单已生成: {OUTPUT_JSON}")
            print(f"   文件大小: {OUTPUT_JSON.stat().st_size / 1024:.1f} KB")

            if stats:
                print("\n📊 提取统计:")
                print(f"   命名空间: {stats.get('total_namespaces', 0)}")
                print(f"   类:       {stats.get('total_classes', 0)}")
                print(f"   方法:     {stats.get('total_methods', 0)}")
                print(f"   属性:     {stats.get('total_properties', 0)}")

            return json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
        else:
            print("❌ 未找到输出文件，Fusion 端可能写盘失败")
            print("Fusion 端 stdout:")
            print(stdout)
            return None

    except Exception as e:
        print(f"❌ 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        cad.close()


if __name__ == "__main__":
    extract_api_docs_via_mcp()
