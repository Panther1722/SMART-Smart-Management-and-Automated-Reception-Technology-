"""PII encrypt/decrypt helpers for database persistence."""

from __future__ import annotations

from .encryption import decrypt_value, encrypt_value
from .field_extraction import ExtractedFields
from .models import BookingRequest, ChatSession


def encrypt_email(value: str | None) -> str | None:
    return encrypt_value(value)


def decrypt_email(value: str | None) -> str | None:
    return decrypt_value(value)


def encrypt_fields(fields: ExtractedFields) -> ExtractedFields:
    return ExtractedFields(
        guest_name=encrypt_value(fields.guest_name),
        guest_email=encrypt_value(fields.guest_email),
        guest_phone=encrypt_value(fields.guest_phone),
        check_in=fields.check_in,
        check_out=fields.check_out,
        guests_count=fields.guests_count,
        special_request=fields.special_request,
    )


def decrypt_fields(fields: ExtractedFields) -> ExtractedFields:
    return ExtractedFields(
        guest_name=decrypt_value(fields.guest_name),
        guest_email=decrypt_value(fields.guest_email),
        guest_phone=decrypt_value(fields.guest_phone),
        check_in=fields.check_in,
        check_out=fields.check_out,
        guests_count=fields.guests_count,
        special_request=fields.special_request,
    )


def decrypt_booking_row(row: BookingRequest) -> BookingRequest:
    row.guest_name = decrypt_value(row.guest_name)
    row.guest_email = decrypt_value(row.guest_email)
    row.guest_phone = decrypt_value(row.guest_phone)
    return row


def decrypt_session(row: ChatSession) -> ChatSession:
    row.guest_email = decrypt_value(row.guest_email) or row.guest_email
    return row
