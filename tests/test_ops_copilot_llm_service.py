import json
import sqlite3
import tempfile
import unittest

import httpx

from model_router_service import ModelRouterService
from ops_copilot_llm_service import OpsCopilotLLMService


class OpsCopilotLLMServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = f"{self.tmp.name}/demo.db"
        self.model_router = ModelRouterService(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _service(self, handler):
        return OpsCopilotLLMService(
            endpoint="https://example.openai.azure.com",
            api_key="test-key",
            deployment="ops-copilot-test",
            api_version="2024-10-21",
            model_router=self.model_router,
            transport=httpx.MockTransport(handler),
        )

    def _invocation_rows(self):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                "SELECT provider, model_name, status, input_tokens, output_tokens FROM model_invocations ORDER BY created_at ASC"
            ).fetchall()
        finally:
            conn.close()

    @staticmethod
    def _base_kwargs():
        return {
            "tenant_id": "default",
            "actor": "mgr",
            "role": "SUPERVISOR",
            "request_id": "req-ops-llm",
            "question": "What should I change this week?",
            "scope": {"campaign_id": None, "campaign_name": None, "scope_label": "All active campaigns", "campaign_selected": False},
            "summary": [{"label": "Best Bucket", "value": "31-60", "detail": "0.0% PTP conversion across 16 observed accounts"}],
            "evidence": [{"title": "31-60 is the strongest bucket", "summary": "Only populated bucket in the current window.", "sample_size": 16}],
            "recommendations": [
                {
                    "id": "rec-bucket-31-60",
                    "title": "Change the play for 31-60 DPD",
                    "summary": "Deterministic summary",
                    "rationale": "Deterministic rationale",
                    "actions": [],
                    "expected_impact": {"summary": "+2.5 to +4.0 pts PTP conversion"},
                }
            ],
            "quick_replies": ["What is working by bucket right now?"],
            "campaigns": [{"campaign_id": "cmp-1", "name": "Campaign 1", "score": 52.0}],
            "buckets": [{"bucket": "31-60", "sample_size": 16, "ptp_rate_pct": 0.0, "current_strategy": "firm_commitment"}],
            "agents": [],
            "customers": [],
        }

    def test_generate_readout_parses_json_and_records_invocation(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertIn("/openai/deployments/ops-copilot-test/chat/completions", str(request.url))
            payload = json.loads(request.content.decode("utf-8"))
            self.assertEqual(payload["messages"][0]["role"], "system")
            self.assertEqual(payload["messages"][1]["role"], "user")
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "answer": "LLM answer",
                                        "quick_replies": ["Which lane needs focus next?"],
                                        "summary_detail_overrides": [{"label": "Best Bucket", "detail": "LLM detail"}],
                                        "recommendation_overrides": [
                                            {
                                                "id": "rec-bucket-31-60",
                                                "summary": "LLM summary",
                                                "rationale": "LLM rationale",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 321, "completion_tokens": 87},
                },
            )

        service = self._service(handler)
        result = service.generate_readout(**self._base_kwargs())

        self.assertIsNotNone(result)
        self.assertEqual(result["answer"], "LLM answer")
        self.assertEqual(result["quick_replies"], ["Which lane needs focus next?"])
        self.assertEqual(result["summary_detail_overrides"][0]["detail"], "LLM detail")
        self.assertEqual(result["recommendation_overrides"][0]["summary"], "LLM summary")

        rows = self._invocation_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "azure_openai")
        self.assertEqual(rows[0][1], "ops-copilot-test")
        self.assertEqual(rows[0][2], "succeeded")
        self.assertEqual(rows[0][3], 321)
        self.assertEqual(rows[0][4], 87)

    def test_generate_readout_returns_none_and_records_failure_on_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": {"message": "bad request"}})

        service = self._service(handler)
        result = service.generate_readout(**self._base_kwargs())

        self.assertIsNone(result)
        rows = self._invocation_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "failed")


if __name__ == "__main__":
    unittest.main()
