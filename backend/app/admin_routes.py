"""Admin MFA and JWT authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .audit import write_audit
from .auth import create_admin_jwt, verify_totp
from .config import Settings, get_settings
from .database import get_db
from .schemas import AdminMfaRequest, AdminMfaResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/mfa/verify", response_model=AdminMfaResponse)
def verify_mfa(
    request: Request,
    payload: AdminMfaRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not verify_totp(payload.code, settings):
        write_audit(
            db,
            event="mfa_failed",
            actor="admin",
            resource="/api/admin/mfa/verify",
            outcome="failure",
            request_id=getattr(request.state, "request_id", None),
            client_ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=401,
            detail={"code": "mfa_invalid", "message": "Invalid MFA code"},
        )

    token = create_admin_jwt(settings=settings)
    write_audit(
        db,
        event="mfa_success",
        actor="admin",
        resource="/api/admin/mfa/verify",
        outcome="success",
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
    )
    return AdminMfaResponse(access_token=token, token_type="bearer")
