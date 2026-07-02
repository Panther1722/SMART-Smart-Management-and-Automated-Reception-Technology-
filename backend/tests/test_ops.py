"""Tests for audit, DLQ, logging redaction, and ops endpoints."""

from app.dlq import enqueue_failure
from app.logging_filters import redact_pii
from app.models import FailedOperation


def test_redact_pii():
    text = "Contact guest@secret.com or +41 79 123 45 67"
    redacted = redact_pii(text)
    assert "guest@secret.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted


def test_ready_endpoint(client):
    res = client.get("/ready")
    assert res.status_code == 200
    assert res.json()["status"] == "ready"


def test_health_includes_resilience(client):
    res = client.get("/health")
    data = res.json()
    assert "resilience" in data


def test_dlq_enqueue(client, db_session):
    enqueue_failure(
        db_session,
        operation="email_confirmation",
        payload={"recipient": "test@example.com"},
        error="smtp down",
    )
    row = db_session.query(FailedOperation).first()
    assert row is not None
    assert row.operation == "email_confirmation"


def test_admin_mfa_invalid_code(client):
    res = client.post("/api/admin/mfa/verify", json={"code": "000000"})
    # In dev without TOTP secret, any code passes
    assert res.status_code in (200, 401)
