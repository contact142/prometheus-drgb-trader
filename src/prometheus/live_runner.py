"""Live runner: infinite loop with graceful shutdown.

Runs PROMETHEUS in paper mode with either synthetic or real Kraken
price data. Set `data_source: kraken` in config for real prices.
"""

from __future__ import annotations

import json
import logging
import random
import signal
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .agents.prometheus_agent import PrometheusAgent
from .drgb.reality_stream import TickData
from .infra.broker import PaperBroker
from .infra.config import load_config
from .infra.logging_setup import setup_logging

logger = logging.getLogger(__name__)


class KrakenPriceFeed:
    """Real-time price feed from Kraken public REST API.

    Fetches ticker data for all symbols in batches every `refresh_seconds`.
    Thread-safe price cache accessed by the main loop via `get_tick()`.
    """

    TICKER_URL = "https://api.kraken.com/0/public/Ticker"
    PAIRS_URL = "https://api.kraken.com/0/public/AssetPairs"
    BATCH_SIZE = 80  # pairs per request (URL length safe)
    BATCH_DELAY = 1.5  # seconds between batches (rate limit)

    def __init__(self, symbols: list[str], refresh_seconds: float = 10.0) -> None:
        self._symbols = set(symbols)
        self._refresh_seconds = refresh_seconds
        self._lock = threading.Lock()
        self._prices: dict[str, dict[str, float]] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        # Mapping: wsname (BTC/USD) <-> Kraken internal pair name (XXBTZUSD)
        self._ws_to_kraken: dict[str, str] = {}
        self._kraken_to_ws: dict[str, str] = {}
        self._ready = threading.Event()

    def start(self) -> None:
        """Build pair mapping and start background polling thread."""
        self._build_pair_mapping()
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        # Wait for first fetch to complete (up to 60s)
        self._ready.wait(timeout=60)

    def stop(self) -> None:
        self._running = False

    @property
    def available_symbols(self) -> list[str]:
        """Symbols that were successfully mapped to Kraken pairs."""
        return sorted(self._ws_to_kraken.keys())

    def get_tick(self, symbol: str) -> dict[str, float] | None:
        """Get cached price data for a symbol. Thread-safe."""
        with self._lock:
            return self._prices.get(symbol)

    def _build_pair_mapping(self) -> None:
        """Fetch AssetPairs from Kraken and map wsname -> internal pair name."""
        logger.info("Fetching Kraken asset pairs for %d symbols...", len(self._symbols))
        try:
            data = self._api_get(self.PAIRS_URL)
            mapped = 0
            for pair_name, info in data.items():
                wsname = info.get("wsname", "")
                if wsname in self._symbols and info.get("status") == "online":
                    self._ws_to_kraken[wsname] = pair_name
                    self._kraken_to_ws[pair_name] = wsname
                    mapped += 1
            logger.info(
                "Kraken pair mapping: %d/%d symbols mapped",
                mapped, len(self._symbols),
            )
            unmapped = self._symbols - set(self._ws_to_kraken.keys())
            if unmapped:
                logger.warning("Unmapped symbols (not on Kraken): %s", sorted(unmapped)[:20])
        except Exception:
            logger.exception("Failed to fetch Kraken asset pairs")

    def _poll_loop(self) -> None:
        """Background thread: fetch all tickers in batches, then sleep."""
        while self._running:
            try:
                self._fetch_all_tickers()
                self._ready.set()
            except Exception:
                logger.exception("Kraken ticker poll error")
            time.sleep(self._refresh_seconds)

    def _fetch_all_tickers(self) -> None:
        """Batch-fetch tickers for all mapped pairs."""
        kraken_pairs = list(self._ws_to_kraken.values())
        if not kraken_pairs:
            return

        fetched = 0
        for i in range(0, len(kraken_pairs), self.BATCH_SIZE):
            if not self._running:
                return
            batch = kraken_pairs[i : i + self.BATCH_SIZE]
            pair_str = ",".join(batch)
            try:
                data = self._api_get(f"{self.TICKER_URL}?pair={pair_str}")
                with self._lock:
                    for kname, ticker in data.items():
                        wsname = self._kraken_to_ws.get(kname)
                        if wsname:
                            self._prices[wsname] = {
                                "price": float(ticker["c"][0]),
                                "bid": float(ticker["b"][0]),
                                "ask": float(ticker["a"][0]),
                                "volume": float(ticker["v"][1]),
                                "high": float(ticker["h"][1]),
                                "low": float(ticker["l"][1]),
                                "open": float(ticker["o"]),
                            }
                            fetched += 1
            except Exception:
                logger.exception("Kraken ticker batch error (batch %d)", i // self.BATCH_SIZE)
            if i + self.BATCH_SIZE < len(kraken_pairs):
                time.sleep(self.BATCH_DELAY)

        logger.debug("Kraken price refresh: %d/%d symbols updated", fetched, len(kraken_pairs))

    @staticmethod
    def _api_get(url: str) -> dict[str, Any]:
        """GET from Kraken public API, return result dict."""
        req = urllib.request.Request(url, headers={"User-Agent": "PROMETHEUS/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
        errors = body.get("error", [])
        if errors:
            raise RuntimeError(f"Kraken API error: {errors}")
        return body.get("result", {})


class LiveRunner:
    """Main live trading loop."""

    # Default starting prices per asset for synthetic paper mode
    SYNTHETIC_DEFAULTS: dict[str, dict[str, float]] = {
        "BTC/USD": {"price": 50000.0, "vol": 0.001},
        "XMR/USD": {"price": 230.0, "vol": 0.0015},
        "RNDR/USD": {"price": 7.50, "vol": 0.002},
        "CANT/USD": {"price": 0.035, "vol": 0.002},
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

        # Multi-asset: use 'symbols' list, fall back to single 'symbol'
        symbols_cfg = config.get("symbols")
        if symbols_cfg:
            self._symbols = list(symbols_cfg)
        else:
            self._symbols = [config.get("symbol", "BTC/USD")]

        # Data source: "synthetic" (random walk) or "kraken" (real prices)
        self._data_source = config.get("data_source", "synthetic")
        self._kraken_feed: KrakenPriceFeed | None = None

        if self._data_source == "kraken":
            refresh = config.get("kraken_refresh_seconds", 10.0)
            self._kraken_feed = KrakenPriceFeed(self._symbols, refresh_seconds=refresh)
            self._kraken_feed.start()
            # Filter to only symbols that Kraken actually has
            available = set(self._kraken_feed.available_symbols)
            before = len(self._symbols)
            self._symbols = [s for s in self._symbols if s in available]
            logger.info(
                "Kraken feed: %d/%d symbols available for trading",
                len(self._symbols), before,
            )

        broker_cfg = config.get("broker", {})
        self.broker = PaperBroker(
            initial_balance=broker_cfg.get("initial_balance", 100_000),
            default_symbol=self._symbols[0] if self._symbols else "BTC/USD",
            min_hold_pct=broker_cfg.get("min_hold_pct", 0.0),
        )
        self._running = False
        self._tick_interval = config.get("tick_interval_seconds", 1.0)

        # Per-asset agents and synthetic price state
        self._agents: dict[str, PrometheusAgent] = {}
        self._synthetic_prices: dict[str, float] = {}
        self._synthetic_vols: dict[str, float] = {}

        for sym in self._symbols:
            self._agents[sym] = PrometheusAgent(config)
            defaults = self.SYNTHETIC_DEFAULTS.get(sym, {"price": 100.0, "vol": 0.002})
            self._synthetic_prices[sym] = defaults["price"]
            self._synthetic_vols[sym] = defaults["vol"]

    def start(self) -> None:
        """Start the main loop."""
        self._running = True
        logger.info(
            "PROMETHEUS starting in %s mode (data_source=%s)",
            self.config.get("mode", "paper"),
            self._data_source,
        )
        logger.info("Symbols: %d assets, Tick interval: %.1fs", len(self._symbols), self._tick_interval)

        tick_count = 0
        while self._running:
            try:
                traded_count = 0
                for symbol in self._symbols:
                    tick = self._get_tick(symbol)
                    if tick is None:
                        continue  # No price data yet for this symbol
                    self.broker.update_price(symbol, tick.close)

                    trade = self._agents[symbol].process_tick(tick)

                    if trade:
                        side = "buy" if trade.direction > 0 else "sell"
                        balance = self.broker.get_balance()
                        # Size per asset: fraction of equity divided by number of assets
                        per_asset_fraction = trade.size_fraction / len(self._symbols)
                        qty = (balance["equity"] * per_asset_fraction) / tick.close
                        if qty > 0:
                            self.broker.submit_order(symbol, side, qty, tick.close)
                            traded_count += 1

                tick_count += 1
                if tick_count % 50 == 0:
                    bal = self.broker.get_balance()
                    positions = self.broker.get_positions()
                    pos_count = len(positions)
                    top_positions = sorted(positions, key=lambda p: abs(p["value"]), reverse=True)[:5]
                    pos_str = " | ".join(
                        f"{p['symbol']}: ${p['value']:.2f}"
                        for p in top_positions
                    ) or "no positions"
                    logger.info(
                        "Tick %d | Equity: $%.2f | PnL: %.2f%% | %d positions | Top: %s",
                        tick_count,
                        bal["equity"],
                        bal["pnl_pct"] * 100,
                        pos_count,
                        pos_str,
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
        if self._kraken_feed:
            self._kraken_feed.stop()
        bal = self.broker.get_balance()
        logger.info(
            "Final state: Equity=$%.2f, PnL=$%.2f (%.2f%%), Trades=%d",
            bal["equity"],
            bal["pnl"],
            bal["pnl_pct"] * 100,
            len(self.broker.order_history),
        )
        for pos in sorted(
            self.broker.get_positions(), key=lambda p: abs(p["value"]), reverse=True
        )[:10]:
            logger.info(
                "  Position: %s %.6f ($%.2f)",
                pos["symbol"], pos["quantity"], pos["value"],
            )

    def _get_tick(self, symbol: str) -> TickData | None:
        """Get next tick for a symbol.

        Uses real Kraken prices if data_source=kraken, else synthetic random walk.
        """
        if self._kraken_feed:
            cached = self._kraken_feed.get_tick(symbol)
            if cached is None:
                return None  # No data yet
            price = cached["price"]
            if price <= 0:
                return None
            return TickData(
                timestamp=time.time(),
                open=cached.get("open", price),
                high=cached.get("high", price),
                low=cached.get("low", price),
                close=price,
                volume=cached.get("volume", 0.0),
                bid=cached.get("bid", price),
                ask=cached.get("ask", price),
            )

        # Synthetic random walk for paper mode
        vol = self._synthetic_vols[symbol]
        ret = random.gauss(0, vol)
        self._synthetic_prices[symbol] *= 1 + ret
        price = self._synthetic_prices[symbol]
        spread = price * 0.0005

        return TickData(
            timestamp=time.time(),
            open=price * (1 - abs(ret) / 2),
            high=price * (1 + abs(ret)),
            low=price * (1 - abs(ret)),
            close=price,
            volume=random.uniform(0.1, 10.0),
            bid=price - spread / 2,
            ask=price + spread / 2,
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
