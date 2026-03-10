from __future__ import annotations

import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from approval_service import ApprovalService
from audit_store import SQLiteAuditStore
from campaign_service import CampaignService
from experiment_service import ExperimentService
from strategy_engine import StrategyEngine


class OpsControlService:
    BUCKETS: Tuple[str, ...] = ("1-30", "31-60", "61-90", "90+")
    _RISK_ORDER = {"1-30": 1, "31-60": 2, "61-90": 3, "90+": 4}
    _STATE_PRIORITY = {"PTP": 0, "ESCALATED": 1, "CALLBACK": 2, "IN_PROGRESS": 3, "NEW": 4, "CLOSED": 5}

    def __init__(
        self,
        db_path: str,
        *,
        audit: SQLiteAuditStore,
        campaign_service: CampaignService,
        approvals: ApprovalService,
        experiments: ExperimentService,
        strategy_engine: StrategyEngine,
    ) -> None:
        self.db_path = db_path
        self.audit = audit
        self.campaign_service = campaign_service
        self.approvals = approvals
        self.experiments = experiments
        self.strategy_engine = strategy_engine

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def chat(
        self,
        *,
        tenant_id: str,
        actor: str,
        role: str,
        request_id: str,
        message: str,
        campaign_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_message = (message or "").strip()
        focus = self._detect_focus(normalized_message)
        campaigns = self._campaign_lens()
        buckets = self._bucket_lens(campaign_id=campaign_id)
        agents = self._agent_lens(campaign_id=campaign_id)
        customers = self._customer_lens(campaign_id=campaign_id)
        scope = self._scope(campaign_id=campaign_id, campaigns=campaigns)
        summary = self._summary_cards(scope=scope, campaigns=campaigns, buckets=buckets, agents=agents, customers=customers)
        evidence = self._evidence_cards(
            focus=focus,
            scope=scope,
            campaigns=campaigns,
            buckets=buckets,
            agents=agents,
            customers=customers,
        )
        recommendations = self._recommendations(scope=scope, campaigns=campaigns, buckets=buckets, agents=agents, customers=customers)
        quick_replies = self._quick_replies(campaign_selected=bool(campaign_id))
        answer = self._answer(
            focus=focus,
            scope=scope,
            campaigns=campaigns,
            buckets=buckets,
            agents=agents,
            customers=customers,
            recommendations=recommendations,
        )
        payload = {
            "scope": scope,
            "message": normalized_message,
            "answer": answer,
            "summary": summary,
            "evidence": evidence,
            "recommendations": recommendations,
            "quick_replies": quick_replies,
            "generated_at": time.time(),
            "actor": actor,
            "role": role,
            "tenant_id": tenant_id,
        }
        self.audit.record_event(
            event_type="ops_control_chat",
            payload={
                "tenant_id": tenant_id,
                "actor": actor,
                "role": role,
                "request_id": request_id,
                "campaign_id": campaign_id,
                "message": normalized_message,
                "focus": sorted(focus),
            },
        )
        return payload

    def apply_action(
        self,
        *,
        tenant_id: str,
        actor: str,
        role: str,
        request_id: str,
        action_type: str,
        payload: Dict[str, Any],
        can_mutate: bool,
    ) -> Dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        if action_type == "launch_experiment":
            return self._apply_launch_experiment(
                tenant_id=tenant_id,
                actor=actor,
                role=role,
                request_id=request_id,
                payload=body,
                can_mutate=can_mutate,
            )
        if action_type == "request_strategy_change":
            return self._queue_strategy_change(
                tenant_id=tenant_id,
                actor=actor,
                role=role,
                request_id=request_id,
                payload=body,
            )
        if action_type == "request_agent_rebalance":
            return self._queue_agent_rebalance(
                tenant_id=tenant_id,
                actor=actor,
                role=role,
                request_id=request_id,
                payload=body,
            )
        raise ValueError("unsupported_action_type")

    def _apply_launch_experiment(
        self,
        *,
        tenant_id: str,
        actor: str,
        role: str,
        request_id: str,
        payload: Dict[str, Any],
        can_mutate: bool,
    ) -> Dict[str, Any]:
        experiment_payload = {
            "name": str(payload.get("name") or "Ops Control Experiment").strip(),
            "objective": str(payload.get("objective") or "Improve collections performance").strip(),
            "control": str(payload.get("control") or "control").strip() or "control",
            "treatment": str(payload.get("treatment") or "treatment").strip() or "treatment",
            "split_ratio": float(payload.get("split_ratio") or 0.5),
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        }
        if can_mutate:
            experiment = self.experiments.create_experiment(
                tenant_id=tenant_id,
                payload=experiment_payload,
                actor=actor,
                request_id=request_id,
            )
            self.audit.record_event(
                event_type="ops_control_action",
                payload={
                    "tenant_id": tenant_id,
                    "actor": actor,
                    "role": role,
                    "request_id": request_id,
                    "action_type": "launch_experiment",
                    "result_type": "experiment_created",
                    "experiment_id": experiment.get("id"),
                    "payload": experiment_payload,
                },
            )
            return {
                "ok": True,
                "action_type": "launch_experiment",
                "result_type": "experiment_created",
                "message": f"Experiment {experiment.get('id')} created.",
                "experiment": experiment,
            }

        approval = self.approvals.enqueue(
            tenant_id=tenant_id,
            action_type="ops_control_launch_experiment",
            actor=actor,
            request_id=request_id,
            reference_type="campaign_bucket",
            reference_id=str(experiment_payload.get("metadata", {}).get("campaign_id") or "all"),
            risk_score=0.41,
            payload=experiment_payload,
            policy_version="ops_control_v1",
        )
        self.audit.record_event(
            event_type="ops_control_action",
            payload={
                "tenant_id": tenant_id,
                "actor": actor,
                "role": role,
                "request_id": request_id,
                "action_type": "launch_experiment",
                "result_type": "approval_queued",
                "approval_id": approval.get("id"),
                "payload": experiment_payload,
            },
        )
        return {
            "ok": True,
            "action_type": "launch_experiment",
            "result_type": "approval_queued",
            "message": f"Experiment proposal queued for approval as {approval.get('id')}.",
            "approval": approval,
        }

    def _queue_strategy_change(
        self,
        *,
        tenant_id: str,
        actor: str,
        role: str,
        request_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        bucket = str(payload.get("bucket") or "unknown").strip() or "unknown"
        approval = self.approvals.enqueue(
            tenant_id=tenant_id,
            action_type="ops_control_strategy_change",
            actor=actor,
            request_id=request_id,
            reference_type="campaign_bucket",
            reference_id=f"{str(payload.get('campaign_id') or 'all')}:{bucket}",
            risk_score=0.52 if bucket in {"61-90", "90+"} else 0.44,
            payload=payload,
            policy_version="ops_control_v1",
        )
        self.audit.record_event(
            event_type="ops_control_action",
            payload={
                "tenant_id": tenant_id,
                "actor": actor,
                "role": role,
                "request_id": request_id,
                "action_type": "request_strategy_change",
                "result_type": "approval_queued",
                "approval_id": approval.get("id"),
                "payload": payload,
            },
        )
        return {
            "ok": True,
            "action_type": "request_strategy_change",
            "result_type": "approval_queued",
            "message": f"Strategy change submitted for approval as {approval.get('id')}.",
            "approval": approval,
        }

    def _queue_agent_rebalance(
        self,
        *,
        tenant_id: str,
        actor: str,
        role: str,
        request_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        approval = self.approvals.enqueue(
            tenant_id=tenant_id,
            action_type="ops_control_agent_rebalance",
            actor=actor,
            request_id=request_id,
            reference_type="agent",
            reference_id=str(payload.get("target_agent_id") or "team"),
            risk_score=0.36,
            payload=payload,
            policy_version="ops_control_v1",
        )
        self.audit.record_event(
            event_type="ops_control_action",
            payload={
                "tenant_id": tenant_id,
                "actor": actor,
                "role": role,
                "request_id": request_id,
                "action_type": "request_agent_rebalance",
                "result_type": "approval_queued",
                "approval_id": approval.get("id"),
                "payload": payload,
            },
        )
        return {
            "ok": True,
            "action_type": "request_agent_rebalance",
            "result_type": "approval_queued",
            "message": f"Agent rebalance submitted for approval as {approval.get('id')}.",
            "approval": approval,
        }

    def _scope(self, *, campaign_id: Optional[str], campaigns: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        if campaign_id:
            selected = next((row for row in campaigns if row.get("campaign_id") == campaign_id), None)
            return {
                "campaign_id": campaign_id,
                "campaign_name": selected.get("name") if selected else campaign_id,
                "scope_label": f"{selected.get('name') if selected else campaign_id} ({campaign_id})",
                "campaign_selected": True,
            }
        return {
            "campaign_id": None,
            "campaign_name": None,
            "scope_label": "All active campaigns",
            "campaign_selected": False,
        }

    def _campaign_lens(self) -> List[Dict[str, Any]]:
        rows = self.campaign_service.list_campaigns(limit=50)
        out: List[Dict[str, Any]] = []
        for row in rows:
            campaign_id = str(row.get("campaign_id") or "").strip()
            if not campaign_id:
                continue
            campaign_meta = self.campaign_service.metrics(campaign_id)
            metrics = self.audit.metrics(campaign_id=campaign_id)
            recovery = self.audit.realized_recovery_trend(days=30, campaign_id=campaign_id)
            roll = self.audit.roll_forward_matrix(days=30, campaign_id=campaign_id)
            containment_rate = None if not roll.get("total_transitions") else round(100.0 - float(roll.get("roll_forward_pct") or 0.0), 1)
            score = self._campaign_score(
                contact_rate=float(metrics.get("contact_rate_pct") or 0.0),
                discipline=float(metrics.get("followup_discipline_rate_pct") or 0.0),
                recovery=float(recovery.get("recovery_rate_pct") or 0.0),
                containment=containment_rate,
            )
            sample = int(campaign_meta.get("total_accounts") or metrics.get("accounts_assigned") or 0)
            confidence = self._confidence(sample)
            out.append(
                {
                    "campaign_id": campaign_id,
                    "name": str(campaign_meta.get("name") or row.get("name") or campaign_id),
                    "status": str(campaign_meta.get("status") or row.get("status") or "created"),
                    "total_accounts": sample,
                    "contact_rate_pct": round(float(metrics.get("contact_rate_pct") or 0.0), 1),
                    "followup_discipline_rate_pct": round(float(metrics.get("followup_discipline_rate_pct") or 0.0), 1),
                    "recovery_rate_pct": round(float(recovery.get("recovery_rate_pct") or 0.0), 1),
                    "containment_rate_pct": containment_rate,
                    "ptp_count": int(metrics.get("ptp_count") or 0),
                    "ptp_miss_open_alerts": int(metrics.get("ptp_miss_open_alerts") or 0),
                    "expected_recovery_amount": float(metrics.get("expected_recovery_amount") or 0.0),
                    "score": score,
                    "confidence": confidence,
                }
            )
        out.sort(key=lambda item: (item.get("score") or 0.0), reverse=True)
        return out

    def _bucket_lens(self, *, campaign_id: Optional[str]) -> List[Dict[str, Any]]:
        roll = self.audit.roll_forward_matrix(days=30, campaign_id=campaign_id)
        with self._connect() as conn:
            out: List[Dict[str, Any]] = []
            for bucket in self.BUCKETS:
                task_where, task_args = self._bucket_task_filter(bucket=bucket, campaign_id=campaign_id)
                outcome_where, outcome_args = self._bucket_outcome_filter(bucket=bucket, campaign_id=campaign_id)
                followup_where, followup_args = self._bucket_followup_filter(bucket=bucket, campaign_id=campaign_id)

                exposure = self._query_number(
                    conn,
                    f"SELECT COUNT(*) AS n FROM tasks t WHERE {task_where}",
                    tuple(task_args),
                )
                avg_amount_due = self._query_number(
                    conn,
                    f"SELECT AVG(COALESCE(t.amount_due, 0)) AS v FROM tasks t WHERE {task_where}",
                    tuple(task_args),
                    key="v",
                )
                active_ptp = self._query_number(
                    conn,
                    f"SELECT COUNT(*) AS n FROM tasks t WHERE {task_where} AND t.state = 'PTP'",
                    tuple(task_args),
                )
                sla_breaches = self._query_number(
                    conn,
                    f"""SELECT COUNT(*) AS n
                    FROM tasks t
                    WHERE {task_where}
                      AND t.state != 'CLOSED'
                      AND COALESCE(t.sla_due_at, 0) > 0
                      AND t.sla_due_at < ?""",
                    tuple(task_args + [time.time()]),
                )
                outcome_row = self._query_row(
                    conn,
                    f"""SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN o.ptp_date IS NOT NULL AND o.ptp_date != '' THEN 1 ELSE 0 END) AS ptp,
                        SUM(CASE WHEN o.callback_time IS NOT NULL AND o.callback_time != '' THEN 1 ELSE 0 END) AS callbacks
                    FROM outcomes o
                    WHERE {outcome_where}""",
                    tuple(outcome_args),
                )
                missed_ptp_count = self._query_number(
                    conn,
                    f"""SELECT COUNT(*) AS n
                    FROM followups f
                    JOIN outcomes o ON o.session_id = f.session_id
                    WHERE {followup_where}
                      AND f.reminder_type = 'ptp_t_plus_1_miss'
                      AND f.status IN ('sent', 'missed')""",
                    tuple(followup_args),
                )
                open_ptp_alerts = self._query_number(
                    conn,
                    f"""SELECT COUNT(*) AS n
                    FROM alerts a
                    JOIN followups f ON f.idempotency_key = a.entity_id
                    JOIN outcomes o ON o.session_id = f.session_id
                    WHERE {followup_where}
                      AND a.type = 'PTP_MISS'
                      AND a.status != 'RESOLVED'""",
                    tuple(followup_args),
                )
                strategy_row = self._query_row(
                    conn,
                    f"""SELECT
                        COALESCE(o.strategy_mode, '') AS strategy_mode,
                        COALESCE(o.tone_profile, '') AS tone_profile,
                        COUNT(*) AS n
                    FROM outcomes o
                    WHERE {outcome_where}
                      AND COALESCE(o.strategy_mode, '') != ''
                    GROUP BY COALESCE(o.strategy_mode, ''), COALESCE(o.tone_profile, '')
                    ORDER BY n DESC
                    LIMIT 1""",
                    tuple(outcome_args),
                )
                default_strategy = self._default_strategy(bucket)
                strategy_mode = str(strategy_row["strategy_mode"] or default_strategy["strategy_mode"]) if strategy_row else default_strategy["strategy_mode"]
                tone_profile = str(strategy_row["tone_profile"] or default_strategy["tone_profile"]) if strategy_row else default_strategy["tone_profile"]
                outcomes_total = int((outcome_row["total"] if outcome_row else 0) or 0)
                ptp_count = int((outcome_row["ptp"] if outcome_row else 0) or 0)
                callbacks = int((outcome_row["callbacks"] if outcome_row else 0) or 0)
                ptp_rate_pct = round((ptp_count / max(1, outcomes_total)) * 100.0, 1) if outcomes_total else 0.0
                missed_ptp_rate_pct = round((missed_ptp_count / max(1, ptp_count)) * 100.0, 1) if ptp_count else 0.0
                roll_forward_pct = self._bucket_roll_forward_pct(roll=roll, bucket=bucket)
                containment_rate_pct = None if roll_forward_pct is None else round(100.0 - roll_forward_pct, 1)
                sample = int(max(exposure, outcomes_total))
                confidence = self._confidence(sample)
                score = (ptp_rate_pct * 0.55) + ((containment_rate_pct or 0.0) * 0.25) + ((100.0 - missed_ptp_rate_pct) * 0.20)
                risk_score = (roll_forward_pct or 0.0) * 0.45 + missed_ptp_rate_pct * 0.35 + ((sla_breaches / max(1, exposure)) * 100.0) * 0.20
                out.append(
                    {
                        "bucket": bucket,
                        "exposure": int(exposure),
                        "avg_amount_due": float(avg_amount_due or 0.0),
                        "outcomes_count": outcomes_total,
                        "active_ptp": int(active_ptp),
                        "ptp_count": ptp_count,
                        "callback_count": callbacks,
                        "ptp_rate_pct": ptp_rate_pct,
                        "sla_breaches": int(sla_breaches),
                        "missed_ptp_count": int(missed_ptp_count),
                        "missed_ptp_rate_pct": missed_ptp_rate_pct,
                        "open_ptp_alerts": int(open_ptp_alerts),
                        "roll_forward_pct": roll_forward_pct,
                        "containment_rate_pct": containment_rate_pct,
                        "current_strategy": strategy_mode,
                        "current_tone": tone_profile,
                        "sample_size": sample,
                        "confidence": confidence,
                        "score": round(score, 1),
                        "risk_score": round(risk_score, 1),
                    }
                )
        out.sort(key=lambda item: self._RISK_ORDER.get(str(item.get("bucket")), 99))
        return out

    def _agent_lens(self, *, campaign_id: Optional[str]) -> List[Dict[str, Any]]:
        rows = self.audit.agent_metrics(campaign_id=campaign_id)
        out: List[Dict[str, Any]] = []
        for row in rows:
            total_calls = int(row.get("total_calls") or 0)
            score = (
                float(row.get("ptp_conversion_pct") or 0.0) * 0.55
                + float(row.get("connect_rate_pct") or 0.0) * 0.30
                - min(20.0, float(row.get("compliance_violations") or 0.0) * 5.0)
                - min(12.0, float(row.get("escalations") or 0.0) * 1.5)
            )
            enriched = dict(row)
            enriched["score"] = round(score, 1)
            enriched["confidence"] = self._confidence(total_calls)
            out.append(enriched)
        out.sort(key=lambda item: (item.get("score") or 0.0), reverse=True)
        return out

    def _customer_lens(self, *, campaign_id: Optional[str]) -> List[Dict[str, Any]]:
        filters = ["1=1"]
        args: List[Any] = []
        if campaign_id:
            filters.append("campaign_id = ?")
            args.append(campaign_id)
        where_sql = " AND ".join(filters)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT
                    id,
                    campaign_id,
                    customer_id,
                    customer_name,
                    amount_due,
                    dpd,
                    ptp_date,
                    state,
                    owner,
                    sla_due_at,
                    disposition,
                    callback_at
                FROM tasks
                WHERE {where_sql}
                ORDER BY
                    CASE state
                        WHEN 'PTP' THEN 0
                        WHEN 'ESCALATED' THEN 1
                        WHEN 'CALLBACK' THEN 2
                        WHEN 'IN_PROGRESS' THEN 3
                        ELSE 4
                    END,
                    COALESCE(sla_due_at, 9999999999) ASC,
                    COALESCE(dpd, 0) DESC,
                    COALESCE(amount_due, 0) DESC
                LIMIT 12""",
                tuple(args),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            now = time.time()
            for row in rows:
                customer_id = str(row["customer_id"] or "")
                task_id = str(row["id"] or "")
                open_task_alerts = int(
                    self._query_number(
                        conn,
                        "SELECT COUNT(*) AS n FROM alerts WHERE entity_type = 'task' AND entity_id = ? AND status != 'RESOLVED'",
                        (task_id,),
                    )
                )
                open_ptp_alerts = int(
                    self._query_number(
                        conn,
                        """SELECT COUNT(*) AS n
                        FROM alerts a
                        JOIN followups f ON f.idempotency_key = a.entity_id
                        WHERE a.type = 'PTP_MISS'
                          AND a.status != 'RESOLVED'
                          AND f.customer_id = ?""",
                        (customer_id,),
                    )
                )
                latest = self._query_row(
                    conn,
                    """SELECT
                        COALESCE(disposition, '') AS disposition,
                        COALESCE(ptp_date, '') AS ptp_date,
                        COALESCE(callback_time, '') AS callback_time
                    FROM outcomes
                    WHERE customer_id = ?
                      AND (? IS NULL OR campaign_id = ?)
                    ORDER BY COALESCE(end_ts, start_ts, 0) DESC
                    LIMIT 1""",
                    (customer_id, campaign_id, campaign_id),
                )
                state = str(row["state"] or "NEW")
                dpd = int(row["dpd"] or 0)
                amount_due = float(row["amount_due"] or 0.0)
                sla_breach = bool(row["sla_due_at"] and float(row["sla_due_at"]) < now and state != "CLOSED")
                risk_score = (
                    min(35.0, dpd * 0.35)
                    + min(30.0, amount_due / 2500.0)
                    + (18.0 if sla_breach else 0.0)
                    + (14.0 if open_ptp_alerts else 0.0)
                    + (8.0 if open_task_alerts else 0.0)
                    + max(0.0, 12.0 - self._STATE_PRIORITY.get(state, 5) * 2.0)
                )
                out.append(
                    {
                        "task_id": task_id,
                        "campaign_id": str(row["campaign_id"] or ""),
                        "customer_id": customer_id,
                        "customer_name": str(row["customer_name"] or customer_id),
                        "amount_due": amount_due,
                        "dpd": dpd,
                        "state": state,
                        "owner": row["owner"],
                        "sla_breach": sla_breach,
                        "open_task_alerts": open_task_alerts,
                        "open_ptp_alerts": open_ptp_alerts,
                        "latest_disposition": str(latest["disposition"] or row["disposition"] or "") if latest else str(row["disposition"] or ""),
                        "latest_ptp_date": str(latest["ptp_date"] or row["ptp_date"] or "") if latest else str(row["ptp_date"] or ""),
                        "latest_callback_time": str(latest["callback_time"] or "") if latest else "",
                        "risk_score": round(risk_score, 1),
                        "confidence": self._confidence(max(1, dpd)),
                    }
                )
        out.sort(key=lambda item: (item.get("risk_score") or 0.0), reverse=True)
        return out

    def _recommendations(
        self,
        *,
        scope: Dict[str, Any],
        campaigns: Sequence[Dict[str, Any]],
        buckets: Sequence[Dict[str, Any]],
        agents: Sequence[Dict[str, Any]],
        customers: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        recs: List[Dict[str, Any]] = []
        best_bucket = self._best_bucket(buckets)
        risk_bucket = self._risk_bucket(buckets)
        if risk_bucket and int(risk_bucket.get("sample_size") or 0) > 0:
            current_strategy = str(risk_bucket.get("current_strategy") or "current_strategy")
            proposed_strategy = self._proposed_bucket_strategy(str(risk_bucket.get("bucket") or ""))
            impact = self._bucket_impact(risk_bucket=risk_bucket, best_bucket=best_bucket)
            recs.append(
                {
                    "id": f"rec-bucket-{risk_bucket['bucket']}",
                    "kind": "bucket_strategy",
                    "title": f"Change the play for {risk_bucket['bucket']} DPD",
                    "summary": (
                        f"{risk_bucket['bucket']} is carrying {int(risk_bucket.get('exposure') or 0)} accounts with "
                        f"{self._percent(risk_bucket.get('ptp_rate_pct'))} PTP conversion and "
                        f"{self._percent(risk_bucket.get('missed_ptp_rate_pct'))} missed-PTP pressure."
                    ),
                    "rationale": (
                        f"The current operating mode is {current_strategy}. The control layer recommends testing "
                        f"{proposed_strategy} on resistant accounts to improve containment before the bucket rolls forward."
                    ),
                    "confidence": impact["confidence"],
                    "expected_impact": impact,
                    "actions": [
                        {
                            "id": f"act-exp-{risk_bucket['bucket']}",
                            "action_type": "launch_experiment",
                            "cta_label": "Launch experiment",
                            "approval_mode": "direct_if_permitted",
                            "title": f"Test {current_strategy} vs {proposed_strategy}",
                            "summary": f"Create a governed experiment for {risk_bucket['bucket']} DPD accounts.",
                            "payload": {
                                "name": f"{scope['campaign_name'] or 'Ops'} {risk_bucket['bucket']} strategy test",
                                "objective": f"Improve kept commitments and containment in {risk_bucket['bucket']} DPD",
                                "control": current_strategy,
                                "treatment": proposed_strategy,
                                "split_ratio": 0.5,
                                "metadata": {
                                    "campaign_id": scope.get("campaign_id"),
                                    "bucket": risk_bucket.get("bucket"),
                                    "generated_by": "ops_control_layer",
                                    "basis": impact["basis"],
                                },
                            },
                        },
                        {
                            "id": f"act-strategy-{risk_bucket['bucket']}",
                            "action_type": "request_strategy_change",
                            "cta_label": "Submit strategy change",
                            "approval_mode": "approval_required",
                            "title": f"Submit a {risk_bucket['bucket']} strategy update",
                            "summary": "Queue a governed strategy change request with evidence and expected impact.",
                            "payload": {
                                "campaign_id": scope.get("campaign_id"),
                                "bucket": risk_bucket.get("bucket"),
                                "current_strategy": current_strategy,
                                "proposed_strategy": proposed_strategy,
                                "rationale": (
                                    f"{risk_bucket['bucket']} DPD is under the benchmark bucket on conversion and containment."
                                ),
                                "expected_impact": impact,
                            },
                        },
                    ],
                }
            )

        if len(agents) >= 2:
            best_agent = agents[0]
            lagging_agent = agents[-1]
            score_gap = float(best_agent.get("score") or 0.0) - float(lagging_agent.get("score") or 0.0)
            if score_gap >= 8.0:
                impact = self._agent_impact(best_agent=best_agent, lagging_agent=lagging_agent)
                recs.append(
                    {
                        "id": f"rec-agent-{lagging_agent.get('agent_id')}",
                        "kind": "agent_rebalance",
                        "title": f"Rebalance complex work toward {best_agent.get('display_name')}",
                        "summary": (
                            f"{best_agent.get('display_name')} is converting at {self._percent(best_agent.get('ptp_conversion_pct'))}, "
                            f"while {lagging_agent.get('display_name')} is at {self._percent(lagging_agent.get('ptp_conversion_pct'))}."
                        ),
                        "rationale": (
                            "The gap is large enough to justify a governed routing or coaching change instead of waiting for more missed PTPs."
                        ),
                        "confidence": impact["confidence"],
                        "expected_impact": impact,
                        "actions": [
                            {
                                "id": f"act-agent-{lagging_agent.get('agent_id')}",
                                "action_type": "request_agent_rebalance",
                                "cta_label": "Submit rebalance request",
                                "approval_mode": "approval_required",
                                "title": "Move tougher accounts to the strongest lane",
                                "summary": "Queue a governed routing or coaching change for approval.",
                                "payload": {
                                    "campaign_id": scope.get("campaign_id"),
                                    "source_agent_id": lagging_agent.get("agent_id"),
                                    "source_agent_name": lagging_agent.get("display_name"),
                                    "target_agent_id": best_agent.get("agent_id"),
                                    "target_agent_name": best_agent.get("display_name"),
                                    "reason": "Performance gap by conversion and compliance-adjusted score",
                                    "expected_impact": impact,
                                },
                            }
                        ],
                    }
                )

        if len(campaigns) >= 2:
            best_campaign = campaigns[0]
            weakest_campaign = campaigns[-1]
            score_gap = float(best_campaign.get("score") or 0.0) - float(weakest_campaign.get("score") or 0.0)
            if score_gap >= 7.0:
                impact = self._campaign_impact(best_campaign=best_campaign, weakest_campaign=weakest_campaign)
                recs.append(
                    {
                        "id": f"rec-campaign-{weakest_campaign.get('campaign_id')}",
                        "kind": "campaign_operating_gap",
                        "title": f"Replicate the operating rhythm from {best_campaign.get('name')}",
                        "summary": (
                            f"{weakest_campaign.get('name')} is lagging on contact coverage and follow-up discipline "
                            f"versus {best_campaign.get('name')}."
                        ),
                        "rationale": "This is a process gap more than a volume gap, so a disciplined lane change should be tested.",
                        "confidence": impact["confidence"],
                        "expected_impact": impact,
                        "actions": [],
                    }
                )

        return recs[:3]

    def _summary_cards(
        self,
        *,
        scope: Dict[str, Any],
        campaigns: Sequence[Dict[str, Any]],
        buckets: Sequence[Dict[str, Any]],
        agents: Sequence[Dict[str, Any]],
        customers: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        cards: List[Dict[str, str]] = []
        if scope.get("campaign_selected"):
            selected = next((row for row in campaigns if row.get("campaign_id") == scope.get("campaign_id")), None)
            if selected:
                cards.append(
                    {
                        "label": "Campaign In Scope",
                        "value": str(selected.get("name") or scope.get("campaign_id")),
                        "detail": (
                            f"{selected.get('total_accounts')} accounts, {self._percent(selected.get('followup_discipline_rate_pct'))} follow-up discipline"
                        ),
                    }
                )
        elif campaigns:
            leader = campaigns[0]
            cards.append(
                {
                    "label": "Best Campaign",
                    "value": str(leader.get("name") or leader.get("campaign_id")),
                    "detail": f"Score {leader.get('score')}, containment {self._percent(leader.get('containment_rate_pct'))}",
                }
            )
        best_bucket = self._best_bucket(buckets)
        if best_bucket:
            cards.append(
                {
                    "label": "Best Bucket",
                    "value": str(best_bucket.get("bucket")),
                    "detail": (
                        f"{self._percent(best_bucket.get('ptp_rate_pct'))} PTP conversion across {best_bucket.get('sample_size')} observed accounts"
                    ),
                }
            )
        risk_bucket = self._risk_bucket(buckets)
        if risk_bucket:
            cards.append(
                {
                    "label": "Biggest Containment Gap",
                    "value": str(risk_bucket.get("bucket")),
                    "detail": (
                        f"{self._percent(risk_bucket.get('roll_forward_pct'))} roll-forward risk and "
                        f"{self._percent(risk_bucket.get('missed_ptp_rate_pct'))} missed-PTP pressure"
                    ),
                }
            )
        if agents:
            cards.append(
                {
                    "label": "Top Agent",
                    "value": str(agents[0].get("display_name") or agents[0].get("agent_id")),
                    "detail": f"{self._percent(agents[0].get('ptp_conversion_pct'))} PTP conversion on {agents[0].get('total_calls')} calls",
                }
            )
        elif customers:
            cards.append(
                {
                    "label": "Hottest Account",
                    "value": str(customers[0].get("customer_name") or customers[0].get("customer_id")),
                    "detail": f"DPD {customers[0].get('dpd')}, risk score {customers[0].get('risk_score')}",
                }
            )
        return cards[:4]

    def _evidence_cards(
        self,
        *,
        focus: Set[str],
        scope: Dict[str, Any],
        campaigns: Sequence[Dict[str, Any]],
        buckets: Sequence[Dict[str, Any]],
        agents: Sequence[Dict[str, Any]],
        customers: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        cards: List[Dict[str, Any]] = []
        selected_campaign = next((row for row in campaigns if row.get("campaign_id") == scope.get("campaign_id")), None)
        if selected_campaign:
            cards.append(
                {
                    "title": f"{selected_campaign.get('name')} campaign view",
                    "entity_type": "campaign",
                    "entity_id": selected_campaign.get("campaign_id"),
                    "summary": "This is the current operating baseline for the selected campaign.",
                    "sample_size": int(selected_campaign.get("total_accounts") or 0),
                    "confidence": selected_campaign.get("confidence"),
                    "metrics": [
                        {"label": "Contact rate", "value": self._percent(selected_campaign.get("contact_rate_pct"))},
                        {"label": "Follow-up discipline", "value": self._percent(selected_campaign.get("followup_discipline_rate_pct"))},
                        {"label": "Containment", "value": self._percent(selected_campaign.get("containment_rate_pct"))},
                        {"label": "Recovery", "value": self._percent(selected_campaign.get("recovery_rate_pct"))},
                    ],
                }
            )
        elif campaigns and ("campaign" in focus or not focus):
            leader = campaigns[0]
            cards.append(
                {
                    "title": f"{leader.get('name')} is the campaign leader",
                    "entity_type": "campaign",
                    "entity_id": leader.get("campaign_id"),
                    "summary": "Best overall operating score across contact coverage, discipline, recovery, and containment.",
                    "sample_size": int(leader.get("total_accounts") or 0),
                    "confidence": leader.get("confidence"),
                    "metrics": [
                        {"label": "Contact rate", "value": self._percent(leader.get("contact_rate_pct"))},
                        {"label": "Follow-up discipline", "value": self._percent(leader.get("followup_discipline_rate_pct"))},
                        {"label": "Containment", "value": self._percent(leader.get("containment_rate_pct"))},
                        {"label": "Expected recovery", "value": self._currency(leader.get("expected_recovery_amount"))},
                    ],
                }
            )

        best_bucket = self._best_bucket(buckets)
        if best_bucket:
            cards.append(
                {
                    "title": f"{best_bucket.get('bucket')} is the strongest bucket",
                    "entity_type": "bucket",
                    "entity_id": best_bucket.get("bucket"),
                    "summary": f"Current strategy: {best_bucket.get('current_strategy')} with tone {best_bucket.get('current_tone')}.",
                    "sample_size": int(best_bucket.get("sample_size") or 0),
                    "confidence": best_bucket.get("confidence"),
                    "metrics": [
                        {"label": "PTP conversion", "value": self._percent(best_bucket.get("ptp_rate_pct"))},
                        {"label": "Missed PTP rate", "value": self._percent(best_bucket.get("missed_ptp_rate_pct"))},
                        {"label": "Containment", "value": self._percent(best_bucket.get("containment_rate_pct"))},
                        {"label": "Exposure", "value": str(int(best_bucket.get("exposure") or 0))},
                    ],
                }
            )

        risk_bucket = self._risk_bucket(buckets)
        if risk_bucket:
            cards.append(
                {
                    "title": f"{risk_bucket.get('bucket')} needs intervention",
                    "entity_type": "bucket",
                    "entity_id": risk_bucket.get("bucket"),
                    "summary": "This is the weakest point in the current containment system.",
                    "sample_size": int(risk_bucket.get("sample_size") or 0),
                    "confidence": risk_bucket.get("confidence"),
                    "metrics": [
                        {"label": "Current strategy", "value": str(risk_bucket.get("current_strategy") or "-")},
                        {"label": "Roll-forward risk", "value": self._percent(risk_bucket.get("roll_forward_pct"))},
                        {"label": "Missed PTP rate", "value": self._percent(risk_bucket.get("missed_ptp_rate_pct"))},
                        {"label": "SLA breaches", "value": str(int(risk_bucket.get("sla_breaches") or 0))},
                    ],
                }
            )

        if agents and ("agent" in focus or "briefing" in focus or not focus):
            top_agent = agents[0]
            cards.append(
                {
                    "title": f"{top_agent.get('display_name')} is the strongest operator",
                    "entity_type": "agent",
                    "entity_id": top_agent.get("agent_id"),
                    "summary": "Agent ranking is adjusted for compliance and escalation drag, not just raw volume.",
                    "sample_size": int(top_agent.get("total_calls") or 0),
                    "confidence": top_agent.get("confidence"),
                    "metrics": [
                        {"label": "Connect rate", "value": self._percent(top_agent.get("connect_rate_pct"))},
                        {"label": "PTP conversion", "value": self._percent(top_agent.get("ptp_conversion_pct"))},
                        {"label": "Escalations", "value": str(int(top_agent.get("escalations") or 0))},
                        {"label": "Compliance violations", "value": str(int(top_agent.get("compliance_violations") or 0))},
                    ],
                }
            )
        if customers and ("customer" in focus or "briefing" in focus):
            customer = customers[0]
            cards.append(
                {
                    "title": f"{customer.get('customer_name')} is the hottest account",
                    "entity_type": "customer",
                    "entity_id": customer.get("customer_id"),
                    "summary": "Use this to discuss why the control layer also works at the account level.",
                    "sample_size": 1,
                    "confidence": customer.get("confidence"),
                    "metrics": [
                        {"label": "DPD", "value": str(customer.get("dpd") or 0)},
                        {"label": "Amount due", "value": self._currency(customer.get("amount_due"))},
                        {"label": "State", "value": str(customer.get("state") or "-")},
                        {"label": "Open PTP alerts", "value": str(int(customer.get("open_ptp_alerts") or 0))},
                    ],
                }
            )
        return cards[:5]

    def _answer(
        self,
        *,
        focus: Set[str],
        scope: Dict[str, Any],
        campaigns: Sequence[Dict[str, Any]],
        buckets: Sequence[Dict[str, Any]],
        agents: Sequence[Dict[str, Any]],
        customers: Sequence[Dict[str, Any]],
        recommendations: Sequence[Dict[str, Any]],
    ) -> str:
        if not campaigns and not buckets and not agents and not customers:
            return "No live operational data is available yet. Upload a campaign, capture at least one commitment, and the control layer will start generating evidence-backed guidance."

        parts: List[str] = []
        if scope.get("campaign_selected"):
            parts.append(f"Scope is {scope.get('scope_label')}.")
        elif campaigns:
            parts.append(f"Top campaign right now is {campaigns[0].get('name')} based on contact coverage, follow-up discipline, and containment.")

        risk_bucket = self._risk_bucket(buckets)
        best_bucket = self._best_bucket(buckets)
        if risk_bucket and best_bucket:
            parts.append(
                f"The strongest bucket is {best_bucket.get('bucket')} at {self._percent(best_bucket.get('ptp_rate_pct'))} PTP conversion, while {risk_bucket.get('bucket')} is the main leak with {self._percent(risk_bucket.get('roll_forward_pct'))} roll-forward risk."
            )
            parts.append(
                f"{risk_bucket.get('bucket')} is currently running {risk_bucket.get('current_strategy')}, and it should be the first place to test a strategy adjustment."
            )

        if agents and ("agent" in focus or "briefing" in focus or "recommend" in focus or not focus):
            parts.append(
                f"At the agent layer, {agents[0].get('display_name')} is the benchmark at {self._percent(agents[0].get('ptp_conversion_pct'))} PTP conversion."
            )

        if customers and ("customer" in focus or "briefing" in focus):
            parts.append(
                f"At the account level, {customers[0].get('customer_name')} is the highest-priority customer because of DPD, amount due, and open alert pressure."
            )

        if recommendations:
            top_rec = recommendations[0]
            impact = top_rec.get("expected_impact") if isinstance(top_rec.get("expected_impact"), dict) else {}
            if impact:
                parts.append(
                    f"The highest-value move is {top_rec.get('title').lower()}, with an estimated uplift of {impact.get('summary')}."
                )
        return " ".join(part for part in parts if part)

    @staticmethod
    def _detect_focus(message: str) -> Set[str]:
        lower = message.lower()
        if not lower:
            return {"briefing", "campaign", "bucket", "agent", "recommend", "simulate"}
        focus: Set[str] = set()
        if any(token in lower for token in ("campaign", "portfolio")):
            focus.add("campaign")
        if any(token in lower for token in ("bucket", "dpd", "1-30", "31-60", "61-90", "90+")):
            focus.add("bucket")
        if any(token in lower for token in ("agent", "collector", "team")):
            focus.add("agent")
        if any(token in lower for token in ("customer", "account", "borrower", "lead")):
            focus.add("customer")
        if any(token in lower for token in ("strategy", "script", "playbook", "approach")):
            focus.add("strategy")
        if any(token in lower for token in ("why", "underperform", "root cause", "diagnose")):
            focus.add("diagnose")
        if any(token in lower for token in ("change", "recommend", "should", "improve", "working", "best")):
            focus.add("recommend")
        if any(token in lower for token in ("simulate", "what if", "impact", "uplift", "if we")):
            focus.add("simulate")
        if any(token in lower for token in ("launch", "apply", "run", "start", "approve", "submit")):
            focus.add("execute")
        if not focus:
            focus.add("briefing")
        return focus

    def _quick_replies(self, *, campaign_selected: bool) -> List[str]:
        scope_text = "in this campaign" if campaign_selected else "across campaigns"
        return [
            f"What is working by bucket {scope_text}?",
            f"Which agent is outperforming after bucket mix {scope_text}?",
            f"What should I change this week {scope_text}?",
            f"Simulate the impact of a strategy change in 31-60 DPD {scope_text}.",
        ]

    @staticmethod
    def _campaign_score(*, contact_rate: float, discipline: float, recovery: float, containment: Optional[float]) -> float:
        return round((contact_rate * 0.25) + (discipline * 0.35) + (recovery * 0.15) + ((containment or 0.0) * 0.25), 1)

    @staticmethod
    def _confidence(sample_size: int) -> str:
        if sample_size >= 30:
            return "high"
        if sample_size >= 10:
            return "medium"
        return "low"

    def _default_strategy(self, bucket: str) -> Dict[str, str]:
        representative_dpd = {"1-30": 15, "31-60": 45, "61-90": 75, "90+": 110}.get(bucket, 15)
        decision = self.strategy_engine.classify(representative_dpd)
        return {"strategy_mode": decision.strategy_mode, "tone_profile": decision.tone_profile}

    @classmethod
    def _bucket_roll_forward_pct(cls, *, roll: Dict[str, Any], bucket: str) -> Optional[float]:
        matrix = roll.get("matrix") if isinstance(roll.get("matrix"), dict) else {}
        current = matrix.get(bucket) if isinstance(matrix.get(bucket), dict) else {}
        if not current:
            return None
        total = sum(float(v or 0.0) for v in current.values())
        if total <= 0:
            return None
        source_rank = cls._RISK_ORDER.get(bucket, 0)
        forward = 0.0
        for target, value in current.items():
            if cls._RISK_ORDER.get(str(target), 0) > source_rank:
                forward += float(value or 0.0)
        return round((forward / total) * 100.0, 1)

    def _best_bucket(self, buckets: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        ranked = [row for row in buckets if int(row.get("sample_size") or 0) > 0]
        if not ranked:
            return None
        return max(ranked, key=lambda row: (float(row.get("score") or 0.0), int(row.get("sample_size") or 0)))

    def _risk_bucket(self, buckets: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        ranked = [row for row in buckets if int(row.get("sample_size") or 0) > 0]
        if not ranked:
            return None
        return max(ranked, key=lambda row: (float(row.get("risk_score") or 0.0), int(row.get("sample_size") or 0)))

    def _proposed_bucket_strategy(self, bucket: str) -> str:
        mapping = {
            "1-30": "soft_reminder_callback_first",
            "31-60": "callback_salvage",
            "61-90": "high_urgency_supervisor_lane",
            "90+": "pre_legal_supervisor_lane",
        }
        return mapping.get(bucket, "callback_salvage")

    def _bucket_impact(self, *, risk_bucket: Dict[str, Any], best_bucket: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        current_rate = float(risk_bucket.get("ptp_rate_pct") or 0.0)
        benchmark = float(best_bucket.get("ptp_rate_pct") or 0.0) if best_bucket else current_rate + 8.0
        gap = max(4.0, benchmark - current_rate)
        uplift_low = round(min(12.0, max(2.5, gap * 0.35)), 1)
        uplift_high = round(min(18.0, max(uplift_low + 1.5, gap * 0.65)), 1)
        exposure = int(risk_bucket.get("exposure") or risk_bucket.get("sample_size") or 0)
        avg_due = float(risk_bucket.get("avg_amount_due") or 0.0)
        add_low = round((exposure * uplift_low) / 100.0, 1)
        add_high = round((exposure * uplift_high) / 100.0, 1)
        recovery_low = round(add_low * avg_due * 0.45, 0)
        recovery_high = round(add_high * avg_due * 0.45, 0)
        confidence = risk_bucket.get("confidence") or "medium"
        return {
            "summary": f"+{uplift_low:.1f} to +{uplift_high:.1f} pts PTP conversion",
            "confidence": confidence,
            "basis": (
                "Inference from current conversion gap, exposure, and containment pressure. "
                "This is a directional estimate, not an attributed forecast."
            ),
            "uplift_low_pct": uplift_low,
            "uplift_high_pct": uplift_high,
            "additional_commitments_low": add_low,
            "additional_commitments_high": add_high,
            "recovery_low": recovery_low,
            "recovery_high": recovery_high,
        }

    def _agent_impact(self, *, best_agent: Dict[str, Any], lagging_agent: Dict[str, Any]) -> Dict[str, Any]:
        gap = max(4.0, float(best_agent.get("ptp_conversion_pct") or 0.0) - float(lagging_agent.get("ptp_conversion_pct") or 0.0))
        uplift_low = round(min(10.0, max(2.0, gap * 0.30)), 1)
        uplift_high = round(min(14.0, max(uplift_low + 1.0, gap * 0.50)), 1)
        total_calls = int(lagging_agent.get("total_calls") or 0)
        add_low = round((total_calls * uplift_low) / 100.0, 1)
        add_high = round((total_calls * uplift_high) / 100.0, 1)
        return {
            "summary": f"+{uplift_low:.1f} to +{uplift_high:.1f} pts PTP conversion on the lagging lane",
            "confidence": self._confidence(total_calls),
            "basis": "Inference from the current spread between the best and weakest agent after compliance and escalation drag.",
            "uplift_low_pct": uplift_low,
            "uplift_high_pct": uplift_high,
            "additional_commitments_low": add_low,
            "additional_commitments_high": add_high,
        }

    def _campaign_impact(self, *, best_campaign: Dict[str, Any], weakest_campaign: Dict[str, Any]) -> Dict[str, Any]:
        discipline_gap = max(
            3.0,
            float(best_campaign.get("followup_discipline_rate_pct") or 0.0) - float(weakest_campaign.get("followup_discipline_rate_pct") or 0.0),
        )
        uplift_low = round(min(9.0, max(2.0, discipline_gap * 0.25)), 1)
        uplift_high = round(min(13.0, max(uplift_low + 1.0, discipline_gap * 0.45)), 1)
        sample = int(weakest_campaign.get("total_accounts") or 0)
        return {
            "summary": f"+{uplift_low:.1f} to +{uplift_high:.1f} pts follow-up discipline",
            "confidence": self._confidence(sample),
            "basis": "Inference from the current operating gap between the strongest and weakest campaign.",
            "uplift_low_pct": uplift_low,
            "uplift_high_pct": uplift_high,
        }

    @staticmethod
    def _query_row(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        try:
            return conn.execute(sql, args).fetchone()
        except Exception:
            return None

    @staticmethod
    def _query_number(
        conn: sqlite3.Connection,
        sql: str,
        args: tuple[Any, ...],
        *,
        key: str = "n",
    ) -> float:
        row = OpsControlService._query_row(conn, sql, args)
        if not row:
            return 0.0
        try:
            value = row[key]
        except Exception:
            value = row[0]
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _bucket_task_filter(*, bucket: str, campaign_id: Optional[str]) -> Tuple[str, List[Any]]:
        filters = ["1=1"]
        args: List[Any] = []
        if campaign_id:
            filters.append("t.campaign_id = ?")
            args.append(campaign_id)
        if bucket == "1-30":
            filters.append("t.dpd BETWEEN 1 AND 30")
        elif bucket == "31-60":
            filters.append("t.dpd BETWEEN 31 AND 60")
        elif bucket == "61-90":
            filters.append("t.dpd BETWEEN 61 AND 90")
        else:
            filters.append("t.dpd > 90")
        return " AND ".join(filters), args

    @staticmethod
    def _bucket_outcome_filter(*, bucket: str, campaign_id: Optional[str]) -> Tuple[str, List[Any]]:
        filters = ["o.dpd_bucket = ?"]
        args: List[Any] = [bucket]
        if campaign_id:
            filters.append("o.campaign_id = ?")
            args.append(campaign_id)
        return " AND ".join(filters), args

    @staticmethod
    def _bucket_followup_filter(*, bucket: str, campaign_id: Optional[str]) -> Tuple[str, List[Any]]:
        filters = ["o.dpd_bucket = ?"]
        args: List[Any] = [bucket]
        if campaign_id:
            filters.append("o.campaign_id = ?")
            args.append(campaign_id)
        return " AND ".join(filters), args

    @staticmethod
    def _percent(value: Optional[Any]) -> str:
        try:
            return f"{float(value or 0.0):.1f}%"
        except Exception:
            return "0.0%"

    @staticmethod
    def _currency(value: Optional[Any]) -> str:
        try:
            number = float(value or 0.0)
        except Exception:
            number = 0.0
        try:
            import locale

            locale.setlocale(locale.LC_ALL, "en_IN.UTF-8")
            return locale.currency(number, grouping=True)
        except Exception:
            return f"INR {number:,.0f}"
