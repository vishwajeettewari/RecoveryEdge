from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


RULE_TYPES = ["PTP_MISS", "SLA_BREACH", "ESCALATION_SPIKE", "COMPLIANCE_VIOLATION", "COMPLIANCE_BLOCK"]


class AlertsService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()
        self._seed_rules()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    threshold_json TEXT,
                    routing_json TEXT,
                    created_at REAL,
                    updated_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    rule_id TEXT,
                    type TEXT NOT NULL,
                    ts REAL NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entity_type TEXT,
                    entity_id TEXT,
                    message TEXT,
                    payload_json TEXT,
                    assigned_to TEXT,
                    acked_at REAL,
                    resolved_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    alert_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    to_addr TEXT,
                    status TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    last_error TEXT,
                    created_at REAL,
                    updated_at REAL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_rules(self) -> None:
        now = time.time()
        defaults = [
            ("rule-ptp-miss", "PTP Miss", "PTP_MISS", {"window_hours": 24}, {"channels": ["inapp"]}),
            ("rule-sla", "SLA Breach", "SLA_BREACH", {"window_hours": 1}, {"channels": ["inapp"]}),
            ("rule-comp", "Compliance Violation", "COMPLIANCE_VIOLATION", {"min_severity": "medium"}, {"channels": ["inapp"]}),
            ("rule-comp-block", "Compliance Block", "COMPLIANCE_BLOCK", {"enabled": True}, {"channels": ["inapp"]}),
            ("rule-esc-spike", "Escalation Spike", "ESCALATION_SPIKE", {"count": 5, "window_minutes": 60}, {"channels": ["inapp"]}),
        ]
        conn = self._connect()
        try:
            for rid, name, rtype, threshold, routing in defaults:
                row = conn.execute("SELECT id FROM alert_rules WHERE id = ?", (rid,)).fetchone()
                if row:
                    continue
                conn.execute(
                    """
                    INSERT INTO alert_rules (id, name, enabled, type, threshold_json, routing_json, created_at, updated_at)
                    VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                    """,
                    (rid, name, rtype, json.dumps(threshold, ensure_ascii=False), json.dumps(routing, ensure_ascii=False), now, now),
                )
            conn.commit()
        finally:
            conn.close()

    def list_rules(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM alert_rules ORDER BY created_at ASC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def upsert_rule(self, *, rule_id: Optional[str], name: str, rtype: str, enabled: bool, threshold: Dict[str, Any], routing: Dict[str, Any]) -> Dict[str, Any]:
        if rtype not in RULE_TYPES:
            raise ValueError("invalid_rule_type")
        rid = rule_id or f"rule-{uuid.uuid4().hex[:10]}"
        now = time.time()
        conn = self._connect()
        try:
            existing = conn.execute("SELECT id FROM alert_rules WHERE id = ?", (rid,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE alert_rules
                    SET name = ?, type = ?, enabled = ?, threshold_json = ?, routing_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (name, rtype, 1 if enabled else 0, json.dumps(threshold, ensure_ascii=False), json.dumps(routing, ensure_ascii=False), now, rid),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO alert_rules (id, name, enabled, type, threshold_json, routing_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (rid, name, 1 if enabled else 0, rtype, json.dumps(threshold, ensure_ascii=False), json.dumps(routing, ensure_ascii=False), now, now),
                )
            conn.commit()
            row = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rid,)).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def toggle_rule(self, *, rule_id: str, enabled: bool) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute("UPDATE alert_rules SET enabled = ?, updated_at = ? WHERE id = ?", (1 if enabled else 0, time.time(), rule_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def list_alerts(self, *, status: Optional[str], severity: Optional[str], rtype: Optional[str], page: int, page_size: int) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where = ["1=1"]
            args: List[Any] = []
            if status:
                where.append("status = ?")
                args.append(status)
            if severity:
                where.append("severity = ?")
                args.append(severity)
            if rtype:
                where.append("type = ?")
                args.append(rtype)
            total = conn.execute(f"SELECT COUNT(*) AS n FROM alerts WHERE {' AND '.join(where)}", tuple(args)).fetchone()["n"]
            lim = max(1, min(100, int(page_size)))
            offset = max(0, (max(1, int(page)) - 1) * lim)
            rows = conn.execute(
                f"SELECT * FROM alerts WHERE {' AND '.join(where)} ORDER BY ts DESC LIMIT ? OFFSET ?",
                tuple(args + [lim, offset]),
            ).fetchall()
            return {"rows": [dict(r) for r in rows], "total": int(total or 0), "page": max(1, int(page)), "page_size": lim}
        finally:
            conn.close()

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def ack_alert(self, *, alert_id: str, actor: str) -> bool:
        return self._set_alert_status(alert_id=alert_id, status="ACKED", actor=actor)

    def assign_alert(self, *, alert_id: str, assignee: str, actor: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE alerts SET assigned_to = ?, status = CASE WHEN status = 'OPEN' THEN 'ACKED' ELSE status END WHERE id = ?",
                (assignee, alert_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def resolve_alert(self, *, alert_id: str, actor: str) -> bool:
        return self._set_alert_status(alert_id=alert_id, status="RESOLVED", actor=actor)

    def evaluate(self) -> Dict[str, int]:
        conn = self._connect()
        out = {"created": 0, "ptp_miss": 0, "sla_breach": 0, "compliance_violation": 0, "compliance_block": 0, "escalation_spike": 0}
        now = time.time()
        try:
            rules = conn.execute("SELECT * FROM alert_rules WHERE enabled = 1").fetchall()
            rule_map = {str(r["type"]): dict(r) for r in rules}

            if "PTP_MISS" in rule_map:
                rows = conn.execute(
                    "SELECT idempotency_key, session_id, reminder_type, scheduled_ts FROM followups WHERE reminder_type = 'ptp_t_plus_1_miss' AND status IN ('missed', 'sent')"
                ).fetchall()
                for r in rows:
                    created = self._create_alert_if_new(
                        conn,
                        rule_id=str(rule_map["PTP_MISS"]["id"]),
                        rtype="PTP_MISS",
                        severity="high",
                        entity_type="followup",
                        entity_id=str(r["idempotency_key"]),
                        message="PTP follow-up miss detected",
                        payload={"session_id": r["session_id"], "reminder_type": r["reminder_type"]},
                    )
                    out["created"] += int(created)
                    out["ptp_miss"] += int(created)

            if "SLA_BREACH" in rule_map:
                rows = conn.execute(
                    "SELECT id, campaign_id, customer_id, state, sla_due_at FROM tasks WHERE state != 'CLOSED' AND COALESCE(sla_due_at, 0) > 0 AND sla_due_at < ?",
                    (now,),
                ).fetchall()
                for r in rows:
                    created = self._create_alert_if_new(
                        conn,
                        rule_id=str(rule_map["SLA_BREACH"]["id"]),
                        rtype="SLA_BREACH",
                        severity="medium",
                        entity_type="task",
                        entity_id=str(r["id"]),
                        message="Task SLA breach",
                        payload={"campaign_id": r["campaign_id"], "customer_id": r["customer_id"], "state": r["state"]},
                    )
                    out["created"] += int(created)
                    out["sla_breach"] += int(created)

            if "COMPLIANCE_VIOLATION" in rule_map:
                rows = conn.execute(
                    """
                    SELECT id, session_id, rule_code, severity, detail
                    FROM compliance_violations
                    WHERE LOWER(severity) IN ('medium', 'high')
                    """
                ).fetchall()
                for r in rows:
                    created = self._create_alert_if_new(
                        conn,
                        rule_id=str(rule_map["COMPLIANCE_VIOLATION"]["id"]),
                        rtype="COMPLIANCE_VIOLATION",
                        severity=str(r["severity"] or "medium"),
                        entity_type="compliance_violation",
                        entity_id=str(r["id"]),
                        message=f"Compliance violation: {r['rule_code']}",
                        payload={"session_id": r["session_id"], "detail": r["detail"]},
                    )
                    out["created"] += int(created)
                    out["compliance_violation"] += int(created)
                    if str(r["severity"] or "").lower() == "high":
                        self._enforce_compliance_block(conn, session_id=str(r["session_id"] or ""), reason=str(r["rule_code"] or "high_violation"))

            if "COMPLIANCE_BLOCK" in rule_map:
                rows = conn.execute("SELECT id, customer_id FROM tasks WHERE compliance_block = 1 AND state != 'CLOSED'").fetchall()
                for r in rows:
                    created = self._create_alert_if_new(
                        conn,
                        rule_id=str(rule_map["COMPLIANCE_BLOCK"]["id"]),
                        rtype="COMPLIANCE_BLOCK",
                        severity="high",
                        entity_type="task",
                        entity_id=str(r["id"]),
                        message="Task blocked by compliance",
                        payload={"customer_id": r["customer_id"]},
                    )
                    out["created"] += int(created)
                    out["compliance_block"] += int(created)

            if "ESCALATION_SPIKE" in rule_map:
                thr = rule_map["ESCALATION_SPIKE"].get("threshold_json")
                try:
                    tjson = json.loads(thr) if thr else {}
                except Exception:
                    tjson = {}
                count_threshold = int(tjson.get("count", 5))
                window_min = int(tjson.get("window_minutes", 60))
                since = now - (window_min * 60)
                n = conn.execute(
                    "SELECT COUNT(*) AS n FROM task_events WHERE event_type = 'escalate' AND ts >= ?",
                    (since,),
                ).fetchone()["n"]
                if int(n or 0) >= count_threshold:
                    created = self._create_alert_if_new(
                        conn,
                        rule_id=str(rule_map["ESCALATION_SPIKE"]["id"]),
                        rtype="ESCALATION_SPIKE",
                        severity="medium",
                        entity_type="system",
                        entity_id=f"esc_spike_{int(since)}",
                        message=f"Escalation spike detected ({int(n)} in {window_min}m)",
                        payload={"count": int(n), "window_minutes": window_min},
                    )
                    out["created"] += int(created)
                    out["escalation_spike"] += int(created)

            conn.commit()
            return out
        finally:
            conn.close()

    def _create_alert_if_new(
        self,
        conn: sqlite3.Connection,
        *,
        rule_id: str,
        rtype: str,
        severity: str,
        entity_type: str,
        entity_id: str,
        message: str,
        payload: Dict[str, Any],
    ) -> bool:
        existing = conn.execute(
            "SELECT id FROM alerts WHERE type = ? AND entity_type = ? AND entity_id = ? AND status IN ('OPEN', 'ACKED')",
            (rtype, entity_type, entity_id),
        ).fetchone()
        if existing:
            return False
        aid = f"alt-{uuid.uuid4().hex[:12]}"
        now = time.time()
        conn.execute(
            """
            INSERT INTO alerts (id, rule_id, type, ts, severity, status, entity_type, entity_id, message, payload_json, assigned_to, acked_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (aid, rule_id, rtype, now, severity, entity_type, entity_id, message, json.dumps(payload, ensure_ascii=False)),
        )
        nid = f"ntf-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO notifications (id, alert_id, channel, to_addr, status, attempts, last_error, created_at, updated_at)
            VALUES (?, ?, 'inapp', NULL, 'queued', 0, NULL, ?, ?)
            """,
            (nid, aid, now, now),
        )
        conn.execute(
            "INSERT INTO events (ts, session_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
            (now, None, "alert_created", json.dumps({"alert_id": aid, "type": rtype, "entity_id": entity_id}, ensure_ascii=False)),
        )
        return True

    def _enforce_compliance_block(self, conn: sqlite3.Connection, *, session_id: str, reason: str) -> None:
        if not session_id:
            return
        out = conn.execute("SELECT customer_id FROM outcomes WHERE session_id = ?", (session_id,)).fetchone()
        if not out:
            return
        customer_id = str(out["customer_id"] or "")
        if not customer_id:
            return
        rows = conn.execute(
            "SELECT id, compliance_status_json FROM tasks WHERE customer_id = ? AND state != 'CLOSED'",
            (customer_id,),
        ).fetchall()
        now = time.time()
        for row in rows:
            status = {}
            try:
                status = json.loads(row["compliance_status_json"] or "{}")
            except Exception:
                status = {}
            status["NO_THREATS_OK"] = False
            conn.execute(
                "UPDATE tasks SET compliance_block = 1, compliance_status_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(status, ensure_ascii=False), now, row["id"]),
            )
            conn.execute(
                "INSERT INTO task_events (task_id, ts, actor, event_type, payload_json) VALUES (?, ?, ?, ?, ?)",
                (row["id"], now, "system", "compliance_block", json.dumps({"reason": reason}, ensure_ascii=False)),
            )

    def _set_alert_status(self, *, alert_id: str, status: str, actor: str) -> bool:
        now = time.time()
        conn = self._connect()
        try:
            if status == "ACKED":
                cur = conn.execute("UPDATE alerts SET status = 'ACKED', acked_at = COALESCE(acked_at, ?) WHERE id = ?", (now, alert_id))
            else:
                cur = conn.execute("UPDATE alerts SET status = 'RESOLVED', resolved_at = ? WHERE id = ?", (now, alert_id))
            if cur.rowcount > 0:
                conn.execute(
                    "INSERT INTO events (ts, session_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
                    (now, None, "alert_status", json.dumps({"alert_id": alert_id, "status": status, "actor": actor}, ensure_ascii=False)),
                )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
