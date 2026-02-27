"""Tests for the Regime Detection Engine."""

import pytest
from prometheus.regime import Regime, RegimeDetector


class TestRegimeDetector:
    def test_default_init(self):
        detector = RegimeDetector()
        assert detector.tension_threshold == 0.03

    def test_trending_strong_up(self):
        detector = RegimeDetector(trend_strong=0.003)
        market = {"volatility": 0.01, "momentum": 0.005, "trend_strength": 0.7}
        regime = detector.detect(market)
        assert regime == Regime.TRENDING_STRONG_UP

    def test_trending_strong_down(self):
        detector = RegimeDetector(trend_strong=0.003)
        market = {"volatility": 0.01, "momentum": -0.005, "trend_strength": 0.7}
        regime = detector.detect(market)
        assert regime == Regime.TRENDING_STRONG_DOWN

    def test_volatile_choppy(self):
        detector = RegimeDetector(vol_high=0.02)
        market = {"volatility": 0.03, "momentum": 0.0001, "trend_strength": 0.1}
        regime = detector.detect(market)
        assert regime == Regime.VOLATILE_CHOPPY

    def test_range_tight(self):
        detector = RegimeDetector(vol_low=0.005, trend_weak=0.001)
        market = {"volatility": 0.003, "momentum": 0.0005, "trend_strength": 0.5}
        regime = detector.detect(market)
        assert regime in (Regime.RANGE_TIGHT, Regime.BREAKOUT_IMMINENT)

    def test_drgb_tension_override(self):
        detector = RegimeDetector(tension_threshold=0.03)
        market = {"volatility": 0.01, "momentum": 0.005, "trend_strength": 0.7}
        drgb = {"tension": 0.05}  # Above threshold
        regime = detector.detect(market, drgb)
        assert regime == Regime.REGIME_TRANSITION

    def test_drgb_tension_below_threshold(self):
        detector = RegimeDetector(tension_threshold=0.03)
        market = {"volatility": 0.01, "momentum": 0.005, "trend_strength": 0.7}
        drgb = {"tension": 0.01}  # Below threshold
        regime = detector.detect(market, drgb)
        assert regime != Regime.REGIME_TRANSITION

    def test_regime_stability(self):
        detector = RegimeDetector()
        market = {"volatility": 0.01, "momentum": 0.005, "trend_strength": 0.7}
        for _ in range(10):
            detector.detect(market)
        assert detector.regime_stability(10) >= 0.5

    def test_recent_regimes(self):
        detector = RegimeDetector()
        market = {"volatility": 0.01, "momentum": 0.005, "trend_strength": 0.7}
        for _ in range(5):
            detector.detect(market)
        assert len(detector.recent_regimes) == 5
