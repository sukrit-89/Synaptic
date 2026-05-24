from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from synaptic.simulation.pis import PISComputer, PISSimulationResult, PIS_THRESHOLD


class TestPISComputation:
    """Test Protocol Impact Score computation logic."""

    @pytest.mark.asyncio
    async def test_pis_below_threshold(self):
        """TVL drops 5% — below 15% threshold."""
        mock_pool = MagicMock()
        mock_fork = MagicMock()
        mock_fork.url = "http://localhost:8546"
        mock_fork.in_use = False

        mock_pool.acquire = AsyncMock(return_value=mock_fork)
        mock_pool.release = AsyncMock()

        pis = PISComputer(mock_pool)

        # Mock the HTTP calls to return TVL values
        with patch("synaptic.simulation.pis.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock()

            # TVL before: 100 ETH, TVL after: 95 ETH (5% drop)
            tvl_responses = [
                MagicMock(json=MagicMock(return_value={"result": hex(100 * 10**18)})),
                MagicMock(json=MagicMock(return_value={"result": {"from": "0xdead", "to": "0xprotocol", "input": "0x", "value": "0x0", "gas": "0x5208", "gasPrice": "0x0"}})),
                MagicMock(json=MagicMock(return_value={"result": "0x0"})),
                MagicMock(json=MagicMock(return_value={"result": hex(95 * 10**18)})),
            ]
            mock_client.post = AsyncMock(side_effect=tvl_responses)

            result = await pis.compute("0xhash", "0xprotocol")

        assert isinstance(result, PISSimulationResult)
        # PIS should be below threshold
        assert result.pis < PIS_THRESHOLD
        assert result.threshold_exceeded is False

    def test_pis_threshold_constant(self):
        assert PIS_THRESHOLD == 0.15

    def test_pis_result_fields(self):
        result = PISSimulationResult(
            tvl_before=100.0,
            tvl_after=50.0,
            pis=0.5,
            threshold_exceeded=True,
            tx_hash="0xabc",
            fork_url="http://localhost:8546",
        )

        assert result.tvl_before == 100.0
        assert result.tvl_after == 50.0
        assert result.pis == 0.5
        assert result.threshold_exceeded is True
        assert result.error is None

    def test_pis_result_with_error(self):
        result = PISSimulationResult(
            tvl_before=0,
            tvl_after=0,
            pis=0,
            threshold_exceeded=False,
            tx_hash="0xabc",
            fork_url="http://localhost:8546",
            error="fork crashed",
        )

        assert result.error == "fork crashed"
        assert result.threshold_exceeded is False
