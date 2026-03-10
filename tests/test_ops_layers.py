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
from payment_orchestration_service import PaymentOrchestrationService
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
        self.payments = PaymentOrchestrationService(self.db_path)
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

    def test_metrics_surface_buyer_demo_fields(self):
        created = self.campaign.create_campaign(name="Buyer Demo", customer_ids=["MD1", "MD2"], max_attempts=2, retry_delay_minutes=15, batch_size=25)
        campaign_id = created["campaign_id"]
        self.workbench.seed_tasks(
            campaign_id=campaign_id,
            portfolio_id="pfl-demo",
            rows=[
                {"customer_id": "MD1", "phone": "+919999999971", "amount_due": 1800, "dpd": 14, "customer_name": "Metric One"},
                {"customer_id": "MD2", "phone": "+919999999972", "amount_due": 2600, "dpd": 42, "customer_name": "Metric Two"},
            ],
            actor="seed",
        )
        rows = self.workbench.list_tasks(campaign_id=campaign_id, page=1, page_size=20)["rows"]
        task_by_customer = {row["customer_id"]: row for row in rows}
        self.workbench.update_task(
            task_id=task_by_customer["MD1"]["id"],
            actor="mgr",
            role="SUPERVISOR",
            state="PTP",
            ptp_date="2026-02-10",
            disposition="ptp_captured",
        )

        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.now().timestamp()
            conn.execute(
                "INSERT INTO campaign_runs (campaign_id, customer_id, ts, attempt_no, outcome) VALUES (?, ?, ?, 1, 'completed')",
                (campaign_id, "MD1", now),
            )
            conn.execute(
                "INSERT INTO campaign_runs (campaign_id, customer_id, ts, attempt_no, outcome) VALUES (?, ?, ?, 1, 'completed')",
                (campaign_id, "MD2", now),
            )
            conn.execute(
                "UPDATE tasks SET sla_due_at = strftime('%s','now') - 30 WHERE id = ?",
                (task_by_customer["MD2"]["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        ptp_date = (datetime.now() - timedelta(days=1)).date().isoformat()
        rows = self.followups.schedule_ptp_followups(
            session_id="sess-metrics-demo",
            customer_id="MD1",
            ptp_date=ptp_date,
            phone="+919999999971",
            channel="whatsapp",
        )
        miss = [r for r in rows if r["reminder_type"] == "ptp_t_plus_1_miss"][0]
        self.followups.mark_status(miss["idempotency_key"], status="missed")

        self.audit.upsert_outcome(
            session_id="sess-metrics-demo",
            customer_id="MD1",
            campaign_id=campaign_id,
            dpd_bucket="1-30",
            disposition="ptp_captured",
            ptp_date=ptp_date,
        )
        self.audit.upsert_outcome(
            session_id="sess-metrics-demo-2",
            customer_id="MD2",
            campaign_id=campaign_id,
            dpd_bucket="31-60",
            disposition="callback_scheduled",
            callback_time="15:00",
        )

        self.alerts.evaluate()
        metrics = self.audit.metrics(campaign_id=campaign_id)

        self.assertEqual(metrics["accounts_assigned"], 2)
        self.assertEqual(metrics["accounts_contacted"], 2)
        self.assertGreater(metrics["contact_rate_pct"], 0)
        self.assertEqual(metrics["bucket_heatmap"]["1-30"], 1)
        self.assertEqual(metrics["bucket_heatmap"]["31-60"], 1)
        self.assertEqual(metrics["queue_snapshot"]["PTP"], 1)
        self.assertGreater(metrics["expected_recovery_amount"], 0)
        self.assertGreaterEqual(metrics["sla_breaches"], 1)
        self.assertGreaterEqual(metrics["followups_due_today"], 1)
        self.assertGreaterEqual(metrics["followups_completed_today"], 1)
        self.assertGreater(metrics["followup_discipline_rate_pct"], 0)
        self.assertGreaterEqual(metrics["ptp_miss_count"], 1)
        self.assertGreaterEqual(metrics["ptp_miss_open_alerts"], 1)

    def test_command_center_scope_filters_apply_across_metrics_layers(self):
        created = self.campaign.create_campaign(
            name="Scoped Metrics",
            customer_ids=["SCOPE-PTP", "OTHER-STATE", "OTHER-BUCKET"],
            max_attempts=2,
            retry_delay_minutes=15,
            batch_size=25,
        )
        campaign_id = created["campaign_id"]
        self.workbench.seed_tasks(
            campaign_id=campaign_id,
            portfolio_id="pfl-scope",
            rows=[
                {"customer_id": "SCOPE-PTP", "phone": "+919999999961", "amount_due": 1500, "dpd": 46, "customer_name": "Scope PTP"},
                {"customer_id": "OTHER-STATE", "phone": "+919999999962", "amount_due": 2200, "dpd": 47, "customer_name": "Other State"},
                {"customer_id": "OTHER-BUCKET", "phone": "+919999999963", "amount_due": 900, "dpd": 18, "customer_name": "Other Bucket"},
            ],
            actor="seed",
        )
        rows = self.workbench.list_tasks(campaign_id=campaign_id, page=1, page_size=20)["rows"]
        task_by_customer = {row["customer_id"]: row for row in rows}

        self.workbench.update_task(
            task_id=task_by_customer["SCOPE-PTP"]["id"],
            actor="mgr",
            role="SUPERVISOR",
            state="PTP",
            ptp_date="2026-03-15",
            disposition="ptp_captured",
        )
        self.workbench.update_task(
            task_id=task_by_customer["OTHER-BUCKET"]["id"],
            actor="mgr",
            role="SUPERVISOR",
            state="PTP",
            ptp_date="2026-03-16",
            disposition="ptp_captured",
        )

        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.now().timestamp()
            for customer_id in ("SCOPE-PTP", "OTHER-STATE", "OTHER-BUCKET"):
                conn.execute(
                    "INSERT INTO campaign_runs (campaign_id, customer_id, ts, attempt_no, outcome) VALUES (?, ?, ?, 1, 'completed')",
                    (campaign_id, customer_id, now),
                )
            conn.commit()
        finally:
            conn.close()

        self.audit.upsert_outcome(
            session_id="sess-scope-1",
            start_ts=1.0,
            end_ts=5.0,
            customer_id="SCOPE-PTP",
            campaign_id=campaign_id,
            dpd_bucket="31-60",
            disposition="ptp_captured",
            ptp_date="2026-03-15",
        )
        self.audit.upsert_outcome(
            session_id="sess-scope-2",
            start_ts=2.0,
            end_ts=7.0,
            customer_id="OTHER-STATE",
            campaign_id=campaign_id,
            dpd_bucket="31-60",
            disposition="contacted",
        )
        self.audit.upsert_outcome(
            session_id="sess-scope-3",
            start_ts=3.0,
            end_ts=8.0,
            customer_id="OTHER-BUCKET",
            campaign_id=campaign_id,
            dpd_bucket="1-30",
            disposition="ptp_captured",
            ptp_date="2026-03-16",
        )
        self.audit.update_outcome_agent(session_id="sess-scope-1", agent_id="agent-scope")
        self.audit.update_outcome_agent(session_id="sess-scope-2", agent_id="agent-other-state")
        self.audit.update_outcome_agent(session_id="sess-scope-3", agent_id="agent-other-bucket")

        self.audit.record_dpd_snapshot(customer_id="SCOPE-PTP", dpd_bucket="1-30", dpd_value=18, source="test")
        self.audit.record_dpd_snapshot(customer_id="SCOPE-PTP", dpd_bucket="31-60", dpd_value=46, source="test")
        self.audit.record_dpd_snapshot(customer_id="OTHER-STATE", dpd_bucket="1-30", dpd_value=18, source="test")
        self.audit.record_dpd_snapshot(customer_id="OTHER-STATE", dpd_bucket="31-60", dpd_value=47, source="test")
        self.audit.record_dpd_snapshot(customer_id="OTHER-BUCKET", dpd_bucket="0", dpd_value=0, source="test")
        self.audit.record_dpd_snapshot(customer_id="OTHER-BUCKET", dpd_bucket="1-30", dpd_value=18, source="test")

        self.payments.create_intent(
            tenant_id="tenant-1",
            actor="tester",
            request_id="req-scope-1",
            payload={"customer_id": "SCOPE-PTP", "amount": 1500, "currency": "INR", "rail": "upi", "status": "SUCCEEDED"},
        )
        self.payments.create_intent(
            tenant_id="tenant-1",
            actor="tester",
            request_id="req-scope-2",
            payload={"customer_id": "OTHER-STATE", "amount": 2200, "currency": "INR", "rail": "upi", "status": "SUCCEEDED"},
        )

        metrics = self.audit.metrics(campaign_id=campaign_id, state="PTP", dpd_bucket="31-60")
        roll_forward = self.audit.roll_forward_matrix(days=30, campaign_id=campaign_id, state="PTP", dpd_bucket="31-60")
        recovery = self.audit.realized_recovery_trend(days=30, campaign_id=campaign_id, state="PTP", dpd_bucket="31-60")
        agents = self.audit.agent_metrics(campaign_id=campaign_id, state="PTP", dpd_bucket="31-60")
        summary = self.workbench.summary_by_state(campaign_id=campaign_id, state="PTP", dpd_bucket="31-60")

        self.assertEqual(metrics["accounts_assigned"], 1)
        self.assertEqual(metrics["accounts_contacted"], 1)
        self.assertEqual(metrics["bucket_heatmap"]["31-60"], 1)
        self.assertEqual(metrics["bucket_heatmap"]["1-30"], 0)
        self.assertEqual(metrics["queue_snapshot"]["PTP"], 1)
        self.assertEqual(metrics["ptp_count"], 1)
        self.assertEqual(metrics["expected_recovery_amount"], 1500.0)
        self.assertEqual(roll_forward["total_transitions"], 1)
        self.assertEqual(roll_forward["matrix"]["1-30"]["31-60"], 1)
        self.assertEqual(recovery["total_recovered"], 1500.0)
        self.assertEqual(recovery["portfolio_value"], 1500.0)
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["agent_id"], "agent-scope")
        self.assertEqual(summary["PTP"], 1)
        self.assertEqual(sum(summary.values()), 1)

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
