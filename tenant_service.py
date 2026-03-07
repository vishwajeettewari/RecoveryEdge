from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional


class TenantService:
    _TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}$")

    _OPERATIONAL_TABLES = [
        "events",
        "outcomes",
        "violations",
        "compliance_violations",
        "campaigns",
        "campaign_accounts",
        "campaign_runs",
        "followups",
        "outbound_queue",
        "portfolios",
        "portfolio_uploads",
        "portfolio_columns",
        "portfolio_rows",
        "campaign_launches",
        "portfolio_exclusions",
        "tasks",
        "task_events",
        "alert_rules",
        "alerts",
        "notifications",
        "report_configs",
        "reports",
        "integration_connections",
        "sync_events",
        "sync_conflicts",
        "users",
        "user_sessions",
    ]

    _COMPOUND_INDEXES = {
        "idx_tasks_tenant_campaign_customer": ("tasks", "tenant_id, campaign_id, customer_id"),
        "idx_tasks_tenant_state": ("tasks", "tenant_id, state"),
        "idx_reports_tenant_campaign_date": ("reports", "tenant_id, campaign_id, report_date"),
        "idx_outcomes_tenant_campaign": ("outcomes", "tenant_id, campaign_id"),
        "idx_events_tenant_session": ("events", "tenant_id, session_id"),
        "idx_followups_tenant_status_ts": ("followups", "tenant_id, status, scheduled_ts"),
        "idx_sync_events_tenant_entity": ("sync_events", "tenant_id, entity_type, entity_id"),
        "idx_alerts_tenant_status": ("alerts", "tenant_id, status"),
    }

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()
        self._migrate_operational_tables()
        self._seed_default_tenant()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(r["name"]) == column for r in rows)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    created_by TEXT,
                    metadata_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tenant_settings (
                    tenant_id TEXT PRIMARY KEY,
                    settings_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    updated_by TEXT
                )
                """
            )

            # Immutable evidence tables.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS consent_artifacts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    customer_id TEXT,
                    session_id TEXT,
                    channel TEXT,
                    consent_status TEXT NOT NULL,
                    artifact_json TEXT,
                    captured_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS communication_artifacts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    customer_id TEXT,
                    journey_id TEXT,
                    channel TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    content_hash TEXT,
                    payload_json TEXT,
                    captured_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS policy_decisions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    session_id TEXT,
                    decision_type TEXT NOT NULL,
                    policy_version TEXT,
                    actor TEXT,
                    request_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS redaction_audit (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_id TEXT,
                    redaction_type TEXT NOT NULL,
                    actor TEXT,
                    request_id TEXT,
                    payload_json TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _migrate_operational_tables(self) -> None:
        conn = self._connect()
        try:
            for table in self._OPERATIONAL_TABLES:
                if not self._table_exists(conn, table):
                    continue
                if not self._column_exists(conn, table, "tenant_id"):
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'"
                    )
                conn.execute(
                    f"UPDATE {table} SET tenant_id = 'default' WHERE tenant_id IS NULL OR TRIM(tenant_id) = ''"
                )
                idx_name = f"idx_{table}_tenant_id"
                conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}(tenant_id)")

            for idx_name, (table, cols) in self._COMPOUND_INDEXES.items():
                if self._table_exists(conn, table):
                    conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({cols})")

            conn.commit()
        finally:
            conn.close()

    def _seed_default_tenant(self) -> None:
        now = time.time()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT tenant_id FROM tenants WHERE tenant_id = 'default'"
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO tenants (tenant_id, name, status, created_at, updated_at, created_by, metadata_json)
                    VALUES ('default', 'Default Tenant', 'active', ?, ?, ?, ?)
                    """,
                    (now, now, "system", json.dumps({}, ensure_ascii=False)),
                )
                conn.execute(
                    """
                    INSERT INTO tenant_settings (tenant_id, settings_json, updated_at, updated_by)
                    VALUES ('default', ?, ?, ?)
                    """,
                    (json.dumps(self.default_settings(), ensure_ascii=False), now, "system"),
                )
                conn.commit()
        finally:
            conn.close()

    @staticmethod
    def validate_tenant_id(tenant_id: str) -> str:
        tid = (tenant_id or "").strip().lower()
        if tid == "default":
            return tid
        if not tid or not TenantService._TENANT_RE.match(tid):
            raise ValueError("invalid_tenant_id")
        return tid

    @staticmethod
    def default_settings() -> Dict[str, Any]:
        return {
            "timezone": "Asia/Kolkata",
            "country": "IN",
            "currency": "INR",
            "channels": {
                "voice": True,
                "whatsapp": True,
                "sms": True,
                "email": True,
            },
            "approval_thresholds": {
                "settlement_amount_gt": 10000,
                "dpd_gt": 90,
            },
            "security": {
                "pii_redaction": True,
                "audit_immutable": True,
            },
        }

    def ensure_tenant(self, tenant_id: str) -> str:
        tid = self.validate_tenant_id(tenant_id)
        if tid == "default":
            return tid
        row = self.get_tenant(tid)
        if not row:
            raise ValueError("tenant_not_found")
        return tid

    def list_tenants(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT t.tenant_id, t.name, t.status, t.created_at, t.updated_at, t.created_by, t.metadata_json,
                       s.settings_json
                FROM tenants t
                LEFT JOIN tenant_settings s ON s.tenant_id = t.tenant_id
                ORDER BY t.tenant_id
                """
            ).fetchall()
            out = []
            for r in rows:
                out.append(
                    {
                        "tenant_id": r["tenant_id"],
                        "name": r["name"],
                        "status": r["status"],
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "created_by": r["created_by"],
                        "metadata": json.loads(r["metadata_json"] or "{}"),
                        "settings": json.loads(r["settings_json"] or "{}"),
                    }
                )
            return out
        finally:
            conn.close()

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        tid = self.validate_tenant_id(tenant_id)
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT t.tenant_id, t.name, t.status, t.created_at, t.updated_at, t.created_by, t.metadata_json,
                       s.settings_json
                FROM tenants t
                LEFT JOIN tenant_settings s ON s.tenant_id = t.tenant_id
                WHERE t.tenant_id = ?
                """,
                (tid,),
            ).fetchone()
            if row is None:
                return None
            return {
                "tenant_id": row["tenant_id"],
                "name": row["name"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "created_by": row["created_by"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "settings": json.loads(row["settings_json"] or "{}"),
            }
        finally:
            conn.close()

    def create_tenant(
        self,
        *,
        tenant_id: str,
        name: str,
        actor: str,
        request_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        tid = self.validate_tenant_id(tenant_id)
        now = time.time()
        meta = metadata or {}
        cfg = self.default_settings()
        if settings:
            cfg.update(settings)
        conn = self._connect()
        try:
            exists = conn.execute(
                "SELECT tenant_id FROM tenants WHERE tenant_id = ?",
                (tid,),
            ).fetchone()
            if exists is not None:
                raise ValueError("tenant_exists")
            conn.execute(
                """
                INSERT INTO tenants (tenant_id, name, status, created_at, updated_at, created_by, metadata_json)
                VALUES (?, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    tid,
                    (name or tid).strip() or tid,
                    now,
                    now,
                    actor,
                    json.dumps(meta, ensure_ascii=False),
                ),
            )
            conn.execute(
                """
                INSERT INTO tenant_settings (tenant_id, settings_json, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
                """,
                (tid, json.dumps(cfg, ensure_ascii=False), now, actor),
            )
            conn.execute(
                """
                INSERT INTO policy_decisions (id, tenant_id, session_id, decision_type, policy_version, actor, request_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"pdec-{tid}-{int(now * 1000)}",
                    tid,
                    None,
                    "tenant_created",
                    "v1",
                    actor,
                    request_id,
                    json.dumps({"name": name, "metadata": meta}, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_tenant(tid) or {}

    def patch_tenant_settings(
        self,
        *,
        tenant_id: str,
        actor: str,
        request_id: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        tid = self.ensure_tenant(tenant_id)
        now = time.time()
        current = self.get_tenant(tid) or {}
        settings = current.get("settings") if isinstance(current.get("settings"), dict) else {}
        merged = dict(settings or {})
        merged.update(patch or {})
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO tenant_settings (tenant_id, settings_json, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE
                SET settings_json = excluded.settings_json,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (tid, json.dumps(merged, ensure_ascii=False), now, actor),
            )
            conn.execute(
                "UPDATE tenants SET updated_at = ? WHERE tenant_id = ?",
                (now, tid),
            )
            conn.execute(
                """
                INSERT INTO policy_decisions (id, tenant_id, session_id, decision_type, policy_version, actor, request_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"pdec-{tid}-{int(now * 1000)}",
                    tid,
                    None,
                    "tenant_settings_updated",
                    "v1",
                    actor,
                    request_id,
                    json.dumps({"patch": patch}, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_tenant(tid) or {}
