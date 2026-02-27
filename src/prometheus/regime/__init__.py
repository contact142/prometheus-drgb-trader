"""Regime Detection Engine.

Classifies market regimes using volatility analysis,
trend detection, and DRGB tension integration.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any


class Regime(str, Enum):
    """Market regime labels."""

    TRENDING_STRONG_UP = "TRENDING_STRONG_UP"
    TRENDING_WEAK_UP = "TRENDING_WEAK_UP"
    TRENDING_STRONG_DOWN = "TRENDING_STRONG_DOWN"
    TRENDING_WEAK_DOWN = "TRENDING_WEAK_DOWN"
    RANGE_TIGHT = "RANGE_TIGHT"
    RANGE_WIDE = "RANGE_WIDE"
    VOLATILE_CHOPPY = "VOLATILE_CHOPPY"
    BREAKOUT_IMMINENT = "BREAKOUT_IMMINENT"
    REGIME_TRANSITION = "REGIME_TRANSITION"


class RegimeDetector:
    """Multi-method regime classifier.

    Methods:
    1. Volatility-based: rolling std of returns -> vol regime.
    2. Trend-based: momentum + trend strength -> trend regime.
    3. DRGB tension: high tension -> REGIME_TRANSITION override.

    Args:
        vol_window: Window for volatility calculation.
        trend_window: Window for trend calculation.
        tension_threshold: DRGB tension above this -> REGIME_TRANSITION.
        vol_low: Threshold below which volatility is "low".
        vol_high: Threshold above which volatility is "high".
        trend_strong: Momentum magnitude above this -> "strong" trend.
        trend_weak: Momentum magnitude above this but below strong -> "weak" trend.
    """

    def __init__(
        self,
        vol_window: int = 20,
        trend_window: int = 20,
        tension_threshold: float = 0.03,
        vol_low: float = 0.005,
        vol_high: float = 0.02,
        trend_strong: float = 0.003,
        trend_weak: float = 0.001,
        breakout_vol_ratio: float = 0.4,
    ) -> None:
        self.vol_window = vol_window
        self.trend_window = trend_window
        self.tension_threshold = tension_threshold
        self.vol_low = vol_low
        self.vol_high = vol_high
        self.trend_strong = trend_strong
        self.trend_weak = trend_weak
        self.breakout_vol_ratio = breakout_vol_ratio
        self._returns: deque[float] = deque(maxlen=max(vol_window, trend_window) * 2)
        self._regimes: deque[Regime] = deque(maxlen=50)

    def detect(
        self,
        market_data: dict[str, float],
        drgb_output: dict[str, Any] | None = None,
    ) -> Regime:
        """Classify current market regime.

        Args:
            market_data: Dict with keys from RealityStreamA.state()
                (price, volatility, momentum, trend_strength, etc.).
            drgb_output: Optional dict from GuardianBridge.update().

        Returns:
            Regime enum value.
        """
        # Check DRGB tension override first
        if drgb_output:
            tension = abs(drgb_output.get("tension", 0.0))
            if tension > self.tension_threshold:
                regime = Regime.REGIME_TRANSITION
                self._regimes.append(regime)
                return regime

        volatility = market_data.get("volatility", 0.0)
        momentum = market_data.get("momentum", 0.0)
        trend_strength = market_data.get("trend_strength", 0.0)

        regime = self._classify(volatility, momentum, trend_strength)
        self._regimes.append(regime)
        return regime

    def _classify(
        self, volatility: float, momentum: float, trend_strength: float
    ) -> Regime:
        """Core classification logic."""
        abs_mom = abs(momentum)

        # Check for breakout: very low volatility with building tension
        if volatility < self.vol_low and trend_strength < self.breakout_vol_ratio:
            return Regime.BREAKOUT_IMMINENT

        # High volatility, low trend = choppy
        if volatility > self.vol_high and trend_strength < 0.3:
            return Regime.VOLATILE_CHOPPY

        # Trending regimes
        if abs_mom > self.trend_strong:
            if momentum > 0:
                return Regime.TRENDING_STRONG_UP
            else:
                return Regime.TRENDING_STRONG_DOWN

        if abs_mom > self.trend_weak:
            if momentum > 0:
                return Regime.TRENDING_WEAK_UP
            else:
                return Regime.TRENDING_WEAK_DOWN

        # Range regimes
        if volatility < self.vol_low:
            return Regime.RANGE_TIGHT
        elif volatility > self.vol_high:
            return Regime.RANGE_WIDE
        else:
            return Regime.RANGE_TIGHT

    @property
    def recent_regimes(self) -> list[Regime]:
        """Recent regime history."""
        return list(self._regimes)

    def regime_stability(self, lookback: int = 10) -> float:
        """How stable the regime has been. 1.0 = same regime throughout."""
        recent = list(self._regimes)[-lookback:]
        if not recent:
            return 1.0
        most_common = max(set(recent), key=recent.count)
        return recent.count(most_common) / len(recent)
