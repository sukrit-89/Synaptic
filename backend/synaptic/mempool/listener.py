from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable, Awaitable

import redis.asyncio as aioredis
import websockets
from websockets.exceptions import ConnectionClosed

from synaptic.config import settings

logger = logging.getLogger(__name__)

# Alchemy subscription payload for pending transactions (full tx objects)
SUBSCRIBE_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "eth_subscribe",
    "params": ["alchemy_pendingTransactions", {"hashesOnly": False}],
}


class MempoolListener:
    """Connects to Alchemy WebSocket and yields pending transactions.

    Handles reconnection and deduplicates tx hashes via Redis.
    """

    def __init__(
        self,
        ws_url: str | None = None,
        redis_url: str | None = None,
        dedup_ttl: int = 300,
    ) -> None:
        self.ws_url = ws_url or settings.alchemy_ws_url
        self.redis_url = redis_url or settings.redis_url
        self.dedup_ttl = dedup_ttl  # seconds to remember a seen tx hash
        self._redis: aioredis.Redis | None = None
        self._ws: Any = None
        self._running = False

    async def connect(self) -> None:
        """Establish WebSocket and Redis connections."""
        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        await self._redis.ping()
        logger.info("Redis connected for mempool dedup")

        self._ws = await websockets.connect(self.ws_url, max_size=10 * 1024 * 1024)
        await self._ws.send(json.dumps(SUBSCRIBE_PAYLOAD))
        # Consume subscription confirmation
        resp = await self._ws.recv()
        data = json.loads(resp)
        if "result" not in data:
            raise RuntimeError(f"Alchemy subscription failed: {data}")
        logger.info("Alchemy WebSocket subscribed: %s", data["result"])

    async def _is_duplicate(self, tx_hash: str) -> bool:
        """Check if we've already seen this tx hash. Returns True if duplicate."""
        key = f"mempool:seen:{tx_hash}"
        result = await self._redis.set(key, "1", nx=True, ex=self.dedup_ttl)
        return result is None  # None means key already existed

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        """Yield pending transactions, reconnecting on failure.

        Each yielded item is a raw transaction dict from Alchemy.
        """
        self._running = True
        while self._running:
            try:
                await self.connect()
                logger.info("Mempool stream started")
                async for message in self._ws:
                    if not self._running:
                        break
                    try:
                        data = json.loads(message)
                        tx = data.get("params", {}).get("result")
                        if not tx or not isinstance(tx, dict):
                            continue
                        tx_hash = tx.get("hash", "")
                        if not tx_hash:
                            continue
                        if await self._is_duplicate(tx_hash):
                            continue
                        yield tx
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.debug("Skipping malformed message: %s", e)
            except ConnectionClosed as e:
                logger.warning("WebSocket closed (%s), reconnecting in 2s...", e)
                await asyncio.sleep(2)
            except Exception as e:
                logger.error("Mempool stream error: %s, reconnecting in 5s...", e)
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Gracefully stop the listener."""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._redis:
            await self._redis.aclose()
        logger.info("Mempool listener stopped")

    async def __aenter__(self) -> MempoolListener:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()
