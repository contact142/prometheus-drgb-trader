"""Reality stream implementations for DRGB.

RealityStreamA: Raw market truth (price, volume, microstructure).
RealityStreamB: Modeled/strategic reality (strategy signals, indicators).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TickData:
    """Single market tick / bar."""

    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: float | None = None
    ask: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategySignal:
    """Output from a strategy or indicator."""

    strategy_id: str
    timestamp: float
    direction: float  # -1.0 (strong sell) to +1.0 (strong buy)
    confidence: float  # 0.0 to 1.0
    extra: dict[str, Any] = field(default_factory=dict)


class RealityStreamA:
    """Raw market truth stream.

    Maintains a rolling window of market data and computes
    basic microstructure statistics.
    """

    def __init__(self, window_size: int = 100) -> None:
        self.window_size = window_size
        self._prices: deque[float] = deque(maxlen=window_size)
        self._volumes: deque[float] = deque(maxlen=window_size)
        self._spreads: deque[float] = deque(maxlen=window_size)
        self._returns: deque[float] = deque(maxlen=window_size)
        self._last_price: float | None = None

    def update(self, tick: TickData) -> dict[str, float]:
        """Ingest a tick and return current market state."""
        self._prices.append(tick.close)
        self._volumes.append(tick.volume)

        if tick.bid is not None and tick.ask is not None:
            self._spreads.append(tick.ask - tick.bid)

        if self._last_price is not None and self._last_price != 0:
            ret = (tick.close - self._last_price) / self._last_price
            self._returns.append(ret)
        self._last_price = tick.close

        return self.state()

    def state(self) -> dict[str, float]:
        """Current market microstructure state."""
        prices = list(self._prices)
        returns = list(self._returns)
        volumes = list(self._volumes)

        n = len(prices)
        if n == 0:
            return {
                "price": 0.0,
                "volatility": 0.0,
                "volume_mean": 0.0,
                "spread_mean": 0.0,
                "momentum": 0.0,
                "trend_strength": 0.0,
            }

        price = prices[-1]
        vol = _std(returns) if len(returns) > 1 else 0.0
        vol_mean = sum(volumes) / len(volumes) if volumes else 0.0
        spread_mean = (
            sum(self._spreads) / len(self._spreads) if self._spreads else 0.0
        )

        # Simple momentum: mean of recent returns
        momentum = sum(returns[-20:]) / max(len(returns[-20:]), 1) if returns else 0.0

        # Trend strength: ratio of net move to total path
        if n >= 2:
            net_move = abs(prices[-1] - prices[0])
            total_path = sum(abs(prices[i] - prices[i - 1]) for i in range(1, n))
            trend_strength = net_move / total_path if total_path > 0 else 0.0
        else:
            trend_strength = 0.0

        return {
            "price": price,
            "volatility": vol,
            "volume_mean": vol_mean,
            "spread_mean": spread_mean,
            "momentum": momentum,
            "trend_strength": trend_strength,
        }


class RealityStreamB:
    """Strategic / modeled reality stream.

    Aggregates signals from multiple strategies and indicators
    into a unified strategic state.
    """

    def __init__(self, window_size: int = 50) -> None:
        self.window_size = window_size
        self._signals: dict[str, deque[StrategySignal]] = {}
        self._latest: dict[str, StrategySignal] = {}

    def update(self, signals: list[StrategySignal]) -> dict[str, float]:
        """Ingest strategy signals and return strategic state."""
        for sig in signals:
            if sig.strategy_id not in self._signals:
                self._signals[sig.strategy_id] = deque(maxlen=self.window_size)
            self._signals[sig.strategy_id].append(sig)
            self._latest[sig.strategy_id] = sig
        return self.state()

    def state(self) -> dict[str, float]:
        """Aggregated strategic state."""
        if not self._latest:
            return {
                "consensus_direction": 0.0,
                "consensus_confidence": 0.0,
                "signal_agreement": 0.0,
                "num_strategies": 0,
            }

        directions = []
        confidences = []
        for sig in self._latest.values():
            directions.append(sig.direction * sig.confidence)
            confidences.append(sig.confidence)

        n = len(directions)
        consensus_dir = sum(directions) / n
        consensus_conf = sum(confidences) / n

        # Agreement: how much strategies agree (1.0 = all same direction)
        if n > 1:
            signs = [1 if d >= 0 else -1 for d in directions]
            agreement = abs(sum(signs)) / n
        else:
            agreement = 1.0

        return {
            "consensus_direction": consensus_dir,
            "consensus_confidence": consensus_conf,
            "signal_agreement": agreement,
            "num_strategies": float(n),
        }


def _std(values: list[float]) -> float:
    """Standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return var**0.5
