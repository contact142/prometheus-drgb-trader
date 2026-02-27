"""Live runner: infinite loop with graceful shutdown.

Runs PROMETHEUS in paper mode by default, generating synthetic
tick data. Replace the data feed with real market data for live trading.

PLUG-IN POINT: Replace `_generate_tick()` with your real data feed
(e.g., Kraken WebSocket, Binance stream).
"""

from __future__ import annotations

import logging
import math
import random
import signal
import sys
import time
from pathlib import Path
from typing import Any

from .agents.prometheus_agent import PrometheusAgent
from .drgb.reality_stream import TickData
from .infra.broker import PaperBroker
from .infra.config import load_config
from .infra.logging_setup import setup_logging

logger = logging.getLogger(__name__)


class LiveRunner:
    """Main live trading loop."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.agent = PrometheusAgent(config)
        self.broker = PaperBroker(
            initial_balance=config.get("broker", {}).get("initial_balance", 100_000),
            default_symbol=config.get("symbol", "BTC/USD"),
        )
        self._running = False
        self._tick_interval = config.get("tick_interval_seconds", 1.0)
        self._symbol = config.get("symbol", "BTC/USD")

        # Synthetic price state (for paper mode)
        self._synthetic_price = 50000.0
        self._synthetic_vol = 0.001

    def start(self) -> None:
        """Start the main loop."""
        self._running = True
        logger.info("PROMETHEUS starting in %s mode", self.config.get("mode", "paper"))
        logger.info("Symbol: %s, Tick interval: %.1fs", self._symbol, self._tick_interval)

        tick_count = 0
        while self._running:
            try:
                tick = self._get_tick()
                self.broker.update_price(self._symbol, tick.close)

                trade = self.agent.process_tick(tick)

                if trade:
                    side = "buy" if trade.direction > 0 else "sell"
                    balance = self.broker.get_balance()
                    qty = (balance["equity"] * trade.size_fraction) / tick.close
                    if qty > 0:
                        self.broker.submit_order(
                            self._symbol, side, qty, tick.close
                        )

                tick_count += 1
                if tick_count % 100 == 0:
                    bal = self.broker.get_balance()
                    logger.info(
                        "Tick %d | Price: $%.2f | Equity: $%.2f | PnL: %.2f%%",
                        tick_count,
                        tick.close,
                        bal["equity"],
                        bal["pnl_pct"] * 100,
                    )

                time.sleep(self._tick_interval)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                self.stop()
            except Exception:
                logger.exception("Error in main loop")
                time.sleep(5)

    def stop(self) -> None:
        """Graceful shutdown."""
        logger.info("PROMETHEUS shutting down...")
        self._running = False
        bal = self.broker.get_balance()
        logger.info(
            "Final state: Equity=$%.2f, PnL=$%.2f (%.2f%%), Trades=%d",
            bal["equity"],
            bal["pnl"],
            bal["pnl_pct"] * 100,
            len(self.broker.order_history),
        )

    def _get_tick(self) -> TickData:
        """Get next tick. Override for real data feed.

        PLUG-IN POINT: Replace this with real market data.
        Examples:
        - Kraken WebSocket
        - Binance REST/WS
        - CCXT unified interface
        """
        # Synthetic random walk for paper mode
        ret = random.gauss(0, self._synthetic_vol)
        self._synthetic_price *= 1 + ret
        spread = self._synthetic_price * 0.0005

        return TickData(
            timestamp=time.time(),
            open=self._synthetic_price * (1 - abs(ret) / 2),
            high=self._synthetic_price * (1 + abs(ret)),
            low=self._synthetic_price * (1 - abs(ret)),
            close=self._synthetic_price,
            volume=random.uniform(0.1, 10.0),
            bid=self._synthetic_price - spread / 2,
            ask=self._synthetic_price + spread / 2,
        )


def main() -> None:
    """Entry point."""
    config_path = Path("config/prometheus.yaml")
    if not config_path.exists():
        config_path = None

    config = load_config(config_path)
    setup_logging(config.get("logging"))

    runner = LiveRunner(config)

    # Graceful shutdown on SIGTERM/SIGINT
    def handle_signal(signum: int, frame: Any) -> None:
        logger.info("Signal %d received, stopping...", signum)
        runner.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    runner.start()


if __name__ == "__main__":
    main()
