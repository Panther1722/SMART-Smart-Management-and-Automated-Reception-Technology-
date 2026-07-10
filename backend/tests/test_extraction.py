from datetime import date

import pytest
from pydantic import ValidationError

from app.date_normalization import normalize_relative_dates
from app.extraction_service import resolve_extraction
from app.field_extraction import ExtractedFields, extract_fields, merge_fields
from app.schemas import ChatRequest, SessionStartRequest


class TestFieldExtraction:
    def test_extract_email_and_name(self):
        fields = extract_fields(
            "Hi, my name is Jane Doe. Email: jane@example.com",
            today=date(2026, 7, 2),
        )
        assert fields.guest_name == "Jane Doe"
        assert fields.guest_email == "jane@example.com"

    def test_extract_guests_count(self):
        fields = extract_fields("Room for 2 guests please", today=date(2026, 7, 2))
        assert fields.guests_count == 2

    def test_merge_fields_overlay_wins(self):
        base = ExtractedFields(guest_name="Alice", guests_count=1)
        overlay = ExtractedFields(guests_count=3)
        merged = merge_fields(base, overlay)
        assert merged.guest_name == "Alice"
        assert merged.guests_count == 3


class TestDateNormalization:
    def test_tomorrow(self):
        result = normalize_relative_dates("I need a room tomorrow", base_date=date(2026, 7, 2))
        assert result.check_in == date(2026, 7, 3)

    def test_next_week_ambiguous(self):
        result = normalize_relative_dates("maybe next week", base_date=date(2026, 7, 2))
        assert result.check_in is None

    def test_possessive_tomorrow(self):
        result = normalize_relative_dates("tomorrows evening", base_date=date(2026, 7, 2))
        assert result.check_in == date(2026, 7, 3)


class TestContextualRelativeDate:
    """Reproduces the guest reply pattern from the reported chat bug."""

    def test_bare_tomorrow_fills_pending_check_out(self):
        session_fields = ExtractedFields(check_in=date(2026, 7, 10))
        merged, _, _ = resolve_extraction(
            "tomorrow i wanna check out",
            [],
            session_fields,
            "booking",
        )
        assert merged.check_out is not None
        assert merged.check_in == date(2026, 7, 10)

    def test_possessive_tomorrow_evening_fills_pending_check_out(self):
        session_fields = ExtractedFields(check_in=date(2026, 7, 10))
        merged, _, _ = resolve_extraction(
            "tomorrows evening",
            [],
            session_fields,
            "booking",
        )
        assert merged.check_out is not None

    def test_explicit_check_out_keyword_not_overridden(self):
        session_fields = ExtractedFields(check_in=date(2026, 7, 10))
        merged, _, _ = resolve_extraction(
            "check out date is 15 july",
            [],
            session_fields,
            "booking",
        )
        assert merged.check_out == date(2026, 7, 15)


class TestSchemas:
    def test_valid_email(self):
        req = SessionStartRequest(email="Guest@Example.COM")
        assert req.email == "guest@example.com"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            SessionStartRequest(email="not-an-email")

    def test_chat_message_length(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="", session_id="abc")

    def test_chat_message_max_length(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="x" * 2001, session_id="abc")
