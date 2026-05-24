from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from synaptic.tasks.celery_app import app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async function in a sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(name="synaptic.tasks.analysis.run_heuristics", bind=True)
def run_heuristics(self, tx_data: dict[str, Any]) -> dict[str, Any]:
    """Run Signal 1 (heuristics) on a parsed transaction.

    Args:
        tx_data: Serialized TransactionData dict
    Returns:
        Serialized SignalResult
    """
    from synaptic.mempool.parser import TransactionData
    from synaptic.signals.heuristics import HeuristicSignal
    from synaptic.state.redis_cache import RedisStateCache

    async def _run():
        cache = RedisStateCache()
        await cache.connect()
        try:
            signal = HeuristicSignal(state_cache=cache)
            tx = _deserialize_tx(tx_data)
            result = await signal.evaluate(tx)
            return {
                "signal_id": result.signal_id,
                "fired": result.fired,
                "confidence": result.confidence,
                "metadata": result.metadata,
            }
        finally:
            await cache.close()

    return _run_async(_run())


@app.task(name="synaptic.tasks.analysis.run_simulation", bind=True)
def run_simulation(
    self,
    tx_data: dict[str, Any],
    protocol_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Run Signal 3 (counterfactual simulation) on a parsed transaction.

    Args:
        tx_data: Serialized TransactionData dict
        protocol_configs: Protocol configuration for PIS computation
    Returns:
        Serialized SignalResult
    """
    from synaptic.mempool.parser import TransactionData
    from synaptic.signals.simulation import SimulationSignal
    from synaptic.simulation.fork_pool import ForkPool
    from synaptic.simulation.pis import PISComputer

    async def _run():
        pool = ForkPool()
        await pool.initialize()
        try:
            pis = PISComputer(pool)
            signal = SimulationSignal(pis_computer=pis, protocol_configs=protocol_configs)
            tx = _deserialize_tx(tx_data)
            result = await signal.evaluate(tx)
            return {
                "signal_id": result.signal_id,
                "fired": result.fired,
                "confidence": result.confidence,
                "metadata": result.metadata,
            }
        finally:
            await pool.shutdown()

    return _run_async(_run())


@app.task(name="synaptic.tasks.analysis.aggregate_signals", bind=True)
def aggregate_signals(
    self,
    tx_hash: str,
    signal_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate signal results into a consensus decision.

    Args:
        tx_hash: Transaction hash
        signal_results: List of serialized SignalResult dicts
    Returns:
        Serialized ConsensusDecision
    """
    from synaptic.signals.base import SignalResult
    from synaptic.consensus.engine import ConsensusEngine

    async def _run():
        engine = ConsensusEngine(total_signals=len(signal_results))
        results = [
            SignalResult(
                signal_id=s["signal_id"],
                fired=s["fired"],
                confidence=s["confidence"],
                metadata=s.get("metadata", {}),
            )
            for s in signal_results
        ]
        decision = await engine.decide(tx_hash, results)
        return decision.to_dict()

    return _run_async(_run())


def _deserialize_tx(tx_data: dict[str, Any]):
    """Deserialize a TransactionData dict back into a TransactionData object."""
    from synaptic.mempool.parser import TransactionData

    return TransactionData(
        hash=tx_data["hash"],
        to=tx_data.get("to"),
        from_addr=tx_data["from_addr"],
        value=tx_data["value"],
        data=bytes.fromhex(tx_data["data_hex"]) if isinstance(tx_data.get("data_hex"), str) else tx_data.get("data", b""),
        gas_price=tx_data["gas_price"],
        max_fee_per_gas=tx_data.get("max_fee_per_gas"),
        max_priority_fee_per_gas=tx_data.get("max_priority_fee_per_gas"),
        nonce=tx_data["nonce"],
        gas=tx_data["gas"],
        chain_id=tx_data.get("chain_id"),
    )
