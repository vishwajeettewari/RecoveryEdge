from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


class ChannelHubService:
    SUPPORTED_CHANNELS = {"voice", "whatsapp", "sms", "email"}

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
                CREATE TABLE IF NOT EXISTS channel_messages (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    journey_id TEXT,
                    customer_id TEXT,
                    loan_account_id TEXT,
                    channel TEXT NOT NULL,
                    provider TEXT,
                    provider_message_id TEXT,
                    direction TEXT NOT NULL,
                    message_type TEXT,
                    content TEXT,
                    status TEXT NOT NULL,
                    metadata_json TEXT,
                    actor TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_messages_provider_message ON channel_messages(tenant_id, provider, provider_message_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_channel_messages_tenant_customer ON channel_messages(tenant_id, customer_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_channel_messages_tenant_journey ON channel_messages(tenant_id, journey_id, created_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    def send_message(
        self,
        *,
        tenant_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        channel = str(payload.get("channel") or "").strip().lower()
        if channel not in self.SUPPORTED_CHANNELS:
            raise ValueError("unsupported_channel")
        customer_id = str(payload.get("customer_id") or "").strip() or None
        journey_id = str(payload.get("journey_id") or "").strip() or None
        if not customer_id and not journey_id:
            raise ValueError("customer_or_journey_required")
        content = str(payload.get("content") or payload.get("message") or "").strip()
        if not content:
            raise ValueError("content_required")

        now = time.time()
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO channel_messages (
                    id, tenant_id, journey_id, customer_id, loan_account_id,
                    channel, provider, provider_message_id, direction, message_type,
                    content, status, metadata_json, actor, request_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'outbound', ?, ?, 'QUEUED', ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    tenant_id,
                    journey_id,
                    customer_id,
                    str(payload.get("loan_account_id") or "").strip() or None,
                    channel,
                    str(payload.get("provider") or "internal").strip() or "internal",
                    str(payload.get("provider_message_id") or "").strip() or None,
                    str(payload.get("message_type") or "text").strip().lower() or "text",
                    content,
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

        return self.get_message(tenant_id=tenant_id, message_id=message_id) or {}

    def ingest_inbound(
        self,
        *,
        provider: str,
        tenant_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        channel = str(payload.get("channel") or "").strip().lower()
        if channel not in self.SUPPORTED_CHANNELS:
            channel = "voice"
        provider_name = str(provider or payload.get("provider") or "unknown").strip().lower() or "unknown"
        provider_message_id = str(payload.get("provider_message_id") or payload.get("message_id") or "").strip() or None
        customer_id = str(payload.get("customer_id") or "").strip() or None
        journey_id = str(payload.get("journey_id") or "").strip() or None
        content = str(payload.get("content") or payload.get("message") or "").strip()
        status = str(payload.get("status") or "RECEIVED").strip().upper() or "RECEIVED"

        now = time.time()
        conn = self._connect()
        try:
            if provider_message_id:
                existing = conn.execute(
                    """
                    SELECT *
                    FROM channel_messages
                    WHERE tenant_id = ? AND provider = ? AND provider_message_id = ?
                    """,
                    (tenant_id, provider_name, provider_message_id),
                ).fetchone()
                if existing is not None:
                    out = dict(existing)
                    out["metadata"] = json.loads(out.pop("metadata_json") or "{}")
                    out["deduplicated"] = True
                    return out

            message_id = f"msg-{uuid.uuid4().hex[:12]}"
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            conn.execute(
                """
                INSERT INTO channel_messages (
                    id, tenant_id, journey_id, customer_id, loan_account_id,
                    channel, provider, provider_message_id, direction, message_type,
                    content, status, metadata_json, actor, request_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'inbound', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    tenant_id,
                    journey_id,
                    customer_id,
                    str(payload.get("loan_account_id") or "").strip() or None,
                    channel,
                    provider_name,
                    provider_message_id,
                    str(payload.get("message_type") or "text").strip().lower() or "text",
                    content,
                    status,
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

        out = self.get_message(tenant_id=tenant_id, message_id=message_id) or {}
        out["deduplicated"] = False
        return out

    def update_message_status(
        self,
        *,
        tenant_id: str,
        message_id: str,
        status: str,
        actor: str,
    ) -> bool:
        now = time.time()
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                UPDATE channel_messages
                SET status = ?, actor = ?, updated_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (status.upper(), actor, now, tenant_id, message_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def list_messages(
        self,
        *,
        tenant_id: str,
        journey_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        channel: Optional[str] = None,
        direction: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where = ["tenant_id = ?"]
            args: List[Any] = [tenant_id]
            if journey_id:
                where.append("journey_id = ?")
                args.append(journey_id)
            if customer_id:
                where.append("customer_id = ?")
                args.append(customer_id)
            if channel:
                where.append("channel = ?")
                args.append(channel.lower())
            if direction:
                where.append("direction = ?")
                args.append(direction.lower())

            total = conn.execute(
                f"SELECT COUNT(*) AS n FROM channel_messages WHERE {' AND '.join(where)}",
                tuple(args),
            ).fetchone()["n"]
            lim = max(1, min(200, int(page_size)))
            offset = max(0, (max(1, int(page)) - 1) * lim)
            rows = conn.execute(
                f"SELECT * FROM channel_messages WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(args + [lim, offset]),
            ).fetchall()
            return {
                "rows": [self._row_to_dict(r) for r in rows],
                "total": int(total or 0),
                "page": max(1, int(page)),
                "page_size": lim,
            }
        finally:
            conn.close()

    def get_message(self, *, tenant_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM channel_messages WHERE tenant_id = ? AND id = ?",
                (tenant_id, message_id),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_dict(row)
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["metadata"] = json.loads(out.pop("metadata_json") or "{}")
        return out
