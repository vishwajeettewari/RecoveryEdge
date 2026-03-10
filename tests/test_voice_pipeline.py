import unittest

from voice_pipeline import (
    DialogueState,
    DialogueStateManager,
    InterruptionIntent,
    InterruptionPolicy,
    LanguageDetectionGate,
    PromptHistoryGuard,
    UserIntent,
    UtteranceIntentClassifier,
)


class VoicePipelineTests(unittest.TestCase):
    def test_name_response_blocks_language_detection_for_native_script_name(self):
        classifier = UtteranceIntentClassifier()
        gate = LanguageDetectionGate()

        intent = classifier.classify(
            "ਵਿਸ਼ਵਜੀਤ ਤਿਵਾੜੀ",
            current_step="confirm_identity",
        )
        decision = gate.evaluate(
            intent=intent,
            explicit_language_request=None,
            detected_language="pa-IN",
            current_language="hi-IN",
            confidence=0.96,
            meaningful_words=classifier.meaningful_word_count("ਵਿਸ਼ਵਜੀਤ ਤਿਵਾੜੀ"),
            sentence_count=classifier.sentence_count("ਵਿਸ਼ਵਜੀਤ ਤਿਵਾੜੀ"),
        )

        self.assertEqual(intent, UserIntent.NAME_RESPONSE)
        self.assertFalse(decision.detection_allowed)
        self.assertFalse(decision.should_offer_confirmation)

    def test_explicit_language_request_requires_confirmation(self):
        classifier = UtteranceIntentClassifier()
        gate = LanguageDetectionGate()
        text = "Please talk in Hindi."
        intent = classifier.classify(
            text,
            current_step="ask_payment_made",
            explicit_language_request="hi-IN",
        )
        decision = gate.evaluate(
            intent=intent,
            explicit_language_request="hi-IN",
            detected_language="en-IN",
            current_language="en-IN",
            confidence=0.99,
            meaningful_words=classifier.meaningful_word_count(text),
            sentence_count=classifier.sentence_count(text),
        )

        self.assertEqual(intent, UserIntent.LANGUAGE_REQUEST)
        self.assertTrue(decision.should_offer_confirmation)
        self.assertEqual(decision.candidate_language, "hi-IN")
        self.assertEqual(decision.reason, "explicit_request")

    def test_language_detection_needs_multiple_substantive_turns(self):
        classifier = UtteranceIntentClassifier()
        gate = LanguageDetectionGate()
        text = "मैं कल भुगतान कर दूंगा और आप शाम को कॉल मत कीजिए।"
        meaningful_words = classifier.meaningful_word_count(text)
        sentence_count = classifier.sentence_count(text)

        first = gate.evaluate(
            intent=UserIntent.PAYMENT_PROMISE,
            explicit_language_request=None,
            detected_language="hi-IN",
            current_language="en-IN",
            confidence=0.95,
            meaningful_words=meaningful_words,
            sentence_count=sentence_count,
        )
        second = gate.evaluate(
            intent=UserIntent.PAYMENT_PROMISE,
            explicit_language_request=None,
            detected_language="hi-IN",
            current_language="en-IN",
            confidence=0.95,
            meaningful_words=meaningful_words,
            sentence_count=sentence_count,
        )

        self.assertFalse(first.should_offer_confirmation)
        self.assertTrue(second.should_offer_confirmation)
        self.assertEqual(second.candidate_language, "hi-IN")

    def test_dialogue_state_updates_to_ptp_capture_on_payment_promise(self):
        manager = DialogueStateManager()
        manager.sync_from_step("closing")

        state = manager.update_from_user_intent(
            current_step="closing",
            intent=UserIntent.PAYMENT_PROMISE,
        )

        self.assertEqual(state, DialogueState.PTP_CAPTURE)
        self.assertEqual(manager.state_to_step(state, has_ptp=True), "confirm_ptp")

    def test_interruption_policy_enters_repair_mode_after_repeated_confusion(self):
        policy = InterruptionPolicy()

        self.assertFalse(policy.observe(interruption_intent=InterruptionIntent.CONFUSION, text="What?"))
        self.assertTrue(
            policy.observe(
                interruption_intent=InterruptionIntent.CONFUSION,
                text="Why are you speaking Punjabi?",
            )
        )

    def test_prompt_history_guard_only_rephrases_same_prompt(self):
        guard = PromptHistoryGuard()
        self.assertFalse(guard.should_rephrase(prompt_key="ask_payment_made:hi-IN", prompt_text="क्या आपने भुगतान किया है?"))
        guard.remember(prompt_key="ask_payment_made:hi-IN", prompt_text="क्या आपने भुगतान किया है?")
        self.assertTrue(guard.should_rephrase(prompt_key="ask_payment_made:hi-IN", prompt_text="क्या आपने भुगतान किया है?"))
        self.assertFalse(
            guard.should_rephrase(
                prompt_key="ask_payment_made:hi-IN",
                prompt_text="क्या यह भुगतान अभी बाकी है?",
            )
        )


if __name__ == "__main__":
    unittest.main()
