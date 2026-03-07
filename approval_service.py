from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


class ApprovalService:
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
                CREATE TABLE IF NOT EXISTS approval_queue (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    reference_type TEXT,
                    reference_id TEXT,
                    action_type TEXT NOT NULL,
                    risk_score REAL,
                    status TEXT NOT NULL,
                    policy_version TEXT,
                    payload_json TEXT,
                    created_by TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    decided_at REAL,
                    decided_by TEXT,
                    decision_note TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_actions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT,
                    note TEXT,
                    payload_json TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_approval_queue_tenant_status ON approval_queue(tenant_id, status, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_approval_actions_tenant_approval ON approval_actions(tenant_id, approval_id, created_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    def enqueue(
        self,
        *,
        tenant_id: str,
        action_type: str,
        actor: str,
        request_id: str,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        risk_score: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
        policy_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        approval_id = f"apr-{uuid.uuid4().hex[:12]}"
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO approval_queue (
                    id, tenant_id, reference_type, reference_id, action_type,
                    risk_score, status, policy_version, payload_json,
                    created_by, request_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    tenant_id,
                    reference_type,
                    reference_id,
                    action_type,
                    risk_score,
                    policy_version,
                    json.dumps(payload or {}, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO approval_actions (
                    id, tenant_id, approval_id, action, actor, note, payload_json, request_id, created_at
                ) VALUES (?, ?, ?, 'ENQUEUED', ?, NULL, ?, ?, ?)
                """,
                (
                    f"apa-{uuid.uuid4().hex[:12]}",
                    tenant_id,
                    approval_id,
                    actor,
                    json.dumps(payload or {}, ensure_ascii=False),
                    request_id,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_approval(tenant_id=tenant_id, approval_id=approval_id) or {}

    def list_queue(
        self,
        *,
        tenant_id: str,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where = ["tenant_id = ?"]
            args: List[Any] = [tenant_id]
            if status:
                where.append("status = ?")
                args.append(status.upper())
            total = conn.execute(
                f"SELECT COUNT(*) AS n FROM approval_queue WHERE {' AND '.join(where)}",
                tuple(args),
            ).fetchone()["n"]
            lim = max(1, min(200, int(page_size)))
            offset = max(0, (max(1, int(page)) - 1) * lim)
            rows = conn.execute(
                f"SELECT * FROM approval_queue WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(args + [lim, offset]),
            ).fetchall()
            out = [self._queue_row_to_dict(r) for r in rows]
            return {
                "rows": out,
                "total": int(total or 0),
                "page": max(1, int(page)),
                "page_size": lim,
            }
        finally:
            conn.close()

    def approve(
        self,
        *,
        tenant_id: str,
        approval_id: str,
        actor: str,
        request_id: str,
        note: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._decide(
            tenant_id=tenant_id,
            approval_id=approval_id,
            actor=actor,
            request_id=request_id,
            action="APPROVED",
            note=note,
            payload=payload,
        )

    def reject(
        self,
        *,
        tenant_id: str,
        approval_id: str,
        actor: str,
        request_id: str,
        note: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._decide(
            tenant_id=tenant_id,
            approval_id=approval_id,
            actor=actor,
            request_id=request_id,
            action="REJECTED",
            note=note,
            payload=payload,
        )

    def get_approval(self, *, tenant_id: str, approval_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM approval_queue WHERE tenant_id = ? AND id = ?",
                (tenant_id, approval_id),
            ).fetchone()
            if row is None:
                return None
            out = self._queue_row_to_dict(row)
            actions = conn.execute(
                "SELECT * FROM approval_actions WHERE tenant_id = ? AND approval_id = ? ORDER BY created_at ASC",
                (tenant_id, approval_id),
            ).fetchall()
            out["actions"] = [self._action_row_to_dict(a) for a in actions]
            return out
        finally:
            conn.close()

    def _decide(
        self,
        *,
        tenant_id: str,
        approval_id: str,
        actor: str,
        request_id: str,
        action: str,
        note: Optional[str],
        payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        now = time.time()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT status FROM approval_queue WHERE tenant_id = ? AND id = ?",
                (tenant_id, approval_id),
            ).fetchone()
            if row is None:
                raise ValueError("approval_not_found")
            if str(row["status"] or "").upper() != "PENDING":
                raise ValueError("approval_not_pending")
            conn.execute(
                """
                UPDATE approval_queue
                SET status = ?, updated_at = ?, decided_at = ?, decided_by = ?, decision_note = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (action, now, now, actor, note, tenant_id, approval_id),
            )
            conn.execute(
                """
                INSERT INTO approval_actions (
                    id, tenant_id, approval_id, action, actor, note, payload_json, request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"apa-{uuid.uuid4().hex[:12]}",
                    tenant_id,
                    approval_id,
                    action,
                    actor,
                    note,
                    json.dumps(payload or {}, ensure_ascii=False),
                    request_id,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_approval(tenant_id=tenant_id, approval_id=approval_id) or {}

    @staticmethod
    def _queue_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["payload"] = json.loads(out.pop("payload_json") or "{}")
        return out

    @staticmethod
    def _action_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["payload"] = json.loads(out.pop("payload_json") or "{}")
        return out
