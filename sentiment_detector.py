from __future__ import annotations

from dataclasses import dataclass

from intent_classifier import normalize_text


class SentimentLevel:
    NEUTRAL = "NEUTRAL"
    CONFUSED = "CONFUSED"
    FRUSTRATED = "FRUSTRATED"
    HOSTILE = "HOSTILE"


@dataclass(frozen=True)
class SentimentResult:
    level: str
    should_terminate: bool = False
    reason: str | None = None


class SentimentDetector:
    def detect(self, text: str) -> SentimentResult:
        norm = normalize_text(text)
        if not norm:
            return SentimentResult(level=SentimentLevel.NEUTRAL)
        hostile_markers = (
            "fuck",
            "fucking",
            "fuck off",
            "shut up",
            "idiot",
            "भाड़ में जा",
            "भाड़ में जाइए",
            "चुप रह",
            "हराम",
            "साले",
            "ਭਾੜ ਵਿੱਚ ਜਾ",
            "ਚੁੱਪ ਕਰ",
        )
        if any(marker in norm for marker in hostile_markers):
            return SentimentResult(
                level=SentimentLevel.HOSTILE,
                should_terminate=True,
                reason="abusive_language",
            )
        confused_markers = (
            "what",
            "repeat",
            "again",
            "not clear",
            "don t know",
            "dont know",
            "नहीं पता",
            "समझा नहीं",
            "क्या",
            "ਨਹੀਂ ਪਤਾ",
            "ਸਮਝ ਨਹੀਂ ਆਇਆ",
            "ਕੀ",
        )
        if any(marker in norm for marker in confused_markers):
            return SentimentResult(
                level=SentimentLevel.CONFUSED,
                reason="clarification_needed",
            )
        frustrated_markers = (
            "frustrated",
            "annoyed",
            "stop calling",
            "tired",
            " परेशान",
            "परेशान",
            "तंग",
            "irritated",
            "ਬਹੁਤ ਹੋ ਗਿਆ",
            "ਤੰਗ",
        )
        if any(marker in norm for marker in frustrated_markers):
            return SentimentResult(
                level=SentimentLevel.FRUSTRATED,
                reason="customer_frustration",
            )
        return SentimentResult(level=SentimentLevel.NEUTRAL)
