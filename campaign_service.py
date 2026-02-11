from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


class CampaignService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def create_campaign(
        self,
        *,
        name: str,
        customer_ids: List[str],
        max_attempts: int = 3,
        retry_delay_minutes: int = 30,
        batch_size: int = 250,
    ) -> Dict[str, Any]:
        campaign_id = f"cmp-{uuid.uuid4().hex[:10]}"
        now = time.time()
        rows = [(campaign_id, cid, "pending", 0, now, now) for cid in customer_ids if cid]
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO campaigns (campaign_id, name, status, max_attempts, retry_delay_minutes, batch_size, created_ts, updated_ts)
                VALUES (?, ?, 'created', ?, ?, ?, ?, ?)
                """,
                (campaign_id, name or campaign_id, max(1, int(max_attempts)), max(1, int(retry_delay_minutes)), max(10, int(batch_size)), now, now),
            )
            if rows:
                conn.executemany(
                    """
                    INSERT INTO campaign_accounts (campaign_id, customer_id, state, attempts, next_retry_ts, updated_ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
            conn.commit()
        finally:
            conn.close()
        return {"campaign_id": campaign_id, "accounts": len(rows)}

    def set_status(self, campaign_id: str, status: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE campaigns SET status = ?, updated_ts = ? WHERE campaign_id = ?",
                (status, time.time(), campaign_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def run_pending_batch(self, campaign_id: str) -> Dict[str, int]:
        conn = self._connect()
        now = time.time()
        out = {"processed": 0, "retry_scheduled": 0, "completed": 0, "escalated": 0, "failed": 0}
        try:
            campaign = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
            if not campaign or campaign["status"] not in {"active", "created"}:
                return out

            batch_size = max(10, int(campaign["batch_size"] or 250))
            retry_delay = max(1, int(campaign["retry_delay_minutes"] or 30)) * 60
            max_attempts = max(1, int(campaign["max_attempts"] or 3))

            rows = conn.execute(
                """
                SELECT * FROM campaign_accounts
                WHERE campaign_id = ?
                  AND state IN ('pending', 'retry_scheduled')
                  AND COALESCE(next_retry_ts, 0) <= ?
                ORDER BY updated_ts ASC
                LIMIT ?
                """,
                (campaign_id, now, batch_size),
            ).fetchall()

            for row in rows:
                attempts = int(row["attempts"] or 0) + 1
                customer_id = str(row["customer_id"])
                outcome = self._simulate_attempt(customer_id=customer_id, attempts=attempts)
                out["processed"] += 1

                if outcome == "completed":
                    conn.execute(
                        "UPDATE campaign_accounts SET state='completed', attempts=?, updated_ts=? WHERE campaign_id=? AND customer_id=?",
                        (attempts, now, campaign_id, customer_id),
                    )
                    out["completed"] += 1
                elif outcome == "escalated":
                    conn.execute(
                        "UPDATE campaign_accounts SET state='escalated', attempts=?, updated_ts=? WHERE campaign_id=? AND customer_id=?",
                        (attempts, now, campaign_id, customer_id),
                    )
                    out["escalated"] += 1
                elif attempts >= max_attempts:
                    conn.execute(
                        "UPDATE campaign_accounts SET state='failed', attempts=?, updated_ts=? WHERE campaign_id=? AND customer_id=?",
                        (attempts, now, campaign_id, customer_id),
                    )
                    out["failed"] += 1
                else:
                    backoff = retry_delay * attempts
                    conn.execute(
                        "UPDATE campaign_accounts SET state='retry_scheduled', attempts=?, next_retry_ts=?, updated_ts=? WHERE campaign_id=? AND customer_id=?",
                        (attempts, now + backoff, now, campaign_id, customer_id),
                    )
                    out["retry_scheduled"] += 1

                conn.execute(
                    """
                    INSERT INTO campaign_runs (campaign_id, customer_id, ts, attempt_no, outcome)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (campaign_id, customer_id, now, attempts, outcome),
                )

            if out["processed"] > 0:
                conn.execute(
                    "UPDATE campaigns SET status='active', updated_ts=? WHERE campaign_id=?",
                    (time.time(), campaign_id),
                )

            remaining = conn.execute(
                """
                SELECT COUNT(*) AS n FROM campaign_accounts
                WHERE campaign_id=? AND state IN ('pending', 'retry_scheduled')
                """,
                (campaign_id,),
            ).fetchone()["n"]
            if int(remaining or 0) == 0:
                conn.execute(
                    "UPDATE campaigns SET status='completed', updated_ts=? WHERE campaign_id=?",
                    (time.time(), campaign_id),
                )

            conn.commit()
            return out
        finally:
            conn.close()

    def metrics(self, campaign_id: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            campaign = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
            if not campaign:
                return {"error": "campaign_not_found"}
            totals = {}
            for state in ("pending", "retry_scheduled", "completed", "escalated", "failed"):
                n = conn.execute(
                    "SELECT COUNT(*) AS n FROM campaign_accounts WHERE campaign_id = ? AND state = ?",
                    (campaign_id, state),
                ).fetchone()["n"]
                totals[state] = int(n or 0)
            totals["campaign_id"] = campaign_id
            totals["status"] = campaign["status"]
            totals["name"] = campaign["name"]
            totals["max_attempts"] = int(campaign["max_attempts"] or 0)
            totals["retry_delay_minutes"] = int(campaign["retry_delay_minutes"] or 0)
            totals["batch_size"] = int(campaign["batch_size"] or 0)
            totals["total_accounts"] = sum(totals[s] for s in ("pending", "retry_scheduled", "completed", "escalated", "failed"))
            return totals
        finally:
            conn.close()

    def list_campaigns(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM campaigns ORDER BY updated_ts DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _simulate_attempt(*, customer_id: str, attempts: int) -> str:
        # Deterministic simulation for repeatable demos.
        seed = sum(ord(c) for c in customer_id) + attempts * 17
        mod = seed % 100
        if mod < 45:
            return "completed"
        if mod < 60:
            return "escalated"
        if mod < 92:
            return "retry_scheduled"
        return "failed"
