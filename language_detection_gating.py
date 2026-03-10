from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LanguageDecision:
    detection_allowed: bool
    candidate_language: Optional[str] = None
    should_offer_confirmation: bool = False
    reason: Optional[str] = None
    meaningful_words: int = 0
    sentence_count: int = 0


class LanguageDetectionGate:
    def __init__(self) -> None:
        self._last_language: Optional[str] = None
        self._streak: int = 0

    def evaluate(
        self,
        *,
        intent_label: str,
        is_entity_response: bool,
        explicit_language_request: Optional[str],
        detected_language: Optional[str],
        current_language: Optional[str],
        confidence: Optional[float],
        meaningful_words: int,
        sentence_count: int,
    ) -> LanguageDecision:
        if explicit_language_request:
            self._reset()
            return LanguageDecision(
                detection_allowed=False,
                candidate_language=explicit_language_request,
                should_offer_confirmation=True,
                reason="explicit_request",
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
            )
        detection_allowed = (
            not is_entity_response
            and intent_label != "LANGUAGE_REQUEST"
            and meaningful_words >= 3
            and confidence is not None
            and confidence > 0.8
        )
        if not detection_allowed or not detected_language:
            self._reset()
            return LanguageDecision(
                detection_allowed=detection_allowed,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
            )
        if detected_language == self._last_language:
            self._streak += 1
        else:
            self._last_language = detected_language
            self._streak = 1
        should_offer = (
            detected_language != current_language
            and (sentence_count >= 2 or self._streak >= 2)
        )
        return LanguageDecision(
            detection_allowed=True,
            candidate_language=detected_language if should_offer else None,
            should_offer_confirmation=should_offer,
            reason="multiple_sentences_detected" if should_offer else "insufficient_language_evidence",
            meaningful_words=meaningful_words,
            sentence_count=sentence_count,
        )

    def _reset(self) -> None:
        self._last_language = None
        self._streak = 0
