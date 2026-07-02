from unittest.mock import MagicMock, patch

from app.resilience import CircuitBreaker, retry_http_post


def test_circuit_breaker_opens_after_failures():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.allow() is False


def test_circuit_breaker_resets_on_success():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    breaker.record_failure()
    breaker.record_success()
    assert breaker.allow() is True


def test_retry_http_post_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True}
    mock_response.raise_for_status.return_value = None

    with patch("app.resilience.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.return_value = mock_response
        result = retry_http_post(
            "https://example.com/api",
            headers={},
            payload={"x": 1},
            timeout=5.0,
            circuit=CircuitBreaker(),
        )
    assert result == {"ok": True}
