import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .audit import write_audit
from .auth import create_session_token, require_admin_access, require_session_token
from .chat_rules import build_reply, is_booking_ready_for_confirmation
from .database import get_db
from .dlq import enqueue_failure
from .email_service import (
    get_email_config,
    is_email_enabled,
    send_booking_confirmation,
    send_staff_booking_notification,
    send_test_email,
)
from .extraction_service import resolve_extraction, session_request_type_from_rows
from .field_extraction import ExtractedFields, fields_from_booking_request, merge_fields
from .llm_service import generate_chat_reply, get_llm_config
from .models import BookingRequest, ChatSession
from .pii import decrypt_session, encrypt_email
from .rate_limit import limiter
from .resilience import get_llm_circuit_breaker
from .schemas import (
    BookingRequestCreate,
    BookingRequestOut,
    ChatHistoryMessage,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
    EmailTestResponse,
    SessionOut,
    SessionStartRequest,
    SessionStartResponse,
)

logger = logging.getLogger("app.routes")



router = APIRouter()





def _session_rows(db: Session, session_id: str) -> list[BookingRequest]:

    return (

        db.query(BookingRequest)

        .filter(BookingRequest.session_id == session_id)

        .order_by(BookingRequest.created_at.asc(), BookingRequest.id.asc())

        .all()

    )





def _get_chat_session(db: Session, session_id: str) -> ChatSession | None:
    chat_session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if chat_session:
        decrypt_session(chat_session)
    return chat_session





def _require_session_email(db: Session, session_id: str) -> str:

    """Return the guest email for a started session or raise 400."""

    chat_session = _get_chat_session(db, session_id)

    if chat_session is None or not chat_session.guest_email:

        raise HTTPException(

            status_code=400,

            detail="Please provide your email before starting the chat.",

        )

    return chat_session.guest_email





def _session_fields(db: Session, session_id: str, session_email: str | None = None) -> ExtractedFields:

    """Merge structured fields saved earlier in the same chat session."""

    merged = ExtractedFields()

    if session_email:

        merged = merge_fields(merged, ExtractedFields(guest_email=session_email))

    for row in _session_rows(db, session_id):

        merged = merge_fields(merged, fields_from_booking_request(row))

    return merged





def _rows_to_chat_history(rows: list[BookingRequest]) -> list[dict[str, str]]:

    history: list[dict[str, str]] = []

    for row in rows:

        if row.raw_message:

            history.append({"role": "user", "content": row.raw_message})

        if row.ai_reply:

            history.append({"role": "assistant", "content": row.ai_reply})

    return history





def _rows_to_history_messages(rows: list[BookingRequest]) -> list[ChatHistoryMessage]:

    messages: list[ChatHistoryMessage] = []

    for row in rows:

        if row.raw_message:

            messages.append(

                ChatHistoryMessage(

                    id=f"user-{row.id}",

                    role="user",

                    text=row.raw_message,

                    created_at=row.created_at,

                )

            )

        if row.ai_reply:

            messages.append(

                ChatHistoryMessage(

                    id=f"assistant-{row.id}",

                    role="assistant",

                    text=row.ai_reply,

                    created_at=row.created_at,

                )

            )

    return messages





@router.post("/api/session/start", response_model=SessionStartResponse)
@limiter.limit("20/minute")
def start_session(request: Request, payload: SessionStartRequest, db: Session = Depends(get_db)):

    """Create or update a chat session with the guest email before chat begins."""

    session_id = (payload.session_id or str(uuid.uuid4())).strip()

    guest_email = payload.email



    try:

        chat_session = _get_chat_session(db, session_id)

        if chat_session is None:

            chat_session = ChatSession(session_id=session_id, guest_email=encrypt_email(guest_email) or guest_email)

            db.add(chat_session)

        else:

            chat_session.guest_email = encrypt_email(guest_email) or guest_email

        db.commit()

        db.refresh(chat_session)
        logger.info("Session started session_id=%s", session_id)
        return SessionStartResponse(
            session_id=session_id,
            guest_email=guest_email,
            session_token=create_session_token(session_id),
        )

    except SQLAlchemyError as e:

        db.rollback()

        logger.exception("Failed to start session")

        raise HTTPException(status_code=500, detail="Database write failed") from e





@router.get("/api/session/{session_id}", response_model=SessionOut)

def get_session(session_id: str, db: Session = Depends(get_db)):

    session_id = session_id.strip()

    if not session_id:

        raise HTTPException(status_code=400, detail="session_id is required")



    chat_session = _get_chat_session(db, session_id)

    if chat_session is None:

        raise HTTPException(status_code=404, detail="Session not found")

    return chat_session





@router.post("/api/booking-request", response_model=BookingRequestOut)

def create_booking_request(payload: BookingRequestCreate, db: Session = Depends(get_db)):

    try:

        req = BookingRequest(**payload.model_dump())

        db.add(req)

        db.commit()

        db.refresh(req)

        return req

    except SQLAlchemyError as e:

        db.rollback()

        logger.exception("Failed to create booking request")

        raise HTTPException(status_code=500, detail="Database write failed") from e





@router.get("/api/booking-requests", response_model=list[BookingRequestOut])
def list_booking_requests(
    request: Request,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin_access),
):
    write_audit(
        db,
        event="phi_access",
        actor=actor,
        resource="/api/booking-requests",
        outcome="success",
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
    )

    return (

        db.query(BookingRequest)

        .order_by(BookingRequest.created_at.desc(), BookingRequest.id.desc())

        .limit(100)

        .all()

    )





@router.get("/api/chat-history/{session_id}", response_model=ChatHistoryResponse)

def get_chat_history(request: Request, session_id: str, db: Session = Depends(get_db)):

    session_id = session_id.strip()

    if not session_id:

        raise HTTPException(status_code=400, detail="session_id is required")

    require_session_token(request, session_id)

    chat_session = _get_chat_session(db, session_id)
    write_audit(
        db,
        event="phi_access",
        actor=f"session:{session_id[:8]}",
        resource=f"/api/chat-history/{session_id}",
        outcome="success",
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
    )
    rows = _session_rows(db, session_id)

    return ChatHistoryResponse(

        session_id=session_id,

        guest_email=chat_session.guest_email if chat_session else None,

        messages=_rows_to_history_messages(rows),

    )





@router.post("/api/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
def chat(request: Request, payload: ChatRequest, db: Session = Depends(get_db)):

    if not payload.session_id:

        raise HTTPException(

            status_code=400,

            detail="session_id is required. Start a session with your email first.",

        )



    session_id = payload.session_id.strip()
    require_session_token(request, session_id)
    session_email = _require_session_email(db, session_id)

    if payload.client_message_id:
        existing = (
            db.query(BookingRequest)
            .filter(
                BookingRequest.session_id == session_id,
                BookingRequest.client_message_id == payload.client_message_id,
            )
            .first()
        )
        if existing and existing.ai_reply:
            return ChatResponse(reply=existing.ai_reply, session_id=session_id)

    prior_rows = _session_rows(db, session_id)

    session_fields = _session_fields(db, session_id, session_email=session_email)

    session_request_type = session_request_type_from_rows(prior_rows)

    chat_history = _rows_to_chat_history(prior_rows)



    merged_fields, request_type, extraction_source = resolve_extraction(

        payload.message,

        chat_history,

        session_fields,

        session_request_type,

    )

    if not merged_fields.guest_email:

        merged_fields = merge_fields(merged_fields, ExtractedFields(guest_email=session_email))

    chat_session = _get_chat_session(db, session_id)
    email_recipient = merged_fields.guest_email or session_email
    booking_ready = is_booking_ready_for_confirmation(merged_fields, request_type)

    fallback_reply = build_reply(
        request_type,
        merged_fields,
        email_sent=False,
        email_recipient=None,
        booking_ready=booking_ready,
    )

    reply = generate_chat_reply(
        payload.message,
        chat_history,
        merged_fields,
        request_type=request_type,
        fallback_reply=fallback_reply,
        email_sent=False,
        email_recipient=None,
        booking_ready=booking_ready,
    )

    logger.info(
        "Chat reply generated session_id=%s request_type=%s source=%s llm_enabled=%s",
        session_id,
        request_type,
        extraction_source,
        get_llm_config()["enabled"],
    )

    try:
        req = BookingRequest(
            session_id=session_id,
            client_message_id=payload.client_message_id,
            raw_message=payload.message,
            guest_name=encrypt_email(merged_fields.guest_name),
            guest_email=encrypt_email(merged_fields.guest_email or session_email),
            guest_phone=encrypt_email(merged_fields.guest_phone),
            check_in=merged_fields.check_in,
            check_out=merged_fields.check_out,
            guests_count=merged_fields.guests_count,
            request_type=request_type,
            special_request=merged_fields.special_request,
            ai_reply=reply,
        )
        db.add(req)
        db.commit()

        email_sent = False
        if (
            chat_session is not None
            and chat_session.confirmation_email_sent_at is None
            and booking_ready
            and is_email_enabled()
        ):
            if send_booking_confirmation(
                email_recipient,
                merged_fields,
                request_type=request_type,
            ):
                send_staff_booking_notification(
                    merged_fields,
                    guest_email=email_recipient,
                    request_type=request_type,
                )
                chat_session.confirmation_email_sent_at = datetime.now(UTC)
                db.commit()
                email_sent = True
            else:
                logger.error(
                    "Booking saved but confirmation email failed session_id=%s recipient=%s",
                    session_id,
                    email_recipient,
                )
                enqueue_failure(
                    db,
                    operation="email_confirmation",
                    payload={
                        "recipient": email_recipient,
                        "request_type": request_type,
                        "fields": {
                            "guest_name": merged_fields.guest_name,
                            "guest_email": merged_fields.guest_email,
                            "guest_phone": merged_fields.guest_phone,
                            "check_in": str(merged_fields.check_in) if merged_fields.check_in else None,
                            "check_out": str(merged_fields.check_out) if merged_fields.check_out else None,
                            "guests_count": merged_fields.guests_count,
                            "special_request": merged_fields.special_request,
                        },
                    },
                    error="confirmation email send failed",
                )
        elif booking_ready and not is_email_enabled():
            logger.warning(
                "Booking complete but email not sent (SMTP not configured) session_id=%s recipient=%s",
                session_id,
                email_recipient,
            )

        logger.info(
            "Chat message saved session_id=%s request_type=%s merged_fields=%s email_sent=%s",
            session_id,
            request_type,
            merged_fields,
            email_sent,
        )
        return ChatResponse(reply=reply, session_id=session_id)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to persist chat message")
        raise HTTPException(status_code=500, detail="Database write failed") from e






@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database not ready") from exc


@router.get("/health")

def health():

    llm = get_llm_config()
    email = get_email_config()
    circuit = get_llm_circuit_breaker()

    return {

        "status": "ok",

        "resilience": {
            "llm_circuit_open": not circuit.allow(),
            "llm_circuit_failures": circuit._failures,
        },

        "llm": {

            "enabled": llm["enabled"],

            "configured": llm["configured"],

            "active": llm["active"],

            "reply_mode": llm["reply_mode"],

            "provider": llm["provider"],

            "model": llm["model"],

            "chat_temperature": llm["chat_temperature"],

            "chat_max_tokens": llm["chat_max_tokens"],

        },

        "email": {

            "enabled": email["enabled"],

            "configured": email["configured"],

            "provider": email["provider"],

            "smtp_host": email["smtp_host"],

            "mailpit_mode": email["mailpit_mode"],

            "mailpit_ui": email["mailpit_ui"] if email["mailpit_mode"] else None,

            "resend_configured": email["resend_configured"],

            "notify_email_set": bool(email.get("notify_email")),

        },

    }


@router.post("/api/email/test", response_model=EmailTestResponse)
def test_email(_: str = Depends(require_admin_access)):
    """Send a test booking email to BOOKING_NOTIFY_EMAIL or SMTP_USER."""
    cfg = get_email_config()
    recipient = str(cfg.get("notify_email") or cfg.get("smtp_user") or "").strip()
    if not recipient:
        raise HTTPException(
            status_code=400,
            detail="Set BOOKING_NOTIFY_EMAIL or SMTP_USER in .env first.",
        )
    if not is_email_enabled():
        raise HTTPException(
            status_code=503,
            detail="Email is not configured. Set Mailpit SMTP or RESEND_API_KEY in .env.",
        )

    ok = send_test_email(recipient)
    provider = str(cfg["provider"])
    mailpit_ui = str(cfg["mailpit_ui"]) if cfg["mailpit_mode"] else None
    if ok and cfg["mailpit_mode"]:
        message = f"Test email captured by Mailpit for {recipient}. Open {mailpit_ui} to view it."
    elif ok:
        message = f"Test email sent to {recipient}."
    else:
        message = f"Failed to send test email to {recipient}. Check backend logs."

    return EmailTestResponse(
        ok=ok,
        message=message,
        provider=provider,
        mailpit_ui=mailpit_ui,
    )
