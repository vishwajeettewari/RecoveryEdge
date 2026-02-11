from __future__ import annotations

import csv
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


CSV_COLUMNS = [
    "report_date",
    "campaign_id",
    "attempts",
    "connected",
    "connected_rate",
    "ptp_count",
    "ptp_conversion",
    "ptp_amount_sum",
    "expected_recovery_amount",
    "escalations",
    "compliance_violations",
    "bucket_1_30",
    "bucket_31_60",
    "bucket_61_90",
    "bucket_90_plus",
    "queue_new",
    "queue_in_progress",
    "queue_ptp",
    "queue_callback",
    "queue_escalated",
    "queue_closed",
    "top_5_escalation_reasons_json",
]


class ReportsService:
    def __init__(self, db_path: str, data_dir: str, tz_name: str = "Asia/Kolkata") -> None:
        self.db_path = db_path
        self.tz_name = tz_name or "Asia/Kolkata"
        self.base_dir = os.path.join(data_dir, "reports")
        os.makedirs(self.base_dir, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS report_configs (
                    id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL,
                    daily_time TEXT NOT NULL,
                    last_run_date TEXT,
                    updated_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    report_date TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    path_csv TEXT NOT NULL,
                    path_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                )
                """
            )
            row = conn.execute("SELECT id FROM report_configs WHERE id = 'default'").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO report_configs (id, enabled, daily_time, last_run_date, updated_at) VALUES ('default', 1, '09:00', NULL, ?)",
                    (time.time(),),
                )
            conn.commit()
        finally:
            conn.close()

    def set_schedule(self, *, enabled: bool, daily_time: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE report_configs SET enabled = ?, daily_time = ?, updated_at = ? WHERE id = 'default'",
                (1 if enabled else 0, daily_time, time.time()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM report_configs WHERE id = 'default'").fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_schedule(self) -> Dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM report_configs WHERE id = 'default'").fetchone()
            return dict(row) if row else {"id": "default", "enabled": 1, "daily_time": "09:00", "last_run_date": None}
        finally:
            conn.close()

    def generate_report(self, *, campaign_id: str, report_date: Optional[str] = None) -> Dict[str, Any]:
        report_date = report_date or self._today_str()
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT * FROM reports WHERE campaign_id = ? AND report_date = ?",
                (campaign_id, report_date),
            ).fetchone()
            if existing:
                return dict(existing)

            summary = self._build_summary(conn, campaign_id=campaign_id, report_date=report_date)
            day_dir = os.path.join(self.base_dir, report_date)
            os.makedirs(day_dir, exist_ok=True)
            rid = f"rpt-{uuid.uuid4().hex[:12]}"
            json_path = os.path.join(day_dir, f"{campaign_id}-{rid}.json")
            csv_path = os.path.join(day_dir, f"{campaign_id}-{rid}.csv")

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerow(self._summary_to_csv_row(summary))

            ts = time.time()
            conn.execute(
                """
                INSERT INTO reports (id, campaign_id, report_date, created_at, path_csv, path_json, summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rid, campaign_id, report_date, ts, csv_path, json_path, json.dumps(summary, ensure_ascii=False)),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def run_scheduler_tick(self) -> Dict[str, Any]:
        schedule = self.get_schedule()
        if int(schedule.get("enabled") or 0) != 1:
            return {"ran": False, "reason": "disabled"}

        tz = ZoneInfo(self.tz_name)
        now = datetime.now(tz)
        today = now.strftime("%Y-%m-%d")
        hhmm = str(schedule.get("daily_time") or "09:00")
        try:
            h, m = hhmm.split(":", 1)
            target_h = int(h)
            target_m = int(m)
        except Exception:
            target_h, target_m = 9, 0

        if (now.hour, now.minute) < (target_h, target_m):
            return {"ran": False, "reason": "before_time"}
        if str(schedule.get("last_run_date") or "") == today:
            return {"ran": False, "reason": "already_ran"}

        conn = self._connect()
        created = 0
        try:
            camps = conn.execute("SELECT campaign_id FROM campaigns").fetchall()
            for c in camps:
                rid = self.generate_report(campaign_id=str(c["campaign_id"]), report_date=today)
                if rid:
                    created += 1
            conn.execute("UPDATE report_configs SET last_run_date = ?, updated_at = ? WHERE id = 'default'", (today, time.time()))
            conn.commit()
            return {"ran": True, "created": created}
        finally:
            conn.close()

    def list_reports(self, *, page: int = 1, page_size: int = 20, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where = ""
            args: List[Any] = []
            if campaign_id:
                where = "WHERE campaign_id = ?"
                args.append(campaign_id)
            total = conn.execute(f"SELECT COUNT(*) AS n FROM reports {where}", tuple(args)).fetchone()["n"]
            lim = max(1, min(100, int(page_size)))
            offset = max(0, (max(1, int(page)) - 1) * lim)
            rows = conn.execute(
                f"SELECT * FROM reports {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(args + [lim, offset]),
            ).fetchall()
            return {"rows": [dict(r) for r in rows], "total": int(total or 0), "page": max(1, int(page)), "page_size": lim}
        finally:
            conn.close()

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _build_summary(self, conn: sqlite3.Connection, *, campaign_id: str, report_date: str) -> Dict[str, Any]:
        attempts = conn.execute(
            "SELECT COUNT(*) AS n FROM campaign_runs WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()["n"]
        connected = conn.execute(
            "SELECT COUNT(*) AS n FROM campaign_runs WHERE campaign_id = ? AND outcome != 'failed'",
            (campaign_id,),
        ).fetchone()["n"]
        ptp_count = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE campaign_id = ? AND state = 'PTP'",
            (campaign_id,),
        ).fetchone()["n"]
        ptp_amount_sum = conn.execute(
            "SELECT COALESCE(SUM(amount_due), 0) AS v FROM tasks WHERE campaign_id = ? AND state = 'PTP'",
            (campaign_id,),
        ).fetchone()["v"]
        escalations = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE campaign_id = ? AND state = 'ESCALATED'",
            (campaign_id,),
        ).fetchone()["n"]
        compliance_violations = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM compliance_violations cv
            JOIN outcomes o ON o.session_id = cv.session_id
            WHERE o.campaign_id = ?
            """,
            (campaign_id,),
        ).fetchone()["n"]

        bucket_rows = conn.execute(
            """
            SELECT
              SUM(CASE WHEN dpd BETWEEN 1 AND 30 THEN 1 ELSE 0 END) AS b1,
              SUM(CASE WHEN dpd BETWEEN 31 AND 60 THEN 1 ELSE 0 END) AS b2,
              SUM(CASE WHEN dpd BETWEEN 61 AND 90 THEN 1 ELSE 0 END) AS b3,
              SUM(CASE WHEN dpd > 90 THEN 1 ELSE 0 END) AS b4
            FROM tasks
            WHERE campaign_id = ?
            """,
            (campaign_id,),
        ).fetchone()

        queue_rows = conn.execute(
            "SELECT state, COUNT(*) AS n FROM tasks WHERE campaign_id = ? GROUP BY state",
            (campaign_id,),
        ).fetchall()
        queue_snapshot = {"NEW": 0, "IN_PROGRESS": 0, "PTP": 0, "CALLBACK": 0, "ESCALATED": 0, "CLOSED": 0}
        for r in queue_rows:
            queue_snapshot[str(r["state"])] = int(r["n"] or 0)

        reason_rows = conn.execute(
            """
            SELECT json_extract(payload_json, '$.escalate_reason') AS reason, COUNT(*) AS n
            FROM task_events
            WHERE event_type = 'escalate'
            GROUP BY json_extract(payload_json, '$.escalate_reason')
            ORDER BY n DESC
            LIMIT 5
            """
        ).fetchall()
        top_reasons = [{"reason": str(r["reason"] or "unknown"), "count": int(r["n"] or 0)} for r in reason_rows]

        attempts_i = int(attempts or 0)
        connected_i = int(connected or 0)
        ptp_i = int(ptp_count or 0)
        connected_rate = round((connected_i / attempts_i), 4) if attempts_i > 0 else 0.0
        ptp_conversion = round((ptp_i / connected_i), 4) if connected_i > 0 else 0.0

        summary = {
            "report_date": report_date,
            "campaign_id": campaign_id,
            "totals": {
                "attempts": attempts_i,
                "connected": connected_i,
                "connected_rate": connected_rate,
                "ptp_count": ptp_i,
                "ptp_conversion": ptp_conversion,
                "ptp_amount_sum": float(ptp_amount_sum or 0.0),
                "expected_recovery_amount": float(ptp_amount_sum or 0.0),
                "escalations": int(escalations or 0),
                "compliance_violations": int(compliance_violations or 0),
            },
            "bucket_heatmap": {
                "1-30": int(bucket_rows["b1"] or 0),
                "31-60": int(bucket_rows["b2"] or 0),
                "61-90": int(bucket_rows["b3"] or 0),
                "90+": int(bucket_rows["b4"] or 0),
            },
            "queue_snapshot": queue_snapshot,
            "top_5_escalation_reasons": top_reasons,
        }
        return summary

    @staticmethod
    def _summary_to_csv_row(summary: Dict[str, Any]) -> Dict[str, Any]:
        totals = summary.get("totals", {})
        buckets = summary.get("bucket_heatmap", {})
        queue = summary.get("queue_snapshot", {})
        return {
            "report_date": summary.get("report_date"),
            "campaign_id": summary.get("campaign_id"),
            "attempts": totals.get("attempts", 0),
            "connected": totals.get("connected", 0),
            "connected_rate": totals.get("connected_rate", 0.0),
            "ptp_count": totals.get("ptp_count", 0),
            "ptp_conversion": totals.get("ptp_conversion", 0.0),
            "ptp_amount_sum": totals.get("ptp_amount_sum", 0.0),
            "expected_recovery_amount": totals.get("expected_recovery_amount", 0.0),
            "escalations": totals.get("escalations", 0),
            "compliance_violations": totals.get("compliance_violations", 0),
            "bucket_1_30": buckets.get("1-30", 0),
            "bucket_31_60": buckets.get("31-60", 0),
            "bucket_61_90": buckets.get("61-90", 0),
            "bucket_90_plus": buckets.get("90+", 0),
            "queue_new": queue.get("NEW", 0),
            "queue_in_progress": queue.get("IN_PROGRESS", 0),
            "queue_ptp": queue.get("PTP", 0),
            "queue_callback": queue.get("CALLBACK", 0),
            "queue_escalated": queue.get("ESCALATED", 0),
            "queue_closed": queue.get("CLOSED", 0),
            "top_5_escalation_reasons_json": json.dumps(summary.get("top_5_escalation_reasons", []), ensure_ascii=False),
        }

    def _today_str(self) -> str:
        return datetime.now(ZoneInfo(self.tz_name)).strftime("%Y-%m-%d")
