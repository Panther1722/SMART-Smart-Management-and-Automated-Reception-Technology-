import os
import time
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


engine = create_engine(
    _get_database_url(),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

BOOKING_REQUESTS_TABLE = "booking_requests"
BOOKING_REQUESTS_COLUMNS = {
    "id",
    "session_id",
    "client_message_id",
    "raw_message",
    "guest_name",
    "guest_email",
    "guest_phone",
    "check_in",
    "check_out",
    "guests_count",
    "request_type",
    "special_request",
    "ai_reply",
    "created_at",
}


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(max_attempts: int = 30, sleep_seconds: float = 1.0) -> None:
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as e:  # noqa: BLE001 - startup retry loop
            last_err = e
            time.sleep(sleep_seconds)
    raise RuntimeError(f"Database not reachable after {max_attempts} attempts") from last_err


def _should_reset_schema() -> bool:
    return os.getenv("DB_RESET_SCHEMA", "").lower() in ("1", "true", "yes")


def _booking_requests_schema_is_current() -> bool:
    inspector = inspect(engine)
    if not inspector.has_table(BOOKING_REQUESTS_TABLE):
        return False
    existing = {column["name"] for column in inspector.get_columns(BOOKING_REQUESTS_TABLE)}
    return existing == BOOKING_REQUESTS_COLUMNS


def _ensure_chat_sessions_columns() -> None:
    """Add new chat_sessions columns on existing databases without a full reset."""
    inspector = inspect(engine)
    if not inspector.has_table("chat_sessions"):
        return
    existing = {column["name"] for column in inspector.get_columns("chat_sessions")}
    if "confirmation_email_sent_at" not in existing:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE chat_sessions "
                    "ADD COLUMN confirmation_email_sent_at TIMESTAMPTZ"
                )
            )


def _ensure_booking_requests_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table(BOOKING_REQUESTS_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(BOOKING_REQUESTS_TABLE)}
    if "client_message_id" not in existing:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE booking_requests ADD COLUMN client_message_id VARCHAR(64)")
            )


def ensure_schema(base) -> None:
    """Create tables and migrate columns on existing databases."""
    from .models import BookingRequest

    inspector = inspect(engine)
    if _should_reset_schema():
        if inspector.has_table(BOOKING_REQUESTS_TABLE):
            BookingRequest.__table__.drop(engine, checkfirst=True)

    base.metadata.create_all(bind=engine)
    _ensure_chat_sessions_columns()
    _ensure_booking_requests_columns()
