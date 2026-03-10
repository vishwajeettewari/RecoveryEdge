from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class DialogueState:
    GREETING = "GREETING"
    IDENTITY_CONFIRM = "IDENTITY_CONFIRM"
    PAYMENT_AWARENESS = "PAYMENT_AWARENESS"
    PAYMENT_STATUS = "PAYMENT_STATUS"
    PTP_CAPTURE = "PTP_CAPTURE"
    PAYMENT_ASSIST = "PAYMENT_ASSIST"
    CLOSURE = "CLOSURE"


@dataclass(frozen=True)
class DialogueSnapshot:
    current_state: str
    last_valid_state: str


class DialogueStateManager:
    def __init__(self) -> None:
        self.current_state = DialogueState.GREETING
        self.last_valid_state = DialogueState.GREETING

    def sync_from_step(
        self,
        step: Optional[str],
        *,
        payment_made: Optional[bool] = None,
        ptp_date: Optional[str] = None,
        reference_number: Optional[str] = None,
        payment_assist_offered: bool = False,
    ) -> str:
        state = self.map_step_to_state(
            step,
            payment_made=payment_made,
            ptp_date=ptp_date,
            reference_number=reference_number,
            payment_assist_offered=payment_assist_offered,
        )
        self.current_state = state
        if state != DialogueState.CLOSURE:
            self.last_valid_state = state
        return state

    def update_from_user_intent(
        self,
        *,
        current_step: Optional[str],
        intent: str,
        payment_made: Optional[bool] = None,
        ptp_date: Optional[str] = None,
        payment_assist_offered: bool = False,
    ) -> str:
        state = self.map_step_to_state(
            current_step,
            payment_made=payment_made,
            ptp_date=ptp_date,
            payment_assist_offered=payment_assist_offered,
        )
        if intent == "IDENTITY_RESPONSE":
            state = DialogueState.IDENTITY_CONFIRM
        elif intent in {"AWARENESS_YES", "AWARENESS_NO"}:
            state = DialogueState.PAYMENT_AWARENESS
        elif intent in {"PAYMENT_DONE", "PAYMENT_NOT_DONE"}:
            state = DialogueState.PAYMENT_STATUS
        elif intent == "PROMISE_TO_PAY":
            state = DialogueState.PTP_CAPTURE
        elif intent == "LANGUAGE_REQUEST":
            # Keep the current business state while the language side flow runs.
            state = state
        elif state == DialogueState.CLOSURE and intent in {"QUESTION", "CONFUSION"}:
            state = self.last_valid_state
        self.current_state = state
        if state not in {DialogueState.CLOSURE, DialogueState.PAYMENT_ASSIST}:
            self.last_valid_state = state
        return state

    def restore_last_valid_state(self) -> str:
        self.current_state = self.last_valid_state
        return self.current_state

    def snapshot(self) -> DialogueSnapshot:
        return DialogueSnapshot(
            current_state=self.current_state,
            last_valid_state=self.last_valid_state,
        )

    @staticmethod
    def map_step_to_state(
        step: Optional[str],
        *,
        payment_made: Optional[bool] = None,
        ptp_date: Optional[str] = None,
        reference_number: Optional[str] = None,
        payment_assist_offered: bool = False,
    ) -> str:
        step_name = (step or "").strip()
        if step_name in {"consent", "greeting"}:
            return DialogueState.GREETING
        if step_name == "confirm_identity":
            return DialogueState.IDENTITY_CONFIRM
        if step_name == "confirm_awareness":
            return DialogueState.PAYMENT_AWARENESS
        if step_name in {"ask_payment_made", "ask_reference_number"}:
            return DialogueState.PAYMENT_STATUS
        if step_name in {"ask_ptp_or_callback", "confirm_ptp"} or payment_made is False:
            return DialogueState.PTP_CAPTURE
        if step_name == "closing":
            if ptp_date and not payment_assist_offered:
                return DialogueState.PAYMENT_ASSIST
            if payment_made and not reference_number:
                return DialogueState.PAYMENT_STATUS
            return DialogueState.CLOSURE
        return DialogueState.PAYMENT_STATUS

    @staticmethod
    def state_to_step(
        state: str,
        *,
        payment_made: Optional[bool] = None,
        has_reference: bool = False,
        has_ptp: bool = False,
        payment_assist_offered: bool = False,
    ) -> str:
        if state == DialogueState.GREETING:
            return "consent"
        if state == DialogueState.IDENTITY_CONFIRM:
            return "confirm_identity"
        if state == DialogueState.PAYMENT_AWARENESS:
            return "confirm_awareness"
        if state == DialogueState.PAYMENT_STATUS:
            if payment_made is True:
                return "ask_reference_number" if not has_reference else "closing"
            return "ask_payment_made"
        if state == DialogueState.PTP_CAPTURE:
            return "confirm_ptp" if has_ptp else "ask_ptp_or_callback"
        if state == DialogueState.PAYMENT_ASSIST:
            return "closing"
        return "closing"
