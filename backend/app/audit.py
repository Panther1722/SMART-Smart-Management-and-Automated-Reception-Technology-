"""Granular audit logging for auth and PHI access events."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog

logger = logging.getLogger("app.audit")


def write_audit(
    db: Session,
    *,
    event: str,
    actor: str,
    resource: str,
    outcome: str,
    request_id: str | None = None,
    client_ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    entry = AuditLog(
        event=event,
        actor=actor,
        resource=resource,
        outcome=outcome,
        request_id=request_id,
        client_ip=client_ip,
        details_json=details or {},
    )
    db.add(entry)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist audit log event=%s", event)
    logger.info(
        "audit event=%s actor=%s resource=%s outcome=%s request_id=%s",
        event,
        actor,
        resource,
        outcome,
        request_id,
    )
