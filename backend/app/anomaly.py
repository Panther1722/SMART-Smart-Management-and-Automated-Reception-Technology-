"""Real-time anomaly detection for error bursts and circuit-breaker events."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from .alerting import send_alert

logger = logging.getLogger("app.anomaly")

_lock = threading.Lock()
_error_timestamps: deque[float] = deque(maxlen=500)
_rate_limit_hits: deque[float] = deque(maxlen=500)

WINDOW_SECONDS = 60.0
ERROR_BURST_THRESHOLD = 10
RATE_LIMIT_BURST_THRESHOLD = 50


def record_http_status(status: int) -> None:
    if status < 500:
        return
    now = time.monotonic()
    with _lock:
        _error_timestamps.append(now)
        recent = [t for t in _error_timestamps if now - t <= WINDOW_SECONDS]
        if len(recent) >= ERROR_BURST_THRESHOLD:
            send_alert(
                "error_burst_detected",
                {"count_5xx_last_60s": len(recent), "threshold": ERROR_BURST_THRESHOLD},
            )
            logger.error("anomaly_detected type=error_burst count=%d", len(recent))


def record_rate_limit_hit() -> None:
    now = time.monotonic()
    with _lock:
        _rate_limit_hits.append(now)
        recent = [t for t in _rate_limit_hits if now - t <= WINDOW_SECONDS]
        if len(recent) >= RATE_LIMIT_BURST_THRESHOLD:
            send_alert(
                "rate_limit_burst",
                {"count_429_last_60s": len(recent), "threshold": RATE_LIMIT_BURST_THRESHOLD},
            )
            logger.error("anomaly_detected type=rate_limit_burst count=%d", len(recent))


def record_circuit_open(service: str) -> None:
    send_alert("circuit_breaker_open", {"service": service})
    logger.error("anomaly_detected type=circuit_open service=%s", service)
