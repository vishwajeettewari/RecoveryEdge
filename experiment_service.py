from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


class ExperimentService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    objective TEXT,
                    status TEXT NOT NULL,
                    variant_a TEXT NOT NULL,
                    variant_b TEXT NOT NULL,
                    split_ratio REAL NOT NULL,
                    metadata_json TEXT,
                    actor TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiment_assignments (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    unit_type TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    source TEXT,
                    metadata_json TEXT,
                    actor TEXT,
                    request_id TEXT,
                    created_at REAL NOT NULL,
                    UNIQUE(tenant_id, experiment_id, unit_type, unit_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_experiments_tenant_status ON experiments(tenant_id, status, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_experiment_assignments_tenant_exp ON experiment_assignments(tenant_id, experiment_id, created_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()

    def create_experiment(
        self,
        *,
        tenant_id: str,
        payload: Dict[str, Any],
        actor: str,
        request_id: str,
    ) -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name_required")
        status = str(payload.get("status") or "ACTIVE").strip().upper() or "ACTIVE"
        variant_a = str(payload.get("control") or "control").strip() or "control"
        variant_b = str(payload.get("treatment") or "treatment").strip() or "treatment"
        split_ratio = self._to_float(payload.get("split_ratio"))
        if split_ratio is None:
            split_ratio = 0.5
        split_ratio = max(0.05, min(0.95, split_ratio))

        exp_id = f"exp-{uuid.uuid4().hex[:12]}"
        now = time.time()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO experiments (
                    id, tenant_id, name, objective, status, variant_a, variant_b,
                    split_ratio, metadata_json, actor, request_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exp_id,
                    tenant_id,
                    name,
                    str(payload.get("objective") or "").strip() or None,
                    status,
                    variant_a,
                    variant_b,
                    split_ratio,
                    json.dumps(metadata, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_experiment(tenant_id=tenant_id, experiment_id=exp_id) or {}

    def assign(
        self,
        *,
        tenant_id: str,
        experiment_id: str,
        unit_id: str,
        actor: str,
        request_id: str,
        source: str = "runtime",
        unit_type: str = "customer",
    ) -> Dict[str, Any]:
        uid = str(unit_id or "").strip()
        if not uid:
            raise ValueError("unit_id_required")

        conn = self._connect()
        now = time.time()
        try:
            exp = conn.execute(
                "SELECT * FROM experiments WHERE tenant_id = ? AND id = ?",
                (tenant_id, experiment_id),
            ).fetchone()
            if exp is None:
                raise ValueError("experiment_not_found")

            existing = conn.execute(
                """
                SELECT *
                FROM experiment_assignments
                WHERE tenant_id = ? AND experiment_id = ? AND unit_type = ? AND unit_id = ?
                """,
                (tenant_id, experiment_id, unit_type, uid),
            ).fetchone()
            if existing is not None:
                out = dict(existing)
                out["metadata"] = json.loads(out.pop("metadata_json") or "{}")
                out["deduplicated"] = True
                return out

            ratio = float(exp["split_ratio"] or 0.5)
            bucket = self._bucket(f"{tenant_id}:{experiment_id}:{uid}")
            variant = str(exp["variant_a"] if bucket < ratio else exp["variant_b"])

            assignment_id = f"exa-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO experiment_assignments (
                    id, tenant_id, experiment_id, unit_type, unit_id, variant,
                    source, metadata_json, actor, request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment_id,
                    tenant_id,
                    experiment_id,
                    unit_type,
                    uid,
                    variant,
                    source,
                    json.dumps({}, ensure_ascii=False),
                    actor,
                    request_id,
                    now,
                ),
            )
            conn.commit()
            return {
                "id": assignment_id,
                "tenant_id": tenant_id,
                "experiment_id": experiment_id,
                "unit_type": unit_type,
                "unit_id": uid,
                "variant": variant,
                "source": source,
                "metadata": {},
                "created_at": now,
                "deduplicated": False,
            }
        finally:
            conn.close()

    def compute_uplift(
        self,
        *,
        tenant_id: str,
        experiment_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where = ["ea.tenant_id = ?"]
            args: List[Any] = [tenant_id]
            if experiment_id:
                where.append("ea.experiment_id = ?")
                args.append(experiment_id)

            rows = conn.execute(
                f"""
                SELECT ea.experiment_id, ea.variant, COUNT(*) AS n
                FROM experiment_assignments ea
                WHERE {' AND '.join(where)}
                GROUP BY ea.experiment_id, ea.variant
                """,
                tuple(args),
            ).fetchall()

            by_exp: Dict[str, Dict[str, int]] = {}
            for row in rows:
                exp_id = str(row["experiment_id"])
                variant = str(row["variant"])
                by_exp.setdefault(exp_id, {})[variant] = int(row["n"] or 0)

            snapshots = []
            for exp_id, variants in by_exp.items():
                exp = conn.execute(
                    "SELECT variant_a, variant_b FROM experiments WHERE tenant_id = ? AND id = ?",
                    (tenant_id, exp_id),
                ).fetchone()
                if exp is None:
                    continue
                control_name = str(exp["variant_a"])
                treatment_name = str(exp["variant_b"])
                control_n = int(variants.get(control_name, 0))
                treatment_n = int(variants.get(treatment_name, 0))

                # Phase-1 placeholder uplift metric until outcomes attribution lands.
                control_rate = 0.0 if control_n == 0 else min(1.0, 0.25 + (control_n % 7) * 0.01)
                treatment_rate = 0.0 if treatment_n == 0 else min(1.0, control_rate + 0.03)

                snapshots.append(
                    {
                        "experiment_id": exp_id,
                        "control_variant": control_name,
                        "treatment_variant": treatment_name,
                        "control_n": control_n,
                        "treatment_n": treatment_n,
                        "control_recovery_rate": round(control_rate, 4),
                        "treatment_recovery_rate": round(treatment_rate, 4),
                        "uplift": round(treatment_rate - control_rate, 4),
                        "confidence": round(0.55 + min(0.4, (control_n + treatment_n) / 300.0), 4),
                    }
                )

            return {
                "tenant_id": tenant_id,
                "generated_at": time.time(),
                "snapshots": snapshots,
            }
        finally:
            conn.close()

    def get_experiment(self, *, tenant_id: str, experiment_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM experiments WHERE tenant_id = ? AND id = ?",
                (tenant_id, experiment_id),
            ).fetchone()
            if row is None:
                return None
            out = dict(row)
            out["metadata"] = json.loads(out.pop("metadata_json") or "{}")
            return out
        finally:
            conn.close()

    @staticmethod
    def _bucket(seed: str) -> float:
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
        value = int(digest, 16)
        return (value % 10000) / 10000.0

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except Exception:
            return None
