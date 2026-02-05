from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional, Tuple


def _now_ts() -> float:
    return round(time.time(), 3)


class ActionRouter:
    def __init__(self, pay_base_url: str = "https://pay.example/demo") -> None:
        self.pay_base_url = (pay_base_url or "").rstrip("/") or "https://pay.example/demo"

    def send_payment_link(
        self,
        *,
        session_id: str,
        customer_id: Optional[str],
        customer_phone: Optional[str],
        amount: Optional[str],
        channel: str = "whatsapp",
    ) -> Dict[str, Any]:
        channel = (channel or "whatsapp").strip().lower()
        token = uuid.uuid4().hex[:10]
        link = f"{self.pay_base_url}?sid={session_id}&cid={customer_id or ''}&amt={amount or ''}&t={token}"
        body = f"Payment link for your overdue amount{(' INR ' + str(amount)) if amount else ''}: {link}"
        return {
            "ts": _now_ts(),
            "channel": channel,
            "to": customer_phone,
            "amount": amount,
            "link": link,
            "body": body,
            "message_id": f"msg-{token}",
        }

    def escalate_ticket(
        self,
        *,
        session_id: str,
        customer_id: Optional[str],
        category: str,
        reason: str,
        last_user_text: str,
        last_assistant_text: str,
    ) -> Dict[str, Any]:
        tid = f"TCK-{uuid.uuid4().hex[:8].upper()}"
        summary = (
            f"Escalation requested. Category={category}. Reason={reason}. "
            f"Last customer: {last_user_text[:160]}. Last agent: {last_assistant_text[:160]}."
        )
        return {
            "ts": _now_ts(),
            "ticket_id": tid,
            "session_id": session_id,
            "customer_id": customer_id,
            "category": category,
            "reason": reason,
            "summary": summary,
            "status": "open",
        }

