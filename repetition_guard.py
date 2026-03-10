from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from intent_classifier import normalize_text


class RepetitionAction:
    ALLOW = "ALLOW"
    REPHRASE = "REPHRASE"
    MOVE_STATE = "MOVE_STATE"
    TERMINATE = "TERMINATE"


@dataclass(frozen=True)
class RepetitionDecision:
    action: str
    repeat_count: int
    reason: Optional[str] = None


class RepetitionGuard:
    def __init__(self) -> None:
        self._last_prompt_key: Optional[str] = None
        self._last_prompt_text: str = ""
        self._repeat_count: int = 0

    def evaluate(self, *, prompt_key: str, prompt_text: str) -> RepetitionDecision:
        norm = normalize_text(prompt_text)
        if not norm:
            return RepetitionDecision(action=RepetitionAction.ALLOW, repeat_count=0)
        if prompt_key == self._last_prompt_key and norm == self._last_prompt_text:
            next_count = self._repeat_count + 1
            if next_count == 1:
                return RepetitionDecision(
                    action=RepetitionAction.REPHRASE,
                    repeat_count=next_count,
                    reason="same_prompt_repeated_once",
                )
            if next_count == 2:
                return RepetitionDecision(
                    action=RepetitionAction.MOVE_STATE,
                    repeat_count=next_count,
                    reason="same_prompt_repeated_twice",
                )
            return RepetitionDecision(
                action=RepetitionAction.TERMINATE,
                repeat_count=next_count,
                reason="same_prompt_repeated_three_times",
            )
        return RepetitionDecision(action=RepetitionAction.ALLOW, repeat_count=0)

    def remember(self, *, prompt_key: str, prompt_text: str) -> int:
        norm = normalize_text(prompt_text)
        if prompt_key == self._last_prompt_key and norm == self._last_prompt_text:
            self._repeat_count += 1
        else:
            self._repeat_count = 0
        self._last_prompt_key = prompt_key
        self._last_prompt_text = norm
        return self._repeat_count
