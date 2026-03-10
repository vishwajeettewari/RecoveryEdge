from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from datetime_utils import parse_date_from_text, parse_time_from_text


class VoiceIntent:
    IDENTITY_RESPONSE = "IDENTITY_RESPONSE"
    AWARENESS_YES = "AWARENESS_YES"
    AWARENESS_NO = "AWARENESS_NO"
    PAYMENT_DONE = "PAYMENT_DONE"
    PAYMENT_NOT_DONE = "PAYMENT_NOT_DONE"
    PROMISE_TO_PAY = "PROMISE_TO_PAY"
    QUESTION = "QUESTION"
    CONFUSION = "CONFUSION"
    ABUSE = "ABUSE"
    LANGUAGE_REQUEST = "LANGUAGE_REQUEST"
    OTHER = "OTHER"


@dataclass(frozen=True)
class IntentResult:
    label: str
    is_entity_response: bool
    payment_status: Optional[bool] = None
    awareness: Optional[bool] = None
    partial_payment: bool = False
    meaningful_words: int = 0
    sentence_count: int = 0
    script_language: Optional[str] = None


def normalize_text(text: str) -> str:
    txt = unicodedata.normalize("NFKC", (text or "")).casefold()
    out = []
    for ch in txt:
        if ch.isspace():
            out.append(" ")
            continue
        cat = unicodedata.category(ch)
        if cat[0] in {"L", "N"} or cat in {"Mn", "Mc", "Me"}:
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def detect_script_language(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = (
        ("pa-IN", r"[\u0a00-\u0a7f]"),
        ("gu-IN", r"[\u0a80-\u0aff]"),
        ("or-IN", r"[\u0b00-\u0b7f]"),
        ("ta-IN", r"[\u0b80-\u0bff]"),
        ("te-IN", r"[\u0c00-\u0c7f]"),
        ("kn-IN", r"[\u0c80-\u0cff]"),
        ("ml-IN", r"[\u0d00-\u0d7f]"),
        ("bn-IN", r"[\u0980-\u09ff]"),
        ("hi-IN", r"[\u0900-\u097f]"),
    )
    for code, pattern in patterns:
        if re.search(pattern, text):
            return code
    return None


class IntentClassifier:
    def __init__(self, *, tz: str = "Asia/Kolkata") -> None:
        self._tz = tz

    def classify(
        self,
        text: str,
        *,
        current_step: Optional[str],
        explicit_language_request: Optional[str] = None,
    ) -> IntentResult:
        raw = (text or "").strip()
        norm = normalize_text(raw)
        meaningful_words = self.meaningful_word_count(raw)
        sentence_count = self.sentence_count(raw)
        script_language = detect_script_language(raw)
        if not norm:
            return IntentResult(
                label=VoiceIntent.OTHER,
                is_entity_response=False,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        if explicit_language_request:
            return IntentResult(
                label=VoiceIntent.LANGUAGE_REQUEST,
                is_entity_response=False,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        if self._is_abuse(norm):
            return IntentResult(
                label=VoiceIntent.ABUSE,
                is_entity_response=False,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        if self._is_confusion(norm):
            return IntentResult(
                label=VoiceIntent.CONFUSION,
                is_entity_response=False,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        if self._is_question(raw, norm):
            return IntentResult(
                label=VoiceIntent.QUESTION,
                is_entity_response=False,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        if self._looks_like_identity_response(raw, norm, current_step=current_step):
            return IntentResult(
                label=VoiceIntent.IDENTITY_RESPONSE,
                is_entity_response=True,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        awareness = self._awareness_value(norm, current_step=current_step)
        if awareness is not None:
            return IntentResult(
                label=VoiceIntent.AWARENESS_YES if awareness else VoiceIntent.AWARENESS_NO,
                is_entity_response=False,
                awareness=awareness,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        payment_status = self._payment_status_value(norm, current_step=current_step)
        if payment_status is not None:
            return IntentResult(
                label=VoiceIntent.PAYMENT_DONE if payment_status else VoiceIntent.PAYMENT_NOT_DONE,
                is_entity_response=False,
                payment_status=payment_status,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        promise = self._looks_like_payment_promise(raw, norm)
        if promise:
            return IntentResult(
                label=VoiceIntent.PROMISE_TO_PAY,
                is_entity_response=False,
                partial_payment=self._looks_like_partial_payment(norm),
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        if self._looks_like_entity_response(raw, norm):
            return IntentResult(
                label=VoiceIntent.OTHER,
                is_entity_response=True,
                meaningful_words=meaningful_words,
                sentence_count=sentence_count,
                script_language=script_language,
            )
        return IntentResult(
            label=VoiceIntent.OTHER,
            is_entity_response=False,
            meaningful_words=meaningful_words,
            sentence_count=sentence_count,
            script_language=script_language,
        )

    def meaningful_word_count(self, text: str) -> int:
        tokens = [tok for tok in normalize_text(text).split() if tok]
        filler = {
            "yes",
            "no",
            "ok",
            "okay",
            "haan",
            "han",
            "nahi",
            "nahin",
            "ji",
            "haanji",
            "what",
            "again",
            "repeat",
        }
        return sum(1 for tok in tokens if tok not in filler and not tok.isdigit())

    def sentence_count(self, text: str) -> int:
        if not (text or "").strip():
            return 0
        parts = [part for part in re.split(r"[.!?।]+|\n+", text) if part.strip()]
        return max(1, len(parts))

    def script_language(self, text: str) -> Optional[str]:
        return detect_script_language(text)

    def _is_question(self, raw: str, norm: str) -> bool:
        if "?" in raw:
            return True
        starters = (
            "what",
            "why",
            "how",
            "when",
            "where",
            "who",
            "can you",
            "could you",
            "kya",
            "kyun",
            "kaise",
            "kab",
            "क्या",
            "क्यों",
            "कैसे",
            "कब",
            "कौन",
            "ਕੀ",
            "ਕਿਉਂ",
            "ਕਦੋਂ",
            "ਕੌਣ",
        )
        return any(norm.startswith(prefix) for prefix in starters)

    def _is_confusion(self, norm: str) -> bool:
        patterns = (
            "what",
            "repeat",
            "again",
            "not clear",
            "didn t understand",
            "didnt understand",
            "i didn t tell you",
            "i didnt tell you",
            "नहीं पता",
            "समझा नहीं",
            "समझ नहीं आया",
            "क्या",
            "ਮੈਨੂੰ ਨਹੀਂ ਪਤਾ",
            "ਨਹੀਂ ਪਤਾ",
            "ਸਮਝ ਨਹੀਂ ਆਇਆ",
            "ਕੀ",
        )
        return any(pattern in norm for pattern in patterns)

    def _is_abuse(self, norm: str) -> bool:
        patterns = (
            "fuck",
            "fucking",
            "fuck off",
            "idiot",
            "shut up",
            "भाड़ में जा",
            "भाड़ में जाइए",
            "चुप रह",
            "गाली",
            "साले",
            "हराम",
            "ਮਾਦਰ",
            "ਭਾੜ ਵਿੱਚ ਜਾ",
            "ਗੱਲ ਨਾ ਕਰ",
        )
        return any(pattern in norm for pattern in patterns)

    def _looks_like_identity_response(self, raw: str, norm: str, *, current_step: Optional[str]) -> bool:
        if any(marker in norm for marker in ("my name is", "mera naam", "ਮੇਰਾ ਨਾਮ", "ਮੇਰਾ ਨਾਂ", "i am", "i m", "this is")):
            return True
        if current_step != "confirm_identity":
            return False
        if self._payment_status_value(norm, current_step=current_step) is not None:
            return False
        if self._looks_like_payment_promise(raw, norm):
            return False
        tokens = [tok for tok in norm.split() if tok]
        if not (1 <= len(tokens) <= 4):
            return False
        disallowed = {
            "payment",
            "paid",
            "pay",
            "hindi",
            "english",
            "punjabi",
            "utr",
            "reference",
            "call",
            "callback",
        }
        return not any(tok in disallowed or any(ch.isdigit() for ch in tok) for tok in tokens)

    def _awareness_value(self, norm: str, *, current_step: Optional[str]) -> Optional[bool]:
        if current_step != "confirm_awareness" and not any(marker in norm for marker in ("aware", "पता", "ਜਾਣਕਾਰੀ", "ਨਹੀਂ ਪਤਾ")):
            return None
        no_markers = (
            "don t know",
            "dont know",
            "didn t know",
            "didnt know",
            "not aware",
            "no idea",
            "नहीं पता",
            "पता नहीं",
            "मुझे नहीं पता",
            "ਨਹੀਂ ਪਤਾ",
            "ਮੈਨੂੰ ਨਹੀਂ ਪਤਾ",
            "ਪਤਾ ਨਹੀਂ",
        )
        yes_markers = (
            "i know",
            "aware",
            "yes i know",
            "हाँ पता है",
            "हां पता है",
            "मुझे पता है",
            "पता है",
            "ਹਾਂ ਪਤਾ ਹੈ",
            "ਮੈਨੂੰ ਪਤਾ ਹੈ",
            "ਪਤਾ ਹੈ",
        )
        if any(marker in norm for marker in no_markers):
            return False
        if any(marker in norm for marker in yes_markers):
            return True
        return None

    def _payment_status_value(self, norm: str, *, current_step: Optional[str]) -> Optional[bool]:
        if current_step not in {"ask_payment_made", "ask_reference_number", "ask_ptp_or_callback"} and not any(
            marker in norm
            for marker in ("payment", "paid", "पेमेंट", "भुगतान", "ਪੇਮੈਂਟ", "ਭੁਗਤਾਨ", "ਬਾਕੀ", "बाकी")
        ):
            return None
        done_markers = (
            "already paid",
            "paid",
            "payment done",
            "कर दिया",
            "हो गया",
            "पेमेंट कर दिया",
            "भुगतान कर दिया",
            "paid it",
            "ਕਰ ਦਿੱਤਾ",
            "ਪੇਮੈਂਟ ਕਰ ਦਿੱਤੀ",
            "ਭੁਗਤਾਨ ਕਰ ਦਿੱਤਾ",
        )
        pending_markers = (
            "not paid",
            "pending",
            "बाकी है",
            "बाकी",
            "नहीं किया",
            "पेमेंट नहीं हुआ",
            "भुगतान नहीं किया",
            "ਬਾਕੀ ਹੈ",
            "ਹਾਲੇ ਬਾਕੀ ਹੈ",
            "ਨਹੀਂ ਕੀਤਾ",
            "ਪੇਮੈਂਟ ਨਹੀਂ ਹੋਈ",
        )
        if any(marker in norm for marker in done_markers):
            return True
        if any(marker in norm for marker in pending_markers):
            return False
        return None

    def _looks_like_payment_promise(self, raw: str, norm: str) -> bool:
        if parse_date_from_text(raw or "", tz=self._tz):
            return True
        if re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", norm):
            return True
        commitment_markers = (
            "tomorrow",
            "next week",
            "salary",
            "will pay",
            "can pay",
            "pay by",
            "कर दूंगा",
            "कर दूँगा",
            "कर दूंगी",
            "कल",
            "अगले",
            "भुगतान कर दूंगा",
            "ਨਿਬਟਾ ਦਿਆਂਗਾ",
            "ਕੱਲ",
            "ਅਗਲੇ ਹਫ਼ਤੇ",
            "ਭੁਗਤਾਨ ਕਰ ਦਿਆਂਗਾ",
            "partial payment",
            "half payment",
            "aadha",
            "आधा",
            "ਥੋੜਾ",
        )
        return any(marker in norm for marker in commitment_markers)

    def _looks_like_partial_payment(self, norm: str) -> bool:
        markers = (
            "partial payment",
            "half payment",
            "some amount",
            "aadha",
            "आधा",
            "थोड़ा",
            "ਥੋੜਾ",
            "ਕੁਝ ਰਕਮ",
        )
        return any(marker in norm for marker in markers)

    def _looks_like_entity_response(self, raw: str, norm: str) -> bool:
        if re.search(r"\b(?:utr|ref(?:erence)?(?: number| no)?)\b", norm):
            return True
        if parse_time_from_text(raw or "", allow_implicit=False):
            return True
        if parse_date_from_text(raw or "", tz=self._tz):
            return True
        tokens = [tok for tok in norm.split() if tok]
        return bool(tokens) and len(tokens) <= 4 and all(any(ch.isdigit() for ch in tok) for tok in tokens)
