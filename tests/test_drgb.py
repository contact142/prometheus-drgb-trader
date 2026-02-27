"""Tests for the Dual Reality Guardian Bridge."""

import pytest
from prometheus.drgb import GuardianBridge, GuardianSignal, RealityStreamA, RealityStreamB
from prometheus.drgb.convergence import DefaultConvergenceStrategy
from prometheus.drgb.reality_stream import StrategySignal, TickData


def _make_tick(close: float = 100.0, volume: float = 1.0, bid: float = 99.9, ask: float = 100.1) -> TickData:
    return TickData(
        timestamp=1000.0, open=close, high=close * 1.01,
        low=close * 0.99, close=close, volume=volume,
        bid=bid, ask=ask,
    )


def _make_signal(direction: float = 0.5, confidence: float = 0.8) -> StrategySignal:
    return StrategySignal(
        strategy_id="test_strat", timestamp=1000.0,
        direction=direction, confidence=confidence,
    )


class TestRealityStreamA:
    def test_empty_state(self):
        stream = RealityStreamA()
        state = stream.state()
        assert state["price"] == 0.0
        assert state["volatility"] == 0.0

    def test_single_tick(self):
        stream = RealityStreamA()
        state = stream.update(_make_tick(100.0))
        assert state["price"] == 100.0

    def test_volatility_increases_with_varying_prices(self):
        stream = RealityStreamA()
        prices = [100, 105, 95, 110, 90, 115, 85]
        for p in prices:
            state = stream.update(_make_tick(p))
        assert state["volatility"] > 0

    def test_momentum_positive(self):
        stream = RealityStreamA()
        for p in [100, 101, 102, 103, 104, 105]:
            state = stream.update(_make_tick(p))
        assert state["momentum"] > 0

    def test_trend_strength(self):
        stream = RealityStreamA()
        # Strong trend: monotonic increase
        for p in range(100, 120):
            state = stream.update(_make_tick(float(p)))
        assert state["trend_strength"] > 0.5


class TestRealityStreamB:
    def test_empty_state(self):
        stream = RealityStreamB()
        state = stream.state()
        assert state["consensus_direction"] == 0.0
        assert state["num_strategies"] == 0

    def test_single_signal(self):
        stream = RealityStreamB()
        state = stream.update([_make_signal(0.8, 0.9)])
        assert state["consensus_direction"] > 0
        assert state["num_strategies"] == 1.0

    def test_conflicting_signals(self):
        stream = RealityStreamB()
        signals = [
            StrategySignal("s1", 1000, 1.0, 0.9),
            StrategySignal("s2", 1000, -1.0, 0.9),
        ]
        state = stream.update(signals)
        assert abs(state["consensus_direction"]) < 0.5
        assert state["signal_agreement"] < 0.5


class TestConvergenceStrategy:
    def test_perfect_alignment(self):
        strategy = DefaultConvergenceStrategy()
        a_state = {"momentum": 0.01, "trend_strength": 0.8, "volatility": 0.005}
        b_state = {"consensus_direction": 1.0, "signal_agreement": 0.8, "consensus_confidence": 0.9}
        score = strategy.compute(a_state, b_state)
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should show good alignment

    def test_opposing_signals(self):
        strategy = DefaultConvergenceStrategy()
        a_state = {"momentum": 0.01, "trend_strength": 0.8, "volatility": 0.005}
        b_state = {"consensus_direction": -1.0, "signal_agreement": 0.8, "consensus_confidence": 0.9}
        score = strategy.compute(a_state, b_state)
        assert score < 0.7  # Should show less alignment

    def test_score_bounds(self):
        strategy = DefaultConvergenceStrategy()
        for _ in range(100):
            import random
            a = {"momentum": random.uniform(-0.1, 0.1), "trend_strength": random.random(), "volatility": random.uniform(0, 0.05)}
            b = {"consensus_direction": random.uniform(-1, 1), "signal_agreement": random.random(), "consensus_confidence": random.random()}
            score = strategy.compute(a, b)
            assert 0.0 <= score <= 1.0


class TestGuardianBridge:
    def test_initial_state(self):
        bridge = GuardianBridge()
        result = bridge.update(_make_tick(), [_make_signal()])
        assert "convergence" in result
        assert "divergence" in result
        assert "tension" in result
        assert "signal" in result
        assert 0 <= result["convergence"] <= 1
        assert result["divergence"] == pytest.approx(1.0 - result["convergence"])

    def test_tension_starts_zero(self):
        bridge = GuardianBridge()
        result = bridge.update(_make_tick(), [])
        assert result["tension"] == 0.0

    def test_tension_changes_with_divergence(self):
        bridge = GuardianBridge(tension_window=10)
        # Feed stable data then shock
        for i in range(15):
            bridge.update(_make_tick(100.0), [_make_signal(0.5, 0.8)])
        # Now feed contradictory data
        for i in range(5):
            result = bridge.update(
                _make_tick(100.0 + i * 5),
                [_make_signal(-1.0, 0.9)],
            )
        # Tension should be non-zero after divergence change
        assert result["tension"] != 0.0

    def test_safe_signal_on_high_convergence(self):
        bridge = GuardianBridge(safe_threshold=0.5)
        # Aligned data
        for _ in range(5):
            result = bridge.update(
                _make_tick(100.0),
                [_make_signal(0.0, 0.5)],
            )
        # With neutral momentum and signals, convergence should be decent
        assert result["signal"] in (GuardianSignal.SAFE, GuardianSignal.CAUTION, GuardianSignal.OPPORTUNITY)

    def test_tick_count_increments(self):
        bridge = GuardianBridge()
        assert bridge.tick_count == 0
        bridge.update(_make_tick(), [])
        assert bridge.tick_count == 1
        bridge.update(_make_tick(), [])
        assert bridge.tick_count == 2

    def test_divergence_is_complement(self):
        bridge = GuardianBridge()
        result = bridge.update(_make_tick(), [_make_signal()])
        assert result["convergence"] + result["divergence"] == pytest.approx(1.0)
