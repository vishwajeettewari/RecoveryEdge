import re
import time
import unicodedata
from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Dict, Optional, Tuple

from datetime_utils import (
    parse_date_from_text,
    parse_time_from_text,
    validate_callback_time,
    validate_ptp_date,
)


def _norm(s: str) -> str:
    # Keep native-script letters and combining marks so words like "हाँ" stay intact.
    txt = unicodedata.normalize("NFKC", (s or "")).casefold()
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


def _is_yes(text: str) -> bool:
    t = _norm(text)
    tokens = [tok for tok in t.split() if tok]
    if not tokens:
        return False
    yes_tokens = {
        "yes",
        "y",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "right",
        "correct",
        "affirmative",
        "haan",
        "han",
        "ha",
        "ji",
        "jihaan",
        "हाँ",
        "हां",
        "हाँजी",
        "जीहाँ",
        "हांजी",
        "जी",
        "ஆம்",
        "ஆமாம்",
        "ஆமா",
        "சரி",
        "அமாம்",
        "ಅವును",
        "ಹೌದು",
        "അതെ",
        "হ্যাঁ",
        "হ্যা",
        "હા",
        "ਹਾਂ",
        "ହଁ",
    }
    no_tokens = {
        "no",
        "nah",
        "nope",
        "nahi",
        "nahin",
        "na",
        "नहीं",
        "नहि",
        "ना",
        "मत",
        "இல்லை",
        "வேண்டாம்",
        "வேணாம்",
        "కాదు",
        "లేదు",
        "ಇಲ್ಲ",
        "ಬೇಡ",
        "ഇല്ല",
        "വേണ്ട",
        "না",
        "নয়",
        "નથી",
        "ના",
        "ਨਹੀਂ",
        "ନା",
    }
    if any(tok in no_tokens for tok in tokens):
        return False
    return any(tok in yes_tokens for tok in tokens)


def _is_no(text: str) -> bool:
    t = _norm(text)
    tokens = [tok for tok in t.split() if tok]
    if not tokens:
        return False
    yes_tokens = {
        "yes",
        "y",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "right",
        "correct",
        "affirmative",
        "haan",
        "han",
        "ha",
        "ji",
        "jihaan",
        "हाँ",
        "हां",
        "हाँजी",
        "जीहाँ",
        "ஆம்",
        "ஆமாம்",
        "ஆமா",
        "சரி",
        "அமாம்",
        "అవును",
        "ಹೌದು",
        "അതെ",
        "হ্যাঁ",
        "হ্যা",
        "હા",
        "ਹਾਂ",
        "ହଁ",
    }
    no_tokens = {
        "no",
        "n",
        "nah",
        "nope",
        "nahi",
        "nahin",
        "na",
        "नहीं",
        "नहि",
        "ना",
        "मत",
        "இல்லை",
        "வேண்டாம்",
        "வேணாம்",
        "కాదు",
        "లేదు",
        "ఇಲ್ಲ",
        "ಬೇಡ",
        "ಇಲ್ಲ",
        "ഇല്ല",
        "വേണ്ട",
        "না",
        "নয়",
        "નથી",
        "ના",
        "ਨਹੀਂ",
        "ନା",
    }
    if any(tok in yes_tokens for tok in tokens):
        return False
    return any(tok in no_tokens for tok in tokens)


_DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b")
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_RELATIVE_DAY_PHRASE_RE = re.compile(
    r"\b(?:in|after|within)\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty)\s+day(?:s)?\b"
    r"|\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty)\s+day(?:s)?\s+(?:later|from now)\b"
    r"|\b(?:in|after)\s+\d+\s+din(?:o)?\b"
    r"|\b\d+\s+din(?:o)?(?:\s+(?:mein|me|later))?\b"
    r"|\b(?:today|tomorrow|day after tomorrow|next week|next month|kal|parso)\b"
)


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
    callback_requested: bool = False

    # hardship / difficulty
    hardship_detected: bool = False

    # refusal semantics (payment collection steps)
    refusal_detected: bool = False
    refusal_strength: Optional[str] = None  # "soft" | "hard"
    refusal_reason: Optional[str] = None  # "inability" | "unwilling" | "unknown"
    no_count: int = 0

    # dispute / negotiation
    dispute_raised: bool = False
    dispute_type: Optional[str] = None  # "amount" | "loan" | "already_paid" | "other"
    partial_payment_offered: bool = False
    partial_amount: Optional[str] = None
    document_requested: bool = False
    legal_hold: bool = False
    emi_restructure_requested: bool = False

    # edge-case flags
    dnd_requested: bool = False
    wrong_party: bool = False
    identity_denied: bool = False

    # meta
    disposition: Optional[str] = None
    last_agent_intent: Optional[str] = None  # last question we asked (step id)
    last_asked_step: Optional[str] = None
    last_asked_ts: float = 0.0
    current_step: str = "consent"
    attempts: Dict[str, int] = field(default_factory=dict)
    last_transition_reason: Optional[str] = None

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

    def __init__(
        self,
        *,
        enable_advanced: bool = False,
        max_retries: int = 2,
        tz: str = "Asia/Kolkata",
        ptp_min_days: int = 0,
        ptp_max_days: int = 30,
        callback_hours_start: int = 9,
        callback_hours_end: int = 20,
        now_fn: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._enable_advanced = bool(enable_advanced)
        self._max_retries = max(0, int(max_retries))
        self._tz = tz
        self._ptp_min_days = int(ptp_min_days)
        self._ptp_max_days = int(ptp_max_days)
        self._callback_hours_start = int(callback_hours_start)
        self._callback_hours_end = int(callback_hours_end)
        self._now_fn = now_fn

    def _now(self):
        if self._now_fn:
            return self._now_fn()
        return None

    def _retry_exceeded(self, state: WorkflowState, step: str) -> bool:
        if not self._enable_advanced:
            return False
        count = state.attempts.get(step, 0)
        return count > self._max_retries

    def _classify_payment_negative(self, text: str) -> Optional[Tuple[str, str]]:
        """Classify refusal semantics for payment-oriented steps.

        Returns:
            ("soft"|"hard", "inability"|"unwilling"|"unknown") or None
        """
        t = _norm(text)
        if not t:
            return None

        hard_unwilling = (
            "won t pay",
            "wont pay",
            "will not pay",
            "never",
            "not ever",
            "not in my life",
        )
        hard_inability = (
            "cannot make payment",
            "can t make payment",
            "cant make payment",
            "cannot pay",
            "can t pay",
            "cant pay",
            "unable to pay",
            "not able to pay",
            "no money",
            "no funds",
            "no cash",
            "not possible",
            "won t be able to",
            "wont be able to",
            "will not be able to",
        )
        soft_inability = (
            "not yet",
            "later",
            "can t now",
            "cant now",
            "cannot now",
            "not now",
        )

        if any(p in t for p in hard_unwilling):
            return ("hard", "unwilling")
        if any(p in t for p in hard_inability):
            return ("hard", "inability")
        if any(p in t for p in soft_inability):
            return ("soft", "inability")
        if _is_no(text):
            return ("soft", "unknown")
        return None

    def _is_explicit_unpaid_text(self, t_norm: str) -> bool:
        unpaid_phrases = (
            "not paid",
            "not paid yet",
            "have not paid",
            "haven t paid",
            "did not pay",
            "didn t pay",
            "have not made payment",
            "haven t made payment",
            "have not made it",
            "haven t made it",
            "did not make payment",
            "didn t make payment",
            "payment not done",
            "not done yet",
            "yet to pay",
            "yet to make payment",
            "payment pending",
            "pending payment",
        )
        if any(p in t_norm for p in unpaid_phrases):
            return True

        # Contraction/negation-aware fallback for mixed utterances like:
        # "yes ... I haven't made it" or "no, can't pay now".
        negation_re = re.compile(
            r"\b(?:not|never|cannot|cant|can t|unable|won t|"
            r"haven t|hasn t|hadn t|didn t|don t|doesn t)\b"
        )
        pay_action_re = re.compile(r"\b(?:pay|paid|make|made|done|clear|cleared|settle|settled)\b")
        if negation_re.search(t_norm) and pay_action_re.search(t_norm):
            return True

        # "no" should only imply unpaid when paired with explicit payment actions.
        if re.search(r"\bno\b", t_norm) and pay_action_re.search(t_norm):
            return True
        return False

    def _is_explicit_paid_text(self, t_norm: str) -> bool:
        if not t_norm:
            return False
        paid_phrases = (
            "already paid",
            "i paid",
            "i have paid",
            "payment done",
            "paid it",
            "made payment",
            "made the payment",
            "cleared the payment",
            "payment cleared",
            "settled payment",
        )
        if not any(p in t_norm for p in paid_phrases):
            return False
        # Guard against mixed/contradictory statements.
        return not self._is_explicit_unpaid_text(t_norm)

    def _resolve_callback_time_candidate(self, text: str) -> Optional[str]:
        """Parse callback time from natural speech with business-hours disambiguation."""
        raw = (text or "").lower()
        t_norm = _norm(text)
        # Do not reinterpret date commitments like "in 10 days" as callback clock-time.
        if _RELATIVE_DAY_PHRASE_RE.search(t_norm):
            return None
        # Avoid reading date literals (e.g. 01/02/2026) as callback times unless the
        # user also gives explicit time context.
        if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", raw):
            explicit_time_context = any(
                token in t_norm
                for token in (
                    " am",
                    " pm",
                    " at ",
                    "time",
                    "callback",
                    "call",
                    "between",
                    "around",
                    "by ",
                    ":",
                )
            )
            if not explicit_time_context:
                return None
        parsed = parse_time_from_text(text, allow_implicit=True)
        if not parsed:
            return None

        # If explicit meridiem exists, honor it as-is.
        has_explicit_meridiem = " am" in f" {t_norm}" or " pm" in f" {t_norm}"
        if validate_callback_time(
            parsed,
            start_hour=self._callback_hours_start,
            end_hour=self._callback_hours_end,
        ):
            return parsed

        if has_explicit_meridiem:
            return None

        # For implicit hours in collections calls, interpret 1-8 as PM when needed.
        try:
            hour_s, minute_s = parsed.split(":")
            hour_i = int(hour_s)
            minute_i = int(minute_s)
        except ValueError:
            return None

        if 1 <= hour_i <= 8:
            pm_candidate = f"{hour_i + 12:02d}:{minute_i:02d}"
            if validate_callback_time(
                pm_candidate,
                start_hour=self._callback_hours_start,
                end_hour=self._callback_hours_end,
            ):
                return pm_candidate
        return None

    def compute_next_step(self, state: WorkflowState) -> str:
        if self._enable_advanced:
            if state.dnd_requested:
                state.disposition = "dnd_requested"
                state.last_transition_reason = "dnd_requested"
                return "closing"
            if state.wrong_party or state.identity_denied:
                state.disposition = "wrong_party"
                state.last_transition_reason = "wrong_party"
                return "closing"
            if state.consent is False:
                state.disposition = "consent_refused"
                state.last_transition_reason = "consent_refused"
                return "closing"
            if state.legal_hold:
                state.disposition = "legal_hold"
                state.last_transition_reason = "legal_hold"
                return "closing"

        if state.disposition in {"no_consent", "closed"}:
            return "closing"
        if state.consent is not True:
            return "consent"
        if not state.identity_confirmed:
            if self._retry_exceeded(state, "confirm_identity"):
                state.disposition = "identity_not_confirmed"
                state.last_transition_reason = "retry_exceeded"
                return "closing"
            return "confirm_identity"
        if not state.awareness_confirmed:
            if self._retry_exceeded(state, "confirm_awareness"):
                state.disposition = "awareness_not_confirmed"
                state.last_transition_reason = "retry_exceeded"
                return "closing"
            return "confirm_awareness"
        if state.payment_made is None:
            if self._retry_exceeded(state, "ask_payment_made"):
                state.disposition = "payment_status_unknown"
                state.last_transition_reason = "retry_exceeded"
                return "closing"
            return "ask_payment_made"
        if state.payment_made is True:
            if not state.reference_number:
                if self._retry_exceeded(state, "ask_reference_number"):
                    state.disposition = "paid_ref_pending"
                    state.last_transition_reason = "retry_exceeded"
                    return "closing"
                return "ask_reference_number"
            return "closing"
        # payment_made is False
        if not state.ptp_date and not state.callback_time:
            if self._retry_exceeded(state, "ask_ptp_or_callback"):
                if state.refusal_detected:
                    state.disposition = "refusal_unresolved"
                else:
                    state.disposition = "ptp_unconfirmed"
                state.last_transition_reason = "retry_exceeded"
                return "closing"
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
            now_ts = time.time()
            state.last_agent_intent = step
            state.last_asked_step = step
            state.last_asked_ts = now_ts
            if self._enable_advanced:
                state.attempts[step] = state.attempts.get(step, 0) + 1
                state.last_transition_reason = "asked"

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
        if extracted.get("reference_number") and not state.reference_number:
            state.reference_number = str(extracted["reference_number"])
        if self._enable_advanced:
            if extracted.get("ptp_date") and not state.ptp_date:
                parsed = parse_date_from_text(str(extracted["ptp_date"]), tz=self._tz, now=self._now())
                if parsed and validate_ptp_date(
                    parsed,
                    tz=self._tz,
                    now=self._now(),
                    min_days=self._ptp_min_days,
                    max_days=self._ptp_max_days,
                ):
                    state.ptp_date = parsed
                else:
                    state.last_transition_reason = "invalid_ptp_date"
            if extracted.get("callback_time") and not state.callback_time:
                parsed = parse_time_from_text(str(extracted["callback_time"]))
                if parsed and validate_callback_time(
                    parsed,
                    start_hour=self._callback_hours_start,
                    end_hour=self._callback_hours_end,
                ):
                    state.callback_time = parsed
                else:
                    state.last_transition_reason = "invalid_callback_time"
        else:
            if extracted.get("ptp_date") and not state.ptp_date:
                state.ptp_date = str(extracted["ptp_date"])
            if extracted.get("callback_time") and not state.callback_time:
                state.callback_time = str(extracted["callback_time"])

        t_norm = _norm(t)
        payment_step = step in {"ask_payment_made", "ask_ptp_or_callback"}
        negative_cls = self._classify_payment_negative(t) if payment_step else None
        if payment_step and negative_cls:
            strength, reason = negative_cls
            state.refusal_detected = True
            state.refusal_strength = strength
            state.refusal_reason = reason
            state.no_count += 1

        if self._enable_advanced:
            hardship_phrases = (
                "no money",
                "no funds",
                "no cash",
                "lost job",
                "lost my job",
                "job lost",
                "job loss",
                "fired",
                "salary delayed",
                "salary not",
                "salary issue",
                "hospital",
                "medical",
                "sick",
                "emergency",
            )
            if any(p in t_norm for p in hardship_phrases):
                state.hardship_detected = True
                if step == "ask_ptp_or_callback":
                    state.callback_requested = True
                if not state.last_transition_reason:
                    state.last_transition_reason = "hardship"
            if any(
                phrase in t_norm
                for phrase in (
                    "do not call",
                    "dont call",
                    "don t call",
                    "stop calling",
                    "remove my number",
                    "do not contact",
                    "dont contact",
                    "don t contact",
                    "never call",
                )
            ):
                state.dnd_requested = True
                state.disposition = "dnd_requested"
                state.last_transition_reason = "dnd_requested"
            if any(
                phrase in t_norm
                for phrase in (
                    "wrong number",
                    "wrong person",
                    "not the person",
                    "no such person",
                    "not this person",
                )
            ):
                state.wrong_party = True
                state.identity_denied = True
                state.disposition = "wrong_party"
                state.last_transition_reason = "wrong_party"
            name = extracted.get("customer_name")
            if name:
                name_norm = _norm(str(name))
                if name_norm and f"not {name_norm}" in t_norm:
                    state.wrong_party = True
                    state.identity_denied = True
                    state.disposition = "wrong_party"
                    state.last_transition_reason = "wrong_party"
            if any(
                phrase in t_norm
                for phrase in (
                    "do not consent",
                    "dont consent",
                    "don t consent",
                    "do not record",
                    "dont record",
                    "don t record",
                )
                ):
                    state.consent = False
                    state.disposition = "consent_refused"
                    state.last_transition_reason = "consent_refused"

            # Dispute detection (amount wrong, not my loan, already disputed)
            dispute_phrases = (
                "wrong amount", "amount is wrong", "amount wrong",
                "not my loan", "not my account", "i don t owe",
                "i dont owe", "already disputed", "filed dispute",
                "raise dispute", "raised complaint", "filed complaint",
                "complain", "ombudsman", "banking ombudsman",
                "amount doesn t match", "amount mismatch",
                "galat amount", "galat hai", "mera loan nahi",
                "mera nahi", "yeh mera nahi",
            )
            if any(p in t_norm for p in dispute_phrases):
                state.dispute_raised = True
                if "amount" in t_norm or "galat" in t_norm or "mismatch" in t_norm:
                    state.dispute_type = "amount"
                elif "not my" in t_norm or "mera nahi" in t_norm:
                    state.dispute_type = "loan"
                else:
                    state.dispute_type = "other"
                state.last_transition_reason = "dispute_raised"

            # Legal hold detection
            legal_phrases = (
                "lawyer", "advocate", "legal notice", "court",
                "case filed", "filed case", "ncdrc",
                "consumer forum", "consumer court",
                "legal action", "my lawyer",
                "vakeel", "vakil", "court case",
            )
            if any(p in t_norm for p in legal_phrases):
                state.legal_hold = True
                state.disposition = "legal_hold"
                state.last_transition_reason = "legal_hold"

            # Partial payment offer
            partial_phrases = (
                "pay half", "partial payment", "pay part",
                "can pay some", "pay something", "aadha",
                "thoda", "kuch de sakta", "kuch de sakti",
                "some amount", "half amount",
                "installment", "emi change", "emi kam",
                "reduce emi", "lower emi", "restructure",
            )
            if any(p in t_norm for p in partial_phrases):
                state.partial_payment_offered = True
                if "emi" in t_norm or "restructure" in t_norm or "installment" in t_norm:
                    state.emi_restructure_requested = True
                    state.last_transition_reason = "emi_restructure"
                else:
                    state.last_transition_reason = "partial_payment"
                # Extract partial amount if mentioned
                amt_m = re.search(r'(\d[\d,]*)\b', t_norm)
                if amt_m:
                    state.partial_amount = amt_m.group(1).replace(",", "")

            # Document request detection
            doc_phrases = (
                "send proof", "send document", "send statement",
                "loan statement", "proof of", "show me",
                "send details", "email statement", "sms statement",
                "whatsapp statement", "document bhejo",
                "statement bhejo", "proof bhejo",
            )
            if any(p in t_norm for p in doc_phrases):
                state.document_requested = True
                state.last_transition_reason = "document_requested"

        # Infer callback time (very light heuristic).
        if not self._enable_advanced and not state.callback_time:
            m = _TIME_RE.search(t)
            if m and ("call" in _norm(t) or "callback" in _norm(t) or "later" in _norm(t)):
                hh = m.group(1)
                mm = m.group(2) or "00"
                ap = (m.group(3) or "").lower()
                state.callback_time = f"{hh}:{mm} {ap}".strip()

        # Consent handling (only if pending).
        # Require explicit positive confirmation when consent was asked.
        if step == "consent":
            if _is_yes(t):
                state.consent = True
            elif _is_no(t):
                state.consent = False
                state.disposition = "no_consent"
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
            elif self._enable_advanced and _is_no(t):
                state.identity_denied = True
                state.wrong_party = True
                state.disposition = "wrong_party"
                state.last_transition_reason = "wrong_party"

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
        explicit_unpaid = self._is_explicit_unpaid_text(t_norm)
        explicit_paid = self._is_explicit_paid_text(t_norm)
        if explicit_unpaid:
            state.payment_made = False
        elif explicit_paid:
            state.payment_made = True
        elif step == "ask_payment_made":
            if explicit_unpaid or _is_no(t):
                state.payment_made = False
            elif explicit_paid or _is_yes(t):
                state.payment_made = True
        if step == "ask_payment_made" and negative_cls:
            # Step-bound conflict rule: explicit unpaid/negative in payment status step wins.
            state.payment_made = False

        # PTP/callback capture
        if step == "ask_ptp_or_callback":
            if self._enable_advanced:
                now = self._now()
                invalid_reason = None
                if not state.ptp_date and not state.callback_time:
                    uncertain_phrases = (
                        "not sure",
                        "don t know",
                        "dont know",
                        "do not know",
                        "cannot say",
                        "can t say",
                        "cant say",
                        "not decided",
                        "maybe",
                    )
                    unable_phrases = (
                        "cant pay",
                        "can t pay",
                        "cannot pay",
                        "not able to pay",
                        "cannot make payment",
                        "can t make payment",
                        "cant make payment",
                        "won t be able to",
                        "wont be able to",
                        "will not be able to",
                        "no money",
                        "never",
                        "not possible",
                        "broke",
                    )
                    if any(p in t_norm for p in uncertain_phrases):
                        state.callback_requested = True
                        if state.last_transition_reason not in {"hardship", "needs_callback"}:
                            state.last_transition_reason = "uncertain_commitment"
                    if any(p in t_norm for p in unable_phrases) or negative_cls:
                        state.callback_requested = True
                        if state.last_transition_reason != "hardship":
                            state.last_transition_reason = "needs_callback"
                if not state.ptp_date:
                    date_attempted = False
                    parsed_date = parse_date_from_text(t, tz=self._tz, now=now)
                    if parsed_date:
                        date_attempted = True
                        if validate_ptp_date(
                            parsed_date,
                            tz=self._tz,
                            now=now,
                            min_days=self._ptp_min_days,
                            max_days=self._ptp_max_days,
                        ):
                            state.ptp_date = parsed_date
                        else:
                            invalid_reason = "invalid_ptp_date"
                else:
                    date_attempted = False
                if not state.callback_time and not state.ptp_date and not date_attempted:
                    parsed_time = self._resolve_callback_time_candidate(t)
                    if parsed_time:
                        state.callback_time = parsed_time
                        state.callback_requested = True
                    elif parse_time_from_text(t, allow_implicit=True):
                        invalid_reason = "invalid_callback_time"
                if invalid_reason:
                    state.last_transition_reason = invalid_reason
                elif state.ptp_date or state.callback_time:
                    state.last_transition_reason = None
            else:
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
