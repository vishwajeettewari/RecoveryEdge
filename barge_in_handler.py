from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BargeInDecision:
    should_interrupt: bool
    reason: Optional[str] = None


class BargeInHandler:
    def __init__(self, *, grace_s: float = 0.45, min_speech_frames: int = 5) -> None:
        self._grace_s = max(0.05, float(grace_s))
        self._min_speech_frames = max(1, int(min_speech_frames))

    def should_interrupt_from_vad(
        self,
        *,
        in_silence: bool,
        tts_start_ts: float,
        vad_speech_frames: int,
        last_rms: float,
        vad_threshold: float,
        tts_playing: bool,
        tts_pending: bool,
        now: Optional[float] = None,
    ) -> BargeInDecision:
        current = now if now is not None else time.time()
        if not (tts_playing or tts_pending):
            return BargeInDecision(False)
        if not tts_start_ts or in_silence:
            return BargeInDecision(False)
        if (current - tts_start_ts) < self._grace_s:
            return BargeInDecision(False)
        if vad_speech_frames < self._min_speech_frames:
            return BargeInDecision(False)
        if last_rms < (vad_threshold * 1.2):
            return BargeInDecision(False)
        return BargeInDecision(True, "vad")

    def should_interrupt_from_stt(
        self,
        *,
        text: str,
        tts_start_ts: float,
        tts_playing: bool,
        tts_pending: bool,
        current_llm_text: str,
        last_assistant_text: str,
        current_step: Optional[str],
        now: Optional[float] = None,
    ) -> BargeInDecision:
        current = now if now is not None else time.time()
        if not (tts_playing or tts_pending):
            return BargeInDecision(False)
        if tts_start_ts and (current - tts_start_ts) < self._grace_s:
            return BargeInDecision(False)
        t = (text or "").strip().lower()
        clean = "".join(ch for ch in t if ch.isalnum() or ch.isspace()).strip()
        parts = [part for part in clean.split() if part]
        if len(parts) == 1:
            single = parts[0]
            if single in {"hi", "hello", "hey", "hmm", "hm", "ok", "okay"}:
                return BargeInDecision(False)
            if single in {"yes", "yeah", "yep", "haan", "han", "no", "nah", "nahi"}:
                if current_step in {"consent", "confirm_identity", "confirm_awareness", "confirm_ptp"}:
                    return BargeInDecision(True, "stt_short_binary")
        if len(t) <= 3:
            return BargeInDecision(False)
        norm = " ".join(t.split())
        current_norm = " ".join((current_llm_text or "").lower().split())
        last_norm = " ".join((last_assistant_text or "").lower().split())
        if current_norm and (norm in current_norm or current_norm in norm):
            return BargeInDecision(False)
        if last_norm and (norm in last_norm or last_norm in norm):
            return BargeInDecision(False)
        return BargeInDecision(True, "stt")
