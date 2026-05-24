from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from synaptic.config import settings

logger = logging.getLogger(__name__)

# Key prefixes
RESERVE_PREFIX = "reserve:"
PRICE_PREFIX = "price:"
TVL_PREFIX = "tvl:"
META_PREFIX = "meta:"


class RedisStateCache:
    """Async Redis wrapper for Synaptic's hot state.

    Stores ABIs (via decoder), reserve states, price feeds, and metadata
    with per-block TTLs.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._url = redis_url or settings.redis_url
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(self._url, decode_responses=True)
        await self._redis.ping()
        logger.info("Redis state cache connected")

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    @property
    def redis(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("RedisStateCache not connected — call connect() first")
        return self._redis

    # --- Reserve state ---

    async def set_reserves(
        self, protocol: str, pair: str, reserves: dict[str, Any], ttl: int = 12
    ) -> None:
        """Store reserve state for a protocol/pair with block-level TTL."""
        key = f"{RESERVE_PREFIX}{protocol}:{pair}"
        await self.redis.set(key, json.dumps(reserves), ex=ttl)

    async def get_reserves(self, protocol: str, pair: str) -> dict[str, Any] | None:
        key = f"{RESERVE_PREFIX}{protocol}:{pair}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    # --- Price feeds ---

    async def set_price(self, token: str, price_usd: float, ttl: int = 12) -> None:
        key = f"{PRICE_PREFIX}{token.lower()}"
        await self.redis.set(key, str(price_usd), ex=ttl)

    async def get_price(self, token: str) -> float | None:
        key = f"{PRICE_PREFIX}{token.lower()}"
        val = await self.redis.get(key)
        return float(val) if val else None

    # --- TVL tracking ---

    async def set_tvl(self, protocol: str, tvl: float, ttl: int = 60) -> None:
        key = f"{TVL_PREFIX}{protocol}"
        await self.redis.set(key, str(tvl), ex=ttl)

    async def get_tvl(self, protocol: str) -> float | None:
        key = f"{TVL_PREFIX}{protocol}"
        val = await self.redis.get(key)
        return float(val) if val else None

    # --- Generic metadata ---

    async def set_meta(self, key: str, value: Any, ttl: int | None = None) -> None:
        full_key = f"{META_PREFIX}{key}"
        serialized = json.dumps(value) if not isinstance(value, str) else value
        if ttl:
            await self.redis.set(full_key, serialized, ex=ttl)
        else:
            await self.redis.set(full_key, serialized)

    async def get_meta(self, key: str) -> Any | None:
        full_key = f"{META_PREFIX}{key}"
        val = await self.redis.get(full_key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return val

    # --- Health ---

    async def ping(self) -> bool:
        try:
            return await self.redis.ping()
        except Exception:
            return False
