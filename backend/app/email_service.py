"""Booking confirmation emails via Resend API or SMTP (Gmail, Mailpit, etc.)."""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import date
from email.message import EmailMessage

import httpx

from .field_extraction import ExtractedFields

logger = logging.getLogger("app.email_service")

_RESEND_API_URL = "https://api.resend.com/emails"


def get_email_config() -> dict[str, object]:
    smtp_user = (
        os.getenv("SMTP_USER", "").strip()
        or os.getenv("EMAIL_USER", "").strip()
    )
    smtp_password = (
        os.getenv("SMTP_PASSWORD", "").strip()
        or os.getenv("SMTP_APP_PASSWORD", "").strip()
        or os.getenv("EMAIL_PASSWORD", "").strip()
    )
    email_from = os.getenv("EMAIL_FROM", "").strip() or smtp_user
    notify_email = (
        os.getenv("BOOKING_NOTIFY_EMAIL", "").strip()
        or os.getenv("STAFF_NOTIFY_EMAIL", "").strip()
    )
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
    resend_from = (
        os.getenv("RESEND_FROM", "").strip()
        or f"{os.getenv('HOTEL_NAME', 'SMART Hotel').strip() or 'SMART Hotel'} <onboarding@resend.dev>"
    )

    mailpit_mode = smtp_host in {"mailpit", "localhost", "127.0.0.1"} and smtp_port == 1025
    smtp_configured = bool(email_from) and (
        mailpit_mode or bool(smtp_user and smtp_password)
    )
    resend_configured = bool(resend_api_key)

    provider = os.getenv("EMAIL_PROVIDER", "auto").strip().lower()
    if provider == "auto":
        if resend_configured:
            active_provider = "resend"
        elif smtp_configured:
            active_provider = "smtp"
        else:
            active_provider = "none"
    else:
        active_provider = provider

    enabled_env = os.getenv("EMAIL_ENABLED", "").strip().lower()
    if enabled_env in ("0", "false", "no"):
        enabled = False
    elif enabled_env in ("1", "true", "yes"):
        enabled = True
    else:
        enabled = resend_configured or smtp_configured

    configured = (
        (active_provider == "resend" and resend_configured)
        or (active_provider == "smtp" and smtp_configured)
        or (active_provider == "auto" and (resend_configured or smtp_configured))
    )

    return {
        "enabled": enabled,
        "configured": configured,
        "provider": active_provider,
        "resend_configured": resend_configured,
        "smtp_configured": smtp_configured,
        "mailpit_mode": mailpit_mode,
        "mailpit_ui": os.getenv("MAILPIT_UI_URL", "http://localhost:8025").strip(),
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "email_from": email_from,
        "resend_from": resend_from,
        "hotel_name": os.getenv("HOTEL_NAME", "SMART Hotel").strip() or "SMART Hotel",
        "notify_email": notify_email,
    }


def is_email_enabled() -> bool:
    cfg = get_email_config()
    return bool(cfg["enabled"] and cfg["configured"])


def _format_date(value: date) -> str:
    return value.strftime("%d %B %Y")


def _booking_detail_lines(
    fields: ExtractedFields,
    *,
    guest_email: str | None = None,
    request_type: str | None = None,
) -> list[str]:
    guest_name = fields.guest_name or "—"
    check_in = _format_date(fields.check_in) if fields.check_in else "—"
    check_out = _format_date(fields.check_out) if fields.check_out else "—"
    guests = fields.guests_count if fields.guests_count is not None else "—"
    lines = [
        f"  Guest:     {guest_name}",
        f"  Check-in:  {check_in}",
        f"  Check-out: {check_out}",
        f"  Guests:    {guests}",
    ]
    email = guest_email or fields.guest_email
    if email:
        lines.append(f"  Email:     {email}")
    if fields.guest_phone:
        lines.append(f"  Phone:     {fields.guest_phone}")
    if fields.special_request:
        lines.append(f"  Notes:     {fields.special_request}")
    if request_type:
        lines.append(f"  Request:   {request_type}")
    return lines


def build_confirmation_body(
    *,
    to_email: str,
    fields: ExtractedFields,
    hotel_name: str,
    request_type: str | None = None,
) -> tuple[str, str]:
    guest_name = fields.guest_name or "Guest"
    subject = f"{hotel_name} — booking request received"
    body_lines = [
        f"Dear {guest_name},",
        "",
        f"Thank you for contacting {hotel_name}. We have received your booking request with the following details:",
        "",
        *_booking_detail_lines(fields, guest_email=to_email, request_type=request_type),
        "",
        "This is not a confirmed reservation yet. Our team will review availability and contact you shortly.",
        "",
        "Best regards,",
        f"{hotel_name} Reception",
    ]
    return subject, "\n".join(body_lines)


def build_staff_notification_body(
    *,
    fields: ExtractedFields,
    hotel_name: str,
    guest_email: str,
    request_type: str | None = None,
) -> tuple[str, str]:
    guest_name = fields.guest_name or "Guest"
    subject = f"{hotel_name} — new booking request from {guest_name}"
    body_lines = [
        "A guest completed a booking request in the AI receptionist chat.",
        "",
        "Booking details:",
        "",
        *_booking_detail_lines(fields, guest_email=guest_email, request_type=request_type),
        "",
        "Please review availability and follow up with the guest.",
        "",
        f"{hotel_name} — automated notification",
    ]
    return subject, "\n".join(body_lines)


def _send_via_resend(*, to_email: str, subject: str, body: str) -> bool:
    cfg = get_email_config()
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return False

    from_address = str(cfg["resend_from"])
    allowed_to = os.getenv("RESEND_ALLOWED_TO", "").strip().lower()
    payload_to = to_email
    payload_body = body

    if allowed_to and to_email.lower() != allowed_to:
        payload_to = allowed_to
        payload_body = (
            f"(Resend test mode — intended for {to_email})\n\n{body}"
        )
        logger.info(
            "Resend free tier: redirecting email for %s to verified inbox %s",
            to_email,
            allowed_to,
        )

    try:
        response = httpx.post(
            _RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_address,
                "to": [payload_to],
                "subject": subject,
                "text": payload_body,
            },
            timeout=20.0,
        )
        if response.status_code in (200, 201):
            return True
        logger.error(
            "Resend API rejected email to %s: HTTP %s %s",
            to_email,
            response.status_code,
            response.text[:500],
        )
        return False
    except Exception:
        logger.exception("Resend API failed for %s", to_email)
        return False


def _send_via_smtp(*, to_email: str, subject: str, body: str) -> bool:
    cfg = get_email_config()
    hotel_name = str(cfg["hotel_name"])
    from_address = str(cfg["email_from"])

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{hotel_name} <{from_address}>"
    msg["To"] = to_email
    msg.set_content(body)

    host = str(cfg["smtp_host"])
    port = int(cfg["smtp_port"])
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() not in ("0", "false", "no")
    use_ssl = os.getenv("SMTP_USE_SSL", "false").strip().lower() in ("1", "true", "yes")
    smtp_user = str(cfg["smtp_user"])
    smtp_password = str(cfg["smtp_password"])
    needs_auth = bool(smtp_user and smtp_password)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                if needs_auth:
                    smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                if needs_auth:
                    smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP login rejected for %s@%s:%s — Gmail needs an App Password "
            "(https://myaccount.google.com/apppasswords), not your normal password. "
            "Or set RESEND_API_KEY for real delivery without Gmail SMTP.",
            smtp_user,
            host,
            port,
        )
        return False
    except Exception:
        logger.exception("SMTP failed sending email to %s via %s:%s", to_email, host, port)
        return False


def _deliver_email(*, to_email: str, subject: str, body: str) -> bool:
    cfg = get_email_config()
    provider = str(cfg["provider"])

    if provider == "resend" or (provider == "auto" and cfg["resend_configured"]):
        if _send_via_resend(to_email=to_email, subject=subject, body=body):
            logger.info("Confirmation email sent via Resend to %s", to_email)
            return True
        if provider == "resend":
            return False

    if provider in {"smtp", "auto"} and cfg["smtp_configured"]:
        if _send_via_smtp(to_email=to_email, subject=subject, body=body):
            if cfg["mailpit_mode"]:
                logger.info(
                    "Confirmation email captured by Mailpit for %s — view at %s",
                    to_email,
                    cfg["mailpit_ui"],
                )
            else:
                logger.info("Confirmation email sent via SMTP to %s", to_email)
            return True

    logger.warning("No working email provider configured; could not send to %s", to_email)
    return False


def send_booking_confirmation(
    to_email: str,
    fields: ExtractedFields,
    *,
    request_type: str | None = None,
) -> bool:
    """Send a guest confirmation email. Returns True on success, False if skipped or failed."""
    cfg = get_email_config()
    if not cfg["enabled"]:
        logger.debug("Email disabled; skipping confirmation to %s", to_email)
        return False
    if not cfg["configured"]:
        logger.warning("Email enabled but no provider is configured (Resend or SMTP)")
        return False

    hotel_name = str(cfg["hotel_name"])
    subject, body = build_confirmation_body(
        to_email=to_email,
        fields=fields,
        hotel_name=hotel_name,
        request_type=request_type,
    )
    return _deliver_email(to_email=to_email, subject=subject, body=body)


def send_staff_booking_notification(
    fields: ExtractedFields,
    *,
    guest_email: str,
    request_type: str | None = None,
) -> bool:
    """Notify hotel staff of a new booking request. Returns True on success."""
    cfg = get_email_config()
    notify_email = str(cfg.get("notify_email") or "").strip()
    if not notify_email:
        return False
    if not cfg["enabled"] or not cfg["configured"]:
        return False

    hotel_name = str(cfg["hotel_name"])
    subject, body = build_staff_notification_body(
        fields=fields,
        hotel_name=hotel_name,
        guest_email=guest_email,
        request_type=request_type,
    )
    if not _deliver_email(to_email=notify_email, subject=subject, body=body):
        return False
    logger.info("Staff booking notification sent to %s", notify_email)
    return True


def send_test_email(to_email: str) -> bool:
    """Send a simple test message to verify email delivery."""
    cfg = get_email_config()
    if not is_email_enabled():
        return False
    hotel_name = str(cfg["hotel_name"])
    subject = f"{hotel_name} — email test"
    body = (
        f"This is a test email from {hotel_name}.\n\n"
        "If you received this, booking confirmation emails are working."
    )
    return _deliver_email(to_email=to_email, subject=subject, body=body)
