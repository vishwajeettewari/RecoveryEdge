import unittest

from workflow_engine import WorkflowEngine, WorkflowState


class WorkflowEngineTests(unittest.TestCase):
    def test_flow_consent_identity_awareness(self):
        eng = WorkflowEngine()
        st = WorkflowState()

        self.assertEqual(eng.compute_next_step(st), "consent")
        eng.update_from_assistant("This call may be recorded. Do I have your consent?", st)
        eng.update_from_user("yes", st)
        self.assertTrue(st.consent)

        self.assertEqual(eng.compute_next_step(st), "confirm_identity")
        eng.update_from_assistant("Am I speaking with Rahul?", st)
        eng.update_from_user("yes", st)
        self.assertTrue(st.identity_confirmed)

        self.assertEqual(eng.compute_next_step(st), "confirm_awareness")
        eng.update_from_assistant("Are you aware your payment is overdue?", st)
        eng.update_from_user("yes", st)
        self.assertTrue(st.awareness_confirmed)

    def test_payment_ptp(self):
        eng = WorkflowEngine()
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True)

        self.assertEqual(eng.compute_next_step(st), "ask_payment_made")
        eng.update_from_assistant("Have you made the payment?", st)
        eng.update_from_user("no", st)
        self.assertFalse(st.payment_made)

        self.assertEqual(eng.compute_next_step(st), "ask_ptp_or_callback")
        eng.update_from_assistant("By when can you make the payment?", st)
        eng.update_from_user("I will pay on 06/02/2026", st)
        self.assertTrue(st.ptp_date)
        self.assertEqual(eng.compute_next_step(st), "closing")


if __name__ == "__main__":
    unittest.main()

