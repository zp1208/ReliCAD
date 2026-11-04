import ast
import re
import textwrap

def extract_valid_calls(code_raw: str):
    lines = code_raw.split("\n")
    extracted_lines = []
    current_block = []
    in_code_block = False

    def _flush_current_block():
        nonlocal current_block
        if not current_block:
            return

        block_text = textwrap.dedent("\n".join(current_block)).strip("\n")
        current_block = []
        if not block_text:
            return

        if extracted_lines:
            extracted_lines.append("")
        extracted_lines.extend(block_text.split("\n"))

    for line in lines:
        stripped = line.strip()

        # 开围栏：行内任意位置出现 ```python 即视为代码块起始，
        # 用于处理 prose 与开围栏挤在同一行的情况（如 "I'll fix it.```python"）。
        # 这样该行连同前面的自然语言说明一并被丢弃，代码从下一行开始收集。
        if not in_code_block and "```python" in stripped:
            in_code_block = True
            current_block = []
            continue

        # 闭围栏：裸 ``` 独占一行。
        if in_code_block and stripped.startswith("```"):
            _flush_current_block()
            in_code_block = False
            continue

        if in_code_block:
            current_block.append(line.rstrip())

    if in_code_block:
        _flush_current_block()

    # 如果没有提取到任何代码块，将整个输入视为纯代码
    if not extracted_lines:
        block_text = textwrap.dedent(code_raw).strip("\n")
        if block_text:
            extracted_lines = block_text.split("\n")

    return "\n".join(f"        {line}" if line else "" for line in extracted_lines)


def inject_auto_close_calls(indented_code: str) -> str:
    lines = indented_code.split("\n")
    injected_lines = []
    pending_close_before_constraint = False

    def _last_non_empty(buf):
        for prev in reversed(buf):
            if prev.strip():
                return prev.strip()
        return ""

    def _inject_if_not_duplicate(buf, call):
        if _last_non_empty(buf) != call.strip():
            buf.append(call)

    def _indent_of(line):
        return line[: len(line) - len(line.lstrip())]

    for line in lines:
        stripped = line.strip()

        if re.search(r"cad\.create_sketch\s*\(", stripped):
            pending_close_before_constraint = True

        if pending_close_before_constraint and re.search(r"cad\.add_constraint\s*\(", stripped):
            sketch_match = re.search(r"sketch_ref\s*=\s*([^,\)]+)", stripped)
            sketch_expr = sketch_match.group(1).strip() if sketch_match else "None"
            indent = _indent_of(line)
            _inject_if_not_duplicate(
                injected_lines,
                f"{indent}cad.auto_close_loop(sketch_ref={sketch_expr})",
            )
            pending_close_before_constraint = False

        if pending_close_before_constraint and re.search(r"cad\.(extrude|revolve|helix_sweep)\s*\(", stripped):
            sketch_match = re.search(r"sketch_ref\s*=\s*([^,\)]+)", stripped)
            sketch_expr = sketch_match.group(1).strip() if sketch_match else "None"
            indent = _indent_of(line)
            _inject_if_not_duplicate(
                injected_lines,
                f"{indent}cad.auto_close_loop(sketch_ref={sketch_expr})",
            )
            pending_close_before_constraint = False

        injected_lines.append(line)

    return "\n".join(injected_lines)
