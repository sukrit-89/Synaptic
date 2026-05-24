from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from synaptic.mempool.parser import TransactionData, parse_transaction


class TestParseTransaction:
    """Test raw transaction parsing."""

    def test_parse_legacy_transaction(self):
        raw = {
            "hash": "0xabc",
            "to": "0x1234567890abcdef1234567890abcdef12345678",
            "from": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "value": "0xde0b6b3a7640000",  # 1 ETH
            "input": "0xa9059cbb",
            "gasPrice": "0x6fc23ac00",  # 30 gwei
            "nonce": "0x2a",  # 42
            "gas": "0x7a120",  # 500,000
            "chainId": "0x1",
        }
        tx = parse_transaction(raw)

        assert tx.hash == "0xabc"
        assert tx.value == 10**18
        assert tx.nonce == 42
        assert tx.gas == 500_000
        assert tx.chain_id == 1
        assert tx.function_selector == bytes.fromhex("a9059cbb")
        assert tx.is_contract_interaction is True

    def test_parse_eip1559_transaction(self):
        raw = {
            "hash": "0xdef",
            "to": "0x1234567890abcdef1234567890abcdef12345678",
            "from": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "value": "0x0",
            "input": "0x",
            "gasPrice": "0x0",
            "maxFeePerGas": "0xba43b7400",  # 50 gwei
            "maxPriorityFeePerGas": "0x77359400",  # 2 gwei
            "nonce": "0x0",
            "gas": "0x5208",  # 21,000
        }
        tx = parse_transaction(raw)

        assert tx.max_fee_per_gas == 50 * 10**9
        assert tx.max_priority_fee_per_gas == 2 * 10**9
        assert tx.data == b""
        assert tx.is_contract_interaction is False

    def test_parse_contract_creation(self):
        raw = {
            "hash": "0xcreate",
            "to": None,
            "from": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "value": "0x0",
            "input": "0x6080604052",
            "gasPrice": "0x6fc23ac00",
            "nonce": "0x0",
            "gas": "0x1e8480",
        }
        tx = parse_transaction(raw)

        assert tx.to is None
        assert tx.data_length > 0

    def test_value_eth_property(self):
        raw = {
            "hash": "0xval",
            "to": "0x1234567890abcdef1234567890abcdef12345678",
            "from": "0xdead",
            "value": "0x1bc16d674ec80000",  # 2 ETH
            "input": "0x",
            "gasPrice": "0x0",
            "nonce": "0x0",
            "gas": "0x5208",
        }
        tx = parse_transaction(raw)

        assert tx.value_eth == 2.0
        assert tx.is_high_value is False

    def test_is_high_value(self):
        raw = {
            "hash": "0xhigh",
            "to": "0x1234567890abcdef1234567890abcdef12345678",
            "from": "0xdead",
            "value": hex(200 * 10**18),
            "input": "0x",
            "gasPrice": "0x0",
            "nonce": "0x0",
            "gas": "0x5208",
        }
        tx = parse_transaction(raw)

        assert tx.is_high_value is True

    def test_missing_fields_default_safely(self):
        """Minimal raw tx — missing optional fields should default."""
        raw = {
            "hash": "0xmin",
            "from": "0xdead",
        }
        tx = parse_transaction(raw)

        assert tx.to is None
        assert tx.value == 0
        assert tx.data == b""
        assert tx.gas_price == 0
        assert tx.nonce == 0
        assert tx.gas == 21000
