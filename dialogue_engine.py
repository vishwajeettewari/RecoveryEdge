from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from workflow_engine import WorkflowState


@dataclass(frozen=True)
class ConversationState:
    borrower_name: Optional[str] = None
    loan_amount: Optional[str] = None
    due_amount: Optional[str] = None
    payment_status: Optional[str] = None
    ptp_date: Optional[str] = None
    ptp_amount: Optional[str] = None
    ptp_confirmed: bool = False
    language: Optional[str] = None
    abuse_count: int = 0
    current_step: str = "INTRO"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_conversation_state(
    *,
    facts: dict[str, Any],
    workflow_state: WorkflowState,
    language: Optional[str],
) -> ConversationState:
    payment_status: Optional[str]
    if workflow_state.payment_made is True:
        payment_status = "payment_done"
    elif workflow_state.payment_made is False:
        payment_status = "payment_pending"
    else:
        payment_status = None

    return ConversationState(
        borrower_name=str(facts.get("customer_name") or "").strip() or None,
        loan_amount=str(facts.get("loan_amount") or facts.get("overdue_amount") or "").strip() or None,
        due_amount=str(facts.get("due_amount") or facts.get("overdue_amount") or "").strip() or None,
        payment_status=payment_status,
        ptp_date=str(workflow_state.ptp_date or facts.get("ptp_date") or "").strip() or None,
        ptp_amount=str(facts.get("ptp_amount") or "").strip() or None,
        ptp_confirmed=bool(workflow_state.ptp_confirmed),
        language=str(language or facts.get("language_preference") or "").strip() or None,
        abuse_count=int(getattr(workflow_state, "abuse_count", 0) or 0),
        current_step=str(getattr(workflow_state, "current_step", "INTRO") or "INTRO"),
    )


def requires_llm_reasoning(
    *,
    workflow_state: WorkflowState,
    pending_customer_meta_question: Optional[str],
) -> bool:
    if pending_customer_meta_question:
        return False
    return bool(
        workflow_state.dispute_raised
        or workflow_state.hardship_detected
        or workflow_state.partial_payment_offered
        or workflow_state.emi_restructure_requested
    )
