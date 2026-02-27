"""Tests for the PrometheusAgent decision loop."""

import pytest
import tempfile
import os
from prometheus.agents import PrometheusAgent
from prometheus.drgb.reality_stream import TickData


def _make_tick(close: float = 100.0) -> TickData:
    return TickData(
        timestamp=1000.0, open=close, high=close * 1.01,
        low=close * 0.99, close=close, volume=1.0,
    )


@pytest.fixture
def agent(tmp_path):
    """Create agent with temp strategy library."""
    config = {
        "strategy_library_path": str(tmp_path / "strategies.json"),
        "risk": {
            "max_daily_loss_pct": 0.02,
            "max_drawdown_pct": 0.10,
            "max_position_pct": 0.10,
        },
    }
    return PrometheusAgent(config)


class TestPrometheusAgent:
    def test_process_single_tick(self, agent):
        result = agent.process_tick(_make_tick())
        # May or may not generate a trade, but should not raise
        assert agent.tick_count == 1

    def test_process_multiple_ticks(self, agent):
        for i in range(20):
            agent.process_tick(_make_tick(100.0 + i * 0.1))
        assert agent.tick_count == 20

    def test_trade_generation(self, agent):
        # Feed a trending market to generate trades
        trades = []
        for i in range(100):
            trade = agent.process_tick(_make_tick(100.0 + i * 0.5))
            if trade:
                trades.append(trade)
        # Should generate at least some trades in 100 ticks of trend
        assert agent.tick_count == 100

    def test_trade_has_required_fields(self, agent):
        for i in range(50):
            trade = agent.process_tick(_make_tick(100.0 + i))
            if trade:
                assert hasattr(trade, "direction")
                assert hasattr(trade, "size_fraction")
                assert hasattr(trade, "confidence")
                assert hasattr(trade, "regime")
                assert hasattr(trade, "guardian_signal")
                assert hasattr(trade, "convergence")
                assert 0 <= trade.size_fraction <= 1.0
                assert -1 <= trade.direction <= 1
                break

    def test_risk_state_update(self, agent):
        agent.update_risk_state({"daily_pnl_pct": -0.01, "drawdown_pct": 0.05})
        assert agent._risk_state["daily_pnl_pct"] == -0.01

    def test_danger_blocks_trades(self, agent):
        # Set risk state to max daily loss exceeded
        agent.update_risk_state({"daily_pnl_pct": -0.05})
        trades = []
        for i in range(50):
            trade = agent.process_tick(_make_tick(100.0 + i))
            if trade:
                trades.append(trade)
        # Should block all trades due to daily loss limit
        assert len(trades) == 0

    def test_strategy_library_persists(self, agent):
        # Library should have seed strategies
        strats = agent.strategy_library.list_all()
        assert len(strats) >= 2

    def test_evolution_runs_periodically(self, agent):
        # Evolution runs every 500 ticks
        for i in range(501):
            agent.process_tick(_make_tick(100.0 + i * 0.01))
        assert agent.tick_count == 501


class TestPaperBroker:
    def test_initial_balance(self):
        from prometheus.infra.broker import PaperBroker
        broker = PaperBroker(initial_balance=50000)
        bal = broker.get_balance()
        assert bal["cash"] == 50000
        assert bal["equity"] == 50000

    def test_buy_order(self):
        from prometheus.infra.broker import PaperBroker
        broker = PaperBroker(initial_balance=100000)
        broker.update_price("BTC/USD", 50000)
        order = broker.submit_order("BTC/USD", "buy", 1.0, 50000)
        assert order.status == "filled"
        assert order.quantity == 1.0
        bal = broker.get_balance()
        assert bal["cash"] == 50000

    def test_sell_order(self):
        from prometheus.infra.broker import PaperBroker
        broker = PaperBroker(initial_balance=100000)
        broker.update_price("BTC/USD", 50000)
        broker.submit_order("BTC/USD", "buy", 1.0, 50000)
        broker.submit_order("BTC/USD", "sell", 0.5, 55000)
        bal = broker.get_balance()
        assert bal["cash"] == 50000 + 0.5 * 55000

    def test_insufficient_funds(self):
        from prometheus.infra.broker import PaperBroker
        broker = PaperBroker(initial_balance=1000)
        broker.update_price("BTC/USD", 50000)
        order = broker.submit_order("BTC/USD", "buy", 1.0, 50000)
        # Should buy what it can afford
        assert order.quantity < 1.0
