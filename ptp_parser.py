from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from dialogue_normalizer import normalize_borrower_text

_CORRECTION_RE = re.compile(r"^(?:नहीं|नही|गलत|wrong|no)\s+")
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
_ORDINAL_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b", re.IGNORECASE)
_DAY_MONTH_RE = re.compile(
    r"\b(\d{1,2}|[a-z\u0900-\u097f]+)\s+"
    r"(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|"
    r"september|sept|sep|october|oct|november|nov|december|dec|"
    r"जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|सितम्बर|अक्टूबर|नवंबर|नवम्बर|दिसंबर|दिसम्बर)\b"
)
_MONTH_DAY_RE = re.compile(
    r"\b("
    r"january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|"
    r"september|sept|sep|october|oct|november|nov|december|dec|"
    r"जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|सितम्बर|अक्टूबर|नवंबर|नवम्बर|दिसंबर|दिसम्बर"
    r")\s+(\d{1,2}|[a-z\u0900-\u097f]+)\b"
)
_RELATIVE_IN_DAYS_PATTERNS = (
    re.compile(
        r"\b(?:in|after|within)\s+"
        r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
        r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty)\s+day(?:s)?\b"
    ),
    re.compile(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
        r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty)\s+day(?:s)?\s+"
        r"(?:later|from now)\b"
    ),
    re.compile(
        r"\b(\d+|ek|do|teen|char|chaar|panch|paanch|cheh|chhe|saat|aath|nau|das|dus|gyarah|"
        r"barah|terah|chaudah|pandrah|solah|satrah|atharah|unnis|bees|tees)\s+din(?:o)?\s*"
        r"(?:mein|me|baad)?\b"
    ),
    re.compile(
        r"\b(\d+|एक|दो|तीन|चार|पांच|पाँच|छह|सात|आठ|नौ|दस|ग्यारह|बारह|तेरह|चौदह|पंद्रह|"
        r"पन्द्रह|सोलह|सत्रह|अठारह|उन्नीस|बीस|तीस)\s+दिन(?:ों)?\s*(?:में|मे|बाद)?\b"
    ),
)

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
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
    "जनवरी": 1,
    "फरवरी": 2,
    "मार्च": 3,
    "अप्रैल": 4,
    "मई": 5,
    "जून": 6,
    "जुलाई": 7,
    "अगस्त": 8,
    "सितंबर": 9,
    "सितम्बर": 9,
    "अक्टूबर": 10,
    "नवंबर": 11,
    "नवम्बर": 11,
    "दिसंबर": 12,
    "दिसम्बर": 12,
}

_NUMBER_WORDS = {
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
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "chaar": 4,
    "panch": 5,
    "paanch": 5,
    "cheh": 6,
    "chhe": 6,
    "saat": 7,
    "aath": 8,
    "nau": 9,
    "das": 10,
    "dus": 10,
    "gyarah": 11,
    "barah": 12,
    "terah": 13,
    "chaudah": 14,
    "pandrah": 15,
    "solah": 16,
    "satrah": 17,
    "atharah": 18,
    "unnis": 19,
    "bees": 20,
    "tees": 30,
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
}


@dataclass(frozen=True)
class PTPParseResult:
    ptp_date: Optional[str]
    confidence: float = 0.0
    normalized_text: str = ""
    corrected: bool = False
    source: Optional[str] = None


def _ensure_now(tz: str, now: Optional[datetime]) -> datetime:
    if isinstance(now, datetime):
        if now.tzinfo is None:
            return now.replace(tzinfo=ZoneInfo(tz))
        return now
    return datetime.now(ZoneInfo(tz))


def _word_to_int(token: str) -> Optional[int]:
    value = (token or "").strip().lower()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value in _NUMBER_WORDS:
        return _NUMBER_WORDS[value]
    parts = value.split()
    if len(parts) == 2 and parts[0] in {"twenty", "thirty"} and parts[1] in _NUMBER_WORDS:
        return _NUMBER_WORDS[parts[0]] + _NUMBER_WORDS[parts[1]]
    return None


def _next_valid_day(*, day: int, month: Optional[int], today: date) -> Optional[date]:
    if day < 1 or day > 31:
        return None
    if month is not None:
        year = today.year
        for year_offset in range(0, 2):
            try:
                candidate = date(year + year_offset, month, day)
            except ValueError:
                continue
            if candidate >= today:
                return candidate
        return None
    for month_offset in range(0, 13):
        year = today.year + ((today.month - 1 + month_offset) // 12)
        month_value = ((today.month - 1 + month_offset) % 12) + 1
        try:
            candidate = date(year, month_value, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    return None


def _extract_bare_day(value: str) -> Optional[int]:
    tokens = [token for token in value.split() if token]
    if not tokens or len(tokens) > 5:
        return None
    filler_tokens = {
        "तारीख",
        "तारिख",
        "date",
        "दिन",
        "तक",
        "ko",
        "को",
        "on",
        "by",
        "pay",
        "payment",
        "भुगतान",
        "पेमेंट",
        "कर",
        "करूंगा",
        "करूँगा",
        "करूंगी",
        "करूँगी",
        "करेंगे",
        "दूंगा",
        "दूँगा",
        "दूंगी",
        "दूँगी",
        "देंगे",
        "dega",
        "denge",
    }
    day: Optional[int] = None
    for token in tokens:
        parsed = _word_to_int(token)
        if parsed is not None:
            if day is not None:
                return None
            day = parsed
            continue
        if token not in filler_tokens:
            return None
    return day


def parse_ptp_date(
    text: str,
    *,
    tz: str = "Asia/Kolkata",
    now: Optional[datetime] = None,
) -> PTPParseResult:
    normalized = normalize_borrower_text(text)
    if not normalized:
        return PTPParseResult(ptp_date=None, normalized_text="")

    corrected = bool(_CORRECTION_RE.search(normalized))
    value = _CORRECTION_RE.sub("", normalized).strip() if corrected else normalized

    now_dt = _ensure_now(tz, now)
    today = now_dt.date()

    if "आज" in value.split():
        return PTPParseResult(today.isoformat(), 0.78, normalized, corrected, "relative_today")
    if "कल" in value.split():
        return PTPParseResult((today + timedelta(days=1)).isoformat(), 0.82, normalized, corrected, "relative_tomorrow")
    if "परसों" in value.split():
        return PTPParseResult((today + timedelta(days=2)).isoformat(), 0.82, normalized, corrected, "relative_day_after")
    if "अगले हफ्ते" in value:
        return PTPParseResult((today + timedelta(days=7)).isoformat(), 0.72, normalized, corrected, "relative_next_week")

    for pattern in _RELATIVE_IN_DAYS_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        days = _word_to_int(match.group(1))
        if days is not None:
            return PTPParseResult((today + timedelta(days=days)).isoformat(), 0.86, normalized, corrected, "relative_in_days")

    match = _ISO_RE.search(value)
    if match:
        try:
            candidate = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            candidate = None
        if candidate:
            return PTPParseResult(candidate.isoformat(), 0.98, normalized, corrected, "iso")

    match = _DMY_RE.search(value)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year_raw = match.group(3)
        year = today.year if not year_raw else int(year_raw) + (2000 if len(year_raw) == 2 else 0)
        try:
            candidate = date(year, month, day)
        except ValueError:
            candidate = None
        if candidate:
            if not year_raw and candidate < today:
                candidate = date(year + 1, month, day)
            return PTPParseResult(candidate.isoformat(), 0.96, normalized, corrected, "dmy")

    for pattern, month_first in ((_DAY_MONTH_RE, False), (_MONTH_DAY_RE, True)):
        match = pattern.search(value)
        if not match:
            continue
        if month_first:
            month_token, day_token = match.group(1), match.group(2)
        else:
            day_token, month_token = match.group(1), match.group(2)
        month = _MONTHS.get(month_token)
        day = _word_to_int(day_token)
        if month and day:
            candidate = _next_valid_day(day=day, month=month, today=today)
            if candidate:
                return PTPParseResult(candidate.isoformat(), 0.95, normalized, corrected, "day_month")

    match = _ORDINAL_RE.search(value)
    if match:
        candidate = _next_valid_day(day=int(match.group(1)), month=None, today=today)
        if candidate:
            return PTPParseResult(candidate.isoformat(), 0.74, normalized, corrected, "ordinal")

    bare_day = _extract_bare_day(value)
    if bare_day is not None:
        candidate = _next_valid_day(day=bare_day, month=None, today=today)
        if candidate:
            return PTPParseResult(candidate.isoformat(), 0.68, normalized, corrected, "bare_day")

    return PTPParseResult(ptp_date=None, confidence=0.0, normalized_text=normalized, corrected=corrected, source=None)
