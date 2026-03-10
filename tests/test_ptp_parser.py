from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from ptp_parser import parse_ptp_date


NOW = datetime(2026, 3, 10, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


class PTPParserTests(unittest.TestCase):
    def test_explicit_hindi_day_month(self):
        result = parse_ptp_date("11 मार्च तक", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-11")
        self.assertGreaterEqual(result.confidence, 0.9)

    def test_hindi_number_word(self):
        result = parse_ptp_date("ग्यारह", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-11")

    def test_relative_tomorrow(self):
        result = parse_ptp_date("kal kar dunga", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-11")

    def test_relative_day_after_tomorrow(self):
        result = parse_ptp_date("parso", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-12")

    def test_relative_two_days(self):
        result = parse_ptp_date("2 din mein", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-12")

    def test_punjabi_tomorrow_variant(self):
        result = parse_ptp_date("ਕੱਲ੍ਹ", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-11")

    def test_relative_minutes_maps_to_same_day(self):
        result = parse_ptp_date("अभी 5 मिनट बाद भुगतान कर दूँगा", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-10")
        self.assertGreaterEqual(result.confidence, 0.7)

    def test_correction_marks_override(self):
        result = parse_ptp_date("नहीं 11", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-11")
        self.assertTrue(result.corrected)

    def test_day_only_hindi_correction_phrase(self):
        result = parse_ptp_date("11 को कर दो", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-11")

    def test_longer_hindi_commitment_with_day_only_date(self):
        result = parse_ptp_date("मैं कह रहा हूँ मैं 11 को कर लूँगा", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-11")


if __name__ == "__main__":
    unittest.main()
