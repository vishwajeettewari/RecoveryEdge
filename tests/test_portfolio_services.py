import tempfile
import unittest

from audit_store import SQLiteAuditStore
from campaign_service import CampaignService
from compliance_engine import ComplianceEngine
from followup_service import FollowupService
from integrations.crm_adapter import CRMAdapter
from knowledge_store import SQLiteFTSKnowledgeStore
from strategy_engine import StrategyEngine


class PortfolioServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = f"{self.tmp.name}/demo.db"
        self.audit = SQLiteAuditStore(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_strategy_engine_boundaries(self):
        eng = StrategyEngine()
        self.assertEqual(eng.classify(0).dpd_bucket, "0")
        self.assertEqual(eng.classify(15).strategy_mode, "soft_reminder")
        self.assertEqual(eng.classify(45).strategy_mode, "firm_commitment")
        self.assertEqual(eng.classify(70).strategy_mode, "high_urgency")
        self.assertEqual(eng.classify(120).strategy_mode, "pre_legal_caution")

    def test_strategy_engine_prioritizes_dispute_and_hardship_playbooks(self):
        eng = StrategyEngine()
        dispute = eng.classify(45, dispute_raised=True)
        self.assertEqual(dispute.strategy_mode, "dispute_resolution")
        self.assertIn("acknowledge_dispute", dispute.preferred_actions)

        hardship = eng.classify(75, hardship_detected=True, partial_payment_offered=True)
        self.assertEqual(hardship.strategy_mode, "hardship_partial_resolution")
        self.assertIn("accept_partial_payment", hardship.preferred_actions)

    def test_compliance_detects_sensitive_and_gate(self):
        eng = ComplianceEngine()
        out = eng.evaluate_assistant_text(
            text="Please share OTP and make payment now.",
            consent=False,
            identity_confirmed=False,
            current_step="ask_payment_made",
        )
        codes = {v.rule_code for v in out}
        self.assertIn("DISALLOWED_SENSITIVE_ASK", codes)
        self.assertIn("MISSING_CONSENT_GATE", codes)

    def test_compliance_detects_legal_hold_and_hardship_pressure(self):
        eng = ComplianceEngine()
        out = eng.evaluate_assistant_text(
            text="Pay now or I will speak to your office. Since you mentioned a problem, pay immediately.",
            consent=True,
            identity_confirmed=True,
            current_step="ask_ptp_or_callback",
            hardship_detected=True,
            legal_hold=True,
        )
        codes = {v.rule_code for v in out}
        self.assertIn("LEGAL_HOLD_COLLECTION_ASK", codes)
        self.assertIn("THIRD_PARTY_DISCLOSURE_RISK", codes)
        self.assertIn("HARDSHIP_PRESSURE_RISK", codes)

    def test_knowledge_store_preserves_indic_tokens(self):
        query = SQLiteFTSKnowledgeStore._fts_query("मुझे लोन स्टेटमेंट भेजो")
        self.assertEqual(query, "मुझे AND लोन AND स्टेटमेंट AND भेजो")

    def test_campaign_retry_and_metrics(self):
        svc = CampaignService(self.db_path)
        created = svc.create_campaign(name="T1", customer_ids=["A1", "B1", "C1"], max_attempts=2, retry_delay_minutes=1, batch_size=10)
        cid = created["campaign_id"]
        svc.set_status(cid, "active")
        r1 = svc.run_pending_batch(cid)
        self.assertGreaterEqual(r1["processed"], 1)
        m = svc.metrics(cid)
        self.assertEqual(m["total_accounts"], 3)
        self.assertIn(m["status"], {"active", "completed"})

    def test_followup_idempotency(self):
        svc = FollowupService(self.db_path)
        items1 = svc.schedule_ptp_followups(session_id="s1", customer_id="c1", ptp_date="2026-02-10", phone="999", channel="whatsapp")
        items2 = svc.schedule_ptp_followups(session_id="s1", customer_id="c1", ptp_date="2026-02-10", phone="999", channel="whatsapp")
        self.assertEqual(len(items1), 3)
        self.assertEqual([x["idempotency_key"] for x in items1], [x["idempotency_key"] for x in items2])

        callback1 = svc.schedule_callback_followup(
            session_id="s1",
            customer_id="c1",
            phone="999",
            callback_ts=1739185200.0,
            channel="voice",
        )
        callback2 = svc.schedule_callback_followup(
            session_id="s1",
            customer_id="c1",
            phone="999",
            callback_ts=1739185200.0,
            channel="voice",
        )
        self.assertEqual(len(callback1), 1)
        self.assertEqual(callback1[0]["idempotency_key"], callback2[0]["idempotency_key"])

    def test_crm_outbound_queue_and_replay(self):
        crm = CRMAdapter(self.db_path)
        self.audit.upsert_outcome(session_id="s-replay", customer_id="c9", disposition="ptp")
        replay = crm.replay_session("s-replay")
        self.assertTrue(replay["ok"])
        st1 = crm.status()
        self.assertGreaterEqual(st1["queued"], 1)
        crm.process_queue(limit=20)
        st2 = crm.status()
        self.assertGreaterEqual(st2["acked"] + st2["retry_scheduled"] + st2["dead_letter"], 1)


if __name__ == "__main__":
    unittest.main()
