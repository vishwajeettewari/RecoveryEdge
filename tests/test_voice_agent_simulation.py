import unittest

from testing.voice_agent_simulation import run_all_voice_agent_scenarios


class VoiceAgentSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results = {row["scenario"]: row for row in run_all_voice_agent_scenarios()}

    def test_all_required_scenarios_are_present(self):
        self.assertEqual(len(self.results), 10)
        self.assertEqual(sum(1 for row in self.results.values() if row["passed"]), 10)

    def test_borrower_unaware_of_loan(self):
        result = self.results["borrower_unaware_of_loan"]
        self.assertEqual(result["final_step"], "closing")
        self.assertFalse(result["payment_made"])
        self.assertTrue(result["ptp_date"])
        self.assertIn("ask_ptp_or_callback", result["steps_visited"])
        self.assertFalse(result["payment_question_repeated_after_unpaid"])

    def test_borrower_already_paid(self):
        result = self.results["borrower_already_paid"]
        self.assertTrue(result["payment_made"])
        self.assertEqual(result["reference_number"], "1234567890")
        self.assertIn("ask_reference_number", result["steps_visited"])

    def test_borrower_promises_payment(self):
        result = self.results["borrower_promises_payment"]
        self.assertFalse(result["payment_made"])
        self.assertTrue(result["ptp_date"])
        self.assertIn("closing", result["steps_visited"])

    def test_borrower_speaks_punjabi_requires_confirmation_not_auto_switch(self):
        result = self.results["borrower_speaks_punjabi"]
        self.assertTrue(result["language_offers"])
        self.assertFalse(result["language_switched"])

    def test_borrower_mixes_hindi_and_punjabi_without_auto_switch(self):
        result = self.results["borrower_mixes_hindi_and_punjabi"]
        self.assertEqual(result["language_offers"], [])
        self.assertIn("confirm_identity", result["steps_visited"])
        self.assertIn("confirm_awareness", result["steps_visited"])

    def test_borrower_interrupts_agent(self):
        result = self.results["borrower_interrupts_agent"]
        self.assertTrue(result["interruption_override"])
        self.assertTrue(result["ptp_date"])

    def test_borrower_abuses_agent(self):
        result = self.results["borrower_abuses_agent"]
        self.assertEqual(result["last_transition_reason"], "abusive_language")
        self.assertEqual(
            result["turns"][-1]["assistant_prompt"],
            "समझ गया सर, मैं बाद में कॉल कर लेता हूँ।",
        )

    def test_borrower_changes_answer_mid_conversation(self):
        result = self.results["borrower_changes_answer_mid_conversation"]
        self.assertFalse(result["payment_made"])
        self.assertIn("ask_reference_number", result["steps_visited"])
        self.assertIn("ask_ptp_or_callback", result["steps_visited"])

    def test_borrower_partial_payment_promise(self):
        result = self.results["borrower_partial_payment_promise"]
        self.assertTrue(result["ptp_date"])
        partial_turns = [turn for turn in result["turns"] if turn["intent"] == "PROMISE_TO_PAY"]
        self.assertTrue(partial_turns)

    def test_borrower_refuses_to_pay(self):
        result = self.results["borrower_refuses_to_pay"]
        self.assertTrue(result["refusal_detected"])
        self.assertEqual(result["final_step"], "closing")
        self.assertTrue(result["no_repeated_prompts"])


if __name__ == "__main__":
    unittest.main()
