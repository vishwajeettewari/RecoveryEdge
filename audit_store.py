from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class SQLiteAuditStore:
    def __init__(self, path: str, retention_days: int = 30, metrics_tz: str = "Asia/Kolkata") -> None:
        self.path = path
        self.retention_days = max(1, int(retention_days))
        self.metrics_tz = metrics_tz or "Asia/Kolkata"
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._init_db()
        self._migrate_db()
        self._purge_old()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    session_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outcomes (
                    session_id TEXT PRIMARY KEY,
                    start_ts REAL,
                    end_ts REAL,
                    customer_id TEXT,
                    campaign_id TEXT,
                    dpd_bucket TEXT,
                    strategy_mode TEXT,
                    tone_profile TEXT,
                    disposition TEXT,
                    ptp_date TEXT,
                    callback_time TEXT,
                    escalations INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    session_id TEXT,
                    kind TEXT NOT NULL,
                    detail TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compliance_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    session_id TEXT,
                    rule_code TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    detail TEXT,
                    excerpt TEXT,
                    resolved INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    retry_delay_minutes INTEGER NOT NULL,
                    batch_size INTEGER NOT NULL,
                    created_ts REAL NOT NULL,
                    updated_ts REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_accounts (
                    campaign_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_ts REAL,
                    updated_ts REAL NOT NULL,
                    PRIMARY KEY (campaign_id, customer_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    ts REAL NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    outcome TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS followups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    session_id TEXT NOT NULL,
                    customer_id TEXT,
                    reminder_type TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    phone TEXT,
                    scheduled_ts REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    updated_ts REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbound_queue (
                    queue_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_ts REAL,
                    created_ts REAL NOT NULL,
                    updated_ts REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    email TEXT,
                    role TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    default_tenant_id TEXT NOT NULL DEFAULT 'default',
                    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL,
                    must_change_password INTEGER NOT NULL DEFAULT 0,
                    password_changed_at REAL,
                    created_at REAL NOT NULL,
                    last_login_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    refresh_token_hash TEXT NOT NULL,
                    access_jti TEXT,
                    user_agent TEXT,
                    ip_addr TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    last_seen_at REAL,
                    revoked_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_tenant_memberships (
                    user_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    created_by TEXT,
                    PRIMARY KEY (user_id, tenant_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_events (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    external_event_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    received_at REAL NOT NULL,
                    UNIQUE(provider, external_event_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_idempotency (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_key TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    body_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(route_key, idempotency_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    consumed_at REAL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_hash ON user_sessions(refresh_token_hash)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_tenant_memberships_user ON user_tenant_memberships(user_id, is_default)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_idempotency_route_key ON api_idempotency(route_key, expires_at)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id, expires_at)")
            # ── Post-call summaries ──────────────────────────────────────
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS call_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    customer_id TEXT,
                    generated_ts REAL,
                    key_facts TEXT,
                    objections TEXT,
                    commitment TEXT,
                    next_step TEXT,
                    compliance_notes TEXT,
                    sentiment TEXT,
                    disposition TEXT,
                    raw_summary TEXT,
                    search_text TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_summaries_customer ON call_summaries(customer_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_summaries_ts ON call_summaries(generated_ts DESC)"
            )
            # ── DPD roll-forward snapshots ───────────────────────────────
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dpd_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    snapshot_ts REAL NOT NULL,
                    dpd_bucket TEXT,
                    dpd_value INTEGER,
                    source TEXT DEFAULT 'call'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dpd_snap_cust ON dpd_snapshots(customer_id, snapshot_ts)"
            )
            conn.commit()
        finally:
            conn.close()

    def _migrate_db(self) -> None:
        conn = self._connect()
        try:
            cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(outcomes)").fetchall()
            }
            if "campaign_id" not in cols:
                conn.execute("ALTER TABLE outcomes ADD COLUMN campaign_id TEXT")
            if "dpd_bucket" not in cols:
                conn.execute("ALTER TABLE outcomes ADD COLUMN dpd_bucket TEXT")
            if "strategy_mode" not in cols:
                conn.execute("ALTER TABLE outcomes ADD COLUMN strategy_mode TEXT")
            if "tone_profile" not in cols:
                conn.execute("ALTER TABLE outcomes ADD COLUMN tone_profile TEXT")
            if "agent_id" not in cols:
                conn.execute("ALTER TABLE outcomes ADD COLUMN agent_id TEXT")
            if "connect_duration_s" not in cols:
                conn.execute("ALTER TABLE outcomes ADD COLUMN connect_duration_s REAL")

            user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "default_tenant_id" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN default_tenant_id TEXT NOT NULL DEFAULT 'default'")
            if "failed_login_attempts" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
            if "locked_until" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN locked_until REAL")
            if "must_change_password" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
            if "password_changed_at" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN password_changed_at REAL")

            sess_cols = {r["name"] for r in conn.execute("PRAGMA table_info(user_sessions)").fetchall()}
            if "tenant_id" not in sess_cols:
                conn.execute("ALTER TABLE user_sessions ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
            if "refresh_token_hash" not in sess_cols:
                conn.execute("ALTER TABLE user_sessions ADD COLUMN refresh_token_hash TEXT")
                conn.execute(
                    "UPDATE user_sessions SET refresh_token_hash = ? WHERE refresh_token_hash IS NULL OR TRIM(refresh_token_hash) = ''",
                    (self.hash_token("legacy-session"),),
                )
            if "access_jti" not in sess_cols:
                conn.execute("ALTER TABLE user_sessions ADD COLUMN access_jti TEXT")
            if "user_agent" not in sess_cols:
                conn.execute("ALTER TABLE user_sessions ADD COLUMN user_agent TEXT")
            if "ip_addr" not in sess_cols:
                conn.execute("ALTER TABLE user_sessions ADD COLUMN ip_addr TEXT")
            if "last_seen_at" not in sess_cols:
                conn.execute("ALTER TABLE user_sessions ADD COLUMN last_seen_at REAL")
            if "revoked_at" not in sess_cols:
                conn.execute("ALTER TABLE user_sessions ADD COLUMN revoked_at REAL")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_tenant_memberships (
                    user_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    created_by TEXT,
                    PRIMARY KEY (user_id, tenant_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_events (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    external_event_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    received_at REAL NOT NULL,
                    UNIQUE(provider, external_event_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_idempotency (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_key TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    body_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(route_key, idempotency_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    consumed_at REAL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_hash ON user_sessions(refresh_token_hash)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_tenant_memberships_user ON user_tenant_memberships(user_id, is_default)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_idempotency_route_key ON api_idempotency(route_key, expires_at)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id, expires_at)")
            conn.commit()
        finally:
            conn.close()

    def _purge_old(self) -> None:
        cutoff = time.time() - (self.retention_days * 86400)
        conn = self._connect()
        try:
            conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            conn.execute("DELETE FROM violations WHERE ts < ?", (cutoff,))
            conn.execute("DELETE FROM compliance_violations WHERE ts < ?", (cutoff,))
            conn.execute(
                """
                DELETE FROM outcomes
                WHERE COALESCE(end_ts, start_ts, 0) > 0
                  AND COALESCE(end_ts, start_ts, 0) < ?
                """,
                (cutoff,),
            )
            conn.commit()
        finally:
            conn.close()

    def record_event(self, *, event_type: str, payload: Dict[str, Any], session_id: Optional[str] = None, ts: Optional[float] = None) -> None:
        ts = float(ts if ts is not None else time.time())
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO events (ts, session_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
                (ts, session_id, event_type, json.dumps(payload, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_outcome(
        self,
        *,
        session_id: str,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        customer_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        dpd_bucket: Optional[str] = None,
        strategy_mode: Optional[str] = None,
        tone_profile: Optional[str] = None,
        disposition: Optional[str] = None,
        ptp_date: Optional[str] = None,
        callback_time: Optional[str] = None,
        escalations_inc: int = 0,
    ) -> None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM outcomes WHERE session_id = ?", (session_id,)).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO outcomes (
                        session_id, start_ts, end_ts, customer_id, campaign_id, dpd_bucket,
                        strategy_mode, tone_profile, disposition, ptp_date, callback_time, escalations
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        start_ts,
                        end_ts,
                        customer_id,
                        campaign_id,
                        dpd_bucket,
                        strategy_mode,
                        tone_profile,
                        disposition,
                        ptp_date,
                        callback_time,
                        max(0, int(escalations_inc)),
                    ),
                )
            else:
                escalations = int(row["escalations"] or 0) + max(0, int(escalations_inc))
                conn.execute(
                    """
                    UPDATE outcomes
                    SET start_ts = COALESCE(?, start_ts),
                        end_ts = COALESCE(?, end_ts),
                        customer_id = COALESCE(?, customer_id),
                        campaign_id = COALESCE(?, campaign_id),
                        dpd_bucket = COALESCE(?, dpd_bucket),
                        strategy_mode = COALESCE(?, strategy_mode),
                        tone_profile = COALESCE(?, tone_profile),
                        disposition = COALESCE(?, disposition),
                        ptp_date = COALESCE(?, ptp_date),
                        callback_time = COALESCE(?, callback_time),
                        escalations = ?
                    WHERE session_id = ?
                    """,
                    (
                        start_ts,
                        end_ts,
                        customer_id,
                        campaign_id,
                        dpd_bucket,
                        strategy_mode,
                        tone_profile,
                        disposition,
                        ptp_date,
                        callback_time,
                        escalations,
                        session_id,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def record_violation(self, *, session_id: str, kind: str, detail: Optional[str] = None) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO violations (ts, session_id, kind, detail) VALUES (?, ?, ?, ?)",
                (time.time(), session_id, kind, detail),
            )
            conn.commit()
        finally:
            conn.close()

    def record_compliance_violation(
        self,
        *,
        session_id: str,
        rule_code: str,
        severity: str,
        detail: str,
        excerpt: str,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO compliance_violations (ts, session_id, rule_code, severity, detail, excerpt, resolved)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (time.time(), session_id, rule_code, severity, detail, excerpt),
            )
            conn.commit()
        finally:
            conn.close()

    def list_compliance_violations(
        self,
        *,
        severity: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            sql = "SELECT * FROM compliance_violations WHERE 1=1"
            args: List[Any] = []
            if severity:
                sql += " AND severity = ?"
                args.append(severity)
            if session_id:
                sql += " AND session_id = ?"
                args.append(session_id)
            sql += " ORDER BY ts DESC LIMIT ?"
            args.append(max(1, int(limit)))
            rows = conn.execute(sql, tuple(args)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def metrics(self, *, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            tz = ZoneInfo(self.metrics_tz)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        day_start = datetime(now.year, now.month, now.day, tzinfo=tz).timestamp()
        day_end = day_start + 86400
        now_ts = time.time()
        conn = self._connect()
        try:
            where = ""
            args: List[Any] = []
            if campaign_id:
                where = " WHERE campaign_id = ?"
                args = [campaign_id]

            def safe_row(sql: str, params: tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
                try:
                    return conn.execute(sql, params).fetchone()
                except Exception:
                    return None

            def safe_rows(sql: str, params: tuple[Any, ...] = ()) -> List[sqlite3.Row]:
                try:
                    return conn.execute(sql, params).fetchall()
                except Exception:
                    return []

            def safe_number(sql: str, params: tuple[Any, ...] = (), key: str = "n", default: float = 0.0) -> float:
                row = safe_row(sql, params)
                if not row:
                    return default
                try:
                    value = row[key]
                except Exception:
                    try:
                        value = row[0]
                    except Exception:
                        return default
                if value is None:
                    return default
                try:
                    return float(value)
                except Exception:
                    return default

            if campaign_id:
                sessions_today = safe_number(
                    """
                    SELECT COUNT(DISTINCT e.session_id) AS n
                    FROM events e
                    JOIN outcomes o ON o.session_id = e.session_id
                    WHERE e.ts >= ? AND o.campaign_id = ?
                    """,
                    (day_start, campaign_id),
                )
            else:
                sessions_today = safe_number(
                    "SELECT COUNT(DISTINCT session_id) AS n FROM events WHERE ts >= ?",
                    (day_start,),
                )

            ptp_count = safe_number(
                f"SELECT COUNT(*) AS n FROM outcomes{where + (' AND' if where else ' WHERE')} ptp_date IS NOT NULL AND ptp_date != ''",
                tuple(args),
            )
            callback_count = safe_number(
                f"SELECT COUNT(*) AS n FROM outcomes{where + (' AND' if where else ' WHERE')} callback_time IS NOT NULL AND callback_time != ''",
                tuple(args),
            )
            escalations = safe_number(
                f"SELECT COALESCE(SUM(escalations), 0) AS n FROM outcomes{where}",
                tuple(args),
            )
            ended = safe_number(
                f"SELECT COUNT(*) AS n FROM outcomes{where + (' AND' if where else ' WHERE')} end_ts IS NOT NULL",
                tuple(args),
            )
            avg_handle_s = safe_number(
                f"SELECT AVG(end_ts - start_ts) AS v FROM outcomes{where + (' AND' if where else ' WHERE')} start_ts IS NOT NULL AND end_ts IS NOT NULL",
                tuple(args),
                key="v",
                default=0.0,
            )

            assigned = safe_number(
                "SELECT COUNT(*) AS n FROM campaign_accounts" + (" WHERE campaign_id = ?" if campaign_id else ""),
                tuple([campaign_id] if campaign_id else []),
            )
            contacted = safe_number(
                "SELECT COUNT(DISTINCT customer_id) AS n FROM campaign_runs" + (" WHERE campaign_id = ?" if campaign_id else ""),
                tuple([campaign_id] if campaign_id else []),
            )
            retries_pending = safe_number(
                "SELECT COUNT(*) AS n FROM campaign_accounts WHERE state = 'retry_scheduled'" + (" AND campaign_id = ?" if campaign_id else ""),
                tuple([campaign_id] if campaign_id else []),
            )

            task_where = " WHERE 1=1"
            task_args: List[Any] = []
            if campaign_id:
                task_where += " AND campaign_id = ?"
                task_args.append(campaign_id)

            bucket_row = safe_row(
                """
                SELECT
                    SUM(CASE WHEN dpd BETWEEN 1 AND 30 THEN 1 ELSE 0 END) AS b1,
                    SUM(CASE WHEN dpd BETWEEN 31 AND 60 THEN 1 ELSE 0 END) AS b2,
                    SUM(CASE WHEN dpd BETWEEN 61 AND 90 THEN 1 ELSE 0 END) AS b3,
                    SUM(CASE WHEN dpd > 90 THEN 1 ELSE 0 END) AS b4
                FROM tasks
                """
                + task_where,
                tuple(task_args),
            )
            bucket_heatmap = {
                "1-30": int((bucket_row["b1"] if bucket_row else 0) or 0),
                "31-60": int((bucket_row["b2"] if bucket_row else 0) or 0),
                "61-90": int((bucket_row["b3"] if bucket_row else 0) or 0),
                "90+": int((bucket_row["b4"] if bucket_row else 0) or 0),
            }

            expected_recovery_amount = safe_number(
                "SELECT COALESCE(SUM(amount_due), 0) AS v FROM tasks" + task_where + " AND state = 'PTP'",
                tuple(task_args),
                key="v",
            )
            sla_breaches = safe_number(
                "SELECT COUNT(*) AS n FROM tasks" + task_where + " AND state != 'CLOSED' AND COALESCE(sla_due_at, 0) > 0 AND sla_due_at < ?",
                tuple(task_args + [now_ts]) if campaign_id else (now_ts,),
            )

            queue_rows = safe_rows(
                "SELECT state, COUNT(*) AS n FROM tasks" + task_where + " GROUP BY state",
                tuple(task_args),
            )
            queue_snapshot = {state: 0 for state in ("NEW", "IN_PROGRESS", "PTP", "CALLBACK", "ESCALATED", "CLOSED")}
            for r in queue_rows:
                queue_snapshot[str(r["state"] or "NEW")] = int(r["n"] or 0)

            by_bucket_rows = safe_rows(
                """
                SELECT COALESCE(dpd_bucket, 'unknown') AS bucket,
                       COUNT(*) AS total,
                       SUM(CASE WHEN ptp_date IS NOT NULL AND ptp_date != '' THEN 1 ELSE 0 END) AS ptp
                FROM outcomes
                """
                + where
                + """
                GROUP BY COALESCE(dpd_bucket, 'unknown')
                """,
                tuple(args),
            )
            ptp_rate_by_bucket = {
                str(r["bucket"] or "unknown"): {
                    "total": int(r["total"] or 0),
                    "ptp": int(r["ptp"] or 0),
                    "rate": round((int(r["ptp"] or 0) / int(r["total"] or 1)) * 100.0, 2),
                }
                for r in by_bucket_rows
            }

            conversion_rows = safe_rows(
                """
                SELECT campaign_id,
                       COUNT(*) AS total,
                       SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) AS completed
                FROM campaign_accounts
                """
                + (" WHERE campaign_id = ?" if campaign_id else "")
                + """
                GROUP BY campaign_id
                """,
                tuple([campaign_id] if campaign_id else []),
            )
            conversion_by_campaign = {
                str(r["campaign_id"] or ""): {
                    "total": int(r["total"] or 0),
                    "completed": int(r["completed"] or 0),
                    "rate": round((int(r["completed"] or 0) / int(r["total"] or 1)) * 100.0, 2),
                }
                for r in conversion_rows
                if r["campaign_id"]
            }

            escalation_rows = safe_rows(
                """
                SELECT json_extract(e.payload_json, '$.reason') AS reason, COUNT(*) AS n
                FROM events e
                JOIN outcomes o ON o.session_id = e.session_id
                WHERE e.event_type = 'action'
                  AND json_extract(e.payload_json, '$.name') = 'escalate_ticket'
                """
                + (" AND o.campaign_id = ?" if campaign_id else "")
                + """
                GROUP BY json_extract(e.payload_json, '$.reason')
                """,
                tuple([campaign_id] if campaign_id else []),
            )
            escalations_by_reason = {str(r["reason"] or "unknown"): int(r["n"] or 0) for r in escalation_rows}

            followup_from = "FROM followups f"
            followup_filters: List[str] = []
            followup_args: List[Any] = []
            if campaign_id:
                followup_from += " JOIN outcomes o ON o.session_id = f.session_id"
                followup_filters.append("o.campaign_id = ?")
                followup_args.append(campaign_id)

            def followup_count(*, extra_filters: List[str], extra_args: List[Any]) -> int:
                filters = followup_filters + extra_filters
                where_sql = f" WHERE {' AND '.join(filters)}" if filters else ""
                return int(
                    safe_number(
                        f"SELECT COUNT(*) AS n {followup_from}{where_sql}",
                        tuple(followup_args + extra_args),
                    )
                    or 0
                )

            followups_scheduled_total = followup_count(extra_filters=[], extra_args=[])
            followups_pending_total = followup_count(extra_filters=["f.status = 'scheduled'"], extra_args=[])
            followups_sent_total = followup_count(extra_filters=["f.status = 'sent'"], extra_args=[])
            followups_missed_total = followup_count(extra_filters=["f.status = 'missed'"], extra_args=[])
            followups_due_today = followup_count(
                extra_filters=["f.scheduled_ts >= ?", "f.scheduled_ts < ?"],
                extra_args=[day_start, day_end],
            )
            followups_completed_today = followup_count(
                extra_filters=["f.scheduled_ts >= ?", "f.scheduled_ts < ?", "f.status IN ('sent', 'missed')"],
                extra_args=[day_start, day_end],
            )
            ptp_miss_count = followup_count(
                extra_filters=["f.reminder_type = 'ptp_t_plus_1_miss'", "f.status IN ('sent', 'missed')"],
                extra_args=[],
            )

            if campaign_id:
                ptp_miss_open_alerts = int(
                    safe_number(
                        """
                        SELECT COUNT(*) AS n
                        FROM alerts a
                        JOIN followups f ON f.idempotency_key = a.entity_id
                        JOIN outcomes o ON o.session_id = f.session_id
                        WHERE a.type = 'PTP_MISS'
                          AND a.status != 'RESOLVED'
                          AND o.campaign_id = ?
                        """,
                        (campaign_id,),
                    )
                    or 0
                )
            else:
                ptp_miss_open_alerts = int(
                    safe_number(
                        "SELECT COUNT(*) AS n FROM alerts WHERE type = 'PTP_MISS' AND status != 'RESOLVED'",
                        (),
                    )
                    or 0
                )

            if campaign_id:
                profanity_incidents = int(
                    safe_number(
                        """
                        SELECT COUNT(*) AS n
                        FROM violations v
                        JOIN outcomes o ON o.session_id = v.session_id
                        WHERE v.kind = 'profanity'
                          AND o.campaign_id = ?
                        """,
                        (campaign_id,),
                    )
                    or 0
                )
            else:
                profanity_incidents = int(
                    safe_number(
                        "SELECT COUNT(*) AS n FROM violations WHERE kind = 'profanity'",
                        (),
                    )
                    or 0
                )

            contact_rate_pct = round((float(contacted or 0) / max(1.0, float(assigned or 0))) * 100.0, 2) if assigned else 0.0
            followup_discipline_rate_pct = (
                round((followups_completed_today / max(1, followups_due_today)) * 100.0, 2) if followups_due_today else 0.0
            )

            return {
                "sessions_today": int(sessions_today or 0),
                "ptp_count": int(ptp_count or 0),
                "callback_count": int(callback_count or 0),
                "escalations": int(escalations or 0),
                "ended_sessions": int(ended or 0),
                "avg_handle_seconds": float(avg_handle_s) if avg_handle_s else None,
                "accounts_assigned": int(assigned or 0),
                "accounts_contacted": int(contacted or 0),
                "contact_rate_pct": contact_rate_pct,
                "retries_pending": int(retries_pending or 0),
                "bucket_heatmap": bucket_heatmap,
                "expected_recovery_amount": float(expected_recovery_amount or 0.0),
                "sla_breaches": int(sla_breaches or 0),
                "queue_snapshot": queue_snapshot,
                "ptp_rate_by_bucket": ptp_rate_by_bucket,
                "conversion_by_campaign": conversion_by_campaign,
                "escalations_by_reason": escalations_by_reason,
                "followups_scheduled_total": followups_scheduled_total,
                "followups_pending_total": followups_pending_total,
                "followups_sent_total": followups_sent_total,
                "followups_missed_total": followups_missed_total,
                "followups_due_today": followups_due_today,
                "followups_completed_today": followups_completed_today,
                "followup_discipline_rate_pct": followup_discipline_rate_pct,
                "ptp_miss_count": ptp_miss_count,
                "ptp_miss_open_alerts": ptp_miss_open_alerts,
                "profanity_incidents": profanity_incidents,
            }
        finally:
            conn.close()

    def recent_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT session_id, start_ts, end_ts, customer_id, campaign_id, dpd_bucket, disposition, ptp_date, callback_time, escalations
                FROM outcomes
                ORDER BY COALESCE(end_ts, start_ts, 0) DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def session_timeline(self, session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            events = conn.execute(
                """
                SELECT ts, event_type, payload_json
                FROM events
                WHERE session_id = ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (session_id, max(1, int(limit))),
            ).fetchall()
            violations = conn.execute(
                """
                SELECT ts, rule_code, severity, detail, excerpt
                FROM compliance_violations
                WHERE session_id = ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (session_id, max(1, int(limit))),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for e in events:
                payload = {}
                try:
                    payload = json.loads(e["payload_json"] or "{}")
                except Exception:
                    payload = {}
                out.append({"ts": e["ts"], "type": e["event_type"], "payload": payload})
            for v in violations:
                out.append(
                    {
                        "ts": v["ts"],
                        "type": "compliance_violation",
                        "payload": {
                            "rule_code": v["rule_code"],
                            "severity": v["severity"],
                            "detail": v["detail"],
                            "excerpt": v["excerpt"],
                        },
                    }
                )
            out.sort(key=lambda x: float(x.get("ts") or 0))
            return out
        finally:
            conn.close()

    # -------------------------
    # User / auth operations
    # -------------------------
    def has_users(self) -> bool:
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            return int(row["n"] or 0) > 0
        finally:
            conn.close()

    def create_user(
        self,
        *,
        user_id: str,
        username: str,
        password_hash: str,
        full_name: Optional[str],
        email: Optional[str],
        role: str,
        is_active: bool = True,
        default_tenant_id: str = "default",
        must_change_password: bool = False,
        actor: Optional[str] = None,
    ) -> None:
        now = time.time()
        default_tid = (default_tenant_id or "default").strip().lower() or "default"
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO users (
                    id, username, password_hash, full_name, email, role, is_active,
                    default_tenant_id, failed_login_attempts, locked_until,
                    must_change_password, password_changed_at, created_at, last_login_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?, NULL)
                """,
                (
                    user_id,
                    username.strip().lower(),
                    password_hash,
                    full_name,
                    email,
                    role.strip().upper(),
                    1 if is_active else 0,
                    default_tid,
                    1 if must_change_password else 0,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO user_tenant_memberships (user_id, tenant_id, is_default, created_at, created_by)
                VALUES (?, ?, 1, ?, ?)
                """,
                (user_id, default_tid, now, actor or "system"),
            )
            conn.commit()
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_users(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    id, username, full_name, email, role, is_active, default_tenant_id,
                    failed_login_attempts, locked_until, must_change_password,
                    password_changed_at, created_at, last_login_at
                FROM users
                ORDER BY created_at ASC
                """
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_user(
        self,
        *,
        user_id: str,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        full_name: Optional[str] = None,
        email: Optional[str] = None,
        default_tenant_id: Optional[str] = None,
        must_change_password: Optional[bool] = None,
    ) -> bool:
        updates: List[str] = []
        args: List[Any] = []
        if role is not None:
            updates.append("role = ?")
            args.append(role.strip().upper())
        if is_active is not None:
            updates.append("is_active = ?")
            args.append(1 if is_active else 0)
        if full_name is not None:
            updates.append("full_name = ?")
            args.append(full_name)
        if email is not None:
            updates.append("email = ?")
            args.append(email)
        if default_tenant_id is not None:
            updates.append("default_tenant_id = ?")
            args.append((default_tenant_id or "default").strip().lower() or "default")
        if must_change_password is not None:
            updates.append("must_change_password = ?")
            args.append(1 if must_change_password else 0)
        if not updates:
            return False
        args.append(user_id)
        conn = self._connect()
        try:
            cur = conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                tuple(args),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def set_user_password(self, *, user_id: str, password_hash: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                UPDATE users
                SET password_hash = ?,
                    password_changed_at = ?,
                    must_change_password = 0
                WHERE id = ?
                """,
                (password_hash, time.time(), user_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def mark_user_login(self, *, user_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE users
                SET last_login_at = ?,
                    failed_login_attempts = 0,
                    locked_until = NULL
                WHERE id = ?
                """,
                (time.time(), user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_login_failure(self, *, user_id: str, threshold: int = 5, lock_seconds: int = 900) -> Dict[str, Any]:
        conn = self._connect()
        now = time.time()
        try:
            row = conn.execute(
                "SELECT failed_login_attempts, locked_until FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                return {"failed_login_attempts": 0, "locked_until": None, "locked": False}
            attempts = int(row["failed_login_attempts"] or 0) + 1
            locked_until: Optional[float] = None
            if attempts >= max(1, int(threshold)):
                locked_until = now + max(1, int(lock_seconds))
                attempts = 0
            conn.execute(
                "UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?",
                (attempts, locked_until, user_id),
            )
            conn.commit()
            return {
                "failed_login_attempts": attempts,
                "locked_until": locked_until,
                "locked": bool(locked_until and locked_until > now),
            }
        finally:
            conn.close()

    def is_user_locked(self, *, user_id: str) -> bool:
        conn = self._connect()
        now = time.time()
        try:
            row = conn.execute("SELECT locked_until FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                return False
            locked_until = row["locked_until"]
            return bool(locked_until and float(locked_until) > now)
        finally:
            conn.close()

    def add_user_tenant_membership(
        self,
        *,
        user_id: str,
        tenant_id: str,
        is_default: bool = False,
        actor: str = "system",
    ) -> None:
        tid = (tenant_id or "default").strip().lower() or "default"
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO user_tenant_memberships (user_id, tenant_id, is_default, created_at, created_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, tid, 1 if is_default else 0, now, actor),
            )
            if is_default:
                conn.execute("UPDATE users SET default_tenant_id = ? WHERE id = ?", (tid, user_id))
                conn.execute(
                    "UPDATE user_tenant_memberships SET is_default = CASE WHEN tenant_id = ? THEN 1 ELSE 0 END WHERE user_id = ?",
                    (tid, user_id),
                )
            conn.commit()
        finally:
            conn.close()

    def list_user_tenants(self, *, user_id: str) -> List[str]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT tenant_id FROM user_tenant_memberships WHERE user_id = ? ORDER BY is_default DESC, tenant_id ASC",
                (user_id,),
            ).fetchall()
            return [str(r["tenant_id"]) for r in rows]
        finally:
            conn.close()

    def get_user_default_tenant(self, *, user_id: str) -> str:
        conn = self._connect()
        try:
            row = conn.execute("SELECT default_tenant_id FROM users WHERE id = ?", (user_id,)).fetchone()
            if row and row["default_tenant_id"]:
                return str(row["default_tenant_id"])
            row2 = conn.execute(
                "SELECT tenant_id FROM user_tenant_memberships WHERE user_id = ? AND is_default = 1",
                (user_id,),
            ).fetchone()
            if row2 and row2["tenant_id"]:
                return str(row2["tenant_id"])
            return "default"
        finally:
            conn.close()

    def user_has_tenant(self, *, user_id: str, tenant_id: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM user_tenant_memberships WHERE user_id = ? AND tenant_id = ?",
                (user_id, (tenant_id or "default").strip().lower() or "default"),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256((token or "").encode("utf-8")).hexdigest()

    def create_user_session(
        self,
        *,
        session_id: str,
        user_id: str,
        tenant_id: str,
        refresh_token_hash: str,
        expires_at: float,
        access_jti: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_addr: Optional[str] = None,
    ) -> None:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO user_sessions (
                    id, user_id, tenant_id, refresh_token_hash, access_jti,
                    user_agent, ip_addr, created_at, expires_at, last_seen_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    session_id,
                    user_id,
                    (tenant_id or "default").strip().lower() or "default",
                    refresh_token_hash,
                    access_jti,
                    user_agent,
                    ip_addr,
                    now,
                    expires_at,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_user_session(self, *, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM user_sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_user_session_by_refresh_hash(self, *, refresh_token_hash: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT *
                FROM user_sessions
                WHERE refresh_token_hash = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (refresh_token_hash,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def rotate_user_session(
        self,
        *,
        session_id: str,
        refresh_token_hash: str,
        access_jti: Optional[str],
        expires_at: float,
    ) -> bool:
        now = time.time()
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                UPDATE user_sessions
                SET refresh_token_hash = ?,
                    access_jti = ?,
                    expires_at = ?,
                    last_seen_at = ?
                WHERE id = ?
                  AND revoked_at IS NULL
                """,
                (refresh_token_hash, access_jti, expires_at, now, session_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def list_user_sessions(self, *, user_id: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT id, user_id, tenant_id, user_agent, ip_addr, created_at, expires_at, last_seen_at, revoked_at
                FROM user_sessions
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def revoke_user_session(self, *, session_id: str) -> bool:
        conn = self._connect()
        now = time.time()
        try:
            cur = conn.execute(
                "UPDATE user_sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now, session_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def revoke_user_sessions(self, *, user_id: str) -> int:
        conn = self._connect()
        now = time.time()
        try:
            cur = conn.execute(
                "UPDATE user_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()

    def upsert_idempotency(
        self,
        *,
        route_key: str,
        idempotency_key: str,
        body_hash: str,
        response_json: Dict[str, Any],
        status_code: int,
        window_seconds: int = 86400,
    ) -> Dict[str, Any]:
        now = time.time()
        expires_at = now + max(1, int(window_seconds))
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM api_idempotency WHERE route_key = ? AND idempotency_key = ?",
                (route_key, idempotency_key),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO api_idempotency (route_key, idempotency_key, body_hash, response_json, status_code, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        route_key,
                        idempotency_key,
                        body_hash,
                        json.dumps(response_json, ensure_ascii=False),
                        int(status_code),
                        now,
                        expires_at,
                    ),
                )
                conn.execute("DELETE FROM api_idempotency WHERE expires_at < ?", (now,))
                conn.commit()
                return {"replayed": False, "conflict": False}
            existing = dict(row)
            if float(existing.get("expires_at") or 0) < now:
                conn.execute("DELETE FROM api_idempotency WHERE id = ?", (existing["id"],))
                conn.execute(
                    """
                    INSERT INTO api_idempotency (route_key, idempotency_key, body_hash, response_json, status_code, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        route_key,
                        idempotency_key,
                        body_hash,
                        json.dumps(response_json, ensure_ascii=False),
                        int(status_code),
                        now,
                        expires_at,
                    ),
                )
                conn.commit()
                return {"replayed": False, "conflict": False}
            if str(existing.get("body_hash") or "") != body_hash:
                return {"replayed": False, "conflict": True, "status_code": 409}
            payload = {}
            try:
                payload = json.loads(existing.get("response_json") or "{}")
            except Exception:
                payload = {}
            return {
                "replayed": True,
                "conflict": False,
                "status_code": int(existing.get("status_code") or 200),
                "response_json": payload,
            }
        finally:
            conn.close()

    def get_idempotency(
        self,
        *,
        route_key: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        now = time.time()
        try:
            row = conn.execute(
                """
                SELECT id, route_key, idempotency_key, body_hash, response_json, status_code, created_at, expires_at
                FROM api_idempotency
                WHERE route_key = ? AND idempotency_key = ?
                """,
                (route_key, idempotency_key),
            ).fetchone()
            if row is None:
                return None
            out = dict(row)
            if float(out.get("expires_at") or 0) < now:
                conn.execute("DELETE FROM api_idempotency WHERE id = ?", (out["id"],))
                conn.commit()
                return None
            try:
                out["response_json"] = json.loads(out.get("response_json") or "{}")
            except Exception:
                out["response_json"] = {}
            return out
        finally:
            conn.close()

    def store_idempotency(
        self,
        *,
        route_key: str,
        idempotency_key: str,
        body_hash: str,
        response_json: Dict[str, Any],
        status_code: int,
        window_seconds: int = 86400,
    ) -> None:
        now = time.time()
        expires_at = now + max(1, int(window_seconds))
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO api_idempotency (route_key, idempotency_key, body_hash, response_json, status_code, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(route_key, idempotency_key)
                DO UPDATE SET
                    body_hash = excluded.body_hash,
                    response_json = excluded.response_json,
                    status_code = excluded.status_code,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (
                    route_key,
                    idempotency_key,
                    body_hash,
                    json.dumps(response_json, ensure_ascii=False),
                    int(status_code),
                    now,
                    expires_at,
                ),
            )
            conn.execute("DELETE FROM api_idempotency WHERE expires_at < ?", (now,))
            conn.commit()
        finally:
            conn.close()

    def webhook_seen(
        self,
        *,
        provider: str,
        external_event_id: str,
        request_hash: str,
    ) -> bool:
        conn = self._connect()
        now = time.time()
        try:
            try:
                conn.execute(
                    """
                    INSERT INTO webhook_events (id, provider, external_event_id, request_hash, received_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"whk-{secrets.token_hex(8)}",
                        provider.strip().lower(),
                        external_event_id.strip(),
                        request_hash,
                        now,
                    ),
                )
                conn.commit()
                return False
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT request_hash FROM webhook_events WHERE provider = ? AND external_event_id = ?",
                    (provider.strip().lower(), external_event_id.strip()),
                ).fetchone()
                # Seen before, regardless of payload. Caller can decide strictness.
                return row is not None
        finally:
            conn.close()

    def create_password_reset_token(self, *, user_id: str, ttl_seconds: int = 1800) -> str:
        raw_token = secrets.token_urlsafe(32)
        token_hash = self.hash_token(raw_token)
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("UPDATE password_reset_tokens SET consumed_at = ? WHERE user_id = ? AND consumed_at IS NULL", (now, user_id))
            conn.execute(
                """
                INSERT INTO password_reset_tokens (id, user_id, token_hash, created_at, expires_at, consumed_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (f"prt-{secrets.token_hex(8)}", user_id, token_hash, now, now + max(60, int(ttl_seconds))),
            )
            conn.commit()
            return raw_token
        finally:
            conn.close()

    def consume_password_reset_token(self, *, token: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        token_hash = self.hash_token(token)
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT *
                FROM password_reset_tokens
                WHERE token_hash = ?
                  AND consumed_at IS NULL
                  AND expires_at > ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (token_hash, now),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE password_reset_tokens SET consumed_at = ? WHERE id = ?", (now, row["id"]))
            conn.commit()
            return dict(row)
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Feature: Post-call summaries (Feature 5)
    # ─────────────────────────────────────────────────────────────────────────

    def store_call_summary(
        self,
        *,
        session_id: str,
        customer_id: Optional[str] = None,
        summary: Dict[str, Any],
    ) -> None:
        key_facts = summary.get("key_facts") or []
        objections = summary.get("objections") or []
        compliance_notes = summary.get("compliance_notes") or []
        commitment = str(summary.get("commitment") or "")
        next_step = str(summary.get("next_step") or "")
        sentiment = str(summary.get("sentiment") or "")
        disposition = str(summary.get("disposition") or "")
        raw = str(summary.get("raw") or "")
        search_text = " ".join(filter(None, [
            " ".join(key_facts) if isinstance(key_facts, list) else str(key_facts),
            " ".join(objections) if isinstance(objections, list) else str(objections),
            " ".join(compliance_notes) if isinstance(compliance_notes, list) else str(compliance_notes),
            commitment, next_step, sentiment,
        ]))
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO call_summaries (
                    session_id, customer_id, generated_ts,
                    key_facts, objections, commitment, next_step,
                    compliance_notes, sentiment, disposition, raw_summary, search_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    generated_ts = excluded.generated_ts,
                    key_facts = excluded.key_facts,
                    objections = excluded.objections,
                    commitment = excluded.commitment,
                    next_step = excluded.next_step,
                    compliance_notes = excluded.compliance_notes,
                    sentiment = excluded.sentiment,
                    disposition = excluded.disposition,
                    raw_summary = excluded.raw_summary,
                    search_text = excluded.search_text
                """,
                (
                    session_id, customer_id, time.time(),
                    json.dumps(key_facts, ensure_ascii=False),
                    json.dumps(objections, ensure_ascii=False),
                    commitment, next_step,
                    json.dumps(compliance_notes, ensure_ascii=False),
                    sentiment, disposition, raw, search_text,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_call_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM call_summaries WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                return None
            out = dict(row)
            for field in ("key_facts", "objections", "compliance_notes"):
                try:
                    out[field] = json.loads(out.get(field) or "[]")
                except Exception:
                    out[field] = []
            return out
        finally:
            conn.close()

    def search_summaries(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            q = f"%{(query or '').strip().lower()}%"
            rows = conn.execute(
                """
                SELECT * FROM call_summaries
                WHERE LOWER(COALESCE(search_text,'')) LIKE ?
                   OR LOWER(COALESCE(customer_id,'')) LIKE ?
                   OR LOWER(COALESCE(session_id,'')) LIKE ?
                ORDER BY generated_ts DESC
                LIMIT ?
                """,
                (q, q, q, max(1, min(200, int(limit)))),
            ).fetchall()
            out = []
            for row in rows:
                d = dict(row)
                for field in ("key_facts", "objections", "compliance_notes"):
                    try:
                        d[field] = json.loads(d.get(field) or "[]")
                    except Exception:
                        d[field] = []
                out.append(d)
            return out
        finally:
            conn.close()

    def recent_summaries(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.search_summaries("", limit=limit)

    # ─────────────────────────────────────────────────────────────────────────
    # Feature: DPD roll-forward tracking (Feature 1)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _dpd_to_bucket(dpd: int) -> str:
        if dpd <= 0:
            return "0"
        if dpd <= 30:
            return "1-30"
        if dpd <= 60:
            return "31-60"
        if dpd <= 90:
            return "61-90"
        return "90+"

    def record_dpd_snapshot(
        self,
        *,
        customer_id: str,
        dpd_value: int,
        dpd_bucket: Optional[str] = None,
        source: str = "call",
    ) -> None:
        if not customer_id:
            return
        bucket = dpd_bucket or self._dpd_to_bucket(int(dpd_value or 0))
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO dpd_snapshots (customer_id, snapshot_ts, dpd_bucket, dpd_value, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (customer_id, time.time(), bucket, int(dpd_value or 0), source),
            )
            conn.commit()
        finally:
            conn.close()

    def roll_forward_matrix(self, days: int = 30, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        from collections import defaultdict
        cutoff = time.time() - (max(1, int(days)) * 86400)
        BUCKETS = ["0", "1-30", "31-60", "61-90", "90+"]
        bucket_order = {b: i for i, b in enumerate(BUCKETS)}
        conn = self._connect()
        try:
            if campaign_id:
                rows = conn.execute(
                    """
                    SELECT ds.customer_id, ds.dpd_bucket, ds.snapshot_ts
                    FROM dpd_snapshots ds
                    WHERE ds.snapshot_ts >= ?
                      AND EXISTS (
                          SELECT 1
                          FROM tasks t
                          WHERE t.customer_id = ds.customer_id
                            AND t.campaign_id = ?
                      )
                    ORDER BY ds.customer_id, ds.snapshot_ts ASC
                    """,
                    (cutoff, campaign_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT customer_id, dpd_bucket, snapshot_ts
                    FROM dpd_snapshots WHERE snapshot_ts >= ?
                    ORDER BY customer_id, snapshot_ts ASC
                    """,
                    (cutoff,),
                ).fetchall()
        except Exception:
            rows = []
        finally:
            conn.close()

        cust_snaps: Dict[str, List] = defaultdict(list)
        for r in rows:
            cust_snaps[r["customer_id"]].append((r["snapshot_ts"], r["dpd_bucket"]))

        matrix: Dict[str, Dict[str, int]] = {b: {b2: 0 for b2 in BUCKETS} for b in BUCKETS}
        total_transitions = 0
        roll_forward_count = 0
        rollback_count = 0
        cure_count = 0
        for snaps in cust_snaps.values():
            if len(snaps) < 2:
                continue
            from_b = snaps[0][1] or "0"
            to_b = snaps[-1][1] or "0"
            from_b = from_b if from_b in bucket_order else "0"
            to_b = to_b if to_b in bucket_order else "0"
            if from_b in matrix:
                matrix[from_b][to_b] = matrix[from_b].get(to_b, 0) + 1
            total_transitions += 1
            if bucket_order.get(to_b, 0) > bucket_order.get(from_b, 0):
                roll_forward_count += 1
            elif bucket_order.get(to_b, 0) < bucket_order.get(from_b, 0):
                rollback_count += 1
            if from_b != "0" and to_b == "0":
                cure_count += 1

        return {
            "buckets": BUCKETS,
            "matrix": matrix,
            "total_transitions": total_transitions,
            "roll_forward_count": roll_forward_count,
            "roll_forward_pct": round((roll_forward_count / max(1, total_transitions)) * 100.0, 2),
            "rollback_count": rollback_count,
            "rollback_pct": round((rollback_count / max(1, total_transitions)) * 100.0, 2),
            "cure_count": cure_count,
            "cure_rate_pct": round((cure_count / max(1, total_transitions)) * 100.0, 2),
            "window_days": int(days),
            "campaign_id": campaign_id,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Feature: Agent productivity (Feature 3)
    # ─────────────────────────────────────────────────────────────────────────

    def update_outcome_agent(
        self,
        *,
        session_id: str,
        agent_id: str,
        connect_duration_s: Optional[float] = None,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE outcomes
                SET agent_id = ?,
                    connect_duration_s = COALESCE(?, connect_duration_s)
                WHERE session_id = ?
                """,
                (agent_id, connect_duration_s, session_id),
            )
            conn.commit()
        finally:
            conn.close()

    def agent_metrics(self, *, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            campaign_where = " AND o.campaign_id = ?" if campaign_id else ""
            campaign_args = (campaign_id,) if campaign_id else ()
            rows = conn.execute(
                """
                SELECT
                    COALESCE(o.agent_id, 'unknown') AS agent_id,
                    u.full_name AS display_name,
                    COUNT(*) AS total_calls,
                    SUM(CASE WHEN o.end_ts IS NOT NULL THEN 1 ELSE 0 END) AS connected_calls,
                    AVG(CASE WHEN o.start_ts IS NOT NULL AND o.end_ts IS NOT NULL
                             THEN o.end_ts - o.start_ts ELSE NULL END) AS avg_handle_time_s,
                    SUM(CASE WHEN o.ptp_date IS NOT NULL AND o.ptp_date != '' THEN 1 ELSE 0 END) AS ptp_count,
                    SUM(COALESCE(o.escalations, 0)) AS total_escalations
                FROM outcomes o
                LEFT JOIN users u ON u.id = o.agent_id OR u.username = o.agent_id
                WHERE o.agent_id IS NOT NULL
                """
                + campaign_where
                + """
                GROUP BY COALESCE(o.agent_id, 'unknown')
                ORDER BY ptp_count DESC
                """,
                campaign_args,
            ).fetchall()
            viol_rows = conn.execute(
                """
                SELECT o.agent_id, COUNT(*) AS n
                FROM compliance_violations cv
                JOIN outcomes o ON cv.session_id = o.session_id
                WHERE o.agent_id IS NOT NULL
                """
                + campaign_where
                + """
                GROUP BY o.agent_id
                """,
                campaign_args,
            ).fetchall()
            viol_by_agent = {r["agent_id"]: int(r["n"] or 0) for r in viol_rows}
            out = []
            for idx, r in enumerate(rows):
                agent_id = r["agent_id"]
                total = int(r["total_calls"] or 0)
                connected = int(r["connected_calls"] or 0)
                ptp = int(r["ptp_count"] or 0)
                out.append({
                    "rank": idx + 1,
                    "agent_id": agent_id,
                    "display_name": r["display_name"] or agent_id,
                    "total_calls": total,
                    "connected_calls": connected,
                    "connect_rate_pct": round((connected / max(1, total)) * 100.0, 1),
                    "avg_handle_time_s": round(float(r["avg_handle_time_s"] or 0), 1),
                    "ptp_count": ptp,
                    "ptp_conversion_pct": round((ptp / max(1, connected)) * 100.0, 1),
                    "total_escalations": int(r["total_escalations"] or 0),
                    "escalations": int(r["total_escalations"] or 0),  # UI alias
                    "compliance_violations": viol_by_agent.get(agent_id, 0),
                })
            return out
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Feature: Realized recovery rate (Feature 2)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_query(conn: "sqlite3.Connection", sql: str, args: tuple = ()) -> List[Any]:
        try:
            return conn.execute(sql, args).fetchall()
        except Exception:
            return []

    def realized_recovery_trend(self, days: int = 30, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        cutoff = time.time() - (max(1, int(days)) * 86400)
        conn = self._connect()
        try:
            payment_filter = """
                WHERE status = 'SUCCEEDED'
                  AND COALESCE(updated_at, created_at) >= ?
            """
            payment_args: List[Any] = [cutoff]
            if campaign_id:
                payment_filter += """
                  AND EXISTS (
                      SELECT 1
                      FROM outcomes o
                      WHERE o.customer_id = payment_intents.customer_id
                        AND o.campaign_id = ?
                  )
                """
                payment_args.append(campaign_id)

            daily_rows = self._safe_query(
                conn,
                """
                SELECT
                    DATE(COALESCE(updated_at, created_at), 'unixepoch', 'localtime') AS day,
                    SUM(amount) AS day_amount,
                    COUNT(*) AS day_count
                FROM payment_intents
                """
                + payment_filter
                + """
                GROUP BY day
                ORDER BY day ASC
                """,
                tuple(payment_args),
            )
            total_recovered = sum(float(r["day_amount"] or 0) for r in daily_rows)
            reconciliation = self._safe_query(
                conn,
                """
                SELECT pi.id, pi.customer_id, pi.amount, pi.currency,
                       pi.loan_account_id,
                       COALESCE(pi.updated_at, pi.created_at) AS ts,
                       DATE(COALESCE(pi.updated_at, pi.created_at), 'unixepoch', 'localtime') AS date,
                       o.session_id
                FROM payment_intents pi
                LEFT JOIN outcomes o ON o.customer_id = pi.customer_id
                WHERE pi.status = 'SUCCEEDED'
                  AND COALESCE(pi.updated_at, pi.created_at) >= ?
                """
                + (
                    """
                  AND EXISTS (
                      SELECT 1
                      FROM outcomes ox
                      WHERE ox.customer_id = pi.customer_id
                        AND ox.campaign_id = ?
                  )
                    """
                    if campaign_id
                    else ""
                )
                + """
                ORDER BY ts DESC
                LIMIT 100
                """,
                tuple([cutoff, campaign_id] if campaign_id else [cutoff]),
            )
            # Portfolio value: sum of all outstanding principal from loan_accounts.
            portfolio_value = 0.0
            if campaign_id:
                pv_rows = self._safe_query(
                    conn,
                    "SELECT SUM(COALESCE(amount_due, 0)) AS total FROM tasks WHERE campaign_id = ?",
                    (campaign_id,),
                )
            else:
                pv_rows = self._safe_query(
                    conn,
                    "SELECT SUM(COALESCE(principal_outstanding, 0)) AS total FROM loan_accounts",
                    (),
                )
            if pv_rows:
                portfolio_value = float(pv_rows[0]["total"] or 0)
            recovery_rate_pct = (
                round((total_recovered / portfolio_value) * 100.0, 2)
                if portfolio_value > 0
                else 0.0
            )
            return {
                "dates": [r["day"] for r in daily_rows],
                "amounts": [float(r["day_amount"] or 0) for r in daily_rows],
                "daily_counts": [int(r["day_count"] or 0) for r in daily_rows],
                "total_recovered": round(total_recovered, 2),
                "portfolio_value": round(portfolio_value, 2),
                "recovery_rate_pct": recovery_rate_pct,
                "window_days": int(days),
                "reconciliation": [dict(r) for r in reconciliation],
                "campaign_id": campaign_id,
            }
        finally:
            conn.close()
