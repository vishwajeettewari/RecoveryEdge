from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_DMY_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_NUMBER_WORDS = {
    "zero": 0,
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
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "एक": 1,
    "दो": 2,
    "तीन": 3,
    "चार": 4,
    "पांच": 5,
    "पाँच": 5,
    "छह": 6,
    "सात": 7,
    "आठ": 8,
    "नौ": 9,
    "दस": 10,
    "ग्यारह": 11,
    "बारह": 12,
    "तेरह": 13,
    "चौदह": 14,
    "पंद्रह": 15,
    "पन्द्रह": 15,
    "सोलह": 16,
    "सत्रह": 17,
    "अठारह": 18,
    "उन्नीस": 19,
    "बीस": 20,
    "तीस": 30,
    "इक": 1,
    "ਇਕ": 1,
    "ਇੱਕ": 1,
    "ਦੋ": 2,
    "ਤਿੰਨ": 3,
    "ਚਾਰ": 4,
    "ਪੰਜ": 5,
    "ਛੇ": 6,
    "ਸੱਤ": 7,
    "ਅੱਠ": 8,
    "ਨੌ": 9,
    "ਦਸ": 10,
}

_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def _ensure_now(tz: str, now: Optional[datetime]) -> datetime:
    if isinstance(now, datetime):
        if now.tzinfo is None:
            return now.replace(tzinfo=ZoneInfo(tz))
        return now
    return datetime.now(ZoneInfo(tz))


def _normalize_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", (text or "")).casefold()
    out = []
    for ch in t:
        if ch.isspace():
            out.append(" ")
            continue
        cat = unicodedata.category(ch)
        if cat[0] in {"L", "N"} or cat in {"Mn", "Mc", "Me"} or ch in {":", "/", "-"}:
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _word_to_int(raw: str) -> Optional[int]:
    token = (raw or "").strip().lower().replace("-", " ")
    token = " ".join(token.split())
    if not token:
        return None
    if token.isdigit():
        try:
            return int(token)
        except ValueError:
            try:
                return int("".join(str(unicodedata.digit(ch)) for ch in token))
            except Exception:
                return None
    if token in _NUMBER_WORDS:
        return _NUMBER_WORDS[token]
    parts = token.split()
    if len(parts) == 2 and parts[0] in {"twenty", "thirty"} and parts[1] in _NUMBER_WORDS:
        tail = _NUMBER_WORDS[parts[1]]
        if 0 <= tail <= 9:
            return _NUMBER_WORDS[parts[0]] + tail
    return None


def parse_date_from_text(text: str, *, tz: str, now: Optional[datetime] = None) -> Optional[str]:
    t = _normalize_text(text)
    if not t:
        return None

    tokens = t.split()

    now_dt = _ensure_now(tz, now)
    today = now_dt.date()

    if "day after tomorrow" in t:
        return (today + timedelta(days=2)).isoformat()
    if "today" in tokens or "aaj" in tokens or "आज" in tokens or "ਅੱਜ" in tokens:
        return today.isoformat()
    if "tomorrow" in tokens or "kal" in tokens or "कल" in tokens or "ਕੱਲ" in tokens:
        return (today + timedelta(days=1)).isoformat()
    if "parso" in tokens or "parson" in tokens or "परसों" in tokens or "ਪਰਸੋਂ" in tokens:
        return (today + timedelta(days=2)).isoformat()

    # Relative offsets like "in 10 days", "after ten days", "10 दिन में".
    relative_patterns = (
        r"\b(?:in|after|within)\s+([a-z0-9-]+(?:\s+[a-z0-9-]+)?)\s+day(?:s)?\b",
        r"\b([a-z0-9-]+(?:\s+[a-z0-9-]+)?)\s+day(?:s)?\s+(?:later|from now)\b",
        r"\b(?:in|after)\s+(\d{1,3})\s+din(?:o)?\b",
        r"\b(\d{1,3})\s+din(?:o)?\s+(?:mein|me|later)?\b",
        r"\b([^\s]+)\s+दिन(?:ों)?\s*(?:में|मे|बाद)?\b",
        r"\b([^\s]+)\s+ਦਿਨ(?:ਾਂ)?\s*(?:ਵਿੱਚ|ਚ|ਬਾਅਦ)?\b",
    )
    for pattern in relative_patterns:
        m = re.search(pattern, t)
        if not m:
            continue
        day_count = _word_to_int(m.group(1))
        if day_count is None:
            continue
        if day_count < 0:
            return None
        return (today + timedelta(days=day_count)).isoformat()

    if "next" in tokens:
        for i, tok in enumerate(tokens[:-1]):
            if tok == "next":
                candidate = tokens[i + 1]
                if candidate in _WEEKDAYS:
                    idx = _WEEKDAYS[candidate]
                    days_ahead = (idx - today.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    return (today + timedelta(days=days_ahead)).isoformat()

    for tok in tokens:
        if tok in _WEEKDAYS:
            idx = _WEEKDAYS[tok]
            days_ahead = (idx - today.weekday()) % 7
            return (today + timedelta(days=days_ahead)).isoformat()

    m = _DATE_ISO_RE.search(t)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d.isoformat()
        except ValueError:
            return None

    m = _DATE_DMY_RE.search(t)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year_raw = m.group(3)
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year = 2000 + year
        else:
            year = today.year
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if year_raw is None and d < today:
            try:
                d = date(year + 1, month, day)
            except ValueError:
                return None
        return d.isoformat()

    return None


def parse_time_from_text(text: str, *, allow_implicit: bool = False) -> Optional[str]:
    t = _normalize_text(text)
    if not t:
        return None

    for word, num in _NUMBER_WORDS.items():
        t = re.sub(rf"\b{word}\b", str(num), t)

    if "noon" in t:
        return "12:00"
    if "midnight" in t:
        return "00:00"

    m = _TIME_RE.search(t)
    if not m:
        return None

    has_meridiem = bool(m.group(3))
    has_colon = bool(m.group(2))
    time_context = any(
        x in t
        for x in (
            "am",
            "pm",
            "at ",
            "time",
            "call",
            "callback",
            "later",
            "between",
            "around",
            "by ",
        )
    )
    if not allow_implicit and not (has_meridiem or has_colon or time_context):
        return None

    hour = int(m.group(1))
    minute = int(m.group(2) or "00")
    meridiem = (m.group(3) or "").lower()

    if meridiem:
        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12

    if hour > 23 or minute > 59:
        return None

    return f"{hour:02d}:{minute:02d}"


def validate_ptp_date(
    date_str: str,
    *,
    tz: str,
    now: Optional[datetime] = None,
    min_days: int = 0,
    max_days: int = 30,
) -> bool:
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return False

    now_dt = _ensure_now(tz, now)
    today = now_dt.date()
    if d < today:
        return False
    delta = (d - today).days
    if delta < min_days or delta > max_days:
        return False
    return True


def validate_callback_time(time_str: str, *, start_hour: int = 9, end_hour: int = 20) -> bool:
    try:
        hour, minute = time_str.split(":")
        hour_i = int(hour)
        minute_i = int(minute)
    except ValueError:
        return False
    if hour_i < 0 or hour_i > 23 or minute_i < 0 or minute_i > 59:
        return False
    return start_hour <= hour_i <= end_hour
