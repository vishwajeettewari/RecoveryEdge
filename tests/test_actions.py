import unittest

from actions import ActionRouter


class ActionRouterTests(unittest.TestCase):
    def test_send_payment_link_uses_mock_when_twilio_not_configured(self):
        router = ActionRouter(pay_base_url="https://pay.example/demo")
        result = router.send_payment_link(
            session_id="s1",
            customer_id="C1",
            customer_phone="+919900000000",
            amount="1200",
            channel="sms",
        )
        self.assertEqual(result["provider"], "mock")
        self.assertEqual(result["delivery_status"], "simulated")
        self.assertTrue(result["delivery_ok"])
        self.assertTrue(str(result["message_id"]).startswith("msg-"))

    def test_send_payment_link_calls_twilio_with_sms_numbers(self):
        captured = {}

        router = ActionRouter(
            pay_base_url="https://pay.example/demo",
            twilio_account_sid="ACxxxx",
            twilio_auth_token="token",
            twilio_from_number="+17756406811",
        )

        def fake_send(*, to_number: str, from_number: str, body: str):
            captured["to"] = to_number
            captured["from"] = from_number
            captured["body"] = body
            return "SM123", "queued", None

        router._send_twilio_message = fake_send  # type: ignore[method-assign]

        result = router.send_payment_link(
            session_id="s2",
            customer_id="C2",
            customer_phone="+14155550100",
            amount="999",
            channel="sms",
        )
        self.assertEqual(captured["to"], "+14155550100")
        self.assertEqual(captured["from"], "+17756406811")
        self.assertIn("https://pay.example/demo", captured["body"])
        self.assertEqual(result["provider"], "twilio")
        self.assertEqual(result["message_id"], "SM123")
        self.assertEqual(result["delivery_status"], "queued")
        self.assertTrue(result["delivery_ok"])

    def test_send_payment_link_formats_whatsapp_addresses(self):
        captured = {}

        router = ActionRouter(
            pay_base_url="https://pay.example/demo",
            twilio_account_sid="ACxxxx",
            twilio_auth_token="token",
            twilio_from_number="+17756406811",
            twilio_whatsapp_from="whatsapp:+17756406811",
        )

        def fake_send(*, to_number: str, from_number: str, body: str):
            captured["to"] = to_number
            captured["from"] = from_number
            return "SM456", "sent", None

        router._send_twilio_message = fake_send  # type: ignore[method-assign]

        result = router.send_payment_link(
            session_id="s3",
            customer_id="C3",
            customer_phone="+918888888888",
            amount="500",
            channel="whatsapp",
        )
        self.assertEqual(captured["to"], "whatsapp:+918888888888")
        self.assertEqual(captured["from"], "whatsapp:+17756406811")
        self.assertEqual(result["provider"], "twilio")
        self.assertEqual(result["message_id"], "SM456")
        self.assertEqual(result["delivery_status"], "sent")
        self.assertTrue(result["delivery_ok"])

    def test_place_test_voice_call_sends_to_normalized_number(self):
        captured = {}
        router = ActionRouter(
            pay_base_url="https://pay.example/demo",
            twilio_account_sid="ACxxxx",
            twilio_auth_token="token",
            twilio_from_number="+17756406811",
        )

        def fake_call(*, to_number: str, from_number: str, twiml: str, timeout_s: int):
            captured["to"] = to_number
            captured["from"] = from_number
            captured["twiml"] = twiml
            captured["timeout_s"] = timeout_s
            return "CA123", "queued", None

        router._send_twilio_voice_call = fake_call  # type: ignore[method-assign]
        result = router.place_test_voice_call(
            customer_phone="+91-9950022999",
            customer_name="Ravi",
            amount="1500",
            timeout_s=20,
        )
        self.assertEqual(captured["to"], "+919950022999")
        self.assertEqual(captured["from"], "+17756406811")
        self.assertIn("Ravi", captured["twiml"])
        self.assertIn("1500", captured["twiml"])
        self.assertEqual(captured["timeout_s"], 20)
        self.assertEqual(result["call_sid"], "CA123")
        self.assertTrue(result["delivery_ok"])

    def test_place_test_voice_call_rejects_invalid_phone(self):
        router = ActionRouter(
            pay_base_url="https://pay.example/demo",
            twilio_account_sid="ACxxxx",
            twilio_auth_token="token",
            twilio_from_number="+17756406811",
        )
        result = router.place_test_voice_call(customer_phone="abcd")
        self.assertFalse(result["delivery_ok"])
        self.assertEqual(result["delivery_error"], "invalid_to_or_from_number")

    def test_place_agent_stream_call_uses_stream_ws_url(self):
        captured = {}
        router = ActionRouter(
            pay_base_url="https://pay.example/demo",
            twilio_account_sid="ACxxxx",
            twilio_auth_token="token",
            twilio_from_number="+17756406811",
        )

        def fake_call(*, to_number: str, from_number: str, twiml: str, timeout_s: int):
            captured["to"] = to_number
            captured["from"] = from_number
            captured["twiml"] = twiml
            return "CA999", "queued", None

        router._send_twilio_voice_call = fake_call  # type: ignore[method-assign]
        result = router.place_agent_stream_call(
            customer_phone="+91-9950022999",
            stream_ws_url="wss://example.ngrok-free.app/ws/twilio-media",
            customer_name="Asha",
            customer_id="CUST001",
            campaign_id="cmp-1",
            amount="1200",
            language="en-IN",
            tts_speaker="priya",
            timeout_s=20,
        )
        self.assertEqual(captured["to"], "+919950022999")
        self.assertIn("wss://example.ngrok-free.app/ws/twilio-media", captured["twiml"])
        self.assertIn("customer_name", captured["twiml"])
        self.assertIn("campaign_id", captured["twiml"])
        self.assertIn("tts_speaker", captured["twiml"])
        self.assertIn("priya", captured["twiml"])
        self.assertEqual(result["call_sid"], "CA999")
        self.assertTrue(result["delivery_ok"])


if __name__ == "__main__":
    unittest.main()
