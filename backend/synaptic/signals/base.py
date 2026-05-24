from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from synaptic.mempool.parser import TransactionData


@dataclass(frozen=True, slots=True)
class SignalResult:
    """Result from evaluating a single signal against a transaction."""

    signal_id: str  # e.g. "heuristics", "anomaly", "simulation", "invariant"
    fired: bool  # True if this signal considers the tx suspicious
    confidence: float  # 0.0 to 1.0
    metadata: dict[str, Any] = field(default_factory=dict)  # signal-specific details

    @property
    def label(self) -> str:
        return f"{self.signal_id}:{'FIRE' if self.fired else 'OK'}"


class Signal(abc.ABC):
    """Abstract base class for all Synaptic signals.

    Each signal evaluates a transaction independently and returns a SignalResult.
    The consensus engine aggregates results from all signals.
    """

    @property
    @abc.abstractmethod
    def signal_id(self) -> str:
        """Unique identifier for this signal."""
        ...

    @abc.abstractmethod
    async def evaluate(self, tx: TransactionData) -> SignalResult:
        """Evaluate a transaction and return a signal result."""
        ...

    def __repr__(self) -> str:
        return f"<Signal:{self.signal_id}>"
