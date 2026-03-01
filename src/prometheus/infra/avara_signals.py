"""AVARA Live Trading Signal Reader.

Reads regime detection, position data, strategy state, and fill history
from the live AVARA trading system. Prometheus uses these signals to:
- Cross-reference its paper trading with real live performance
- Learn from AVARA's regime detection (GMM-based, battle-tested)
- Understand what the live system is doing and why
- Generate actionable insights for the live accounts

Signals are read from:
- Subwallet JSON state files (position, cash, avg entry, profit)
- Reallocation state files (capital movement between assets)
- Kraken API (live balances + prices)
- Guardian metrics endpoint (when available)
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AVARAAccountSignals:
    """Signals from one AVARA live trading account."""

    name: str
    account_id: str
    balances: dict[str, float] = field(default_factory=dict)
    positions: list[dict[str, Any]] = field(default_factory=list)
    total_usd: float = 0.0
    cash_usd: float = 0.0
    cash_pct: float = 0.0
    subwallet_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    reallocation_state: dict[str, Any] = field(default_factory=dict)
    regime_per_asset: dict[str, str] = field(default_factory=dict)
    regime_confidence: dict[str, float] = field(default_factory=dict)
    total_profit_usd: float = 0.0
    total_fills: int = 0
    last_updated: float = 0.0


@dataclass
class AVARASignals:
    """Aggregate signals from all AVARA live accounts."""

    accounts: list[AVARAAccountSignals] = field(default_factory=list)
    prices: dict[str, float] = field(default_factory=dict)
    guardian_healthy: bool = False
    guardian_uptime: float = 0.0
    timestamp: float = field(default_factory=time.time)
    errors: list[str] = field(default_factory=list)


ACCOUNTS = [
    {
        "name": "DEREK",
        "id": "69aa5fed-7a66-4493-8aea-d1f5b88ca20d",
        "assets": ["CC", "XMR", "RNDR"],
        "targets": {"CC": 0.45, "RNDR": 0.35, "XMR": 0.20},
    },
    {
        "name": "ACCOUNT 2",
        "id": "b6946ca4-ef97-4cd7-9db0-68497935e6c0",
        "assets": ["CC", "XMR", "RNDR"],
        "targets": {"CC": 0.334, "RNDR": 0.333, "XMR": 0.333},
    },
]

# Map AVARA asset names to Kraken balance keys
ASSET_PRICE_MAP = {
    "CC": "CC/USD",
    "RENDER": "RENDER/USD",
    "XXMR": "XMR/USD",
    "PAXG": "PAXG/USD",
    "SOL": "SOL/USD",
}


class AVARASignalReader:
    """Reads live signals from the AVARA trading system.

    Works by:
    1. Reading subwallet state files via docker exec
    2. Parsing guardian logs for regime/fill data
    3. Fetching live balances via the AVARA AccountService
    4. Querying the health endpoint
    """

    def __init__(self, refresh_interval: float = 300.0) -> None:
        """
        Args:
            refresh_interval: Seconds between full signal refreshes (default 5 min).
        """
        self._refresh_interval = refresh_interval
        self._last_refresh = 0.0
        self._cached: AVARASignals | None = None

    def get_signals(self, force: bool = False) -> AVARASignals:
        """Get current AVARA signals, using cache if recent enough."""
        now = time.time()
        if not force and self._cached and (now - self._last_refresh) < self._refresh_interval:
            return self._cached

        signals = AVARASignals()

        # Health check
        try:
            health = self._fetch_health()
            signals.guardian_healthy = health.get("status") == "healthy"
        except Exception as e:
            signals.errors.append(f"Health check failed: {e}")

        # Read subwallet states
        for acct_cfg in ACCOUNTS:
            acct = AVARAAccountSignals(
                name=acct_cfg["name"],
                account_id=acct_cfg["id"],
            )

            # Subwallet state files
            for asset in acct_cfg["assets"]:
                state = self._read_subwallet(acct_cfg["id"], asset)
                if state:
                    acct.subwallet_states[asset] = state
                    acct.total_profit_usd += state.get("total_profit_usd", 0)
                    acct.total_fills += state.get("fills_processed", 0)

                    # Extract regime from buy_reference behavior
                    # (approximation — real regime comes from strategy)
                    if state.get("position_size", 0) > 0 and state.get("available_cash", 0) > 0:
                        cash_ratio = state["available_cash"] / (
                            state["available_cash"] + state["position_size"] * state.get("avg_entry_price", 1)
                        )
                        if cash_ratio > 0.6:
                            acct.regime_per_asset[asset] = "bear"
                        elif cash_ratio > 0.3:
                            acct.regime_per_asset[asset] = "sideways"
                        else:
                            acct.regime_per_asset[asset] = "bull"

            # Reallocation state
            realloc = self._read_reallocation(acct_cfg["id"])
            if realloc:
                acct.reallocation_state = realloc

            # Live balances
            try:
                balances = self._fetch_balances(acct_cfg["id"])
                acct.balances = balances
            except Exception as e:
                signals.errors.append(f"Balance fetch failed for {acct_cfg['name']}: {e}")

            acct.last_updated = time.time()
            signals.accounts.append(acct)

        # Get prices for valuation
        try:
            signals.prices = self._fetch_prices()
        except Exception as e:
            signals.errors.append(f"Price fetch failed: {e}")

        # Compute USD values
        for acct in signals.accounts:
            total = 0.0
            for asset, bal in acct.balances.items():
                ws = ASSET_PRICE_MAP.get(asset)
                price = signals.prices.get(ws, 0) if ws else (1.0 if asset in ("ZUSD", "USDT", "USDG") else 0)
                value = bal * price
                total += value
                if value > 0.01:
                    acct.positions.append({
                        "asset": asset, "balance": bal, "price": price, "value": value,
                    })
            acct.total_usd = total
            acct.cash_usd = sum(
                p["value"] for p in acct.positions if p["asset"] in ("ZUSD", "USDT", "USDG")
            )
            acct.cash_pct = (acct.cash_usd / total * 100) if total > 0 else 0

        signals.timestamp = time.time()
        self._cached = signals
        self._last_refresh = time.time()
        logger.info(
            "AVARA signals refreshed: %d accounts, %d prices, %d errors",
            len(signals.accounts), len(signals.prices), len(signals.errors),
        )
        return signals

    def get_summary(self) -> dict[str, Any]:
        """Get a compact summary dict suitable for logging or reporting."""
        sig = self.get_signals()
        summary = {
            "timestamp": sig.timestamp,
            "guardian_healthy": sig.guardian_healthy,
            "errors": sig.errors,
            "accounts": [],
        }
        for acct in sig.accounts:
            a = {
                "name": acct.name,
                "total_usd": round(acct.total_usd, 2),
                "cash_usd": round(acct.cash_usd, 2),
                "cash_pct": round(acct.cash_pct, 1),
                "total_profit": round(acct.total_profit_usd, 2),
                "total_fills": acct.total_fills,
                "regimes": acct.regime_per_asset,
                "assets": {},
            }
            for asset, state in acct.subwallet_states.items():
                a["assets"][asset] = {
                    "position": round(state.get("position_size", 0), 4),
                    "cash": round(state.get("available_cash", 0), 2),
                    "avg_entry": round(state.get("avg_entry_price", 0), 6),
                    "profit": round(state.get("total_profit_usd", 0), 2),
                    "buy_ref": round(state.get("buy_reference_price", 0), 6),
                }
            summary["accounts"].append(a)
        return summary

    # ── Internal helpers ──

    @staticmethod
    def _docker_exec(cmd: str, timeout: int = 10) -> str:
        """Run a command inside the avara-orchestrator container."""
        try:
            result = subprocess.run(
                ["docker", "exec", "avara-orchestrator", "bash", "-c", cmd],
                capture_output=True, text=True, timeout=timeout,
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.warning("docker exec timed out: %s", cmd[:80])
            return ""
        except Exception as e:
            logger.debug("docker exec failed: %s — %s", cmd[:80], e)
            return ""

    def _read_subwallet(self, account_id: str, asset: str) -> dict[str, Any] | None:
        """Read subwallet state file from inside the container."""
        # Try short account name mapping
        name_map = {
            "69aa5fed-7a66-4493-8aea-d1f5b88ca20d": "derek",
            "b6946ca4-ef97-4cd7-9db0-68497935e6c0": "account2",
        }
        account_name = name_map.get(account_id, account_id)

        path = f"/app/data/subwallet_{account_name}_{asset}.json"
        raw = self._docker_exec(f"cat {path} 2>/dev/null")
        if not raw:
            # Try with full UUID
            path = f"/app/data/subwallet_{account_id}_{asset}.json"
            raw = self._docker_exec(f"cat {path} 2>/dev/null")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in %s", path)
        return None

    def _read_reallocation(self, account_id: str) -> dict[str, Any] | None:
        """Read reallocation state file."""
        name_map = {
            "69aa5fed-7a66-4493-8aea-d1f5b88ca20d": "derek",
            "b6946ca4-ef97-4cd7-9db0-68497935e6c0": "account2",
        }
        account_name = name_map.get(account_id, account_id)
        path = f"/app/data/reallocation_{account_name}.json"
        raw = self._docker_exec(f"cat {path} 2>/dev/null")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return None

    def _fetch_health(self) -> dict[str, Any]:
        """Fetch guardian health endpoint."""
        url = "http://localhost:8000/health"
        req = urllib.request.Request(url, headers={"User-Agent": "PROMETHEUS/0.1"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _fetch_balances(self, account_id: str) -> dict[str, float]:
        """Fetch live Kraken balances via docker exec + AVARA AccountService."""
        cmd = f"""python3 -c "
import sys, asyncio; sys.path.insert(0, '/app')
from core.account_service import get_account_service
from core.exchange_client import KrakenExchangeClient
import json

async def main():
    svc = get_account_service()
    creds = svc.get_exchange_credentials('{account_id}', 'kraken')
    client = KrakenExchangeClient(api_key=creds['api_key'], api_secret=creds['api_secret'])
    balances = client.get_balances()
    print(json.dumps({{k: str(v) for k, v in balances.items() if float(v) > 0}}))

asyncio.run(main())
" """
        raw = self._docker_exec(cmd, timeout=20)
        if raw:
            try:
                return {k: float(v) for k, v in json.loads(raw).items()}
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    @staticmethod
    def _fetch_prices() -> dict[str, float]:
        """Fetch prices for AVARA's traded assets from Kraken public API."""
        pairs = "CCUSD,RENDERUSD,SOLUSD,XMRUSD,PAXGUSD"
        url = f"https://api.kraken.com/0/public/Ticker?pair={pairs}"
        req = urllib.request.Request(url, headers={"User-Agent": "PROMETHEUS/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        prices = {}
        for pair, info in data.get("result", {}).items():
            price = float(info["c"][0])
            if "CC" in pair and "USD" in pair and "RENDER" not in pair:
                prices["CC/USD"] = price
            elif "RENDER" in pair:
                prices["RENDER/USD"] = price
            elif "SOL" in pair:
                prices["SOL/USD"] = price
            elif "XMR" in pair:
                prices["XMR/USD"] = price
            elif "PAXG" in pair:
                prices["PAXG/USD"] = price
        return prices


# Singleton for shared use
_reader: AVARASignalReader | None = None


def get_avara_signals(force: bool = False) -> AVARASignals:
    """Get AVARA signals using the shared reader instance."""
    global _reader
    if _reader is None:
        _reader = AVARASignalReader()
    return _reader.get_signals(force=force)


def get_avara_summary() -> dict[str, Any]:
    """Get compact AVARA summary using the shared reader instance."""
    global _reader
    if _reader is None:
        _reader = AVARASignalReader()
    return _reader.get_summary()
