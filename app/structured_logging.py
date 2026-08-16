from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "pmo-ai-agent-api",
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "correlation_id",
            "api_version",
            "thread_id",
            "tenant_id",
            "user_id",
            "intent",
            "tool_name",
            "latency_ms",
            "duration_ms",
            "retry_count",
            "transport",
            "success",
            "status",
            "error_code",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level_name: str) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level_name.upper(), logging.INFO))
