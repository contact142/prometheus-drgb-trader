"""Sub-agents for the PROMETHEUS multi-agent brain.

Each agent has a clear interface designed for later swap-in of
true RL implementations (e.g., PPO). Current implementations use
simple heuristic policies.
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from ..regime import Regime


class EvolutionPhase(str, Enum):
    """Strategy evolution phases."""

    IMITATION = "IMITATION"
    OPTIMIZATION = "OPTIMIZATION"
    RECOMBINATION = "RECOMBINATION"
    INVENTION = "INVENTION"
    MASTERY = "MASTERY"


# ─── Strategy Selector ──────────────────────────────────────────────


class StrategySelectorAgent:
    """Selects which strategy to run based on regime and DRGB state.

    Heuristic policy: pick the strategy with highest fitness for the
    current regime. Later: swap in RL policy (PPO/DQN).

    PLUG-IN POINT: Replace `select()` body with RL inference.
    """

    def __init__(self, regime_strategy_map: dict[str, str] | None = None) -> None:
        self._regime_map = regime_strategy_map or {
            "TRENDING_STRONG_UP": "momentum_v1",
            "TRENDING_WEAK_UP": "momentum_v1",
            "TRENDING_STRONG_DOWN": "momentum_v1",
            "TRENDING_WEAK_DOWN": "momentum_v1",
            "RANGE_TIGHT": "mean_reversion_v1",
            "RANGE_WIDE": "mean_reversion_v1",
            "VOLATILE_CHOPPY": "mean_reversion_v1",
            "BREAKOUT_IMMINENT": "momentum_v1",
            "REGIME_TRANSITION": "mean_reversion_v1",
        }

    def select(
        self,
        regime: Regime,
        drgb_state: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Select strategy ID for current conditions.

        Args:
            regime: Current market regime.
            drgb_state: Current DRGB output.
            history: Recent trade/performance history.

        Returns:
            Strategy ID string.
        """
        return self._regime_map.get(regime.value, "momentum_v1")


# ─── Parameter Tuner ─────────────────────────────────────────────────


class ParameterTunerAgent:
    """Tunes strategy parameters based on performance.

    Heuristic: small random perturbations scaled by DRGB convergence.
    PLUG-IN POINT: Replace with gradient-based or RL tuning.
    """

    def __init__(self, perturbation_scale: float = 0.05) -> None:
        self.perturbation_scale = perturbation_scale

    def tune(
        self,
        strategy_config: dict[str, Any],
        drgb_state: dict[str, Any],
        recent_performance: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Return tuned parameters.

        Only perturbs numeric parameters. Scale of perturbation
        is reduced when DRGB shows high convergence (things are working).
        """
        convergence = drgb_state.get("convergence", 0.5)
        # Less tuning when things are working well
        scale = self.perturbation_scale * (1.0 - convergence * 0.5)

        tuned = {}
        for key, value in strategy_config.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                noise = random.gauss(0, scale) * abs(value) if value != 0 else random.gauss(0, scale * 0.01)
                tuned[key] = value + noise
            else:
                tuned[key] = value
        return tuned


# ─── Risk Guardian ───────────────────────────────────────────────────


class RiskGuardianAgent:
    """Approves or rejects trades based on risk limits.

    Heuristic: hard limits on drawdown, daily loss, position size.
    PLUG-IN POINT: Replace with learned risk model.
    """

    def __init__(
        self,
        max_daily_loss_pct: float = 0.02,
        max_weekly_loss_pct: float = 0.05,
        max_drawdown_pct: float = 0.10,
        max_position_pct: float = 0.10,
        danger_scale: float = 0.5,
    ) -> None:
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_weekly_loss_pct = max_weekly_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_position_pct = max_position_pct
        self.danger_scale = danger_scale

    def approve(
        self,
        strategy_id: str,
        params: dict[str, Any],
        size_fraction: float,
        drgb_state: dict[str, Any],
        risk_state: dict[str, float] | None = None,
    ) -> bool:
        """Approve or reject a proposed trade.

        Args:
            strategy_id: Which strategy is proposing.
            params: Strategy parameters.
            size_fraction: Proposed position size as fraction of equity.
            drgb_state: Current DRGB output.
            risk_state: Current risk metrics (daily_pnl, weekly_pnl,
                drawdown, etc.).

        Returns:
            True if trade is approved.
        """
        signal = drgb_state.get("signal", "SAFE")

        # Hard reject in DANGER
        if signal == "DANGER":
            return False

        # Check position size
        effective_max = self.max_position_pct
        if signal == "CAUTION":
            effective_max *= self.danger_scale

        if size_fraction > effective_max:
            return False

        # Check risk state limits
        if risk_state:
            if abs(risk_state.get("daily_pnl_pct", 0.0)) > self.max_daily_loss_pct:
                return False
            if abs(risk_state.get("weekly_pnl_pct", 0.0)) > self.max_weekly_loss_pct:
                return False
            if risk_state.get("drawdown_pct", 0.0) > self.max_drawdown_pct:
                return False

        return True


# ─── Strategy Inventor ───────────────────────────────────────────────


class StrategyInventorAgent:
    """Evolves and invents new strategies over time.

    Phases:
    - IMITATION: Copy and slightly modify existing strategies.
    - OPTIMIZATION: Fine-tune parameters of existing strategies.
    - RECOMBINATION: Combine parameters from multiple strategies.
    - INVENTION: Generate new strategy variants.
    - MASTERY: Prune weak strategies, refine the best.

    PLUG-IN POINT: Replace with evolutionary/neuroevolution algorithms.
    """

    def __init__(self) -> None:
        self._generation = 0

    def evolve_strategies(
        self,
        strategy_library: list[dict[str, Any]],
        drgb_data: dict[str, Any],
        phase: EvolutionPhase,
    ) -> list[dict[str, Any]]:
        """Evolve the strategy library based on current phase.

        Args:
            strategy_library: List of strategy metadata dicts.
            drgb_data: Recent DRGB statistics.
            phase: Current evolution phase.

        Returns:
            Updated strategy library (may include new entries).
        """
        if phase == EvolutionPhase.IMITATION:
            return self._imitate(strategy_library)
        elif phase == EvolutionPhase.OPTIMIZATION:
            return self._optimize(strategy_library)
        elif phase == EvolutionPhase.RECOMBINATION:
            return self._recombine(strategy_library)
        elif phase == EvolutionPhase.INVENTION:
            return self._invent(strategy_library)
        elif phase == EvolutionPhase.MASTERY:
            return self._master(strategy_library)
        return strategy_library

    def _imitate(self, library: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Copy top strategies with small mutations."""
        if not library:
            return library
        top = sorted(library, key=lambda s: s.get("fitness_score", 0), reverse=True)
        # Clone top strategy with slight parameter mutation
        if top:
            clone = dict(top[0])
            clone["strategy_id"] = f"clone_{self._generation}"
            clone["origin"] = "agent_generated"
            clone["generation"] = self._generation
            self._generation += 1
            library.append(clone)
        return library

    def _optimize(self, library: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Stub: would run parameter optimization on each strategy."""
        return library

    def _recombine(self, library: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Stub: would crossover parameters between strategies."""
        return library

    def _invent(self, library: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Stub: would generate novel strategy structures."""
        return library

    def _master(self, library: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prune weakest strategies."""
        if len(library) <= 2:
            return library
        return sorted(
            library, key=lambda s: s.get("fitness_score", 0), reverse=True
        )[: max(len(library) // 2, 2)]


# ─── Compounding Agent ───────────────────────────────────────────────


class CompoundingAgent:
    """Calculates position size using regime + DRGB-dependent Kelly fraction.

    PLUG-IN POINT: Replace with learned sizing model.
    """

    def __init__(
        self,
        base_kelly_fraction: float = 0.25,
        max_fraction: float = 0.10,
        min_fraction: float = 0.01,
    ) -> None:
        self.base_kelly_fraction = base_kelly_fraction
        self.max_fraction = max_fraction
        self.min_fraction = min_fraction

    def calculate_size(
        self,
        drgb_state: dict[str, Any],
        regime: Regime,
        equity_curve_state: dict[str, float] | None = None,
    ) -> float:
        """Calculate position size as fraction of equity.

        Scales base Kelly fraction by:
        - DRGB convergence (higher = more confident = bigger)
        - Guardian signal (DANGER = zero, OPPORTUNITY = boost)
        - Regime stability (trending = more, choppy = less)
        """
        signal = drgb_state.get("signal", "CAUTION")
        convergence = drgb_state.get("convergence", 0.5)

        if signal == "DANGER":
            return 0.0

        # Base fraction scaled by convergence
        fraction = self.base_kelly_fraction * convergence

        # Signal multiplier
        signal_mult = {
            "SAFE": 1.0,
            "CAUTION": 0.5,
            "OPPORTUNITY": 1.3,
            "DANGER": 0.0,
        }.get(signal, 0.5)

        fraction *= signal_mult

        # Regime multiplier
        regime_mult = {
            Regime.TRENDING_STRONG_UP: 1.2,
            Regime.TRENDING_STRONG_DOWN: 1.2,
            Regime.TRENDING_WEAK_UP: 1.0,
            Regime.TRENDING_WEAK_DOWN: 1.0,
            Regime.RANGE_TIGHT: 0.8,
            Regime.RANGE_WIDE: 0.6,
            Regime.VOLATILE_CHOPPY: 0.4,
            Regime.BREAKOUT_IMMINENT: 0.9,
            Regime.REGIME_TRANSITION: 0.3,
        }.get(regime, 0.5)

        fraction *= regime_mult

        return max(self.min_fraction, min(self.max_fraction, fraction))
