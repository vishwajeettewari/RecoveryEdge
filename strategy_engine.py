from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StrategyDecision:
    dpd_bucket: str
    strategy_mode: str
    tone_profile: str
    instruction: str


class StrategyEngine:
    """Deterministic DPD-to-tone strategy mapper for portfolio demos."""

    def classify(self, dpd: Optional[object]) -> StrategyDecision:
        value = self._to_int(dpd)
        if value <= 0:
            return StrategyDecision(
                dpd_bucket="0",
                strategy_mode="baseline",
                tone_profile="neutral",
                instruction="Use a neutral reminder tone and verify account context before asking for commitment.",
            )
        if value <= 30:
            return StrategyDecision(
                dpd_bucket="1-30",
                strategy_mode="soft_reminder",
                tone_profile="empathetic",
                instruction="Use a soft reminder tone. Prioritize cooperative language and ask for a feasible payment date.",
            )
        if value <= 60:
            return StrategyDecision(
                dpd_bucket="31-60",
                strategy_mode="firm_commitment",
                tone_profile="firm_respectful",
                instruction="Use a firm but respectful tone. Ask directly for commitment date or callback slot.",
            )
        if value <= 90:
            return StrategyDecision(
                dpd_bucket="61-90",
                strategy_mode="high_urgency",
                tone_profile="urgent_controlled",
                instruction="Use high urgency language without threats. If no commitment after retries, trigger supervisor follow-up.",
            )
        return StrategyDecision(
            dpd_bucket="90+",
            strategy_mode="pre_legal_caution",
            tone_profile="strict_compliant",
            instruction="Use pre-legal caution language compliant with RBI/TRAI. Avoid intimidation and offer escalation path.",
        )

    @staticmethod
    def _to_int(dpd: Optional[object]) -> int:
        if dpd is None:
            return 0
        if isinstance(dpd, bool):
            return 0
        if isinstance(dpd, (int, float)):
            return int(dpd)
        txt = str(dpd).strip()
        if not txt:
            return 0
        try:
            return int(float(txt))
        except Exception:
            return 0
