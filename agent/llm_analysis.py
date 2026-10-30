from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .llm_telemetry import make_telemetry
from .prompts import SYSTEM_PROMPT

SEVERITIES = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def review_impact(state):
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    if not api_key or not model:
        return {
            "status": "skipped",
            "reason": "LLM_API_KEY or LLM_MODEL is not configured.",
            "telemetry": {
                "status": "skipped",
                "model": model,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "request_payload_sanitized": {},
                "response_payload_sanitized": {},
            },
        }

    context = {
        "changed_files": state.get("changed_files", []),
        "deterministic_severity": state.get("severity", "Low"),
        "findings": state.get("findings", []),
        "impacted_services": [item.get("name") for item in state.get("impacted_services", [])],
        "schema_changes": state.get("schema_changes", []),
        "api_changes": state.get("api_changes", []),
        "contract_type_changes": state.get("contract_type_changes", []),
        "missing_dependent_changes": state.get("missing_dependent_changes", []),
        "dependency_evidence": state.get("dependency_evidence", []),
        "required_tests": state.get("required_tests", []),
    }
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        "temperature": 0,
    }
    base_url = (os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    started_at = _utc_now()
    started = time.perf_counter()
    raw_response = {}

    try:
        request = Request(
            f"{base_url}/chat/completions",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=int(os.environ.get("LLM_TIMEOUT_SECONDS", "20"))) as response:
            raw_response = json.loads(response.read().decode("utf-8"))

        choice = raw_response["choices"][0]
        content = choice["message"]["content"]
        result = json.loads(content)
        severity = result.get("severity")
        summary = result.get("summary")
        findings = result.get("findings", [])
        if severity not in SEVERITIES or not isinstance(summary, str) or not isinstance(findings, list):
            raise ValueError("LLM response did not match the expected analysis schema.")
        valid_findings = [
            item for item in findings
            if isinstance(item, dict)
            and item.get("severity") in SEVERITIES
            and all(isinstance(item.get(key), str) for key in ("file", "rationale", "evidence"))
        ]
        telemetry = make_telemetry(
            status="completed",
            model=raw_response.get("model") or model,
            request_timestamp=started_at,
            response_timestamp=_utc_now(),
            latency_ms=round((time.perf_counter() - started) * 1000),
            request_payload=request_payload,
            response_payload=raw_response,
            usage=raw_response.get("usage", {}),
            finish_reason=choice.get("finish_reason"),
        )
        return {
            "status": "completed",
            "severity": severity,
            "summary": summary,
            "findings": valid_findings,
            "telemetry": telemetry,
        }
    except HTTPError as error:
        error_body = ""
        try:
            error_body = error.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        reason = f"LLM request failed with HTTP {error.code} ({error.reason})."
        telemetry = make_telemetry(
            status="failed",
            model=model,
            request_timestamp=started_at,
            response_timestamp=_utc_now(),
            latency_ms=round((time.perf_counter() - started) * 1000),
            request_payload=request_payload,
            response_payload={"http_status": error.code, "body": error_body},
            error=reason,
        )
        return {"status": "failed", "reason": reason, "telemetry": telemetry}
    except Exception as error:
        reason = f"LLM review failed ({type(error).__name__})."
        telemetry = make_telemetry(
            status="failed",
            model=model,
            request_timestamp=started_at,
            response_timestamp=_utc_now(),
            latency_ms=round((time.perf_counter() - started) * 1000),
            request_payload=request_payload,
            response_payload=raw_response,
            error=reason,
        )
        return {"status": "failed", "reason": reason, "telemetry": telemetry}
