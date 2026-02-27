"""Auto-Optimizer: DRGB-aware continuous parameter optimization.

Supports three sweep levels:
- Micro: tiny nudges every few minutes.
- Meso: moderate exploration every few hours.
- Macro: GA-style evolution daily.

Fitness includes DRGB divergence-alpha bonus and anti-overfitting measures.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class SweepLevel(str, Enum):
    MICRO = "MICRO"
    MESO = "MESO"
    MACRO = "MACRO"


@dataclass
class OptimizationResult:
    """Result of an optimization run."""

    best_params: dict[str, Any]
    fitness: float
    sweep_level: SweepLevel
    iterations: int
    metadata: dict[str, Any]


class DRGBFitness:
    """DRGB-enhanced fitness function.

    Base: Sortino ratio (risk-adjusted compounded return).
    Penalties: max drawdown.
    Bonuses: regime consistency, DRGB divergence-alpha.
    """

    def __init__(
        self,
        drawdown_penalty_weight: float = 2.0,
        regime_consistency_bonus: float = 0.5,
        divergence_alpha_bonus: float = 0.3,
    ) -> None:
        self.drawdown_penalty_weight = drawdown_penalty_weight
        self.regime_consistency_bonus = regime_consistency_bonus
        self.divergence_alpha_bonus = divergence_alpha_bonus

    def evaluate(
        self,
        returns: list[float],
        drawdowns: list[float],
        regime_consistency: float,
        drgb_divergence_alpha: float,
    ) -> float:
        """Compute fitness score.

        Args:
            returns: List of period returns.
            drawdowns: List of drawdown values (positive = loss).
            regime_consistency: 0-1 how consistent regime was.
            drgb_divergence_alpha: Alpha generated during divergence.

        Returns:
            Fitness score (higher is better).
        """
        if not returns:
            return -999.0

        # Sortino ratio
        mean_ret = sum(returns) / len(returns)
        downside = [r for r in returns if r < 0]
        if downside and len(downside) > 1:
            downside_std = (
                sum(r**2 for r in downside) / len(downside)
            ) ** 0.5
            sortino = mean_ret / downside_std if downside_std > 0 else mean_ret * 10
        else:
            sortino = mean_ret * 10  # No downside = great

        # Max drawdown penalty
        max_dd = max(drawdowns) if drawdowns else 0.0
        dd_penalty = max_dd * self.drawdown_penalty_weight

        # Bonuses
        regime_bonus = regime_consistency * self.regime_consistency_bonus
        div_bonus = drgb_divergence_alpha * self.divergence_alpha_bonus

        return sortino - dd_penalty + regime_bonus + div_bonus


class AutoOptimizer:
    """Continuous parameter optimizer with three sweep levels.

    Can run offline (backtest mode) or online (live).

    PLUG-IN POINT: Replace sweep methods with Bayesian optimization,
    CMA-ES, or other advanced methods.
    """

    def __init__(
        self,
        fitness_fn: DRGBFitness | None = None,
        micro_perturbation: float = 0.02,
        meso_perturbation: float = 0.10,
        macro_population: int = 20,
    ) -> None:
        self.fitness_fn = fitness_fn or DRGBFitness()
        self.micro_perturbation = micro_perturbation
        self.meso_perturbation = meso_perturbation
        self.macro_population = macro_population

    def micro_sweep(
        self,
        params: dict[str, Any],
        eval_fn: Callable[[dict[str, Any]], float],
        iterations: int = 10,
    ) -> OptimizationResult:
        """Tiny nudges to parameters."""
        best_params = dict(params)
        best_fitness = eval_fn(best_params)

        for _ in range(iterations):
            candidate = self._perturb(best_params, self.micro_perturbation)
            fitness = eval_fn(candidate)
            if fitness > best_fitness:
                best_fitness = fitness
                best_params = candidate

        return OptimizationResult(
            best_params=best_params,
            fitness=best_fitness,
            sweep_level=SweepLevel.MICRO,
            iterations=iterations,
            metadata={},
        )

    def meso_sweep(
        self,
        params: dict[str, Any],
        eval_fn: Callable[[dict[str, Any]], float],
        iterations: int = 50,
    ) -> OptimizationResult:
        """Moderate exploration."""
        best_params = dict(params)
        best_fitness = eval_fn(best_params)

        for _ in range(iterations):
            candidate = self._perturb(best_params, self.meso_perturbation)
            fitness = eval_fn(candidate)
            if fitness > best_fitness:
                best_fitness = fitness
                best_params = candidate

        return OptimizationResult(
            best_params=best_params,
            fitness=best_fitness,
            sweep_level=SweepLevel.MESO,
            iterations=iterations,
            metadata={},
        )

    def macro_sweep(
        self,
        params: dict[str, Any],
        eval_fn: Callable[[dict[str, Any]], float],
        generations: int = 10,
    ) -> OptimizationResult:
        """GA-style evolution: population-based search."""
        population = [
            self._perturb(params, self.meso_perturbation * 2)
            for _ in range(self.macro_population)
        ]
        population.append(dict(params))  # Keep original

        best_params = dict(params)
        best_fitness = eval_fn(best_params)

        for _gen in range(generations):
            scored = [(p, eval_fn(p)) for p in population]
            scored.sort(key=lambda x: x[1], reverse=True)

            if scored[0][1] > best_fitness:
                best_fitness = scored[0][1]
                best_params = scored[0][0]

            # Select top half
            survivors = [p for p, _ in scored[: len(scored) // 2]]

            # Breed next generation
            population = list(survivors)
            while len(population) < self.macro_population:
                parent_a = random.choice(survivors)
                parent_b = random.choice(survivors)
                child = self._crossover(parent_a, parent_b)
                child = self._perturb(child, self.micro_perturbation)
                population.append(child)

        return OptimizationResult(
            best_params=best_params,
            fitness=best_fitness,
            sweep_level=SweepLevel.MACRO,
            iterations=generations * self.macro_population,
            metadata={"generations": generations},
        )

    def _perturb(
        self, params: dict[str, Any], scale: float
    ) -> dict[str, Any]:
        """Random perturbation of numeric parameters."""
        result = {}
        for key, value in params.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                noise = random.gauss(0, scale) * abs(value) if value != 0 else random.gauss(0, scale * 0.01)
                result[key] = value + noise
            else:
                result[key] = value
        return result

    def _crossover(
        self, a: dict[str, Any], b: dict[str, Any]
    ) -> dict[str, Any]:
        """Uniform crossover between two parameter sets."""
        result = {}
        for key in set(list(a.keys()) + list(b.keys())):
            if key in a and key in b:
                result[key] = a[key] if random.random() < 0.5 else b[key]
            elif key in a:
                result[key] = a[key]
            else:
                result[key] = b[key]
        return result
