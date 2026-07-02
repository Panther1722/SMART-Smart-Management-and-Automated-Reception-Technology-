"""Retry with exponential backoff and a simple circuit breaker for external calls."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx

logger = logging.getLogger("app.resilience")

T = TypeVar("T")


@dataclass
class CircuitBreaker:
    """Open the circuit after consecutive failures; half-open after cooldown."""

    failure_threshold: int = 5
    cooldown_seconds: float = 30.0
    _failures: int = 0
    _opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self.cooldown_seconds:
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()
            from .anomaly import record_circuit_open

            record_circuit_open("llm")
            logger.warning(
                "Circuit breaker opened after %d failures; cooldown %.0fs",
                self._failures,
                self.cooldown_seconds,
            )


_llm_circuit = CircuitBreaker()


def get_llm_circuit_breaker() -> CircuitBreaker:
    return _llm_circuit


def retry_http_post(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict,
    timeout: float,
    max_attempts: int = 3,
    circuit: CircuitBreaker | None = None,
) -> dict:
    """POST JSON with retries on transient network/server errors."""
    breaker = circuit or _llm_circuit
    if not breaker.allow():
        raise httpx.HTTPError("LLM circuit breaker is open")

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Unexpected response shape")
            breaker.record_success()
            return data
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last_error = exc
            retryable = isinstance(exc, httpx.TimeoutException | httpx.NetworkError)
            if isinstance(exc, httpx.HTTPStatusError):
                retryable = exc.response.status_code >= 500
            if not retryable or attempt == max_attempts:
                breaker.record_failure()
                raise
            backoff = min(2 ** (attempt - 1), 8)
            logger.warning(
                "HTTP POST retry attempt=%d/%d url=%s backoff=%ds error=%s",
                attempt,
                max_attempts,
                url,
                backoff,
                exc,
            )
            time.sleep(backoff)

    breaker.record_failure()
    raise last_error or RuntimeError("retry_http_post failed")


def with_fallback(
    primary: Callable[[], T],
    fallback: Callable[[], T],
    *,
    label: str = "operation",
) -> T:
    """Run primary; on any exception, log and return fallback result."""
    try:
        return primary()
    except Exception:
        logger.exception("%s failed — using fallback", label)
        return fallback()
