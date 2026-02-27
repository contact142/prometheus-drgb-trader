"""Guardian Bridge: the core DRGB orchestrator.

Computes convergence/divergence scores, bridge tension,
and guardian signals by comparing two reality streams.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any

from .convergence import ConvergenceStrategy, DefaultConvergenceStrategy
from .reality_stream import RealityStreamA, RealityStreamB, StrategySignal, TickData


class GuardianSignal(str, Enum):
    """Discrete guardian state signals."""

    SAFE = "SAFE"
    CAUTION = "CAUTION"
    DANGER = "DANGER"
    OPPORTUNITY = "OPPORTUNITY"


class GuardianBridge:
    """Dual Reality Guardian Bridge.

    Continuously compares market truth (StreamA) with strategic models (StreamB)
    and produces convergence, divergence, tension, and guardian signals.

    Args:
        convergence_strategy: Pluggable convergence computation. Defaults to
            DefaultConvergenceStrategy.
        tension_window: Number of recent divergence values for tension calc.
        safe_threshold: Convergence above this -> SAFE.
        caution_threshold: Convergence below this -> CAUTION.
        danger_threshold: Convergence below this -> DANGER.
        opportunity_tension: Tension magnitude above this -> OPPORTUNITY.
    """

    def __init__(
        self,
        convergence_strategy: ConvergenceStrategy | None = None,
        tension_window: int = 20,
        safe_threshold: float = 0.7,
        caution_threshold: float = 0.4,
        danger_threshold: float = 0.2,
        opportunity_tension: float = 0.05,
        stream_a_window: int = 100,
        stream_b_window: int = 50,
    ) -> None:
        self.stream_a = RealityStreamA(window_size=stream_a_window)
        self.stream_b = RealityStreamB(window_size=stream_b_window)
        self._convergence_strategy = convergence_strategy or DefaultConvergenceStrategy()
        self._divergence_history: deque[float] = deque(maxlen=tension_window)
        self._tension_history: deque[float] = deque(maxlen=tension_window)
        self.safe_threshold = safe_threshold
        self.caution_threshold = caution_threshold
        self.danger_threshold = danger_threshold
        self.opportunity_tension = opportunity_tension
        self._tick_count = 0

    def update(
        self,
        tick_data: TickData,
        strategy_signals: list[StrategySignal] | None = None,
    ) -> dict[str, Any]:
        """Process new data and return full DRGB state.

        Returns:
            Dict with keys: convergence, divergence, tension, signal,
            a_state, b_state, tick_count.
        """
        a_state = self.stream_a.update(tick_data)
        b_state = self.stream_b.update(strategy_signals or [])

        convergence = self._convergence_strategy.compute(a_state, b_state)
        divergence = 1.0 - convergence

        self._divergence_history.append(divergence)
        tension = self._compute_tension()
        self._tension_history.append(tension)

        signal = self._determine_signal(convergence, tension)
        self._tick_count += 1

        return {
            "convergence": convergence,
            "divergence": divergence,
            "tension": tension,
            "signal": signal,
            "a_state": a_state,
            "b_state": b_state,
            "tick_count": self._tick_count,
        }

    def _compute_tension(self) -> float:
        """Bridge tension: 2nd-derivative-style rate of divergence change.

        Uses finite differences on the divergence history.
        """
        hist = list(self._divergence_history)
        if len(hist) < 3:
            return 0.0

        # First derivative (rate of change)
        d1 = [hist[i] - hist[i - 1] for i in range(1, len(hist))]

        # Second derivative (acceleration)
        if len(d1) < 2:
            return d1[-1] if d1 else 0.0

        d2 = [d1[i] - d1[i - 1] for i in range(1, len(d1))]

        # Use recent average of 2nd derivative
        recent = d2[-min(5, len(d2)) :]
        return sum(recent) / len(recent)

    def _determine_signal(
        self, convergence: float, tension: float
    ) -> GuardianSignal:
        """Map convergence and tension to a discrete guardian signal."""
        # High tension with moderate convergence = opportunity
        if abs(tension) > self.opportunity_tension and convergence > self.caution_threshold:
            return GuardianSignal.OPPORTUNITY

        if convergence >= self.safe_threshold:
            return GuardianSignal.SAFE
        elif convergence >= self.caution_threshold:
            return GuardianSignal.CAUTION
        elif convergence >= self.danger_threshold:
            # Check if tension is accelerating toward danger
            if tension > 0:  # Divergence increasing
                return GuardianSignal.DANGER
            return GuardianSignal.CAUTION
        else:
            return GuardianSignal.DANGER

    @property
    def tick_count(self) -> int:
        return self._tick_count
