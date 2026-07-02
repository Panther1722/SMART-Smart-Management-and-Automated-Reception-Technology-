from datetime import date, datetime
from typing import Literal

import re

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

VALID_REQUEST_TYPES = frozenset(
    {
        "booking",
        "cancellation",
        "pricing",
        "availability",
        "general inquiry",
    }
)

RequestTypeLiteral = Literal[
    "booking",
    "cancellation",
    "pricing",
    "availability",
    "general inquiry",
]


class ExtractedFieldsSchema(BaseModel):
    """Structured booking fields stored on a request."""

    guest_name: str | None = None
    guest_email: str | None = None
    guest_phone: str | None = None
    check_in: date | None = None
    check_out: date | None = None
    guests_count: int | None = Field(default=None, ge=1)
    special_request: str | None = None


class LLMExtractionResult(BaseModel):
    """Strict JSON schema for LLM structured extraction."""

    guest_name: str | None = None
    guest_email: str | None = None
    guest_phone: str | None = None
    check_in: date | None = None
    check_out: date | None = None
    guests_count: int | None = Field(default=None, ge=1)
    request_type: RequestTypeLiteral | None = None
    special_request: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("guest_name", "guest_email", "guest_phone", "special_request", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("missing_fields", mode="before")
    @classmethod
    def _normalize_missing_fields(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]


class BookingRequestCreate(BaseModel):
    session_id: str | None = Field(default=None, max_length=100)
    raw_message: str | None = Field(default=None, max_length=2000)
    guest_name: str | None = Field(default=None, max_length=200)
    guest_email: str | None = Field(default=None, max_length=320)
    guest_phone: str | None = Field(default=None, max_length=50)
    check_in: date | None = None
    check_out: date | None = None
    guests_count: int | None = Field(default=None, ge=1)
    request_type: str | None = Field(default=None, max_length=50)
    special_request: str | None = None
    ai_reply: str | None = None


class BookingRequestOut(BaseModel):
    id: int
    session_id: str | None
    raw_message: str | None
    guest_name: str | None
    guest_email: str | None
    guest_phone: str | None
    check_in: date | None
    check_out: date | None
    guests_count: int | None
    request_type: str | None
    special_request: str | None
    ai_reply: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=100)
    client_message_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class ChatHistoryMessage(BaseModel):
    id: str
    role: str
    text: str
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    session_id: str
    guest_email: str | None = None
    messages: list[ChatHistoryMessage]


class SessionStartRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    session_id: str | None = Field(default=None, max_length=100)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("email must be a string")
        email = value.strip().lower()
        if not _EMAIL_RE.match(email):
            raise ValueError("Invalid email address")
        return email


class SessionStartResponse(BaseModel):
    session_id: str
    guest_email: str
    session_token: str


class AdminMfaRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class AdminMfaResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SessionOut(BaseModel):
    session_id: str
    guest_email: str


class EmailTestResponse(BaseModel):
    ok: bool
    message: str
    provider: str
    mailpit_ui: str | None = None

    model_config = {"from_attributes": True}
