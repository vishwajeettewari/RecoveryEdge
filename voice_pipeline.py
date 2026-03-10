from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from barge_in_handler import BargeInDecision, BargeInHandler
from dialogue_state_manager import DialogueState, DialogueStateManager
from entity_extractor import EntityExtractor, ExtractedEntities
from intent_classifier import IntentClassifier, IntentResult, VoiceIntent, detect_script_language, normalize_text
from language_detection_gating import LanguageDecision, LanguageDetectionGate as _LanguageDetectionGate
from repetition_guard import RepetitionAction, RepetitionDecision, RepetitionGuard as _RepetitionGuard
from sentiment_detector import SentimentDetector, SentimentLevel, SentimentResult


class UserIntent:
    IDENTITY_RESPONSE = VoiceIntent.IDENTITY_RESPONSE
    NAME_RESPONSE = VoiceIntent.IDENTITY_RESPONSE
    AWARENESS_YES = VoiceIntent.AWARENESS_YES
    AWARENESS_NO = VoiceIntent.AWARENESS_NO
    PAYMENT_DONE = VoiceIntent.PAYMENT_DONE
    PAYMENT_NOT_DONE = VoiceIntent.PAYMENT_NOT_DONE
    PAYMENT_PROMISE = VoiceIntent.PROMISE_TO_PAY
    PROMISE_TO_PAY = VoiceIntent.PROMISE_TO_PAY
    QUESTION = VoiceIntent.QUESTION
    CONFUSION = VoiceIntent.CONFUSION
    ABUSE = VoiceIntent.ABUSE
    LANGUAGE_REQUEST = VoiceIntent.LANGUAGE_REQUEST
    ENTITY_RESPONSE = "ENTITY_RESPONSE"
    PAYMENT_STATUS = "PAYMENT_STATUS"
    OTHER = VoiceIntent.OTHER


class InterruptionIntent:
    CORRECTION = "CORRECTION"
    CONFUSION = "CONFUSION"
    PAYMENT_STATUS = "PAYMENT_STATUS"
    QUESTION = "QUESTION"
    LANGUAGE_PREFERENCE = "LANGUAGE_PREFERENCE"
    HOSTILE = "HOSTILE"
    OTHER = "OTHER"


class UtteranceIntentClassifier:
    def __init__(self, *, tz: str = "Asia/Kolkata") -> None:
        self._classifier = IntentClassifier(tz=tz)

    def classify_result(
        self,
        text: str,
        *,
        current_step: Optional[str],
        explicit_language_request: Optional[str] = None,
    ) -> IntentResult:
        return self._classifier.classify(
            text,
            current_step=current_step,
            explicit_language_request=explicit_language_request,
        )

    def classify(
        self,
        text: str,
        *,
        current_step: Optional[str],
        explicit_language_request: Optional[str] = None,
    ) -> str:
        result = self.classify_result(
            text,
            current_step=current_step,
            explicit_language_request=explicit_language_request,
        )
        if result.is_entity_response and result.label == VoiceIntent.OTHER:
            return UserIntent.ENTITY_RESPONSE
        if result.label in {VoiceIntent.PAYMENT_DONE, VoiceIntent.PAYMENT_NOT_DONE}:
            return UserIntent.PAYMENT_STATUS
        return result.label

    def meaningful_word_count(self, text: str) -> int:
        return self._classifier.meaningful_word_count(text)

    def sentence_count(self, text: str) -> int:
        return self._classifier.sentence_count(text)

    def script_language(self, text: str) -> Optional[str]:
        return self._classifier.script_language(text)


class LanguageDetectionGate:
    def __init__(self) -> None:
        self._gate = _LanguageDetectionGate()

    def evaluate(
        self,
        *,
        intent: str,
        explicit_language_request: Optional[str],
        detected_language: Optional[str],
        current_language: Optional[str],
        confidence: Optional[float],
        meaningful_words: int,
        sentence_count: int,
        is_entity_response: bool = False,
    ) -> LanguageDecision:
        return self._gate.evaluate(
            intent_label=intent,
            is_entity_response=is_entity_response or intent in {UserIntent.ENTITY_RESPONSE, UserIntent.IDENTITY_RESPONSE},
            explicit_language_request=explicit_language_request,
            detected_language=detected_language,
            current_language=current_language,
            confidence=confidence,
            meaningful_words=meaningful_words,
            sentence_count=sentence_count,
        )


class PromptHistoryGuard:
    def __init__(self) -> None:
        self._guard = _RepetitionGuard()

    def evaluate(self, *, prompt_key: str, prompt_text: str) -> RepetitionDecision:
        return self._guard.evaluate(prompt_key=prompt_key, prompt_text=prompt_text)

    def should_rephrase(self, *, prompt_key: str, prompt_text: str) -> bool:
        decision = self.evaluate(prompt_key=prompt_key, prompt_text=prompt_text)
        return decision.action == RepetitionAction.REPHRASE

    def remember(self, *, prompt_key: str, prompt_text: str) -> int:
        return self._guard.remember(prompt_key=prompt_key, prompt_text=prompt_text)


class InterruptionPolicy:
    def __init__(self) -> None:
        self.confusion_count = 0

    def classify(
        self,
        text: str,
        *,
        user_intent: str,
        explicit_language_request: Optional[str] = None,
        hostile: bool = False,
    ) -> str:
        norm = normalize_text(text)
        if hostile or user_intent == VoiceIntent.ABUSE:
            return InterruptionIntent.HOSTILE
        if explicit_language_request:
            return InterruptionIntent.LANGUAGE_PREFERENCE
        if any(pattern in norm for pattern in ("no i said", "actually", "i meant", "wrong", "incorrect", "गलत", "ਮੈਂ ਉਹ ਨਹੀਂ ਕਿਹਾ")):
            return InterruptionIntent.CORRECTION
        if user_intent in {VoiceIntent.CONFUSION, VoiceIntent.AWARENESS_NO} or any(
            pattern in norm
            for pattern in (
                "what",
                "repeat",
                "again",
                "not clear",
                "i didn t tell you",
                "i didnt tell you",
                "समझा नहीं",
                "नहीं पता",
                "ਨਹੀਂ ਪਤਾ",
                "ਸਮਝ ਨਹੀਂ ਆਇਆ",
            )
        ):
            return InterruptionIntent.CONFUSION
        if user_intent in {VoiceIntent.PAYMENT_DONE, VoiceIntent.PAYMENT_NOT_DONE, VoiceIntent.PROMISE_TO_PAY}:
            return InterruptionIntent.PAYMENT_STATUS
        if user_intent == VoiceIntent.QUESTION:
            return InterruptionIntent.QUESTION
        return InterruptionIntent.OTHER

    def observe(self, *, interruption_intent: str, text: str) -> bool:
        norm = normalize_text(text)
        if interruption_intent == InterruptionIntent.CONFUSION or any(
            pattern in norm
            for pattern in (
                "why are you speaking punjabi",
                "punjabi kyun",
                "पंजाबी क्यों",
                "ਪੰਜਾਬੀ ਕਿਉਂ",
            )
        ):
            self.confusion_count += 1
        elif interruption_intent not in {InterruptionIntent.OTHER, InterruptionIntent.QUESTION}:
            self.confusion_count = 0
        return self.confusion_count >= 2

    def reset(self) -> None:
        self.confusion_count = 0


@dataclass(frozen=True)
class UtteranceAnalysis:
    intent: str
    intent_result: IntentResult
    interruption_intent: str
    dialogue_state: str
    language_decision: LanguageDecision
    sentiment: SentimentResult
    entities: ExtractedEntities
    meaningful_words: int
    sentence_count: int
    explicit_language_request: Optional[str] = None
    detected_language: Optional[str] = None
    script_language: Optional[str] = None


class VoiceTurnAnalyzer:
    def __init__(self, *, tz: str = "Asia/Kolkata") -> None:
        self.intent_classifier = UtteranceIntentClassifier(tz=tz)
        self.entity_extractor = EntityExtractor(tz=tz)
        self.sentiment_detector = SentimentDetector()
        self.language_gate = LanguageDetectionGate()

    def analyze(
        self,
        text: str,
        *,
        current_step: Optional[str],
        explicit_language_request: Optional[str],
        detected_language: Optional[str],
        current_language: Optional[str],
        confidence: Optional[float],
        interruption_policy: InterruptionPolicy,
        dialogue_state_manager: DialogueStateManager,
        interrupted: bool,
    ) -> UtteranceAnalysis:
        intent_result = self.intent_classifier.classify_result(
            text,
            current_step=current_step,
            explicit_language_request=explicit_language_request,
        )
        sentiment = self.sentiment_detector.detect(text)
        entities = self.entity_extractor.extract(text, current_step=current_step)
        interruption_intent = interruption_policy.classify(
            text,
            user_intent=intent_result.label,
            explicit_language_request=explicit_language_request,
            hostile=sentiment.level == SentimentLevel.HOSTILE,
        )
        if not interrupted and interruption_intent in {
            InterruptionIntent.PAYMENT_STATUS,
            InterruptionIntent.QUESTION,
        }:
            interruption_intent = InterruptionIntent.OTHER
        language_decision = self.language_gate.evaluate(
            intent=intent_result.label,
            explicit_language_request=explicit_language_request,
            detected_language=detected_language,
            current_language=current_language,
            confidence=confidence,
            meaningful_words=intent_result.meaningful_words,
            sentence_count=intent_result.sentence_count,
            is_entity_response=intent_result.is_entity_response,
        )
        dialogue_state = dialogue_state_manager.update_from_user_intent(
            current_step=current_step,
            intent=intent_result.label,
            payment_made=intent_result.payment_status,
            ptp_date=entities.ptp_date,
        )
        return UtteranceAnalysis(
            intent=intent_result.label if not intent_result.is_entity_response else UserIntent.ENTITY_RESPONSE,
            intent_result=intent_result,
            interruption_intent=interruption_intent,
            dialogue_state=dialogue_state,
            language_decision=language_decision,
            sentiment=sentiment,
            entities=entities,
            meaningful_words=intent_result.meaningful_words,
            sentence_count=intent_result.sentence_count,
            explicit_language_request=explicit_language_request,
            detected_language=detected_language,
            script_language=detect_script_language(text),
        )


__all__ = [
    "BargeInDecision",
    "BargeInHandler",
    "DialogueState",
    "DialogueStateManager",
    "EntityExtractor",
    "ExtractedEntities",
    "IntentResult",
    "InterruptionIntent",
    "InterruptionPolicy",
    "LanguageDecision",
    "LanguageDetectionGate",
    "PromptHistoryGuard",
    "RepetitionAction",
    "RepetitionDecision",
    "SentimentDetector",
    "SentimentLevel",
    "SentimentResult",
    "UserIntent",
    "UtteranceAnalysis",
    "UtteranceIntentClassifier",
    "VoiceIntent",
    "VoiceTurnAnalyzer",
]
