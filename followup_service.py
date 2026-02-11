from __future__ import annotations

import hashlib
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo


class FollowupService:
    def __init__(self, db_path: str, tz_name: str = "Asia/Kolkata") -> None:
        self.db_path = db_path
        self.tz_name = tz_name or "Asia/Kolkata"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def schedule_ptp_followups(
        self,
        *,
        session_id: str,
        customer_id: Optional[str],
        ptp_date: str,
        phone: Optional[str],
        channel: str = "whatsapp",
    ) -> List[Dict[str, str]]:
        tz = ZoneInfo(self.tz_name)
        try:
            base_date = datetime.fromisoformat(str(ptp_date)).date()
        except Exception:
            return []

        schedule = [
            ("ptp_t_minus_1", datetime.combine(base_date - timedelta(days=1), datetime.min.time(), tz).replace(hour=11, minute=0)),
            ("ptp_t_day", datetime.combine(base_date, datetime.min.time(), tz).replace(hour=11, minute=0)),
            ("ptp_t_plus_1_miss", datetime.combine(base_date + timedelta(days=1), datetime.min.time(), tz).replace(hour=11, minute=0)),
        ]

        out: List[Dict[str, str]] = []
        conn = self._connect()
        now = time.time()
        try:
            for reminder_type, dt in schedule:
                idem = self._idempotency_key(session_id=session_id, reminder_type=reminder_type, target_ts=dt.timestamp())
                conn.execute(
                    """
                    INSERT OR IGNORE INTO followups (idempotency_key, session_id, customer_id, reminder_type, channel, phone, scheduled_ts, status, created_ts, updated_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?)
                    """,
                    (idem, session_id, customer_id, reminder_type, channel, phone, dt.timestamp(), now, now),
                )
                out.append({"reminder_type": reminder_type, "idempotency_key": idem})
            conn.commit()
        finally:
            conn.close()
        return out

    def due_followups(self, limit: int = 200) -> List[Dict[str, object]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM followups
                WHERE status = 'scheduled' AND scheduled_ts <= ?
                ORDER BY scheduled_ts ASC
                LIMIT ?
                """,
                (time.time(), max(1, int(limit))),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def mark_sent(self, idempotency_key: str) -> None:
        self.mark_status(idempotency_key, status="sent")

    def mark_status(self, idempotency_key: str, *, status: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE followups SET status=?, updated_ts=? WHERE idempotency_key=?",
                (status, time.time(), idempotency_key),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _idempotency_key(*, session_id: str, reminder_type: str, target_ts: float) -> str:
        raw = f"{session_id}|{reminder_type}|{int(target_ts)}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:20]
