"""Simple in-memory circuit breaker for external providers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float | None = None


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3, reset_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._state = CircuitState()

    def allow(self) -> bool:
        if self._state.opened_at is None:
            return True
        if time.monotonic() - self._state.opened_at >= self.reset_timeout:
            self._state = CircuitState()
            return True
        return False

    def record_success(self) -> None:
        self._state = CircuitState()

    def record_failure(self) -> None:
        if self._state.opened_at is not None:
            return
        self._state.failures += 1
        if self._state.failures >= self.failure_threshold:
            self._state.opened_at = time.monotonic()
            increment_circuit_open_total()


_CIRCUITS: Dict[str, CircuitBreaker] = {}

provider_failure_totals = {
    "openrouter": 0,
    "huggingface": 0,
}
circuit_open_total = 0


def get_circuit(name: str) -> CircuitBreaker:
    if name not in _CIRCUITS:
        _CIRCUITS[name] = CircuitBreaker(name)
    return _CIRCUITS[name]


def increment_provider_failure(provider: str) -> None:
    if provider in provider_failure_totals:
        provider_failure_totals[provider] += 1


def increment_circuit_open_total() -> None:
    global circuit_open_total
    circuit_open_total += 1
