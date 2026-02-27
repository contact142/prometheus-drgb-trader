"""Pluggable convergence strategies for the Guardian Bridge.

The convergence strategy computes how well RealityStreamA (market truth)
and RealityStreamB (strategic models) agree with each other.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Protocol


class ConvergenceStrategy(Protocol):
    """Protocol for convergence computation."""

    def compute(
        self, a_state: dict[str, float], b_state: dict[str, float]
    ) -> float:
        """Return convergence score in [0, 1]. 1 = perfect alignment."""
        ...


class DefaultConvergenceStrategy:
    """Default convergence: weighted comparison of direction alignment and volatility fit.

    Compares:
    - Market momentum vs strategy consensus direction.
    - Market trend strength vs strategy agreement.
    - Penalizes high volatility when strategies are confident.
    """

    def __init__(
        self,
        direction_weight: float = 0.5,
        agreement_weight: float = 0.3,
        volatility_weight: float = 0.2,
    ) -> None:
        self.direction_weight = direction_weight
        self.agreement_weight = agreement_weight
        self.volatility_weight = volatility_weight

    def compute(
        self, a_state: dict[str, float], b_state: dict[str, float]
    ) -> float:
        """Compute convergence score [0, 1]."""
        # Direction alignment: do market momentum and strategy consensus agree?
        momentum = a_state.get("momentum", 0.0)
        consensus = b_state.get("consensus_direction", 0.0)

        # Both normalized roughly to [-1, 1] range
        # Alignment = 1 when same sign and magnitude, 0 when opposite
        if abs(momentum) < 1e-10 and abs(consensus) < 1e-10:
            direction_score = 1.0  # Both neutral = aligned
        else:
            # Cosine-like: product of signs, scaled by magnitudes
            mom_norm = math.tanh(momentum * 100)  # Scale small returns to [-1,1]
            direction_score = (1.0 + mom_norm * consensus) / 2.0

        # Agreement match: high strategy agreement + strong trend = convergent
        trend_strength = a_state.get("trend_strength", 0.0)
        signal_agreement = b_state.get("signal_agreement", 0.0)
        agreement_score = 1.0 - abs(trend_strength - signal_agreement)

        # Volatility penalty: high vol + high confidence = divergent
        volatility = a_state.get("volatility", 0.0)
        confidence = b_state.get("consensus_confidence", 0.0)
        vol_scaled = min(volatility * 100, 1.0)  # Scale to [0,1]
        vol_score = 1.0 - (vol_scaled * confidence)
        vol_score = max(0.0, min(1.0, vol_score))

        # Weighted combination
        score = (
            self.direction_weight * direction_score
            + self.agreement_weight * agreement_score
            + self.volatility_weight * vol_score
        )
        return max(0.0, min(1.0, score))
