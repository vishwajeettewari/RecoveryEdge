import asyncio
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import suppress
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

import web_app
from audit_store import SQLiteAuditStore
from datetime_utils import parse_date_from_text as real_parse_date_from_text
from followup_service import FollowupService
from strategy_engine import StrategyEngine
from web_session import EmotionalState, WebCallSession
from workflow_engine import WorkflowEngine, WorkflowState


class _DummyVoiceSession:
    def __init__(self, *_: object, **__: object) -> None:
        self._session_id = "sess-ws-dummy"
        self._facts: dict[str, object] = {}
        self.stt = SimpleNamespace(language="en-IN")

    async def set_context(self, ctx: dict) -> None:
        self._facts.update(ctx or {})

    def _resolve_stt_connect_language(self, language: str | None) -> str | None:
        return language

    async def start(self) -> None:
        return None

    async def start_greeting(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def handle_text(self, text: str) -> None:
        return None

    async def handle_audio(self, data: bytes) -> None:
        return None

    async def admin_set_disposition(self, disposition: str) -> None:
        self._facts["disposition"] = disposition

    def get_snapshot(self) -> dict:
        dpd = self._facts.get("dpd")
        try:
            dpd_i = int(dpd) if dpd is not None else None
        except Exception:
            dpd_i = None
        if dpd_i is None or dpd_i <= 0:
            bucket = "0" if dpd is not None else None
        elif dpd_i <= 30:
            bucket = "1-30"
        elif dpd_i <= 60:
            bucket = "31-60"
        elif dpd_i <= 90:
            bucket = "61-90"
        else:
            bucket = "90+"
        return {
            "session_id": self._session_id,
            "customer_id": self._facts.get("customer_id"),
            "campaign_id": self._facts.get("campaign_id"),
            "dpd_bucket": bucket,
            "strategy_mode": "firm_commitment",
            "tone_profile": "firm_respectful",
            "disposition": self._facts.get("disposition"),
            "ptp_date": self._facts.get("ptp_date"),
            "callback_time": self._facts.get("callback_time"),
        }


class WebSessionOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "demo.db")
        self.audit = SQLiteAuditStore(self.db_path)
        self.followups = FollowupService(self.db_path)
        self.strategy = StrategyEngine()

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    async def _noop_send(_: object) -> None:
        return None

    @staticmethod
    async def _noop_async(*_: object, **__: object) -> None:
        return None

    def _outcome_session(self) -> WebCallSession:
        session = WebCallSession.__new__(WebCallSession)
        session._session_id = "sess-outcome-1"
        session._workflow_tz = "Asia/Kolkata"
        session._enable_advanced_workflow = True
        session._dynamic_stt_language = False
        session._apply_context_language_to_stt = False
        session._stt_task = None
        session._in_silence = True
        session._pending_stt_language = None
        session._facts = {
            "customer_id": "CUST-1001",
            "campaign_id": "cmp-outcome",
            "customer_name": "Asha Rao",
            "phone": "+919999999999",
            "overdue_amount": "2500",
            "brand_name": "TuringEdge",
            "ptp_date": None,
            "callback_time": None,
        }
        session._wf_state = WorkflowState()
        session._wf_state.current_step = "ask_ptp_or_callback"
        session._wf_state.disposition = "ptp_captured"
        session._audit_store = self.audit
        session._followup_service = self.followups
        session._action_router = SimpleNamespace()
        session._crm_adapter = None
        session._excel_sink = None
        session._session_registry = None
        session._persist_state = lambda: None
        session._publish_snapshot = lambda: None
        session._resolve_stt_connect_language = lambda language: language
        session._get_strategy_decision = lambda: self.strategy.classify(45)
        session._set_workflow_step = lambda reason: None
        session.send_event = self._noop_send
        session._apply_language_update = self._noop_async
        session._log_redact_pii = False
        return session

    def _typed_session(self) -> WebCallSession:
        session = WebCallSession.__new__(WebCallSession)
        session._session_id = "sess-profanity-1"
        session._last_activity_ts = 0.0
        session._pending_step_id = None
        session._reply_to_step_id = None
        session._pending_customer_meta_question = None
        session._force_dynamic_reply_once = False
        session._preview_active = False
        session._last_user_text = ""
        session._facts = {
            "customer_name": "Asha Rao",
            "ptp_date": None,
            "reference_number": None,
            "callback_time": None,
            "brand_name": "TuringEdge",
        }
        session._wf_state = WorkflowState()
        session._wf_state.current_step = "closing"
        session._wf_state.last_agent_intent = "closing"
        session._audit_store = self.audit
        session._excel_sink = None
        session._compliance_engine = None
        session._session_registry = None
        session._log_redact_pii = False
        session._wf = WorkflowEngine(
            enable_advanced=True,
            max_retries=3,
            tz="Asia/Kolkata",
            ptp_min_days=0,
            ptp_max_days=30,
            callback_hours_start=9,
            callback_hours_end=20,
        )
        session._preempt_mode_for_user_turn = lambda: "idle"
        session.send_event = self._noop_send
        session._emit_chat_message = self._noop_async
        session._resolve_output_language = lambda language: language or "en-IN"
        session._debug_trace = lambda *args, **kwargs: None
        session._extract_facts_from_text = lambda text: None
        session._detect_customer_meta_question = lambda text: None
        session._detect_language_switch_request = lambda text: None
        session._update_policy_from_user = lambda text: None
        session._consume_pending_step_binding = lambda: None
        session._sync_workflow_from_facts = lambda: None
        session._persist_commitments = lambda: None
        session._persist_state = lambda: None
        session._start_generation_from_text = self._noop_async
        return session

    def _auto_ptp_session(self) -> WebCallSession:
        session = WebCallSession.__new__(WebCallSession)
        session._session_id = "sess-auto-ptp-1"
        session._last_activity_ts = 0.0
        session._pending_step_id = None
        session._reply_to_step_id = None
        session._pending_customer_meta_question = None
        session._force_dynamic_reply_once = False
        session._preview_active = False
        session._last_user_text = ""
        session._workflow_tz = "Asia/Kolkata"
        session._enable_advanced_workflow = True
        session._ptp_min_days = 0
        session._ptp_max_days = 30
        session._callback_hours_start = 9
        session._callback_hours_end = 20
        session._facts = {
            "customer_id": "CUST-1002",
            "campaign_id": "cmp-auto-ptp",
            "customer_name": "Asha Rao",
            "phone": "+919999999999",
            "overdue_amount": "2500",
            "brand_name": "TuringEdge",
            "language_preference": "en-IN",
            "ptp_date": None,
            "reference_number": None,
            "callback_time": None,
        }
        session._wf_state = WorkflowState(
            consent=True,
            identity_confirmed=True,
            awareness_confirmed=True,
            payment_made=False,
            current_step="ask_ptp_or_callback",
            last_agent_intent="ask_ptp_or_callback",
        )
        session._audit_store = self.audit
        session._followup_service = self.followups
        session._action_router = None
        session._crm_adapter = None
        session._excel_sink = None
        session._compliance_engine = None
        session._session_registry = None
        session._log_redact_pii = False
        session._last_persisted_ptp = None
        session._last_persisted_callback = None
        session._emotional_state = EmotionalState()
        session._wf = WorkflowEngine(
            enable_advanced=True,
            max_retries=3,
            tz="Asia/Kolkata",
            ptp_min_days=0,
            ptp_max_days=30,
            callback_hours_start=9,
            callback_hours_end=20,
        )
        session._preempt_mode_for_user_turn = lambda: "idle"
        session.send_event = self._noop_send
        session._emit_chat_message = self._noop_async
        session._resolve_output_language = lambda language: language or "en-IN"
        session._debug_trace = lambda *args, **kwargs: None
        session._detect_customer_meta_question = lambda text: None
        session._detect_language_switch_request = lambda text: None
        session._update_policy_from_user = lambda text: None
        session._consume_pending_step_binding = lambda: None
        session._persist_state = lambda: None
        session._start_generation_from_text = self._noop_async
        session._get_strategy_decision = lambda: self.strategy.classify(45)
        return session

    def test_context_and_save_ptp_or_callback_persist_outcomes_and_followups(self):
        session = self._outcome_session()

        asyncio.run(
            session.set_context(
                {
                    "customer_id": "CUST-1001",
                    "campaign_id": "cmp-outcome",
                    "phone": "+919999999999",
                    "language_preference": "en-IN",
                    "dpd": 45,
                }
            )
        )
        result = asyncio.run(
            session.handle_action(
                name="save_ptp_or_callback",
                payload={"ptp_date": "2026-03-12", "callback_time": "15:30", "auto_send_link": False},
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["ptp_date"], "2026-03-12")
        self.assertEqual(result["callback_time"], "15:30")
        self.assertEqual(len(result["followups"]), 4)
        reminder_types = {row["reminder_type"] for row in result["followups"]}
        self.assertEqual(reminder_types, {"ptp_t_minus_1", "ptp_t_day", "ptp_t_plus_1_miss", "callback_due"})

        metrics = self.audit.metrics(campaign_id="cmp-outcome")
        self.assertEqual(metrics["ptp_count"], 1)
        self.assertEqual(metrics["callback_count"], 1)
        self.assertEqual(metrics["followups_scheduled_total"], 4)

        conn = sqlite3.connect(self.db_path)
        try:
            snapshot_count = conn.execute(
                "SELECT COUNT(*) FROM dpd_snapshots WHERE customer_id = ?",
                ("CUST-1001",),
            ).fetchone()[0]
            outcome = conn.execute(
                "SELECT ptp_date, callback_time, campaign_id FROM outcomes WHERE session_id = ?",
                ("sess-outcome-1",),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(snapshot_count, 1)
        self.assertEqual(outcome[0], "2026-03-12")
        self.assertEqual(outcome[1], "15:30")
        self.assertEqual(outcome[2], "cmp-outcome")

    def test_handle_text_records_profanity_when_customer_abuses_in_closing(self):
        session = self._typed_session()

        asyncio.run(session.handle_text("fuck you"))

        self.assertEqual(session._wf_state.last_transition_reason, "abusive_language")
        metrics = self.audit.metrics()
        self.assertEqual(metrics["profanity_incidents"], 1)

    def test_handle_text_auto_captures_ordinal_ptp_and_persists_metrics(self):
        session = self._auto_ptp_session()
        fixed_now = datetime(2026, 3, 10, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

        with patch(
            "web_session.parse_date_from_text",
            side_effect=lambda text, *, tz, now=None: real_parse_date_from_text(text, tz=tz, now=fixed_now),
        ):
            asyncio.run(session.handle_text("I will make the payment on 12th"))

        self.assertEqual(session._wf_state.ptp_date, "2026-03-12")
        self.assertEqual(session._facts["ptp_date"], "2026-03-12")
        self.assertEqual(session._wf_state.current_step, "closing")

        metrics = self.audit.metrics(campaign_id="cmp-auto-ptp")
        self.assertEqual(metrics["ptp_count"], 1)

        conn = sqlite3.connect(self.db_path)
        try:
            outcome = conn.execute(
                "SELECT ptp_date, campaign_id FROM outcomes WHERE session_id = ?",
                ("sess-auto-ptp-1",),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(outcome[0], "2026-03-12")
        self.assertEqual(outcome[1], "cmp-auto-ptp")


class VoiceSocketOutcomeTests(unittest.TestCase):
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

    def test_voice_socket_persists_open_and_close_timestamps(self):
        with self._client() as client:
            agent_token = self._login(client, "agent", "agent123")
            ws_token_resp = client.post(
                "/api/auth/ws-token",
                json={},
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            self.assertEqual(ws_token_resp.status_code, 200, ws_token_resp.text)
            ws_token = ws_token_resp.json()["ws_token"]

            with patch.object(web_app, "WebCallSession", _DummyVoiceSession):
                with client.websocket_connect(f"/ws/voice?token={ws_token}") as websocket:
                    websocket.send_json(
                        {
                            "type": "start",
                            "customer_id": "WS-1001",
                            "campaign_id": "cmp-ws-proof",
                            "phone": "+919999999998",
                            "dpd": 35,
                            "language_preference": "en-IN",
                        }
                    )
                    websocket.receive_json()
                    websocket.receive_json()
                    websocket.send_json({"type": "stop"})

            demo = web_app._get_demo_singletons()
            audit = demo["audit"]
            row = None
            for _ in range(20):
                recent = audit.recent_sessions(limit=20)
                matches = [entry for entry in recent if entry["session_id"] == "sess-ws-dummy"]
                if matches and matches[0]["end_ts"] is not None:
                    row = matches[0]
                    break
                time.sleep(0.05)
            self.assertIsNotNone(row)
            self.assertIsNotNone(row["start_ts"])
            self.assertIsNotNone(row["end_ts"])
            self.assertGreaterEqual(float(row["end_ts"]), float(row["start_ts"]))


if __name__ == "__main__":
    unittest.main()
