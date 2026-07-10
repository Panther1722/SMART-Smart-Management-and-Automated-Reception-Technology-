"""Deterministic normalization of relative date phrases.

This module intentionally keeps scope narrow: it only normalizes a few common,
unambiguous relative expressions using the server's local timezone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class NormalizedRelativeDates:
    check_in: date | None = None
    check_out: date | None = None


_TODAY_RE = re.compile(r"\btoday'?s?\b", re.IGNORECASE)
_TOMORROW_RE = re.compile(r"\btomorrow'?s?\b", re.IGNORECASE)
_DAY_AFTER_TOMORROW_RE = re.compile(r"\bday\s+after\s+tomorrow'?s?\b", re.IGNORECASE)
_NEXT_WEEK_RE = re.compile(r"\bnext\s+week\b", re.IGNORECASE)
_THIS_WEEKDAY_RE = re.compile(
    r"\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_NEXT_WEEKDAY_RE = re.compile(
    r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)

_WEEKDAYS: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def local_today() -> date:
    """Server-local current date (timezone-aware)."""
    return datetime.now().astimezone().date()


def normalize_relative_dates(message: str, *, base_date: date | None = None) -> NormalizedRelativeDates:
    """
    Normalize relative date expressions in a single message.

    Returns only unambiguous values. If the phrase is too vague (e.g. "next week"),
    we prefer returning None so the assistant can ask a clarifying question.
    """
    base = base_date or local_today()
    lowered = message.strip().lower()
    if not lowered:
        return NormalizedRelativeDates()

    # Most specific first.
    if _DAY_AFTER_TOMORROW_RE.search(lowered):
        return NormalizedRelativeDates(check_in=base + timedelta(days=2))
    if _TOMORROW_RE.search(lowered):
        return NormalizedRelativeDates(check_in=base + timedelta(days=1))
    if _TODAY_RE.search(lowered):
        return NormalizedRelativeDates(check_in=base)

    # "this Friday" / "next Friday"
    this_match = _THIS_WEEKDAY_RE.search(lowered)
    if this_match:
        weekday = _WEEKDAYS[this_match.group(1).lower()]
        return NormalizedRelativeDates(check_in=_next_weekday(base, weekday, include_today=True))

    next_match = _NEXT_WEEKDAY_RE.search(lowered)
    if next_match:
        weekday = _WEEKDAYS[next_match.group(1).lower()]
        this_occurrence = _next_weekday(base, weekday, include_today=True)
        # "next Friday" should never be earlier than 7 days out.
        if this_occurrence <= base + timedelta(days=6):
            return NormalizedRelativeDates(check_in=this_occurrence + timedelta(days=7))
        return NormalizedRelativeDates(check_in=this_occurrence)

    # "next week" is often ambiguous (Mon? any day? a range?) → don't invent.
    if _NEXT_WEEK_RE.search(lowered):
        return NormalizedRelativeDates()

    return NormalizedRelativeDates()


def _next_weekday(base: date, weekday: int, *, include_today: bool) -> date:
    base_weekday = base.weekday()
    days_ahead = (weekday - base_weekday) % 7
    if days_ahead == 0 and not include_today:
        days_ahead = 7
    return base + timedelta(days=days_ahead)

