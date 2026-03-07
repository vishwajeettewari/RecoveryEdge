from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


INTENT_STATUSES = {
    "INITIATED",
    "PENDING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
}


class PaymentOrchestrationService:
    def __init__(self, db_path: str, pay_base_url: str = "https://pay.example/demo") -> None:
        self.db_path = db_path
        self.pay_base_url = pay_base_url.rstrip("/")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_intents (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    customer_id TEXT,
                    loan_account_id TEXT,
                    journey_id TEXT,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    rail TEXT NOT NULL,
                    provider_ref TEXT,
                    payment_link TEXT,
                    status TEXT NOT NULL,
                    expiry_ts REAL,
                    metadata_json TEXT,
                    actor TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    payment_intent_id TEXT,
                    rail TEXT NOT NULL,
                    provider_event_id TEXT,
                    event_type TEXT NOT NULL,
                    normalized_status TEXT,
                    payload_json TEXT,
                    actor TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_events_provider_event ON payment_events(tenant_id, rail, provider_event_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_payment_intents_tenant_customer ON payment_intents(tenant_id, customer_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_payment_intents_tenant_status ON payment_intents(tenant_id, status, updated_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    def create_intent(
        self,
        *,
        tenant_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        amount = self._to_float(payload.get("amount"))
        if amount is None or amount <= 0:
            raise ValueError("invalid_amount")
        rail = str(payload.get("rail") or "upi").strip().lower() or "upi"
        currency = str(payload.get("currency") or "INR").strip().upper() or "INR"
        status = str(payload.get("status") or "INITIATED").strip().upper() or "INITIATED"
        if status not in INTENT_STATUSES:
            status = "INITIATED"

        intent_id = f"payi-{uuid.uuid4().hex[:12]}"
        now = time.time()
        expiry_ts = self._to_float(payload.get("expiry_ts"))
        if expiry_ts is None:
            expiry_ts = now + 72 * 3600

        provider_ref = str(payload.get("provider_ref") or "").strip() or None
        payment_link = str(payload.get("payment_link") or "").strip()
        if not payment_link:
            payment_link = f"{self.pay_base_url}/{intent_id}"

        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO payment_intents (
                    id, tenant_id, customer_id, loan_account_id, journey_id,
                    amount, currency, rail, provider_ref, payment_link,
                    status, expiry_ts, metadata_json, actor, request_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent_id,
                    tenant_id,
                    str(payload.get("customer_id") or "").strip() or None,
                    str(payload.get("loan_account_id") or "").strip() or None,
                    str(payload.get("journey_id") or "").strip() or None,
                    amount,
                    currency,
                    rail,
                    provider_ref,
                    payment_link,
                    status,
                    expiry_ts,
                    json.dumps(metadata, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_intent(tenant_id=tenant_id, intent_id=intent_id) or {}

    def ingest_webhook(
        self,
        *,
        rail: str,
        tenant_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        normalized_rail = str(rail or payload.get("rail") or "upi").strip().lower() or "upi"
        provider_event_id = str(payload.get("provider_event_id") or payload.get("event_id") or "").strip() or None
        event_type = str(payload.get("event_type") or payload.get("type") or "payment_update").strip().lower()
        status = self._normalize_status(payload.get("status") or payload.get("payment_status"))
        intent_id = str(payload.get("payment_intent_id") or payload.get("intent_id") or "").strip() or None

        conn = self._connect()
        now = time.time()
        try:
            if provider_event_id:
                duplicate = conn.execute(
                    """
                    SELECT id, payment_intent_id, normalized_status
                    FROM payment_events
                    WHERE tenant_id = ? AND rail = ? AND provider_event_id = ?
                    """,
                    (tenant_id, normalized_rail, provider_event_id),
                ).fetchone()
                if duplicate is not None:
                    return {
                        "ok": True,
                        "deduplicated": True,
                        "event_id": duplicate["id"],
                        "payment_intent_id": duplicate["payment_intent_id"],
                        "status": duplicate["normalized_status"],
                    }

            if intent_id:
                intent = conn.execute(
                    "SELECT id, status FROM payment_intents WHERE tenant_id = ? AND id = ?",
                    (tenant_id, intent_id),
                ).fetchone()
            else:
                provider_ref = str(payload.get("provider_ref") or "").strip()
                intent = None
                if provider_ref:
                    intent = conn.execute(
                        """
                        SELECT id, status
                        FROM payment_intents
                        WHERE tenant_id = ? AND provider_ref = ?
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (tenant_id, provider_ref),
                    ).fetchone()
                if intent is not None:
                    intent_id = str(intent["id"])

            event_id = f"paye-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO payment_events (
                    id, tenant_id, payment_intent_id, rail, provider_event_id,
                    event_type, normalized_status, payload_json,
                    actor, request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    tenant_id,
                    intent_id,
                    normalized_rail,
                    provider_event_id,
                    event_type,
                    status,
                    json.dumps(payload or {}, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                ),
            )

            if intent_id:
                conn.execute(
                    """
                    UPDATE payment_intents
                    SET status = ?, updated_at = ?
                    WHERE tenant_id = ? AND id = ?
                    """,
                    (status, now, tenant_id, intent_id),
                )

            conn.commit()
            return {
                "ok": True,
                "deduplicated": False,
                "event_id": event_id,
                "payment_intent_id": intent_id,
                "status": status,
            }
        finally:
            conn.close()

    def get_intent(self, *, tenant_id: str, intent_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM payment_intents WHERE tenant_id = ? AND id = ?",
                (tenant_id, intent_id),
            ).fetchone()
            if row is None:
                return None
            return self._intent_to_dict(row)
        finally:
            conn.close()

    def list_intents(
        self,
        *,
        tenant_id: str,
        customer_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            where = ["tenant_id = ?"]
            args: List[Any] = [tenant_id]
            if customer_id:
                where.append("customer_id = ?")
                args.append(customer_id)
            if status:
                where.append("status = ?")
                args.append(status.upper())
            rows = conn.execute(
                f"SELECT * FROM payment_intents WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?",
                tuple(args + [max(1, min(500, int(limit)))]),
            ).fetchall()
            return [self._intent_to_dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _normalize_status(raw: Any) -> str:
        token = str(raw or "").strip().lower()
        if token in {"success", "succeeded", "paid", "completed", "settled"}:
            return "SUCCEEDED"
        if token in {"failed", "failure", "declined"}:
            return "FAILED"
        if token in {"cancelled", "canceled", "void"}:
            return "CANCELLED"
        if token in {"expired", "timed_out"}:
            return "EXPIRED"
        if token in {"pending", "processing", "initiated", "created"}:
            return "PENDING"
        return "PENDING"

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _intent_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["metadata"] = json.loads(out.pop("metadata_json") or "{}")
        return out
