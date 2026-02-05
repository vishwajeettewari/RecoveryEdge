import re
from typing import Optional


_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")

# Very conservative phone matcher (handles +91 / spaces / dashes).
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s\-]?)?(?:\d[\s\-]?){9,12}\d(?!\w)")

# PAN (India): 5 letters + 4 digits + 1 letter.
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)

# Aadhaar (India): 12 digits, often written as 4-4-4. Keep it strict to avoid false positives.
_AADHAAR_RE = re.compile(r"(?<!\d)(?:\d{4}[\s\-]?){2}\d{4}(?!\d)")


def redact_pii(text: Optional[str]) -> Optional[str]:
    """Best-effort PII redaction for demo logs and exports.

    This is intentionally regex-based (offline and deterministic).
    """
    if text is None:
        return None
    t = str(text)
    t = _EMAIL_RE.sub("[REDACTED_EMAIL]", t)
    t = _PAN_RE.sub("[REDACTED_PAN]", t)
    t = _AADHAAR_RE.sub("[REDACTED_AADHAAR]", t)
    t = _PHONE_RE.sub("[REDACTED_PHONE]", t)
    return t

