"""Strategy library with persistence.

Provides a base strategy interface and a file-backed library
for both human-created and agent-generated strategies.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class StrategyMetadata:
    """Metadata for a strategy."""

    strategy_id: str
    name: str
    origin: str = "human_created"  # human_created | agent_generated
    created_at: float = field(default_factory=time.time)
    parent_ids: list[str] = field(default_factory=list)
    generation: int = 0
    fitness_score: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0
    parameters: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


class BaseStrategy(ABC):
    """Abstract base for all trading strategies."""

    def __init__(self, strategy_id: str, params: dict[str, Any] | None = None) -> None:
        self.strategy_id = strategy_id
        self.params = params or {}

    @abstractmethod
    def generate_signal(
        self,
        market_data: dict[str, float],
        regime: str,
        drgb_state: dict[str, Any],
    ) -> dict[str, float]:
        """Generate a trading signal.

        Returns:
            Dict with 'direction' (-1 to 1) and 'confidence' (0 to 1).
        """
        ...

    @abstractmethod
    def get_params(self) -> dict[str, Any]:
        """Return current parameters."""
        ...

    @abstractmethod
    def set_params(self, params: dict[str, Any]) -> None:
        """Update parameters."""
        ...


class MomentumStrategy(BaseStrategy):
    """Simple momentum-based strategy (seed strategy)."""

    def __init__(
        self,
        strategy_id: str = "momentum_v1",
        params: dict[str, Any] | None = None,
    ) -> None:
        default_params = {
            "momentum_threshold": 0.001,
            "confidence_scale": 2.0,
            "regime_boost": {"TRENDING_STRONG_UP": 1.5, "TRENDING_STRONG_DOWN": 1.5},
        }
        if params:
            default_params.update(params)
        super().__init__(strategy_id, default_params)

    def generate_signal(
        self,
        market_data: dict[str, float],
        regime: str,
        drgb_state: dict[str, Any],
    ) -> dict[str, float]:
        momentum = market_data.get("momentum", 0.0)
        threshold = self.params["momentum_threshold"]

        if abs(momentum) < threshold:
            return {"direction": 0.0, "confidence": 0.1}

        direction = 1.0 if momentum > 0 else -1.0
        confidence = min(abs(momentum) * self.params["confidence_scale"] * 100, 1.0)

        # Regime boost
        boost = self.params.get("regime_boost", {}).get(regime, 1.0)
        confidence = min(confidence * boost, 1.0)

        # DRGB adjustment: reduce confidence when divergent
        convergence = drgb_state.get("convergence", 0.5)
        confidence *= (0.5 + 0.5 * convergence)

        return {"direction": direction, "confidence": confidence}

    def get_params(self) -> dict[str, Any]:
        return dict(self.params)

    def set_params(self, params: dict[str, Any]) -> None:
        self.params.update(params)


class MeanReversionStrategy(BaseStrategy):
    """Simple mean reversion strategy (seed strategy)."""

    def __init__(
        self,
        strategy_id: str = "mean_reversion_v1",
        params: dict[str, Any] | None = None,
    ) -> None:
        default_params = {
            "volatility_threshold": 0.01,
            "reversion_strength": 1.5,
        }
        if params:
            default_params.update(params)
        super().__init__(strategy_id, default_params)

    def generate_signal(
        self,
        market_data: dict[str, float],
        regime: str,
        drgb_state: dict[str, Any],
    ) -> dict[str, float]:
        momentum = market_data.get("momentum", 0.0)
        volatility = market_data.get("volatility", 0.0)

        if volatility < self.params["volatility_threshold"]:
            return {"direction": 0.0, "confidence": 0.1}

        # Bet against momentum (mean reversion)
        direction = -1.0 if momentum > 0 else 1.0
        confidence = min(
            abs(momentum) * self.params["reversion_strength"] * 100, 1.0
        )

        # Only works well in range/choppy regimes
        if "TRENDING" in regime:
            confidence *= 0.3
        elif "RANGE" in regime or "CHOPPY" in regime:
            confidence *= 1.2

        confidence = min(confidence, 1.0)
        convergence = drgb_state.get("convergence", 0.5)
        confidence *= (0.5 + 0.5 * convergence)

        return {"direction": direction, "confidence": confidence}

    def get_params(self) -> dict[str, Any]:
        return dict(self.params)

    def set_params(self, params: dict[str, Any]) -> None:
        self.params.update(params)


class StrategyLibrary:
    """File-backed strategy library.

    Persists strategy metadata to JSON. Strategy instances are
    created from metadata at runtime.
    """

    def __init__(self, path: str | Path = "data/strategies.json") -> None:
        self.path = Path(path)
        self._strategies: dict[str, StrategyMetadata] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            with open(self.path) as f:
                data = json.load(f)
            for sid, meta in data.items():
                self._strategies[sid] = StrategyMetadata(**meta)

    def save(self) -> None:
        """Persist to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {sid: asdict(meta) for sid, meta in self._strategies.items()}
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def register(self, meta: StrategyMetadata) -> None:
        """Register a strategy."""
        self._strategies[meta.strategy_id] = meta
        self.save()

    def get(self, strategy_id: str) -> StrategyMetadata | None:
        return self._strategies.get(strategy_id)

    def list_all(self) -> list[StrategyMetadata]:
        return list(self._strategies.values())

    def list_by_origin(self, origin: str) -> list[StrategyMetadata]:
        return [m for m in self._strategies.values() if m.origin == origin]

    def update_fitness(self, strategy_id: str, fitness: float) -> None:
        if strategy_id in self._strategies:
            self._strategies[strategy_id].fitness_score = fitness
            self.save()

    def top_n(self, n: int = 5) -> list[StrategyMetadata]:
        """Top N strategies by fitness."""
        return sorted(
            self._strategies.values(),
            key=lambda m: m.fitness_score,
            reverse=True,
        )[:n]
