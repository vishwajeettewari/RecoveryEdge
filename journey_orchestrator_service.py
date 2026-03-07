from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


JOURNEY_STATUSES = {"ACTIVE", "PAUSED", "CLOSED", "FAILED"}


class JourneyOrchestratorService:
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
                CREATE TABLE IF NOT EXISTS journeys (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    loan_account_id TEXT,
                    status TEXT NOT NULL,
                    stage TEXT,
                    current_step INTEGER NOT NULL DEFAULT 0,
                    channel_hint TEXT,
                    context_json TEXT,
                    started_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    closed_at REAL,
                    created_by TEXT,
                    request_id TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS journey_steps (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    journey_id TEXT NOT NULL,
                    step_no INTEGER NOT NULL,
                    step_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    channel TEXT,
                    status TEXT NOT NULL,
                    signal TEXT,
                    payload_json TEXT,
                    actor TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_journeys_tenant_customer ON journeys(tenant_id, customer_id, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_journey_steps_tenant_journey_no ON journey_steps(tenant_id, journey_id, step_no)"
            )
            self._migrate_tasks(conn)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        try:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        except sqlite3.OperationalError:
            return False
        return any(str(r["name"]) == column for r in rows)

    def _migrate_tasks(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute("SELECT 1 FROM tasks LIMIT 1")
        except sqlite3.OperationalError:
            return
        if not self._column_exists(conn, "tasks", "journey_id"):
            conn.execute("ALTER TABLE tasks ADD COLUMN journey_id TEXT")
        if not self._column_exists(conn, "tasks", "loan_account_id"):
            conn.execute("ALTER TABLE tasks ADD COLUMN loan_account_id TEXT")
        if not self._column_exists(conn, "tasks", "current_nba_decision_id"):
            conn.execute("ALTER TABLE tasks ADD COLUMN current_nba_decision_id TEXT")
        if not self._column_exists(conn, "tasks", "approval_state"):
            conn.execute("ALTER TABLE tasks ADD COLUMN approval_state TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_tenant_journey ON tasks(tenant_id, journey_id)")

    def start_journey(
        self,
        *,
        tenant_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        customer_id = str(payload.get("customer_id") or "").strip()
        if not customer_id:
            raise ValueError("customer_id_required")

        now = time.time()
        journey_id = f"jny-{uuid.uuid4().hex[:12]}"
        stage = str(payload.get("stage") or "outreach").strip().lower()
        channel_hint = str(payload.get("channel_hint") or payload.get("channel") or "voice").strip().lower() or "voice"
        context_payload = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        loan_account_id = str(payload.get("loan_account_id") or "").strip() or None

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO journeys (
                    id, tenant_id, customer_id, loan_account_id, status,
                    stage, current_step, channel_hint, context_json,
                    started_at, updated_at, closed_at, created_by, request_id
                ) VALUES (?, ?, ?, ?, 'ACTIVE', ?, 0, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    journey_id,
                    tenant_id,
                    customer_id,
                    loan_account_id,
                    stage,
                    channel_hint,
                    json.dumps(context_payload, ensure_ascii=False),
                    now,
                    now,
                    actor,
                    request_id,
                ),
            )
            self._insert_step(
                conn,
                tenant_id=tenant_id,
                journey_id=journey_id,
                step_no=1,
                step_type="journey_started",
                direction="system",
                channel=channel_hint,
                status="DONE",
                signal="start",
                payload={"stage": stage, "context": context_payload},
                actor=actor,
                request_id=request_id,
                ts=now,
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_journey(tenant_id=tenant_id, journey_id=journey_id) or {}

    def advance_journey(
        self,
        *,
        tenant_id: str,
        journey_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        now = time.time()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM journeys WHERE tenant_id = ? AND id = ?",
                (tenant_id, journey_id),
            ).fetchone()
            if row is None:
                raise ValueError("journey_not_found")
            if str(row["status"] or "").upper() == "CLOSED":
                raise ValueError("journey_closed")

            step_no = int(row["current_step"] or 0) + 1
            step_type = str(payload.get("step_type") or "journey_advance").strip().lower()
            direction = str(payload.get("direction") or "system").strip().lower() or "system"
            channel = str(payload.get("channel") or row["channel_hint"] or "voice").strip().lower() or "voice"
            signal = str(payload.get("signal") or payload.get("event") or "advance").strip().lower() or "advance"
            status = str(payload.get("status") or "DONE").strip().upper() or "DONE"
            stage = str(payload.get("stage") or row["stage"] or "outreach").strip().lower()

            should_close = bool(payload.get("close") or False)
            if str(payload.get("result") or "").strip().lower() in {"paid", "settled", "resolved", "closed"}:
                should_close = True

            next_status = "CLOSED" if should_close else str(row["status"] or "ACTIVE").upper()
            if next_status not in JOURNEY_STATUSES:
                next_status = "ACTIVE"

            closed_at = now if next_status == "CLOSED" else None

            conn.execute(
                """
                UPDATE journeys
                SET status = ?, stage = ?, current_step = ?, updated_at = ?, closed_at = COALESCE(?, closed_at)
                WHERE tenant_id = ? AND id = ?
                """,
                (next_status, stage, step_no, now, closed_at, tenant_id, journey_id),
            )
            self._insert_step(
                conn,
                tenant_id=tenant_id,
                journey_id=journey_id,
                step_no=step_no,
                step_type=step_type,
                direction=direction,
                channel=channel,
                status=status,
                signal=signal,
                payload=payload,
                actor=actor,
                request_id=request_id,
                ts=now,
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_journey(tenant_id=tenant_id, journey_id=journey_id) or {}

    def get_journey(self, *, tenant_id: str, journey_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            journey = conn.execute(
                "SELECT * FROM journeys WHERE tenant_id = ? AND id = ?",
                (tenant_id, journey_id),
            ).fetchone()
            if journey is None:
                return None
            steps = conn.execute(
                """
                SELECT *
                FROM journey_steps
                WHERE tenant_id = ? AND journey_id = ?
                ORDER BY step_no ASC, created_at ASC
                """,
                (tenant_id, journey_id),
            ).fetchall()
            out = dict(journey)
            out["context"] = json.loads(out.pop("context_json") or "{}")
            out["steps"] = [self._step_row_to_dict(r) for r in steps]
            return out
        finally:
            conn.close()

    def list_journeys(
        self,
        *,
        tenant_id: str,
        customer_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
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
                f"SELECT * FROM journeys WHERE {' AND '.join(where)} ORDER BY updated_at DESC LIMIT ?",
                tuple(args + [max(1, min(200, int(limit)))]),
            ).fetchall()
            return [self._journey_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def _insert_step(
        self,
        conn: sqlite3.Connection,
        *,
        tenant_id: str,
        journey_id: str,
        step_no: int,
        step_type: str,
        direction: str,
        channel: Optional[str],
        status: str,
        signal: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
        ts: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO journey_steps (
                id, tenant_id, journey_id, step_no, step_type,
                direction, channel, status, signal, payload_json,
                actor, request_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"jst-{uuid.uuid4().hex[:12]}",
                tenant_id,
                journey_id,
                max(1, int(step_no)),
                step_type,
                direction,
                channel,
                status,
                signal,
                json.dumps(payload or {}, ensure_ascii=False),
                actor,
                request_id,
                ts,
            ),
        )

    @staticmethod
    def _journey_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["context"] = json.loads(out.pop("context_json") or "{}")
        return out

    @staticmethod
    def _step_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["payload"] = json.loads(out.pop("payload_json") or "{}")
        return out
