from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class StrategyDecision:
    dpd_bucket: str
    strategy_mode: str
    tone_profile: str
    objective: str
    instruction: str
    guardrails: Tuple[str, ...] = field(default_factory=tuple)
    preferred_actions: Tuple[str, ...] = field(default_factory=tuple)
    prohibited_actions: Tuple[str, ...] = field(default_factory=tuple)


class StrategyEngine:
    """Deterministic playbook engine for collections conversations."""

    def classify(
        self,
        dpd: Optional[object],
        *,
        hardship_detected: bool = False,
        dispute_raised: bool = False,
        legal_hold: bool = False,
        partial_payment_offered: bool = False,
        emi_restructure_requested: bool = False,
        callback_requested: bool = False,
        document_requested: bool = False,
        refusal_detected: bool = False,
        refusal_strength: Optional[str] = None,
        no_count: int = 0,
        payment_made: Optional[bool] = None,
        stress_level: Optional[object] = None,
        sentiment: Optional[str] = None,
    ) -> StrategyDecision:
        value = self._to_int(dpd)
        stress = self._to_float(stress_level) or 0.0
        sentiment_norm = str(sentiment or "").strip().lower()

        if legal_hold:
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="legal_hold_exit",
                tone_profile="calm_compliant_exit",
                objective="Stop collection pressure and close the call safely.",
                instruction=(
                    "Customer mentioned legal escalation. Acknowledge calmly, stop all collection activity, "
                    "do not ask for payment, and confirm specialist follow-up."
                ),
                guardrails=(
                    "No payment ask.",
                    "No dispute argument.",
                    "Close politely after acknowledging.",
                ),
                preferred_actions=("acknowledge_legal_reference", "route_to_legal", "close_call"),
                prohibited_actions=("payment_demand", "urgency_language", "threats"),
            )

        if dispute_raised:
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="dispute_resolution",
                tone_profile="calm_validating",
                objective="Preserve trust, capture the dispute, and route the case without argument.",
                instruction=(
                    "Treat the account as disputed. Validate the concern, avoid arguing on amount or ownership, "
                    "offer review/escalation, and only discuss an undisputed amount if the customer volunteers it."
                ),
                guardrails=(
                    "Do not argue on balance or liability.",
                    "Do not pressure for immediate payment.",
                    "Capture dispute reason clearly.",
                ),
                preferred_actions=("acknowledge_dispute", "capture_dispute_reason", "offer_specialist_followup"),
                prohibited_actions=("balance_argument", "forced_commitment", "threat_language"),
            )

        if hardship_detected and partial_payment_offered:
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="hardship_partial_resolution",
                tone_profile="empathetic_solutioning",
                objective="Retain engagement and convert hardship into a realistic staged commitment.",
                instruction=(
                    "Lead with empathy. Accept the partial payment constructively, clarify when the partial amount "
                    "can be paid, and agree a practical follow-up for the remainder."
                ),
                guardrails=(
                    "Do not shame the customer for hardship.",
                    "Do not insist on full payment in the same breath.",
                    "Keep the ask practical and specific.",
                ),
                preferred_actions=("acknowledge_hardship", "accept_partial_payment", "schedule_remainder_followup"),
                prohibited_actions=("full_balance_pressure", "aggressive_deadline", "repeat_same_demand"),
            )

        if hardship_detected:
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="hardship_support",
                tone_profile="empathetic_controlled",
                objective="Keep the customer engaged and move toward a viable recovery path without coercion.",
                instruction=(
                    "Acknowledge hardship before any ask. Prefer callback, smaller feasible commitment, or documented "
                    "review path over a hard payment demand."
                ),
                guardrails=(
                    "Empathy before commitment ask.",
                    "Avoid immediate-payment pressure.",
                    "Offer a viable next step.",
                ),
                preferred_actions=("acknowledge_hardship", "offer_callback", "seek_feasible_commitment"),
                prohibited_actions=("pay_now_pressure", "moralizing", "repeat_same_script"),
            )

        if emi_restructure_requested:
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="restructure_request",
                tone_profile="supportive_formal",
                objective="Capture the restructure request cleanly and preserve the relationship.",
                instruction=(
                    "Acknowledge the EMI restructure request, avoid promising approval, and route it to the right team "
                    "while asking only for the minimum next step."
                ),
                guardrails=(
                    "Do not promise approval.",
                    "Do not continue pressing the same payment demand.",
                ),
                preferred_actions=("acknowledge_request", "confirm_review_followup", "offer_callback"),
                prohibited_actions=("false_approval", "hard_sell_payment"),
            )

        if document_requested:
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="document_assurance",
                tone_profile="reassuring_precise",
                objective="Reduce trust friction by acknowledging the document request and keeping the conversation moving.",
                instruction=(
                    "Confirm the statement or proof will be sent to the registered contact, then ask for the smallest "
                    "reasonable next step only if the customer is still engaged."
                ),
                guardrails=(
                    "Do not claim a document was sent unless that action exists.",
                    "Do not ignore the document request.",
                ),
                preferred_actions=("acknowledge_document_request", "confirm_registered_channel", "offer_callback"),
                prohibited_actions=("dismiss_request", "pretend_document_sent"),
            )

        if partial_payment_offered:
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="partial_payment_conversion",
                tone_profile="constructive_firm",
                objective="Convert willingness into a concrete partial-payment commitment and follow-up plan.",
                instruction=(
                    "Accept the partial payment positively, capture when it can be made, and agree a next step for the remaining balance."
                ),
                guardrails=(
                    "Do not reject willingness to pay.",
                    "Avoid pushing immediately back to the full amount.",
                ),
                preferred_actions=("accept_partial_offer", "capture_partial_date", "plan_remainder_followup"),
                prohibited_actions=("all_or_nothing_demand", "tone_escalation"),
            )

        if payment_made is True:
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="payment_verification",
                tone_profile="efficient_reassuring",
                objective="Verify the claimed payment quickly and close the loop.",
                instruction=(
                    "Assume good faith, ask for UTR or payment date, and avoid unnecessary collection language once payment is claimed."
                ),
                guardrails=(
                    "Do not keep asking for payment after claimed payment.",
                    "Ask only for verification details.",
                ),
                preferred_actions=("request_utr", "capture_payment_date", "close_after_verification"),
                prohibited_actions=("repeat_payment_demand", "disbelief_language"),
            )

        if refusal_detected:
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="resistance_resolution",
                tone_profile="firm_solution_oriented" if refusal_strength == "hard" else "empathetic_solution_oriented",
                objective="Acknowledge payment resistance and move the call toward one practical recovery path.",
                instruction=(
                    "Acknowledge the customer's resistance briefly, explain that the loan still needs a workable resolution, "
                    "and ask for one feasible next step such as a dated commitment, partial payment, or callback to discuss options."
                ),
                guardrails=(
                    "Do not threaten or moralize.",
                    "Do not repeat the same payment ask word-for-word.",
                    "Keep the tone respectful and solution-oriented.",
                ),
                preferred_actions=("acknowledge_resistance", "seek_feasible_commitment", "offer_options"),
                prohibited_actions=("empty_closing", "argument", "pressure_language"),
            )

        if callback_requested or (refusal_detected and (refusal_strength == "hard" or no_count >= 2 or stress >= 0.65)):
            return StrategyDecision(
                dpd_bucket=self._bucket_label(value),
                strategy_mode="callback_salvage",
                tone_profile="deescalating_respectful",
                objective="Preserve contactability and avoid further resistance.",
                instruction=(
                    "Do not repeat the same demand. Pivot to a callback window or one practical next step that reduces friction."
                ),
                guardrails=(
                    "No repeated payment-demand loop.",
                    "Keep tone calm and respectful.",
                ),
                preferred_actions=("offer_callback", "clarify_best_time", "minimize_friction"),
                prohibited_actions=("repeat_same_ask", "pressure_language"),
            )

        if value <= 0:
            return StrategyDecision(
                dpd_bucket="0",
                strategy_mode="baseline",
                tone_profile="neutral",
                objective="Verify context and get a clean payment-status answer.",
                instruction="Use a neutral reminder tone and verify account context before asking for commitment.",
                guardrails=("Stay factual.", "Do not create urgency without delinquency context."),
                preferred_actions=("verify_context", "clarify_payment_status"),
            )
        if value <= 30:
            return StrategyDecision(
                dpd_bucket="1-30",
                strategy_mode="soft_reminder",
                tone_profile="empathetic" if sentiment_norm != "negative" and stress < 0.55 else "calm_empathetic",
                objective="Protect willingness and convert early-stage delinquency into a concrete commitment.",
                instruction=(
                    "Use a soft reminder tone. Prioritize cooperative language, keep the ask low-friction, "
                    "and capture a feasible payment date or callback."
                ),
                guardrails=("Do not over-escalate early-stage delinquency.",),
                preferred_actions=("friendly_reminder", "capture_payment_date", "offer_callback_if_uncertain"),
            )
        if value <= 60:
            return StrategyDecision(
                dpd_bucket="31-60",
                strategy_mode="firm_commitment",
                tone_profile="firm_respectful",
                objective="Convert moderate-risk delinquency into a dated commitment or controlled callback.",
                instruction=(
                    "Use a firm but respectful tone. Ask directly for a commitment date or callback slot, "
                    "but stay solution-oriented if the customer shows strain."
                ),
                guardrails=("Be direct without sounding punitive.",),
                preferred_actions=("ask_for_commitment", "capture_callback_if_needed"),
            )
        if value <= 90:
            return StrategyDecision(
                dpd_bucket="61-90",
                strategy_mode="high_urgency",
                tone_profile="urgent_controlled" if stress < 0.6 else "firm_deescalating",
                objective="Increase urgency while avoiding escalation into avoidance or complaint.",
                instruction=(
                    "Use high urgency language without threats. Make the next step explicit, and if the customer resists, "
                    "prefer a controlled callback or supervisor follow-up over a repeated demand loop."
                ),
                guardrails=("No intimidation.", "No legal bluffing.", "Do not trap the customer in repetition."),
                preferred_actions=("state_urgency", "ask_for_specific_date", "route_followup_if_blocked"),
            )
        return StrategyDecision(
            dpd_bucket="90+",
            strategy_mode="pre_legal_caution",
            tone_profile="strict_compliant",
            objective="Maximize recovery while minimizing legal and conduct risk in late-stage delinquency.",
            instruction=(
                "Use pre-legal caution language compliant with RBI/TRAI. Be explicit about seriousness without intimidation, "
                "offer an escalation path, and avoid any statement that sounds like a threat or false legal claim."
            ),
            guardrails=("No threats.", "No harassment.", "No false legal consequences."),
            preferred_actions=("state_seriousness", "ask_for_final_commitment", "offer_supervisor_path"),
            prohibited_actions=("intimidation", "false_legal_claim", "public_shaming"),
        )

    @staticmethod
    def _bucket_label(value: int) -> str:
        if value <= 0:
            return "0"
        if value <= 30:
            return "1-30"
        if value <= 60:
            return "31-60"
        if value <= 90:
            return "61-90"
        return "90+"

    @staticmethod
    def _to_int(dpd: Optional[object]) -> int:
        if dpd is None:
            return 0
        if isinstance(dpd, bool):
            return 0
        if isinstance(dpd, (int, float)):
            return int(dpd)
        txt = str(dpd).strip()
        if not txt:
            return 0
        try:
            return int(float(txt))
        except Exception:
            return 0

    @staticmethod
    def _to_float(value: Optional[object]) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        txt = str(value).strip()
        if not txt:
            return None
        try:
            return float(txt)
        except Exception:
            return None
