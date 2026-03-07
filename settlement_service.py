from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


class SettlementService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
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
                CREATE TABLE IF NOT EXISTS settlement_offers (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    customer_id TEXT,
                    loan_account_id TEXT,
                    journey_id TEXT,
                    offered_amount REAL NOT NULL,
                    original_due_amount REAL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expiry_ts REAL,
                    terms_json TEXT,
                    actor TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settlement_acceptances (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    offer_id TEXT NOT NULL,
                    accepted_amount REAL NOT NULL,
                    acceptance_channel TEXT,
                    accepted_by TEXT,
                    notes TEXT,
                    payload_json TEXT,
                    actor TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_settlement_offers_tenant_customer ON settlement_offers(tenant_id, customer_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_settlement_acceptances_tenant_offer ON settlement_acceptances(tenant_id, offer_id, created_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    def create_offer(
        self,
        *,
        tenant_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        offered_amount = self._to_float(payload.get("offered_amount"))
        if offered_amount is None or offered_amount <= 0:
            raise ValueError("invalid_offered_amount")
        original_due_amount = self._to_float(payload.get("original_due_amount"))
        currency = str(payload.get("currency") or "INR").strip().upper() or "INR"
        status = str(payload.get("status") or "OPEN").strip().upper() or "OPEN"
        expiry_ts = self._to_float(payload.get("expiry_ts"))
        if expiry_ts is None:
            expiry_ts = time.time() + (7 * 24 * 3600)

        now = time.time()
        offer_id = f"stl-{uuid.uuid4().hex[:12]}"
        terms = payload.get("terms") if isinstance(payload.get("terms"), dict) else {}

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO settlement_offers (
                    id, tenant_id, customer_id, loan_account_id, journey_id,
                    offered_amount, original_due_amount, currency, status, expiry_ts,
                    terms_json, actor, request_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    offer_id,
                    tenant_id,
                    str(payload.get("customer_id") or "").strip() or None,
                    str(payload.get("loan_account_id") or "").strip() or None,
                    str(payload.get("journey_id") or "").strip() or None,
                    offered_amount,
                    original_due_amount,
                    currency,
                    status,
                    expiry_ts,
                    json.dumps(terms, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_offer(tenant_id=tenant_id, offer_id=offer_id) or {}

    def counter_offer(
        self,
        *,
        tenant_id: str,
        base_offer_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        offered_amount = self._to_float(payload.get("offered_amount"))
        if offered_amount is None or offered_amount <= 0:
            raise ValueError("invalid_offered_amount")

        now = time.time()
        conn = self._connect()
        try:
            base = conn.execute(
                "SELECT * FROM settlement_offers WHERE tenant_id = ? AND id = ?",
                (tenant_id, base_offer_id),
            ).fetchone()
            if base is None:
                raise ValueError("base_offer_not_found")

            base_status = str(base["status"] or "").upper()
            if base_status not in {"OPEN", "PENDING", "COUNTERED"}:
                raise ValueError("base_offer_not_negotiable")

            try:
                base_terms = json.loads(base["terms_json"] or "{}")
            except Exception:
                base_terms = {}

            current_round = int(base_terms.get("round") or 1)
            max_rounds = int(payload.get("max_rounds") or base_terms.get("max_rounds") or 3)
            if current_round >= max_rounds:
                raise ValueError("max_counter_rounds_exceeded")

            original_due_amount = self._to_float(payload.get("original_due_amount"))
            if original_due_amount is None:
                original_due_amount = self._to_float(base["original_due_amount"])
            if original_due_amount is None:
                original_due_amount = self._to_float(base["offered_amount"])

            discount_pct = 0.0
            if original_due_amount and original_due_amount > 0:
                discount_pct = round((1.0 - (offered_amount / original_due_amount)) * 100.0, 2)
            if discount_pct > 25:
                raise ValueError("discount_exceeds_policy_limit_25_pct")

            currency = (
                str(payload.get("currency") or base["currency"] or "INR").strip().upper() or "INR"
            )
            expiry_ts = self._to_float(payload.get("expiry_ts"))
            if expiry_ts is None:
                expiry_ts = now + (3 * 24 * 3600)

            extra_terms = payload.get("terms") if isinstance(payload.get("terms"), dict) else {}
            terms = dict(base_terms)
            terms.update(extra_terms)
            terms["round"] = current_round + 1
            terms["max_rounds"] = max_rounds
            terms["counter_of"] = base_offer_id
            terms["discount_pct"] = discount_pct

            offer_id = f"stl-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO settlement_offers (
                    id, tenant_id, customer_id, loan_account_id, journey_id,
                    offered_amount, original_due_amount, currency, status, expiry_ts,
                    terms_json, actor, request_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    offer_id,
                    tenant_id,
                    str(payload.get("customer_id") or base["customer_id"] or "").strip() or None,
                    str(payload.get("loan_account_id") or base["loan_account_id"] or "").strip() or None,
                    str(payload.get("journey_id") or base["journey_id"] or "").strip() or None,
                    offered_amount,
                    original_due_amount,
                    currency,
                    "OPEN",
                    expiry_ts,
                    json.dumps(terms, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE settlement_offers SET status = 'COUNTERED', updated_at = ? WHERE tenant_id = ? AND id = ?",
                (now, tenant_id, base_offer_id),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_offer(tenant_id=tenant_id, offer_id=offer_id) or {}

    def accept_offer(
        self,
        *,
        tenant_id: str,
        offer_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        now = time.time()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM settlement_offers WHERE tenant_id = ? AND id = ?",
                (tenant_id, offer_id),
            ).fetchone()
            if row is None:
                raise ValueError("offer_not_found")
            status = str(row["status"] or "").upper()
            if status not in {"OPEN", "PENDING"}:
                raise ValueError("offer_not_open")
            expiry_ts = self._to_float(row["expiry_ts"])
            if expiry_ts is not None and expiry_ts < now:
                conn.execute(
                    "UPDATE settlement_offers SET status = 'EXPIRED', updated_at = ? WHERE tenant_id = ? AND id = ?",
                    (now, tenant_id, offer_id),
                )
                conn.commit()
                raise ValueError("offer_expired")

            accepted_amount = self._to_float(payload.get("accepted_amount"))
            if accepted_amount is None:
                accepted_amount = float(row["offered_amount"])

            acceptance_id = f"stla-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO settlement_acceptances (
                    id, tenant_id, offer_id, accepted_amount, acceptance_channel,
                    accepted_by, notes, payload_json, actor, request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    acceptance_id,
                    tenant_id,
                    offer_id,
                    accepted_amount,
                    str(payload.get("acceptance_channel") or "voice").strip().lower() or "voice",
                    str(payload.get("accepted_by") or "borrower").strip() or "borrower",
                    str(payload.get("notes") or "").strip() or None,
                    json.dumps(payload or {}, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                ),
            )
            conn.execute(
                "UPDATE settlement_offers SET status = 'ACCEPTED', updated_at = ? WHERE tenant_id = ? AND id = ?",
                (now, tenant_id, offer_id),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_offer_with_acceptance(tenant_id=tenant_id, offer_id=offer_id) or {}

    def get_offer(self, *, tenant_id: str, offer_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM settlement_offers WHERE tenant_id = ? AND id = ?",
                (tenant_id, offer_id),
            ).fetchone()
            if row is None:
                return None
            return self._offer_to_dict(row)
        finally:
            conn.close()

    def get_offer_with_acceptance(self, *, tenant_id: str, offer_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            offer = conn.execute(
                "SELECT * FROM settlement_offers WHERE tenant_id = ? AND id = ?",
                (tenant_id, offer_id),
            ).fetchone()
            if offer is None:
                return None
            acceptance = conn.execute(
                """
                SELECT *
                FROM settlement_acceptances
                WHERE tenant_id = ? AND offer_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (tenant_id, offer_id),
            ).fetchone()
            out = self._offer_to_dict(offer)
            if acceptance is not None:
                out["acceptance"] = self._acceptance_to_dict(acceptance)
            else:
                out["acceptance"] = None
            return out
        finally:
            conn.close()

    def list_offers(
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
                f"SELECT * FROM settlement_offers WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?",
                tuple(args + [max(1, min(500, int(limit)))]),
            ).fetchall()
            return [self._offer_to_dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _offer_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["terms"] = json.loads(out.pop("terms_json") or "{}")
        return out

    @staticmethod
    def _acceptance_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["payload"] = json.loads(out.pop("payload_json") or "{}")
        return out
