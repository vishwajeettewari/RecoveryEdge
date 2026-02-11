from __future__ import annotations

import json
import os
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
                    INSERT INTO outcomes (session_id, start_ts, end_ts, customer_id, campaign_id, dpd_bucket, disposition, ptp_date, callback_time, escalations)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        start_ts,
                        end_ts,
                        customer_id,
                        campaign_id,
                        dpd_bucket,
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
        conn = self._connect()
        try:
            where = ""
            args: List[Any] = []
            if campaign_id:
                where = " WHERE campaign_id = ?"
                args = [campaign_id]

            sessions_today = conn.execute(
                f"SELECT COUNT(DISTINCT session_id) AS n FROM events WHERE ts >= ?",
                (day_start,),
            ).fetchone()["n"]

            ptp_count = conn.execute(
                f"SELECT COUNT(*) AS n FROM outcomes{where + (' AND' if where else ' WHERE') if True else ''} ptp_date IS NOT NULL AND ptp_date != ''",
                tuple(args),
            ).fetchone()["n"]
            callback_count = conn.execute(
                f"SELECT COUNT(*) AS n FROM outcomes{where + (' AND' if where else ' WHERE') if True else ''} callback_time IS NOT NULL AND callback_time != ''",
                tuple(args),
            ).fetchone()["n"]
            escalations = conn.execute(
                f"SELECT COALESCE(SUM(escalations), 0) AS n FROM outcomes{where}",
                tuple(args),
            ).fetchone()["n"]
            ended = conn.execute(
                f"SELECT COUNT(*) AS n FROM outcomes{where + (' AND' if where else ' WHERE') if True else ''} end_ts IS NOT NULL",
                tuple(args),
            ).fetchone()["n"]
            avg_handle_s = conn.execute(
                f"SELECT AVG(end_ts - start_ts) AS v FROM outcomes{where + (' AND' if where else ' WHERE') if True else ''} start_ts IS NOT NULL AND end_ts IS NOT NULL",
                tuple(args),
            ).fetchone()["v"]

            assigned = conn.execute(
                "SELECT COUNT(*) AS n FROM campaign_accounts" + (" WHERE campaign_id = ?" if campaign_id else ""),
                tuple([campaign_id] if campaign_id else []),
            ).fetchone()["n"]
            contacted = conn.execute(
                "SELECT COUNT(DISTINCT customer_id) AS n FROM campaign_runs" + (" WHERE campaign_id = ?" if campaign_id else ""),
                tuple([campaign_id] if campaign_id else []),
            ).fetchone()["n"]
            retries_pending = conn.execute(
                "SELECT COUNT(*) AS n FROM campaign_accounts WHERE state = 'retry_scheduled'" + (" AND campaign_id = ?" if campaign_id else ""),
                tuple([campaign_id] if campaign_id else []),
            ).fetchone()["n"]

            by_bucket_rows = conn.execute(
                """
                SELECT COALESCE(dpd_bucket, 'unknown') AS bucket,
                       COUNT(*) AS total,
                       SUM(CASE WHEN ptp_date IS NOT NULL AND ptp_date != '' THEN 1 ELSE 0 END) AS ptp
                FROM outcomes
                GROUP BY COALESCE(dpd_bucket, 'unknown')
                """
            ).fetchall()
            ptp_rate_by_bucket = {
                r["bucket"]: {
                    "total": int(r["total"] or 0),
                    "ptp": int(r["ptp"] or 0),
                    "rate": round((int(r["ptp"] or 0) / int(r["total"] or 1)) * 100.0, 2),
                }
                for r in by_bucket_rows
            }

            conversion_rows = conn.execute(
                """
                SELECT campaign_id,
                       COUNT(*) AS total,
                       SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) AS completed
                FROM campaign_accounts
                GROUP BY campaign_id
                """
            ).fetchall()
            conversion_by_campaign = {
                r["campaign_id"]: {
                    "total": int(r["total"] or 0),
                    "completed": int(r["completed"] or 0),
                    "rate": round((int(r["completed"] or 0) / int(r["total"] or 1)) * 100.0, 2),
                }
                for r in conversion_rows
            }

            escalation_rows = conn.execute(
                """
                SELECT json_extract(payload_json, '$.reason') AS reason, COUNT(*) AS n
                FROM events
                WHERE event_type = 'action'
                  AND json_extract(payload_json, '$.name') = 'escalate_ticket'
                GROUP BY json_extract(payload_json, '$.reason')
                """
            ).fetchall()
            escalations_by_reason = {str(r["reason"] or "unknown"): int(r["n"] or 0) for r in escalation_rows}

            return {
                "sessions_today": int(sessions_today or 0),
                "ptp_count": int(ptp_count or 0),
                "callback_count": int(callback_count or 0),
                "escalations": int(escalations or 0),
                "ended_sessions": int(ended or 0),
                "avg_handle_seconds": float(avg_handle_s) if avg_handle_s is not None else None,
                "accounts_assigned": int(assigned or 0),
                "accounts_contacted": int(contacted or 0),
                "retries_pending": int(retries_pending or 0),
                "ptp_rate_by_bucket": ptp_rate_by_bucket,
                "conversion_by_campaign": conversion_by_campaign,
                "escalations_by_reason": escalations_by_reason,
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
