from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis
from eth_abi import decode as abi_decode
from eth_utils import function_signature_to_4byte_selector

from synaptic.config import settings

logger = logging.getLogger(__name__)

# Cache key prefix for ABIs in Redis
ABI_PREFIX = "abi:"
SELECTOR_PREFIX = "selector:"


class CalldataDecoder:
    """Decodes transaction calldata using cached ABIs.

    Falls back to raw hex display for unknown function selectors.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def load_abi(self, contract_address: str, abi: list[dict[str, Any]]) -> None:
        """Load and index an ABI for a contract address.

        Indexes all function selectors → (name, input types) for fast lookup.
        """
        addr_key = contract_address.lower()
        abi_json = json.dumps(abi)
        await self._redis.set(f"{ABI_PREFIX}{addr_key}", abi_json)

        for item in abi:
            if item.get("type") != "function":
                continue
            name = item["name"]
            inputs = item.get("inputs", [])
            types = ",".join(inp["type"] for inp in inputs)
            sig = f"{name}({types})"
            selector = function_signature_to_4byte_selector(sig)
            selector_hex = selector.hex()
            entry = json.dumps({"name": name, "types": types, "signature": sig})
            await self._redis.hset(f"{SELECTOR_PREFIX}{addr_key}", selector_hex, entry)

        logger.info("Loaded ABI for %s (%d functions)", addr_key, len(abi))

    async def decode(self, to: str | None, calldata: bytes) -> dict[str, Any]:
        """Decode calldata for a contract interaction.

        Returns:
            {
                "function": str,
                "signature": str,
                "args": list,
                "decoded": bool,
            }
        """
        if not to or len(calldata) < 4:
            return {"function": None, "signature": None, "args": [], "decoded": False}

        selector_hex = calldata[:4].hex()
        addr_key = to.lower()

        # Try contract-specific ABI first
        entry_json = await self._redis.hget(f"{SELECTOR_PREFIX}{addr_key}", selector_hex)
        if entry_json:
            entry = json.loads(entry_json)
            return await self._decode_with_entry(entry, calldata)

        # Try scanning all loaded ABIs (for contracts we haven't explicitly indexed)
        # This handles proxies and common patterns
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=f"{SELECTOR_PREFIX}*", count=50)
            for key in keys:
                entry_json = await self._redis.hget(key, selector_hex)
                if entry_json:
                    entry = json.loads(entry_json)
                    return await self._decode_with_entry(entry, calldata)
            if cursor == 0:
                break

        # Unknown selector
        return {
            "function": f"unknown_{selector_hex}",
            "signature": None,
            "args": list(calldata[4:]),
            "decoded": False,
        }

    async def _decode_with_entry(
        self, entry: dict[str, str], calldata: bytes
    ) -> dict[str, Any]:
        """Decode calldata using a known function entry."""
        name = entry["name"]
        types_str = entry["types"]
        sig = entry["signature"]

        if not types_str:
            # No inputs
            return {"function": name, "signature": sig, "args": [], "decoded": True}

        types = types_str.split(",")
        try:
            args = list(abi_decode(types, calldata[4:]))
            # Convert bytes/hex types to strings for JSON serialization
            args = [_serialize_arg(a) for a in args]
            return {"function": name, "signature": sig, "args": args, "decoded": True}
        except Exception as e:
            logger.debug("ABI decode failed for %s: %s", sig, e)
            return {
                "function": name,
                "signature": sig,
                "args": [calldata[4:].hex()],
                "decoded": False,
            }


def _serialize_arg(arg: Any) -> Any:
    """Convert ABI-decoded values to JSON-serializable types."""
    if isinstance(arg, bytes):
        return "0x" + arg.hex()
    if isinstance(arg, tuple):
        return [_serialize_arg(a) for a in arg]
    if isinstance(arg, list):
        return [_serialize_arg(a) for a in arg]
    return arg
