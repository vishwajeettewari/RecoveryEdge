from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


TASK_STATES = ["NEW", "IN_PROGRESS", "PTP", "CALLBACK", "ESCALATED", "CLOSED"]


class WorkbenchService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()
        self._migrate_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    portfolio_id TEXT,
                    customer_id TEXT NOT NULL,
                    customer_name TEXT,
                    phone TEXT,
                    amount_due REAL,
                    dpd INTEGER,
                    ptp_date TEXT,
                    state TEXT NOT NULL,
                    disposition TEXT,
                    owner TEXT,
                    sla_due_at REAL,
                    last_action_at REAL,
                    priority INTEGER DEFAULT 2,
                    tags_json TEXT,
                    compliance_status_json TEXT,
                    compliance_block INTEGER DEFAULT 0,
                    callback_at REAL,
                    notes TEXT,
                    created_at REAL,
                    updated_at REAL
                )
                """
            )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_campaign_customer ON tasks(campaign_id, customer_id)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    ts REAL NOT NULL,
                    actor TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _migrate_db(self) -> None:
        conn = self._connect()
        try:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            if "ptp_date" not in cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN ptp_date TEXT")
            conn.commit()
        finally:
            conn.close()

    def _task_scope_conditions(
        self,
        *,
        campaign_id: Optional[str] = None,
        state: Optional[str] = None,
        dpd_bucket: Optional[str] = None,
        owner: Optional[str] = None,
        q: Optional[str] = None,
    ) -> tuple[List[str], List[Any]]:
        where = ["1=1"]
        args: List[Any] = []
        if campaign_id:
            where.append("campaign_id = ?")
            args.append(campaign_id)
        if state:
            where.append("state = ?")
            args.append(state)
        if owner:
            where.append("owner = ?")
            args.append(owner)
        if q:
            where.append("(customer_id LIKE ? OR COALESCE(customer_name,'') LIKE ?)")
            like = f"%{q.strip()}%"
            args.extend([like, like])
        if dpd_bucket:
            if dpd_bucket == "1-30":
                where.append("dpd BETWEEN 1 AND 30")
            elif dpd_bucket == "31-60":
                where.append("dpd BETWEEN 31 AND 60")
            elif dpd_bucket == "61-90":
                where.append("dpd BETWEEN 61 AND 90")
            elif dpd_bucket == "90+":
                where.append("dpd > 90")
        return where, args

    def seed_tasks(self, *, campaign_id: str, portfolio_id: str, rows: List[Dict[str, Any]], actor: str = "system") -> int:
        conn = self._connect()
        now = time.time()
        created = 0
        try:
            for row in rows:
                cid = str(row.get("customer_id") or "").strip()
                if not cid:
                    continue
                existing = conn.execute(
                    "SELECT id FROM tasks WHERE campaign_id = ? AND customer_id = ?",
                    (campaign_id, cid),
                ).fetchone()
                if existing:
                    continue
                task_id = f"tsk-{uuid.uuid4().hex[:12]}"
                compliance_status = {
                    "CONSENT_OK": True,
                    "IDENTITY_OK": True,
                    "NO_THREATS_OK": True,
                    "SENSITIVE_ASKS_OK": True,
                }
                conn.execute(
                    """
                    INSERT INTO tasks (
                        id, campaign_id, portfolio_id, customer_id, customer_name, phone, amount_due, dpd, ptp_date,
                        state, disposition, owner, sla_due_at, last_action_at, priority, tags_json,
                        compliance_status_json, compliance_block, callback_at, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'NEW', NULL, NULL, ?, ?, 2, '[]', ?, 0, NULL, NULL, ?, ?)
                    """,
                    (
                        task_id,
                        campaign_id,
                        portfolio_id,
                        cid,
                        row.get("customer_name"),
                        row.get("phone"),
                        row.get("amount_due"),
                        row.get("dpd"),
                        self._compute_sla_due("NEW", now, None),
                        now,
                        json.dumps(compliance_status, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                self._insert_event(conn, task_id=task_id, actor=actor, event_type="created", payload={"state": "NEW"}, ts=now)
                created += 1
            conn.commit()
            return created
        finally:
            conn.close()

    def list_tasks(
        self,
        *,
        campaign_id: Optional[str] = None,
        state: Optional[str] = None,
        dpd_bucket: Optional[str] = None,
        owner: Optional[str] = None,
        q: Optional[str] = None,
        sort: str = "updated_desc",
        page: int = 1,
        page_size: int = 25,
    ) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where, args = self._task_scope_conditions(
                campaign_id=campaign_id,
                state=state,
                dpd_bucket=dpd_bucket,
                owner=owner,
                q=q,
            )

            order_sql = {
                "updated_desc": "updated_at DESC",
                "sla_asc": "sla_due_at ASC",
                "dpd_desc": "dpd DESC",
            }.get(sort, "updated_at DESC")

            total = conn.execute(
                f"SELECT COUNT(*) AS n FROM tasks WHERE {' AND '.join(where)}",
                tuple(args),
            ).fetchone()["n"]

            offset = max(0, (max(1, int(page)) - 1) * max(1, min(100, int(page_size))))
            lim = max(1, min(100, int(page_size)))
            rows = conn.execute(
                f"SELECT * FROM tasks WHERE {' AND '.join(where)} ORDER BY {order_sql} LIMIT ? OFFSET ?",
                tuple(args + [lim, offset]),
            ).fetchall()

            now = time.time()
            out = []
            for r in rows:
                d = dict(r)
                d["sla_breach"] = bool(d.get("state") != "CLOSED" and d.get("sla_due_at") and float(d["sla_due_at"]) < now)
                d["aging_seconds"] = max(0, int(now - float(d.get("last_action_at") or now)))
                out.append(d)
            return {
                "rows": out,
                "page": max(1, int(page)),
                "page_size": lim,
                "total": int(total or 0),
            }
        finally:
            conn.close()

    def customer_ids_in_scope(
        self,
        *,
        campaign_id: Optional[str] = None,
        state: Optional[str] = None,
        dpd_bucket: Optional[str] = None,
    ) -> List[str]:
        conn = self._connect()
        try:
            where, args = self._task_scope_conditions(
                campaign_id=campaign_id,
                state=state,
                dpd_bucket=dpd_bucket,
            )
            rows = conn.execute(
                f"SELECT DISTINCT customer_id FROM tasks WHERE {' AND '.join(where)}",
                tuple(args),
            ).fetchall()
            return [str(r["customer_id"] or "") for r in rows if r["customer_id"]]
        finally:
            conn.close()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return None
            events = conn.execute(
                "SELECT * FROM task_events WHERE task_id = ? ORDER BY ts DESC LIMIT 100",
                (task_id,),
            ).fetchall()
            out = dict(row)
            now = time.time()
            out["sla_breach"] = bool(out.get("state") != "CLOSED" and out.get("sla_due_at") and float(out["sla_due_at"]) < now)
            out["events"] = [dict(e) for e in events]
            return out
        finally:
            conn.close()

    def claim_task(self, *, task_id: str, actor: str) -> Dict[str, Any]:
        conn = self._connect()
        now = time.time()
        try:
            cur = conn.execute(
                """
                UPDATE tasks
                SET owner = ?, state = CASE WHEN state = 'NEW' THEN 'IN_PROGRESS' ELSE state END,
                    sla_due_at = CASE WHEN state = 'NEW' THEN ? ELSE sla_due_at END,
                    last_action_at = ?, updated_at = ?
                WHERE id = ?
                  AND (owner IS NULL OR owner = '' OR owner = ?)
                """,
                (actor, self._compute_sla_due("IN_PROGRESS", now, None), now, now, task_id, actor),
            )
            if cur.rowcount <= 0:
                conn.rollback()
                return {"ok": False, "error": "already_claimed"}
            self._insert_event(conn, task_id=task_id, actor=actor, event_type="claimed", payload={}, ts=now)
            conn.commit()
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return {"ok": True, "task": dict(row) if row else None}
        finally:
            conn.close()

    def update_task(
        self,
        *,
        task_id: str,
        actor: str,
        role: str,
        state: Optional[str] = None,
        ptp_date: Optional[str] = None,
        disposition: Optional[str] = None,
        notes: Optional[str] = None,
        callback_at: Optional[float] = None,
        compliance_override: bool = False,
        escalate_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._connect()
        now = time.time()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "task_not_found"}
            current = dict(row)

            new_state = (state or current.get("state") or "NEW").upper()
            if new_state not in TASK_STATES:
                return {"ok": False, "error": "invalid_state"}

            override_roles = {"ADMIN", "COLLECTIONS_MANAGER", "SUPERVISOR"}

            if int(current.get("compliance_block") or 0) == 1 and not compliance_override:
                if role not in override_roles:
                    return {"ok": False, "error": "compliance_blocked"}
                if new_state not in {"ESCALATED", "CLOSED"}:
                    return {"ok": False, "error": "compliance_blocked_requires_override"}

            if int(current.get("compliance_block") or 0) == 1 and compliance_override and role in override_roles:
                conn.execute("UPDATE tasks SET compliance_block = 0 WHERE id = ?", (task_id,))

            sla_due = self._compute_sla_due(new_state, now, callback_at if callback_at else current.get("callback_at"))
            conn.execute(
                """
                UPDATE tasks
                SET state = ?,
                    ptp_date = COALESCE(?, ptp_date),
                    disposition = COALESCE(?, disposition),
                    notes = COALESCE(?, notes),
                    callback_at = COALESCE(?, callback_at),
                    sla_due_at = ?,
                    last_action_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (new_state, ptp_date, disposition, notes, callback_at, sla_due, now, now, task_id),
            )
            payload = {
                "state": new_state,
                "ptp_date": ptp_date,
                "disposition": disposition,
                "notes": notes,
                "callback_at": callback_at,
                "escalate_reason": escalate_reason,
                "compliance_override": bool(compliance_override),
            }
            evt_type = "updated"
            if new_state == "ESCALATED":
                evt_type = "escalate"
            self._insert_event(conn, task_id=task_id, actor=actor, event_type=evt_type, payload=payload, ts=now)
            conn.execute(
                "INSERT INTO events (ts, session_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
                (now, None, "task_update", json.dumps({"task_id": task_id, "actor": actor, **payload}, ensure_ascii=False)),
            )
            conn.commit()
            out = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return {"ok": True, "task": dict(out) if out else None}
        finally:
            conn.close()

    def bulk_update(self, *, ids: List[str], actor: str, role: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        updated = 0
        errors: List[Dict[str, str]] = []
        for tid in ids:
            if action == "assign":
                owner = str(payload.get("owner") or "").strip()
                if not owner:
                    errors.append({"task_id": tid, "error": "missing_owner"})
                    continue
                res = self._assign_owner(task_id=tid, owner=owner, actor=actor)
            elif action == "close":
                res = self.update_task(
                    task_id=tid,
                    actor=actor,
                    role=role,
                    state="CLOSED",
                    disposition=str(payload.get("disposition") or "closed"),
                    notes=str(payload.get("notes") or ""),
                )
            elif action == "escalate":
                res = self.update_task(
                    task_id=tid,
                    actor=actor,
                    role=role,
                    state="ESCALATED",
                    disposition=str(payload.get("disposition") or "escalated"),
                    notes=str(payload.get("notes") or ""),
                    escalate_reason=str(payload.get("reason") or "bulk_escalation"),
                )
            else:
                errors.append({"task_id": tid, "error": "invalid_action"})
                continue
            if res.get("ok"):
                updated += 1
            else:
                errors.append({"task_id": tid, "error": str(res.get("error") or "unknown")})
        return {"ok": True, "updated": updated, "errors": errors}

    def summary_by_state(
        self,
        campaign_id: Optional[str] = None,
        *,
        state: Optional[str] = None,
        dpd_bucket: Optional[str] = None,
    ) -> Dict[str, int]:
        conn = self._connect()
        try:
            where_parts, args = self._task_scope_conditions(
                campaign_id=campaign_id,
                state=state,
                dpd_bucket=dpd_bucket,
            )
            where = f" WHERE {' AND '.join(where_parts)}"
            rows = conn.execute(
                f"SELECT state, COUNT(*) AS n FROM tasks{where} GROUP BY state",
                tuple(args),
            ).fetchall()
            out = {s: 0 for s in TASK_STATES}
            for r in rows:
                out[str(r["state"])] = int(r["n"] or 0)
            return out
        finally:
            conn.close()

    def set_compliance_block(
        self,
        *,
        task_id: str,
        actor: str,
        blocked: bool,
        badges: Optional[Dict[str, bool]] = None,
        reason: str = "compliance",
    ) -> None:
        conn = self._connect()
        now = time.time()
        try:
            row = conn.execute("SELECT compliance_status_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return
            status = {}
            try:
                status = json.loads(row["compliance_status_json"] or "{}")
            except Exception:
                status = {}
            if badges:
                status.update(badges)
            conn.execute(
                "UPDATE tasks SET compliance_block = ?, compliance_status_json = ?, updated_at = ? WHERE id = ?",
                (1 if blocked else 0, json.dumps(status, ensure_ascii=False), now, task_id),
            )
            self._insert_event(
                conn,
                task_id=task_id,
                actor=actor,
                event_type="compliance_block" if blocked else "compliance_unblock",
                payload={"reason": reason, "badges": status},
                ts=now,
            )
            conn.commit()
        finally:
            conn.close()

    def apply_session_gate_status(self, *, session_snapshot: Dict[str, Any], actor: str = "system") -> Dict[str, int]:
        """Propagate consent/identity gate failures from live session snapshot into tasks.

        If consent or identity is explicitly False, mark task as compliance-blocked.
        """
        customer_id = str(session_snapshot.get("customer_id") or "").strip()
        campaign_id = str(session_snapshot.get("campaign_id") or "").strip()
        consent = session_snapshot.get("consent")
        identity = session_snapshot.get("identity_confirmed")

        badges: Dict[str, bool] = {}
        should_block = False
        if consent is False:
            badges["CONSENT_OK"] = False
            should_block = True
        if identity is False:
            badges["IDENTITY_OK"] = False
            should_block = True
        if not customer_id or not should_block:
            return {"matched": 0, "updated": 0, "blocked": 0}

        conn = self._connect()
        try:
            where = ["customer_id = ?", "state != 'CLOSED'"]
            args: List[Any] = [customer_id]
            if campaign_id:
                where.append("campaign_id = ?")
                args.append(campaign_id)
            rows = conn.execute(
                f"SELECT id, compliance_status_json, compliance_block FROM tasks WHERE {' AND '.join(where)}",
                tuple(args),
            ).fetchall()
        finally:
            conn.close()

        updated = 0
        blocked = 0
        for row in rows:
            tid = str(row["id"])
            prev_block = int(row["compliance_block"] or 0)
            try:
                current_status = json.loads(row["compliance_status_json"] or "{}")
            except Exception:
                current_status = {}
            already_applied = prev_block == 1 and all(current_status.get(k) is v for k, v in badges.items())
            if already_applied:
                continue
            self.set_compliance_block(task_id=tid, actor=actor, blocked=True, badges=badges, reason="missing_gate")
            updated += 1
            if prev_block != 1:
                blocked += 1
        return {"matched": len(rows), "updated": updated, "blocked": blocked}

    def _assign_owner(self, *, task_id: str, owner: str, actor: str) -> Dict[str, Any]:
        conn = self._connect()
        now = time.time()
        try:
            cur = conn.execute("UPDATE tasks SET owner = ?, updated_at = ?, last_action_at = ? WHERE id = ?", (owner, now, now, task_id))
            if cur.rowcount <= 0:
                return {"ok": False, "error": "task_not_found"}
            self._insert_event(conn, task_id=task_id, actor=actor, event_type="assign", payload={"owner": owner}, ts=now)
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @staticmethod
    def _compute_sla_due(state: str, now_ts: float, callback_at: Optional[float]) -> float:
        s = (state or "NEW").upper()
        if s == "NEW":
            return now_ts + 4 * 3600
        if s == "IN_PROGRESS":
            return now_ts + 8 * 3600
        if s == "ESCALATED":
            return now_ts + 2 * 3600
        if s == "CALLBACK" and callback_at:
            return float(callback_at)
        return now_ts + 8 * 3600

    @staticmethod
    def _insert_event(conn: sqlite3.Connection, *, task_id: str, actor: str, event_type: str, payload: Dict[str, Any], ts: float) -> None:
        conn.execute(
            "INSERT INTO task_events (task_id, ts, actor, event_type, payload_json) VALUES (?, ?, ?, ?, ?)",
            (task_id, ts, actor, event_type, json.dumps(payload, ensure_ascii=False)),
        )
