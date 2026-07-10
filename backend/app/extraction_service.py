"""Orchestrates rule-based and LLM extraction with validation and merge logic."""

from __future__ import annotations

import logging

from .chat_rules import REQUEST_TYPE_GENERAL, detect_request_type
from .date_normalization import normalize_relative_dates
from .field_extraction import ExtractedFields, extract_fields, merge_fields
from .llm_service import extract_booking_fields_llm, is_llm_enabled
from .schemas import LLMExtractionResult

logger = logging.getLogger("app.extraction_service")

_REQUEST_TYPE_PRIORITY: dict[str, int] = {
    "cancellation": 5,
    "availability": 4,
    "pricing": 4,
    "booking": 3,
    "general inquiry": 1,
}


def llm_result_to_fields(result: LLMExtractionResult) -> ExtractedFields:
    return ExtractedFields(
        guest_name=result.guest_name,
        guest_email=result.guest_email,
        guest_phone=result.guest_phone,
        check_in=result.check_in,
        check_out=result.check_out,
        guests_count=result.guests_count,
        special_request=result.special_request,
    )


def _apply_relative_date_overrides(message: str, fields: ExtractedFields) -> ExtractedFields:
    """
    Deterministically resolve relative dates using the backend clock.

    If the message contains a relative date phrase (today/tomorrow/this Friday/etc.),
    prefer the backend-normalized value over LLM-provided years (e.g. 2024).
    """
    normalized = normalize_relative_dates(message)
    if normalized.check_in is None and normalized.check_out is None:
        return fields

    overlay = ExtractedFields(check_in=normalized.check_in, check_out=normalized.check_out)
    merged = merge_fields(fields, overlay)

    if normalized.check_in is not None and fields.check_in is not None and fields.check_in.year == 2024:
        merged.check_in = normalized.check_in
    if normalized.check_out is not None and fields.check_out is not None and fields.check_out.year == 2024:
        merged.check_out = normalized.check_out

    return merged


def _apply_contextual_relative_date(
    message: str, session_fields: ExtractedFields, current_fields: ExtractedFields
) -> ExtractedFields:
    """
    Fill in a still-missing check-in/check-out from a bare relative-date reply.

    Rule-based extraction only recognizes "tomorrow" etc. next to explicit
    check-in/check-out keywords. When the guest instead replies with just
    "tomorrow evening" (no keyword) to a direct follow-up question, apply it
    to whichever date the conversation is still waiting on, but only if this
    message didn't already yield an explicit check-in/check-out itself.
    """
    if current_fields.check_in is not None or current_fields.check_out is not None:
        return current_fields

    normalized = normalize_relative_dates(message)
    if normalized.check_in is None:
        return current_fields

    if session_fields.check_in is None:
        return merge_fields(current_fields, ExtractedFields(check_in=normalized.check_in))
    if session_fields.check_out is None:
        return merge_fields(current_fields, ExtractedFields(check_out=normalized.check_in))
    return current_fields


def _validate_dates(fields: ExtractedFields) -> ExtractedFields:
    """Basic sanity checks to prevent inverted date ranges."""
    if fields.check_in and fields.check_out and fields.check_out < fields.check_in:
        return ExtractedFields(
            guest_name=fields.guest_name,
            guest_email=fields.guest_email,
            guest_phone=fields.guest_phone,
            check_in=fields.check_out,
            check_out=fields.check_in,
            guests_count=fields.guests_count,
            special_request=fields.special_request,
        )
    return fields


def resolve_request_type(
    session_type: str | None,
    rule_type: str,
    llm_type: str | None,
    *,
    llm_confidence: float = 0.0,
) -> str:
    """Keep session request_type unless the current message has a stronger signal."""
    current_signal = rule_type
    if llm_type and llm_confidence >= 0.6:
        if _priority(llm_type) > _priority(current_signal):
            current_signal = llm_type
        elif (
            llm_type == REQUEST_TYPE_GENERAL
            and llm_confidence >= 0.65
            and rule_type == REQUEST_TYPE_GENERAL
        ):
            # Amenities, small talk, or other hotel-adjacent questions — use conversational
            # reply mode without discarding accumulated session fields.
            current_signal = REQUEST_TYPE_GENERAL

    if not session_type:
        return current_signal
    if _priority(current_signal) > _priority(session_type):
        return current_signal
    if (
        current_signal == REQUEST_TYPE_GENERAL
        and rule_type == REQUEST_TYPE_GENERAL
        and llm_type == REQUEST_TYPE_GENERAL
        and llm_confidence >= 0.65
    ):
        return REQUEST_TYPE_GENERAL
    return session_type


def resolve_extraction(
    message: str,
    chat_history: list[dict[str, str]],
    session_fields: ExtractedFields,
    session_request_type: str | None,
) -> tuple[ExtractedFields, str, str]:
    """
    Run rule-based + optional LLM extraction, validate, and merge with session state.

    Returns:
        merged_fields, final_request_type, extraction_source
    """
    rule_fields = extract_fields(message)
    rule_type = detect_request_type(message)
    llm_result: LLMExtractionResult | None = None
    source = "rule_based"

    if is_llm_enabled():
        llm_result = extract_booking_fields_llm(
            message=message,
            chat_history=chat_history,
            session_fields=session_fields,
            session_request_type=session_request_type,
        )
        if llm_result is not None:
            source = "llm+rule_based"

    current_fields = rule_fields
    if llm_result is not None:
        llm_fields = llm_result_to_fields(llm_result)
        llm_fields = _apply_relative_date_overrides(message, llm_fields)
        current_fields = merge_fields(rule_fields, llm_fields)

    current_fields = _apply_contextual_relative_date(message, session_fields, current_fields)

    merged_fields = merge_fields(session_fields, current_fields)
    merged_fields = _validate_dates(merged_fields)
    final_request_type = resolve_request_type(
        session_request_type,
        rule_type,
        llm_result.request_type if llm_result else None,
        llm_confidence=llm_result.confidence if llm_result else 0.0,
    )

    logger.info(
        "Extraction resolved source=%s rule_type=%s final_type=%s merged=%s",
        source,
        rule_type,
        final_request_type,
        merged_fields,
    )
    return merged_fields, final_request_type, source


def _priority(request_type: str | None) -> int:
    if not request_type:
        return 0
    return _REQUEST_TYPE_PRIORITY.get(request_type, _REQUEST_TYPE_PRIORITY[REQUEST_TYPE_GENERAL])


def session_request_type_from_rows(rows) -> str | None:
    latest: str | None = None
    latest_priority = -1
    for row in rows:
        if not row.request_type:
            continue
        priority = _priority(row.request_type)
        if priority >= latest_priority:
            latest = row.request_type
            latest_priority = priority
    return latest
