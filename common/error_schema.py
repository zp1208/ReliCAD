import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


ERROR_PREFIX = "ERROR_JSON:"
OK_PREFIX = "OK_JSON:"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_compact(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


@dataclass
class ErrorEnvelope:
    # 结构化错误载荷，供 executable/validation/router 统一解析
    stage: str
    category: str
    severity: str
    code: str
    reason: str
    traceback: str = ""
    route_hint: str = "to_executable"
    suggestion: str = ""
    retry_count: int = 1
    retry_limit: int = 2
    error_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_message(self) -> str:
        return f"{ERROR_PREFIX}{_json_compact(self.to_dict())}"


@dataclass
class OkEnvelope:
    # 结构化成功载荷，便于日志与路由统一处理
    stage: str
    code: str = "OK"
    detail: str = ""
    data: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if payload["data"] is None:
            payload.pop("data")
        return payload

    def to_message(self) -> str:
        return f"{OK_PREFIX}{_json_compact(self.to_dict())}"


def parse_error_message(content: str) -> Optional[Dict[str, Any]]:
    if not isinstance(content, str) or not content.startswith(ERROR_PREFIX):
        return None
    try:
        return json.loads(content[len(ERROR_PREFIX):])
    except Exception:
        return None


def parse_ok_message(content: str) -> Optional[Dict[str, Any]]:
    if not isinstance(content, str) or not content.startswith(OK_PREFIX):
        return None
    try:
        return json.loads(content[len(OK_PREFIX):])
    except Exception:
        return None

