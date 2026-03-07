from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


DEFAULT_MODELS = [
    {"provider": "sarvam", "model_name": "sarvam-m", "modality": "llm", "cost_tier": "standard"},
    {"provider": "sarvam", "model_name": "saarika-v2", "modality": "stt", "cost_tier": "standard"},
    {"provider": "sarvam", "model_name": "bulbul-v2", "modality": "tts", "cost_tier": "standard"},
]


class ModelRouterService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()
        self._seed_defaults()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_registry (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cost_tier TEXT,
                    latency_class TEXT,
                    metadata_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(tenant_id, provider, model_name)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_routes (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    policy_version TEXT,
                    constraints_json TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_invocations (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    route_id TEXT,
                    request_id TEXT,
                    actor TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    latency_ms INTEGER,
                    status TEXT NOT NULL,
                    payload_json TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_model_routes_tenant_task ON model_routes(tenant_id, task_type, modality, enabled, priority)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_model_invocations_tenant_task ON model_invocations(tenant_id, task_type, created_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_defaults(self) -> None:
        conn = self._connect()
        now = time.time()
        try:
            for model in DEFAULT_MODELS:
                model_id = f"mdl-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO model_registry (
                        id, tenant_id, provider, model_name, modality,
                        status, cost_tier, latency_class, metadata_json,
                        created_at, updated_at
                    ) VALUES (?, 'default', ?, ?, ?, 'ACTIVE', ?, 'balanced', '{}', ?, ?)
                    ON CONFLICT(tenant_id, provider, model_name) DO UPDATE SET
                        status = excluded.status,
                        modality = excluded.modality,
                        cost_tier = excluded.cost_tier,
                        updated_at = excluded.updated_at
                    """,
                    (
                        model_id,
                        model["provider"],
                        model["model_name"],
                        model["modality"],
                        model["cost_tier"],
                        now,
                        now,
                    ),
                )
            # Default routes by modality.
            self._ensure_default_route(conn, now, task_type="scripted_collection_turn", modality="llm", provider="sarvam", model_name="sarvam-m")
            self._ensure_default_route(conn, now, task_type="dispute_handling", modality="llm", provider="sarvam", model_name="sarvam-m")
            self._ensure_default_route(conn, now, task_type="hardship_negotiation", modality="llm", provider="sarvam", model_name="sarvam-m")
            self._ensure_default_route(conn, now, task_type="summarization", modality="llm", provider="sarvam", model_name="sarvam-m")
            self._ensure_default_route(conn, now, task_type="qa_scoring", modality="llm", provider="sarvam", model_name="sarvam-m")
            self._ensure_default_route(conn, now, task_type="realtime_transcription", modality="stt", provider="sarvam", model_name="saarika-v2")
            self._ensure_default_route(conn, now, task_type="voice_rendering", modality="tts", provider="sarvam", model_name="bulbul-v2")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _ensure_default_route(
        conn: sqlite3.Connection,
        now: float,
        *,
        task_type: str,
        modality: str,
        provider: str,
        model_name: str,
    ) -> None:
        row = conn.execute(
            """
            SELECT id
            FROM model_routes
            WHERE tenant_id = 'default' AND task_type = ? AND modality = ? AND priority = 1
            """,
            (task_type, modality),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO model_routes (
                    id, tenant_id, task_type, modality, provider, model_name,
                    priority, policy_version, constraints_json, enabled,
                    created_at, updated_at
                ) VALUES (?, 'default', ?, ?, ?, ?, 1, 'v1', '{}', 1, ?, ?)
                """,
                (
                    f"mrt-{uuid.uuid4().hex[:12]}",
                    task_type,
                    modality,
                    provider,
                    model_name,
                    now,
                    now,
                ),
            )

    def route(
        self,
        *,
        tenant_id: str,
        task_type: str,
        modality: str,
        policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        tid = tenant_id or "default"
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM model_routes
                WHERE tenant_id IN (?, 'default')
                  AND task_type = ?
                  AND modality = ?
                  AND enabled = 1
                ORDER BY CASE WHEN tenant_id = ? THEN 0 ELSE 1 END ASC, priority ASC, updated_at DESC
                """,
                (tid, task_type, modality, tid),
            ).fetchall()
            selected = rows[0] if rows else None
            if selected is None:
                # Fallback to any model in registry by modality.
                fallback = conn.execute(
                    """
                    SELECT provider, model_name
                    FROM model_registry
                    WHERE tenant_id IN (?, 'default') AND modality = ? AND status = 'ACTIVE'
                    ORDER BY CASE WHEN tenant_id = ? THEN 0 ELSE 1 END ASC, updated_at DESC
                    LIMIT 1
                    """,
                    (tid, modality, tid),
                ).fetchone()
                if fallback is None:
                    raise ValueError("no_model_route_found")
                return {
                    "route_id": None,
                    "tenant_id": tid,
                    "task_type": task_type,
                    "modality": modality,
                    "provider": fallback["provider"],
                    "model_name": fallback["model_name"],
                    "policy_version": None,
                    "constraints": {},
                }
            out = dict(selected)
            out["constraints"] = json.loads(out.pop("constraints_json") or "{}")
            return {
                "route_id": out["id"],
                "tenant_id": out["tenant_id"],
                "task_type": out["task_type"],
                "modality": out["modality"],
                "provider": out["provider"],
                "model_name": out["model_name"],
                "policy_version": out["policy_version"],
                "constraints": out["constraints"],
            }
        finally:
            conn.close()

    def record_invocation(
        self,
        *,
        tenant_id: str,
        task_type: str,
        modality: str,
        provider: str,
        model_name: str,
        route_id: Optional[str],
        request_id: str,
        actor: str,
        status: str,
        latency_ms: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        invocation_id = f"minv-{uuid.uuid4().hex[:12]}"
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO model_invocations (
                    id, tenant_id, task_type, modality, provider, model_name,
                    route_id, request_id, actor, input_tokens, output_tokens,
                    latency_ms, status, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invocation_id,
                    tenant_id,
                    task_type,
                    modality,
                    provider,
                    model_name,
                    route_id,
                    request_id,
                    actor,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    status,
                    json.dumps(payload or {}, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
            return invocation_id
        finally:
            conn.close()

    def list_routes(
        self,
        *,
        tenant_id: str,
        task_type: Optional[str] = None,
        modality: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            where = ["tenant_id = ?"]
            args: List[Any] = [tenant_id]
            if task_type:
                where.append("task_type = ?")
                args.append(task_type)
            if modality:
                where.append("modality = ?")
                args.append(modality)
            rows = conn.execute(
                f"SELECT * FROM model_routes WHERE {' AND '.join(where)} ORDER BY task_type, priority ASC",
                tuple(args),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["constraints"] = json.loads(item.pop("constraints_json") or "{}")
                out.append(item)
            return out
        finally:
            conn.close()
