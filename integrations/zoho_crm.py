"""Zoho CRM demo connector.

In demo mode (default) this module simulates Zoho CRM push/pull operations and
stores a local sync log in data/crm_sync.db.  No real Zoho account is required.

To connect a real Zoho org set these env vars:
  ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN, ZOHO_ORG_ID
The real Zoho REST API base is https://www.zohoapis.in/crm/v3 (India DC).
"""
from __future__ import annotations

import json
import random
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Real Zoho REST API shape (commented out — plug in keys to activate)
# ---------------------------------------------------------------------------
# import httpx
# _ZOHO_BASE = "https://www.zohoapis.in/crm/v3"
# _TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"
#
# async def _refresh_token(client_id, client_secret, refresh_token):
#     async with httpx.AsyncClient() as c:
#         r = await c.post(_TOKEN_URL, data={
#             "grant_type": "refresh_token",
#             "client_id": client_id,
#             "client_secret": client_secret,
#             "refresh_token": refresh_token,
#         })
#     return r.json().get("access_token")
#
# async def _push_contact(access_token, org_id, payload):
#     async with httpx.AsyncClient() as c:
#         r = await c.post(
#             f"{_ZOHO_BASE}/Contacts",
#             headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
#             json={"data": [payload]},
#         )
#     return r.json()
# ---------------------------------------------------------------------------


class ZohoCRM:
    """Demo-mode Zoho CRM connector with local sync log."""

    DB_SCHEMA = """
    CREATE TABLE IF NOT EXISTS crm_sync_log (
        id TEXT PRIMARY KEY,
        session_id TEXT,
        customer_id TEXT,
        direction TEXT NOT NULL,         -- 'push' | 'pull'
        entity_type TEXT,               -- 'contact' | 'deal' | 'activity'
        zoho_record_id TEXT,
        status TEXT NOT NULL,           -- 'ok' | 'failed' | 'conflict'
        retry_count INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT,
        response_json TEXT,
        error TEXT,
        pushed_at REAL,
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_crm_sync_session ON crm_sync_log(session_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_crm_sync_customer ON crm_sync_log(customer_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_crm_sync_status ON crm_sync_log(status, created_at DESC);
    """

    def __init__(self, db_path: str = "data/crm_sync.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            for stmt in self.DB_SCHEMA.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Push: send outcome to Zoho
    # ------------------------------------------------------------------
    def push_outcome(self, *, session_id: str, outcome: Dict[str, Any]) -> Dict[str, Any]:
        """Push a call outcome to Zoho CRM (demo: ~90% success rate)."""
        now = time.time()
        sync_id = f"zsync-{uuid.uuid4().hex[:10]}"
        customer_id = str(outcome.get("customer_id") or "")

        # Demo: simulate 90% success.
        seed = sum(ord(c) for c in sync_id)
        success = (seed % 100) < 90
        zoho_record_id = f"zoho-{uuid.uuid4().hex[:8]}" if success else None
        status = "ok" if success else "failed"
        error = None if success else "zoho_api_timeout_simulated"

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO crm_sync_log
                    (id, session_id, customer_id, direction, entity_type, zoho_record_id,
                     status, retry_count, payload_json, response_json, error, pushed_at, created_at)
                VALUES (?, ?, ?, 'push', 'activity', ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    sync_id,
                    session_id,
                    customer_id,
                    zoho_record_id,
                    status,
                    json.dumps(outcome, ensure_ascii=False),
                    json.dumps({"record_id": zoho_record_id}, ensure_ascii=False),
                    error,
                    now if success else None,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "sync_id": sync_id,
            "session_id": session_id,
            "customer_id": customer_id,
            "status": status,
            "zoho_record_id": zoho_record_id,
            "error": error,
        }

    # ------------------------------------------------------------------
    # Pull: fetch payment/status update from Zoho for a customer
    # ------------------------------------------------------------------
    def pull_status(self, *, customer_id: str, demo_db_path: Optional[str] = None) -> Dict[str, Any]:
        """Pull latest payment status for customer (demo: read from payment_intents)."""
        now = time.time()
        sync_id = f"zpull-{uuid.uuid4().hex[:10]}"
        payment_info: Dict[str, Any] = {}

        if demo_db_path:
            try:
                pconn = sqlite3.connect(demo_db_path, check_same_thread=False)
                pconn.row_factory = sqlite3.Row
                row = pconn.execute(
                    """
                    SELECT id, amount, currency, status, created_at
                    FROM payment_intents
                    WHERE customer_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (customer_id,),
                ).fetchone()
                if row:
                    payment_info = dict(row)
                pconn.close()
            except Exception:
                pass

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO crm_sync_log
                    (id, session_id, customer_id, direction, entity_type, zoho_record_id,
                     status, retry_count, payload_json, response_json, error, pushed_at, created_at)
                VALUES (?, NULL, ?, 'pull', 'contact', NULL, 'ok', 0, ?, ?, NULL, ?, ?)
                """,
                (
                    sync_id,
                    customer_id,
                    json.dumps({"customer_id": customer_id}, ensure_ascii=False),
                    json.dumps({"payment": payment_info}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "sync_id": sync_id,
            "customer_id": customer_id,
            "direction": "pull",
            "payment": payment_info,
        }

    # ------------------------------------------------------------------
    # Conflict resolution: last-write-wins with audit trail
    # ------------------------------------------------------------------
    def handle_conflict(
        self,
        *,
        session_id: str,
        remote: Dict[str, Any],
        local: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resolve conflict: last-write-wins.  Logs both versions for audit."""
        now = time.time()
        sync_id = f"zconf-{uuid.uuid4().hex[:10]}"
        remote_ts = float(remote.get("updated_at") or remote.get("ts") or 0)
        local_ts = float(local.get("updated_at") or local.get("ts") or now)
        winner = "remote" if remote_ts >= local_ts else "local"
        resolved = remote if winner == "remote" else local

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO crm_sync_log
                    (id, session_id, customer_id, direction, entity_type, zoho_record_id,
                     status, retry_count, payload_json, response_json, error, pushed_at, created_at)
                VALUES (?, ?, ?, 'push', 'conflict', NULL, 'conflict', 0, ?, ?, NULL, ?, ?)
                """,
                (
                    sync_id,
                    session_id,
                    str(local.get("customer_id") or remote.get("customer_id") or ""),
                    json.dumps({"remote": remote, "local": local}, ensure_ascii=False),
                    json.dumps({"winner": winner, "resolved": resolved}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "sync_id": sync_id,
            "winner": winner,
            "resolved": resolved,
            "remote_ts": remote_ts,
            "local_ts": local_ts,
        }

    # ------------------------------------------------------------------
    # Status / sync log
    # ------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        """Return push/pull counts and last sync timestamp."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM crm_sync_log GROUP BY status"
            ).fetchall()
            counts = {r["status"]: int(r["n"]) for r in rows}
            last_row = conn.execute(
                "SELECT pushed_at FROM crm_sync_log WHERE pushed_at IS NOT NULL ORDER BY pushed_at DESC LIMIT 1"
            ).fetchone()
            last_sync_ts = float(last_row["pushed_at"]) if last_row else None
            return {
                "provider": "zoho",
                "counts": counts,
                "last_sync_ts": last_sync_ts,
                "queued": counts.get("failed", 0),
                "acked": counts.get("ok", 0),
                "failed": counts.get("failed", 0),
                "conflicts": counts.get("conflict", 0),
            }
        finally:
            conn.close()

    def sync_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return last N sync log entries."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM crm_sync_log ORDER BY created_at DESC LIMIT ?",
                (max(1, min(200, int(limit))),),
            ).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                for field in ("payload_json", "response_json"):
                    raw = item.pop(field, None)
                    key = field.replace("_json", "")
                    try:
                        item[key] = json.loads(raw or "{}")
                    except Exception:
                        item[key] = {}
                out.append(item)
            return out
        finally:
            conn.close()

    def process_queue(self, *, main_db_path: Optional[str] = None) -> Dict[str, int]:
        """Re-attempt failed pushes (demo: simulate retry success ~80%)."""
        conn = self._connect()
        now = time.time()
        stats = {"retried": 0, "recovered": 0, "still_failed": 0}
        try:
            rows = conn.execute(
                "SELECT * FROM crm_sync_log WHERE status = 'failed' ORDER BY created_at ASC LIMIT 50"
            ).fetchall()
            for row in rows:
                retry_count = int(row["retry_count"] or 0) + 1
                seed = sum(ord(c) for c in row["id"]) + retry_count * 7
                success = (seed % 100) < 80
                new_status = "ok" if success else "failed"
                zoho_id = f"zoho-{uuid.uuid4().hex[:8]}" if success else None
                conn.execute(
                    """
                    UPDATE crm_sync_log
                    SET status = ?, retry_count = ?, zoho_record_id = COALESCE(?, zoho_record_id), pushed_at = ?
                    WHERE id = ?
                    """,
                    (new_status, retry_count, zoho_id, now if success else None, row["id"]),
                )
                stats["retried"] += 1
                if success:
                    stats["recovered"] += 1
                else:
                    stats["still_failed"] += 1
            conn.commit()
        finally:
            conn.close()
        return stats
