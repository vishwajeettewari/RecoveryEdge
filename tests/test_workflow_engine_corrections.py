from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from workflow_engine import WorkflowEngine, WorkflowState


class WorkflowEngineCorrectionTests(unittest.TestCase):
    def setUp(self) -> None:
        now = datetime(2026, 3, 10, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        self.engine = WorkflowEngine(
            enable_advanced=True,
            tz="Asia/Kolkata",
            now_fn=lambda: now,
        )

    def test_correction_overwrites_existing_ptp_date(self):
        state = WorkflowState(
            consent=True,
            identity_confirmed=True,
            awareness_confirmed=True,
            payment_made=False,
            ptp_date="2026-03-16",
            current_step="confirm_ptp",
        )
        self.engine.update_from_user(
            "नहीं 11",
            state,
            extracted={"ptp_date": "2026-03-11", "corrected": True},
            reply_to_step_id="confirm_ptp",
        )
        self.assertEqual(state.ptp_date, "2026-03-11")

    def test_callback_correction_overwrites_existing_time(self):
        state = WorkflowState(
            consent=True,
            identity_confirmed=True,
            awareness_confirmed=True,
            payment_made=False,
            callback_time="10:00",
            current_step="ask_ptp_or_callback",
        )
        self.engine.update_from_user(
            "नहीं, 3 बजे",
            state,
            extracted={"callback_time": "15:00", "corrected": True},
            reply_to_step_id="ask_ptp_or_callback",
        )
        self.assertEqual(state.callback_time, "15:00")


if __name__ == "__main__":
    unittest.main()
