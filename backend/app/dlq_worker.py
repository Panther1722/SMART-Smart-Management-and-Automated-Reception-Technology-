"""Background DLQ worker for self-healing retries."""

from __future__ import annotations

import asyncio
import logging

from .database import SessionLocal
from .dlq import process_pending
from .email_service import send_booking_confirmation

logger = logging.getLogger("app.dlq_worker")


def _handle_email_retry(payload: dict) -> None:
    from datetime import date

    from .field_extraction import ExtractedFields

    fields_data = payload.get("fields") or {}
    fields = ExtractedFields(
        guest_name=fields_data.get("guest_name"),
        guest_email=fields_data.get("guest_email"),
        guest_phone=fields_data.get("guest_phone"),
        check_in=date.fromisoformat(fields_data["check_in"]) if fields_data.get("check_in") else None,
        check_out=date.fromisoformat(fields_data["check_out"]) if fields_data.get("check_out") else None,
        guests_count=fields_data.get("guests_count"),
        special_request=fields_data.get("special_request"),
    )
    send_booking_confirmation(
        payload["recipient"],
        fields,
        request_type=payload.get("request_type"),
    )


_HANDLERS = {
    "email_confirmation": _handle_email_retry,
}


async def run_dlq_worker(interval_seconds: float = 30.0) -> None:
    while True:
        try:
            db = SessionLocal()
            try:
                count = process_pending(db, _HANDLERS)
                if count:
                    logger.info("dlq_worker processed=%d", count)
            finally:
                db.close()
        except Exception:
            logger.exception("dlq_worker iteration failed")
        await asyncio.sleep(interval_seconds)
