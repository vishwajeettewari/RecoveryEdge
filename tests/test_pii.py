import unittest

from pii import redact_pii


class PiiTests(unittest.TestCase):
    def test_redacts_email_phone_pan(self):
        s = "Email rahul@example.com phone +91 99999 11111 PAN ABCDE1234F"
        out = redact_pii(s)
        self.assertIn("[REDACTED_EMAIL]", out)
        self.assertIn("[REDACTED_PHONE]", out)
        self.assertIn("[REDACTED_PAN]", out)


if __name__ == "__main__":
    unittest.main()

