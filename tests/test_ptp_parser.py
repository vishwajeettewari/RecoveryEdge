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

    def test_correction_marks_override(self):
        result = parse_ptp_date("नहीं 11", tz="Asia/Kolkata", now=NOW)
        self.assertEqual(result.ptp_date, "2026-03-11")
        self.assertTrue(result.corrected)


if __name__ == "__main__":
    unittest.main()
