"""Rough USD estimates for task model use."""

from __future__ import annotations

_RATES = (
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4.1-mini", 0.40, 1.60),
    ("gpt-4.1", 2.00, 8.00),
    ("gpt-4o", 2.50, 10.00),
    ("claude-opus-4", 15.00, 75.00),
    ("claude-sonnet-4", 3.00, 15.00),
    ("claude-3-7-sonnet", 3.00, 15.00),
    ("claude-3-5-sonnet", 3.00, 15.00),
    ("grok-3", 3.00, 15.00),
    ("grok-2", 2.00, 10.00),
    ("moonshot", 0.20, 0.80),
    ("kimi", 0.20, 0.80),
    ("llama", 0.0, 0.0),
)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = str(model or "").strip().lower()
    inn, out = 0.0, 0.0
    for prefix, input_rate, output_rate in _RATES:
        if prefix in key:
            inn, out = input_rate, output_rate
            break
    dollars = (max(0, int(input_tokens)) * inn + max(0, int(output_tokens)) * out) / 1_000_000
    return round(dollars, 6)
