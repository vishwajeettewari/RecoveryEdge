import re
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


def _norm(s: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())
    return " ".join(cleaned.split())


def _is_yes(text: str) -> bool:
    t = _norm(text)
    tokens = [tok for tok in t.split() if tok]
    if not tokens:
        return False
    yes_tokens = {"yes", "y", "yeah", "yep", "ok", "okay", "sure", "haan", "han", "ha", "ji", "jihaan"}
    no_tokens = {"no", "nah", "nope", "nahi", "nahin", "na", "not"}
    if any(tok in no_tokens for tok in tokens):
        return False
    return any(tok in yes_tokens for tok in tokens)


def _is_no(text: str) -> bool:
    t = _norm(text)
    tokens = [tok for tok in t.split() if tok]
    if not tokens:
        return False
    yes_tokens = {"yes", "y", "yeah", "yep", "ok", "okay", "sure", "haan", "han", "ha", "ji", "jihaan"}
    no_tokens = {"no", "n", "nah", "nope", "nahi", "nahin", "na", "not"}
    if any(tok in yes_tokens for tok in tokens):
        return False
    return any(tok in no_tokens for tok in tokens)


_DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b")
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)


@dataclass
class WorkflowState:
    # compliance / gating
    consent: Optional[bool] = None
    consent_asked: bool = False

    # flow confirmations
    identity_confirmed: bool = False
    awareness_confirmed: bool = False

    # action capture
    payment_made: Optional[bool] = None
    ptp_date: Optional[str] = None
    callback_time: Optional[str] = None
    reference_number: Optional[str] = None

    # meta
    disposition: Optional[str] = None
    last_agent_intent: Optional[str] = None  # last question we asked (step id)
    last_asked_step: Optional[str] = None
    last_asked_ts: float = 0.0
    current_step: str = "consent"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorkflowEngine:
    """Deterministic collections workflow engine (demo-grade).

    This engine decides what the *next* required step is and provides simple
    parsing to update state from user utterances.
    """

    STEPS = (
        "consent",
        "confirm_identity",
        "confirm_awareness",
        "ask_payment_made",
        "ask_reference_number",
        "ask_ptp_or_callback",
        "closing",
    )

    def compute_next_step(self, state: WorkflowState) -> str:
        if state.disposition in {"no_consent", "closed"}:
            return "closing"
        if state.consent is not True:
            return "consent"
        if not state.identity_confirmed:
            return "confirm_identity"
        if not state.awareness_confirmed:
            return "confirm_awareness"
        if state.payment_made is None:
            return "ask_payment_made"
        if state.payment_made is True:
            if not state.reference_number:
                return "ask_reference_number"
            return "closing"
        # payment_made is False
        if not state.ptp_date and not state.callback_time:
            return "ask_ptp_or_callback"
        return "closing"

    def update_from_assistant(self, text: str, state: WorkflowState) -> None:
        """Best-effort lock of what the assistant just asked."""
        t = _norm(text)
        if not t:
            return
        step = None
        if "consent" in t or "recorded" in t:
            step = "consent"
            state.consent_asked = True
        elif "speaking with" in t or "confirm your name" in t or "your name" in t:
            step = "confirm_identity"
        elif "aware" in t and ("overdue" in t or "due" in t or "payment" in t):
            step = "confirm_awareness"
        elif "made the payment" in t or "made payment" in t or "paid" in t:
            step = "ask_payment_made"
        elif "utr" in t or "reference" in t or "transaction" in t:
            step = "ask_reference_number"
        elif "when" in t and ("pay" in t or "payment" in t or "callback" in t):
            step = "ask_ptp_or_callback"

        if step:
            state.last_agent_intent = step
            state.last_asked_step = step
            state.last_asked_ts = time.time()

    def update_from_user(
        self,
        user_text: str,
        state: WorkflowState,
        *,
        extracted: Optional[Dict[str, Any]] = None,
        reply_to_step_id: Optional[str] = None,
    ) -> None:
        """Update state from user utterance + already-extracted facts."""
        t = (user_text or "").strip()
        if not t:
            return

        step = reply_to_step_id or state.last_agent_intent or state.current_step

        # Facts extracted elsewhere (preferred, because it is more conservative).
        extracted = extracted or {}
        if extracted.get("ptp_date") and not state.ptp_date:
            state.ptp_date = str(extracted["ptp_date"])
        if extracted.get("reference_number") and not state.reference_number:
            state.reference_number = str(extracted["reference_number"])
        if extracted.get("callback_time") and not state.callback_time:
            state.callback_time = str(extracted["callback_time"])

        # Infer callback time (very light heuristic).
        if not state.callback_time:
            m = _TIME_RE.search(t)
            if m and ("call" in _norm(t) or "callback" in _norm(t) or "later" in _norm(t)):
                hh = m.group(1)
                mm = m.group(2) or "00"
                ap = (m.group(3) or "").lower()
                state.callback_time = f"{hh}:{mm} {ap}".strip()

        # Consent handling (only if pending).
        # Consent handling: if we asked for consent, treat any non-negative reply as consent.
        if step == "consent":
            if _is_no(t):
                state.consent = False
                state.disposition = "no_consent"
            else:
                state.consent = True
        elif state.consent is None:
            if _is_yes(t):
                state.consent = True
            elif _is_no(t):
                state.consent = False
                state.disposition = "no_consent"

        # Identity confirmation
        if step == "confirm_identity" and not state.identity_confirmed:
            if _is_yes(t) or (extracted.get("customer_name") and len(str(extracted.get("customer_name"))) >= 2):
                state.identity_confirmed = True

        # Awareness confirmation (be flexible; any substantive reply counts as answered)
        if step == "confirm_awareness" and not state.awareness_confirmed:
            if _is_yes(t) or _is_no(t):
                state.awareness_confirmed = True
            else:
                keywords = (
                    "aware",
                    "know",
                    "overdue",
                    "due",
                    "payment",
                    "paid",
                    "already",
                    "not paid",
                    "pay",
                    "dispute",
                    "wrong",
                )
                if any(k in _norm(t) for k in keywords):
                    state.awareness_confirmed = True
                elif extracted.get("ptp_date") or extracted.get("reference_number") or extracted.get("callback_time"):
                    state.awareness_confirmed = True
                elif len(_norm(t).split()) >= 2:
                    state.awareness_confirmed = True

        # Payment made (global heuristic + step-specific)
        t_norm = _norm(t)
        tokens = t_norm.split()
        neg_markers = {"not", "no", "nahi", "nahin", "na", "never"}
        pay_markers = {"pay", "paid", "payment", "make", "made"}
        if any(tok in neg_markers for tok in tokens) and any(tok in pay_markers for tok in tokens):
            state.payment_made = False
        elif "didn t" in t_norm and "pay" in t_norm:
            state.payment_made = False
        elif step == "ask_payment_made":
            if _is_yes(t) or "paid" in t_norm or "done" in t_norm or "already paid" in t_norm:
                state.payment_made = True
            elif _is_no(t) or "not paid" in t_norm or "not yet" in t_norm:
                state.payment_made = False

        # PTP/callback capture
        if step == "ask_ptp_or_callback":
            if not state.ptp_date:
                dm = _DATE_RE.search(t)
                if dm:
                    state.ptp_date = dm.group(1)
            # "tomorrow"/"next week" are useful for demo but not deterministic dates; store raw.
            if not state.ptp_date:
                tn = _norm(t)
                if any(x in tn for x in ["tomorrow", "next week", "next monday", "today evening", "salary"]):
                    state.ptp_date = t.strip()

        # Recompute step
        state.current_step = self.compute_next_step(state)
