import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta

from audit_store import SQLiteAuditStore
from alerts_service import AlertsService
from campaign_service import CampaignService
from followup_service import FollowupService
from reports_service import ReportsService
from sync_service import SyncService
from workbench_service import WorkbenchService


class OpsLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = f"{self.tmp.name}/demo.db"
        self.data_dir = f"{self.tmp.name}/data"
        os.makedirs(self.data_dir, exist_ok=True)
        self.audit = SQLiteAuditStore(self.db_path)
        self.campaign = CampaignService(self.db_path)
        self.workbench = WorkbenchService(self.db_path)
        self.followups = FollowupService(self.db_path)
        self.alerts = AlertsService(self.db_path)
        self.reports = ReportsService(self.db_path, self.data_dir)
        self.sync = SyncService(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_task(self, campaign_id="cmp-test", customer_id="CUST001", amount_due=1000.0, dpd=10):
        created = self.workbench.seed_tasks(
            campaign_id=campaign_id,
            portfolio_id="pfl-test",
            rows=[
                {
                    "customer_id": customer_id,
                    "phone": "+919876543210",
                    "amount_due": amount_due,
                    "dpd": dpd,
                    "customer_name": "Demo Customer",
                }
            ],
            actor="tester",
        )
        self.assertEqual(created, 1)
        out = self.workbench.list_tasks(campaign_id=campaign_id, page=1, page_size=20)
        self.assertEqual(out["total"], 1)
        return out["rows"][0]["id"]

    def test_task_creation_on_campaign_seed(self):
        self.workbench.seed_tasks(
            campaign_id="cmp-a",
            portfolio_id="pfl-a",
            rows=[
                {"customer_id": "A1", "phone": "+919999999991", "amount_due": 100, "dpd": 11},
                {"customer_id": "A2", "phone": "+919999999992", "amount_due": 200, "dpd": 45},
            ],
            actor="seed",
        )
        rows = self.workbench.list_tasks(campaign_id="cmp-a", page=1, page_size=20)
        self.assertEqual(rows["total"], 2)

    def test_claim_lock(self):
        task_id = self._seed_task(campaign_id="cmp-claim", customer_id="C-LOCK")
        first = self.workbench.claim_task(task_id=task_id, actor="sup-1")
        second = self.workbench.claim_task(task_id=task_id, actor="sup-2")
        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(second["error"], "already_claimed")

    def test_bulk_update(self):
        self.workbench.seed_tasks(
            campaign_id="cmp-bulk",
            portfolio_id="pfl-b",
            rows=[
                {"customer_id": "B1", "phone": "+919999999981", "amount_due": 100, "dpd": 12},
                {"customer_id": "B2", "phone": "+919999999982", "amount_due": 200, "dpd": 18},
            ],
            actor="seed",
        )
        rows = self.workbench.list_tasks(campaign_id="cmp-bulk", page=1, page_size=20)["rows"]
        ids = [r["id"] for r in rows]

        assign = self.workbench.bulk_update(ids=ids, actor="sup", role="SUPERVISOR", action="assign", payload={"owner": "agent-1"})
        self.assertEqual(assign["updated"], 2)

        close = self.workbench.bulk_update(
            ids=ids,
            actor="sup",
            role="SUPERVISOR",
            action="close",
            payload={"disposition": "done", "notes": "bulk close"},
        )
        self.assertEqual(close["updated"], 2)
        out = self.workbench.list_tasks(campaign_id="cmp-bulk", page=1, page_size=20)
        self.assertTrue(all(r["state"] == "CLOSED" for r in out["rows"]))

    def test_sla_breach_flag(self):
        task_id = self._seed_task(campaign_id="cmp-sla", customer_id="C-SLA")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("UPDATE tasks SET sla_due_at = strftime('%s','now') - 30 WHERE id = ?", (task_id,))
            conn.commit()
        finally:
            conn.close()
        out = self.workbench.list_tasks(campaign_id="cmp-sla", page=1, page_size=20)
        self.assertTrue(out["rows"][0]["sla_breach"])

    def test_compliance_block_requires_override(self):
        task_id = self._seed_task(campaign_id="cmp-comp", customer_id="C-COMP")
        out = self.workbench.apply_session_gate_status(
            session_snapshot={
                "session_id": "sess-gate-1",
                "campaign_id": "cmp-comp",
                "customer_id": "C-COMP",
                "consent": False,
                "identity_confirmed": True,
            },
            actor="system",
        )
        self.assertEqual(out["updated"], 1)
        task = self.workbench.get_task(task_id)
        self.assertEqual(int(task["compliance_block"] or 0), 1)
        status = json.loads(task["compliance_status_json"] or "{}")
        self.assertEqual(status.get("CONSENT_OK"), False)

        blocked = self.workbench.update_task(
            task_id=task_id,
            actor="sup",
            role="SUPERVISOR",
            state="IN_PROGRESS",
            compliance_override=False,
        )
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["error"], "compliance_blocked_requires_override")

        eval_out = self.alerts.evaluate()
        self.assertGreaterEqual(eval_out["compliance_block"], 1)
        arows = self.alerts.list_alerts(status=None, severity=None, rtype="COMPLIANCE_BLOCK", page=1, page_size=20)
        self.assertGreaterEqual(arows["total"], 1)

        allowed = self.workbench.update_task(
            task_id=task_id,
            actor="sup",
            role="SUPERVISOR",
            state="IN_PROGRESS",
            compliance_override=True,
        )
        self.assertTrue(allowed["ok"])

    def test_ptp_miss_creates_alert(self):
        ptp_date = (datetime.now() - timedelta(days=1)).date().isoformat()
        rows = self.followups.schedule_ptp_followups(
            session_id="sess-ptp",
            customer_id="C-PTP",
            ptp_date=ptp_date,
            phone="+919876543219",
            channel="whatsapp",
        )
        miss = [r for r in rows if r["reminder_type"] == "ptp_t_plus_1_miss"][0]
        self.followups.mark_status(miss["idempotency_key"], status="missed")

        out = self.alerts.evaluate()
        self.assertGreaterEqual(out["ptp_miss"], 1)
        alerts = self.alerts.list_alerts(status=None, severity=None, rtype="PTP_MISS", page=1, page_size=20)
        self.assertGreaterEqual(alerts["total"], 1)

    def test_sla_breach_creates_alert(self):
        task_id = self._seed_task(campaign_id="cmp-alert-sla", customer_id="C-ALERT-SLA")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("UPDATE tasks SET sla_due_at = strftime('%s','now') - 60 WHERE id = ?", (task_id,))
            conn.commit()
        finally:
            conn.close()

        out = self.alerts.evaluate()
        self.assertGreaterEqual(out["sla_breach"], 1)
        alerts = self.alerts.list_alerts(status=None, severity=None, rtype="SLA_BREACH", page=1, page_size=20)
        self.assertGreaterEqual(alerts["total"], 1)

    def test_ack_resolve_flow(self):
        task_id = self._seed_task(campaign_id="cmp-alert-ack", customer_id="C-ACK")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("UPDATE tasks SET sla_due_at = strftime('%s','now') - 120 WHERE id = ?", (task_id,))
            conn.commit()
        finally:
            conn.close()

        self.alerts.evaluate()
        rows = self.alerts.list_alerts(status=None, severity=None, rtype="SLA_BREACH", page=1, page_size=20)["rows"]
        self.assertTrue(rows)
        alert_id = rows[0]["id"]
        self.assertTrue(self.alerts.ack_alert(alert_id=alert_id, actor="sup"))
        self.assertTrue(self.alerts.resolve_alert(alert_id=alert_id, actor="sup"))
        final = self.alerts.get_alert(alert_id)
        self.assertEqual(final["status"], "RESOLVED")

    def test_report_generation_outputs_files(self):
        created = self.campaign.create_campaign(name="report-c", customer_ids=["R1", "R2"], max_attempts=2, retry_delay_minutes=1, batch_size=20)
        campaign_id = created["campaign_id"]

        self.workbench.seed_tasks(
            campaign_id=campaign_id,
            portfolio_id="pfl-r",
            rows=[
                {"customer_id": "R1", "phone": "+919999999971", "amount_due": 1200, "dpd": 25},
                {"customer_id": "R2", "phone": "+919999999972", "amount_due": 2200, "dpd": 75},
            ],
            actor="seed",
        )
        tasks = self.workbench.list_tasks(campaign_id=campaign_id, page=1, page_size=20)["rows"]
        self.workbench.update_task(task_id=tasks[0]["id"], actor="sup", role="SUPERVISOR", state="PTP", disposition="ptp")
        self.workbench.update_task(
            task_id=tasks[1]["id"],
            actor="sup",
            role="SUPERVISOR",
            state="ESCALATED",
            disposition="escalated",
            escalate_reason="hardship",
        )

        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.now().timestamp()
            conn.execute(
                "INSERT INTO campaign_runs (campaign_id, customer_id, ts, attempt_no, outcome) VALUES (?, ?, ?, 1, 'completed')",
                (campaign_id, "R1", now),
            )
            conn.execute(
                "INSERT INTO campaign_runs (campaign_id, customer_id, ts, attempt_no, outcome) VALUES (?, ?, ?, 1, 'failed')",
                (campaign_id, "R2", now),
            )
            conn.commit()
        finally:
            conn.close()

        report = self.reports.generate_report(campaign_id=campaign_id, report_date="2026-02-10")
        self.assertTrue(os.path.exists(report["path_json"]))
        self.assertTrue(os.path.exists(report["path_csv"]))

        summary = json.loads(report["summary_json"])
        self.assertIn("connected_rate", summary["totals"])
        self.assertIn("ptp_conversion", summary["totals"])
        self.assertIn("expected_recovery_amount", summary["totals"])
        self.assertIn("bucket_heatmap", summary)
        self.assertIn("top_5_escalation_reasons", summary)

    def test_reports_endpoint_lists_and_downloads(self):
        created = self.campaign.create_campaign(name="report-d", customer_ids=["RD1"], max_attempts=2, retry_delay_minutes=1, batch_size=20)
        row = self.reports.generate_report(campaign_id=created["campaign_id"], report_date="2026-02-11")
        listing = self.reports.list_reports(page=1, page_size=20)
        self.assertGreaterEqual(listing["total"], 1)
        fetched = self.reports.get_report(row["id"])
        self.assertIsNotNone(fetched)
        self.assertTrue(os.path.exists(fetched["path_json"]))
        self.assertTrue(os.path.exists(fetched["path_csv"]))

    def test_inbound_creates_event(self):
        self._seed_task(campaign_id="cmp-sync", customer_id="SYNC1")
        callback_at = (datetime.now() + timedelta(hours=2)).isoformat()
        out = self.sync.inbound_lms(
            {
                "customer_id": "SYNC1",
                "payment_status": "",
                "callback_at": callback_at,
                "external_ref": "lms-1",
            },
            actor="lms",
        )
        self.assertTrue(out["ok"])
        events = self.sync.list_sync_events(direction="inbound", status=None, page=1, page_size=20)
        self.assertGreaterEqual(events["total"], 1)

    def test_conflict_detected(self):
        self._seed_task(campaign_id="cmp-sync2", customer_id="SYNC2", amount_due=1000)
        out = self.sync.inbound_lms(
            {
                "customer_id": "SYNC2",
                "payment_status": "PAID",
                "paid_amount": 800,
                "paid_at": datetime.now().isoformat(),
                "external_ref": "lms-2",
            },
            actor="lms",
        )
        self.assertEqual(out["status"], "conflict")
        conflicts = self.sync.list_conflicts(status="OPEN", page=1, page_size=20)
        self.assertGreaterEqual(conflicts["total"], 1)

    def test_inbound_dispute_routes_escalated_conflict(self):
        task_id = self._seed_task(campaign_id="cmp-sync3", customer_id="SYNC3", amount_due=1000)
        out = self.sync.inbound_lms(
            {
                "customer_id": "SYNC3",
                "payment_status": "DISPUTE",
                "paid_amount": 0,
                "external_ref": "lms-3",
            },
            actor="lms",
        )
        self.assertEqual(out["status"], "conflict")
        task = self.workbench.get_task(task_id)
        self.assertEqual(task["state"], "ESCALATED")

    def test_resolution_trust_lms_applies_update(self):
        task_id = self._seed_task(campaign_id="cmp-sync4", customer_id="SYNC4", amount_due=1000)
        created = self.sync.inbound_lms(
            {
                "customer_id": "SYNC4",
                "payment_status": "PAID",
                "paid_amount": 1000,
                "paid_at": datetime.now().isoformat(),
                "external_ref": "lms-4",
            },
            actor="lms",
        )
        self.assertEqual(created["status"], "conflict")
        resolved = self.sync.resolve_conflict(conflict_id=created["conflict_id"], action="TRUST_LMS", resolved_by="sup")
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["source_of_truth"], "LMS")

        task = self.workbench.get_task(task_id)
        self.assertEqual(task["state"], "CLOSED")
        events = [e for e in task["events"] if e["event_type"] == "sync_conflict_resolved"]
        self.assertTrue(events)


if __name__ == "__main__":
    unittest.main()
