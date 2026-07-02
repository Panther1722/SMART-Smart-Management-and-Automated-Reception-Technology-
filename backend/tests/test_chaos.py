"""Chaos/resilience tests: circuit breaker and LLM fallback."""

from unittest.mock import patch

import httpx

from app.resilience import CircuitBreaker, retry_http_post


def test_circuit_breaker_blocks_when_open():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=120)
    breaker.record_failure()
    assert breaker.allow() is False


def test_llm_retry_exhaustion_opens_circuit():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=120)

    def fail_post(*args, **kwargs):
        response = httpx.Response(503, request=httpx.Request("POST", "http://test"))
        raise httpx.HTTPStatusError("fail", request=response.request, response=response)

    with patch("app.resilience.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.side_effect = fail_post
        try:
            retry_http_post(
                "http://test/api",
                headers={},
                payload={},
                timeout=1.0,
                max_attempts=1,
                circuit=breaker,
            )
        except httpx.HTTPStatusError:
            pass
    assert breaker.allow() is False


def test_generate_chat_reply_fallback_when_llm_disabled():
    from app.field_extraction import ExtractedFields
    from app.llm_service import generate_chat_reply

    reply = generate_chat_reply(
        "I need a room",
        [],
        ExtractedFields(),
        request_type="booking",
        fallback_reply="Rule-based reply",
    )
    assert reply == "Rule-based reply"
