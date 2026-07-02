"""HIPAA-oriented log filters: redact PHI/PII from log records."""

from __future__ import annotations

import logging
import re

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b\+?\d[\d\s().-]{7,}\d\b")


def redact_pii(text: str) -> str:
    if not text:
        return text
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


class PIIRedactionFilter(logging.Filter):
    """Strip emails and phone numbers from all log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_pii(str(record.msg))
        if record.args:
            record.args = tuple(
                redact_pii(str(arg)) if isinstance(arg, str) else arg for arg in record.args
            )
        return True
