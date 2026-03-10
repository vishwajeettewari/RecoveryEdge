import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

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

    def test_dnd_override(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True)
        st.current_step = "confirm_identity"
        eng.update_from_user("please do not call again", st)
        self.assertEqual(st.disposition, "dnd_requested")
        self.assertEqual(st.current_step, "closing")

    def test_wrong_party(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True)
        st.current_step = "confirm_identity"
        eng.update_from_user("wrong number", st)
        self.assertEqual(st.disposition, "wrong_party")
        self.assertEqual(st.current_step, "closing")

    def test_consent_refusal(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState()
        st.current_step = "consent"
        eng.update_from_user("no", st)
        self.assertEqual(st.disposition, "consent_refused")
        self.assertEqual(st.current_step, "closing")

    def test_consent_requires_explicit_yes(self):
        eng = WorkflowEngine()
        st = WorkflowState()
        st.current_step = "consent"
        eng.update_from_user("can you repeat that", st)
        self.assertIsNone(st.consent)
        self.assertEqual(st.current_step, "consent")

    def test_retry_limit_identity(self):
        eng = WorkflowEngine(enable_advanced=True, max_retries=2)
        st = WorkflowState(consent=True)
        eng.update_from_assistant("Am I speaking with Rahul?", st)
        eng.update_from_assistant("Am I speaking with Rahul?", st)
        eng.update_from_assistant("Am I speaking with Rahul?", st)
        step = eng.compute_next_step(st)
        self.assertEqual(step, "closing")
        self.assertEqual(st.disposition, "identity_not_confirmed")

    def test_strict_date_time_parse(self):
        now = datetime(2026, 2, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I will pay on 06/02/2026", st)
        self.assertEqual(st.ptp_date, "2026-02-06")

        st2 = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st2.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I will pay on 01/02/2026", st2)
        self.assertIsNone(st2.ptp_date)
        self.assertEqual(st2.last_transition_reason, "invalid_ptp_date")
        self.assertEqual(st2.current_step, "ask_ptp_or_callback")

        st3 = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st3.current_step = "ask_ptp_or_callback"
        eng.update_from_user("call me at 23:30", st3)
        self.assertIsNone(st3.callback_time)
        self.assertEqual(st3.last_transition_reason, "invalid_callback_time")
        self.assertEqual(st3.current_step, "ask_ptp_or_callback")

    def test_no_money_sets_callback_prompt(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I have no money", st)
        self.assertTrue(st.callback_requested)
        self.assertEqual(st.last_transition_reason, "hardship")
        self.assertEqual(st.current_step, "ask_ptp_or_callback")

    def test_hardship_detection(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I lost my job last month", st)
        self.assertTrue(st.hardship_detected)
        self.assertEqual(st.last_transition_reason, "hardship")

    def test_no_step_bound_consent_only(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState()
        st.current_step = "consent"
        eng.update_from_user("no", st, reply_to_step_id="consent")
        self.assertFalse(st.consent)
        self.assertIn(st.disposition, {"no_consent", "consent_refused"})
        self.assertFalse(st.refusal_detected)
        self.assertEqual(st.no_count, 0)

    def test_no_step_bound_awareness_not_refusal(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True)
        st.current_step = "confirm_awareness"
        eng.update_from_user("no", st, reply_to_step_id="confirm_awareness")
        self.assertTrue(st.awareness_confirmed)
        self.assertEqual(st.last_transition_reason, "awareness_denied_context")
        self.assertFalse(st.refusal_detected)
        self.assertEqual(st.no_count, 0)

    def test_gujarati_polite_affirmative_counts_as_consent(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState()
        st.current_step = "consent"
        eng.update_from_user("જી આવડીએ.", st, reply_to_step_id="consent")
        self.assertTrue(st.consent)
        self.assertEqual(st.current_step, "confirm_identity")

    def test_punjabi_polite_affirmative_counts_as_consent(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState()
        st.current_step = "consent"
        eng.update_from_user("ਜੀ ਬਿਲਕੁਲ।", st, reply_to_step_id="consent")
        self.assertTrue(st.consent)
        self.assertEqual(st.current_step, "confirm_identity")

    def test_consent_unclear_marks_reason_without_advancing(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState()
        st.current_step = "consent"
        eng.update_from_user("नमस्कार", st, reply_to_step_id="consent")
        self.assertIsNone(st.consent)
        self.assertEqual(st.current_step, "consent")
        self.assertEqual(st.last_transition_reason, "consent_unclear")

    def test_confirm_identity_yes_without_name_keeps_step_pending(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True)
        st.current_step = "confirm_identity"
        eng.update_from_user("हां, पूछ सकते हैं।", st, reply_to_step_id="confirm_identity")
        self.assertFalse(st.identity_confirmed)
        self.assertEqual(st.current_step, "confirm_identity")

    def test_confirm_identity_yes_confirms_known_name(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True)
        st.current_step = "confirm_identity"
        eng.update_from_user(
            "हाँ",
            st,
            extracted={"customer_name": "Vishwajit Tiwari", "identity_name_preexisting": True},
            reply_to_step_id="confirm_identity",
        )
        self.assertTrue(st.identity_confirmed)
        self.assertEqual(st.current_step, "confirm_awareness")

    def test_confirm_identity_name_reply_requires_explicit_confirmation_when_name_was_not_known(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True)
        st.current_step = "confirm_identity"
        eng.update_from_user(
            "मेरा नाम विश्वजीत तिवारी है",
            st,
            extracted={"customer_name": "विश्वजीत तिवारी", "identity_name_preexisting": False},
            reply_to_step_id="confirm_identity",
        )
        self.assertFalse(st.identity_confirmed)
        self.assertEqual(st.identity_prompt_mode, "confirm_known_name")
        self.assertEqual(st.last_transition_reason, "identity_name_captured")
        self.assertEqual(st.current_step, "confirm_identity")

    def test_confirm_identity_followup_yes_confirms_name_captured_in_previous_turn(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(
            consent=True,
            identity_confirmed=False,
            identity_prompt_mode="confirm_known_name",
            current_step="confirm_identity",
            last_transition_reason="identity_name_captured",
        )
        eng.update_from_user(
            "हाँ",
            st,
            extracted={"customer_name": "विश्वजीत तिवारी", "identity_name_preexisting": False},
            reply_to_step_id="confirm_identity",
        )
        self.assertTrue(st.identity_confirmed)
        self.assertEqual(st.current_step, "confirm_awareness")

    def test_awareness_clarification_keeps_step_pending(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True)
        st.current_step = "confirm_awareness"
        eng.update_from_user("what do you mean", st, reply_to_step_id="confirm_awareness")
        self.assertFalse(st.awareness_confirmed)
        self.assertEqual(st.current_step, "confirm_awareness")

    def test_name_reconfirmation_keeps_awareness_step_pending(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True)
        st.current_step = "confirm_awareness"
        eng.update_from_user(
            "आपने मेरा नाम सुना?",
            st,
            extracted={"customer_name": "विश्वजीत तिवारी", "identity_name_preexisting": True},
            reply_to_step_id="confirm_awareness",
        )
        self.assertFalse(st.awareness_confirmed)
        self.assertEqual(st.current_step, "confirm_awareness")
        self.assertEqual(st.last_transition_reason, "identity_reconfirm_requested")

    def test_hard_refusal_detected_in_ask_ptp_or_callback(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I cannot make payment, no money", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertTrue(st.refusal_detected)
        self.assertEqual(st.refusal_strength, "hard")
        self.assertEqual(st.refusal_reason, "inability")
        self.assertEqual(st.no_count, 1)
        self.assertTrue(st.callback_requested)

    def test_soft_refusal_detected_in_ask_ptp_or_callback(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("not yet, maybe later", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertTrue(st.refusal_detected)
        self.assertEqual(st.refusal_strength, "soft")
        self.assertEqual(st.refusal_reason, "inability")
        self.assertEqual(st.no_count, 1)

    def test_hindi_payment_refusal_requests_resolution_not_callback_loop(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("आप कभी भी कॉल बैक करिए, मैं भुगतान नहीं कर सकता।", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertTrue(st.refusal_detected)
        self.assertEqual(st.refusal_strength, "hard")
        self.assertEqual(st.refusal_reason, "inability")
        self.assertEqual(st.last_transition_reason, "resolve_refusal")
        self.assertEqual(st.current_step, "ask_ptp_or_callback")
        self.assertTrue(st.callback_requested)

    def test_hindi_payment_challenge_counts_as_hard_unwilling_refusal(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("नहीं करूंगा तो क्या कर लोगे?", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertTrue(st.refusal_detected)
        self.assertEqual(st.refusal_strength, "hard")
        self.assertEqual(st.refusal_reason, "unwilling")
        self.assertEqual(st.last_transition_reason, "resolve_refusal")
        self.assertEqual(st.current_step, "ask_ptp_or_callback")

    def test_hindi_uncertain_callback_phrase_sets_uncertain_commitment(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("मेरे को नहीं पता, आप देख लीजिए।", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertTrue(st.callback_requested)
        self.assertEqual(st.last_transition_reason, "uncertain_commitment")
        self.assertEqual(st.current_step, "ask_ptp_or_callback")

    def test_hindi_relative_payment_commitment_requires_ptp_confirmation(self):
        now = datetime(2026, 3, 7, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        st.last_transition_reason = "uncertain_commitment"
        eng.update_from_user("दो दिन में कर देंगे।", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.ptp_date, "2026-03-09")
        self.assertEqual(st.current_step, "confirm_ptp")
        self.assertTrue(st.ptp_confirmation_required)
        self.assertFalse(st.ptp_confirmed)

    def test_ambiguous_relative_timeline_requests_clarification(self):
        now = datetime(2026, 3, 7, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        st.last_transition_reason = "uncertain_commitment"
        eng.update_from_user("दो दिन में।", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertIsNone(st.ptp_date)
        self.assertEqual(st.current_step, "ask_ptp_or_callback")
        self.assertEqual(st.last_transition_reason, "ptp_callback_ambiguous")

    def test_hindi_do_not_call_request_closes_as_dnd(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("आप मेरे को कॉल ना ही करें तो अच्छा है।", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertTrue(st.dnd_requested)
        self.assertEqual(st.disposition, "dnd_requested")
        self.assertEqual(st.current_step, "closing")

    def test_refusal_then_valid_ptp_advances_flow(self):
        now = datetime(2026, 2, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I won't be able to pay", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertTrue(st.refusal_detected)
        eng.update_from_user("I will pay on 06/02/2026", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.ptp_date, "2026-02-06")
        self.assertEqual(st.current_step, "closing")
        self.assertTrue(st.refusal_detected)

    def test_retry_exceeded_closes_when_no_commitment(self):
        eng = WorkflowEngine(enable_advanced=True, max_retries=2)
        st = WorkflowState(
            consent=True,
            identity_confirmed=True,
            awareness_confirmed=True,
            payment_made=False,
            refusal_detected=True,
            refusal_strength="hard",
            refusal_reason="inability",
            no_count=3,
        )
        for _ in range(3):
            eng.update_from_assistant("When can you make the payment?", st)
        step = eng.compute_next_step(st)
        self.assertEqual(step, "closing")
        self.assertEqual(st.disposition, "refusal_unresolved")
        self.assertEqual(st.last_transition_reason, "retry_exceeded")

    def test_retry_exceeded_payment_status_keeps_clarifying(self):
        eng = WorkflowEngine(enable_advanced=True, max_retries=2)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True)
        for _ in range(3):
            eng.update_from_assistant("Have you made the payment?", st)
        step = eng.compute_next_step(st)
        self.assertEqual(step, "ask_payment_made")
        self.assertEqual(st.last_transition_reason, "payment_status_unclear")
        self.assertIsNone(st.payment_made)

    def test_conflict_paid_then_cannot_pay_resolves_to_unpaid(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True)
        st.current_step = "ask_payment_made"
        eng.update_from_user("I already paid", st, reply_to_step_id="ask_payment_made")
        self.assertTrue(st.payment_made)
        eng.update_from_user("I cannot make payment", st, reply_to_step_id="ask_payment_made")
        self.assertFalse(st.payment_made)
        self.assertTrue(st.refusal_detected)

    def test_mixed_yes_then_havent_made_resolves_to_unpaid(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True)
        st.current_step = "ask_payment_made"
        eng.update_from_user("Yes, I am waiting. I haven't made it.", st, reply_to_step_id="ask_payment_made")
        self.assertFalse(st.payment_made)
        self.assertEqual(st.current_step, "ask_ptp_or_callback")

    def test_reference_step_unpaid_correction_exits_utr_loop(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(
            consent=True,
            identity_confirmed=True,
            awareness_confirmed=True,
            payment_made=True,
        )
        st.current_step = "ask_reference_number"
        eng.update_from_user(
            "I haven't made the payment.",
            st,
            reply_to_step_id="ask_reference_number",
        )
        self.assertFalse(st.payment_made)
        self.assertEqual(st.current_step, "ask_ptp_or_callback")

    def test_reference_step_future_commitment_exits_utr_loop_and_confirms_ptp(self):
        now = datetime(2026, 2, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(
            consent=True,
            identity_confirmed=True,
            awareness_confirmed=True,
            payment_made=True,
        )
        st.current_step = "ask_reference_number"
        eng.update_from_user(
            "मैं कल कर दूंगा।",
            st,
            extracted={"ptp_date": "2026-02-06"},
            reply_to_step_id="ask_reference_number",
        )
        self.assertFalse(st.payment_made)
        self.assertEqual(st.ptp_date, "2026-02-06")
        self.assertEqual(st.current_step, "confirm_ptp")
        self.assertTrue(st.ptp_confirmation_required)

    def test_uncertain_commitment_sets_uncertainty_reason(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I'm not sure right now", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.last_transition_reason, "uncertain_commitment")
        self.assertTrue(st.callback_requested)
        self.assertEqual(st.current_step, "ask_ptp_or_callback")

    def test_relative_tomorrow_phrase_normalizes_to_iso(self):
        now = datetime(2026, 2, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("Let's say by tomorrow.", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.ptp_date, "2026-02-06")
        self.assertEqual(st.current_step, "confirm_ptp")
        self.assertTrue(st.ptp_confirmation_required)

    def test_relative_day_after_tomorrow_phrase_normalizes_to_iso(self):
        now = datetime(2026, 2, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("day after tomorrow", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.ptp_date, "2026-02-07")
        self.assertEqual(st.current_step, "confirm_ptp")
        self.assertTrue(st.ptp_confirmation_required)

    def test_ordinal_day_phrase_sets_ptp_in_current_month(self):
        now = datetime(2026, 3, 10, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I will make the payment on 12th", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.ptp_date, "2026-03-12")
        self.assertEqual(st.current_step, "closing")

    def test_ordinal_day_phrase_rolls_to_next_month_when_past(self):
        now = datetime(2026, 3, 20, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("Payment on 12th", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.ptp_date, "2026-04-12")
        self.assertEqual(st.current_step, "closing")

    def test_in_days_phrase_sets_ptp_not_callback_time(self):
        now = datetime(2026, 2, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        eng = WorkflowEngine(enable_advanced=True, now_fn=lambda: now)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I can pay in 10 days.", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.ptp_date, "2026-02-15")
        self.assertIsNone(st.callback_time)
        self.assertEqual(st.current_step, "confirm_ptp")
        self.assertTrue(st.ptp_confirmation_required)

    def test_confirm_ptp_yes_advances_to_closing(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(
            consent=True,
            identity_confirmed=True,
            awareness_confirmed=True,
            payment_made=False,
            ptp_date="2026-02-06",
            ptp_confirmation_required=True,
            current_step="confirm_ptp",
        )
        eng.update_from_user("हाँ", st, reply_to_step_id="confirm_ptp")
        self.assertTrue(st.ptp_confirmed)
        self.assertFalse(st.ptp_confirmation_required)
        self.assertEqual(st.disposition, "ptp_captured")
        self.assertEqual(st.current_step, "closing")

    def test_confirm_ptp_no_returns_to_commitment_capture(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(
            consent=True,
            identity_confirmed=True,
            awareness_confirmed=True,
            payment_made=False,
            ptp_date="2026-02-06",
            ptp_confirmation_required=True,
            current_step="confirm_ptp",
        )
        eng.update_from_user("नहीं", st, reply_to_step_id="confirm_ptp")
        self.assertIsNone(st.ptp_date)
        self.assertFalse(st.ptp_confirmed)
        self.assertFalse(st.ptp_confirmation_required)
        self.assertEqual(st.current_step, "ask_ptp_or_callback")

    def test_right_is_treated_as_yes_for_consent(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState()
        st.current_step = "consent"
        eng.update_from_user("Right", st, reply_to_step_id="consent")
        self.assertTrue(st.consent)

    def test_not_aware_does_not_force_unpaid_in_payment_step(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True)
        st.current_step = "ask_payment_made"
        eng.update_from_user("I was not even aware of that.", st, reply_to_step_id="ask_payment_made")
        self.assertIsNone(st.payment_made)
        self.assertEqual(st.last_transition_reason, "awareness_denied_context")

    def test_bare_number_does_not_become_callback_time(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("I think it's 9.", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertIsNone(st.callback_time)
        self.assertEqual(st.current_step, "ask_ptp_or_callback")

    def test_callback_intent_with_kal_prefers_callback_time(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("kal 11 baje call kariye", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.callback_time, "11:00")
        self.assertIsNone(st.ptp_date)
        self.assertEqual(st.current_step, "closing")

    def test_callback_range_infers_pm_hour(self):
        eng = WorkflowEngine(enable_advanced=True)
        st = WorkflowState(consent=True, identity_confirmed=True, awareness_confirmed=True, payment_made=False)
        st.current_step = "ask_ptp_or_callback"
        eng.update_from_user("Call me back between 2 and 3.", st, reply_to_step_id="ask_ptp_or_callback")
        self.assertEqual(st.callback_time, "14:00")


if __name__ == "__main__":
    unittest.main()
