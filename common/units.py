"""Utilities for normalizing numeric intent parameters into mm (lengths) and degrees (angles)."""

import math
import re


LENGTH_UNITS_TO_MM = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "毫米": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimeters": 10.0,
    "厘米": 10.0,
    "公分": 10.0,
    "m": 1000.0,
    "meter": 1000.0,
    "meters": 1000.0,
    "米": 1000.0,
}

ANGLE_UNITS_TO_DEG = {
    "deg": 1.0,
    "degree": 1.0,
    "degrees": 1.0,
    "度": 1.0,
    "°": 1.0,
    "rad": 180.0 / math.pi,
    "radian": 180.0 / math.pi,
    "radians": 180.0 / math.pi,
    "弧度": 180.0 / math.pi,
}

_UNIT_PATTERN = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*"
    r"(millimeters?|millimeter|centimeters?|centimeter|meters?|meter|"
    r"degrees?|degree|radians?|radian|"
    r"毫米|厘米|公分|米|弧度|度|°|"
    r"mm|cm|deg|rad|m)?",
    flags=re.IGNORECASE,
)
_UNIT_ONLY_PATTERN = re.compile(
    r"(millimeters?|millimeter|centimeters?|centimeter|meters?|meter|"
    r"degrees?|degree|radians?|radian|"
    r"毫米|厘米|公分|米|弧度|度|°|"
    r"mm|cm|deg|rad|m)",
    flags=re.IGNORECASE,
)


def _dimension_from_unit(unit: str):
    """直接从单位字符串判断维度，比关键词推断更可靠。"""
    if unit in LENGTH_UNITS_TO_MM:
        return "length"
    if unit in ANGLE_UNITS_TO_DEG:
        return "angle"
    return None


def _coerce_text(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _extract_unit_from_text(text: str) -> str:
    lowered = _coerce_text(text).strip().lower()
    for match in _UNIT_ONLY_PATTERN.finditer(lowered):
        token = (match.group(1) or "").lower()
        start = match.start()
        end = match.end()
        left = lowered[start - 1] if start > 0 else " "
        right = lowered[end] if end < len(lowered) else " "
        # English units must be token-bounded so "diameter" does not match "meter".
        # Only ASCII letters matter here; Chinese characters must not block detection.
        if token.isascii() and (left.isascii() and left.isalpha() or right.isascii() and (right.isalpha() or right.isdigit())):
            continue
        return token
    return ""


def _normalize_description_length_units(description: str) -> str:
    """将 description 中的长度单位文字和数值统一替换为 mm。"""
    text = _coerce_text(description)
    if not text:
        return text

    def _replace_len_value(m):
        val = float(m.group(1))
        unit = (m.group(2) or "").lower()
        factor = LENGTH_UNITS_TO_MM.get(unit)
        if factor and factor != 1.0:  # factor==1.0 means already in mm
            converted = round(val * factor, 6)
            return f"{converted}mm"
        return m.group(0)

    text = _UNIT_PATTERN.sub(_replace_len_value, text)

    # 中文单位文字 → 毫米（单次通过，避免连锁替换）
    text = re.sub(r'厘米|公分', '毫米', text)
    text = re.sub(r'(?<!毫)米', '毫米', text)
    # 英文单位文字 → mm（re.ASCII 确保 \b 不把汉字算作词界）
    text = re.sub(r'\bmillimeters?\b', 'mm', text, flags=re.IGNORECASE | re.ASCII)
    text = re.sub(r'\bcentimeters?\b', 'mm', text, flags=re.IGNORECASE | re.ASCII)
    text = re.sub(r'\bmeters?\b', 'mm', text, flags=re.IGNORECASE | re.ASCII)
    text = re.sub(r'\bcm\b', 'mm', text, flags=re.IGNORECASE | re.ASCII)

    return text


def _normalize_description_angle_units(description: str) -> str:
    """将 description 中的弧度单位文字和数值替换为度。"""
    text = _coerce_text(description)
    if not text:
        return text

    def _replace_rad_value(m):
        val = float(m.group(1))
        unit = (m.group(2) or "").lower()
        factor = ANGLE_UNITS_TO_DEG.get(unit)
        if factor and factor != 1.0:
            converted = round(val * factor, 6)
            return f"{converted}°"
        return m.group(0)

    text = _UNIT_PATTERN.sub(_replace_rad_value, text)

    unit_text_map = {"弧度": "度", "radians": "degrees", "radian": "degree"}
    for src, dst in unit_text_map.items():
        text = text.replace(src, dst)
    text = re.sub(r'\brad\b', 'deg', text, flags=re.IGNORECASE | re.ASCII)

    return text


def extract_numeric_with_unit(raw_value, description: str = ""):
    if raw_value is None:
        return None, _extract_unit_from_text(description)

    if isinstance(raw_value, (int, float)):
        return float(raw_value), _extract_unit_from_text(description)

    text = _coerce_text(raw_value).strip()
    if not text:
        return None, _extract_unit_from_text(description)

    match = _UNIT_PATTERN.search(text)
    if not match:
        return None, _extract_unit_from_text(description)

    unit = (match.group(2) or _extract_unit_from_text(description)).lower()
    return float(match.group(1)), unit


def normalize_parameter_value(raw_value, description: str = ""):
    """Return one standardized numeric value when the parameter is measurable."""
    numeric_value, unit = extract_numeric_with_unit(raw_value, description)
    if numeric_value is None or not unit:
        return raw_value

    dimension = _dimension_from_unit(unit)
    if dimension == "length":
        factor = LENGTH_UNITS_TO_MM.get(unit)
        return numeric_value * factor if factor is not None else numeric_value
    if dimension == "angle":
        factor = ANGLE_UNITS_TO_DEG.get(unit)
        return numeric_value * factor if factor is not None else numeric_value
    return raw_value


def normalize_intent_units(intent):
    """Normalize measurable CADIntent parameter values once at the intent boundary."""
    if intent is None:
        return intent

    for field in ("explicit_params", "inferred_params", "default_params"):
        params = getattr(intent, field, {}) or {}
        if not isinstance(params, dict):
            continue
        for name, param in params.items():
            if param is None:
                continue
            raw_desc = _coerce_text(getattr(param, "description", ""))
            param.value = normalize_parameter_value(
                raw_value=getattr(param, "value", None),
                description=raw_desc,
            )
            if raw_desc:
                unit = _extract_unit_from_text(raw_desc)
                dimension = _dimension_from_unit(unit) if unit else None
                if dimension == "angle":
                    param.description = _normalize_description_angle_units(raw_desc)
                elif dimension == "length":
                    param.description = _normalize_description_length_units(raw_desc)
    return intent
