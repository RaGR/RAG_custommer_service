"""Process-wide counters exposed via /metrics."""

from __future__ import annotations

from typing import Dict

from app.providers.circuit import circuit_open_total, provider_failure_totals
from app.security.rate_limit import ratelimit_block_total

requests_total = 0
errors_total = 0
llm_calls_total = 0
llm_latency_ms_total = 0


def inc_requests() -> None:
    global requests_total
    requests_total += 1


def inc_errors() -> None:
    global errors_total
    errors_total += 1


def record_llm_call(latency_ms: int) -> None:
    global llm_calls_total, llm_latency_ms_total
    llm_calls_total += 1
    llm_latency_ms_total += max(latency_ms, 0)


def render_metrics() -> str:
    metrics: Dict[str, int | float] = {
        "requests_total": requests_total,
        "errors_total": errors_total,
        "llm_calls_total": llm_calls_total,
        "llm_latency_ms_total": llm_latency_ms_total,
        "ratelimit_block_total": ratelimit_block_total,
        "provider_openrouter_failures_total": provider_failure_totals.get("openrouter", 0),
        "provider_hf_failures_total": provider_failure_totals.get("huggingface", 0),
        "circuit_open_total": circuit_open_total,
    }
    lines = [f"{key} {value}" for key, value in metrics.items()]
    return "\n".join(lines) + "\n"
