from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List


class CRMAdapter:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def enqueue_outcome(self, *, session_id: str, event_type: str, payload: Dict[str, Any]) -> str:
        queue_id = f"out-{uuid.uuid4().hex[:10]}"
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO outbound_queue (queue_id, session_id, event_type, payload_json, state, attempts, next_retry_ts, created_ts, updated_ts)
                VALUES (?, ?, ?, ?, 'queued', 0, ?, ?, ?)
                """,
                (queue_id, session_id, event_type, json.dumps(payload, ensure_ascii=False), now, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return queue_id

    def process_queue(self, *, limit: int = 100) -> Dict[str, int]:
        conn = self._connect()
        now = time.time()
        out = {"processed": 0, "acked": 0, "retry": 0, "dead_letter": 0}
        try:
            rows = conn.execute(
                """
                SELECT * FROM outbound_queue
                WHERE state IN ('queued', 'retry_scheduled')
                  AND COALESCE(next_retry_ts, 0) <= ?
                ORDER BY updated_ts ASC
                LIMIT ?
                """,
                (now, max(1, int(limit))),
            ).fetchall()
            for row in rows:
                out["processed"] += 1
                attempts = int(row["attempts"] or 0) + 1
                queue_id = row["queue_id"]
                # Demo-realistic ACK simulation.
                should_ack = (sum(ord(c) for c in queue_id) + attempts * 13) % 100 < 80
                if should_ack:
                    conn.execute(
                        "UPDATE outbound_queue SET state='acked', attempts=?, updated_ts=? WHERE queue_id=?",
                        (attempts, now, queue_id),
                    )
                    out["acked"] += 1
                elif attempts >= 4:
                    conn.execute(
                        "UPDATE outbound_queue SET state='dead_letter', attempts=?, updated_ts=? WHERE queue_id=?",
                        (attempts, now, queue_id),
                    )
                    out["dead_letter"] += 1
                else:
                    retry_ts = now + (attempts * 60)
                    conn.execute(
                        "UPDATE outbound_queue SET state='retry_scheduled', attempts=?, next_retry_ts=?, updated_ts=? WHERE queue_id=?",
                        (attempts, retry_ts, now, queue_id),
                    )
                    out["retry"] += 1
            conn.commit()
        finally:
            conn.close()
        return out

    def status(self) -> Dict[str, int]:
        conn = self._connect()
        try:
            out = {}
            for state in ("queued", "retry_scheduled", "acked", "dead_letter"):
                n = conn.execute(
                    "SELECT COUNT(*) AS n FROM outbound_queue WHERE state = ?",
                    (state,),
                ).fetchone()["n"]
                out[state] = int(n or 0)
            return out
        finally:
            conn.close()

    def replay_session(self, session_id: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM outcomes WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "session_not_found"}
            payload = {
                "session_id": session_id,
                "customer_id": row["customer_id"],
                "disposition": row["disposition"],
                "ptp_date": row["ptp_date"],
                "callback_time": row["callback_time"],
                "escalations": int(row["escalations"] or 0),
                "source": "replay",
            }
            qid = self.enqueue_outcome(session_id=session_id, event_type="outcome_replay", payload=payload)
            return {"ok": True, "queue_id": qid, "payload": payload}
        finally:
            conn.close()

    def mock_receive(self, payload: Dict[str, Any], should_fail: bool = False) -> Dict[str, Any]:
        return {
            "ok": not bool(should_fail),
            "received_at": round(time.time(), 3),
            "echo": payload,
        }
