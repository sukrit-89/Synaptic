from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import redis.asyncio as aioredis

from synaptic.config import settings
from synaptic.mempool.decoder import CalldataDecoder

logger = logging.getLogger(__name__)

# Default directory for local ABI files
ABI_DIR = Path(__file__).parent.parent.parent / "abis"


class ABILoader:
    """Loads contract ABIs from local files and optionally from Etherscan.

    Populates the CalldataDecoder's Redis cache on load.
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        decoder: CalldataDecoder,
        abi_dir: Path | None = None,
    ) -> None:
        self._redis = redis
        self._decoder = decoder
        self._abi_dir = abi_dir or ABI_DIR
        self._etherscan_key = settings.etherscan_api_key

    async def load_local(self) -> int:
        """Load all ABI JSON files from the local abis/ directory.

        Expected file naming: <address>.json or <name>.json
        If the filename is an address (0x...), it's indexed by address.
        Otherwise, it's loaded but not address-indexed (for common ABIs).

        Returns number of ABIs loaded.
        """
        if not self._abi_dir.exists():
            logger.info("No local ABI directory at %s, skipping", self._abi_dir)
            return 0

        count = 0
        for path in sorted(self._abi_dir.glob("*.json")):
            try:
                abi = json.loads(path.read_text())
                if not isinstance(abi, list):
                    logger.warning("Skipping %s: not a JSON array", path.name)
                    continue

                # If filename looks like an address, index by address
                name = path.stem
                if name.startswith("0x") and len(name) == 42:
                    await self._decoder.load_abi(name, abi)
                else:
                    # Common ABI — store under a generic key for selector matching
                    await self._decoder.load_abi(f"_common:{name}", abi)

                count += 1
            except Exception as e:
                logger.error("Failed to load ABI %s: %s", path.name, e)

        logger.info("Loaded %d local ABIs", count)
        return count

    async def fetch_from_etherscan(self, address: str) -> list[dict[str, Any]] | None:
        """Fetch ABI from Etherscan for a given contract address.

        Returns None if fetch fails or no API key configured.
        """
        if not self._etherscan_key:
            logger.debug("No Etherscan API key configured, skipping fetch for %s", address)
            return None

        url = "https://api.etherscan.io/api"
        params = {
            "module": "contract",
            "action": "getabi",
            "address": address,
            "apikey": self._etherscan_key,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                data = resp.json()

            if data.get("status") != "1" or not data.get("result"):
                logger.warning("Etherscan ABI fetch failed for %s: %s", address, data.get("message"))
                return None

            abi = json.loads(data["result"])
            await self._decoder.load_abi(address, abi)
            logger.info("Fetched and loaded ABI from Etherscan for %s", address)
            return abi
        except Exception as e:
            logger.error("Etherscan fetch error for %s: %s", address, e)
            return None

    async def ensure_abi(self, address: str) -> bool:
        """Ensure an ABI is loaded for a given address.

        Tries local cache first, then Etherscan. Returns True if ABI is available.
        """
        # Check Redis cache
        from synaptic.mempool.decoder import ABI_PREFIX

        cached = await self._redis.get(f"{ABI_PREFIX}{address.lower()}")
        if cached:
            return True

        # Try Etherscan
        abi = await self.fetch_from_etherscan(address)
        return abi is not None
