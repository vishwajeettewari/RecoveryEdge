import time
import unittest
import inspect
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from web_session import WebCallSession
from sarvam_stt_service import Transcript
import asyncio
from workflow_engine import WorkflowState


class _DummySTT:
    def __init__(self, *, flush_signal: bool, use_sdk: bool):
        self.flush_signal = flush_signal
        self.use_sdk = use_sdk
        self.language = "en-IN"


class WebSessionGuardTests(unittest.TestCase):
    def _session_stub(self) -> WebCallSession:
        s = WebCallSession.__new__(WebCallSession)
        s._session_id = "test-session"
        s._workflow_tz = "Asia/Kolkata"
        s._enable_advanced_workflow = True
        s._ptp_min_days = 0
        s._ptp_max_days = 30
        s._callback_hours_start = 9
        s._callback_hours_end = 20
        s._last_speech_ts = 0.0
        s._in_silence = True
        s._vad_speech_frames = 0
        s._barge_in_min_speech_frames = 5
        s._barge_in_grace_s = 0.45
        s._last_rms = 0.0
        s._vad_threshold = 500.0
        s._segment_speech_frames = 0
        s._min_flush_speech_frames = 4
        s._short_flush_skip_count = 0
        s._force_flush_segment_ms = 700
        s._force_flush_after_skips = 2
        s._force_flush_no_final_s = 6.0
        s._has_sent_audio = True
        s._last_flush_ts = 0.0
        s._last_stt_final_ts = time.time()
        s._flush_min_gap_s = 0.2
        s.stt = _DummySTT(flush_signal=True, use_sdk=True)
        s._tts_playing = asyncio.Event()
        s._tts_pending = False
        s._tts_start_ts = time.time()
        s._current_llm_text = "hello this is kreditbee calling"
        s._last_assistant_text = "hello this is kreditbee calling"
        s._reply_to_step_id = None
        s._pending_step_id = None
        s._wf_state = WorkflowState()
        s._facts = {
            "ptp_date": None,
            "callback_time": None,
            "reference_number": None,
            "language_preference": None,
        }
        return s

    def test_finalize_cancel_ignores_transient_speech(self):
        s = self._session_stub()
        s._last_speech_ts = 10.1
        s._in_silence = False
        s._vad_speech_frames = 5

        self.assertFalse(
            s._should_cancel_pending_final_for_speech(
                last_speech_at_start=10.0,
                speech_active_checks=1,
                time_since_start=0.4,
            )
        )

    def test_finalize_cancel_requires_sustained_speech(self):
        s = self._session_stub()
        s._last_speech_ts = 22.0
        s._in_silence = False
        s._vad_speech_frames = 6

        self.assertTrue(
            s._should_cancel_pending_final_for_speech(
                last_speech_at_start=20.0,
                speech_active_checks=4,
                time_since_start=0.45,
            )
        )

    def test_finalize_cancel_rejects_low_vad_frames(self):
        s = self._session_stub()
        s._last_speech_ts = 18.0
        s._in_silence = False
        s._vad_speech_frames = 2

        self.assertFalse(
            s._should_cancel_pending_final_for_speech(
                last_speech_at_start=17.0,
                speech_active_checks=5,
                time_since_start=0.6,
            )
        )

    def test_silence_flush_requires_meaningful_speech_segment(self):
        s = self._session_stub()
        s._segment_speech_frames = 2
        s._last_flush_ts = 0.0

        self.assertFalse(s._should_flush_on_silence_transition())

    def test_silence_flush_respects_gap(self):
        s = self._session_stub()
        s._segment_speech_frames = 8
        s._last_flush_ts = time.time()

        self.assertFalse(s._should_flush_on_silence_transition())
        s._last_flush_ts = time.time() - 1.0
        self.assertTrue(s._should_flush_on_silence_transition())

    def test_silence_flush_forces_on_long_segment(self):
        s = self._session_stub()
        s._segment_speech_frames = 1
        s._last_flush_ts = time.time() - 1.0
        self.assertTrue(s._should_flush_on_silence_transition(segment_duration_ms=900))

    def test_silence_flush_forces_after_repeated_short_skips(self):
        s = self._session_stub()
        s._segment_speech_frames = 1
        s._short_flush_skip_count = 2
        s._last_flush_ts = time.time() - 1.0
        self.assertTrue(s._should_flush_on_silence_transition(segment_duration_ms=200))

    def test_ambiguous_short_reply_detection(self):
        s = self._session_stub()
        self.assertTrue(s._is_ambiguous_short_reply("sorry"))
        self.assertTrue(s._is_ambiguous_short_reply("repeat"))
        self.assertFalse(s._is_ambiguous_short_reply("hello"))
        self.assertFalse(s._is_ambiguous_short_reply("no"))
        self.assertFalse(s._is_ambiguous_short_reply("I haven't paid"))

    def test_pending_final_prefers_meaningful_text(self):
        s = self._session_stub()
        self.assertTrue(
            s._should_keep_existing_pending_final(
                "I haven't made the payment yet",
                "hello",
            )
        )

    def test_echo_filter_keeps_human_short_barge_in(self):
        s = self._session_stub()
        s._tts_playing.set()
        tr = Transcript(text="hello", is_final=True, language="en-IN", confidence=None)
        self.assertFalse(s._is_likely_echo("hello", tr))
        self.assertTrue(
            s._should_keep_existing_pending_final(
                "no",
                "hello",
            )
        )

    def test_partials_never_schedule_generation(self):
        src = inspect.getsource(WebCallSession._stt_loop)
        self.assertNotIn("_start_generation(text, transcript, preview=True)", src)

    def test_partial_barge_in_allowed_without_state_mutation(self):
        s = self._session_stub()
        s._tts_playing.set()
        s._reply_to_step_id = "consent"
        s._tts_start_ts = time.time() - 1.0
        before_no_count = s._wf_state.no_count
        self.assertTrue(s._should_barge_in_from_stt("yes"))
        self.assertEqual(s._wf_state.no_count, before_no_count)

    def test_pending_final_keeps_meaningful_over_noise_final(self):
        s = self._session_stub()
        self.assertTrue(s._should_keep_existing_pending_final("I cannot make the payment", "Bank"))
        self.assertFalse(s._should_keep_existing_pending_final("Bank", "I cannot make the payment"))

    def test_finalize_waits_for_confirmed_silence_before_generation(self):
        s = self._session_stub()
        s._in_silence = False
        s._last_speech_ts = time.time()
        self.assertFalse(
            s._should_cancel_pending_final_for_speech(
                last_speech_at_start=s._last_speech_ts,
                speech_active_checks=1,
                time_since_start=0.2,
            )
        )

    def test_negative_final_not_misclassified_as_topic_drift(self):
        s = self._session_stub()
        s._wf_state.current_step = "ask_ptp_or_callback"
        self.assertIsNone(s._detect_misunderstanding("I cannot make the payment", "When can you pay?"))

    def test_payment_timing_not_misclassified_as_topic_drift(self):
        s = self._session_stub()
        s._wf_state.current_step = "ask_ptp_or_callback"
        self.assertIsNone(s._detect_misunderstanding("Let's say by tomorrow.", "When can you pay?"))

    def test_sync_workflow_normalizes_relative_ptp_fact(self):
        s = self._session_stub()
        s._facts["ptp_date"] = "Let's say by tomorrow."
        s._sync_workflow_from_facts()
        self.assertRegex(s._wf_state.ptp_date or "", r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(s._facts["ptp_date"], s._wf_state.ptp_date)

    def test_sync_workflow_normalizes_relative_ptp_from_workflow_state(self):
        s = self._session_stub()
        s._wf_state.ptp_date = "Let's say by tomorrow."
        s._sync_workflow_from_facts()
        self.assertRegex(s._wf_state.ptp_date or "", r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(s._facts["ptp_date"], s._wf_state.ptp_date)

    def test_detect_language_switch_request_hindi(self):
        s = self._session_stub()
        self.assertEqual(
            s._detect_language_switch_request("Kya aap Hindi mein baat kar sakte ho?"),
            "hi-IN",
        )

    def test_detect_language_switch_request_hindi_not_understanding_english(self):
        s = self._session_stub()
        self.assertEqual(
            s._detect_language_switch_request("Aapki English nahin samajh aa rahi."),
            "hi-IN",
        )

    def test_detect_language_switch_request_english(self):
        s = self._session_stub()
        self.assertEqual(
            s._detect_language_switch_request("Please talk in English."),
            "en-IN",
        )

    def test_language_switch_not_misclassified_as_topic_drift(self):
        s = self._session_stub()
        s._wf_state.current_step = "consent"
        self.assertIsNone(
            s._detect_misunderstanding(
                "Kya aap Hindi mein baat kar sakte ho?",
                "This call may be recorded for quality.",
            )
        )

    def test_fixed_prompt_localizes_hindi_consent(self):
        s = self._session_stub()
        s._facts["language_preference"] = "hi-IN"
        prompt = s._fixed_prompt_for_step("consent")
        self.assertIn("सहमति", prompt)
        self.assertTrue(bool(re.search(r"[\u0900-\u097f]", prompt)))
        ack = s._language_switch_ack("hi-IN")
        self.assertTrue(bool(re.search(r"[\u0900-\u097f]", ack)))

    def test_closing_prompt_uses_relative_label(self):
        s = self._session_stub()
        s._facts["language_preference"] = "en-IN"
        tomorrow = (datetime.now(ZoneInfo("Asia/Kolkata")).date() + timedelta(days=1)).isoformat()
        s._wf_state.ptp_date = tomorrow
        closing = s._fixed_prompt_for_step("closing")
        self.assertIn("tomorrow", closing.lower())

    def test_branding_normalization_replaces_legacy_name(self):
        s = self._session_stub()
        self.assertEqual(
            s._normalize_branding_text("Hello, this is KreditBee collections."),
            "Hello, this is TuringEdge collections.",
        )

    def test_ensure_consent_prompt_once_deduplicates_existing_line(self):
        s = self._session_stub()
        text = (
            "Hello Rahul Sharma, this is TuringEdge collections calling about your overdue payment. "
            "Is now a good time to talk?. This call may be recorded for quality. "
            "Do I have your consent to continue?. This call may be recorded for quality. "
            "Do I have your consent to continue?"
        )
        normalized = s._ensure_consent_prompt_once(text)
        self.assertEqual(normalized.lower().count("do i have your consent to continue"), 1)

    def test_ensure_consent_prompt_once_appends_when_missing(self):
        s = self._session_stub()
        text = "Hello Rahul Sharma, this is TuringEdge collections calling."
        normalized = s._ensure_consent_prompt_once(text)
        self.assertEqual(normalized.lower().count("do i have your consent to continue"), 1)

    def test_ensure_consent_prompt_once_removes_malformed_variant(self):
        s = self._session_stub()
        text = (
            "Hello Rahul Sharma, this is TuringEdge collections calling about your overdue payment. "
            "This call may be recorderd for quLITY. Do I have your permissn to continue?"
        )
        normalized = s._ensure_consent_prompt_once(text)
        self.assertEqual(normalized.lower().count("do i have your consent to continue"), 1)
        self.assertNotIn("recorderd", normalized.lower())

    def test_has_consent_prompt_detects_permission_variant(self):
        s = self._session_stub()
        text = "This call may be recorderd for quLITY. Do I have your permission to continue?"
        self.assertTrue(s._has_consent_prompt(text))


if __name__ == "__main__":
    unittest.main()
