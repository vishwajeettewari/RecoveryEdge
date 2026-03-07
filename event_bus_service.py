from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


class EventBusService:
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
                CREATE TABLE IF NOT EXISTS domain_outbox (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    actor TEXT,
                    request_id TEXT,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_ts REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_domain_outbox_tenant_status ON domain_outbox(tenant_id, status, next_retry_ts)"
            )
            conn.commit()
        finally:
            conn.close()

    def publish(
        self,
        *,
        tenant_id: str,
        event_type: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> str:
        now = time.time()
        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO domain_outbox (
                    id, tenant_id, event_type, payload_json, actor, request_id,
                    status, attempts, next_retry_ts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 0, ?, ?, ?)
                """,
                (
                    event_id,
                    tenant_id,
                    event_type,
                    json.dumps(payload or {}, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return event_id

    def list_pending(self, *, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        now = time.time()
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM domain_outbox
                WHERE tenant_id = ?
                  AND status IN ('PENDING', 'RETRY')
                  AND COALESCE(next_retry_ts, 0) <= ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (tenant_id, now, max(1, min(1000, int(limit)))),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "id": r["id"],
                        "tenant_id": r["tenant_id"],
                        "event_type": r["event_type"],
                        "payload": json.loads(r["payload_json"] or "{}"),
                        "actor": r["actor"],
                        "request_id": r["request_id"],
                        "status": r["status"],
                        "attempts": int(r["attempts"] or 0),
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                    }
                )
            return out
        finally:
            conn.close()

    def mark_delivered(self, event_id: str) -> None:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE domain_outbox
                SET status = 'DELIVERED', updated_at = ?
                WHERE id = ?
                """,
                (now, event_id),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_failed(self, event_id: str, *, retry_after_s: float = 30.0) -> None:
        now = time.time()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT attempts FROM domain_outbox WHERE id = ?",
                (event_id,),
            ).fetchone()
            attempts = int(row["attempts"] or 0) + 1 if row else 1
            conn.execute(
                """
                UPDATE domain_outbox
                SET status = 'RETRY',
                    attempts = ?,
                    next_retry_ts = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (attempts, now + max(1.0, float(retry_after_s)), now, event_id),
            )
            conn.commit()
        finally:
            conn.close()
