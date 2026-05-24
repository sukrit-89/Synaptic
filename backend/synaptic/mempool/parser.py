from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from web3 import Web3

logger = logging.getLogger(__name__)

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@dataclass(frozen=True, slots=True)
class TransactionData:
    """Structured representation of a pending Ethereum transaction."""

    hash: str
    to: str | None  # None for contract creation
    from_addr: str
    value: int  # wei
    data: bytes
    gas_price: int  # wei
    max_fee_per_gas: int | None
    max_priority_fee_per_gas: int | None
    nonce: int
    gas: int
    chain_id: int | None
    # Derived fields
    function_selector: bytes = field(default=b"")
    data_length: int = field(default=0)

    @property
    def value_eth(self) -> float:
        return self.value / 1e18

    @property
    def is_contract_interaction(self) -> bool:
        return self.to is not None and len(self.data) >= 4

    @property
    def is_high_value(self) -> bool:
        return self.value_eth > 10.0


def parse_transaction(raw: dict[str, Any]) -> TransactionData:
    """Convert a raw JSON-RPC transaction dict into TransactionData.

    Handles both legacy and EIP-1559 transactions.
    """
    to = raw.get("to")
    data_hex = raw.get("input", raw.get("data", "0x"))
    if data_hex is None:
        data_hex = "0x"
    data_bytes = bytes.fromhex(data_hex[2:]) if data_hex.startswith("0x") else bytes.fromhex(data_hex)

    value_hex = raw.get("value", "0x0")
    value = int(value_hex, 16) if isinstance(value_hex, str) else int(value_hex)

    gas_price_hex = raw.get("gasPrice", "0x0")
    gas_price = int(gas_price_hex, 16) if isinstance(gas_price_hex, str) else int(gas_price_hex)

    max_fee = raw.get("maxFeePerGas")
    if max_fee is not None:
        max_fee = int(max_fee, 16) if isinstance(max_fee, str) else int(max_fee)

    max_priority = raw.get("maxPriorityFeePerGas")
    if max_priority is not None:
        max_priority = int(max_priority, 16) if isinstance(max_priority, str) else int(max_priority)

    nonce_hex = raw.get("nonce", "0x0")
    nonce = int(nonce_hex, 16) if isinstance(nonce_hex, str) else int(nonce_hex)

    gas_hex = raw.get("gas", "0x5208")
    gas = int(gas_hex, 16) if isinstance(gas_hex, str) else int(gas_hex)

    chain_id = raw.get("chainId")
    if chain_id is not None:
        chain_id = int(chain_id, 16) if isinstance(chain_id, str) else int(chain_id)

    selector = data_bytes[:4] if len(data_bytes) >= 4 else b""

    return TransactionData(
        hash=raw.get("hash", ""),
        to=_safe_checksum_address(to) if to else None,
        from_addr=_safe_checksum_address(raw.get("from", ZERO_ADDRESS)) or ZERO_ADDRESS,
        value=value,
        data=data_bytes,
        gas_price=gas_price,
        max_fee_per_gas=max_fee,
        max_priority_fee_per_gas=max_priority,
        nonce=nonce,
        gas=gas,
        chain_id=chain_id,
        function_selector=selector,
        data_length=len(data_bytes),
    )


def _safe_checksum_address(value: Any) -> str | None:
    """Return a checksum address, defaulting invalid JSON-RPC test values safely."""
    if not value:
        return None

    try:
        return Web3.to_checksum_address(value)
    except (TypeError, ValueError):
        logger.debug("Invalid address in transaction payload: %r", value)
        return Web3.to_checksum_address(ZERO_ADDRESS)
