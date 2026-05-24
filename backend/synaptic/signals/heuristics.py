from __future__ import annotations

import logging
from typing import Any

from synaptic.mempool.parser import TransactionData
from synaptic.signals.base import Signal, SignalResult
from synaptic.state.redis_cache import RedisStateCache

logger = logging.getLogger(__name__)

# Known flash loan function selectors (common across Aave, dYdX, Balancer, Euler)
FLASH_LOAN_SELECTORS = {
    bytes.fromhex("a415bcad"),  # Aave V3: flashLoan(address,address[],uint256[],uint256[],address,bytes,uint16)
    bytes.fromhex("5cffe9de"),  # Aave V2: flashLoan(address,address[],uint256[],uint256[],address,bytes,uint16,uint16)
    bytes.fromhex("e0232b42"),  # Balancer: flashLoan(address,address[],uint256[],bytes)
    bytes.fromhex("0164ad23"),  # dYdX: operate(Account.Info,Actions.ActionArgs[])
    bytes.fromhex("b2e18b06"),  # Euler: flashLoan(uint256,address,address,uint256,bytes)
}

# Known liquidation selectors
LIQUIDATION_SELECTORS = {
    bytes.fromhex("00a718a9"),  # Aave V3: liquidationCall
    bytes.fromhex("07393199"),  # Compound: liquidateBorrow
}

# Thresholds
RESERVE_SPIKE_RATIO = 0.20  # 20% reserve change = suspicious
HIGH_VALUE_ETH = 50.0  # ETH
SINGLE_TX_GAS_LIMIT = 5_000_000  # Unusually high gas = complex attack


class HeuristicSignal(Signal):
    """Signal 1: Rule-based heuristic pre-filter.

    Fast checks that catch known attack patterns without simulation:
    - Flash loan detection
    - Reserve ratio spike
    - Same-block profit extraction
    - Unusual gas usage
    """

    signal_id = "heuristics"

    def __init__(self, state_cache: RedisStateCache | None = None) -> None:
        self._cache = state_cache

    async def evaluate(self, tx: TransactionData) -> SignalResult:
        """Run all heuristic checks and aggregate."""
        reasons: list[str] = []
        max_confidence = 0.0

        # Check 1: Flash loan pattern
        is_flash_loan, fl_confidence = self._check_flash_loan(tx)
        if is_flash_loan:
            reasons.append("flash_loan_pattern")
            max_confidence = max(max_confidence, fl_confidence)

        # Check 2: Reserve ratio spike (requires state cache)
        if self._cache and tx.to:
            has_spike, spike_confidence = await self._check_reserve_spike(tx)
            if has_spike:
                reasons.append("reserve_spike")
                max_confidence = max(max_confidence, spike_confidence)

        # Check 3: High-value extraction
        is_extraction, ext_confidence = self._check_value_extraction(tx)
        if is_extraction:
            reasons.append("high_value_extraction")
            max_confidence = max(max_confidence, ext_confidence)

        # Check 4: Unusual gas usage
        is_gas_anomaly, gas_confidence = self._check_gas_anomaly(tx)
        if is_gas_anomaly:
            reasons.append("gas_anomaly")
            max_confidence = max(max_confidence, gas_confidence)

        fired = len(reasons) > 0

        return SignalResult(
            signal_id=self.signal_id,
            fired=fired,
            confidence=max_confidence,
            metadata={
                "reasons": reasons,
                "checks_run": 4,
                "checks_fired": len(reasons),
            },
        )

    def _check_flash_loan(self, tx: TransactionData) -> tuple[bool, float]:
        """Detect flash loan patterns via function selector matching."""
        if tx.to is None or len(tx.data) < 4:
            return False, 0.0

        function_selector = tx.function_selector or tx.data[:4]

        # Direct flash loan call
        if function_selector in FLASH_LOAN_SELECTORS:
            return True, 0.85

        # Look for nested calls in calldata that contain flash loan selectors
        # (simplified — real impl would trace internal calls)
        data_hex = tx.data[4:].hex() if len(tx.data) > 4 else ""
        for selector in FLASH_LOAN_SELECTORS:
            if selector.hex() in data_hex:
                return True, 0.65

        return False, 0.0

    async def _check_reserve_spike(self, tx: TransactionData) -> tuple[bool, float]:
        """Check if this tx would cause a >20% reserve change for the target protocol."""
        if not tx.to or not self._cache:
            return False, 0.0

        # Look up cached reserves for this contract
        # Protocol name is derived from contract address (simplified)
        reserves = await self._cache.get_reserves("amm", tx.to.lower())
        if not reserves:
            return False, 0.0

        # Check if tx value represents a significant fraction of reserves
        reserve_total = sum(float(v) for v in reserves.values() if isinstance(v, (int, float)))
        if reserve_total == 0:
            return False, 0.0

        tx_value = tx.value / 1e18
        ratio = tx_value / reserve_total

        if ratio > RESERVE_SPIKE_RATIO:
            return True, min(0.9, 0.5 + ratio)

        return False, 0.0

    def _check_value_extraction(self, tx: TransactionData) -> tuple[bool, float]:
        """Detect unusually high value transfers."""
        if tx.value_eth > HIGH_VALUE_ETH:
            confidence = min(0.8, 0.3 + (tx.value_eth / 1000))
            return True, confidence
        return False, 0.0

    def _check_gas_anomaly(self, tx: TransactionData) -> tuple[bool, float]:
        """Detect unusually complex transactions (high gas limit)."""
        if tx.gas > SINGLE_TX_GAS_LIMIT:
            confidence = min(0.7, 0.3 + (tx.gas / 20_000_000))
            return True, confidence
        return False, 0.0
