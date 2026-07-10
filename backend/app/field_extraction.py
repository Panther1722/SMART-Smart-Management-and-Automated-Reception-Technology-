"""Rule-based extraction of booking fields from free-text chat messages."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{1,6})?(?!\w)",
)

_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bmy name is\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bI am\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bI'm\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bthis is\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,2})",
        re.IGNORECASE,
    ),
)

_GUESTS_RE = re.compile(
    r"\b(?:for\s+)?(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:guests?|people|persons?|pax)\b",
    re.IGNORECASE,
)

_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_SLASH_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b")
# Month word is restricted to actual month names/abbreviations so filler words
# like "is"/"on"/"at" in phrases such as "check out date is 15 july" can't be
# mistaken for a month and consume the day number before the real date match.
_MONTH_WORD_RE = "(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + ")"
_TEXT_DATE_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_WORD_RE})(?:\s+(\d{{4}}))?\b"
    rf"|\b({_MONTH_WORD_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+(\d{{4}}))?\b",
    re.IGNORECASE,
)

_CHECK_IN_RE = re.compile(
    r"check[\s-]?in(?:\s+(?:on|date|is))?\s+(?P<date>.+?)(?=\s+check[\s-]?out|\s+for\s+\d|\s*$)",
    re.IGNORECASE,
)
_CHECK_OUT_RE = re.compile(
    r"check[\s-]?out(?:\s+(?:on|date|is))?\s+(?P<date>.+?)(?=\s+for\s+\d|\s*$)",
    re.IGNORECASE,
)
_DATE_RANGE_RE = re.compile(
    r"\bfrom\s+(?P<start>.+?)\s+(?:to|until|till|-)\s+(?P<end>.+?)(?=\s+for\s|\s*$)",
    re.IGNORECASE,
)
_DATE_RANGE_TO_RE = re.compile(
    r"\b(?P<start>\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+(?:\s+\d{4})?)"
    r"\s+(?:to|until|till|-)\s+"
    r"(?P<end>\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+(?:\s+\d{4})?)",
    re.IGNORECASE,
)
_ORDINAL_DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([A-Za-z]+)(?:\s+(\d{4}))?\b",
    re.IGNORECASE,
)
_FOR_TODAY_RE = re.compile(r"\b(?:for|on)\s+today\b", re.IGNORECASE)
_TODAY_WORD_RE = re.compile(r"\btoday\b", re.IGNORECASE)

_SPECIAL_REQUEST_LABEL_RE = re.compile(
    r"(?:special request(?:s)?|note|please note|request)\s*[:\-]?\s*(.+)",
    re.IGNORECASE,
)

_SPECIAL_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("late check-in", "Late check-in requested"),
    ("late check in", "Late check-in requested"),
    ("early check-out", "Early check-out requested"),
    ("early check out", "Early check-out requested"),
    ("sea view", "Sea view requested"),
    ("quiet room", "Quiet room requested"),
    ("extra bed", "Extra bed requested"),
    ("wheelchair", "Wheelchair accessibility requested"),
    ("pet friendly", "Pet-friendly room requested"),
    ("non-smoking", "Non-smoking room requested"),
    ("non smoking", "Non-smoking room requested"),
)

_NAME_STOPWORDS = frozenset(
    {
        "interested",
        "looking",
        "calling",
        "writing",
        "booking",
        "here",
        "trying",
        "wondering",
    }
)


@dataclass
class ExtractedFields:
    guest_name: str | None = None
    guest_email: str | None = None
    guest_phone: str | None = None
    check_in: date | None = None
    check_out: date | None = None
    guests_count: int | None = None
    special_request: str | None = None


def merge_fields(base: ExtractedFields, overlay: ExtractedFields) -> ExtractedFields:
    """Merge two field sets; overlay values win when present."""
    merged = ExtractedFields(**{f.name: getattr(base, f.name) for f in fields(ExtractedFields)})
    for field in fields(ExtractedFields):
        value = getattr(overlay, field.name)
        if value is not None:
            setattr(merged, field.name, value)
    return merged


def fields_from_booking_request(row) -> ExtractedFields:
    """Build ExtractedFields from a BookingRequest ORM row."""
    return ExtractedFields(
        guest_name=row.guest_name,
        guest_email=row.guest_email,
        guest_phone=row.guest_phone,
        check_in=row.check_in,
        check_out=row.check_out,
        guests_count=row.guests_count,
        special_request=row.special_request,
    )


def extract_fields(message: str, *, today: date | None = None) -> ExtractedFields:
    """Extract structured booking fields from a single chat message."""
    today = today or date.today()
    dates = _extract_dates(message, today)
    return ExtractedFields(
        guest_name=_extract_name(message),
        guest_email=_extract_email(message),
        guest_phone=_extract_phone(message),
        check_in=dates.check_in,
        check_out=dates.check_out,
        guests_count=_extract_guests_count(message),
        special_request=_extract_special_request(message),
    )


def message_mentions_today(message: str) -> bool:
    """Return True when the message includes the word 'today'."""
    return bool(_TODAY_WORD_RE.search(message))


def _extract_email(message: str) -> str | None:
    match = _EMAIL_RE.search(message)
    return match.group(0).lower() if match else None


def _extract_phone(message: str) -> str | None:
    match = _PHONE_RE.search(message)
    if not match:
        return None
    phone = re.sub(r"\s+", " ", match.group(0).strip())
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        return None
    return phone


def _extract_name(message: str) -> str | None:
    for pattern in _NAME_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        name = " ".join(part.capitalize() for part in match.group(1).split())
        first = name.split()[0].lower()
        if first in _NAME_STOPWORDS:
            continue
        return name[:200]
    return None


def _extract_guests_count(message: str) -> int | None:
    match = _GUESTS_RE.search(message)
    if not match:
        return None
    raw = match.group("count").lower()
    if raw.isdigit():
        count = int(raw)
        return count if count >= 1 else None
    return _WORD_NUMBERS.get(raw)


def _extract_special_request(message: str) -> str | None:
    label_match = _SPECIAL_REQUEST_LABEL_RE.search(message)
    if label_match:
        text = label_match.group(1).strip()
        if text:
            return text[:2000]

    found: list[str] = []
    lowered = message.lower()
    for keyword, label in _SPECIAL_KEYWORDS:
        if keyword in lowered:
            found.append(label)
    if found:
        return "; ".join(dict.fromkeys(found))
    return None


def _extract_dates(message: str, today: date) -> ExtractedFields:
    check_in: date | None = None
    check_out: date | None = None

    range_match = _DATE_RANGE_RE.search(message)
    if range_match:
        check_in = _parse_date_phrase(range_match.group("start"), today)
        check_out = _parse_date_phrase(range_match.group("end"), today)

    if not (check_in and check_out):
        range_to_match = _DATE_RANGE_TO_RE.search(message)
        if range_to_match:
            check_in = check_in or _parse_date_phrase(range_to_match.group("start"), today)
            check_out = check_out or _parse_date_phrase(range_to_match.group("end"), today)

    in_match = _CHECK_IN_RE.search(message)
    if in_match:
        check_in = _parse_date_phrase(in_match.group("date"), today)

    out_match = _CHECK_OUT_RE.search(message)
    if out_match:
        check_out = _parse_date_phrase(out_match.group("date"), today)

    if check_in and check_out and check_out < check_in:
        check_in, check_out = check_out, check_in

    if check_in or check_out:
        return ExtractedFields(check_in=check_in, check_out=check_out)

    if _FOR_TODAY_RE.search(message):
        return ExtractedFields(check_in=today)

    found_dates = _find_all_dates(message, today)
    if len(found_dates) >= 2:
        found_dates.sort()
        return ExtractedFields(check_in=found_dates[0], check_out=found_dates[1])
    if len(found_dates) == 1:
        return ExtractedFields(check_in=found_dates[0])

    return ExtractedFields()


def _find_all_dates(message: str, today: date) -> list[date]:
    found: list[date] = []

    for match in _ISO_DATE_RE.finditer(message):
        parsed = _parse_iso_date(match.group(1))
        if parsed:
            found.append(parsed)

    for match in _SLASH_DATE_RE.finditer(message):
        parsed = _parse_slash_date(match.group(1), today)
        if parsed:
            found.append(parsed)

    for match in _TEXT_DATE_RE.finditer(message):
        parsed = _parse_text_date_match(match, today)
        if parsed:
            found.append(parsed)

    for match in _ORDINAL_DATE_RE.finditer(message):
        parsed = _parse_ordinal_date_match(match, today)
        if parsed:
            found.append(parsed)

    unique: list[date] = []
    for item in found:
        if item not in unique:
            unique.append(item)
    return unique


def _parse_date_phrase(phrase: str, today: date) -> date | None:
    phrase = phrase.strip(" ,.")
    if not phrase:
        return None

    relative = _parse_relative_date(phrase, today)
    if relative:
        return relative

    iso = _ISO_DATE_RE.search(phrase)
    if iso:
        return _parse_iso_date(iso.group(1))

    slash = _SLASH_DATE_RE.search(phrase)
    if slash:
        return _parse_slash_date(slash.group(1), today)

    # Try every candidate match, not just the first: a leading filler word
    # (e.g. "is 15 july") can match the day/month pattern with an invalid
    # month name ("is") before the real date is reached.
    for text in _TEXT_DATE_RE.finditer(phrase):
        parsed = _parse_text_date_match(text, today)
        if parsed:
            return parsed

    ordinal = _ORDINAL_DATE_RE.search(phrase)
    if ordinal:
        return _parse_ordinal_date_match(ordinal, today)

    return _find_all_dates(phrase, today)[0] if _find_all_dates(phrase, today) else None


def _parse_relative_date(phrase: str, today: date) -> date | None:
    """Parse today, tomorrow, tonight and similar relative date words."""
    normalized = phrase.strip().lower().split(",")[0].strip()
    offsets = {
        "today": 0,
        "tonight": 0,
        "tomorrow": 1,
    }
    for keyword, offset in offsets.items():
        if normalized == keyword or normalized.startswith(f"{keyword} "):
            return today + timedelta(days=offset)
    return None


def _parse_ordinal_date_match(match: re.Match[str], today: date) -> date | None:
    day = int(match.group(1))
    month_name = match.group(2).lower()
    year = int(match.group(3)) if match.group(3) else today.year
    month = _MONTHS.get(month_name)
    if not month:
        return None
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    return _ensure_future_year(parsed, today)


def _parse_iso_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_slash_date(value: str, today: date) -> date | None:
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d/%m/%y", "%m/%d/%y"):
        try:
            parsed = datetime.strptime(value, fmt).date()
            if parsed.year < 100:
                parsed = parsed.replace(year=today.year)
            return _ensure_future_year(parsed, today)
        except ValueError:
            continue
    return None


def _parse_text_date_match(match: re.Match[str], today: date) -> date | None:
    if match.group(1) and match.group(2):
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3)) if match.group(3) else today.year
    elif match.group(4) and match.group(5):
        month_name = match.group(4).lower()
        day = int(match.group(5))
        year = int(match.group(6)) if match.group(6) else today.year
    else:
        return None

    month = _MONTHS.get(month_name)
    if not month:
        return None

    try:
        parsed = date(year, month, day)
    except ValueError:
        return None

    return _ensure_future_year(parsed, today)


def _ensure_future_year(parsed: date, today: date) -> date:
    """If no year was given and the date looks past, assume next year."""
    if parsed.year != today.year:
        return parsed
    if parsed < today:
        try:
            return parsed.replace(year=today.year + 1)
        except ValueError:
            return parsed
    return parsed
