from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, Optional

from approval_service import ApprovalService
from experiment_service import ExperimentService
from model_router_service import ModelRouterService


class RecoveryBrainService:
    def __init__(
        self,
        db_path: str,
        *,
        model_router: ModelRouterService,
        experiments: ExperimentService,
        approvals: ApprovalService,
    ) -> None:
        self.db_path = db_path
        self.model_router = model_router
        self.experiments = experiments
        self.approvals = approvals
        self._init_db()
        self._seed_default_policy()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nba_policies (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    constraints_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(tenant_id, name, version)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nba_decisions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    customer_id TEXT,
                    loan_account_id TEXT,
                    journey_id TEXT,
                    policy_id TEXT,
                    policy_version TEXT,
                    schema_version TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    message_json TEXT,
                    offer_json TEXT,
                    risk_score REAL,
                    approval_required INTEGER NOT NULL DEFAULT 0,
                    approval_id TEXT,
                    route_json TEXT,
                    features_json TEXT,
                    metadata_json TEXT,
                    actor TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kpi_snapshots (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    snapshot_type TEXT NOT NULL,
                    snapshot_json TEXT,
                    created_at REAL NOT NULL,
                    actor TEXT,
                    request_id TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_nba_decisions_tenant_customer ON nba_decisions(tenant_id, customer_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_nba_decisions_tenant_journey ON nba_decisions(tenant_id, journey_id, created_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_default_policy(self) -> None:
        now = time.time()
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT id
                FROM nba_policies
                WHERE tenant_id = 'default' AND name = 'baseline' AND version = 'v1'
                """,
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO nba_policies (
                        id, tenant_id, name, version, status, constraints_json, created_at, updated_at
                    ) VALUES (?, 'default', 'baseline', 'v1', 'ACTIVE', ?, ?, ?)
                    """,
                    (
                        f"nbp-{uuid.uuid4().hex[:12]}",
                        json.dumps(
                            {
                                "approval_threshold": 0.75,
                                "max_settlement_ratio": 0.85,
                                "preferred_channels": ["whatsapp", "voice", "sms", "email"],
                            },
                            ensure_ascii=False,
                        ),
                        now,
                        now,
                    ),
                )
                conn.commit()
        finally:
            conn.close()

    def decide_nba(
        self,
        *,
        tenant_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        customer_id = str(payload.get("customer_id") or "").strip() or None
        if not customer_id:
            raise ValueError("customer_id_required")

        loan_account_id = str(payload.get("loan_account_id") or "").strip() or None
        journey_id = str(payload.get("journey_id") or "").strip() or None
        features = payload.get("features") if isinstance(payload.get("features"), dict) else {}

        policy = self._resolve_policy(tenant_id=tenant_id)
        constraints = policy.get("constraints") if isinstance(policy.get("constraints"), dict) else {}
        approval_threshold = self._to_float(constraints.get("approval_threshold")) or 0.75
        max_settlement_ratio = self._to_float(constraints.get("max_settlement_ratio")) or 0.85

        dpd = int(self._to_float(features.get("dpd") or payload.get("dpd") or 0) or 0)
        amount_due = float(self._to_float(features.get("amount_due") or payload.get("amount_due") or 0.0) or 0.0)
        hardship_flag = bool(features.get("hardship") or False)
        dispute_flag = bool(features.get("dispute") or False)
        last_outcome = str(features.get("last_outcome") or "").strip().lower()

        risk_score = min(1.0, (dpd / 180.0) + (0.25 if hardship_flag else 0.0) + (0.25 if dispute_flag else 0.0))
        preferred_channel = self._pick_channel(features=features, constraints=constraints)

        action_type = "send_reminder"
        offer_payload: Optional[Dict[str, Any]] = None
        if dispute_flag:
            action_type = "escalate_dispute"
        elif hardship_flag or dpd >= 90:
            action_type = "offer_settlement"
            offer_payload = {
                "settlement_ratio": round(min(max_settlement_ratio, 0.7 + (dpd / 600.0)), 3),
                "max_tenure_months": 3 if dpd < 120 else 6,
                "expiry_hours": 72,
            }
        elif last_outcome in {"no_answer", "unreachable"}:
            action_type = "reschedule_contact"
        elif dpd >= 30:
            action_type = "request_payment_commitment"

        route = self.model_router.route(
            tenant_id=tenant_id,
            task_type="scripted_collection_turn",
            modality="llm",
            policy=payload.get("model_policy") if isinstance(payload.get("model_policy"), dict) else None,
        )

        experiment_assignment = None
        experiment_id = str(payload.get("experiment_id") or "").strip()
        if experiment_id:
            experiment_assignment = self.experiments.assign(
                tenant_id=tenant_id,
                experiment_id=experiment_id,
                unit_id=customer_id,
                actor=actor,
                request_id=request_id,
                source="recovery_brain",
            )

        message = self._compose_message(action_type=action_type, amount_due=amount_due, dpd=dpd)

        approval_required = risk_score >= approval_threshold or action_type in {"offer_settlement", "escalate_dispute"}
        approval_id = None
        if approval_required:
            queued = self.approvals.enqueue(
                tenant_id=tenant_id,
                action_type=action_type,
                actor=actor,
                request_id=request_id,
                reference_type="nba_decision",
                reference_id=None,
                risk_score=risk_score,
                payload={
                    "customer_id": customer_id,
                    "loan_account_id": loan_account_id,
                    "journey_id": journey_id,
                    "action_type": action_type,
                    "message": message,
                    "offer": offer_payload,
                },
                policy_version=str(policy.get("version") or "v1"),
            )
            approval_id = queued.get("id")

        decision_id = f"nbd-{uuid.uuid4().hex[:12]}"
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO nba_decisions (
                    id, tenant_id, customer_id, loan_account_id, journey_id,
                    policy_id, policy_version, schema_version,
                    action_type, channel, message_json, offer_json,
                    risk_score, approval_required, approval_id,
                    route_json, features_json, metadata_json,
                    actor, request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    tenant_id,
                    customer_id,
                    loan_account_id,
                    journey_id,
                    policy.get("id"),
                    policy.get("version"),
                    "v2.1",
                    action_type,
                    preferred_channel,
                    json.dumps(message, ensure_ascii=False),
                    json.dumps(offer_payload or {}, ensure_ascii=False),
                    risk_score,
                    1 if approval_required else 0,
                    approval_id,
                    json.dumps(route, ensure_ascii=False),
                    json.dumps(features, ensure_ascii=False),
                    json.dumps({"experiment_assignment": experiment_assignment}, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO kpi_snapshots (
                    id, tenant_id, snapshot_type, snapshot_json, created_at, actor, request_id
                ) VALUES (?, ?, 'nba_decision', ?, ?, ?, ?)
                """,
                (
                    f"kpi-{uuid.uuid4().hex[:12]}",
                    tenant_id,
                    json.dumps(
                        {
                            "decision_id": decision_id,
                            "risk_score": risk_score,
                            "approval_required": approval_required,
                            "action_type": action_type,
                        },
                        ensure_ascii=False,
                    ),
                    now,
                    actor,
                    request_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self.model_router.record_invocation(
            tenant_id=tenant_id,
            task_type="scripted_collection_turn",
            modality="llm",
            provider=str(route.get("provider") or "unknown"),
            model_name=str(route.get("model_name") or "unknown"),
            route_id=route.get("route_id"),
            request_id=request_id,
            actor=actor,
            status="ROUTED",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            payload={"decision_id": decision_id, "action_type": action_type},
        )

        return self.get_decision(tenant_id=tenant_id, decision_id=decision_id) or {}

    def get_decision(self, *, tenant_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM nba_decisions WHERE tenant_id = ? AND id = ?",
                (tenant_id, decision_id),
            ).fetchone()
            if row is None:
                return None
            return self._decision_to_dict(row)
        finally:
            conn.close()

    def get_uplift_snapshot(self, *, tenant_id: str, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        base = self.experiments.compute_uplift(tenant_id=tenant_id, experiment_id=experiment_id)
        conn = self._connect()
        try:
            total_decisions = conn.execute(
                "SELECT COUNT(*) AS n FROM nba_decisions WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()["n"]
            approvals_pending = conn.execute(
                "SELECT COUNT(*) AS n FROM approval_queue WHERE tenant_id = ? AND status = 'PENDING'",
                (tenant_id,),
            ).fetchone()["n"]
            base["decision_volume"] = int(total_decisions or 0)
            base["approvals_pending"] = int(approvals_pending or 0)
            base["schema_version"] = "v2.1"
            return base
        finally:
            conn.close()

    def _resolve_policy(self, *, tenant_id: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT *
                FROM nba_policies
                WHERE tenant_id IN (?, 'default') AND status = 'ACTIVE'
                ORDER BY CASE WHEN tenant_id = ? THEN 0 ELSE 1 END ASC, updated_at DESC
                LIMIT 1
                """,
                (tenant_id, tenant_id),
            ).fetchone()
            if row is None:
                return {"id": None, "version": "v1", "constraints": {}}
            out = dict(row)
            out["constraints"] = json.loads(out.pop("constraints_json") or "{}")
            return out
        finally:
            conn.close()

    @staticmethod
    def _pick_channel(*, features: Dict[str, Any], constraints: Dict[str, Any]) -> str:
        preferred = constraints.get("preferred_channels") if isinstance(constraints.get("preferred_channels"), list) else []
        allowed = [str(v).strip().lower() for v in preferred if str(v).strip()]
        last_channel = str(features.get("last_channel") or "").strip().lower()
        if last_channel and last_channel in allowed and bool(features.get("responded_last_time") or False):
            return last_channel
        if allowed:
            return allowed[0]
        return "voice"

    @staticmethod
    def _compose_message(*, action_type: str, amount_due: float, dpd: int) -> Dict[str, Any]:
        if action_type == "offer_settlement":
            text = f"We can help close your overdue account (DPD {dpd}). Are you open to a settlement plan?"
        elif action_type == "escalate_dispute":
            text = "We noted your dispute and will route this to a specialist for verification."
        elif action_type == "request_payment_commitment":
            text = f"Your overdue amount is INR {amount_due:.2f}. Can you commit a payment date today?"
        elif action_type == "reschedule_contact":
            text = "We missed you earlier. Please share a suitable callback time today."
        else:
            text = f"Friendly reminder: INR {amount_due:.2f} is overdue. Would you like a payment link now?"
        return {
            "text": text,
            "language": "en-IN",
            "tone": "empathetic_firm",
            "schema_version": "v2.1",
        }

    @staticmethod
    def _decision_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["message"] = json.loads(out.pop("message_json") or "{}")
        out["offer"] = json.loads(out.pop("offer_json") or "{}")
        out["route"] = json.loads(out.pop("route_json") or "{}")
        out["features"] = json.loads(out.pop("features_json") or "{}")
        out["metadata"] = json.loads(out.pop("metadata_json") or "{}")
        out["approval_required"] = bool(int(out.get("approval_required") or 0))
        return out

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except Exception:
            return None
