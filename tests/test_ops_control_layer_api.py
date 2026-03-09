import os
import sqlite3
import tempfile
import unittest
from contextlib import suppress
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import web_app


class OpsControlLayerApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "demo.db")

    def tearDown(self):
        self._reset_app_state()
        self.tmp.cleanup()

    def _reset_app_state(self):
        with suppress(Exception):
            task = getattr(web_app, "_report_scheduler_task", None)
            if task and not task.done():
                task.cancel()
        web_app._report_scheduler_task = None
        web_app._demo_state.clear()

    def _client(self) -> TestClient:
        os.environ["DEMO_DB_PATH"] = self.db_path
        os.environ["APP_ENV"] = "demo"
        os.environ["DEMO_MODE"] = "1"
        os.environ["PILOT_MODE"] = "1"
        os.environ["JWT_SECRET"] = "test-secret"
        os.environ["COOKIE_SECURE"] = "0"
        self._reset_app_state()
        return TestClient(web_app.app)

    @staticmethod
    def _login(client: TestClient, username: str, password: str) -> str:
        res = client.post("/api/auth/login", json={"username": username, "password": password})
        assert res.status_code == 200, res.text
        token = str(res.json().get("access_token") or "")
        assert token
        return token

    @staticmethod
    def _headers(token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "x-request-id": "req-test-ops-control",
        }

    def _seed_operating_data(self):
        demo = web_app._get_demo_singletons()
        campaign = demo["campaign_service"]
        workbench = demo["workbench"]
        audit = demo["audit"]
        followups = demo["followups"]
        alerts = demo["alerts"]

        created = campaign.create_campaign(
            name="Ops Control Demo",
            customer_ids=["OC-1", "OC-2", "OC-3"],
            max_attempts=2,
            retry_delay_minutes=15,
            batch_size=25,
        )
        campaign_id = created["campaign_id"]
        workbench.seed_tasks(
            campaign_id=campaign_id,
            portfolio_id="pfl-ops",
            rows=[
                {"customer_id": "OC-1", "customer_name": "Asha", "phone": "+919999999911", "amount_due": 1800, "dpd": 14},
                {"customer_id": "OC-2", "customer_name": "Rohan", "phone": "+919999999912", "amount_due": 4200, "dpd": 47},
                {"customer_id": "OC-3", "customer_name": "Meera", "phone": "+919999999913", "amount_due": 5100, "dpd": 54},
            ],
            actor="seed",
        )
        tasks = workbench.list_tasks(campaign_id=campaign_id, page=1, page_size=20)["rows"]
        task_by_customer = {row["customer_id"]: row for row in tasks}
        workbench.update_task(
            task_id=task_by_customer["OC-1"]["id"],
            actor="mgr",
            role="SUPERVISOR",
            state="PTP",
            ptp_date=(datetime.now() + timedelta(days=1)).date().isoformat(),
            disposition="ptp_captured",
        )
        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.now().timestamp()
            conn.execute(
                "INSERT INTO campaign_runs (campaign_id, customer_id, ts, attempt_no, outcome) VALUES (?, ?, ?, 1, 'completed')",
                (campaign_id, "OC-1", now),
            )
            conn.execute(
                "INSERT INTO campaign_runs (campaign_id, customer_id, ts, attempt_no, outcome) VALUES (?, ?, ?, 1, 'completed')",
                (campaign_id, "OC-2", now),
            )
            conn.execute(
                "INSERT INTO campaign_runs (campaign_id, customer_id, ts, attempt_no, outcome) VALUES (?, ?, ?, 1, 'completed')",
                (campaign_id, "OC-3", now),
            )
            conn.execute(
                "UPDATE tasks SET sla_due_at = strftime('%s','now') - 180 WHERE id = ?",
                (task_by_customer["OC-3"]["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        missed_ptp_date = (datetime.now() - timedelta(days=1)).date().isoformat()
        rows = followups.schedule_ptp_followups(
            session_id="sess-oc-3",
            customer_id="OC-3",
            ptp_date=missed_ptp_date,
            phone="+919999999913",
            channel="whatsapp",
        )
        miss = [row for row in rows if row["reminder_type"] == "ptp_t_plus_1_miss"][0]
        followups.mark_status(miss["idempotency_key"], status="missed")

        audit.upsert_outcome(
            session_id="sess-oc-1",
            customer_id="OC-1",
            campaign_id=campaign_id,
            dpd_bucket="1-30",
            strategy_mode="soft_reminder",
            tone_profile="empathetic",
            disposition="ptp_captured",
            ptp_date=(datetime.now() + timedelta(days=1)).date().isoformat(),
        )
        audit.update_outcome_agent(session_id="sess-oc-1", agent_id="mgr", connect_duration_s=55)
        audit.upsert_outcome(
            session_id="sess-oc-2",
            customer_id="OC-2",
            campaign_id=campaign_id,
            dpd_bucket="31-60",
            strategy_mode="firm_commitment",
            tone_profile="firm_respectful",
            disposition="callback_scheduled",
            callback_time="15:30",
        )
        audit.update_outcome_agent(session_id="sess-oc-2", agent_id="mgr", connect_duration_s=48)
        audit.upsert_outcome(
            session_id="sess-oc-3",
            customer_id="OC-3",
            campaign_id=campaign_id,
            dpd_bucket="31-60",
            strategy_mode="firm_commitment",
            tone_profile="firm_respectful",
            disposition="ptp_broken",
            ptp_date=missed_ptp_date,
        )
        audit.update_outcome_agent(session_id="sess-oc-3", agent_id="agent", connect_duration_s=34)

        audit.record_dpd_snapshot(customer_id="OC-2", dpd_value=45, dpd_bucket="31-60")
        audit.record_dpd_snapshot(customer_id="OC-2", dpd_value=64, dpd_bucket="61-90")
        audit.record_dpd_snapshot(customer_id="OC-3", dpd_value=52, dpd_bucket="31-60")
        audit.record_dpd_snapshot(customer_id="OC-3", dpd_value=58, dpd_bucket="31-60")

        alerts.evaluate()
        return campaign_id

    def test_control_layer_chat_and_actions(self):
        with self._client() as client:
            token = self._login(client, "mgr", "mgr123")
            campaign_id = self._seed_operating_data()

            response = client.post(
                "/api/control-layer/chat",
                json={
                    "campaign_id": campaign_id,
                    "message": "Which bucket is underperforming, why, and what should I change?",
                },
                headers=self._headers(token),
            )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["scope"]["campaign_id"], campaign_id)
            self.assertGreaterEqual(len(payload["evidence"]), 2)
            self.assertGreaterEqual(len(payload["recommendations"]), 1)
            self.assertIn("31-60", payload["answer"])

            first_rec = payload["recommendations"][0]
            exp_action = [row for row in first_rec["actions"] if row["action_type"] == "launch_experiment"][0]
            exp_response = client.post(
                "/api/control-layer/actions",
                json={"action_type": exp_action["action_type"], "payload": exp_action["payload"]},
                headers=self._headers(token),
            )
            self.assertEqual(exp_response.status_code, 200, exp_response.text)
            self.assertEqual(exp_response.json()["result_type"], "experiment_created")
            self.assertTrue(exp_response.json()["experiment"]["id"])

            strategy_action = [row for row in first_rec["actions"] if row["action_type"] == "request_strategy_change"][0]
            strategy_response = client.post(
                "/api/control-layer/actions",
                json={"action_type": strategy_action["action_type"], "payload": strategy_action["payload"]},
                headers=self._headers(token),
            )
            self.assertEqual(strategy_response.status_code, 200, strategy_response.text)
            self.assertEqual(strategy_response.json()["result_type"], "approval_queued")
            self.assertTrue(strategy_response.json()["approval"]["id"])

    def test_control_layer_launch_experiment_falls_back_to_approval_for_viewer(self):
        with self._client() as client:
            token = self._login(client, "viewer", "viewer123")
            self._seed_operating_data()
            response = client.post(
                "/api/control-layer/actions",
                json={
                    "action_type": "launch_experiment",
                    "payload": {
                        "name": "Viewer requested experiment",
                        "objective": "Improve 31-60 containment",
                        "control": "firm_commitment",
                        "treatment": "callback_salvage",
                        "split_ratio": 0.5,
                        "metadata": {"campaign_id": "cmp-demo", "bucket": "31-60"},
                    },
                },
                headers=self._headers(token),
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["result_type"], "approval_queued")
            self.assertTrue(response.json()["approval"]["id"])
