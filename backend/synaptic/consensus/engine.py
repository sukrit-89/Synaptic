from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from synaptic.signals.base import SignalResult

logger = logging.getLogger(__name__)


class ResponseTier(Enum):
    """Response tiers mapped to signal counts per PRD."""

    LOG_ONLY = 0       # 0 signals — log only
    ALERT_INTERNAL = 1  # 1 signal — internal alert (Synaptic ops)
    ALERT_GOVERNANCE = 2  # 2 signals — alert governance + LLM explanation
    RATE_LIMIT = 3      # 3 signals — rate-limit withdrawals (soft)
    GUARDIAN_PAUSE = 4   # 4 signals — full guardian pause + counter-tx


@dataclass(frozen=True, slots=True)
class ConsensusDecision:
    """A consensus decision made by the engine."""

    tx_hash: str
    tier: ResponseTier
    active_signals: int
    total_signals: int
    fired_signals: list[SignalResult]
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def action_label(self) -> str:
        labels = {
            ResponseTier.LOG_ONLY: "log_only",
            ResponseTier.ALERT_INTERNAL: "alert_internal",
            ResponseTier.ALERT_GOVERNANCE: "alert_governance",
            ResponseTier.RATE_LIMIT: "rate_limit",
            ResponseTier.GUARDIAN_PAUSE: "guardian_pause",
        }
        return labels[self.tier]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tx_hash": self.tx_hash,
            "tier": self.tier.value,
            "action": self.action_label,
            "active_signals": self.active_signals,
            "total_signals": self.total_signals,
            "fired_signals": [s.label for s in self.fired_signals],
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class ConsensusEngine:
    """Maps signal results to response tiers per the PRD signal→action table.

    Signal Count → Response:
        0 → Log only
        1 → Internal alert (Synaptic ops)
        2 → Alert governance multisig + LLM explanation
        3 → Rate-limit withdrawals (soft, playbook-permitted)
        4 → Guardian pause + counter-tx + incident report

    Phase 1: Logs decisions only. No autonomous on-chain action.
    Phase 2+: Connects to playbook contracts for autonomous action.
    """

    def __init__(self, total_signals: int = 2) -> None:
        """Phase 1 only has 2 signals (heuristics + simulation)."""
        self._total_signals = total_signals
        self._decisions: list[ConsensusDecision] = []

    async def decide(
        self, tx_hash: str, signal_results: list[SignalResult]
    ) -> ConsensusDecision:
        """Aggregate signal results into a consensus decision."""
        fired = [s for s in signal_results if s.fired]
        active_count = len(fired)
        total = len(signal_results)

        # Map to response tier
        tier = self._map_tier(active_count)

        decision = ConsensusDecision(
            tx_hash=tx_hash,
            tier=tier,
            active_signals=active_count,
            total_signals=total,
            fired_signals=fired,
            timestamp=datetime.now(timezone.utc),
        )

        self._decisions.append(decision)

        if tier.value >= ResponseTier.ALERT_INTERNAL.value:
            logger.warning(
                "CONSENSUS [%s] tx=%s signals=%d/%d tier=%s",
                decision.action_label,
                tx_hash[:10],
                active_count,
                total,
                tier.name,
            )
        else:
            logger.info(
                "Consensus tx=%s signals=%d/%d tier=%s",
                tx_hash[:10],
                active_count,
                total,
                tier.name,
            )

        return decision

    def _map_tier(self, active_count: int) -> ResponseTier:
        """Map number of active signals to a response tier."""
        if active_count >= 4:
            return ResponseTier.GUARDIAN_PAUSE
        elif active_count >= 3:
            return ResponseTier.RATE_LIMIT
        elif active_count >= 2:
            return ResponseTier.ALERT_GOVERNANCE
        elif active_count >= 1:
            return ResponseTier.ALERT_INTERNAL
        else:
            return ResponseTier.LOG_ONLY

    def get_recent_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent consensus decisions."""
        return [d.to_dict() for d in self._decisions[-limit:]]

    def get_stats(self) -> dict[str, Any]:
        """Return consensus engine statistics."""
        tier_counts = {tier.name: 0 for tier in ResponseTier}
        for d in self._decisions:
            tier_counts[d.tier.name] += 1

        return {
            "total_decisions": len(self._decisions),
            "tier_distribution": tier_counts,
            "total_signals_configured": self._total_signals,
        }
