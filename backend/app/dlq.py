"""Dead-letter queue for failed operations with retry support."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from .alerting import send_alert
from .models import FailedOperation

logger = logging.getLogger("app.dlq")

MAX_DLQ_ALERT_DEPTH = 20


def enqueue_failure(
    db: Session,
    *,
    operation: str,
    payload: dict[str, Any],
    error: str,
) -> None:
    row = FailedOperation(
        operation=operation,
        payload_json=json.dumps(payload),
        error_message=error[:2000],
        attempts=0,
        status="pending",
    )
    db.add(row)
    db.commit()
    pending = db.query(FailedOperation).filter(FailedOperation.status == "pending").count()
    if pending >= MAX_DLQ_ALERT_DEPTH:
        send_alert("dlq_depth_high", {"pending_count": pending})
    logger.error("dlq_enqueued operation=%s error=%s pending=%d", operation, error, pending)


def process_pending(db: Session, handler: dict[str, Any]) -> int:
    """Retry pending DLQ items. Returns count processed."""
    rows = (
        db.query(FailedOperation)
        .filter(FailedOperation.status == "pending", FailedOperation.attempts < 5)
        .order_by(FailedOperation.created_at.asc())
        .limit(10)
        .all()
    )
    processed = 0
    for row in rows:
        row.attempts += 1
        fn = handler.get(row.operation)
        if fn is None:
            row.status = "dead"
            db.commit()
            continue
        try:
            payload = json.loads(row.payload_json)
            fn(payload)
            row.status = "completed"
            processed += 1
        except Exception as exc:
            row.error_message = str(exc)[:2000]
            if row.attempts >= 5:
                row.status = "dead"
        db.commit()
    return processed
