from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from web3 import Web3

from synaptic.simulation.fork_pool import ForkPool, ForkInstance

logger = logging.getLogger(__name__)

# PIS threshold — 15% TVL loss triggers signal
PIS_THRESHOLD = 0.15


@dataclass
class PISSimulationResult:
    """Result of a Protocol Impact Score simulation."""
    tvl_before: float
    tvl_after: float
    pis: float  # (tvl_before - tvl_after) / tvl_before
    threshold_exceeded: bool
    tx_hash: str
    fork_url: str
    error: str | None = None


class PISComputer:
    """Computes Protocol Impact Score by counterfactual simulation.

    Forks current chain state, executes the suspicious tx in a sandbox,
    and measures the TVL impact.
    """

    def __init__(self, fork_pool: ForkPool) -> None:
        self._pool = fork_pool

    async def compute(
        self,
        tx_hash: str,
        protocol_address: str,
        tvl_call_data: bytes | None = None,
    ) -> PISSimulationResult:
        """Compute PIS for a transaction against a protocol.

        Args:
            tx_hash: The suspicious transaction hash to simulate
            protocol_address: Contract address of the protocol
            tvl_call_data: ABI-encoded call to get TVL (optional, uses balanceOf default)
        """
        fork = await self._pool.acquire()
        try:
            return await self._run_simulation(fork, tx_hash, protocol_address, tvl_call_data)
        except Exception as e:
            logger.error("PIS simulation failed: %s", e)
            return PISSimulationResult(
                tvl_before=0,
                tvl_after=0,
                pis=0,
                threshold_exceeded=False,
                tx_hash=tx_hash,
                fork_url=fork.url,
                error=str(e),
            )
        finally:
            await self._pool.release(fork)

    async def _run_simulation(
        self,
        fork: ForkInstance,
        tx_hash: str,
        protocol_address: str,
        tvl_call_data: bytes | None,
    ) -> PISSimulationResult:
        """Execute the simulation on a fork instance."""
        rpc_url = fork.url

        # Get TVL before (protocol's ETH balance as proxy — real impl uses protocol-specific call)
        tvl_before = await self._get_tvl(rpc_url, protocol_address, tvl_call_data)

        # Get the full transaction
        tx_payload = {
            "jsonrpc": "2.0",
            "method": "eth_getTransactionByHash",
            "params": [tx_hash],
            "id": 1,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(rpc_url, json=tx_payload)
            tx_data = resp.json().get("result")

        if not tx_data:
            raise ValueError(f"Transaction {tx_hash} not found on fork")

        # Replay the transaction on the fork
        replay_payload = {
            "jsonrpc": "2.0",
            "method": "eth_sendTransaction",
            "params": [{
                "from": tx_data["from"],
                "to": tx_data.get("to"),
                "data": tx_data.get("input", "0x"),
                "value": tx_data.get("value", "0x0"),
                "gas": tx_data.get("gas", "0x5208"),
                "gasPrice": tx_data.get("gasPrice", "0x0"),
            }],
            "id": 2,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(rpc_url, json=replay_payload)
            result = resp.json()

        if "error" in result:
            logger.warning("Tx replay reverted: %s", result["error"])

        # Get TVL after
        tvl_after = await self._get_tvl(rpc_url, protocol_address, tvl_call_data)

        # Compute PIS
        if tvl_before == 0:
            pis = 0.0
        else:
            pis = max(0.0, (tvl_before - tvl_after) / tvl_before)

        return PISSimulationResult(
            tvl_before=tvl_before,
            tvl_after=tvl_after,
            pis=pis,
            threshold_exceeded=pis >= PIS_THRESHOLD,
            tx_hash=tx_hash,
            fork_url=fork.url,
        )

    async def _get_tvl(
        self, rpc_url: str, protocol_address: str, tvl_call_data: bytes | None
    ) -> float:
        """Get protocol TVL from the fork.

        Default: ETH balance of protocol contract.
        If tvl_call_data provided, calls the protocol directly (e.g., totalSupply, getReserves).
        """
        if tvl_call_data:
            call_payload = {
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [
                    {"to": protocol_address, "data": "0x" + tvl_call_data.hex()},
                    "latest",
                ],
                "id": 1,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(rpc_url, json=call_payload)
                data = resp.json().get("result", "0x0")
            return int(data, 16) / 1e18

        # Default: ETH balance
        balance_payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [protocol_address, "latest"],
            "id": 1,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(rpc_url, json=balance_payload)
            data = resp.json().get("result", "0x0")
        return int(data, 16) / 1e18
