"""Hosted LLM integration: structured extraction + chat replies with rule-based fallback."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime

from .chat_rules import build_reply, conversation_stage, missing_booking_fields
from .field_extraction import ExtractedFields
from .schemas import LLMExtractionResult

logger = logging.getLogger("app.llm_service")

ChatTurn = dict[str, str]

_TEMPORAL_GROUNDING_INSTRUCTION = """Use the date/time above as the source of truth for all relative date expressions.
Interpret words like "today", "tomorrow", "next week", and "next Friday" relative to this date.
Do not guess outdated years such as 2024.
If the date is ambiguous, ask a clarification question instead of inventing one."""


def _temporal_grounding_prefix() -> str:
    now = datetime.now().astimezone()
    current_date = now.date().isoformat()
    current_timestamp = now.isoformat(timespec="seconds")
    tz = now.tzname() or str(now.tzinfo) or "local"
    return (
        f"Current date: {current_date}\n"
        f"Current timezone: {tz}\n"
        f"Current timestamp: {current_timestamp}\n\n"
        f"{_TEMPORAL_GROUNDING_INSTRUCTION}\n"
    )


SYSTEM_PROMPT = """You are a warm, professional hotel receptionist at SMART Hotel, a single boutique hotel prototype.

Your role:
- Help guests with bookings, availability, pricing, cancellations, and hotel-related questions (check-in times, breakfast, parking, amenities, local tips).
- Conduct a natural conversation — acknowledge what the guest just said, refer back to earlier details when relevant, and vary your phrasing.

Conversation style:
- Sound like a real receptionist, not a form. Usually 2–5 sentences.
- If the guest greets you or makes small talk, respond briefly and warmly, then offer help.
- If the guest corrects earlier details ("actually…", "I meant…"), confirm the update clearly.
- If details are still missing for a booking, ask only for what is missing — do not re-ask for information already provided.
- Use the structured session context (collected fields, missing fields, conversation stage, last question you asked) naturally.

Boundaries (tiered):
- Always help: hotel services, stay details, directions, and booking-related requests.
- Brief friendly exchange: one or two sentences of empathy or hospitality, then steer back to how you can help.
- Politely decline: unrelated tasks (e.g. tutoring programming, medical or legal advice, long off-topic requests). Offer hotel assistance instead.

Hard limits:
- Do NOT invent room availability, prices, or confirmed reservations.
- Do NOT claim a booking is confirmed; say the team will follow up after you collect the details.
- When all booking details are collected, the system automatically sends a confirmation email to the guest — mention this naturally; never ask staff or the guest to send email manually."""

EXTRACTION_SYSTEM_PROMPT = """You extract structured booking data from hotel guest chat messages for SMART Hotel.
Return JSON only. No markdown, no explanation, no extra text.

Rules:
- Do NOT invent confirmed bookings, room availability, or prices.
- Read the latest user message together with recent chat history — corrections override earlier values.
- Phrases like "actually", "I meant", "change that to", "not X but Y" should update the relevant field.
- Use session context as a baseline; return the best current value for each field supported by message and history.
- Use null for any field that is unclear or not stated in the message/history.
- Do NOT guess dates; only extract dates explicitly mentioned or clearly implied.
- guests_count must be a positive integer when present, otherwise null.
- request_type must be one of: booking, cancellation, pricing, availability, general inquiry.
- Use "general inquiry" for greetings, hotel amenities, parking, breakfast, directions, or small talk without a booking intent.
- missing_fields must list field names still needed for a booking inquiry (e.g. check_in, guest_name).
- confidence is a number from 0.0 to 1.0 for how certain you are about the extracted values.

JSON schema:
{
  "guest_name": string|null,
  "guest_email": string|null,
  "guest_phone": string|null,
  "check_in": "YYYY-MM-DD"|null,
  "check_out": "YYYY-MM-DD"|null,
  "guests_count": integer|null,
  "request_type": "booking"|"cancellation"|"pricing"|"availability"|"general inquiry"|null,
  "special_request": string|null,
  "missing_fields": string[],
  "confidence": number
}"""

_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def _chat_temperature() -> float:
    return _env_float("LLM_CHAT_TEMPERATURE", 0.6)


def _chat_max_tokens() -> int:
    return _env_int("LLM_CHAT_MAX_TOKENS", 450)


def is_llm_enabled() -> bool:
    return _env_bool("LLM_ENABLED", default=False)


def _get_api_key() -> str:
    """Load API key from environment only — never hardcode secrets in source."""
    return (
        os.getenv("API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
        or os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def get_llm_config() -> dict[str, str | bool | int | float]:
    configured = bool(
        os.getenv("LLM_PROVIDER", "").strip()
        and os.getenv("LLM_MODEL", "").strip()
        and _get_api_key()
    )
    enabled = is_llm_enabled()
    return {
        "enabled": enabled,
        "configured": configured,
        "active": enabled and configured,
        "reply_mode": "llm" if enabled and configured else "rule_based",
        "provider": os.getenv("LLM_PROVIDER", "").strip(),
        "model": os.getenv("LLM_MODEL", "").strip(),
        "has_api_key": bool(_get_api_key()),
        "timeout_seconds": _env_int("LLM_TIMEOUT_SECONDS", 15),
        "max_history_messages": _env_int("LLM_MAX_HISTORY_MESSAGES", 20),
        "chat_temperature": _chat_temperature(),
        "chat_max_tokens": _chat_max_tokens(),
    }


def extract_booking_fields_llm(
    message: str,
    chat_history: list[ChatTurn],
    session_fields: ExtractedFields,
    *,
    session_request_type: str | None = None,
) -> LLMExtractionResult | None:
    """
    Ask the hosted LLM to return strict JSON extraction for the current message.
    Returns None on failure so callers can fall back to rule-based extraction.
    """
    if not is_llm_enabled():
        return None

    try:
        raw_json = _call_llm_provider_json(
            message=message,
            chat_history=chat_history,
            context_block=_build_extraction_context(session_fields, session_request_type),
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
        )
        return _validate_extraction_json(raw_json)
    except Exception:  # noqa: BLE001 - safe fallback to rule-based extraction
        logger.exception("LLM extraction failed; falling back to rule-based extraction")
        return None


def generate_chat_reply(
    message: str,
    chat_history: list[ChatTurn],
    extracted_fields: ExtractedFields,
    *,
    request_type: str,
    fallback_reply: str | None = None,
    email_sent: bool = False,
    email_recipient: str | None = None,
    booking_ready: bool = False,
) -> str:
    """Generate an assistant reply with LLM when enabled, else rule-based fallback."""
    fallback = fallback_reply or build_reply(
        request_type,
        extracted_fields,
        email_sent=email_sent,
        email_recipient=email_recipient,
        booking_ready=booking_ready,
    )

    if not is_llm_enabled():
        logger.debug("LLM disabled; using rule-based reply")
        return fallback

    try:
        return _call_llm_provider_text(
            message=message,
            chat_history=chat_history,
            context_block=_build_context_block(
                extracted_fields,
                request_type,
                chat_history=chat_history,
                email_sent=email_sent,
                email_recipient=email_recipient,
            ),
            system_prompt=SYSTEM_PROMPT,
        )
    except Exception:  # noqa: BLE001 - safe fallback for any provider failure
        logger.exception("LLM reply failed; using rule-based fallback")
        return fallback


def _validate_extraction_json(raw_text: str) -> LLMExtractionResult:
    payload = _parse_json_response(raw_text)
    return LLMExtractionResult.model_validate(payload)


def _parse_json_response(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM extraction JSON must be an object")
    return data


def _build_extraction_context(
    session_fields: ExtractedFields,
    session_request_type: str | None,
) -> str:
    lines = ["Previously known session data:"]
    if session_request_type:
        lines.append(f"Session request_type: {session_request_type}")
    lines.append(_format_fields_block(session_fields))
    lines.append(
        "Use session data as the baseline. Apply updates from the latest user message and recent history. "
        "Corrections and clarifications (e.g. 'actually checkout is Sunday') override earlier values. "
        "Return the best current value for each field supported by the message and history. "
        "Prefer null over guessing when still uncertain."
    )
    return "\n".join(lines)


def _last_assistant_message(chat_history: list[ChatTurn]) -> str | None:
    for turn in reversed(chat_history):
        if turn.get("role") == "assistant":
            content = (turn.get("content") or "").strip()
            if content:
                return content
    return None


def _build_context_block(
    extracted_fields: ExtractedFields,
    request_type: str,
    *,
    chat_history: list[ChatTurn] | None = None,
    email_sent: bool = False,
    email_recipient: str | None = None,
) -> str:
    stage = conversation_stage(extracted_fields, request_type)
    missing = missing_booking_fields(extracted_fields)
    lines = [
        f"Detected request type: {request_type}",
        f"Conversation stage: {stage}",
        _format_fields_block(extracted_fields),
    ]
    if missing:
        lines.append(f"Still needed for booking: {', '.join(missing)}")
    else:
        lines.append("All core booking fields collected (check-in, check-out, guests, name).")
    if email_sent:
        recipient = email_recipient or extracted_fields.guest_email or "the guest"
        lines.append(
            f"A confirmation email with the booking details was just sent automatically to {recipient}."
        )
    last_question = _last_assistant_message(chat_history or [])
    if last_question:
        lines.append(f"Your last message to the guest: {last_question}")
    lines.append(
        "Respond naturally to the guest's latest message. Acknowledge what they said and "
        "only ask for missing details listed above."
    )
    return "Structured context for this session:\n" + "\n".join(lines)


def _format_fields_block(fields: ExtractedFields) -> str:
    field_lines = [
        ("Guest name", fields.guest_name),
        ("Guest email", fields.guest_email),
        ("Guest phone", fields.guest_phone),
        ("Check-in", _format_date(fields.check_in)),
        ("Check-out", _format_date(fields.check_out)),
        ("Guests", str(fields.guests_count) if fields.guests_count else None),
        ("Special request", fields.special_request),
    ]
    parts = [f"{label}: {value}" for label, value in field_lines if value]
    return "\n".join(parts) if parts else "No structured booking details extracted yet."


def _format_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%d %B %Y")


def _llm_config_or_raise() -> tuple[str, str, str]:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip()
    api_key = _get_api_key()
    if not provider or not model or not api_key:
        raise ValueError(
            f"LLM config incomplete (provider={provider!r}, model={model!r}, has_api_key={bool(api_key)})"
        )
    return provider, model, api_key


def _recent_history(chat_history: list[ChatTurn]) -> list[ChatTurn]:
    max_messages = _env_int("LLM_MAX_HISTORY_MESSAGES", 20)
    return chat_history[-max_messages:]


def _call_llm_provider_text(
    *,
    message: str,
    chat_history: list[ChatTurn],
    context_block: str,
    system_prompt: str,
) -> str:
    provider, model, api_key = _llm_config_or_raise()
    recent_history = _recent_history(chat_history)

    if provider == "openai":
        return _call_openai_text(
            message=message,
            chat_history=recent_history,
            context_block=context_block,
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
        )
    if provider == "anthropic":
        return _call_anthropic_text(
            message=message,
            chat_history=recent_history,
            context_block=context_block,
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
        )
    if provider == "gemini":
        return _call_gemini_text(
            message=message,
            chat_history=recent_history,
            context_block=context_block,
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
        )
    raise ValueError(f"Unsupported LLM provider: {provider!r}")


def _call_llm_provider_json(
    *,
    message: str,
    chat_history: list[ChatTurn],
    context_block: str,
    system_prompt: str,
) -> str:
    provider, model, api_key = _llm_config_or_raise()
    recent_history = _recent_history(chat_history)

    if provider == "openai":
        return _call_openai_json(
            message=message,
            chat_history=recent_history,
            context_block=context_block,
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
        )
    if provider == "anthropic":
        return _call_anthropic_json(
            message=message,
            chat_history=recent_history,
            context_block=context_block,
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
        )
    if provider == "gemini":
        return _call_gemini_json(
            message=message,
            chat_history=recent_history,
            context_block=context_block,
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
        )
    raise ValueError(f"Unsupported LLM provider: {provider!r}")


def _call_openai_text(
    *,
    message: str,
    chat_history: list[ChatTurn],
    context_block: str,
    system_prompt: str,
    model: str,
    api_key: str,
) -> str:
    messages = _openai_messages(chat_history, message, system_prompt, context_block)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": _chat_temperature(),
        "max_tokens": _chat_max_tokens(),
    }
    data = _post_json(
        _OPENAI_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload,
    )
    reply = data["choices"][0]["message"]["content"]
    return _non_empty_text(reply, "OpenAI")


def _call_openai_json(
    *,
    message: str,
    chat_history: list[ChatTurn],
    context_block: str,
    system_prompt: str,
    model: str,
    api_key: str,
) -> str:
    messages = _openai_messages(chat_history, message, system_prompt, context_block)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
    }
    data = _post_json(
        _OPENAI_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload,
    )
    return _non_empty_text(data["choices"][0]["message"]["content"], "OpenAI extraction")


def _openai_messages(
    chat_history: list[ChatTurn],
    message: str,
    system_prompt: str,
    context_block: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": context_block},
    ]
    for turn in chat_history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return messages


def _call_anthropic_text(
    *,
    message: str,
    chat_history: list[ChatTurn],
    context_block: str,
    system_prompt: str,
    model: str,
    api_key: str,
) -> str:
    payload = {
        "model": model,
        "max_tokens": _chat_max_tokens(),
        "system": f"{system_prompt}\n\n{context_block}",
        "messages": _anthropic_messages(chat_history, message),
        "temperature": _chat_temperature(),
    }
    data = _post_json(
        _ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    return _non_empty_text(data["content"][0]["text"], "Anthropic")


def _call_anthropic_json(
    *,
    message: str,
    chat_history: list[ChatTurn],
    context_block: str,
    system_prompt: str,
    model: str,
    api_key: str,
) -> str:
    payload = {
        "model": model,
        "max_tokens": 400,
        "system": f"{system_prompt}\n\n{context_block}",
        "messages": _anthropic_messages(chat_history, message),
    }
    data = _post_json(
        _ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    return _non_empty_text(data["content"][0]["text"], "Anthropic extraction")


def _anthropic_messages(chat_history: list[ChatTurn], message: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in chat_history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if not content:
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return messages


def _call_gemini_text(
    *,
    message: str,
    chat_history: list[ChatTurn],
    context_block: str,
    system_prompt: str,
    model: str,
    api_key: str,
) -> str:
    temporal_prefix = _temporal_grounding_prefix()
    payload = {
        "systemInstruction": {"parts": [{"text": f"{temporal_prefix}{system_prompt}\n\n{context_block}"}]},
        "contents": _gemini_contents(chat_history, message),
        "generationConfig": {
            "temperature": _chat_temperature(),
            "maxOutputTokens": _chat_max_tokens(),
        },
    }
    data = _post_gemini(model, api_key, payload)
    return _non_empty_text(data["candidates"][0]["content"]["parts"][0]["text"], "Gemini")


def _call_gemini_json(
    *,
    message: str,
    chat_history: list[ChatTurn],
    context_block: str,
    system_prompt: str,
    model: str,
    api_key: str,
) -> str:
    temporal_prefix = _temporal_grounding_prefix()
    payload = {
        "systemInstruction": {"parts": [{"text": f"{temporal_prefix}{system_prompt}\n\n{context_block}"}]},
        "contents": _gemini_contents(chat_history, message),
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 400,
            "responseMimeType": "application/json",
        },
    }
    data = _post_gemini(model, api_key, payload)
    return _non_empty_text(data["candidates"][0]["content"]["parts"][0]["text"], "Gemini extraction")


def _gemini_contents(chat_history: list[ChatTurn], message: str) -> list[dict[str, object]]:
    contents: list[dict[str, object]] = []
    for turn in chat_history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if not content:
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": [{"text": content}]})
    contents.append({"role": "user", "parts": [{"text": message}]})
    return contents


def _post_gemini(model: str, api_key: str, payload: dict) -> dict:
    url = f"{_GEMINI_API_BASE}/{model}:generateContent"
    return _post_json(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        payload=payload,
    )


def _post_json(url: str, headers: dict[str, str], payload: dict) -> dict:
    from .resilience import get_llm_circuit_breaker, retry_http_post

    timeout = float(_env_int("LLM_TIMEOUT_SECONDS", 15))
    return retry_http_post(
        url,
        headers=headers,
        payload=payload,
        timeout=timeout,
        circuit=get_llm_circuit_breaker(),
    )


def _non_empty_text(value: object, provider_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{provider_name} returned an empty response")
    return text
