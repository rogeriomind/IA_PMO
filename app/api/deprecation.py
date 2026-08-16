from __future__ import annotations

from fastapi import Response

from app.config import Settings


SUCCESSOR_AGENT_ENDPOINT = "/v2/agent/events"


def add_legacy_agent_deprecation_headers(response: Response, settings: Settings) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f"<{SUCCESSOR_AGENT_ENDPOINT}>; rel=\"successor-version\""
    sunset = settings.legacy_api_sunset_date.strip()
    if sunset:
        response.headers["Sunset"] = sunset
