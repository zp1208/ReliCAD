import json
import traceback
import uuid
from datetime import datetime
from pathlib import Path


def build_script(indented_code: str, step_path: str, evidence_path: str) -> str:
    return f"""# -*- coding: utf-8 -*-
import os
import sys
import io
import math
import traceback

# Add agent-master to Python path to locate fusion360 module
script_dir = os.path.dirname(os.path.abspath(__file__))
agent_master_dir = os.path.abspath(os.path.join(script_dir, '..', '..'))
if agent_master_dir not in sys.path:
    sys.path.insert(0, agent_master_dir)

from fusion360.mcp_bridge.CAD_MCP import CAD_MCP

# Force UTF-8 encoding for stdout/stderr on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def run_model():
    try:
        cad = CAD_MCP()
        cad.clear()

        print("Sending atomic commands to Fusion 360...")
{indented_code}

        step_path = os.path.abspath(r"{step_path}")
        cad.export_step(step_path)
        # 运行时证据：成功路径（在 close 前 dump，locals() 含 LLM 变量名）
        cad.dump_evidence(os.path.abspath(r"{evidence_path}"), locals(), partial=False)
        cad.close()
        print("Success: model instructions executed and STEP exported.")
    except Exception as ex:
        # 先报告原始建模错误（不被后续 dump 的潜在异常盖住）
        traceback.print_exc(file=sys.stderr)
        # 运行时证据：失败路径（保留已成功部分 + 失败现场）
        cad.dump_evidence(os.path.abspath(r"{evidence_path}"), locals(), partial=True)
        sys.exit(1)


if __name__ == "__main__":
    run_model()
"""


def resolve_output_script_path(project_root: Path, output_py: str) -> Path:
    output_path = Path(output_py)
    if not output_path.is_absolute():
        output_path = (project_root / output_path).resolve()
    return output_path


def snapshot_generated_script(project_root: Path, output_script_path: Path) -> Path:
    snapshot_dir = (project_root / "result" / "fusion_generated_snapshots").resolve()
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    token = uuid.uuid4().hex[:8]
    snapshot_name = f"{output_script_path.stem}_{stamp}_{token}.py"
    snapshot_path = snapshot_dir / snapshot_name
    snapshot_path.write_text(output_script_path.read_text(encoding="utf-8"), encoding="utf-8")
    return snapshot_path


def write_snapshot_metadata(
    snapshot_path: Path,
    output_script_path: Path,
    returncode=None,
    stdout_val=None,
    stderr_val=None,
):
    metadata_path = snapshot_path.with_suffix(".json")
    payload = {
        "snapshot_path": str(snapshot_path),
        "source_script_path": str(output_script_path),
        "created_at": datetime.now().isoformat(),
        "returncode": returncode,
        "stdout": stdout_val,
        "stderr": stderr_val,
    }
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
