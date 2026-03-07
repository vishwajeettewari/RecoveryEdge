import os
import tempfile
import time
import unittest
from contextlib import suppress

from fastapi.testclient import TestClient

import web_app


class AuthRBACTests(unittest.TestCase):
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

    def _client(self, *, pilot_mode: bool = False) -> TestClient:
        os.environ["DEMO_DB_PATH"] = self.db_path
        os.environ["APP_ENV"] = "demo"
        os.environ["DEMO_MODE"] = "1"
        os.environ["PILOT_MODE"] = "1" if pilot_mode else "0"
        os.environ["JWT_SECRET"] = "test-secret"
        os.environ["COOKIE_SECURE"] = "0"
        self._reset_app_state()
        return TestClient(web_app.app)

    @staticmethod
    def _login(client: TestClient, username: str, password: str) -> str:
        res = client.post("/api/auth/login", json={"username": username, "password": password})
        assert res.status_code == 200, res.text
        return str(res.json().get("access_token") or "")

    def test_login_success_and_failure(self):
        with self._client() as client:
            ok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            self.assertEqual(ok.status_code, 200)
            self.assertTrue(ok.json().get("access_token"))
            bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
            self.assertEqual(bad.status_code, 401)

    def test_permission_denial_for_portfolio_manage(self):
        with self._client() as client:
            ceo_token = self._login(client, "ceo", "ceo123")
            headers = {"Authorization": f"Bearer {ceo_token}"}
            view = client.get("/api/reports", headers=headers)
            self.assertEqual(view.status_code, 200)

            restricted = client.post("/api/reports/schedule", json={"enabled": True, "daily_time": "09:00"}, headers=headers)
            self.assertEqual(restricted.status_code, 403)

    def test_role_can_and_cannot_mutate_workbench(self):
        with self._client() as client:
            demo = web_app._get_demo_singletons()
            workbench = demo["workbench"]
            workbench.seed_tasks(
                campaign_id="cmp-auth",
                portfolio_id="pfl-auth",
                rows=[{"customer_id": "AUTH001", "phone": "+919876543210", "amount_due": 1234, "dpd": 25}],
                actor="seed",
            )
            task_id = workbench.list_tasks(campaign_id="cmp-auth", page=1, page_size=10)["rows"][0]["id"]

            agent_token = self._login(client, "agent", "agent123")
            mgr_token = self._login(client, "mgr", "mgr123")
            cfo_token = self._login(client, "cfo", "cfo123")

            agent_update = client.post(
                f"/api/tasks/{task_id}/update",
                json={"state": "IN_PROGRESS", "disposition": "wip"},
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            self.assertEqual(agent_update.status_code, 200)

            cfo_update = client.post(
                f"/api/tasks/{task_id}/update",
                json={"state": "CLOSED", "disposition": "done"},
                headers={"Authorization": f"Bearer {cfo_token}"},
            )
            self.assertEqual(cfo_update.status_code, 403)

            mgr_claim = client.post(
                f"/api/tasks/{task_id}/claim",
                headers={"Authorization": f"Bearer {mgr_token}"},
            )
            self.assertIn(mgr_claim.status_code, (200, 409))

    def test_integrations_gated_by_pilot_mode(self):
        with self._client(pilot_mode=False) as client:
            mgr = self._login(client, "mgr", "mgr123")
            blocked = client.get("/api/integrations/conflicts", headers={"Authorization": f"Bearer {mgr}"})
            self.assertEqual(blocked.status_code, 403)
            self.assertIn("pilot_mode_disabled", blocked.text)

        with self._client(pilot_mode=True) as client:
            mgr = self._login(client, "mgr", "mgr123")
            allowed = client.get("/api/integrations/conflicts", headers={"Authorization": f"Bearer {mgr}"})
            self.assertEqual(allowed.status_code, 200)
            self.assertIn("rows", allowed.json())

    def test_calling_agent_scoped_to_assigned_tasks_only(self):
        with self._client() as client:
            demo = web_app._get_demo_singletons()
            workbench = demo["workbench"]
            workbench.seed_tasks(
                campaign_id="cmp-scope",
                portfolio_id="pfl-scope",
                rows=[
                    {"customer_id": "SCOPE001", "phone": "+919900000001", "amount_due": 1000, "dpd": 20},
                    {"customer_id": "SCOPE002", "phone": "+919900000002", "amount_due": 1400, "dpd": 45},
                ],
                actor="seed",
            )
            rows = workbench.list_tasks(campaign_id="cmp-scope", page=1, page_size=10)["rows"]
            first_id = rows[0]["id"]
            second_id = rows[1]["id"]
            workbench._assign_owner(task_id=first_id, owner="agent", actor="seed")
            workbench._assign_owner(task_id=second_id, owner="mgr", actor="seed")

            agent = self._login(client, "agent", "agent123")
            headers = {"Authorization": f"Bearer {agent}"}

            scoped = client.get("/api/tasks?campaign_id=cmp-scope", headers=headers)
            self.assertEqual(scoped.status_code, 200)
            payload = scoped.json()
            self.assertEqual(len(payload.get("rows") or []), 1)
            self.assertEqual((payload.get("rows") or [])[0]["owner"], "agent")

            forbidden = client.get(f"/api/tasks/{second_id}", headers=headers)
            self.assertEqual(forbidden.status_code, 403)

            bulk = client.post(
                "/api/tasks/bulk_update",
                json={"ids": [first_id], "action": "close", "payload": {"disposition": "done"}},
                headers=headers,
            )
            self.assertEqual(bulk.status_code, 403)

    def test_telephony_test_call_endpoint_queues_call(self):
        with self._client() as client:
            agent_token = self._login(client, "agent", "agent123")
            demo = web_app._get_demo_singletons()
            router = demo["router"]

            original = router.place_test_voice_call

            def fake_voice_call(**_: object):
                return {
                    "provider": "twilio",
                    "delivery_ok": True,
                    "delivery_status": "queued",
                    "call_sid": "CA_TEST_123",
                    "call_status": "queued",
                    "normalized_to": "+919950022999",
                }

            router.place_test_voice_call = fake_voice_call  # type: ignore[method-assign]
            try:
                out = client.post(
                    "/api/telephony/test_call",
                    json={"phone": "+91-9950022999", "customer_name": "Test User", "amount_due": "1200"},
                    headers={"Authorization": f"Bearer {agent_token}"},
                )
                self.assertEqual(out.status_code, 200, out.text)
                payload = out.json()
                self.assertTrue(payload.get("ok"))
                self.assertEqual(((payload.get("result") or {}).get("call_sid")), "CA_TEST_123")
            finally:
                router.place_test_voice_call = original  # type: ignore[method-assign]

    def test_telephony_agent_call_endpoint_queues_call(self):
        with self._client() as client:
            agent_token = self._login(client, "agent", "agent123")
            demo = web_app._get_demo_singletons()
            router = demo["router"]

            original = router.place_agent_stream_call
            prev_stream_ws = os.environ.get("TELEPHONY_STREAM_WSS_URL")

            def fake_agent_voice_call(**_: object):
                return {
                    "provider": "twilio",
                    "delivery_ok": True,
                    "delivery_status": "queued",
                    "call_sid": "CA_AGENT_123",
                    "call_status": "queued",
                    "normalized_to": "+919950022999",
                    "stream_ws_url": "wss://example.ngrok-free.app/ws/twilio-media",
                }

            router.place_agent_stream_call = fake_agent_voice_call  # type: ignore[method-assign]
            os.environ["TELEPHONY_STREAM_WSS_URL"] = "wss://example.ngrok-free.app/ws/twilio-media"
            try:
                out = client.post(
                    "/api/telephony/agent_call",
                    json={"phone": "+91-9950022999", "customer_name": "Test User", "amount_due": "1200"},
                    headers={"Authorization": f"Bearer {agent_token}"},
                )
                self.assertEqual(out.status_code, 200, out.text)
                payload = out.json()
                self.assertTrue(payload.get("ok"))
                self.assertEqual(((payload.get("result") or {}).get("call_sid")), "CA_AGENT_123")
            finally:
                router.place_agent_stream_call = original  # type: ignore[method-assign]
                if prev_stream_ws is None:
                    os.environ.pop("TELEPHONY_STREAM_WSS_URL", None)
                else:
                    os.environ["TELEPHONY_STREAM_WSS_URL"] = prev_stream_ws

    def test_lockout_and_unlock_after_ttl(self):
        with self._client() as client:
            original = web_app.LOCKOUT_DURATION_SECONDS
            try:
                web_app.LOCKOUT_DURATION_SECONDS = 1
                for _ in range(5):
                    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
                    self.assertEqual(bad.status_code, 401)
                blocked = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
                self.assertEqual(blocked.status_code, 423, blocked.text)
                time.sleep(1.1)
                ok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
                self.assertEqual(ok.status_code, 200, ok.text)
            finally:
                web_app.LOCKOUT_DURATION_SECONDS = original

    def test_refresh_rotation_and_revoke(self):
        with self._client() as client:
            login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            self.assertEqual(login.status_code, 200, login.text)
            payload = login.json()
            old_refresh = str(payload.get("refresh_token") or "")
            self.assertTrue(old_refresh)
            session_id = str(payload.get("session_id") or "")
            self.assertTrue(session_id)

            refreshed = client.post("/api/auth/refresh")
            self.assertEqual(refreshed.status_code, 200, refreshed.text)

            replay_old = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
            self.assertEqual(replay_old.status_code, 401, replay_old.text)

            revoke = client.post(f"/api/auth/sessions/{session_id}/revoke")
            self.assertEqual(revoke.status_code, 200, revoke.text)

            after_revoke = client.post("/api/auth/refresh")
            self.assertEqual(after_revoke.status_code, 401, after_revoke.text)

    def test_password_policy_and_tenant_membership_enforced(self):
        with self._client() as client:
            admin = self._login(client, "admin", "admin123")
            headers = {"Authorization": f"Bearer {admin}"}
            weak_user = client.post(
                "/api/users",
                json={"username": "weak", "password": "weakpass", "role": "VIEWER"},
                headers=headers,
            )
            self.assertEqual(weak_user.status_code, 400, weak_user.text)

            strong_user = client.post(
                "/api/users",
                json={
                    "username": "opsviewer",
                    "password": "StrongPass!123",
                    "role": "VIEWER",
                    "default_tenant_id": "default",
                },
                headers=headers,
            )
            self.assertEqual(strong_user.status_code, 200, strong_user.text)

            create_tenant = client.post(
                "/api/v2/tenants",
                json={"tenant_id": "alpha", "name": "Alpha NBFC"},
                headers=headers,
            )
            self.assertEqual(create_tenant.status_code, 200, create_tenant.text)

            viewer_login = client.post("/api/auth/login", json={"username": "opsviewer", "password": "StrongPass!123"})
            self.assertEqual(viewer_login.status_code, 200, viewer_login.text)
            viewer_token = str(viewer_login.json().get("access_token") or "")
            denied = client.get(
                "/api/v2/recovery/uplift",
                headers={"Authorization": f"Bearer {viewer_token}", "x-tenant-id": "alpha"},
            )
            self.assertEqual(denied.status_code, 403, denied.text)


if __name__ == "__main__":
    unittest.main()
