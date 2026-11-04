"""Shared primitive helpers and checklist item constructors.

These helpers are consumed by checklist-generation modules to keep item
construction logic centralized and avoid circular imports.
"""
INITIAL_CHECK_STATUS = "pending"
ALLOWED_PARAMETER_KEYS = {
    "diameter",
    "radius",
    "thickness",
    "height",
    "width",
    "length",
    "distance",
    "angle",
    "pitch",
}


# ---------------------------------------------------------------------------
# Basic coercion helpers
# ---------------------------------------------------------------------------

from common.units import _coerce_text  # noqa: F401  single source of truth


def _to_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _normalize_reason(reason: str, fallback: str) -> str:
    text = _coerce_text(reason).strip()
    return text if text else fallback


# ---------------------------------------------------------------------------
# Subject and expected-value normalization
# ---------------------------------------------------------------------------

def _normalize_geometry_expected(expected):
    payload = expected if isinstance(expected, dict) else {}
    normalized = {}
    if "exists" in payload:
        normalized["exists"] = bool(payload.get("exists"))
    count = _to_int(payload.get("count"))
    if count is not None:
        normalized["count"] = count
    min_count = _to_int(payload.get("min_count"))
    if min_count is not None:
        normalized["min_count"] = min_count
    if not normalized:
        normalized["exists"] = True
    if "exists" not in normalized:
        normalized["exists"] = True
    return normalized


def _normalize_subject(subject):
    if not isinstance(subject, dict):
        return None
    scope = _coerce_text(subject.get("scope")).strip().lower()
    if scope not in {"global", "feature", "geometry"}:
        return None
    normalized = {"scope": scope}
    subject_type = _coerce_text(subject.get("type")).strip().lower()
    if subject_type:
        normalized["type"] = subject_type
    subject_key = _coerce_text(subject.get("key")).strip().lower()
    if subject_key:
        normalized["key"] = subject_key
    return normalized


# ---------------------------------------------------------------------------
# Checklist item constructors
# ---------------------------------------------------------------------------

def _geometry_check(geometry_type: str, expected=None, reason: str = ""):
    return {
        "kind": "geometry_exist_check",
        "geometry_type": geometry_type,
        "expected": _normalize_geometry_expected(expected),
        "status": INITIAL_CHECK_STATUS,
        "reason": _normalize_reason(
            reason,
            f"Need geometry type {geometry_type} to satisfy the requested existence semantics.",
        ),
    }


def _parameter_check(parameter_key: str, value, subject=None, reason: str = ""):
    payload = {
        "kind": "parameter_check",
        "parameter_key": parameter_key,
        "expected": {"value": float(value)},
        "status": INITIAL_CHECK_STATUS,
        "reason": _normalize_reason(
            reason,
            f"Need {parameter_key} to match the requested value.",
        ),
    }
    normalized_subject = _normalize_subject(subject)
    if normalized_subject is not None:
        payload["subject"] = normalized_subject
    return payload


def _relation_check(kind: str, relation_type: str, reason: str = ""):
    label = "constraint" if kind == "constraint_relation_check" else "relation"
    return {
        "kind": kind,
        "relation_type": relation_type,
        "expected": {"exists": True},
        "status": INITIAL_CHECK_STATUS,
        "reason": _normalize_reason(
            reason,
            f"Need {relation_type} {label} semantics because the request explicitly describes it.",
        ),
    }


def _visual_check(topic: str, reason: str = ""):
    topic_text = _coerce_text(topic).strip() or "visual_confirmation_required"
    return {
        "kind": "visual_only_check",
        "topic": topic_text,
        "status": INITIAL_CHECK_STATUS,
        "reason": _normalize_reason(
            reason,
            f"Need visual confirmation for {topic_text}.",
        ),
    }
