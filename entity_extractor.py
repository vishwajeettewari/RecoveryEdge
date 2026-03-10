from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from datetime_utils import parse_date_from_text, parse_time_from_text


@dataclass(frozen=True)
class ExtractedEntities:
    customer_name: Optional[str] = None
    amount: Optional[str] = None
    ptp_date: Optional[str] = None
    callback_time: Optional[str] = None
    payment_status: Optional[bool] = None
    reference_number: Optional[str] = None


class EntityExtractor:
    def __init__(self, *, tz: str = "Asia/Kolkata") -> None:
        self._tz = tz

    def extract(self, text: str, *, current_step: Optional[str]) -> ExtractedEntities:
        raw = (text or "").strip()
        if not raw:
            return ExtractedEntities()
        customer_name = self._extract_name(raw, current_step=current_step)
        amount = self._extract_amount(raw)
        ptp_date = parse_date_from_text(raw, tz=self._tz)
        callback_time = self._extract_callback_time(raw)
        payment_status = self._extract_payment_status(raw)
        reference_number = self._extract_reference_number(raw)
        return ExtractedEntities(
            customer_name=customer_name,
            amount=amount,
            ptp_date=ptp_date,
            callback_time=callback_time,
            payment_status=payment_status,
            reference_number=reference_number,
        )

    def _extract_name(self, text: str, *, current_step: Optional[str]) -> Optional[str]:
        patterns = (
            r"\b(?:my name is|i am|i'm|im|this is)\s+([A-Za-z][A-Za-z\s\-']{1,40})\b",
            r"(?:मेरा नाम)\s+([\u0900-\u097f][\u0900-\u097f\s]{1,40})",
            r"(?:ਮੇਰਾ ਨਾਮ|ਮੇਰਾ ਨਾਂ)\s+([\u0a00-\u0a7f][\u0a00-\u0a7f\s]{1,40})",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return " ".join(match.group(1).strip(" .,").split())
        if current_step == "confirm_identity":
            bare = text.strip(" .,!?\t")
            tokens = [tok for tok in bare.split() if tok]
            if 1 <= len(tokens) <= 4 and not any(any(ch.isdigit() for ch in tok) for tok in tokens):
                return " ".join(tokens)
        return None

    def _extract_amount(self, text: str) -> Optional[str]:
        match = re.search(r"(?:₹|\brs\.?|\brupees\b)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", text, re.IGNORECASE)
        if not match:
            return None
        return match.group(1).replace(",", "")

    def _extract_callback_time(self, text: str) -> Optional[str]:
        if not re.search(r"\b(call me|call back|callback|call|ਕਾਲ|कॉल)\b", text, re.IGNORECASE):
            return None
        return parse_time_from_text(text, allow_implicit=False)

    def _extract_payment_status(self, text: str) -> Optional[bool]:
        norm = " ".join(text.casefold().split())
        done_markers = (
            "already paid",
            "paid",
            "payment done",
            "कर दिया",
            "हो गया",
            "ਕਰ ਦਿੱਤਾ",
        )
        pending_markers = (
            "not paid",
            "बाकी है",
            "pending",
            "नहीं किया",
            "ਬਾਕੀ ਹੈ",
            "ਹਾਲੇ ਬਾਕੀ",
        )
        if any(marker in norm for marker in done_markers):
            return True
        if any(marker in norm for marker in pending_markers):
            return False
        return None

    def _extract_reference_number(self, text: str) -> Optional[str]:
        match = re.search(r"\b(?:ref(?:erence)?\s*(?:no\.?|number)?|utr)\s*[:\-]?\s*([A-Za-z0-9\-]{6,})\b", text, re.IGNORECASE)
        if not match:
            return None
        return match.group(1)
