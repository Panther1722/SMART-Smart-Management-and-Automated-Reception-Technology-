# Threat Model (STRIDE)

AI Receptionist Prototype — security analysis for guest chat, booking PII, and admin operations.

## Assets

| Asset | Sensitivity | Storage |
|-------|-------------|---------|
| Guest email, name, phone | PII / PHI-like | PostgreSQL (Fernet-encrypted when `FIELD_ENCRYPTION_KEY` set) |
| Chat messages | PII | PostgreSQL |
| Admin API key / JWT | Credential | Environment only |
| LLM API keys | Secret | Environment only |
| Session tokens | Auth | Client `sessionStorage` + HMAC server-side |

## STRIDE Analysis

| Threat | Vector | Mitigation | Implementation |
|--------|--------|------------|----------------|
| **Spoofing** | Stolen session UUID | HMAC session tokens (`X-Session-Token`) | `backend/app/auth.py` |
| **Spoofing** | Admin impersonation | API key + MFA (TOTP) + JWT | `backend/app/admin_routes.py` |
| **Tampering** | SQL injection | SQLAlchemy ORM, parameterized queries | `backend/app/models.py` |
| **Tampering** | Prompt injection | Rule guardrails + LLM system prompts | `backend/app/llm_service.py` |
| **Repudiation** | Deny PHI access | Immutable audit log | `audit_logs` table, `backend/app/audit.py` |
| **Info disclosure** | Open booking list | Admin auth required | `require_admin_access` |
| **Info disclosure** | Logs leak PII | PII redaction filter | `backend/app/logging_filters.py` |
| **Info disclosure** | DB breach | Field encryption at rest | `backend/app/encryption.py` |
| **DoS** | Chat spam | Rate limiting | `slowapi` in `backend/app/rate_limit.py` |
| **DoS** | LLM cost abuse | Rate limits + circuit breaker | `backend/app/resilience.py` |
| **Elevation** | Guess session ID | Session HMAC required in production | `require_session_token` |

## Automated Security Pipeline

- **CI**: `bandit`, `pip-audit`, `ruff`, Docker build scan
- **Dependabot**: weekly dependency updates (`.github/dependabot.yml`)
- **Runtime**: anomaly detection on 5xx bursts and rate-limit spikes (`backend/app/anomaly.py`)

## Residual Risks (prototype scope)

- Single-node Postgres without failover (documented HA path in README)
- TLS optional in local Docker (production uses reverse proxy TLS)
- Guest chat endpoints remain public by design (hotel reception use case)

## Review cadence

Re-run threat model when adding: payments, medical data, multi-tenant hotels, or external integrations.
