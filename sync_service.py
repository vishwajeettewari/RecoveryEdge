from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


class SyncService:
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
                CREATE TABLE IF NOT EXISTS integration_connections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    config_json TEXT,
                    created_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_events (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    direction TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    last_error TEXT,
                    payload_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_conflicts (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    field_diffs_json TEXT,
                    status TEXT NOT NULL,
                    resolution TEXT,
                    source_of_truth TEXT,
                    resolved_by TEXT,
                    payload_json TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def inbound_lms(self, payload: Dict[str, Any], actor: str = "system") -> Dict[str, Any]:
        customer_id = str(payload.get("customer_id") or "").strip()
        if not customer_id:
            raise ValueError("customer_id_required")

        event_id = f"syn-{uuid.uuid4().hex[:12]}"
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO sync_events (id, ts, direction, entity_type, entity_id, status, attempts, last_error, payload_json)
                VALUES (?, ?, 'inbound', 'customer', ?, 'received', 1, NULL, ?)
                """,
                (event_id, now, customer_id, json.dumps(payload, ensure_ascii=False)),
            )

            task = conn.execute(
                """
                SELECT * FROM tasks
                WHERE customer_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (customer_id,),
            ).fetchone()
            if not task:
                conn.execute("UPDATE sync_events SET status = 'no_match' WHERE id = ?", (event_id,))
                conn.commit()
                return {"ok": True, "event_id": event_id, "status": "no_match"}

            task_id = str(task["id"])
            conflicts = self._detect_conflicts(task=dict(task), payload=payload)

            # CALLBACK_AT updates are applied directly.
            callback_at_ts = self._parse_ts(payload.get("callback_at") or payload.get("CALLBACK_AT"))
            if callback_at_ts:
                conn.execute(
                    "UPDATE tasks SET state='CALLBACK', callback_at=?, sla_due_at=?, updated_at=?, last_action_at=? WHERE id=?",
                    (callback_at_ts, callback_at_ts, now, now, task_id),
                )
                self._task_event(conn, task_id=task_id, actor=actor, event_type="sync_callback", payload={"callback_at": callback_at_ts}, ts=now)

            payment_status = str(payload.get("payment_status") or "").upper().strip()
            if payment_status in {"DISPUTE", "HARDSHIP"}:
                # Route to escalated while also creating conflict.
                conn.execute(
                    "UPDATE tasks SET state='ESCALATED', disposition=?, updated_at=?, last_action_at=? WHERE id=?",
                    (payment_status.lower(), now, now, task_id),
                )
                self._task_event(conn, task_id=task_id, actor=actor, event_type="sync_escalated", payload={"reason": payment_status.lower()}, ts=now)

            if conflicts:
                conflict_id = f"cnf-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO sync_conflicts (id, ts, entity_type, entity_id, field_diffs_json, status, resolution, source_of_truth, resolved_by, payload_json)
                    VALUES (?, ?, 'task', ?, ?, 'OPEN', NULL, NULL, NULL, ?)
                    """,
                    (conflict_id, now, task_id, json.dumps(conflicts, ensure_ascii=False), json.dumps(payload, ensure_ascii=False)),
                )
                conn.execute("UPDATE sync_events SET status = 'conflict' WHERE id = ?", (event_id,))
                conn.execute(
                    "INSERT INTO events (ts, session_id, event_type, payload_json) VALUES (?, NULL, 'sync_conflict', ?)",
                    (now, json.dumps({"conflict_id": conflict_id, "task_id": task_id, "customer_id": customer_id}, ensure_ascii=False)),
                )
                conn.commit()
                return {"ok": True, "event_id": event_id, "status": "conflict", "conflict_id": conflict_id, "task_id": task_id}

            if payment_status == "PAID":
                conn.execute(
                    "UPDATE tasks SET state='CLOSED', disposition='paid_inbound', updated_at=?, last_action_at=? WHERE id=?",
                    (now, now, task_id),
                )
                self._task_event(conn, task_id=task_id, actor=actor, event_type="sync_paid", payload=payload, ts=now)

            conn.execute("UPDATE sync_events SET status = 'applied' WHERE id = ?", (event_id,))
            conn.execute(
                "INSERT INTO events (ts, session_id, event_type, payload_json) VALUES (?, NULL, 'sync_applied', ?)",
                (now, json.dumps({"event_id": event_id, "task_id": task_id, "customer_id": customer_id}, ensure_ascii=False)),
            )
            conn.commit()
            return {"ok": True, "event_id": event_id, "status": "applied", "task_id": task_id}
        finally:
            conn.close()

    def list_sync_events(self, *, direction: Optional[str] = None, status: Optional[str] = None, page: int = 1, page_size: int = 25) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where = ["1=1"]
            args: List[Any] = []
            if direction:
                where.append("direction = ?")
                args.append(direction)
            if status:
                where.append("status = ?")
                args.append(status)
            total = conn.execute(f"SELECT COUNT(*) AS n FROM sync_events WHERE {' AND '.join(where)}", tuple(args)).fetchone()["n"]
            lim = max(1, min(100, int(page_size)))
            offset = max(0, (max(1, int(page)) - 1) * lim)
            rows = conn.execute(
                f"SELECT * FROM sync_events WHERE {' AND '.join(where)} ORDER BY ts DESC LIMIT ? OFFSET ?",
                tuple(args + [lim, offset]),
            ).fetchall()
            return {"rows": [dict(r) for r in rows], "total": int(total or 0), "page": max(1, int(page)), "page_size": lim}
        finally:
            conn.close()

    def list_conflicts(self, *, status: Optional[str] = None, page: int = 1, page_size: int = 25) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where = ["1=1"]
            args: List[Any] = []
            if status:
                where.append("status = ?")
                args.append(status)
            total = conn.execute(f"SELECT COUNT(*) AS n FROM sync_conflicts WHERE {' AND '.join(where)}", tuple(args)).fetchone()["n"]
            lim = max(1, min(100, int(page_size)))
            offset = max(0, (max(1, int(page)) - 1) * lim)
            rows = conn.execute(
                f"SELECT * FROM sync_conflicts WHERE {' AND '.join(where)} ORDER BY ts DESC LIMIT ? OFFSET ?",
                tuple(args + [lim, offset]),
            ).fetchall()
            return {"rows": [dict(r) for r in rows], "total": int(total or 0), "page": max(1, int(page)), "page_size": lim}
        finally:
            conn.close()

    def resolve_conflict(
        self,
        *,
        conflict_id: str,
        action: str,
        resolved_by: str,
        manual_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        action = (action or "").upper().strip()
        if action not in {"TRUST_LMS", "TRUST_LOCAL", "MANUAL_OVERRIDE"}:
            raise ValueError("invalid_resolution")

        conn = self._connect()
        now = time.time()
        try:
            conflict = conn.execute("SELECT * FROM sync_conflicts WHERE id = ?", (conflict_id,)).fetchone()
            if not conflict:
                return {"ok": False, "error": "conflict_not_found"}
            if str(conflict["status"] or "").upper() == "RESOLVED":
                return {"ok": True, "status": "already_resolved"}

            task_id = str(conflict["entity_id"])
            payload = {}
            try:
                payload = json.loads(conflict["payload_json"] or "{}")
            except Exception:
                payload = {}

            source_of_truth = "LOCAL"
            if action == "TRUST_LMS":
                source_of_truth = "LMS"
                self._apply_lms_payload(conn, task_id=task_id, payload=payload, actor=resolved_by, ts=now)
            elif action == "MANUAL_OVERRIDE":
                source_of_truth = "MANUAL"
                self._apply_manual_override(conn, task_id=task_id, override=manual_override or {}, actor=resolved_by, ts=now)

            conn.execute(
                """
                UPDATE sync_conflicts
                SET status = 'RESOLVED', resolution = ?, source_of_truth = ?, resolved_by = ?, ts = ?
                WHERE id = ?
                """,
                (action, source_of_truth, resolved_by, now, conflict_id),
            )
            conn.execute(
                "INSERT INTO events (ts, session_id, event_type, payload_json) VALUES (?, NULL, 'sync_conflict_resolved', ?)",
                (now, json.dumps({"conflict_id": conflict_id, "action": action, "source_of_truth": source_of_truth, "resolved_by": resolved_by}, ensure_ascii=False)),
            )
            self._task_event(conn, task_id=task_id, actor=resolved_by, event_type="sync_conflict_resolved", payload={"conflict_id": conflict_id, "action": action, "source_of_truth": source_of_truth}, ts=now)
            conn.commit()
            return {"ok": True, "conflict_id": conflict_id, "source_of_truth": source_of_truth}
        finally:
            conn.close()

    def list_dead_letters(self, *, page: int = 1, page_size: int = 25) -> Dict[str, Any]:
        conn = self._connect()
        try:
            total = conn.execute("SELECT COUNT(*) AS n FROM outbound_queue WHERE state = 'dead_letter'").fetchone()["n"]
            lim = max(1, min(100, int(page_size)))
            offset = max(0, (max(1, int(page)) - 1) * lim)
            rows = conn.execute(
                "SELECT * FROM outbound_queue WHERE state = 'dead_letter' ORDER BY updated_ts DESC LIMIT ? OFFSET ?",
                (lim, offset),
            ).fetchall()
            return {"rows": [dict(r) for r in rows], "total": int(total or 0), "page": max(1, int(page)), "page_size": lim}
        finally:
            conn.close()

    def replay_dead_letter(self, queue_id: str, actor: str = "system") -> Dict[str, Any]:
        conn = self._connect()
        now = time.time()
        try:
            row = conn.execute("SELECT * FROM outbound_queue WHERE queue_id = ?", (queue_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "queue_id_not_found"}
            conn.execute(
                "UPDATE outbound_queue SET state = 'queued', next_retry_ts = ?, updated_ts = ? WHERE queue_id = ?",
                (now, now, queue_id),
            )
            conn.execute(
                """
                INSERT INTO sync_events (id, ts, direction, entity_type, entity_id, status, attempts, last_error, payload_json)
                VALUES (?, ?, 'outbound', 'queue', ?, 'replayed', 1, NULL, ?)
                """,
                (f"syn-{uuid.uuid4().hex[:12]}", now, queue_id, json.dumps({"actor": actor}, ensure_ascii=False)),
            )
            conn.execute(
                "INSERT INTO events (ts, session_id, event_type, payload_json) VALUES (?, NULL, 'dead_letter_replay', ?)",
                (now, json.dumps({"queue_id": queue_id, "actor": actor}, ensure_ascii=False)),
            )
            conn.commit()
            return {"ok": True, "queue_id": queue_id, "status": "queued"}
        finally:
            conn.close()

    @staticmethod
    def _detect_conflicts(task: Dict[str, Any], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        conflicts: List[Dict[str, Any]] = []
        pstatus = str(payload.get("payment_status") or "").upper().strip()
        tstate = str(task.get("state") or "").upper().strip()

        if pstatus == "PAID" and tstate != "CLOSED":
            conflicts.append({"field": "payment_status", "local": tstate, "inbound": "PAID", "reason": "inbound_paid_vs_local_open"})

        paid_amount = payload.get("paid_amount")
        amount_due = task.get("amount_due")
        try:
            if paid_amount is not None and amount_due is not None:
                pa = float(paid_amount)
                ad = float(amount_due)
                if ad > 0:
                    diff = abs(pa - ad) / ad
                    if diff > 0.05:
                        conflicts.append({"field": "paid_amount", "local": ad, "inbound": pa, "reason": "amount_mismatch_gt_5pct"})
        except Exception:
            pass

        if pstatus in {"DISPUTE", "HARDSHIP"}:
            conflicts.append({"field": "payment_status", "local": tstate, "inbound": pstatus, "reason": f"inbound_{pstatus.lower()}"})

        return conflicts

    @staticmethod
    def _apply_lms_payload(conn: sqlite3.Connection, *, task_id: str, payload: Dict[str, Any], actor: str, ts: float) -> None:
        pstatus = str(payload.get("payment_status") or "").upper().strip()
        callback_at = SyncService._parse_ts(payload.get("callback_at") or payload.get("CALLBACK_AT"))
        if callback_at:
            conn.execute(
                "UPDATE tasks SET state='CALLBACK', callback_at=?, sla_due_at=?, updated_at=?, last_action_at=? WHERE id=?",
                (callback_at, callback_at, ts, ts, task_id),
            )
            SyncService._task_event(conn, task_id=task_id, actor=actor, event_type="sync_callback", payload={"callback_at": callback_at}, ts=ts)
        if pstatus == "PAID":
            conn.execute(
                "UPDATE tasks SET state='CLOSED', disposition='paid_inbound', updated_at=?, last_action_at=? WHERE id=?",
                (ts, ts, task_id),
            )
            SyncService._task_event(conn, task_id=task_id, actor=actor, event_type="sync_paid", payload=payload, ts=ts)
        if pstatus in {"DISPUTE", "HARDSHIP"}:
            conn.execute(
                "UPDATE tasks SET state='ESCALATED', disposition=?, updated_at=?, last_action_at=? WHERE id=?",
                (pstatus.lower(), ts, ts, task_id),
            )
            SyncService._task_event(conn, task_id=task_id, actor=actor, event_type="sync_escalated", payload=payload, ts=ts)

    @staticmethod
    def _apply_manual_override(conn: sqlite3.Connection, *, task_id: str, override: Dict[str, Any], actor: str, ts: float) -> None:
        state = str(override.get("state") or "").upper().strip()
        disposition = override.get("disposition")
        callback_at = SyncService._parse_ts(override.get("callback_at"))
        if state:
            conn.execute("UPDATE tasks SET state = ?, updated_at = ?, last_action_at = ? WHERE id = ?", (state, ts, ts, task_id))
        if disposition is not None:
            conn.execute("UPDATE tasks SET disposition = ?, updated_at = ? WHERE id = ?", (str(disposition), ts, task_id))
        if callback_at:
            conn.execute("UPDATE tasks SET callback_at = ?, sla_due_at = ?, updated_at = ? WHERE id = ?", (callback_at, callback_at, ts, task_id))
        SyncService._task_event(conn, task_id=task_id, actor=actor, event_type="sync_manual_override", payload=override, ts=ts)

    @staticmethod
    def _parse_ts(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            v = float(value)
            return v if v > 0 else None
        s = str(value).strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s).timestamp()
        except Exception:
            return None

    @staticmethod
    def _task_event(conn: sqlite3.Connection, *, task_id: str, actor: str, event_type: str, payload: Dict[str, Any], ts: float) -> None:
        conn.execute(
            "INSERT INTO task_events (task_id, ts, actor, event_type, payload_json) VALUES (?, ?, ?, ?, ?)",
            (task_id, ts, actor, event_type, json.dumps(payload, ensure_ascii=False)),
        )
