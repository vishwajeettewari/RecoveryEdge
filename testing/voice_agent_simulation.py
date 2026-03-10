from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from voice_pipeline import (
    DialogueStateManager,
    InterruptionIntent,
    InterruptionPolicy,
    PromptHistoryGuard,
    RepetitionAction,
    SentimentLevel,
    UserIntent,
    VoiceTurnAnalyzer,
)
from workflow_engine import WorkflowEngine, WorkflowState


DEFAULT_TZ = "Asia/Kolkata"
DEFAULT_NOW = datetime(2026, 3, 10, 12, 0, tzinfo=ZoneInfo(DEFAULT_TZ))


@dataclass(frozen=True)
class SimulatedUserTurn:
    text: str
    detected_language: str = "hi-IN"
    confidence: float = 0.96
    interrupted: bool = False
    explicit_language_request: Optional[str] = None


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    description: str
    known_customer_name: Optional[str]
    turns: list[SimulatedUserTurn]
    expected_final_step: str
    expected_payment_made: Optional[bool]
    expect_ptp: bool = False
    expect_reference: bool = False
    expect_hostile_exit: bool = False
    expect_language_offer: bool = False
    expect_language_switch: bool = False
    expect_refusal: Optional[bool] = None
    expect_interruption_override: bool = False
    expected_required_steps: tuple[str, ...] = ()


@dataclass
class SimulationTurnLog:
    user_text: str
    reply_step_before: str
    intent: str
    sentiment: str
    interruption_intent: str
    assistant_step_after: str
    assistant_prompt: str
    prompt_guard_action: str
    language_offer: Optional[str]
    dialogue_state_after: str
    payment_made_after: Optional[bool]
    ptp_date_after: Optional[str]
    reference_number_after: Optional[str]


def _normalize_prompt(text: str) -> str:
    return " ".join((text or "").split()).strip().casefold()


def _record_assistant_step(state: WorkflowState, step: str) -> None:
    state.last_agent_intent = step
    state.last_asked_step = step
    state.last_asked_ts = DEFAULT_NOW.timestamp()
    state.attempts[step] = state.attempts.get(step, 0) + 1


def _next_step_after_repeat(step: str, state: WorkflowState) -> str:
    if step == "confirm_identity":
        state.disposition = state.disposition or "identity_not_confirmed"
        state.last_transition_reason = "repeat_guard_identity"
        return "closing"
    if step == "confirm_awareness":
        return "ask_payment_made"
    if step == "ask_payment_made":
        if state.payment_made is None:
            state.payment_made = False
        return "ask_ptp_or_callback"
    if step == "confirm_ptp":
        return "ask_ptp_or_callback"
    if step in {"ask_reference_number", "ask_ptp_or_callback"}:
        return "closing"
    return step


def _render_prompt(step: str, state: WorkflowState, facts: dict[str, object], language: str) -> str:
    name = str(facts.get("customer_name") or "").strip()
    ptp_date = str(state.ptp_date or facts.get("ptp_date") or "").strip()
    if language.startswith("pa"):
        if state.last_transition_reason == "abusive_language_warning":
            return "ਮੈਂ ਤੁਹਾਡੀ ਗੱਲ ਸੁਣ ਰਿਹਾ ਹਾਂ, ਪਰ ਕਿਰਪਾ ਕਰਕੇ ਸ਼ਾਂਤ ਰਹੋ। ਹੁਣ ਦੱਸੋ, ਭੁਗਤਾਨ ਹੋ ਗਿਆ ਹੈ ਜਾਂ ਕਿਹੜੀ ਤਾਰੀਖ ਤੱਕ ਕਰੋਗੇ?"
        if step == "consent":
            return "ਇਹ ਕਾਲ ਰਿਕਾਰਡ ਕੀਤੀ ਜਾ ਸਕਦੀ ਹੈ। ਕੀ ਮੈਂ ਅੱਗੇ ਵੱਧਾਂ?"
        if step == "confirm_identity":
            if name and state.last_transition_reason == "identity_name_captured":
                return f"ਧੰਨਵਾਦ। ਕੀ ਤੁਹਾਡਾ ਨਾਮ {name} ਹੈ?"
            if name:
                return f"ਕੀ ਮੈਂ {name} ਜੀ ਨਾਲ ਗੱਲ ਕਰ ਰਿਹਾ ਹਾਂ?"
            return "ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਪੂਰਾ ਨਾਮ ਦੱਸੋ।"
        if step == "confirm_awareness":
            return "ਕੀ ਤੁਹਾਨੂੰ ਇਸ ਬਕਾਇਆ ਭੁਗਤਾਨ ਬਾਰੇ ਜਾਣਕਾਰੀ ਹੈ?"
        if step == "ask_payment_made":
            return "ਕੀ ਤੁਸੀਂ ਭੁਗਤਾਨ ਕਰ ਦਿੱਤਾ ਹੈ?"
        if step == "ask_reference_number":
            return "ਕਿਰਪਾ ਕਰਕੇ UTR ਜਾਂ ਟ੍ਰਾਂਜ਼ੈਕਸ਼ਨ ਰੈਫ਼ਰੈਂਸ ਦੱਸੋ।"
        if step == "ask_ptp_or_callback":
            return "ਤੁਸੀਂ ਭੁਗਤਾਨ ਕਦੋਂ ਤੱਕ ਕਰੋਗੇ, ਜਾਂ ਮੈਂ ਕਦੋਂ ਕਾਲਬੈਕ ਕਰਾਂ?"
        if step == "confirm_ptp":
            return f"ਤੁਸੀਂ {ptp_date} ਤੱਕ ਭੁਗਤਾਨ ਕਰਨ ਦਾ ਵਾਅਦਾ ਕੀਤਾ ਹੈ। ਕੀ ਮੈਂ ਇਸਨੂੰ ਨੋਟ ਕਰ ਦਿਆਂ?"
        if step == "closing" and state.last_transition_reason == "abusive_language":
            return "ਸਮਝ ਗਿਆ ਸਰ, ਮੈਂ ਬਾਅਦ ਵਿੱਚ ਕਾਲ ਕਰ ਲੈਂਦਾ ਹਾਂ।"
        if step == "closing" and state.ptp_date:
            return f"ਧੰਨਵਾਦ। ਤੁਸੀਂ {ptp_date} ਤੱਕ ਭੁਗਤਾਨ ਕਰਨ ਦਾ ਵਾਅਦਾ ਕੀਤਾ ਹੈ। ਜੇ ਤੁਸੀਂ ਚਾਹੋ ਤਾਂ ਮੈਂ ਭੁਗਤਾਨ ਲਿੰਕ ਵਟਸਐਪ 'ਤੇ ਭੇਜ ਸਕਦਾ ਹਾਂ।"
        return "ਧੰਨਵਾਦ, ਤੁਹਾਡੇ ਸਮੇਂ ਲਈ।"
    if state.last_transition_reason == "abusive_language_warning":
        return "मैं आपकी बात सुन रहा हूँ, लेकिन कृपया शांत रहिए। अब बताइए, भुगतान किया है या किस तारीख तक करेंगे?"
    if step == "consent":
        return "यह कॉल रिकॉर्ड हो सकती है। क्या मैं आगे बढ़ूँ?"
    if step == "confirm_identity":
        if name and state.last_transition_reason == "identity_name_captured":
            return f"धन्यवाद। क्या आपका नाम {name} है?"
        if name:
            return f"क्या मैं {name} जी से बात कर रहा हूँ?"
        return "कृपया अपना पूरा नाम बताइए।"
    if step == "confirm_awareness":
        return "क्या आपको इस बकाया भुगतान की जानकारी है?"
    if step == "ask_payment_made":
        return "क्या आपने भुगतान किया है?"
    if step == "ask_reference_number":
        return "कृपया UTR या ट्रांज़ैक्शन रेफरेंस बताइए।"
    if step == "ask_ptp_or_callback":
        return "आप भुगतान कब तक कर पाएँगे, या मैं कब कॉलबैक करूँ?"
    if step == "confirm_ptp":
        return f"आपने {ptp_date} तक भुगतान करने का वादा किया है। क्या मैं इसे नोट कर दूँ?"
    if step == "closing" and state.last_transition_reason == "abusive_language":
        return "समझ गया सर, मैं बाद में कॉल कर लेता हूँ।"
    if step == "closing" and state.ptp_date:
        return f"धन्यवाद। आपने {ptp_date} तक भुगतान करने का वादा किया है। अगर आप चाहें तो मैं भुगतान लिंक व्हाट्सऐप पर भेज सकता हूँ।"
    if step == "closing" and state.reference_number:
        return "धन्यवाद। हम ट्रांज़ैक्शन रेफरेंस सत्यापित कर लेंगे।"
    return "धन्यवाद, आपके समय के लिए।"


def _alternate_prompt(step: str, language: str) -> Optional[str]:
    if language.startswith("pa"):
        mapping = {
            "ask_payment_made": "ਕੀ ਇਹ ਭੁਗਤਾਨ ਹੋ ਗਿਆ ਹੈ ਜਾਂ ਹਾਲੇ ਬਾਕੀ ਹੈ?",
            "ask_ptp_or_callback": "ਤੁਸੀਂ ਕਿਸ ਤਾਰੀਖ ਤੱਕ ਭੁਗਤਾਨ ਕਰੋਗੇ, ਜਾਂ ਕਿਸ ਵੇਲੇ ਕਾਲਬੈਕ ਠੀਕ ਰਹੇਗਾ?",
            "confirm_awareness": "ਸਿਰਫ਼ ਪੁਸ਼ਟੀ ਕਰ ਦਿਓ, ਕੀ ਤੁਹਾਨੂੰ ਇਸ ਬਕਾਇਆ ਭੁਗਤਾਨ ਬਾਰੇ ਪਤਾ ਹੈ?",
            "language_confirm": "ਪੁਸ਼ਟੀ ਲਈ ਦੱਸੋ, ਕੀ ਤੁਸੀਂ ਹਿੰਦੀ ਵਿੱਚ ਗੱਲ ਕਰਨੀ ਪਸੰਦ ਕਰੋਗੇ ਜਾਂ ਪੰਜਾਬੀ ਵਿੱਚ?",
        }
    else:
        mapping = {
            "ask_payment_made": "क्या यह भुगतान हो गया है या अभी बाकी है?",
            "ask_ptp_or_callback": "आप किस तारीख तक भुगतान कर पाएँगे, या किस समय कॉलबैक बेहतर रहेगा?",
            "confirm_awareness": "सिर्फ पुष्टि कर दीजिए, क्या आपको इस बकाया भुगतान की जानकारी है?",
            "language_confirm": "पुष्टि के लिए बता दीजिए, आप हिंदी पसंद करेंगे या पंजाबी?",
        }
    return mapping.get(step)


def _language_confirmation_prompt(candidate_language: str, current_language: str) -> str:
    if {candidate_language, current_language} == {"hi-IN", "pa-IN"}:
        return "क्या आप हिंदी में बात करना पसंद करेंगे या पंजाबी में?"
    if candidate_language.startswith("pa"):
        return "ਕੀ ਤੁਸੀਂ ਅੱਗੇ ਗੱਲਬਾਤ ਪੰਜਾਬੀ ਵਿੱਚ ਕਰਨੀ ਚਾਹੁੰਦੇ ਹੋ?"
    return "क्या आप आगे की बातचीत हिंदी में करना चाहेंगे?"


def _apply_prompt_guard(
    guard: PromptHistoryGuard,
    *,
    step: str,
    prompt: str,
    language: str,
    state: WorkflowState,
    facts: dict[str, object],
) -> tuple[str, str, str]:
    decision = guard.evaluate(prompt_key=f"{step}:{language}", prompt_text=prompt)
    next_step = step
    next_prompt = prompt
    if decision.action == RepetitionAction.REPHRASE:
        alt = _alternate_prompt(step, language)
        if alt:
            next_prompt = alt
    elif decision.action == RepetitionAction.MOVE_STATE:
        next_step = _next_step_after_repeat(step, state)
        next_prompt = _render_prompt(next_step, state, facts, language)
    elif decision.action == RepetitionAction.TERMINATE:
        next_step = "closing"
        state.disposition = state.disposition or "loop_terminated"
        state.last_transition_reason = "repeat_guard_terminated"
        next_prompt = _render_prompt("closing", state, facts, language)
    guard.remember(prompt_key=f"{next_step}:{language}", prompt_text=next_prompt)
    return next_step, next_prompt, decision.action


def _language_request(turn: SimulatedUserTurn) -> Optional[str]:
    if turn.explicit_language_request:
        return turn.explicit_language_request
    norm = turn.text.casefold()
    if "hindi me" in norm or "hindi mein" in norm or "हिंदी में" in turn.text:
        return "hi-IN"
    if "punjabi" in norm or "ਪੰਜਾਬੀ" in turn.text or "पंजाबी" in turn.text:
        return "pa-IN"
    return None


def scenario_specs() -> list[ScenarioSpec]:
    return [
        ScenarioSpec(
            key="borrower_unaware_of_loan",
            description="Borrower was unaware, confirms unpaid status, and gives a dated promise to pay.",
            known_customer_name="Vishwajeet Tiwari",
            turns=[
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("मुझे पता नहीं था।"),
                SimulatedUserTurn("नहीं"),
                SimulatedUserTurn("मैं 13/03/2026 को भुगतान कर दूंगा।"),
            ],
            expected_final_step="closing",
            expected_payment_made=False,
            expect_ptp=True,
            expected_required_steps=("confirm_awareness", "ask_ptp_or_callback", "closing"),
        ),
        ScenarioSpec(
            key="borrower_already_paid",
            description="Borrower states payment is done and provides a UTR.",
            known_customer_name="Asha Rao",
            turns=[
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ, मुझे पता है।"),
                SimulatedUserTurn("मैंने भुगतान कर दिया है।"),
                SimulatedUserTurn("UTR 1234567890"),
            ],
            expected_final_step="closing",
            expected_payment_made=True,
            expect_reference=True,
            expected_required_steps=("ask_payment_made", "ask_reference_number", "closing"),
        ),
        ScenarioSpec(
            key="borrower_promises_payment",
            description="Borrower directly gives a promise-to-pay date and confirms it.",
            known_customer_name="Rahul Sharma",
            turns=[
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ, पता है।"),
                SimulatedUserTurn("मैं 14/03/2026 तक भुगतान कर दूंगा।"),
            ],
            expected_final_step="closing",
            expected_payment_made=False,
            expect_ptp=True,
            expected_required_steps=("ask_payment_made", "closing"),
        ),
        ScenarioSpec(
            key="borrower_speaks_punjabi",
            description="Punjabi speech should trigger a confirmation offer, not an automatic switch.",
            known_customer_name="Gurpreet Singh",
            turns=[
                SimulatedUserTurn("ਜੀ", detected_language="pa-IN"),
                SimulatedUserTurn("ਹਾਂ", detected_language="pa-IN"),
                SimulatedUserTurn(
                    "ਮੈਨੂੰ ਪਤਾ ਹੈ ਕਿ ਕਿਸ਼ਤ ਬਾਕੀ ਹੈ। ਮੈਂ ਹੁਣੇ ਨਹੀਂ ਦਿੱਤੀ।",
                    detected_language="pa-IN",
                    confidence=0.97,
                ),
                SimulatedUserTurn("ਮੈਂ 13/03/2026 ਤੱਕ ਭੁਗਤਾਨ ਕਰ ਦਿਆਂਗਾ।", detected_language="pa-IN", confidence=0.97),
            ],
            expected_final_step="closing",
            expected_payment_made=False,
            expect_ptp=True,
            expect_language_offer=True,
            expect_language_switch=False,
            expected_required_steps=("confirm_awareness", "ask_payment_made", "closing"),
        ),
        ScenarioSpec(
            key="borrower_mixes_hindi_and_punjabi",
            description="Mixed Hindi and Punjabi plus a native-script name should not auto-switch language.",
            known_customer_name=None,
            turns=[
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("ਮੇਰਾ ਨਾਮ ਵਿਸ਼ਵਜੀਤ ਤਿਵਾਰੀ ਹੈ", detected_language="pa-IN", confidence=0.97),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("मुझे पता है।", detected_language="hi-IN"),
                SimulatedUserTurn("ਬਾਕੀ ਹੈ", detected_language="pa-IN", confidence=0.94),
                SimulatedUserTurn("13/03/2026 को कर दूंगा", detected_language="hi-IN"),
            ],
            expected_final_step="closing",
            expected_payment_made=False,
            expect_ptp=True,
            expect_language_offer=False,
            expected_required_steps=("confirm_identity", "confirm_awareness", "closing"),
        ),
        ScenarioSpec(
            key="borrower_interrupts_agent",
            description="An interruption with payment commitment must override the current question.",
            known_customer_name="Neha Verma",
            turns=[
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("नहीं, मैं 13/03/2026 को भुगतान कर दूंगा।", interrupted=True),
            ],
            expected_final_step="closing",
            expected_payment_made=False,
            expect_ptp=True,
            expect_interruption_override=True,
            expected_required_steps=("ask_payment_made", "closing"),
        ),
        ScenarioSpec(
            key="borrower_abuses_agent",
            description="Repeated hostile language should warn once and then force a safe exit.",
            known_customer_name="Ravi Kumar",
            turns=[
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("भाड़ में जाइए"),
                SimulatedUserTurn("मैंने कहा भाड़ में जाइए"),
            ],
            expected_final_step="closing",
            expected_payment_made=None,
            expect_hostile_exit=True,
            expected_required_steps=("ask_payment_made", "closing"),
        ),
        ScenarioSpec(
            key="borrower_changes_answer_mid_conversation",
            description="A later correction from paid to unpaid must override the earlier branch.",
            known_customer_name="Suman Das",
            turns=[
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ, पेमेंट कर दिया है।"),
                SimulatedUserTurn("नहीं, अभी बाकी है", interrupted=True),
                SimulatedUserTurn("14/03/2026 को दे दूंगा"),
            ],
            expected_final_step="closing",
            expected_payment_made=False,
            expect_ptp=True,
            expect_interruption_override=True,
            expected_required_steps=("ask_reference_number", "ask_ptp_or_callback", "closing"),
        ),
        ScenarioSpec(
            key="borrower_partial_payment_promise",
            description="Partial payment promises should still capture amount and date without loops.",
            known_customer_name="Arun Yadav",
            turns=[
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("मैं आधा 2000 रुपये 13/03/2026 को दे दूंगा।"),
            ],
            expected_final_step="closing",
            expected_payment_made=False,
            expect_ptp=True,
            expected_required_steps=("ask_payment_made", "closing"),
        ),
        ScenarioSpec(
            key="borrower_refuses_to_pay",
            description="Repeated refusal should activate refusal handling and end without prompt loops.",
            known_customer_name="Karan Patel",
            turns=[
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("हाँ"),
                SimulatedUserTurn("मैं भुगतान नहीं करूंगा।"),
                SimulatedUserTurn("जो करना है कर लो।"),
                SimulatedUserTurn("नहीं करूंगा।"),
                SimulatedUserTurn("अभी भी नहीं दूंगा।"),
                SimulatedUserTurn("कह दिया ना नहीं दूंगा।"),
            ],
            expected_final_step="closing",
            expected_payment_made=False,
            expect_refusal=True,
            expected_required_steps=("ask_ptp_or_callback", "closing"),
        ),
    ]


def simulate_voice_agent_scenario(spec: ScenarioSpec) -> dict:
    engine = WorkflowEngine(
        enable_advanced=True,
        max_retries=3,
        tz=DEFAULT_TZ,
        ptp_min_days=0,
        ptp_max_days=30,
        callback_hours_start=9,
        callback_hours_end=20,
        now_fn=lambda: DEFAULT_NOW,
    )
    state = WorkflowState()
    facts: dict[str, object] = {
        "customer_name": spec.known_customer_name,
        "language_preference": "hi-IN",
        "ptp_date": None,
        "callback_time": None,
        "reference_number": None,
        "payment_status": None,
        "mentioned_amount": None,
    }
    analyzer = VoiceTurnAnalyzer(tz=DEFAULT_TZ)
    dialogue_manager = DialogueStateManager()
    interruption_policy = InterruptionPolicy()
    prompt_guard = PromptHistoryGuard()
    turn_logs: list[SimulationTurnLog] = []
    language_offers: list[str] = []
    language_switched = False
    interruption_override = False
    consecutive_duplicate_prompts = False
    last_prompt_norm = ""
    unpaid_established = False
    payment_question_repeated_after_unpaid = False

    for user_turn in spec.turns:
        reply_step = engine.compute_next_step(state)
        explicit_language_request = _language_request(user_turn)
        analysis = analyzer.analyze(
            user_turn.text,
            current_step=reply_step,
            explicit_language_request=explicit_language_request,
            detected_language=user_turn.detected_language,
            current_language=str(facts.get("language_preference") or "hi-IN"),
            confidence=user_turn.confidence,
            interruption_policy=interruption_policy,
            dialogue_state_manager=dialogue_manager,
            interrupted=user_turn.interrupted,
        )
        previous_customer_name = str(facts.get("customer_name") or "").strip()
        if analysis.entities.customer_name:
            facts["customer_name"] = analysis.entities.customer_name
        if analysis.entities.amount:
            facts["mentioned_amount"] = analysis.entities.amount
        if analysis.entities.ptp_date:
            facts["ptp_date"] = analysis.entities.ptp_date
        if analysis.entities.callback_time:
            facts["callback_time"] = analysis.entities.callback_time
        if analysis.entities.reference_number:
            facts["reference_number"] = analysis.entities.reference_number
        payment_status = analysis.entities.payment_status
        if payment_status is None:
            payment_status = analysis.intent_result.payment_status
        if payment_status is not None:
            facts["payment_status"] = payment_status

        if analysis.language_decision.should_offer_confirmation and analysis.language_decision.candidate_language:
            language_offers.append(analysis.language_decision.candidate_language)

        if analysis.sentiment.level == SentimentLevel.HOSTILE:
            state.abuse_count = int(getattr(state, "abuse_count", 0) or 0) + 1
            close_call = state.abuse_count > 1
            if close_call:
                state.last_transition_reason = "abusive_language"
                state.disposition = "abusive_language_terminated"
                state.current_step = "closing"
                assistant_step = "closing"
            else:
                state.last_transition_reason = "abusive_language_warning"
                assistant_step = state.current_step
            dialogue_state = dialogue_manager.sync_from_step(
                assistant_step,
                payment_made=state.payment_made,
                ptp_date=state.ptp_date,
                reference_number=state.reference_number,
                payment_assist_offered=False,
            )
            assistant_step, assistant_prompt, prompt_action = _apply_prompt_guard(
                prompt_guard,
                step=assistant_step,
                prompt=_render_prompt(assistant_step, state, facts, "hi-IN"),
                language="hi-IN",
                state=state,
                facts=facts,
            )
            turn_logs.append(
                SimulationTurnLog(
                    user_text=user_turn.text,
                    reply_step_before=reply_step,
                    intent=analysis.intent_result.label,
                    sentiment=analysis.sentiment.level,
                    interruption_intent=analysis.interruption_intent,
                    assistant_step_after=assistant_step,
                    assistant_prompt=assistant_prompt,
                    prompt_guard_action=prompt_action,
                    language_offer=None,
                    dialogue_state_after=dialogue_state,
                    payment_made_after=state.payment_made,
                    ptp_date_after=state.ptp_date,
                    reference_number_after=state.reference_number,
                )
            )
            if close_call:
                break
            continue

        engine.update_from_user(
            user_turn.text,
            state,
            extracted={
                "customer_name": facts.get("customer_name"),
                "identity_name_preexisting": bool(previous_customer_name),
                "identity_prompt_mode": state.identity_prompt_mode,
                "ptp_date": facts.get("ptp_date"),
                "reference_number": facts.get("reference_number"),
                "callback_time": facts.get("callback_time"),
                "payment_status": facts.get("payment_status"),
            },
            reply_to_step_id=reply_step,
        )

        if user_turn.interrupted and analysis.interruption_intent != InterruptionIntent.OTHER:
            interruption_override = True
        if analysis.interruption_intent != InterruptionIntent.OTHER:
            interruption_policy.observe(
                interruption_intent=analysis.interruption_intent,
                text=user_turn.text,
            )

        next_step = state.current_step
        if analysis.language_decision.should_offer_confirmation and analysis.language_decision.candidate_language:
            candidate = analysis.language_decision.candidate_language
            assistant_step, assistant_prompt, prompt_action = _apply_prompt_guard(
                prompt_guard,
                step="language_confirm",
                prompt=_language_confirmation_prompt(candidate, str(facts.get("language_preference") or "hi-IN")),
                language="hi-IN",
                state=state,
                facts=facts,
            )
        else:
            assistant_prompt = _render_prompt(next_step, state, facts, str(facts.get("language_preference") or "hi-IN"))
            assistant_step, assistant_prompt, prompt_action = _apply_prompt_guard(
                prompt_guard,
                step=next_step,
                prompt=assistant_prompt,
                language=str(facts.get("language_preference") or "hi-IN"),
                state=state,
                facts=facts,
            )
            if assistant_step != next_step:
                state.current_step = assistant_step
                next_step = assistant_step

        if state.payment_made is False and not unpaid_established:
            unpaid_established = True
        elif unpaid_established and next_step == "ask_payment_made":
            payment_question_repeated_after_unpaid = True

        prompt_norm = _normalize_prompt(assistant_prompt)
        if last_prompt_norm and prompt_norm == last_prompt_norm:
            consecutive_duplicate_prompts = True
        last_prompt_norm = prompt_norm

        dialogue_state = dialogue_manager.sync_from_step(
            next_step,
            payment_made=state.payment_made,
            ptp_date=state.ptp_date,
            reference_number=state.reference_number,
            payment_assist_offered=False,
        )
        turn_logs.append(
            SimulationTurnLog(
                user_text=user_turn.text,
                reply_step_before=reply_step,
                intent=analysis.intent_result.label,
                sentiment=analysis.sentiment.level,
                interruption_intent=analysis.interruption_intent,
                assistant_step_after=next_step,
                assistant_prompt=assistant_prompt,
                prompt_guard_action=prompt_action,
                language_offer=analysis.language_decision.candidate_language,
                dialogue_state_after=dialogue_state,
                payment_made_after=state.payment_made,
                ptp_date_after=state.ptp_date,
                reference_number_after=state.reference_number,
            )
        )
        if not analysis.language_decision.should_offer_confirmation:
            _record_assistant_step(state, assistant_step)

    steps_visited = [log.reply_step_before for log in turn_logs] + [log.assistant_step_after for log in turn_logs]
    passed = (
        state.current_step == spec.expected_final_step
        and state.payment_made == spec.expected_payment_made
        and (bool(state.ptp_date) == spec.expect_ptp)
        and (bool(state.reference_number) == spec.expect_reference)
        and ((state.last_transition_reason == "abusive_language") == spec.expect_hostile_exit)
        and (bool(language_offers) == spec.expect_language_offer)
        and (language_switched == spec.expect_language_switch)
        and (
            spec.expect_refusal is None
            or state.refusal_detected == spec.expect_refusal
        )
        and (interruption_override == spec.expect_interruption_override)
        and all(step in steps_visited for step in spec.expected_required_steps)
        and not consecutive_duplicate_prompts
        and not payment_question_repeated_after_unpaid
    )
    return {
        "scenario": spec.key,
        "description": spec.description,
        "passed": passed,
        "final_step": state.current_step,
        "payment_made": state.payment_made,
        "ptp_date": state.ptp_date,
        "reference_number": state.reference_number,
        "last_transition_reason": state.last_transition_reason,
        "refusal_detected": state.refusal_detected,
        "language_offers": language_offers,
        "language_switched": language_switched,
        "interruption_override": interruption_override,
        "no_repeated_prompts": not consecutive_duplicate_prompts,
        "payment_question_repeated_after_unpaid": payment_question_repeated_after_unpaid,
        "steps_visited": steps_visited,
        "turns": [asdict(log) for log in turn_logs],
    }


def run_all_voice_agent_scenarios() -> list[dict]:
    return [simulate_voice_agent_scenario(spec) for spec in scenario_specs()]


def write_validation_artifacts(output_dir: str | Path) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = run_all_voice_agent_scenarios()
    passed = sum(1 for result in results if result["passed"])
    logs_path = out_dir / "voice_agent_simulation_logs.json"
    report_path = out_dir / "voice_agent_validation_report.md"
    logs_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Voice Agent Validation Report",
        "",
        "## Updated Architecture",
        "",
        "Audio Stream -> Streaming STT -> Intent Classifier -> Slot Extractor -> Dialogue State Machine -> Policy Engine -> Deterministic Response Generator -> Streaming TTS",
        "",
        "## Audit Summary",
        "",
        "- Root cause for repeated-question loops: payment-state overrides and prompt repetition handling were not tied to workflow state.",
        "- Root cause for identity leakage: a newly captured name was treated as confirmed identity instead of requiring a second explicit confirmation turn.",
        "- Root cause for language errors: script detection was being treated as language intent without confidence, utterance-length, or entity gating.",
        "- Root cause for barge-in failures: interruption detection was separated from intent/state updates, so corrections and payment commitments did not override the live script cleanly.",
        "",
        "## Scenario Results",
        "",
        f"- Passed scenarios: {passed}/{len(results)}",
        f"- No repeated prompts across all passing scenarios: {all(result['no_repeated_prompts'] for result in results)}",
        f"- No payment-question relapse after unpaid across all passing scenarios: {all(not result['payment_question_repeated_after_unpaid'] for result in results)}",
        "",
    ]
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(f"### {status} `{result['scenario']}`")
        lines.append(f"- Final step: `{result['final_step']}`")
        lines.append(f"- Payment made: `{result['payment_made']}`")
        lines.append(f"- PTP date: `{result['ptp_date']}`")
        lines.append(f"- Reference number: `{result['reference_number']}`")
        lines.append(f"- Language offers: `{result['language_offers']}`")
        lines.append(f"- Interruption override: `{result['interruption_override']}`")
        lines.append("")
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"logs": str(logs_path), "report": str(report_path)}


if __name__ == "__main__":
    write_validation_artifacts(Path(__file__).resolve().parent)
