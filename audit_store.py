from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional


class SQLiteAuditStore:
    def __init__(self, path: str, retention_days: int = 30) -> None:
        self.path = path
        self.retention_days = max(1, int(retention_days))
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._init_db()
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
            conn.commit()
        finally:
            conn.close()

    def _purge_old(self) -> None:
        cutoff = time.time() - (self.retention_days * 86400)
        conn = self._connect()
        try:
            conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            conn.execute("DELETE FROM violations WHERE ts < ?", (cutoff,))
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
                    INSERT INTO outcomes (session_id, start_ts, end_ts, customer_id, disposition, ptp_date, callback_time, escalations)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        start_ts,
                        end_ts,
                        customer_id,
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

    def metrics(self) -> Dict[str, Any]:
        now = time.time()
        day_start = now - (now % 86400)
        conn = self._connect()
        try:
            sessions_today = conn.execute(
                "SELECT COUNT(DISTINCT session_id) AS n FROM events WHERE ts >= ?",
                (day_start,),
            ).fetchone()["n"]
            ptp_count = conn.execute(
                "SELECT COUNT(*) AS n FROM outcomes WHERE ptp_date IS NOT NULL AND ptp_date != ''"
            ).fetchone()["n"]
            callback_count = conn.execute(
                "SELECT COUNT(*) AS n FROM outcomes WHERE callback_time IS NOT NULL AND callback_time != ''"
            ).fetchone()["n"]
            escalations = conn.execute("SELECT COALESCE(SUM(escalations), 0) AS n FROM outcomes").fetchone()["n"]
            ended = conn.execute("SELECT COUNT(*) AS n FROM outcomes WHERE end_ts IS NOT NULL").fetchone()["n"]
            avg_handle_s = conn.execute(
                "SELECT AVG(end_ts - start_ts) AS v FROM outcomes WHERE start_ts IS NOT NULL AND end_ts IS NOT NULL"
            ).fetchone()["v"]
            return {
                "sessions_today": int(sessions_today or 0),
                "ptp_count": int(ptp_count or 0),
                "callback_count": int(callback_count or 0),
                "escalations": int(escalations or 0),
                "ended_sessions": int(ended or 0),
                "avg_handle_seconds": float(avg_handle_s) if avg_handle_s is not None else None,
            }
        finally:
            conn.close()

    def recent_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT session_id, start_ts, end_ts, customer_id, disposition, ptp_date, callback_time, escalations
                FROM outcomes
                ORDER BY COALESCE(end_ts, start_ts, 0) DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

