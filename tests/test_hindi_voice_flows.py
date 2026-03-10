import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from workflow_engine import WorkflowEngine, WorkflowState


class HindiVoiceFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 10, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        self.engine = WorkflowEngine(enable_advanced=True, now_fn=lambda: self.now)

    def test_hindi_hardship_to_callback_flow(self):
        state = WorkflowState()

        self.engine.update_from_user("हाँ", state, reply_to_step_id="consent")
        self.assertTrue(state.consent)
        self.assertEqual(state.current_step, "confirm_identity")

        self.engine.update_from_user(
            "हाँ, मैं राहुल शर्मा बोल रहा हूँ।",
            state,
            extracted={"customer_name": "राहुल शर्मा", "identity_name_preexisting": True},
            reply_to_step_id="confirm_identity",
        )
        self.assertTrue(state.identity_confirmed)
        self.assertEqual(state.current_step, "confirm_awareness")

        self.engine.update_from_user("मुझे पता नहीं था।", state, reply_to_step_id="confirm_awareness")
        self.assertTrue(state.awareness_confirmed)
        self.assertEqual(state.last_transition_reason, "awareness_denied_context")
        self.assertEqual(state.current_step, "ask_payment_made")

        self.engine.update_from_user(
            "मेरी नौकरी चली गई है, अभी पैसे नहीं हैं।",
            state,
            reply_to_step_id="ask_payment_made",
        )
        self.assertFalse(state.payment_made)
        self.assertTrue(state.hardship_detected)
        self.assertEqual(state.current_step, "ask_ptp_or_callback")

        self.engine.update_from_user(
            "कल 5 बजे कॉल कर लीजिए।",
            state,
            reply_to_step_id="ask_ptp_or_callback",
        )
        self.assertEqual(state.callback_time, "17:00")
        self.assertEqual(state.current_step, "closing")

    def test_hindi_paid_with_utr_closes_without_ptp_branch(self):
        state = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True)
        state.current_step = "ask_payment_made"

        self.engine.update_from_user(
            "मैंने पेमेंट कर दिया है।",
            state,
            reply_to_step_id="ask_payment_made",
        )
        self.assertTrue(state.payment_made)
        self.assertEqual(state.current_step, "ask_reference_number")

        self.engine.update_from_user(
            "UTR 1234567890 है।",
            state,
            extracted={"reference_number": "1234567890"},
            reply_to_step_id="ask_reference_number",
        )
        self.assertEqual(state.reference_number, "1234567890")
        self.assertEqual(state.current_step, "closing")
        self.assertIsNone(state.ptp_date)
        self.assertIsNone(state.callback_time)

    def test_hindi_wrong_number_phrase_closes_immediately(self):
        state = WorkflowState(consent=True)
        state.current_step = "confirm_identity"

        self.engine.update_from_user("गलत नंबर है।", state, reply_to_step_id="confirm_identity")

        self.assertTrue(state.wrong_party)
        self.assertTrue(state.identity_denied)
        self.assertEqual(state.disposition, "wrong_party")
        self.assertEqual(state.current_step, "closing")

    def test_hinglish_salary_delay_leads_to_callback_path(self):
        state = WorkflowState(
            consent=True,
            identity_confirmed=True,
            awareness_confirmed=True,
            payment_made=False,
        )
        state.current_step = "ask_ptp_or_callback"

        self.engine.update_from_user(
            "salary late hai, abhi pay nahi kar paunga",
            state,
            reply_to_step_id="ask_ptp_or_callback",
        )

        self.assertTrue(state.hardship_detected)
        self.assertTrue(state.refusal_detected)
        self.assertTrue(state.callback_requested)
        self.assertEqual(state.last_transition_reason, "hardship")
        self.assertEqual(state.current_step, "ask_ptp_or_callback")


if __name__ == "__main__":
    unittest.main()
