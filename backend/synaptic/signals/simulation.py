from __future__ import annotations

import logging
from typing import Any

from synaptic.mempool.parser import TransactionData
from synaptic.signals.base import Signal, SignalResult
from synaptic.simulation.pis import PISComputer, PIS_THRESHOLD

logger = logging.getLogger(__name__)


class SimulationSignal(Signal):
    """Signal 3: Counterfactual simulation (PIS).

    Forks current chain state, executes the suspicious tx in sandbox,
    computes Protocol Impact Score (PIS).

    PIS = (tvl_before - tvl_after) / tvl_before
    PIS >= 0.15 (15% TVL loss) → signal fires
    """

    signal_id = "simulation"

    def __init__(self, pis_computer: PISComputer, protocol_configs: dict[str, dict[str, Any]] | None = None) -> None:
        """
        Args:
            pis_computer: The PIS computation engine
            protocol_configs: {protocol_name: {"address": "0x...", "tvl_call_data": bytes}}
        """
        self._pis = pis_computer
        self._configs = protocol_configs or {}

    async def evaluate(self, tx: TransactionData) -> SignalResult:
        """Run counterfactual simulation for the transaction."""
        if not tx.to:
            return SignalResult(
                signal_id=self.signal_id,
                fired=False,
                confidence=0.0,
                metadata={"reason": "contract_creation_no_simulation"},
            )

        # Find matching protocol config
        protocol_name, protocol_config = self._find_protocol(tx.to)
        if not protocol_config:
            return SignalResult(
                signal_id=self.signal_id,
                fired=False,
                confidence=0.0,
                metadata={"reason": "no_protocol_config", "to": tx.to},
            )

        # Run PIS simulation
        tvl_call_data = protocol_config.get("tvl_call_data")
        result = await self._pis.compute(
            tx_hash=tx.hash,
            protocol_address=protocol_config["address"],
            tvl_call_data=tvl_call_data,
        )

        if result.error:
            return SignalResult(
                signal_id=self.signal_id,
                fired=False,
                confidence=0.0,
                metadata={"error": result.error, "protocol": protocol_name},
            )

        # PIS fires if threshold exceeded
        fired = result.threshold_exceeded
        confidence = min(1.0, result.pis / PIS_THRESHOLD) if fired else result.pis / PIS_THRESHOLD * 0.5

        return SignalResult(
            signal_id=self.signal_id,
            fired=fired,
            confidence=confidence,
            metadata={
                "protocol": protocol_name,
                "pis": result.pis,
                "tvl_before": result.tvl_before,
                "tvl_after": result.tvl_after,
                "threshold": PIS_THRESHOLD,
                "fork_url": result.fork_url,
            },
        )

    def _find_protocol(self, address: str) -> tuple[str | None, dict[str, Any] | None]:
        """Find a protocol config matching the given contract address."""
        addr_lower = address.lower()
        for name, config in self._configs.items():
            if config.get("address", "").lower() == addr_lower:
                return name, config
        return None, None
