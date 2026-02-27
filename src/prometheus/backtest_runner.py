"""Backtest runner: offline simulation.

Runs PROMETHEUS against historical data for evaluation and optimization.
"""

from __future__ import annotations

import csv
import logging
import random
import time
from pathlib import Path
from typing import Any

from .agents.prometheus_agent import PrometheusAgent, TradeInstruction
from .drgb.reality_stream import TickData
from .infra.broker import PaperBroker
from .infra.config import load_config
from .infra.logging_setup import setup_logging

logger = logging.getLogger(__name__)


class BacktestRunner:
    """Run PROMETHEUS against historical data."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.agent = PrometheusAgent(config)
        self.broker = PaperBroker(
            initial_balance=config.get("broker", {}).get("initial_balance", 100_000),
        )
        self._symbol = config.get("symbol", "BTC/USD")

    def run_from_csv(self, csv_path: str | Path) -> dict[str, Any]:
        """Run backtest from a CSV file.

        Expected CSV columns: timestamp, open, high, low, close, volume
        """
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        trades: list[TradeInstruction] = []
        tick_count = 0

        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                tick = TickData(
                    timestamp=float(row.get("timestamp", time.time())),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                )
                self.broker.update_price(self._symbol, tick.close)
                trade = self.agent.process_tick(tick)

                if trade:
                    trades.append(trade)
                    side = "buy" if trade.direction > 0 else "sell"
                    balance = self.broker.get_balance()
                    qty = (balance["equity"] * trade.size_fraction) / tick.close
                    if qty > 0:
                        self.broker.submit_order(self._symbol, side, qty, tick.close)

                tick_count += 1

        return self._summary(tick_count, trades)

    def run_synthetic(self, num_ticks: int = 10000) -> dict[str, Any]:
        """Run backtest with synthetic data."""
        trades: list[TradeInstruction] = []
        price = 50000.0
        vol = 0.001

        for i in range(num_ticks):
            ret = random.gauss(0, vol)
            price *= 1 + ret

            tick = TickData(
                timestamp=time.time() + i,
                open=price * (1 - abs(ret) / 2),
                high=price * (1 + abs(ret)),
                low=price * (1 - abs(ret)),
                close=price,
                volume=random.uniform(0.1, 10.0),
            )
            self.broker.update_price(self._symbol, tick.close)
            trade = self.agent.process_tick(tick)

            if trade:
                trades.append(trade)
                side = "buy" if trade.direction > 0 else "sell"
                balance = self.broker.get_balance()
                qty = (balance["equity"] * trade.size_fraction) / tick.close
                if qty > 0:
                    self.broker.submit_order(self._symbol, side, qty, tick.close)

        return self._summary(num_ticks, trades)

    def _summary(
        self, tick_count: int, trades: list[TradeInstruction]
    ) -> dict[str, Any]:
        balance = self.broker.get_balance()
        return {
            "ticks_processed": tick_count,
            "total_trades": len(trades),
            "final_equity": balance["equity"],
            "pnl": balance["pnl"],
            "pnl_pct": balance["pnl_pct"] * 100,
            "orders": len(self.broker.order_history),
        }


def main() -> None:
    """Entry point for backtest."""
    config = load_config(Path("config/prometheus.yaml") if Path("config/prometheus.yaml").exists() else None)
    setup_logging(config.get("logging"))

    runner = BacktestRunner(config)
    logger.info("Running synthetic backtest with 5000 ticks...")
    results = runner.run_synthetic(5000)

    logger.info("=== BACKTEST RESULTS ===")
    for key, value in results.items():
        if isinstance(value, float):
            logger.info("  %s: %.4f", key, value)
        else:
            logger.info("  %s: %s", key, value)


if __name__ == "__main__":
    main()
