from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any

from web3 import Web3

from synaptic.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ForkInstance:
    """A single Anvil fork instance."""
    port: int
    process: subprocess.Popen | None = None
    in_use: bool = False
    created_at: float = 0.0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@dataclass
class ForkPool:
    """Manages a pool of pre-spawned Anvil fork instances for counterfactual simulation.

    Pre-spawning avoids 2-3s cold-start latency per simulation.
    Rotates through available forks and re-spawns in background.
    """

    pool_size: int = 3
    base_port: int = 8545
    fork_url: str = ""
    fork_block_lag: int = 5
    _forks: list[ForkInstance] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _initialized: bool = False

    def __post_init__(self) -> None:
        if not self.fork_url:
            self.fork_url = settings.alchemy_http_url
        if not self.pool_size:
            self.pool_size = settings.fork_pool_size
        if not self.fork_block_lag:
            self.fork_block_lag = settings.fork_block_lag

    async def initialize(self) -> None:
        """Pre-spawn all fork instances."""
        logger.info("Initializing fork pool with %d instances", self.pool_size)
        tasks = [self._spawn_fork(self.base_port + i) for i in range(self.pool_size)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Failed to spawn fork on port %d: %s", self.base_port + i, result)
            else:
                self._forks.append(result)

        self._initialized = True
        logger.info("Fork pool ready: %d/%d instances", len(self._forks), self.pool_size)

    async def _spawn_fork(self, port: int) -> ForkInstance:
        """Spawn a single Anvil fork instance."""
        cmd = [
            "anvil",
            "--port", str(port),
            "--fork-url", self.fork_url,
            "--fork-block-number", str(await self._get_latest_block() - self.fork_block_lag),
            "--silent",
            "--accounts", "0",
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for Anvil to be ready
        w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{port}"))
        for _ in range(50):  # 5 second timeout
            try:
                if w3.is_connected():
                    break
            except Exception:
                pass
            await asyncio.sleep(0.1)
        else:
            process.kill()
            raise RuntimeError(f"Anvil on port {port} failed to start in 5s")

        logger.info("Anvil fork spawned on port %d (PID %d)", port, process.pid)
        return ForkInstance(port=port, process=process)

    async def _get_latest_block(self) -> int:
        """Get latest block number from the RPC endpoint."""
        import httpx

        payload = {
            "jsonrpc": "2.0",
            "method": "eth_blockNumber",
            "params": [],
            "id": 1,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self.fork_url, json=payload)
            data = resp.json()
        return int(data["result"], 16)

    async def acquire(self) -> ForkInstance:
        """Acquire an available fork instance. Waits if all are busy."""
        async with self._lock:
            for fork in self._forks:
                if not fork.in_use:
                    fork.in_use = True
                    return fork

        # All busy — wait and retry
        logger.warning("All forks in use, waiting...")
        while True:
            await asyncio.sleep(0.1)
            async with self._lock:
                for fork in self._forks:
                    if not fork.in_use:
                        fork.in_use = True
                        return fork

    async def release(self, fork: ForkInstance) -> None:
        """Release a fork instance back to the pool."""
        async with self._lock:
            fork.in_use = False

        # Respawn this fork in background to get fresh state
        asyncio.create_task(self._respawn_fork(fork))

    async def _respawn_fork(self, fork: ForkInstance) -> None:
        """Kill and re-spawn a fork instance with fresh state."""
        try:
            if fork.process:
                fork.process.kill()
                fork.process.wait(timeout=5)
        except Exception as e:
            logger.warning("Error killing fork on port %d: %s", fork.port, e)

        try:
            new_fork = await self._spawn_fork(fork.port)
            async with self._lock:
                idx = next(i for i, f in enumerate(self._forks) if f.port == fork.port)
                self._forks[idx] = new_fork
            logger.info("Fork on port %d respawned", fork.port)
        except Exception as e:
            logger.error("Failed to respawn fork on port %d: %s", fork.port, e)

    async def health_check(self) -> dict[str, Any]:
        """Return pool health status."""
        healthy = 0
        for fork in self._forks:
            try:
                w3 = Web3(Web3.HTTPProvider(fork.url))
                if w3.is_connected():
                    healthy += 1
            except Exception:
                pass

        return {
            "total": self.pool_size,
            "active": len(self._forks),
            "healthy": healthy,
            "available": sum(1 for f in self._forks if not f.in_use),
        }

    async def shutdown(self) -> None:
        """Kill all fork instances."""
        for fork in self._forks:
            try:
                if fork.process:
                    fork.process.kill()
                    fork.process.wait(timeout=5)
            except Exception:
                pass
        self._forks.clear()
        logger.info("Fork pool shut down")
