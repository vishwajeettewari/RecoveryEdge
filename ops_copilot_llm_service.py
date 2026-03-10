from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Sequence

import httpx

from model_router_service import ModelRouterService
from ws_utils import connect_ws

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are the Operations Copilot for a collections platform.

You must explain performance and next-best actions using ONLY the grounded JSON context provided by the application.

Rules:
- Never invent metrics, entities, buckets, campaigns, or performance claims.
- If the context is thin or there is not enough comparison data, say so directly.
- Keep the operator-facing answer concise and specific.
- Preserve the meaning of the structured recommendations supplied by the application.
- You may rewrite operator-facing wording, but do not change numeric impact ranges, confidence labels, or action mechanics.
- Do not output markdown.

Return valid JSON with this shape:
{
  "answer": "2-4 sentence grounded explanation",
  "quick_replies": ["short prompt", "short prompt", "short prompt", "short prompt"],
  "summary_detail_overrides": [{"label": "Exact existing label", "detail": "Grounded rewrite"}],
  "recommendation_overrides": [{"id": "existing recommendation id", "summary": "Grounded rewrite", "rationale": "Grounded rewrite"}]
}

If no override is needed for a field, return an empty array for that field.
""".strip()


class OpsCopilotLLMService:
    def __init__(
        self,
        *,
        endpoint: Optional[str],
        api_key: Optional[str],
        deployment: Optional[str],
        api_version: str = "2024-10-21",
        timeout_s: float = 15.0,
        enabled: bool = True,
        model_router: Optional[ModelRouterService] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.endpoint = (endpoint or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.deployment = (deployment or "").strip()
        self.api_version = (api_version or "2024-10-21").strip()
        self.timeout_s = max(1.0, float(timeout_s or 15.0))
        self.enabled = bool(enabled)
        self.model_router = model_router
        self.transport = transport

    def is_configured(self) -> bool:
        return self.enabled and bool(self.endpoint and self.api_key and self.deployment)

    def generate_readout(
        self,
        *,
        tenant_id: str,
        actor: str,
        role: str,
        request_id: str,
        question: str,
        scope: Dict[str, Any],
        summary: Sequence[Dict[str, Any]],
        evidence: Sequence[Dict[str, Any]],
        recommendations: Sequence[Dict[str, Any]],
        quick_replies: Sequence[str],
        campaigns: Sequence[Dict[str, Any]],
        buckets: Sequence[Dict[str, Any]],
        agents: Sequence[Dict[str, Any]],
        customers: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            return None

        started = time.time()
        status = "failed"
        input_tokens = None
        output_tokens = None
        payload_excerpt: Dict[str, Any] = {
            "question": question,
            "scope": scope,
            "role": role,
        }
        try:
            request_payload = {
                "question": question,
                "scope": scope,
                "summary": summary,
                "evidence": evidence,
                "recommendations": recommendations,
                "quick_replies": quick_replies,
                "campaigns": campaigns,
                "buckets": buckets,
                "agents": agents,
                "customers": customers,
            }
            if self._uses_realtime_api():
                raw_text, usage = self._call_realtime_completion(
                    question=question,
                    scope=scope,
                    summary=summary,
                    evidence=evidence,
                    recommendations=recommendations,
                    quick_replies=quick_replies,
                    campaigns=campaigns,
                    buckets=buckets,
                    agents=agents,
                    customers=customers,
                )
            else:
                body = self._call_chat_completions(
                    question=question,
                    scope=scope,
                    summary=summary,
                    evidence=evidence,
                    recommendations=recommendations,
                    quick_replies=quick_replies,
                    campaigns=campaigns,
                    buckets=buckets,
                    agents=agents,
                    customers=customers,
                )
                usage = body.get("usage") if isinstance(body, dict) else {}
                raw_text = self._response_text(body)
            if isinstance(usage, dict):
                input_tokens = self._int_or_none(
                    usage.get("prompt_tokens")
                    if "prompt_tokens" in usage
                    else usage.get("input_tokens")
                )
                output_tokens = self._int_or_none(
                    usage.get("completion_tokens")
                    if "completion_tokens" in usage
                    else usage.get("output_tokens")
                )
            parsed = self._parse_json_object(raw_text)
            answer = str(parsed.get("answer") or "").strip()
            if not answer:
                raise ValueError("ops_copilot_llm_missing_answer")
            status = "succeeded"
            return {
                "answer": answer,
                "quick_replies": self._normalize_quick_replies(parsed.get("quick_replies")),
                "summary_detail_overrides": self._normalize_summary_detail_overrides(parsed.get("summary_detail_overrides")),
                "recommendation_overrides": self._normalize_recommendation_overrides(parsed.get("recommendation_overrides")),
            }
        except Exception as exc:
            payload_excerpt["error"] = str(exc)
            logger.warning("ops_copilot_llm_error", extra={"request_id": request_id, "error": str(exc)})
            return None
        finally:
            if self.model_router is not None:
                try:
                    self.model_router.record_invocation(
                        tenant_id=tenant_id,
                        task_type="ops_copilot",
                        modality="llm",
                        provider="azure_openai",
                        model_name=self.deployment or "unknown",
                        route_id=None,
                        request_id=request_id,
                        actor=actor,
                        status=status,
                        latency_ms=int((time.time() - started) * 1000),
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        payload=payload_excerpt,
                    )
                except Exception:
                    logger.exception("ops_copilot_invocation_record_failed")

    def _uses_realtime_api(self) -> bool:
        return "realtime" in self.deployment.lower()

    def _call_chat_completions(
        self,
        *,
        question: str,
        scope: Dict[str, Any],
        summary: Sequence[Dict[str, Any]],
        evidence: Sequence[Dict[str, Any]],
        recommendations: Sequence[Dict[str, Any]],
        quick_replies: Sequence[str],
        campaigns: Sequence[Dict[str, Any]],
        buckets: Sequence[Dict[str, Any]],
        agents: Sequence[Dict[str, Any]],
        customers: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        request_payload = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        self._grounding_context(
                            question=question,
                            scope=scope,
                            summary=summary,
                            evidence=evidence,
                            recommendations=recommendations,
                            quick_replies=quick_replies,
                            campaigns=campaigns,
                            buckets=buckets,
                            agents=agents,
                            customers=customers,
                        ),
                        ensure_ascii=False,
                    ),
                },
            ],
            "max_completion_tokens": 900,
        }
        with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
            response = client.post(
                self._chat_completions_url(),
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=request_payload,
            )
            response.raise_for_status()
            return response.json()

    def _call_realtime_completion(
        self,
        *,
        question: str,
        scope: Dict[str, Any],
        summary: Sequence[Dict[str, Any]],
        evidence: Sequence[Dict[str, Any]],
        recommendations: Sequence[Dict[str, Any]],
        quick_replies: Sequence[str],
        campaigns: Sequence[Dict[str, Any]],
        buckets: Sequence[Dict[str, Any]],
        agents: Sequence[Dict[str, Any]],
        customers: Sequence[Dict[str, Any]],
    ) -> tuple[str, Dict[str, Any]]:
        context = self._grounding_context(
            question=question,
            scope=scope,
            summary=summary,
            evidence=evidence,
            recommendations=recommendations,
            quick_replies=quick_replies,
            campaigns=campaigns,
            buckets=buckets,
            agents=agents,
            customers=customers,
        )
        return asyncio.run(self._call_realtime_completion_async(context))

    async def _call_realtime_completion_async(self, context: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        event = {
            "type": "response.create",
            "response": {
                "conversation": "none",
                "modalities": ["text"],
                "instructions": SYSTEM_PROMPT,
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": json.dumps(context, ensure_ascii=False),
                            }
                        ],
                    }
                ],
            },
        }
        async with connect_ws(
            self._realtime_url(),
            headers={"api-key": self.api_key},
            max_queue=8,
        ) as websocket:
            await websocket.send(json.dumps(event, ensure_ascii=False))
            async for message in websocket:
                data = json.loads(message)
                event_type = str(data.get("type") or "")
                if event_type == "error":
                    error = data.get("error") if isinstance(data.get("error"), dict) else {}
                    raise RuntimeError(str(error.get("message") or "azure_realtime_error"))
                if event_type == "response.done":
                    response = data.get("response") if isinstance(data.get("response"), dict) else {}
                    return self._realtime_response_text(response), self._realtime_usage(response)
        raise RuntimeError("azure_realtime_no_response_done")

    def _chat_completions_url(self) -> str:
        if "/openai/deployments/" in self.endpoint:
            base = self.endpoint
            if not base.endswith("/chat/completions"):
                base = f"{base}/chat/completions"
            return f"{base}?api-version={self.api_version}"
        return (
            f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
            f"?api-version={self.api_version}"
        )

    def _realtime_url(self) -> str:
        base = self.endpoint
        if base.startswith("https://"):
            base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            base = "ws://" + base[len("http://") :]
        return f"{base}/openai/realtime?api-version={self.api_version}&deployment={self.deployment}"

    @staticmethod
    def _grounding_context(
        *,
        question: str,
        scope: Dict[str, Any],
        summary: Sequence[Dict[str, Any]],
        evidence: Sequence[Dict[str, Any]],
        recommendations: Sequence[Dict[str, Any]],
        quick_replies: Sequence[str],
        campaigns: Sequence[Dict[str, Any]],
        buckets: Sequence[Dict[str, Any]],
        agents: Sequence[Dict[str, Any]],
        customers: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "question": question,
            "scope": scope,
            "summary_cards": list(summary),
            "evidence_cards": list(evidence),
            "recommendations": [
                {
                    "id": row.get("id"),
                    "kind": row.get("kind"),
                    "title": row.get("title"),
                    "summary": row.get("summary"),
                    "rationale": row.get("rationale"),
                    "confidence": row.get("confidence"),
                    "expected_impact": row.get("expected_impact"),
                    "actions": [
                        {
                            "id": action.get("id"),
                            "title": action.get("title"),
                            "summary": action.get("summary"),
                            "approval_mode": action.get("approval_mode"),
                            "action_type": action.get("action_type"),
                        }
                        for action in row.get("actions", [])
                        if isinstance(action, dict)
                    ],
                }
                for row in recommendations
                if isinstance(row, dict)
            ],
            "suggested_quick_replies": list(quick_replies),
            "supporting_metrics": {
                "campaigns": [
                    {
                        "campaign_id": row.get("campaign_id"),
                        "name": row.get("name"),
                        "score": row.get("score"),
                        "contact_rate_pct": row.get("contact_rate_pct"),
                        "followup_discipline_rate_pct": row.get("followup_discipline_rate_pct"),
                        "containment_rate_pct": row.get("containment_rate_pct"),
                        "recovery_rate_pct": row.get("recovery_rate_pct"),
                        "total_accounts": row.get("total_accounts"),
                    }
                    for row in campaigns[:5]
                ],
                "buckets": [
                    {
                        "bucket": row.get("bucket"),
                        "sample_size": row.get("sample_size"),
                        "exposure": row.get("exposure"),
                        "ptp_rate_pct": row.get("ptp_rate_pct"),
                        "missed_ptp_rate_pct": row.get("missed_ptp_rate_pct"),
                        "roll_forward_pct": row.get("roll_forward_pct"),
                        "containment_rate_pct": row.get("containment_rate_pct"),
                        "current_strategy": row.get("current_strategy"),
                        "current_tone": row.get("current_tone"),
                        "confidence": row.get("confidence"),
                    }
                    for row in buckets
                    if int(row.get("sample_size") or 0) > 0
                ][:5],
                "agents": [
                    {
                        "agent_id": row.get("agent_id"),
                        "display_name": row.get("display_name"),
                        "total_calls": row.get("total_calls"),
                        "connect_rate_pct": row.get("connect_rate_pct"),
                        "ptp_conversion_pct": row.get("ptp_conversion_pct"),
                        "compliance_violations": row.get("compliance_violations"),
                        "score": row.get("score"),
                    }
                    for row in agents[:5]
                ],
                "customers": [
                    {
                        "customer_id": row.get("customer_id"),
                        "customer_name": row.get("customer_name"),
                        "dpd": row.get("dpd"),
                        "amount_due": row.get("amount_due"),
                        "state": row.get("state"),
                        "risk_score": row.get("risk_score"),
                        "open_ptp_alerts": row.get("open_ptp_alerts"),
                    }
                    for row in customers[:5]
                ],
            },
        }

    @staticmethod
    def _response_text(body: Dict[str, Any]) -> str:
        choices = body.get("choices") if isinstance(body, dict) else None
        first = choices[0] if isinstance(choices, list) and choices else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        return ""

    @staticmethod
    def _realtime_response_text(response: Dict[str, Any]) -> str:
        output = response.get("output") if isinstance(response, dict) else None
        text_parts: List[str] = []
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if str(part.get("type") or "") in {"output_text", "text"}:
                        text = str(part.get("text") or "").strip()
                        if text:
                            text_parts.append(text)
        text = "".join(text_parts).strip()
        if not text:
            raise ValueError("azure_realtime_empty_text")
        return text

    @staticmethod
    def _realtime_usage(response: Dict[str, Any]) -> Dict[str, Any]:
        usage = response.get("usage") if isinstance(response, dict) and isinstance(response.get("usage"), dict) else {}
        if not usage:
            return {}
        return {
            "input_tokens": usage.get("input_tokens")
            or usage.get("prompt_tokens"),
            "output_tokens": usage.get("output_tokens")
            or usage.get("completion_tokens"),
        }

    @staticmethod
    def _parse_json_object(raw_text: str) -> Dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            raise ValueError("ops_copilot_llm_empty_response")
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("ops_copilot_llm_non_json_response")
        parsed = json.loads(text[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("ops_copilot_llm_non_object_response")
        return parsed

    @staticmethod
    def _normalize_quick_replies(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        out: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if not text or text in out:
                continue
            out.append(text)
            if len(out) >= 4:
                break
        return out

    @staticmethod
    def _normalize_summary_detail_overrides(value: Any) -> List[Dict[str, str]]:
        if not isinstance(value, list):
            return []
        out: List[Dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            detail = str(item.get("detail") or "").strip()
            if not label or not detail:
                continue
            out.append({"label": label, "detail": detail})
        return out

    @staticmethod
    def _normalize_recommendation_overrides(value: Any) -> List[Dict[str, str]]:
        if not isinstance(value, list):
            return []
        out: List[Dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            rec_id = str(item.get("id") or "").strip()
            summary = str(item.get("summary") or "").strip()
            rationale = str(item.get("rationale") or "").strip()
            if not rec_id:
                continue
            out.append({"id": rec_id, "summary": summary, "rationale": rationale})
        return out

    @staticmethod
    def _int_or_none(value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None
