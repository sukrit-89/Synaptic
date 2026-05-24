from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from synaptic.mempool.parser import TransactionData


@pytest.fixture
def sample_tx() -> TransactionData:
    """A standard contract interaction transaction."""
    return TransactionData(
        hash="0xabc123def456",
        to="0x1234567890abcdef1234567890abcdef12345678",
        from_addr="0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        value=10**18,  # 1 ETH
        data=bytes.fromhex("a415bcad" + "00" * 128),  # Aave flashLoan selector + dummy data
        gas_price=30 * 10**9,  # 30 gwei
        max_fee_per_gas=50 * 10**9,
        max_priority_fee_per_gas=2 * 10**9,
        nonce=42,
        gas=500_000,
        chain_id=1,
    )


@pytest.fixture
def high_value_tx() -> TransactionData:
    """A high-value ETH transfer."""
    return TransactionData(
        hash="0xhighvalue123",
        to="0x1234567890abcdef1234567890abcdef12345678",
        from_addr="0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        value=100 * 10**18,  # 100 ETH
        data=b"",
        gas_price=30 * 10**9,
        max_fee_per_gas=None,
        max_priority_fee_per_gas=None,
        nonce=1,
        gas=21_000,
        chain_id=1,
    )


@pytest.fixture
def flash_loan_tx() -> TransactionData:
    """A transaction with flash loan function selector."""
    return TransactionData(
        hash="0xflashloan456",
        to="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        from_addr="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        value=0,
        # Aave V3 flashLoan selector
        data=bytes.fromhex("a415bcad" + "00" * 256),
        gas_price=50 * 10**9,
        max_fee_per_gas=100 * 10**9,
        max_priority_fee_per_gas=5 * 10**9,
        nonce=100,
        gas=3_000_000,
        chain_id=1,
    )


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing state cache."""
    mock = AsyncMock()
    mock.ping.return_value = True
    mock.set.return_value = True
    mock.get.return_value = None
    mock.hget.return_value = None
    mock.hset.return_value = None
    mock.scan.return_value = (0, [])
    mock.aclose.return_value = None
    return mock
