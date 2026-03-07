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
    _THIRD_PARTY_DISCLOSURE_PATTERNS = (
        "family",
        "relative",
        "neighbor",
        "neighbour",
        "office",
        "employer",
        "manager",
        "colleague",
        "friends",
        "whatsapp group",
        "social media",
    )
    _LEGAL_MISREPRESENTATION_PATTERNS = (
        "arrest",
        "warrant",
        "criminal case",
        "fir",
        "passport",
        "salary attachment",
        "property seizure",
    )
    _HARDSHIP_PRESSURE_PATTERNS = (
        "pay now",
        "pay immediately",
        "today itself",
        "right now",
        "immediately",
        "without fail today",
    )

    def evaluate_assistant_text(
        self,
        *,
        text: str,
        consent: bool | None,
        identity_confirmed: bool,
        current_step: str,
        hardship_detected: bool = False,
        dispute_raised: bool = False,
        legal_hold: bool = False,
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

        if any(p in t for p in self._THIRD_PARTY_DISCLOSURE_PATTERNS):
            out.append(
                ComplianceViolation(
                    rule_code="THIRD_PARTY_DISCLOSURE_RISK",
                    severity="high",
                    detail="Assistant appears to threaten or imply disclosure to third parties.",
                    excerpt=text[:200],
                )
            )

        if any(p in t for p in self._LEGAL_MISREPRESENTATION_PATTERNS):
            out.append(
                ComplianceViolation(
                    rule_code="LEGAL_MISREPRESENTATION_RISK",
                    severity="high",
                    detail="Assistant appears to imply legal consequences that may be misleading or coercive.",
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
        if payment_ask and legal_hold:
            out.append(
                ComplianceViolation(
                    rule_code="LEGAL_HOLD_COLLECTION_ASK",
                    severity="high",
                    detail="Assistant asked for payment after legal escalation was detected.",
                    excerpt=text[:200],
                )
            )
        if payment_ask and dispute_raised and "undisputed" not in t and "review" not in t:
            out.append(
                ComplianceViolation(
                    rule_code="DISPUTE_COLLECTION_PRESSURE",
                    severity="medium",
                    detail="Assistant may be pressing collection despite an active dispute.",
                    excerpt=text[:200],
                )
            )
        if hardship_detected and any(p in t for p in self._HARDSHIP_PRESSURE_PATTERNS):
            out.append(
                ComplianceViolation(
                    rule_code="HARDSHIP_PRESSURE_RISK",
                    severity="medium",
                    detail="Assistant used immediate-payment pressure even though hardship was detected.",
                    excerpt=text[:200],
                )
            )
        return out
