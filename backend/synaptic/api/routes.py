from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, Any]:
    """Health check — verifies Redis, fork pool, and listener connectivity."""
    from synaptic.main import get_app_state

    state = get_app_state()
    checks: dict[str, Any] = {}

    # Redis
    try:
        redis_ok = await state["cache"].ping()
        checks["redis"] = "ok" if redis_ok else "error"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Fork pool
    try:
        pool_health = await state["fork_pool"].health_check()
        checks["fork_pool"] = pool_health
    except Exception as e:
        checks["fork_pool"] = f"error: {e}"

    # Listener
    checks["listener"] = "running" if state.get("listener_running") else "stopped"

    # Overall
    all_ok = (
        checks.get("redis") == "ok"
        and isinstance(checks.get("fork_pool"), dict)
        and checks["fork_pool"].get("healthy", 0) > 0
    )

    status_code = 200 if all_ok else 503
    return {"status": "ok" if all_ok else "degraded", "checks": checks}


@router.get("/status")
async def status() -> dict[str, Any]:
    """Detailed system status."""
    from synaptic.main import get_app_state

    state = get_app_state()

    pool_health = {}
    try:
        pool_health = await state["fork_pool"].health_check()
    except Exception:
        pass

    consensus_stats = {}
    try:
        consensus_stats = state["consensus"].get_stats()
    except Exception:
        pass

    return {
        "fork_pool": pool_health,
        "consensus": consensus_stats,
        "recent_decisions": state["consensus"].get_recent_decisions(limit=20),
    }


@router.post("/analyze")
async def analyze(tx_hash: str, protocol: str | None = None) -> dict[str, Any]:
    """Manually trigger analysis of a transaction hash.

    This is for development/testing — in production, txs come via mempool stream.
    """
    from web3 import Web3
    from synaptic.mempool.parser import TransactionData
    from synaptic.config import settings

    w3 = Web3(Web3.HTTPProvider(settings.alchemy_http_url))
    if not w3.is_connected():
        raise HTTPException(status_code=503, detail="Not connected to Ethereum RPC")

    try:
        tx = w3.eth.get_transaction(tx_hash)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {e}")

    # Convert to TransactionData
    from synaptic.mempool.parser import parse_transaction

    raw = {
        "hash": tx_hash,
        "to": tx.get("to"),
        "from": tx.get("from", ""),
        "value": hex(tx.get("value", 0)),
        "input": tx.get("input", b"").hex() if isinstance(tx.get("input"), bytes) else tx.get("input", "0x"),
        "gasPrice": hex(tx.get("gasPrice", 0)),
        "nonce": hex(tx.get("nonce", 0)),
        "gas": hex(tx.get("gas", 21000)),
    }
    tx_data = parse_transaction(raw)

    from synaptic.main import get_app_state

    state = get_app_state()

    # Run signals
    signal_results = []
    for signal in state["signals"]:
        result = await signal.evaluate(tx_data)
        signal_results.append({
            "signal_id": result.signal_id,
            "fired": result.fired,
            "confidence": result.confidence,
            "metadata": result.metadata,
        })

    # Run consensus
    from synaptic.signals.base import SignalResult

    sr_objects = [
        SignalResult(signal_id=s["signal_id"], fired=s["fired"], confidence=s["confidence"], metadata=s["metadata"])
        for s in signal_results
    ]
    decision = await state["consensus"].decide(tx_hash, sr_objects)

    return {
        "tx_hash": tx_hash,
        "signals": signal_results,
        "decision": decision.to_dict(),
    }
