"""视觉检查模块 - 使用 LLM 视觉能力验证 CAD 模型"""
import json
import base64
from common.LLM import invoke_llm, parse_llm_json
from langchain_core.messages import HumanMessage, SystemMessage


def run_full_visual_check(user_input, combined_image_path: str, pending_info: str = None) -> dict:
    """
    使用 Claude LLM 执行全量拓扑验证。
    检查整体几何、拓扑和视觉质量是否符合规格。

    参数：
        user_input: 用户的原始输入
        combined_image_path: 拼接图路径（来自 render_all_views()）
        pending_info: 规约检查阶段发现需要视觉确认的项目（可选）

    返回：
        {"status": "pass"|"fail", "detail": str, "reason": str}
    """
    # 读取并编码图像为 base64
    with open(combined_image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")

    # 构建图像内容（OpenAI 格式）
    image_contents = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{base64_image}",
                "detail": "high"  # 使用高分辨率模式确保 CAD 细节清晰
            },
        }
    ]

    qa_prompt = """
You are a Senior CAD Quality Engineer.
You task is to compare the User Input with the provided combined rendering and determine whether the generated CAD model visually and semantically matches the user's request.

INPUT STRUCTURE:
- User Input: The original design request
- Priority Visual Checks (if present): Items that could not be verified from structured data in the previous specification check phase. These require visual confirmation and should be given priority attention during your inspection.

CORE VERIFICATION PRINCIPLES:
1. The provided image is a 2×2 grid containing four orthogonal views (TOP, FRONT, RIGHT) and one isometric view (ISO). Use all four views comprehensively.
2. A feature should be considered missing only if it is absent in all four views; do not reject based on a single unclear or occluded view.
3. Verify that the model represents the same object type as described in the User Input, with a consistent overall 3D shape and topology.
4. Ensure all major features (explicitly stated or strongly implied) are present and located on the correct faces or regions. Any missing, misplaced, or structurally incorrect major feature constitutes a mismatch.
5. Ignore minor differences in size, proportion, fillets, chamfers, or rendering artifacts. Only clear visual or semantic inconsistencies should affect the decision.
DECISION RULE (Default to MATCH_SUCCESS):
- Return MISMATCH **ONLY** when you have clear visual evidence of a critical error (missing major feature, wrong topology, completely different object type)
- If uncertain, unclear from views, or cannot confidently confirm an error → return MATCH_SUCCESS (do not fail based on uncertainty)
- When in doubt, pass the model


Always return a JSON object with exactly two fields:
{
  "status": "<MATCH_SUCCESS | MISMATCH>",
  "problem": "<For MISMATCH, describe each concrete error separately, including the incorrect feature, its location if applicable, and the expected correct state. For MATCH_SUCCESS, leave this field empty or null.>"
}
"""

    # 构建用户输入文本
    user_input_text = f"User Input: {user_input}"

    # 如果有 pending_info，添加到输入中
    if pending_info:
        user_input_text += f"\n\n{pending_info}"

    full_content = [{"type": "text", "text": user_input_text}] + image_contents

    feedback = invoke_llm(
        [
            SystemMessage(content=qa_prompt),
            HumanMessage(content=full_content),
        ],
        temperature=0,
    ).strip()

    try:
        result = parse_llm_json(feedback)
        if result.get("status") == "MATCH_SUCCESS":
            return {
                "status": "pass",
                "detail": None
            }
        else:
            return {
                "status": "fail",
                "detail": result.get("problem", feedback)
            }
    except (json.JSONDecodeError, TypeError):
        # 降级到字符串匹配
        if "MATCH_SUCCESS" in feedback:
            return {
                "status": "pass",
                "detail": None
            }
        else:
            return {
                "status": "fail",
                "detail": feedback
            }
