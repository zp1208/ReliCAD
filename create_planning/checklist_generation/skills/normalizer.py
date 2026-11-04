"""Normalize checklist candidates into the final candidate-style checklist contract.

Unit normalization happens earlier at the intent extraction boundary.
This module assumes intent values already use Fusion internal units.
"""

import json
from create_planning.checklist_generation.skills.primitives import (
    ALLOWED_PARAMETER_KEYS,
    _coerce_text,
    _geometry_check,
    _normalize_geometry_expected,
    _normalize_subject,
    _parameter_check,
    _relation_check,
    _to_float,
    _visual_check,
)


# Candidate contract constants shared by sanitization and fallback generation.
CHECK_KIND_ORDER = [
    "geometry_exist_check",
    "parameter_check",
    "constraint_relation_check",
    "geometry_relation_check",
    "visual_only_check",
]
INITIAL_CHECK_STATUS = "pending"
ALLOWED_KINDS = set(CHECK_KIND_ORDER)
ALLOWED_GEOMETRY_TYPES = {"cylinder", "hollow_cylinder", "rectangle", "hole"}
FEATURE_PARAMETER_RULES = {
    "hole": {"diameter"},
    "extrude": {"distance"},
    "revolve": {"angle"},
    "fillet": {"radius"},
    "chamfer": {"distance"},
}
GEOMETRY_PARAMETER_RULES = {
    "cylinder": {"thickness", "height", "diameter", "radius"},
    "hollow_cylinder": {"thickness", "height", "diameter", "radius"},
    "rectangle": {"thickness", "height", "width", "length"},
    "hole": {"diameter", "radius"},
}
ALLOWED_CONSTRAINT_RELATION_TYPES = {
    "parallel",
    "perpendicular",
    "horizontal",
    "vertical",
    "equal",
    "tangent",
    "normal",
    "coincident",
    "concentric",
    "fixed",
    "midpoint",
    "angle",
    "diameter",
    "radius",
    "distance",
}
ALLOWED_GEOMETRY_RELATION_TYPES = {
    "coaxial",
    "concentric",
    "mirror_symmetry",
    "equiangular_distribution",
    "equidistant_distribution",
}
RELATION_TYPE_ALIASES = {
    "equal_angular_spacing_around_center": "equiangular_distribution",
    "equally_spaced_around_center": "equiangular_distribution",
    "equal_angle_distribution": "equiangular_distribution",
    "equal_distance_distribution": "equidistant_distribution",
}


def _normalize_relation_type(relation_type: str) -> str:
    key = _coerce_text(relation_type).strip().lower()
    return RELATION_TYPE_ALIASES.get(key, key)


def _subject_specificity(subject) -> int:
    normalized = _normalize_subject(subject)
    if normalized is None:
        return 0
    scope = normalized.get("scope", "global")
    base = 1 if scope == "global" else 2 if scope == "feature" else 3
    if normalized.get("type"):
        base += 1
    if normalized.get("key"):
        base += 1
    return base


def _normalize_expected_exists(expected):
    if not isinstance(expected, dict) or "exists" not in expected:
        return None
    return {"exists": bool(expected.get("exists"))}


def _parameter_subject_family(subject):
    normalized = _normalize_subject(subject)
    if normalized is None:
        return "global"
    scope = normalized.get("scope", "global")
    subject_type = _coerce_text(normalized.get("type")).strip().lower()
    if scope == "global":
        return "global"
    if scope == "feature" and subject_type == "hole":
        return "hole"
    if scope == "geometry" and subject_type == "hole":
        return "hole"
    return subject_type or scope


def _subject_allows_parameter(subject, parameter_key):
    if subject is None:
        return True

    scope = subject.get("scope")
    subject_type = subject.get("type", "")
    if scope == "global":
        return True
    if scope == "feature":
        allowed = FEATURE_PARAMETER_RULES.get(subject_type)
        return allowed is not None and parameter_key in allowed
    if scope == "geometry":
        allowed = GEOMETRY_PARAMETER_RULES.get(subject_type)
        return allowed is not None and parameter_key in allowed
    return False


def _normalize_parameter_value(expected):
    value = None if not isinstance(expected, dict) else _to_float(expected.get("value"))
    return None if value is None else {"value": value}


def _sanitize_relation_candidate(candidate, allowed_relation_types):
    relation_type = _normalize_relation_type(candidate.get("relation_type"))
    if relation_type not in allowed_relation_types:
        return None

    normalized_expected = _normalize_expected_exists(candidate.get("expected"))
    if normalized_expected is None:
        return None

    return {
        "relation_type": relation_type,
        "expected": normalized_expected,
    }


# Candidate sanitization is the only place that rejects malformed LLM payloads.
def _sanitize_candidate(candidate):
    if not isinstance(candidate, dict):
        return None

    kind = _coerce_text(candidate.get("kind")).strip().lower()
    if kind not in ALLOWED_KINDS:
        return None

    expected = candidate.get("expected")
    reason = _coerce_text(candidate.get("reason")).strip()
    sanitized = {"kind": kind}
    if reason:
        sanitized["reason"] = reason

    if kind == "geometry_exist_check":
        geometry_type = _coerce_text(candidate.get("geometry_type")).strip().lower()
        if geometry_type not in ALLOWED_GEOMETRY_TYPES:
            return None
        normalized_expected = _normalize_geometry_expected(expected)
        if normalized_expected is None:
            return None
        sanitized["geometry_type"] = geometry_type
        sanitized["expected"] = normalized_expected
        return sanitized

    if kind == "parameter_check":
        parameter_key = _coerce_text(candidate.get("parameter_key")).strip().lower()
        if parameter_key not in ALLOWED_PARAMETER_KEYS:
            return None
        normalized_expected = _normalize_parameter_value(expected)
        if normalized_expected is None:
            return None
        subject = _normalize_subject(candidate.get("subject"))
        if not _subject_allows_parameter(subject, parameter_key):
            return None
        sanitized["parameter_key"] = parameter_key
        sanitized["expected"] = normalized_expected
        if subject is not None:
            sanitized["subject"] = subject
        return sanitized

    if kind == "constraint_relation_check":
        relation_payload = _sanitize_relation_candidate(candidate, ALLOWED_CONSTRAINT_RELATION_TYPES)
        if relation_payload is None:
            return None
        sanitized.update(relation_payload)
        return sanitized

    if kind == "geometry_relation_check":
        relation_payload = _sanitize_relation_candidate(candidate, ALLOWED_GEOMETRY_RELATION_TYPES)
        if relation_payload is None:
            return None
        sanitized.update(relation_payload)
        return sanitized

    topic = _coerce_text(candidate.get("topic")).strip()
    if not topic:
        return None
    sanitized["topic"] = topic
    return sanitized


def _sanitize_candidates(candidates):
    """Drop malformed candidates and normalize field values into the prompt contract."""
    if not isinstance(candidates, list):
        raise ValueError("candidate generator must return a list")
    sanitized = []
    for candidate in candidates:
        payload = _sanitize_candidate(candidate)
        if payload is not None:
            sanitized.append(payload)
    return sanitized


def _item_conflict_key(item):
    kind = _coerce_text(item.get("kind")).strip().lower()
    if kind == "geometry_exist_check":
        return (kind, _coerce_text(item.get("geometry_type")).strip().lower())
    if kind == "parameter_check":
        subject = _normalize_subject(item.get("subject"))
        return (
            kind,
            _coerce_text(item.get("parameter_key")).strip().lower(),
            _coerce_text((subject or {}).get("scope")).strip().lower(),
            _coerce_text((subject or {}).get("type")).strip().lower(),
            _coerce_text((subject or {}).get("key")).strip().lower(),
        )
    if kind in {"constraint_relation_check", "geometry_relation_check"}:
        return (kind, _coerce_text(item.get("relation_type")).strip().lower())
    if kind == "visual_only_check":
        return (kind, _coerce_text(item.get("topic")).strip().lower())
    return (kind, json.dumps(item, ensure_ascii=False, sort_keys=True))


def _item_strength(item):
    kind = _coerce_text(item.get("kind")).strip().lower()
    if kind == "geometry_exist_check":
        expected = item.get("expected", {}) if isinstance(item.get("expected"), dict) else {}
        if "count" in expected:
            return 3
        if "min_count" in expected:
            return 2
        return 1
    if kind == "parameter_check":
        return _subject_specificity(item.get("subject"))
    if kind == "visual_only_check":
        return 0
    return 1


def _add_with_priority(entries, item, priority):
    key = _item_conflict_key(item)
    strength = _item_strength(item)
    existing = entries.get(key)
    if existing is None:
        entries[key] = {"item": item, "priority": priority, "strength": strength}
        return
    if priority > existing["priority"]:
        entries[key] = {"item": item, "priority": priority, "strength": strength}
        return
    if priority == existing["priority"] and strength > existing["strength"]:
        entries[key] = {"item": item, "priority": priority, "strength": strength}
        return


# Merge helpers that operate on already-normalized contract items.
def _prune_shadowed_parameter_items(flat_items):
    """Drop weaker parameter checks when a more specific check already covers the same semantic family."""
    pruned = []
    for index, item in enumerate(flat_items):
        if item.get("kind") != "parameter_check":
            pruned.append(item)
            continue
        parameter_key = _coerce_text(item.get("parameter_key")).strip().lower()
        subject = _normalize_subject(item.get("subject"))
        family = _parameter_subject_family(subject)
        specificity = _subject_specificity(subject)
        shadowed = False
        for other_index, other in enumerate(flat_items):
            if other_index == index or other.get("kind") != "parameter_check":
                continue
            if _coerce_text(other.get("parameter_key")).strip().lower() != parameter_key:
                continue
            other_subject = _normalize_subject(other.get("subject"))
            other_family = _parameter_subject_family(other_subject)
            other_specificity = _subject_specificity(other_subject)
            if (subject is None or subject.get("scope") == "global") and other_specificity > specificity:
                shadowed = True
                break
            if family != "global" and family == other_family and other_specificity > specificity:
                shadowed = True
                break
        if not shadowed:
            pruned.append(item)
    return pruned


def _ensure_geometry_anchors(flat_items):
    """Insert implicit geometry_exist_check items required by geometry-scoped parameter checks."""
    existing_geometry = {
        _coerce_text(item.get("geometry_type")).strip().lower()
        for item in flat_items
        if item.get("kind") == "geometry_exist_check"
    }
    synthetic = []
    seen = set()
    for item in flat_items:
        if item.get("kind") != "parameter_check":
            continue
        subject = _normalize_subject(item.get("subject"))
        if subject is None or subject.get("scope") != "geometry":
            continue
        geometry_type = _coerce_text(subject.get("type")).strip().lower()
        if geometry_type in existing_geometry or geometry_type in seen:
            continue
        seen.add(geometry_type)
        synthetic.append(
            _geometry_check(
                geometry_type,
                expected={"exists": True},
                reason=f"Need geometry type {geometry_type} because later parameter checks reference it.",
            )
        )
    return synthetic + flat_items


def _normalize_candidate_item(candidate):
    """Convert one sanitized candidate into the final checklist item shape."""
    if not isinstance(candidate, dict):
        return None

    kind = _coerce_text(candidate.get("kind")).strip().lower()
    reason = candidate.get("reason", "")

    if kind == "geometry_exist_check":
        return _geometry_check(
            _coerce_text(candidate.get("geometry_type")).strip().lower(),
            expected=candidate.get("expected"),
            reason=reason,
        )

    if kind == "parameter_check":
        return _parameter_check(
            _coerce_text(candidate.get("parameter_key")).strip().lower(),
            candidate.get("expected", {}).get("value"),
            subject=candidate.get("subject"),
            reason=reason,
        )

    if kind in {"constraint_relation_check", "geometry_relation_check"}:
        return _relation_check(
            kind,
            _normalize_relation_type(candidate.get("relation_type")),
            reason=reason,
        )

    topic = _coerce_text(candidate.get("topic")).strip()
    return _visual_check(topic, reason=reason) if topic else None


# Public entry points.
def normalize_candidate_checks(*, candidates):
    """Sanitize raw candidates and return final checklist JSON without fallback augmentation."""
    candidates = _sanitize_candidates(candidates)

    entries = {}
    for candidate in candidates:
        normalized = _normalize_candidate_item(candidate)
        if normalized is None:
            continue
        _add_with_priority(entries, normalized, priority=2)

    flat_items = [entry["item"] for entry in entries.values()]
    flat_items = _ensure_geometry_anchors(flat_items)
    flat_items = _prune_shadowed_parameter_items(flat_items)
    return flat_items
