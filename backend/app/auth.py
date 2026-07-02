"""Zero-trust authentication: session HMAC tokens, admin MFA/JWT, dual API keys."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime, timedelta

import jwt
import pyotp
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .audit import write_audit
from .config import Settings, get_settings
from .database import SessionLocal

logger = logging.getLogger("app.auth")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


def create_session_token(session_id: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    secret = settings.session_secret.strip() or "dev-insecure-session-secret"
    return hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()


def verify_session_token(session_id: str, token: str, settings: Settings | None = None) -> bool:
    if not token or not session_id:
        return False
    expected = create_session_token(session_id, settings)
    return hmac.compare_digest(expected, token)


def _valid_admin_keys(settings: Settings) -> set[str]:
    keys = {settings.admin_api_key.strip(), settings.admin_api_key_previous.strip()}
    keys.discard("")
    return keys


def create_admin_jwt(subject: str = "admin", settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    secret = settings.jwt_secret.strip() or settings.session_secret.strip() or "dev-jwt-secret"
    payload = {
        "sub": subject,
        "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes),
        "iat": datetime.now(UTC),
        "scope": "admin",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_admin_jwt(token: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    secret = settings.jwt_secret.strip() or settings.session_secret.strip() or "dev-jwt-secret"
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Invalid or expired admin token"},
        ) from exc


def verify_totp(code: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    secret = settings.admin_totp_secret.strip()
    if not secret:
        return settings.app_env != "production"
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def require_session_token(request: Request, session_id: str) -> None:
    settings = get_settings()
    token = request.headers.get("X-Session-Token", "").strip()
    if settings.app_env == "production" or settings.session_secret.strip():
        if not verify_session_token(session_id, token, settings):
            _audit_auth_failure(request, "session_token_invalid", session_id)
            raise HTTPException(
                status_code=401,
                detail={"code": "invalid_session_token", "message": "Invalid session token"},
            )


def require_admin_access(
    request: Request,
    api_key: str | None = Security(_api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    """Accept admin JWT (post-MFA) or API key (with dual-key rotation support)."""
    actor = "anonymous"

    if bearer and bearer.credentials:
        claims = verify_admin_jwt(bearer.credentials, settings)
        actor = str(claims.get("sub", "admin"))
        _audit_auth_success(request, "admin_jwt", actor)
        return actor

    valid_keys = _valid_admin_keys(settings)
    if not valid_keys:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=503,
                detail={"code": "auth_not_configured", "message": "Admin auth not configured"},
            )
        return "dev-admin"

    if api_key and api_key in valid_keys:
        actor = "api_key"
        _audit_auth_success(request, "admin_api_key", actor)
        return actor

    _audit_auth_failure(request, "admin_unauthorized", "admin")
    raise HTTPException(
        status_code=401,
        detail={"code": "unauthorized", "message": "Invalid admin credentials"},
    )


def _audit_auth_success(request: Request, event: str, actor: str) -> None:
    db = SessionLocal()
    try:
        write_audit(
            db,
            event=event,
            actor=actor,
            resource=request.url.path,
            outcome="success",
            request_id=getattr(request.state, "request_id", None),
            client_ip=request.client.host if request.client else None,
        )
    finally:
        db.close()


def _audit_auth_failure(request: Request, event: str, resource: str) -> None:
    db = SessionLocal()
    try:
        write_audit(
            db,
            event=event,
            actor="anonymous",
            resource=resource,
            outcome="failure",
            request_id=getattr(request.state, "request_id", None),
            client_ip=request.client.host if request.client else None,
        )
    finally:
        db.close()
