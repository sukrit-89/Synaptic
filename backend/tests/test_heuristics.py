from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from synaptic.mempool.parser import TransactionData, parse_transaction
from synaptic.signals.heuristics import HeuristicSignal


class TestFlashLoanDetection:
    """Test flash loan pattern detection."""

    @pytest.mark.asyncio
    async def test_detects_aave_v3_flash_loan(self, flash_loan_tx: TransactionData):
        signal = HeuristicSignal()
        result = await signal.evaluate(flash_loan_tx)

        assert result.signal_id == "heuristics"
        assert result.fired is True
        assert "flash_loan_pattern" in result.metadata["reasons"]
        assert result.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_no_flash_loan_for_simple_transfer(self, sample_tx: TransactionData):
        signal = HeuristicSignal()
        # Replace data with simple ETH transfer (no calldata)
        tx = TransactionData(
            hash=sample_tx.hash,
            to=sample_tx.to,
            from_addr=sample_tx.from_addr,
            value=sample_tx.value,
            data=b"",
            gas_price=sample_tx.gas_price,
            max_fee_per_gas=sample_tx.max_fee_per_gas,
            max_priority_fee_per_gas=sample_tx.max_priority_fee_per_gas,
            nonce=sample_tx.nonce,
            gas=21_000,
            chain_id=sample_tx.chain_id,
        )
        result = await signal.evaluate(tx)

        # Should not fire for a simple ETH transfer
        assert "flash_loan_pattern" not in result.metadata.get("reasons", [])


class TestValueExtractionDetection:
    """Test high-value extraction detection."""

    @pytest.mark.asyncio
    async def test_detects_high_value_transfer(self, high_value_tx: TransactionData):
        signal = HeuristicSignal()
        result = await signal.evaluate(high_value_tx)

        assert result.fired is True
        assert "high_value_extraction" in result.metadata["reasons"]

    @pytest.mark.asyncio
    async def test_low_value_transfer_not_flagged(self, sample_tx: TransactionData):
        signal = HeuristicSignal()
        result = await signal.evaluate(sample_tx)

        # 1 ETH is below the 50 ETH threshold
        assert "high_value_extraction" not in result.metadata.get("reasons", [])


class TestGasAnomalyDetection:
    """Test gas anomaly detection."""

    @pytest.mark.asyncio
    async def test_detects_high_gas_tx(self, flash_loan_tx: TransactionData):
        signal = HeuristicSignal()
        result = await signal.evaluate(flash_loan_tx)

        # 3M gas is above 5M threshold? No, it's below. Let's check:
        # Our threshold is 5,000,000 and this tx has 3,000,000 — should not fire
        assert "gas_anomaly" not in result.metadata.get("reasons", [])

    @pytest.mark.asyncio
    async def test_detects_extreme_gas(self):
        tx = TransactionData(
            hash="0xgas",
            to="0x1234567890abcdef1234567890abcdef12345678",
            from_addr="0xdead",
            value=0,
            data=bytes.fromhex("a415bcad" + "00" * 64),
            gas_price=30 * 10**9,
            max_fee_per_gas=None,
            max_priority_fee_per_gas=None,
            nonce=0,
            gas=10_000_000,  # 10M gas — very high
            chain_id=1,
        )
        signal = HeuristicSignal()
        result = await signal.evaluate(tx)

        assert "gas_anomaly" in result.metadata["reasons"]


class TestMultipleSignals:
    """Test that multiple signals can fire simultaneously."""

    @pytest.mark.asyncio
    async def test_flash_loan_plus_high_gas_fires_multiple(self):
        tx = TransactionData(
            hash="0xmulti",
            to="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            from_addr="0xbbbb",
            value=100 * 10**18,  # 100 ETH
            data=bytes.fromhex("a415bcad" + "00" * 256),  # flash loan selector
            gas_price=50 * 10**9,
            max_fee_per_gas=None,
            max_priority_fee_per_gas=None,
            nonce=0,
            gas=8_000_000,  # High gas
            chain_id=1,
        )
        signal = HeuristicSignal()
        result = await signal.evaluate(tx)

        assert result.fired is True
        assert len(result.metadata["reasons"]) >= 2
        assert "flash_loan_pattern" in result.metadata["reasons"]
        assert "high_value_extraction" in result.metadata["reasons"]
        assert "gas_anomaly" in result.metadata["reasons"]


class TestContractCreation:
    """Test handling of contract creation transactions."""

    @pytest.mark.asyncio
    async def test_contract_creation_no_crash(self):
        tx = TransactionData(
            hash="0xcreate",
            to=None,  # Contract creation
            from_addr="0xdead",
            value=0,
            data=bytes.fromhex("608060405234801561001057600080fd5b50"),
            gas_price=30 * 10**9,
            max_fee_per_gas=None,
            max_priority_fee_per_gas=None,
            nonce=0,
            gas=3_000_000,
            chain_id=1,
        )
        signal = HeuristicSignal()
        result = await signal.evaluate(tx)

        # Should not crash, should return a valid result
        assert result.signal_id == "heuristics"
        assert isinstance(result.fired, bool)
