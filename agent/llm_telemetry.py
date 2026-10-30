from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

SENSITIVE_KEYS = {
    "authorization", "api-key", "api_key", "apikey", "access-token",
    "access_token", "bearer", "client-secret", "client_secret",
    "connection-string", "connection_string", "cookie", "github-token",
    "github_token", "password", "pat", "refresh-token", "refresh_token",
    "secret", "token", "llm_api_key",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+\-/=]+"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
]


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).strip().lower()
    return normalized in SENSITIVE_KEYS or any(
        marker in normalized for marker in ("password", "secret", "token", "api_key", "apikey")
    )


def _sanitize_string(value: str, max_string_length: int) -> str:
    sanitized = value
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    if len(sanitized) > max_string_length:
        return sanitized[:max_string_length] + f"... [TRUNCATED {len(sanitized) - max_string_length} chars]"
    return sanitized


def sanitize_payload(
    payload: Any,
    *,
    max_depth: int = 10,
    max_items: int = 200,
    max_string_length: int = 12000,
    _depth: int = 0,
) -> Any:
    """Return a JSON-safe, recursively redacted copy of a request or response payload."""
    if _depth >= max_depth:
        return "[TRUNCATED: MAX DEPTH]"
    if payload is None or isinstance(payload, (bool, int, float)):
        return payload
    if isinstance(payload, str):
        return _sanitize_string(payload, max_string_length)
    if isinstance(payload, dict):
        result = {}
        for index, (key, value) in enumerate(payload.items()):
            if index >= max_items:
                result["__truncated_items__"] = len(payload) - max_items
                break
            result[str(key)] = "[REDACTED]" if _is_sensitive_key(key) else sanitize_payload(
                value,
                max_depth=max_depth,
                max_items=max_items,
                max_string_length=max_string_length,
                _depth=_depth + 1,
            )
        return result
    if isinstance(payload, (list, tuple, set)):
        items = list(payload)
        result = [
            sanitize_payload(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string_length=max_string_length,
                _depth=_depth + 1,
            )
            for item in items[:max_items]
        ]
        if len(items) > max_items:
            result.append({"__truncated_items__": len(items) - max_items})
        return result
    if hasattr(payload, "model_dump"):
        return sanitize_payload(payload.model_dump(), _depth=_depth + 1)
    if hasattr(payload, "__dict__"):
        return sanitize_payload(vars(payload), _depth=_depth + 1)
    return _sanitize_string(str(payload), max_string_length)


def make_telemetry(
    *,
    status: str,
    model: str | None,
    request_timestamp: str,
    response_timestamp: str,
    latency_ms: int,
    request_payload: Any,
    response_payload: Any,
    usage: dict[str, Any] | None = None,
    finish_reason: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    usage = usage or {}
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    result = {
        "status": status,
        "model": model,
        "request_timestamp": request_timestamp,
        "response_timestamp": response_timestamp,
        "latency_ms": latency_ms,
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "finish_reason": finish_reason,
        "request_payload_sanitized": sanitize_payload(deepcopy(request_payload)),
        "response_payload_sanitized": sanitize_payload(deepcopy(response_payload)),
    }
    if error:
        result["error"] = sanitize_payload(error)
    return result


def json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
