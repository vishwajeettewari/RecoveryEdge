import unittest

from testing.voice_agent_stress import run_voice_agent_stress_test


class VoiceAgentStressTests(unittest.TestCase):
    def test_stress_harness_runs_fifty_calls_without_loops(self):
        summary = run_voice_agent_stress_test(call_count=50)

        self.assertEqual(summary["calls_simulated"], 50)
        self.assertEqual(summary["passed_calls"], 50)
        self.assertEqual(summary["loop_occurrences"], 0)
        self.assertGreaterEqual(summary["ptp_extraction_accuracy"], 0.95)
        self.assertGreaterEqual(summary["intent_classification_accuracy"], 0.9)


if __name__ == "__main__":
    unittest.main()
