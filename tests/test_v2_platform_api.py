import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from contextlib import suppress

from fastapi.testclient import TestClient

import web_app


class V2PlatformApiTests(unittest.TestCase):
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

    def _client(self, *, webhook_secret: str | None = None) -> TestClient:
        os.environ["DEMO_DB_PATH"] = self.db_path
        os.environ["APP_ENV"] = "demo"
        os.environ["DEMO_MODE"] = "1"
        os.environ["PILOT_MODE"] = "1"
        os.environ["JWT_SECRET"] = "test-secret"
        os.environ["COOKIE_SECURE"] = "0"
        if webhook_secret:
            os.environ["V2_WEBHOOK_SECRET"] = webhook_secret
        else:
            os.environ.pop("V2_WEBHOOK_SECRET", None)
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
    def _headers(token: str, tenant_id: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "x-tenant-id": tenant_id,
            "x-request-id": "req-test-v2",
        }

    @staticmethod
    def _webhook_headers(*, secret: str, body_text: str, timestamp: int | None = None) -> dict:
        ts = int(time.time()) if timestamp is None else int(timestamp)
        signed = f"{ts}.{body_text}".encode("utf-8")
        sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        return {
            "x-webhook-timestamp": str(ts),
            "x-webhook-signature": sig,
            "content-type": "application/json",
        }

    def test_v2_tenant_journey_channel_payment_and_settlement_flow(self):
        with self._client() as client:
            admin_token = self._login(client, "admin", "admin123")

            create_tenant = client.post(
                "/api/v2/tenants",
                json={"tenant_id": "alpha", "name": "Alpha NBFC", "settings": {"timezone": "Asia/Kolkata"}},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            self.assertEqual(create_tenant.status_code, 200, create_tenant.text)
            self.assertEqual(create_tenant.json()["tenant"]["tenant_id"], "alpha")

            patch_settings = client.patch(
                "/api/v2/tenants/alpha/settings",
                json={"settings": {"channels": {"voice": True, "whatsapp": True, "sms": True, "email": True}}},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            self.assertEqual(patch_settings.status_code, 200, patch_settings.text)

            headers = self._headers(admin_token, "alpha")
            imported = client.post(
                "/api/v2/customers/import",
                json={
                    "rows": [
                        {
                            "customer_id": "CUST-ALPHA-1",
                            "full_name": "Asha Rao",
                            "phone": "+919999999901",
                            "email": "asha@example.com",
                            "dpd": 54,
                            "risk_band": "MEDIUM",
                        }
                    ]
                },
                headers=headers,
            )
            self.assertEqual(imported.status_code, 200, imported.text)
            self.assertEqual(imported.json()["result"]["inserted"], 1)

            loan = client.post(
                "/api/v2/loan_accounts/upsert",
                json={
                    "loan_account_id": "LN-ALPHA-1",
                    "customer_id": "CUST-ALPHA-1",
                    "principal_outstanding": 25000,
                    "emi_amount": 3200,
                    "dpd": 54,
                    "status": "ACTIVE",
                    "product_type": "PL",
                },
                headers=headers,
            )
            self.assertEqual(loan.status_code, 200, loan.text)
            self.assertEqual(loan.json()["loan_account"]["loan_account_id"], "LN-ALPHA-1")

            start = client.post(
                "/api/v2/journeys/start",
                json={
                    "customer_id": "CUST-ALPHA-1",
                    "loan_account_id": "LN-ALPHA-1",
                    "channel_hint": "whatsapp",
                    "context": {"bucket": "31-60"},
                },
                headers=headers,
            )
            self.assertEqual(start.status_code, 200, start.text)
            journey = start.json()["journey"]
            journey_id = journey["id"]

            sent = client.post(
                "/api/v2/channels/send",
                json={
                    "journey_id": journey_id,
                    "customer_id": "CUST-ALPHA-1",
                    "loan_account_id": "LN-ALPHA-1",
                    "channel": "whatsapp",
                    "content": "Your EMI is overdue. Can we help you close today?",
                },
                headers=headers,
            )
            self.assertEqual(sent.status_code, 200, sent.text)
            self.assertEqual(sent.json()["message"]["direction"], "outbound")

            listed = client.get("/api/v2/channels/messages?customer_id=CUST-ALPHA-1", headers=headers)
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertGreaterEqual(listed.json()["total"], 1)

            intent_resp = client.post(
                "/api/v2/payments/intents",
                json={
                    "customer_id": "CUST-ALPHA-1",
                    "loan_account_id": "LN-ALPHA-1",
                    "journey_id": journey_id,
                    "amount": 3200,
                    "currency": "INR",
                    "rail": "upi",
                },
                headers=headers,
            )
            self.assertEqual(intent_resp.status_code, 200, intent_resp.text)
            intent_id = intent_resp.json()["payment_intent"]["id"]

            webhook = client.post(
                "/api/v2/payments/webhooks/upi",
                json={
                    "tenant_id": "alpha",
                    "provider_event_id": "evt-pay-1",
                    "payment_intent_id": intent_id,
                    "status": "success",
                    "event_type": "payment.captured",
                },
            )
            self.assertEqual(webhook.status_code, 200, webhook.text)
            self.assertEqual(webhook.json()["event"]["status"], "SUCCEEDED")

            offer_resp = client.post(
                "/api/v2/settlements/offers",
                json={
                    "customer_id": "CUST-ALPHA-1",
                    "loan_account_id": "LN-ALPHA-1",
                    "journey_id": journey_id,
                    "offered_amount": 21000,
                    "original_due_amount": 25000,
                    "terms": {"installments": 2},
                },
                headers=headers,
            )
            self.assertEqual(offer_resp.status_code, 200, offer_resp.text)
            offer_id = offer_resp.json()["offer"]["id"]

            accept_resp = client.post(
                f"/api/v2/settlements/{offer_id}/accept",
                json={"accepted_amount": 21000, "acceptance_channel": "voice"},
                headers=headers,
            )
            self.assertEqual(accept_resp.status_code, 200, accept_resp.text)
            self.assertEqual(accept_resp.json()["offer"]["status"], "ACCEPTED")

            c360 = client.get("/api/v2/customers/CUST-ALPHA-1/360", headers=headers)
            self.assertEqual(c360.status_code, 200, c360.text)
            payload = c360.json()
            self.assertEqual(payload["customer_id"], "CUST-ALPHA-1")
            self.assertGreaterEqual(len(payload["loan_accounts"]), 1)
            self.assertGreaterEqual(len(payload["channel_messages"]), 1)
            self.assertGreaterEqual(len(payload["payment_intents"]), 1)
            self.assertGreaterEqual(len(payload["settlement_offers"]), 1)

            wrong_tenant = client.get(
                f"/api/v2/journeys/{journey_id}",
                headers=self._headers(admin_token, "default"),
            )
            self.assertEqual(wrong_tenant.status_code, 404)

    def test_v2_recovery_experiments_and_approval_queue(self):
        with self._client() as client:
            admin_token = self._login(client, "admin", "admin123")
            create_tenant = client.post(
                "/api/v2/tenants",
                json={"tenant_id": "beta", "name": "Beta Finance"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            self.assertEqual(create_tenant.status_code, 200, create_tenant.text)

            headers = self._headers(admin_token, "beta")

            exp_resp = client.post(
                "/api/v2/recovery/experiments",
                json={
                    "name": "Settlement Offer Message Test",
                    "objective": "Improve commitment conversion",
                    "control": "control",
                    "treatment": "new_offer_copy",
                    "split_ratio": 0.5,
                    "unit_id": "CUST-BETA-1",
                },
                headers=headers,
            )
            self.assertEqual(exp_resp.status_code, 200, exp_resp.text)
            experiment_id = exp_resp.json()["experiment"]["id"]
            self.assertIsNotNone(exp_resp.json()["assignment"])

            decide = client.post(
                "/api/v2/recovery/nba/decide",
                json={
                    "customer_id": "CUST-BETA-1",
                    "loan_account_id": "LN-BETA-1",
                    "journey_id": "JNY-BETA-1",
                    "experiment_id": experiment_id,
                    "amount_due": 50000,
                    "features": {
                        "dpd": 132,
                        "amount_due": 50000,
                        "hardship": True,
                        "last_outcome": "no_answer",
                    },
                },
                headers=headers,
            )
            self.assertEqual(decide.status_code, 200, decide.text)
            decision = decide.json()["decision"]
            self.assertTrue(decision["approval_required"])
            approval_id = decision.get("approval_id")
            self.assertTrue(approval_id)

            queue = client.get("/api/v2/approvals/queue?status=PENDING", headers=headers)
            self.assertEqual(queue.status_code, 200, queue.text)
            self.assertGreaterEqual(queue.json()["total"], 1)

            approve = client.post(
                f"/api/v2/approvals/{approval_id}/approve",
                json={"note": "Risk reviewed by supervisor"},
                headers=headers,
            )
            self.assertEqual(approve.status_code, 200, approve.text)
            self.assertEqual(approve.json()["approval"]["status"], "APPROVED")

            uplift = client.get(f"/api/v2/recovery/uplift?experiment_id={experiment_id}", headers=headers)
            self.assertEqual(uplift.status_code, 200, uplift.text)
            self.assertEqual(uplift.json()["tenant_id"], "beta")
            self.assertGreaterEqual(len(uplift.json()["snapshots"]), 1)

    def test_webhook_signature_validation_and_replay_protection(self):
        secret = "test-hook-secret"
        with self._client(webhook_secret=secret) as client:
            admin_token = self._login(client, "admin", "admin123")
            create_tenant = client.post(
                "/api/v2/tenants",
                json={"tenant_id": "alpha", "name": "Alpha NBFC"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            self.assertEqual(create_tenant.status_code, 200, create_tenant.text)
            headers = self._headers(admin_token, "alpha")
            intent_resp = client.post(
                "/api/v2/payments/intents",
                json={
                    "customer_id": "CUST-ALPHA-1",
                    "loan_account_id": "LN-ALPHA-1",
                    "journey_id": "JNY-ALPHA-1",
                    "amount": 3200,
                    "currency": "INR",
                    "rail": "upi",
                },
                headers=headers,
            )
            self.assertEqual(intent_resp.status_code, 200, intent_resp.text)
            intent_id = intent_resp.json()["payment_intent"]["id"]

            payload = {
                "tenant_id": "alpha",
                "provider_event_id": "evt-pay-42",
                "payment_intent_id": intent_id,
                "status": "success",
                "event_type": "payment.captured",
            }
            body_text = json.dumps(payload, separators=(",", ":"))

            bad_sig = client.post(
                "/api/v2/payments/webhooks/upi",
                data=body_text,
                headers={
                    "x-webhook-timestamp": str(int(time.time())),
                    "x-webhook-signature": "deadbeef",
                    "content-type": "application/json",
                },
            )
            self.assertEqual(bad_sig.status_code, 401, bad_sig.text)

            stale = client.post(
                "/api/v2/payments/webhooks/upi",
                data=body_text,
                headers=self._webhook_headers(secret=secret, body_text=body_text, timestamp=int(time.time()) - 301),
            )
            self.assertEqual(stale.status_code, 401, stale.text)

            ok = client.post(
                "/api/v2/payments/webhooks/upi",
                data=body_text,
                headers=self._webhook_headers(secret=secret, body_text=body_text),
            )
            self.assertEqual(ok.status_code, 200, ok.text)

            replay = client.post(
                "/api/v2/payments/webhooks/upi",
                data=body_text,
                headers=self._webhook_headers(secret=secret, body_text=body_text),
            )
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertTrue(bool(replay.json().get("deduplicated")))

    def test_metrics_read_only_and_ops_tick_mutates(self):
        with self._client() as client:
            admin_token = self._login(client, "admin", "admin123")
            auth = {"Authorization": f"Bearer {admin_token}"}
            demo = web_app._get_demo_singletons()
            followups = demo["followups"]
            followups.schedule_ptp_followups(
                session_id="sess-metrics-1",
                customer_id="CUST-METRICS-1",
                ptp_date="2000-01-01",
                phone="+919999999999",
                channel="whatsapp",
            )
            due_before = followups.due_followups(limit=20)
            self.assertGreaterEqual(len(due_before), 1)

            metrics = client.get("/api/metrics", headers=auth)
            self.assertEqual(metrics.status_code, 200, metrics.text)
            due_after_metrics = followups.due_followups(limit=20)
            self.assertEqual(len(due_after_metrics), len(due_before))

            tick = client.post("/api/ops/tick", headers=auth)
            self.assertEqual(tick.status_code, 200, tick.text)
            due_after_tick = followups.due_followups(limit=20)
            self.assertEqual(len(due_after_tick), 0)


if __name__ == "__main__":
    unittest.main()
