from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ComplianceViolation:
    rule_code: str
    severity: str
    detail: str
    excerpt: str


class ComplianceEngine:
    """Rule-based compliance checks for assistant utterances and workflow state."""

    _SENSITIVE_PATTERNS = (
        "otp",
        "cvv",
        "card number",
        "password",
        "pin",
        "netbanking",
        "full bank",
        "debit card",
        "credit card",
    )
    _HARASSMENT_PATTERNS = (
        "threat",
        "police case",
        "jail",
        "seize",
        "harass",
        "public shame",
        "fraudster",
        "cheater",
        "ghar pe aayenge",
    )

    def evaluate_assistant_text(
        self,
        *,
        text: str,
        consent: bool | None,
        identity_confirmed: bool,
        current_step: str,
    ) -> List[ComplianceViolation]:
        t = (text or "").lower()
        out: List[ComplianceViolation] = []
        if not t.strip():
            return out

        if any(p in t for p in self._SENSITIVE_PATTERNS):
            out.append(
                ComplianceViolation(
                    rule_code="DISALLOWED_SENSITIVE_ASK",
                    severity="high",
                    detail="Assistant requested sensitive financial/security information.",
                    excerpt=text[:200],
                )
            )

        if any(p in t for p in self._HARASSMENT_PATTERNS):
            out.append(
                ComplianceViolation(
                    rule_code="HARASSMENT_OR_THREAT",
                    severity="high",
                    detail="Assistant language appears threatening/harassing.",
                    excerpt=text[:200],
                )
            )

        payment_ask = (
            "have you made" in t
            or "when can you pay" in t
            or "payment" in t and "date" in t
            or "promise" in t and "pay" in t
            or "make payment" in t
            or "pay now" in t
        )
        if payment_ask and consent is not True:
            out.append(
                ComplianceViolation(
                    rule_code="MISSING_CONSENT_GATE",
                    severity="medium",
                    detail="Payment collection ask before explicit consent.",
                    excerpt=text[:200],
                )
            )
        if payment_ask and not identity_confirmed and current_step not in {"confirm_identity", "consent"}:
            out.append(
                ComplianceViolation(
                    rule_code="MISSING_IDENTITY_GATE",
                    severity="medium",
                    detail="Payment collection ask before identity confirmation.",
                    excerpt=text[:200],
                )
            )
        return out
