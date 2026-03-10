from __future__ import annotations

import unittest

from intent_classifier import IntentClassifier, VoiceIntent


class DeterministicIntentClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = IntentClassifier()

    def test_ptp_commit_detection(self):
        result = self.classifier.classify(
            "11 मार्च तक कर दूंगा",
            current_step="ask_ptp_or_callback",
        )
        self.assertEqual(result.label, VoiceIntent.PROMISE_TO_PAY)
        self.assertEqual(result.canonical_intent, "ptp_commit")

    def test_acknowledgement_detection(self):
        result = self.classifier.classify(
            "haan",
            current_step="ask_payment_made",
        )
        self.assertEqual(result.canonical_intent, "acknowledgement")

    def test_callback_request_detection(self):
        result = self.classifier.classify(
            "baad mein call karo",
            current_step="ask_ptp_or_callback",
        )
        self.assertEqual(result.canonical_intent, "callback_request")

    def test_punjabi_and_bengali_short_forms_normalize(self):
        punjabi = self.classifier.classify("ਨਹੀਂ", current_step="ask_payment_made")
        bengali = self.classifier.classify("হুম", current_step="ask_payment_made")
        self.assertEqual(punjabi.normalized_text, "नहीं")
        self.assertEqual(bengali.canonical_intent, "acknowledgement")

    def test_abuse_detection_handles_hindi_profanity(self):
        result = self.classifier.classify(
            "माँ की चूत",
            current_step="ask_payment_made",
        )
        self.assertEqual(result.label, VoiceIntent.ABUSE)
        self.assertEqual(result.canonical_intent, "abuse")


if __name__ == "__main__":
    unittest.main()
