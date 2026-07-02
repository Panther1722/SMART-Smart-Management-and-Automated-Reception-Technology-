"""Simple rule-based chat classification and replies (no LLM)."""

from __future__ import annotations

from .field_extraction import ExtractedFields

REQUEST_TYPE_BOOKING = "booking"
REQUEST_TYPE_CANCELLATION = "cancellation"
REQUEST_TYPE_PRICING = "pricing"
REQUEST_TYPE_AVAILABILITY = "availability"
REQUEST_TYPE_GENERAL = "general inquiry"

BOOKING_RELATED_TYPES = frozenset(
    {
        REQUEST_TYPE_BOOKING,
        REQUEST_TYPE_AVAILABILITY,
        REQUEST_TYPE_PRICING,
    }
)

# Order matters: check more specific intents before broader ones (e.g. booking vs availability).
_REQUEST_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        REQUEST_TYPE_CANCELLATION,
        (
            "cancel",
            "cancellation",
            "cancelled",
            "canceled",
            "refund",
            "call off",
        ),
    ),
    (
        REQUEST_TYPE_AVAILABILITY,
        (
            "availability",
            "available",
            "vacancy",
            "vacancies",
            "any rooms",
            "room available",
            "fully booked",
            "sold out",
        ),
    ),
    (
        REQUEST_TYPE_PRICING,
        (
            "price",
            "pricing",
            "cost",
            "rate",
            "rates",
            "how much",
            "per night",
            "nightly rate",
            "quote",
        ),
    ),
    (
        REQUEST_TYPE_BOOKING,
        (
            "book",
            "booking",
            "reserve",
            "reservation",
            "make a reservation",
            "check in",
            "check-in",
            "check out",
            "check-out",
            "stay",
            "room for",
        ),
    ),
)

_DEFAULT_REPLIES: dict[str, str] = {
    REQUEST_TYPE_BOOKING: (
        "I'd be happy to help you with a booking. "
        "Could you share your preferred check-in and check-out dates, "
        "how many guests will be staying, and your name?"
    ),
    REQUEST_TYPE_CANCELLATION: (
        "I can help with a cancellation. "
        "Please share the name on the reservation and your check-in date "
        "(or booking reference if you have one), and I'll guide you through the next steps."
    ),
    REQUEST_TYPE_PRICING: (
        "I can share our current rates. "
        "Which dates are you interested in, and how many guests will you have? "
        "That way I can point you to the right options."
    ),
    REQUEST_TYPE_AVAILABILITY: (
        "I'll check availability for you. "
        "What check-in and check-out dates are you looking at, and how many guests?"
    ),
    REQUEST_TYPE_GENERAL: (
        "Thank you for reaching out — I'm glad to help. I can assist with bookings, "
        "availability, pricing, cancellations, and questions about the hotel. "
        "What would you like to know?"
    ),
}


def detect_request_type(message: str) -> str:
    """Classify the guest message using simple keyword matching."""
    normalized = " ".join(message.lower().split())
    if not normalized:
        return REQUEST_TYPE_GENERAL

    for request_type, keywords in _REQUEST_TYPE_RULES:
        if any(keyword in normalized for keyword in keywords):
            return request_type

    return REQUEST_TYPE_GENERAL


def missing_booking_fields(fields: ExtractedFields) -> list[str]:
    """Field names still needed for a complete booking inquiry."""
    missing: list[str] = []
    if fields.check_in is None:
        missing.append("check_in")
    if fields.check_out is None:
        missing.append("check_out")
    if fields.guests_count is None:
        missing.append("guests_count")
    if not fields.guest_name:
        missing.append("guest_name")
    return missing


def conversation_stage(fields: ExtractedFields, request_type: str) -> str:
    """High-level dialogue phase for LLM context."""
    if request_type in BOOKING_RELATED_TYPES:
        has_any = any(
            (
                fields.check_in,
                fields.check_out,
                fields.guests_count,
                fields.guest_name,
            )
        )
        if not has_any:
            return "greeting_or_early_inquiry"
        if missing_booking_fields(fields):
            return "collecting_booking_details"
        return "booking_details_complete"
    if request_type == REQUEST_TYPE_CANCELLATION:
        return "cancellation_inquiry"
    return "general_conversation"


def build_reply(
    request_type: str,
    fields: ExtractedFields,
    *,
    email_sent: bool = False,
    email_recipient: str | None = None,
    booking_ready: bool = False,
) -> str:
    """Return a receptionist-style reply based on intent and extracted fields."""
    if request_type in BOOKING_RELATED_TYPES:
        return _build_booking_related_reply(
            request_type,
            fields,
            email_sent=email_sent,
            email_recipient=email_recipient,
            booking_ready=booking_ready,
        )

    if request_type == REQUEST_TYPE_CANCELLATION:
        return _build_cancellation_reply(fields)

    return _DEFAULT_REPLIES.get(request_type, _DEFAULT_REPLIES[REQUEST_TYPE_GENERAL])


def _build_booking_related_reply(
    request_type: str,
    fields: ExtractedFields,
    *,
    email_sent: bool = False,
    email_recipient: str | None = None,
    booking_ready: bool = False,
) -> str:
    has_dates = fields.check_in is not None and fields.check_out is not None
    has_guests = fields.guests_count is not None

    if has_dates and has_guests:
        return _confirmation_reply(
            fields,
            request_type,
            email_sent=email_sent,
            email_recipient=email_recipient,
            booking_ready=booking_ready,
        )

    missing: list[str] = []
    if fields.check_in is None:
        missing.append("your check-in date")
    if fields.check_out is None:
        missing.append("your check-out date")
    if fields.guests_count is None:
        missing.append("how many guests will be staying")

    if missing:
        prefix = "Thanks for your message. "
        if fields.guest_name:
            prefix = f"Thanks, {fields.guest_name}. "
        acknowledged: list[str] = []
        if fields.guests_count is not None:
            acknowledged.append(
                f"I have {fields.guests_count} guest{'s' if fields.guests_count != 1 else ''} noted"
            )
        if fields.check_in and fields.check_out is None:
            acknowledged.append(
                f"check-in on {fields.check_in.strftime('%d %B %Y')}"
            )
        if fields.check_out and fields.check_in is None:
            acknowledged.append(
                f"check-out on {fields.check_out.strftime('%d %B %Y')}"
            )
        if acknowledged:
            prefix = prefix + " ".join(acknowledged) + ". "
        return prefix + "Could you please share " + " and ".join(missing) + "?"

    return _DEFAULT_REPLIES.get(request_type, _DEFAULT_REPLIES[REQUEST_TYPE_GENERAL])


def _build_cancellation_reply(fields: ExtractedFields) -> str:
    if fields.guest_name and fields.check_in:
        return (
            f"I can help with the cancellation for {fields.guest_name} "
            f"(check-in {fields.check_in.strftime('%d %B %Y')}). "
            "I'll pass this to our team to review the next steps."
        )
    if fields.guest_name:
        return (
            f"Thank you, {fields.guest_name}. I can help with your cancellation — "
            "could you share the check-in date or booking reference?"
        )
    return _DEFAULT_REPLIES[REQUEST_TYPE_CANCELLATION]


def is_booking_ready_for_confirmation(fields: ExtractedFields, request_type: str) -> bool:
    """True when we have enough booking details to send a confirmation email."""
    if request_type in (REQUEST_TYPE_CANCELLATION, REQUEST_TYPE_GENERAL):
        return False
    return (
        fields.check_in is not None
        and fields.check_out is not None
        and fields.guests_count is not None
        and bool(fields.guest_name)
        and bool(fields.guest_email)
    )


def _confirmation_reply(
    fields: ExtractedFields,
    request_type: str,
    *,
    email_sent: bool = False,
    email_recipient: str | None = None,
    booking_ready: bool = False,
) -> str:
    guest_part = f"Thank you, {fields.guest_name}. " if fields.guest_name else "Thank you. "
    stay_part = (
        f"I have noted a stay from {fields.check_in.strftime('%d %B %Y')} "
        f"to {fields.check_out.strftime('%d %B %Y')} "
        f"for {fields.guests_count} guest{'s' if fields.guests_count != 1 else ''}."
    )

    if request_type == REQUEST_TYPE_PRICING:
        action = "I'll share suitable rates for those dates."
    elif request_type == REQUEST_TYPE_AVAILABILITY:
        action = "I'll check availability for those dates."
    elif email_sent:
        recipient = email_recipient or fields.guest_email or "your email address"
        action = (
            f"We've automatically sent a confirmation email with your booking details to {recipient}. "
            "Our team will review availability and follow up shortly."
        )
    elif booking_ready and request_type == REQUEST_TYPE_BOOKING:
        recipient = fields.guest_email or "your email address"
        action = (
            f"Your booking request is saved and our team will follow up at {recipient} "
            "to confirm availability."
        )
    else:
        action = "I'll pass this to our team to confirm availability."

    extra_parts: list[str] = []
    if fields.guest_phone:
        extra_parts.append(f"phone: {fields.guest_phone}")
    if fields.special_request:
        extra_parts.append(f"special request: {fields.special_request}")

    extra = ""
    if extra_parts:
        extra = " I also noted " + "; ".join(extra_parts) + "."

    return guest_part + stay_part + " " + action + extra
