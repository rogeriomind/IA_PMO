from __future__ import annotations

from typing import Any

from pydantic import BaseModel


DEEPSEEK_PRICES_PER_1M = {
    "deepseek-v4-flash": {
        "input": 0.14,
        "input_cache_read": 0.0028,
        "output": 0.28,
    },
    "deepseek-chat": {
        "input": 0.14,
        "input_cache_read": 0.0028,
        "output": 0.28,
    },
    "deepseek-reasoner": {
        "input": 0.14,
        "input_cache_read": 0.0028,
        "output": 0.28,
    },
    "deepseek-v4-pro": {
        "input": 0.435,
        "input_cache_read": 0.003625,
        "output": 0.87,
    },
}


def structured_output_kwargs(provider: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"include_raw": True}
    if provider.strip().lower() == "deepseek":
        kwargs["method"] = "function_calling"
    return kwargs


def unwrap_structured_output(result: Any) -> Any:
    if isinstance(result, dict) and "parsed" in result and "raw" in result:
        if result.get("parsing_error"):
            raise ValueError(f"Structured output parsing failed: {result['parsing_error']}")
        return result.get("parsed")
    return result


def extract_usage_details(result: Any) -> dict[str, int]:
    raw = _raw_result(result)
    usage = _find_usage(raw)
    if not usage:
        return {}

    prompt_tokens = _number(
        usage,
        "prompt_tokens",
        "input_tokens",
        "input",
    )
    completion_tokens = _number(
        usage,
        "completion_tokens",
        "output_tokens",
        "output",
    )
    total_tokens = _number(
        usage,
        "total_tokens",
        "total",
    )
    cache_hit_tokens = _number(
        usage,
        "prompt_cache_hit_tokens",
        "cache_read_input_tokens",
        "input_cache_read",
        "input_cached_tokens",
    )
    cache_miss_tokens = _number(
        usage,
        "prompt_cache_miss_tokens",
        "input_cache_miss",
    )

    prompt_details = _as_dict(usage.get("prompt_tokens_details"))
    if cache_hit_tokens is None:
        cache_hit_tokens = _number(prompt_details, "cached_tokens")

    if cache_miss_tokens is None and prompt_tokens is not None and cache_hit_tokens is not None:
        cache_miss_tokens = max(prompt_tokens - cache_hit_tokens, 0)

    details: dict[str, int] = {}
    if cache_hit_tokens is not None or cache_miss_tokens is not None:
        if cache_miss_tokens is not None:
            details["input"] = int(cache_miss_tokens)
        if cache_hit_tokens is not None:
            details["input_cache_read"] = int(cache_hit_tokens)
    elif prompt_tokens is not None:
        details["input"] = int(prompt_tokens)

    if completion_tokens is not None:
        details["output"] = int(completion_tokens)

    if total_tokens is None and details:
        total_tokens = sum(value for key, value in details.items() if key != "total")
    if total_tokens is not None:
        details["total"] = int(total_tokens)
    return details


def estimate_cost_details(
    usage_details: dict[str, int],
    *,
    provider: str,
    model: str,
) -> dict[str, float]:
    if not usage_details:
        return {}
    prices = _prices_for_model(provider=provider, model=model)
    if not prices:
        return {}

    input_cost = usage_details.get("input", 0) * prices["input"] / 1_000_000
    cache_cost = usage_details.get("input_cache_read", 0) * prices["input_cache_read"] / 1_000_000
    output_cost = usage_details.get("output", 0) * prices["output"] / 1_000_000
    total = input_cost + cache_cost + output_cost

    details = {
        "input": input_cost,
        "input_cache_read": cache_cost,
        "output": output_cost,
        "total": total,
    }
    return {key: value for key, value in details.items() if value or key == "total"}


def _prices_for_model(*, provider: str, model: str) -> dict[str, float] | None:
    if provider.strip().lower() != "deepseek":
        return None
    normalized = model.strip().lower()
    for model_name, prices in DEEPSEEK_PRICES_PER_1M.items():
        if normalized == model_name or normalized.startswith(model_name):
            return prices
    return None


def _raw_result(result: Any) -> Any:
    if isinstance(result, dict) and "raw" in result:
        return result.get("raw")
    return result


def _find_usage(raw: Any) -> dict[str, Any]:
    candidates: list[Any] = []
    for attr in ("usage_metadata", "response_metadata", "additional_kwargs"):
        value = getattr(raw, attr, None)
        if value:
            candidates.append(value)
    if isinstance(raw, dict):
        candidates.append(raw)

    for candidate in candidates:
        data = _as_dict(candidate)
        usage = data.get("token_usage") or data.get("usage")
        if usage:
            return _as_dict(usage)
        if any(
            key in data
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "prompt_cache_hit_tokens",
                "prompt_cache_miss_tokens",
            )
        ):
            return data
    return {}


def _as_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {}


def _number(data: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None
