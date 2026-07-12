from types import SimpleNamespace

import pytest

from app.observability.llm_usage import (
    estimate_cost_details,
    extract_usage_details,
    structured_output_kwargs,
    unwrap_structured_output,
)


def test_extract_deepseek_usage_with_cache_tokens():
    raw = SimpleNamespace(
        response_metadata={
            "token_usage": {
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 80,
                "prompt_cache_miss_tokens": 20,
                "completion_tokens": 50,
                "total_tokens": 150,
            }
        }
    )

    usage = extract_usage_details({"raw": raw, "parsed": object(), "parsing_error": None})

    assert usage == {
        "input": 20,
        "input_cache_read": 80,
        "output": 50,
        "total": 150,
    }


def test_estimate_deepseek_flash_cost_details():
    usage = {
        "input": 20,
        "input_cache_read": 80,
        "output": 50,
        "total": 150,
    }

    cost = estimate_cost_details(usage, provider="deepseek", model="deepseek-v4-flash")

    assert cost["input"] == pytest.approx(20 * 0.14 / 1_000_000)
    assert cost["input_cache_read"] == pytest.approx(80 * 0.0028 / 1_000_000)
    assert cost["output"] == pytest.approx(50 * 0.28 / 1_000_000)
    assert cost["total"] == pytest.approx(
        (20 * 0.14 + 80 * 0.0028 + 50 * 0.28) / 1_000_000
    )


def test_extract_openai_style_usage_from_usage_metadata():
    raw = SimpleNamespace(
        usage_metadata={
            "input_tokens": 12,
            "output_tokens": 8,
            "total_tokens": 20,
        }
    )

    assert extract_usage_details({"raw": raw, "parsed": object()}) == {
        "input": 12,
        "output": 8,
        "total": 20,
    }


def test_unwrap_structured_output_raises_on_parsing_error():
    with pytest.raises(ValueError):
        unwrap_structured_output({"raw": object(), "parsed": None, "parsing_error": "bad json"})


def test_deepseek_structured_output_uses_function_calling_and_raw_result():
    assert structured_output_kwargs("deepseek") == {
        "include_raw": True,
        "method": "function_calling",
    }
