import csv
import io
import json
import sqlite3
import tempfile
import unittest

from audit_store import SQLiteAuditStore
from campaign_service import CampaignService
from portfolio_service import PortfolioService
from workbench_service import WorkbenchService


class PortfolioWizardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = f"{self.tmp.name}/demo.db"
        self.data_dir = f"{self.tmp.name}/data"
        self.audit = SQLiteAuditStore(self.db_path)
        self.portfolio = PortfolioService(self.db_path, self.data_dir)
        self.campaign = CampaignService(self.db_path)
        self.workbench = WorkbenchService(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _csv_bytes(rows):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return buf.getvalue().encode("utf-8")

    def _upload_and_map(self, rows):
        upload = self.portfolio.upload(filename="portfolio.csv", content=self._csv_bytes(rows))
        mappings = {
            "customer_id": "customer_id",
            "phone": "phone",
            "amount_due": "amount_due",
            "dpd": "dpd",
            "language": "language",
        }
        mapped = self.portfolio.map_columns(
            upload_id=upload["upload_id"],
            mappings=mappings,
            portfolio_name="Pilot Portfolio",
        )
        return upload, mapped

    def test_upload_parse_csv(self):
        rows = [
            {"customer_id": "C1", "phone": "9876543210", "amount_due": "1000", "dpd": "15", "language": "en"},
            {"customer_id": "C2", "phone": "+919876543211", "amount_due": "2000", "dpd": "35", "language": "hi"},
        ]
        upload = self.portfolio.upload(filename="portfolio.csv", content=self._csv_bytes(rows))
        self.assertEqual(upload["row_count"], 2)
        source_cols = {c["source_col"] for c in upload["columns"]}
        self.assertIn("customer_id", source_cols)
        self.assertIn("phone", source_cols)

    def test_mapping_required_fields(self):
        rows = [{"cid": "C1", "ph": "9876543210", "amt": "500", "days": "10"}]
        upload = self.portfolio.upload(filename="portfolio.csv", content=self._csv_bytes(rows))
        with self.assertRaisesRegex(ValueError, "required_mappings_missing"):
            self.portfolio.map_columns(
                upload_id=upload["upload_id"],
                mappings={"cid": "customer_id", "ph": "phone"},
                portfolio_name="Bad Mapping",
            )

    def test_validation_catches_bad_phone_and_dpd(self):
        rows = [
            {"customer_id": "C1", "phone": "12345", "amount_due": "1000", "dpd": "10", "language": "en"},
            {"customer_id": "C2", "phone": "9876543210", "amount_due": "2000", "dpd": "-2", "language": "hi"},
            {"customer_id": "C3", "phone": "9999999999", "amount_due": "3000", "dpd": "5", "language": "en"},
        ]
        _, mapped = self._upload_and_map(rows)
        summary = self.portfolio.validate(portfolio_id=mapped["portfolio_id"])
        self.assertGreater(summary["issues"]["invalid_phones"], 0)
        self.assertGreater(summary["issues"]["invalid_dpd"], 0)
        self.assertLess(summary["data_quality_score"], 100)
        self.assertIn("top_issues", summary)

    def test_launch_seeds_campaign_accounts(self):
        rows = [
            {"customer_id": "C1", "phone": "9876543210", "amount_due": "1000", "dpd": "15", "language": "en"},
            {"customer_id": "C2", "phone": "12345", "amount_due": "2000", "dpd": "22", "language": "hi"},
            {"customer_id": "C3", "phone": "9876543211", "amount_due": "3000", "dpd": "-1", "language": "en"},
            {"customer_id": "C4", "phone": "+919876543212", "amount_due": "1800", "dpd": "61", "language": "ta"},
        ]
        _, mapped = self._upload_and_map(rows)
        summary = self.portfolio.validate(portfolio_id=mapped["portfolio_id"])
        self.assertEqual(summary["valid_rows"], 2)

        launch_candidates = self.portfolio.launch_candidates(
            portfolio_id=mapped["portfolio_id"],
            exclusion_id=None,
            exclude_predicate=None,
        )
        self.assertEqual(launch_candidates["selected_count"], 2)

        customer_ids = [r["customer_id"] for r in launch_candidates["selected_rows"]]
        created = self.campaign.create_campaign(name="W1", customer_ids=customer_ids, max_attempts=2, retry_delay_minutes=1, batch_size=25)
        launch_id = self.portfolio.record_launch(
            portfolio_id=mapped["portfolio_id"],
            campaign_id=created["campaign_id"],
            launch_config={"exclude_predicate": None, "excluded_count": launch_candidates["excluded_count"]},
        )
        tasks_created = self.workbench.seed_tasks(
            campaign_id=created["campaign_id"],
            portfolio_id=mapped["portfolio_id"],
            rows=launch_candidates["selected_rows"],
            actor="tester",
        )

        metrics = self.campaign.metrics(created["campaign_id"])
        self.assertEqual(metrics["total_accounts"], 2)
        self.assertEqual(tasks_created, 2)
        self.assertTrue(launch_id.startswith("lch-"))

        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT campaign_id, launch_config_json FROM campaign_launches WHERE id = ?", (launch_id,)).fetchone()
            self.assertIsNotNone(row)
            cfg = json.loads(row[1])
            self.assertIn("excluded_count", cfg)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
