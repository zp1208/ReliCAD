"""规约检查模块 - 基于结构化数据验证设计规格

通过比对 intent_understanding（设计规格）与 execution_evidence（运行时证据），
使用 LLM 进行智能匹配和参数验证。
"""

import json
import logging
from common.LLM import invoke_llm, parse_llm_json
from langchain_core.messages import HumanMessage, SystemMessage


logger = logging.getLogger("CAD_Agent.spec_check")


SYSTEM_PROMPT = """You are a CAD Model Specification Validator.
Compare the design specifications with runtime evidence, and determine whether each specification is satisfied.

VALIDATION RULES:

1. **Parameter Tolerance**:
   - Allow reasonable tolerance: relative 2% or absolute 0.02mm/0.1°

2. **Status Assignment** (Presume Pass Unless Certain):
   - **"pass"**: Parameter matches within tolerance, or cannot determine from evidence (default stance)
   - **"fail"**: ONLY when CERTAIN a critical structure is completely missing OR critical parameter has severe error
   - **"pending"**: Current evidence insufficient to determine BUT visual check can verify (e.g., "T-shaped overall", "symmetric layout", "aligned holes")

3. **Key Principle**:
   - If unsure whether evidence matches intent → mark as PASS (not fail, not pending)
   - Parameter verification uncertainty → PASS (visual check won't help with numeric values anyway)
   - Only use PENDING when evidence insufficient BUT visual inspection can resolve it
   - Only use FAIL when absolutely confident of critical defect

Return JSON:
{
  "overall_status": "<pass | fail | partial>",
  "checks": [
    {
      "spec_name": "<geometry_element.name>",
      "status": "<pass | fail | pending>",
      "detail": "<For fail/pending: reason. For pass: null>",
      "matched_evidence": "<Path like 'sequence[0].feature' or null>"
    }
  ]
}"""


def run_spec_check(
    intent_understanding: list,
    execution_evidence: dict,
) -> dict:
    """
    使用 LLM 执行规约检查。
    比对设计规格与运行时证据，逐个验证每条规约。

    参数：
        intent_understanding: 设计规格列表（来自 state["intent_understanding"]）
        execution_evidence: 运行时证据（来自 state["execution_evidence"]）
    返回：
        {
            "overall_status": "pass" | "fail" | "partial",
            "checks": [
                {
                    "spec_name": str,
                    "status": "pass" | "fail" | "pending",
                    "detail": str | None,
                    "matched_evidence": str | None
                },
                ...
            ],
            "summary": str
        }
    """
    logger.info("规约检查: 开始检查 %d 条规约", len(intent_understanding))

    # 构建输入载荷
    payload = {
        "intent_understanding": intent_understanding,
        "execution_evidence": execution_evidence,
    }

    # 调用 LLM（单次调用）
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2)),
    ]

    logger.info("规约检查: 调用 LLM 进行验证")
    response_text = invoke_llm(messages, temperature=0)
    logger.info("规约检查: LLM 响应完成，开始解析结果")

    result = parse_llm_json(response_text)
    logger.info(
        "规约检查: 解析成功 - overall_status=%s, 检查项数=%d",
        result.get("overall_status"),
        len(result.get("checks", [])),
    )

    # 统计各状态数量
    status_counts = {"pass": 0, "fail": 0, "pending": 0}
    for check in result["checks"]:
        status = check.get("status", "pending")
        if status in status_counts:
            status_counts[status] += 1

    logger.info(
        "规约检查: 统计 - pass=%d, fail=%d, pending=%d",
        status_counts["pass"],
        status_counts["fail"],
        status_counts["pending"],
    )

    return result
