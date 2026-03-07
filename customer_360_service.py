from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional


class Customer360Service:
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
                CREATE TABLE IF NOT EXISTS customer_profiles (
                    tenant_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    full_name TEXT,
                    phone TEXT,
                    email TEXT,
                    risk_band TEXT,
                    dpd INTEGER,
                    tags_json TEXT,
                    extra_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    updated_by TEXT,
                    request_id TEXT,
                    PRIMARY KEY (tenant_id, customer_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS loan_accounts (
                    tenant_id TEXT NOT NULL,
                    loan_account_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    principal_outstanding REAL,
                    emi_amount REAL,
                    due_date TEXT,
                    dpd INTEGER,
                    status TEXT,
                    product_type TEXT,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    extra_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    updated_by TEXT,
                    request_id TEXT,
                    PRIMARY KEY (tenant_id, loan_account_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_customer_profiles_tenant_phone ON customer_profiles(tenant_id, phone)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_loan_accounts_tenant_customer ON loan_accounts(tenant_id, customer_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def import_customers(
        self,
        *,
        tenant_id: str,
        rows: List[Dict[str, Any]],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        now = time.time()
        inserted = 0
        updated = 0
        skipped = 0
        conn = self._connect()
        try:
            for row in rows or []:
                customer_id = str(row.get("customer_id") or "").strip()
                if not customer_id:
                    skipped += 1
                    continue
                exists = conn.execute(
                    """
                    SELECT 1 FROM customer_profiles
                    WHERE tenant_id = ? AND customer_id = ?
                    """,
                    (tenant_id, customer_id),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO customer_profiles (
                        tenant_id, customer_id, full_name, phone, email,
                        risk_band, dpd, tags_json, extra_json,
                        created_at, updated_at, updated_by, request_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, customer_id) DO UPDATE SET
                        full_name = excluded.full_name,
                        phone = excluded.phone,
                        email = excluded.email,
                        risk_band = excluded.risk_band,
                        dpd = excluded.dpd,
                        tags_json = excluded.tags_json,
                        extra_json = excluded.extra_json,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by,
                        request_id = excluded.request_id
                    """,
                    (
                        tenant_id,
                        customer_id,
                        (str(row.get("full_name") or row.get("customer_name") or "").strip() or None),
                        (str(row.get("phone") or "").strip() or None),
                        (str(row.get("email") or "").strip() or None),
                        (str(row.get("risk_band") or "").strip() or None),
                        self._to_int(row.get("dpd")),
                        json.dumps(row.get("tags") or [], ensure_ascii=False),
                        json.dumps(row.get("extra") or {}, ensure_ascii=False),
                        now,
                        now,
                        actor,
                        request_id,
                    ),
                )
                if exists is None:
                    inserted += 1
                else:
                    updated += 1
            conn.commit()
        finally:
            conn.close()
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    def upsert_loan_account(
        self,
        *,
        tenant_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        now = time.time()
        loan_account_id = str(payload.get("loan_account_id") or "").strip()
        customer_id = str(payload.get("customer_id") or "").strip()
        if not loan_account_id or not customer_id:
            raise ValueError("loan_account_id_and_customer_id_required")
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO loan_accounts (
                    tenant_id, loan_account_id, customer_id, principal_outstanding,
                    emi_amount, due_date, dpd, status, product_type, currency,
                    extra_json, created_at, updated_at, updated_by, request_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, loan_account_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    principal_outstanding = excluded.principal_outstanding,
                    emi_amount = excluded.emi_amount,
                    due_date = excluded.due_date,
                    dpd = excluded.dpd,
                    status = excluded.status,
                    product_type = excluded.product_type,
                    currency = excluded.currency,
                    extra_json = excluded.extra_json,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by,
                    request_id = excluded.request_id
                """,
                (
                    tenant_id,
                    loan_account_id,
                    customer_id,
                    self._to_float(payload.get("principal_outstanding")),
                    self._to_float(payload.get("emi_amount")),
                    (str(payload.get("due_date") or "").strip() or None),
                    self._to_int(payload.get("dpd")),
                    (str(payload.get("status") or "ACTIVE").strip().upper() or "ACTIVE"),
                    (str(payload.get("product_type") or "").strip() or None),
                    (str(payload.get("currency") or "INR").strip().upper() or "INR"),
                    json.dumps(payload.get("extra") or {}, ensure_ascii=False),
                    now,
                    now,
                    actor,
                    request_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_loan_account(tenant_id=tenant_id, loan_account_id=loan_account_id) or {}

    def get_loan_account(self, *, tenant_id: str, loan_account_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT *
                FROM loan_accounts
                WHERE tenant_id = ? AND loan_account_id = ?
                """,
                (tenant_id, loan_account_id),
            ).fetchone()
            if row is None:
                return None
            return self._loan_to_dict(row)
        finally:
            conn.close()

    def get_customer_360(self, *, tenant_id: str, customer_id: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            profile_row = conn.execute(
                """
                SELECT *
                FROM customer_profiles
                WHERE tenant_id = ? AND customer_id = ?
                """,
                (tenant_id, customer_id),
            ).fetchone()
            profile = self._profile_to_dict(profile_row) if profile_row else None

            loans = [
                self._loan_to_dict(r)
                for r in conn.execute(
                    """
                    SELECT *
                    FROM loan_accounts
                    WHERE tenant_id = ? AND customer_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (tenant_id, customer_id),
                ).fetchall()
            ]

            journeys = self._safe_rows_to_dicts(
                conn,
                """
                SELECT id, status, stage, current_step, started_at, updated_at, closed_at
                FROM journeys
                WHERE tenant_id = ? AND customer_id = ?
                ORDER BY updated_at DESC
                LIMIT 20
                """,
                (tenant_id, customer_id),
            )
            messages = self._safe_rows_to_dicts(
                conn,
                """
                SELECT id, journey_id, channel, direction, content, status, created_at
                FROM channel_messages
                WHERE tenant_id = ? AND customer_id = ?
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (tenant_id, customer_id),
            )
            payments = self._safe_rows_to_dicts(
                conn,
                """
                SELECT id, loan_account_id, amount, currency, rail, status, created_at, updated_at
                FROM payment_intents
                WHERE tenant_id = ? AND customer_id = ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (tenant_id, customer_id),
            )
            settlements = self._safe_rows_to_dicts(
                conn,
                """
                SELECT id, loan_account_id, offered_amount, currency, status, expiry_ts, created_at
                FROM settlement_offers
                WHERE tenant_id = ? AND customer_id = ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (tenant_id, customer_id),
            )

            return {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "profile": profile,
                "loan_accounts": loans,
                "journeys": journeys,
                "channel_messages": messages,
                "payment_intents": payments,
                "settlement_offers": settlements,
            }
        finally:
            conn.close()

    def get_timeline(self, *, customer_id: str) -> List[Dict[str, Any]]:
        """Return chronological list of all events for a customer, across all sources."""
        import json as _j
        events: List[Dict[str, Any]] = []
        conn = self._connect()
        try:
            # Calls from outcomes table.
            # outcomes schema: session_id, start_ts, end_ts, customer_id, disposition, ptp_date, callback_time
            for row in self._safe_rows_to_dicts(
                conn,
                "SELECT session_id, disposition, ptp_date, callback_time, COALESCE(start_ts, end_ts) AS ts FROM outcomes WHERE customer_id = ? ORDER BY COALESCE(start_ts, end_ts) DESC LIMIT 50",
                (customer_id,),
            ):
                events.append({
                    "type": "call",
                    "ts": row.get("ts"),
                    "session_id": row.get("session_id"),
                    "disposition": row.get("disposition"),
                    "ptp_date": row.get("ptp_date"),
                    "callback_time": row.get("callback_time"),
                })

            # Post-call summaries.
            # call_summaries schema: session_id, customer_id, generated_ts, commitment, next_step, sentiment, disposition
            for row in self._safe_rows_to_dicts(
                conn,
                "SELECT session_id, generated_ts, commitment, next_step, sentiment, disposition FROM call_summaries WHERE customer_id = ? ORDER BY generated_ts DESC LIMIT 20",
                (customer_id,),
            ):
                events.append({
                    "type": "summary",
                    "ts": row.get("generated_ts"),
                    "session_id": row.get("session_id"),
                    "commitment": row.get("commitment"),
                    "next_step": row.get("next_step"),
                    "sentiment": row.get("sentiment"),
                    "disposition": row.get("disposition"),
                })

            # Payment intents.
            # payment_intents schema: id, customer_id, amount, currency, status, rail, created_at
            for row in self._safe_rows_to_dicts(
                conn,
                "SELECT id, amount, currency, status, rail, COALESCE(created_at, updated_at) AS ts FROM payment_intents WHERE customer_id = ? ORDER BY COALESCE(created_at, updated_at) DESC LIMIT 20",
                (customer_id,),
            ):
                events.append({
                    "type": "payment",
                    "ts": row.get("ts"),
                    "payment_id": row.get("id"),
                    "amount": row.get("amount"),
                    "currency": row.get("currency"),
                    "status": row.get("status"),
                    "rail": row.get("rail"),
                })

            # Settlement offers.
            # settlement_offers schema: id, customer_id, offered_amount, currency, status, expiry_ts, created_at
            for row in self._safe_rows_to_dicts(
                conn,
                "SELECT id, offered_amount, currency, status, expiry_ts, COALESCE(created_at, updated_at) AS ts FROM settlement_offers WHERE customer_id = ? ORDER BY COALESCE(created_at, updated_at) DESC LIMIT 20",
                (customer_id,),
            ):
                events.append({
                    "type": "settlement",
                    "ts": row.get("ts"),
                    "offer_id": row.get("id"),
                    "offered_amount": row.get("offered_amount"),
                    "currency": row.get("currency"),
                    "status": row.get("status"),
                    "expiry_ts": row.get("expiry_ts"),
                })

            # Audit events (PTP, escalations, etc.) via session join.
            # events schema: id, ts, session_id, event_type, payload_json  — no customer_id column.
            # Join outcomes to filter by customer.
            for row in self._safe_rows_to_dicts(
                conn,
                """
                SELECT e.event_type, e.session_id, e.payload_json, e.ts
                FROM events e
                JOIN outcomes o ON e.session_id = o.session_id
                WHERE o.customer_id = ?
                ORDER BY e.ts DESC
                LIMIT 50
                """,
                (customer_id,),
            ):
                payload: Dict[str, Any] = {}
                try:
                    payload = _j.loads(row.get("payload_json") or "{}")
                except Exception:
                    pass
                events.append({
                    "type": row.get("event_type") or "event",
                    "ts": row.get("ts"),
                    "session_id": row.get("session_id"),
                    "payload": payload,
                })

            # Followup schedules.
            # Table is 'followups' (not 'followup_schedules'), with created_ts (not created_at).
            # Columns: id, session_id, customer_id, reminder_type, channel, scheduled_ts, status, created_ts
            for row in self._safe_rows_to_dicts(
                conn,
                "SELECT id, channel, scheduled_ts, status, reminder_type, created_ts AS ts FROM followups WHERE customer_id = ? ORDER BY created_ts DESC LIMIT 20",
                (customer_id,),
            ):
                events.append({
                    "type": "followup",
                    "ts": row.get("ts"),
                    "followup_id": row.get("id"),
                    "channel": row.get("channel"),
                    "scheduled_ts": row.get("scheduled_ts"),
                    "status": row.get("status"),
                    "reminder_type": row.get("reminder_type"),
                })
        finally:
            conn.close()

        events.sort(key=lambda e: float(e.get("ts") or 0), reverse=True)
        return events

    @staticmethod
    def _profile_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "tenant_id": row["tenant_id"],
            "customer_id": row["customer_id"],
            "full_name": row["full_name"],
            "phone": row["phone"],
            "email": row["email"],
            "risk_band": row["risk_band"],
            "dpd": row["dpd"],
            "tags": json.loads(row["tags_json"] or "[]"),
            "extra": json.loads(row["extra_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "updated_by": row["updated_by"],
            "request_id": row["request_id"],
        }

    @staticmethod
    def _loan_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "tenant_id": row["tenant_id"],
            "loan_account_id": row["loan_account_id"],
            "customer_id": row["customer_id"],
            "principal_outstanding": row["principal_outstanding"],
            "emi_amount": row["emi_amount"],
            "due_date": row["due_date"],
            "dpd": row["dpd"],
            "status": row["status"],
            "product_type": row["product_type"],
            "currency": row["currency"],
            "extra": json.loads(row["extra_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "updated_by": row["updated_by"],
            "request_id": row["request_id"],
        }

    @staticmethod
    def _safe_rows_to_dicts(
        conn: sqlite3.Connection, sql: str, args: tuple[Any, ...]
    ) -> List[Dict[str, Any]]:
        try:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]
        except sqlite3.OperationalError:
            return []

    @staticmethod
    def _to_float(v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        try:
            return float(v)
        except Exception:
            return None

    @staticmethod
    def _to_int(v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(float(v))
        except Exception:
            return None
