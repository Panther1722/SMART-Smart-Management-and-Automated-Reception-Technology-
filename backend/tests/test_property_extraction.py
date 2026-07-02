"""Property-based tests using Hypothesis."""

from datetime import date

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.field_extraction import extract_fields, merge_fields, ExtractedFields
from app.schemas import SessionStartRequest
from pydantic import ValidationError
import pytest


@hyp_settings(max_examples=100, deadline=None)
@given(st.text(min_size=0, max_size=500))
def test_extract_fields_never_crashes(message: str):
    fields = extract_fields(message, today=date(2026, 7, 2))
    assert isinstance(fields, ExtractedFields)


@hyp_settings(max_examples=100, deadline=None)
@given(
    st.integers(min_value=1, max_value=20),
    st.integers(min_value=1, max_value=20),
)
def test_merge_guests_count(a: int, b: int):
    merged = merge_fields(
        ExtractedFields(guests_count=a),
        ExtractedFields(guests_count=b),
    )
    assert merged.guests_count == b


@hyp_settings(max_examples=50, deadline=None)
@given(st.emails())
def test_session_email_validation(email: str):
    req = SessionStartRequest(email=email)
    assert "@" in req.email


@pytest.mark.parametrize("bad", ["", "not-email", "@.com"])
def test_invalid_emails_rejected(bad: str):
    with pytest.raises(ValidationError):
        SessionStartRequest(email=bad)
