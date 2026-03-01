#!/usr/bin/env python3
"""PROMETHEUS Intelligence Report Generator.

Analyzes both Prometheus paper trading performance AND live AVARA trading
on both accounts, then generates actionable insights.

Run from the prometheus directory:
    PYTHONPATH=src venv/bin/python generate_report.py

Or from inside the AVARA container for live account data:
    docker exec avara-orchestrator python3 /app/prometheus/generate_report.py
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Kraken public API helpers ─────────────────────────────────────────


def kraken_get(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "PROMETHEUS/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    if body.get("error"):
        raise RuntimeError(f"Kraken API error: {body['error']}")
    return body.get("result", {})


def get_kraken_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch current prices for a list of wsname symbols (e.g. 'BTC/USD')."""
    pairs_data = kraken_get("https://api.kraken.com/0/public/AssetPairs")
    ws_to_pair: dict[str, str] = {}
    for pair_name, info in pairs_data.items():
        ws = info.get("wsname", "")
        if ws:
            ws_to_pair[ws] = pair_name

    need = {ws_to_pair[s] for s in symbols if s in ws_to_pair}
    prices: dict[str, float] = {}
    pair_list = list(need)

    for i in range(0, len(pair_list), 80):
        batch = pair_list[i : i + 80]
        url = f"https://api.kraken.com/0/public/Ticker?pair={','.join(batch)}"
        if i > 0:
            time.sleep(2)
        data = kraken_get(url)
        for rp, info in data.items():
            p = float(info["c"][0])
            for ws, pn in ws_to_pair.items():
                if pn == rp:
                    prices[ws] = p

    return prices


# ── Prometheus paper trading analysis ─────────────────────────────────


def analyze_prometheus_trades(log_path: Path) -> dict[str, Any]:
    """Parse Prometheus log to extract trade stats."""
    positions = defaultdict(lambda: {"qty": 0.0, "cost": 0.0, "buys": 0, "sells": 0})
    strategies_used: dict[str, int] = defaultdict(int)
    regimes_seen: dict[str, int] = defaultdict(int)
    signals_seen: dict[str, int] = defaultdict(int)
    total_buys = 0
    total_sells = 0
    sell_blocked = 0
    first_ts = None
    last_ts = None
    last_cash = 100_000.0
    equity_snapshots: list[dict[str, float]] = []
    fitness_updates: list[dict[str, Any]] = []

    if not log_path.exists():
        return {"error": "Log file not found"}

    with open(log_path) as f:
        for line in f:
            # Parse timestamps
            ts_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if ts_match:
                ts_str = ts_match.group(1)
                if first_ts is None:
                    first_ts = ts_str
                last_ts = ts_str

            # Trade log
            m = re.search(
                r"PAPER TRADE: \S+ (BUY|SELL) ([\d.]+) (\S+) @ \$([\d.]+) \| Cash: \$([\d.]+)",
                line,
            )
            if m:
                side, qty, asset = m.group(1), float(m.group(2)), m.group(3)
                price, cash = float(m.group(4)), float(m.group(5))
                last_cash = cash
                if side == "BUY" and qty > 0:
                    total_buys += 1
                    positions[asset]["qty"] += qty
                    positions[asset]["cost"] += qty * price
                    positions[asset]["buys"] += 1
                elif side == "SELL":
                    total_sells += 1
                    if qty == 0:
                        sell_blocked += 1
                    else:
                        positions[asset]["qty"] -= qty
                        positions[asset]["sells"] += 1

            # Strategy usage
            sm = re.search(r"Trade generated: (\S+) .* \(regime=(\S+), signal=\S+\.(\S+)\)", line)
            if sm:
                strategies_used[sm.group(1)] += 1
                regimes_seen[sm.group(2)] += 1
                signals_seen[sm.group(3)] += 1

            # Equity snapshots
            eq = re.search(r"Tick (\d+) \| Equity: \$([\d.]+) \| PnL: ([\d.-]+)%", line)
            if eq:
                equity_snapshots.append({
                    "tick": int(eq.group(1)),
                    "equity": float(eq.group(2)),
                    "pnl_pct": float(eq.group(3)),
                })

            # Fitness updates
            fm = re.search(r"Fitness update: (\S+) . ([\d.]+) \(W/L=(\d+)/(\d+), avg_pnl=\$([\d.-]+)\)", line)
            if fm:
                fitness_updates.append({
                    "strategy": fm.group(1),
                    "fitness": float(fm.group(2)),
                    "wins": int(fm.group(3)),
                    "losses": int(fm.group(4)),
                    "avg_pnl": float(fm.group(5)),
                })

    held = {a: p for a, p in positions.items() if p["qty"] > 0.001}

    return {
        "first_ts": first_ts,
        "last_ts": last_ts,
        "total_buys": total_buys,
        "total_sells": total_sells,
        "sell_blocked": sell_blocked,
        "effective_sells": total_sells - sell_blocked,
        "last_cash": last_cash,
        "held_count": len(held),
        "held": held,
        "strategies_used": dict(strategies_used),
        "regimes_seen": dict(regimes_seen),
        "signals_seen": dict(signals_seen),
        "equity_snapshots": equity_snapshots,
        "fitness_updates": fitness_updates,
    }


# ── Live AVARA account analysis ──────────────────────────────────────


def analyze_live_accounts() -> dict[str, Any]:
    """Analyze live AVARA trading accounts.

    Must be run from inside the container or with AVARA on PYTHONPATH.
    """
    try:
        sys.path.insert(0, "/app")
        from core.account_service import get_account_service
        from core.exchange_client import KrakenExchangeClient
        import asyncio
    except ImportError:
        return {"error": "Not running inside AVARA container. Run with: docker exec avara-orchestrator python3 /app/prometheus/generate_report.py"}

    accounts = [
        {
            "name": "DEREK",
            "id": "69aa5fed-7a66-4493-8aea-d1f5b88ca20d",
            "targets": {"CC": 0.45, "RENDER": 0.35, "XXMR": 0.20},
            "capital_usd": 231.63,
        },
        {
            "name": "ACCOUNT 2",
            "id": "b6946ca4-ef97-4cd7-9db0-68497935e6c0",
            "targets": {"CC": 0.334, "RENDER": 0.333, "XXMR": 0.333},
            "capital_usd": 333.33,
        },
    ]

    # Price map for USD valuation
    price_map = {
        "CC": "CC/USD", "RENDER": "RENDER/USD", "XXMR": "XMR/USD",
        "PAXG": "PAXG/USD", "SOL": "SOL/USD",
    }

    async def fetch():
        svc = get_account_service()
        results = []
        for acct in accounts:
            creds = svc.get_exchange_credentials(acct["id"], "kraken")
            client = KrakenExchangeClient(
                api_key=creds["api_key"], api_secret=creds["api_secret"]
            )
            balances = client.get_balances()
            results.append({
                "name": acct["name"],
                "id": acct["id"],
                "targets": acct["targets"],
                "capital_usd": acct["capital_usd"],
                "balances": {k: float(v) for k, v in balances.items() if float(v) > 0},
            })
        return results

    account_data = asyncio.run(fetch())

    # Get prices
    symbols_needed = list(set(price_map.values()))
    prices = get_kraken_prices(symbols_needed)

    # Reverse map
    asset_prices = {}
    for asset, ws in price_map.items():
        if ws in prices:
            asset_prices[asset] = prices[ws]
    asset_prices["ZUSD"] = 1.0
    asset_prices["USDT"] = 1.0
    asset_prices["USDG"] = 1.0

    for acct in account_data:
        total = 0.0
        positions = []
        for asset, bal in acct["balances"].items():
            price = asset_prices.get(asset, 0)
            value = bal * price
            total += value
            if value > 0.01:
                positions.append({
                    "asset": asset, "balance": bal, "price": price, "value": value,
                })
        acct["total_usd"] = total
        acct["positions"] = sorted(positions, key=lambda x: x["value"], reverse=True)

        # Allocation analysis
        crypto_value = sum(p["value"] for p in positions if p["asset"] not in ("ZUSD", "USDT", "USDG"))
        acct["crypto_value"] = crypto_value
        acct["cash_value"] = total - crypto_value
        acct["cash_pct"] = (total - crypto_value) / total * 100 if total > 0 else 0

        # Target drift
        drift = []
        for target_asset, target_pct in acct["targets"].items():
            actual = next((p["value"] for p in positions if p["asset"] == target_asset), 0)
            actual_pct = actual / total if total > 0 else 0
            drift.append({
                "asset": target_asset,
                "target_pct": target_pct * 100,
                "actual_pct": actual_pct * 100,
                "drift_pct": (actual_pct - target_pct) * 100,
                "actual_usd": actual,
            })
        acct["drift"] = drift

    return {"accounts": account_data, "prices": asset_prices}


# ── Guardian log analysis ─────────────────────────────────────────────


def analyze_guardian_logs() -> dict[str, Any]:
    """Parse recent guardian logs for regime, fills, and strategy behavior."""
    import glob
    import subprocess

    try:
        result = subprocess.run(
            ["ls", "-t", "/app/logs/"],
            capture_output=True, text=True, timeout=5,
        )
        log_files = [f for f in result.stdout.strip().split("\n") if "guardian_dual" in f]
    except Exception:
        return {"error": "Cannot access guardian logs"}

    if not log_files:
        return {"error": "No guardian log files found"}

    latest = f"/app/logs/{log_files[0]}"
    try:
        with open(latest) as f:
            lines = f.readlines()[-200:]  # last 200 lines
    except Exception:
        return {"error": f"Cannot read {latest}"}

    regimes = []
    fills = []
    errors = []
    heartbeats = 0

    for line in lines:
        if "regime" in line.lower():
            regimes.append(line.strip()[:120])
        if "FILL" in line or "fill" in line:
            fills.append(line.strip()[:120])
        if "ERROR" in line or "error" in line.lower():
            errors.append(line.strip()[:120])
        if "heartbeat" in line.lower():
            heartbeats += 1

    return {
        "log_file": latest,
        "recent_regimes": regimes[-10:],
        "recent_fills": fills[-10:],
        "recent_errors": errors[-10:],
        "heartbeat_count": heartbeats,
        "total_lines_checked": len(lines),
    }


# ── Report generator ─────────────────────────────────────────────────


def generate_report() -> str:
    """Generate the full intelligence report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Prometheus analysis
    log_path = Path("logs/prometheus.log")
    if not log_path.exists():
        # Try container path
        log_path = Path("/app/prometheus/logs/prometheus.log")

    prom = analyze_prometheus_trades(log_path)

    # Get current portfolio value
    prom_prices: dict[str, float] = {}
    if prom.get("held"):
        held_symbols = list(prom["held"].keys())
        prom_prices = get_kraken_prices(held_symbols)

    total_position_value = 0.0
    top_positions = []
    winners = 0
    losers = 0

    if prom.get("held"):
        for asset, pos in prom["held"].items():
            price = prom_prices.get(asset, 0)
            value = pos["qty"] * price
            pnl = value - pos["cost"]
            total_position_value += value
            if pnl >= 0:
                winners += 1
            else:
                losers += 1
            if value > 50:
                top_positions.append({
                    "asset": asset, "qty": pos["qty"], "price": price,
                    "value": value, "cost": pos["cost"], "pnl": pnl,
                    "buys": pos["buys"], "sells": pos["sells"],
                })

    top_positions.sort(key=lambda x: x["value"], reverse=True)
    prom_cash = prom.get("last_cash", 0)
    prom_equity = prom_cash + total_position_value
    prom_pnl = prom_equity - 100_000

    # Live account analysis
    live = analyze_live_accounts()

    # Guardian logs
    guardian = analyze_guardian_logs()

    # Strategy fitness from strategies.json
    strat_path = Path("data/strategies.json")
    if not strat_path.exists():
        strat_path = Path("/app/prometheus/data/strategies.json")
    strategies = {}
    if strat_path.exists():
        with open(strat_path) as f:
            strategies = json.load(f)

    # ── Build report ──

    report = []
    report.append(f"# PROMETHEUS Intelligence Report")
    report.append(f"**Generated**: {now}")
    report.append("")

    # ── Section 1: Prometheus Paper Trading ──
    report.append("## 1. Prometheus Paper Trading Performance")
    report.append("")
    report.append(f"| Metric | Value |")
    report.append(f"|--------|------:|")
    report.append(f"| Running since | {prom.get('first_ts', 'N/A')} |")
    report.append(f"| Last activity | {prom.get('last_ts', 'N/A')} |")
    report.append(f"| Starting balance | $100,000.00 |")
    report.append(f"| Cash | ${prom_cash:,.2f} |")
    report.append(f"| Position value | ${total_position_value:,.2f} |")
    report.append(f"| **Total equity** | **${prom_equity:,.2f}** |")
    report.append(f"| **Net P&L** | **${prom_pnl:+,.2f} ({prom_pnl/1000:+.2f}%)** |")
    report.append(f"| Total buys | {prom.get('total_buys', 0):,} |")
    report.append(f"| Total sells | {prom.get('total_sells', 0):,} (blocked: {prom.get('sell_blocked', 0):,}) |")
    report.append(f"| Assets held | {prom.get('held_count', 0)} |")
    report.append(f"| Winners/Losers | {winners}/{losers} |")
    report.append("")

    # Strategy usage
    if prom.get("strategies_used"):
        report.append("### Strategy Usage")
        report.append(f"| Strategy | Trades | Share |")
        report.append(f"|----------|-------:|------:|")
        total_strat = sum(prom["strategies_used"].values())
        for sid, count in sorted(prom["strategies_used"].items(), key=lambda x: x[1], reverse=True):
            pct = count / total_strat * 100 if total_strat > 0 else 0
            report.append(f"| {sid} | {count:,} | {pct:.1f}% |")
        report.append("")

    # Regime distribution
    if prom.get("regimes_seen"):
        report.append("### Regime Distribution")
        report.append(f"| Regime | Count | Share |")
        report.append(f"|--------|------:|------:|")
        total_reg = sum(prom["regimes_seen"].values())
        for regime, count in sorted(prom["regimes_seen"].items(), key=lambda x: x[1], reverse=True):
            pct = count / total_reg * 100 if total_reg > 0 else 0
            report.append(f"| {regime} | {count:,} | {pct:.1f}% |")
        report.append("")

    # Fitness updates
    if prom.get("fitness_updates"):
        report.append("### Strategy Fitness (Learning Progress)")
        latest_fitness = {}
        for fu in prom["fitness_updates"]:
            latest_fitness[fu["strategy"]] = fu
        report.append(f"| Strategy | Fitness | W/L | Avg P&L |")
        report.append(f"|----------|--------:|----:|--------:|")
        for sid, fu in sorted(latest_fitness.items(), key=lambda x: x[1]["fitness"], reverse=True):
            report.append(f"| {sid} | {fu['fitness']:.3f} | {fu['wins']}/{fu['losses']} | ${fu['avg_pnl']:+.4f} |")
        report.append("")

    # Strategy library state
    if strategies:
        report.append("### Strategy Library (Persisted)")
        report.append(f"| Strategy | Origin | Fitness | Trades | Win Rate |")
        report.append(f"|----------|--------|--------:|-------:|---------:|")
        for sid, meta in sorted(strategies.items(), key=lambda x: x[1].get("fitness_score", 0), reverse=True):
            report.append(
                f"| {sid} | {meta.get('origin', '?')} | {meta.get('fitness_score', 0):.3f} "
                f"| {meta.get('trade_count', 0)} | {meta.get('win_rate', 0)*100:.1f}% |"
            )
        report.append("")

    # Top positions
    if top_positions:
        report.append("### Top Positions (>$50)")
        report.append(f"| Asset | Value | Cost | P&L | Buys | Sells |")
        report.append(f"|-------|------:|-----:|----:|-----:|------:|")
        for p in top_positions[:15]:
            report.append(
                f"| {p['asset']} | ${p['value']:,.2f} | ${p['cost']:,.2f} "
                f"| ${p['pnl']:+,.2f} | {p['buys']} | {p['sells']} |"
            )
        report.append("")

    # ── Section 2: Live AVARA Accounts ──
    report.append("## 2. Live AVARA Trading Accounts")
    report.append("")

    if live.get("error"):
        report.append(f"> {live['error']}")
        report.append("")
    elif live.get("accounts"):
        combined_total = sum(a["total_usd"] for a in live["accounts"])
        report.append(f"**Combined portfolio value: ${combined_total:,.2f}**")
        report.append("")

        for acct in live["accounts"]:
            report.append(f"### {acct['name']}")
            report.append(f"| Asset | Balance | Price | USD Value |")
            report.append(f"|-------|--------:|------:|----------:|")
            for p in acct["positions"]:
                report.append(f"| {p['asset']} | {p['balance']:.6f} | ${p['price']:,.2f} | ${p['value']:,.2f} |")
            report.append(f"| **Total** | | | **${acct['total_usd']:,.2f}** |")
            report.append("")

            # Cash allocation
            report.append(f"- Cash: ${acct['cash_value']:,.2f} ({acct['cash_pct']:.1f}%)")
            report.append(f"- Crypto: ${acct['crypto_value']:,.2f} ({100 - acct['cash_pct']:.1f}%)")
            report.append("")

            # Target allocation drift
            if acct.get("drift"):
                report.append(f"#### Allocation vs Targets")
                report.append(f"| Asset | Target | Actual | Drift |")
                report.append(f"|-------|-------:|-------:|------:|")
                for d in acct["drift"]:
                    emoji = "" if abs(d["drift_pct"]) < 5 else " ⚠️" if abs(d["drift_pct"]) < 15 else " 🔴"
                    report.append(
                        f"| {d['asset']} | {d['target_pct']:.1f}% | {d['actual_pct']:.1f}% "
                        f"| {d['drift_pct']:+.1f}%{emoji} |"
                    )
                report.append("")

    # ── Section 3: Guardian Status ──
    report.append("## 3. Guardian Status")
    report.append("")

    if guardian.get("error"):
        report.append(f"> {guardian['error']}")
    else:
        report.append(f"- Log file: `{guardian.get('log_file', 'N/A')}`")
        report.append(f"- Heartbeats in sample: {guardian.get('heartbeat_count', 0)}")
        report.append("")

        if guardian.get("recent_fills"):
            report.append("### Recent Fills")
            for fill in guardian["recent_fills"][-5:]:
                report.append(f"- `{fill}`")
            report.append("")

        if guardian.get("recent_errors"):
            report.append("### Recent Errors")
            for err in guardian["recent_errors"][-5:]:
                report.append(f"- `{err}`")
            report.append("")

        if guardian.get("recent_regimes"):
            report.append("### Regime Detection")
            for reg in guardian["recent_regimes"][-5:]:
                report.append(f"- `{reg}`")
            report.append("")

    # ── Section 4: Observations & Suggestions ──
    report.append("## 4. Observations & Suggestions")
    report.append("")

    observations = []

    # Prometheus observations
    if prom.get("sell_blocked", 0) > 100:
        observations.append(
            "**Sell constraint was blocking trades**: "
            f"{prom['sell_blocked']:,} sells were blocked by min_hold_pct. "
            "This has been removed (set to 0.0) so Prometheus can now freely "
            "cycle capital through buy/sell rounds and actually learn from outcomes."
        )

    if prom_pnl < -5000:
        observations.append(
            f"**Prometheus is down ${abs(prom_pnl):,.0f}**: "
            "Most of this is unrealized. The system was accumulating positions "
            "without being able to sell (min_hold_pct constraint). Now that "
            "sells are unblocked, expect capital recycling to improve."
        )

    if prom.get("regimes_seen"):
        top_regime = max(prom["regimes_seen"], key=prom["regimes_seen"].get)
        observations.append(
            f"**Dominant market regime**: {top_regime} "
            f"({prom['regimes_seen'][top_regime]:,} observations). "
            "This tells us what the broad market is doing across 625 pairs."
        )

    if prom.get("strategies_used"):
        mom = prom["strategies_used"].get("momentum_v1", 0)
        mr = prom["strategies_used"].get("mean_reversion_v1", 0)
        total = mom + mr
        if total > 0:
            observations.append(
                f"**Strategy split**: momentum_v1 {mom/total*100:.0f}% vs "
                f"mean_reversion_v1 {mr/total*100:.0f}%. "
                "With fitness tracking now active, the selector will start "
                "favoring whichever strategy proves more profitable."
            )

    # Live account observations
    if live.get("accounts"):
        for acct in live["accounts"]:
            cash_pct = acct.get("cash_pct", 0)
            if cash_pct > 80:
                observations.append(
                    f"**{acct['name']} is {cash_pct:.0f}% cash**: "
                    f"${acct['cash_value']:,.0f} sitting idle. "
                    "The trading strategy is holding mostly USD. "
                    "This could mean the regime detector is in bear/defensive mode, "
                    "or the guardian hasn't placed buy orders recently."
                )

            for d in acct.get("drift", []):
                if abs(d["drift_pct"]) > 20:
                    observations.append(
                        f"**{acct['name']} {d['asset']} allocation drift**: "
                        f"Target {d['target_pct']:.0f}% but actual {d['actual_pct']:.1f}% "
                        f"(drift {d['drift_pct']:+.1f}%). "
                        "Consider rebalancing or adjusting capital allocation."
                    )

    for i, obs in enumerate(observations, 1):
        report.append(f"{i}. {obs}")
        report.append("")

    # ── Section 5: What Prometheus is Learning ──
    report.append("## 5. What Prometheus is Learning")
    report.append("")
    report.append("Prometheus is now tracking:")
    report.append("- **Strategy fitness scores** — updated on every completed sell trade")
    report.append("- **Win rate per strategy** — which strategy makes money more often")
    report.append("- **Average P&L per trade** — which strategy makes more per trade")
    report.append("- **Regime-strategy correlation** — which strategy works in which market regime")
    report.append("")
    report.append("The fitness feedback loop works like this:")
    report.append("1. Agent buys an asset using momentum_v1 or mean_reversion_v1")
    report.append("2. When the agent sells, the P&L is computed against cost basis")
    report.append("3. The strategy that initiated the buy gets scored (win/loss)")
    report.append("4. Strategy fitness = win_rate × (1 + tanh(avg_pnl × 100))")
    report.append("5. After 20+ trades per strategy, the selector starts favoring the winner")
    report.append("6. Fitness scores persist to `data/strategies.json` across restarts")
    report.append("")
    report.append("Evolution phases:")
    report.append("- **IMITATION** (0-1000 ticks): Clone top strategy")
    report.append("- **OPTIMIZATION** (1000-5000): Boost best performer's fitness advantage")
    report.append("- **RECOMBINATION** (5000-20000): Create blended variants")
    report.append("- **INVENTION** (20000-50000): Generate contrarian variants")
    report.append("- **MASTERY** (50000+): Prune underperformers")
    report.append("")

    # ── Section 6: System & Codebase Awareness ──
    report.append("## 6. System & Codebase Awareness")
    report.append("")
    try:
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from prometheus.infra.codebase_awareness import format_for_report, scan_codebase
        codebase_ctx = scan_codebase()
        report.extend(format_for_report(codebase_ctx))
    except Exception as e:
        report.append(f"*(Codebase scan failed: {e})*")
        report.append("")

    research_input_path = Path("data/research_input.json")
    if not research_input_path.exists():
        research_input_path = Path("/app/prometheus/data/research_input.json")

    research_entries = []
    if research_input_path.exists():
        try:
            with open(research_input_path) as f:
                rd = json.load(f)
            research_entries = rd.get("entries", [])
        except Exception:
            pass

    if research_entries:
        report.append("## 7. Research Context (From Derek)")
        report.append("")
        report.append("The following research has been provided and is being used by Prometheus:")
        report.append("")
        for entry in research_entries:
            report.append(f"### {entry.get('topic', 'Untitled')}")
            report.append(f"*Source: {entry.get('source', 'Derek')}* | "
                          f"*Provided: {entry.get('provided_at', 'unknown')}*")
            if entry.get("tags"):
                report.append(f"Tags: {', '.join(entry['tags'])}")
            report.append("")
            report.append(entry.get("content", ""))
            report.append("")
    else:
        report.append("## 7. Research Context")
        report.append("")
        report.append("No research has been provided yet. To feed research to Prometheus, "
                      "edit `data/research_input.json` with entries like:")
        report.append("```json")
        report.append(json.dumps({
            "last_updated": "2026-03-01",
            "entries": [{
                "topic": "Macro crypto outlook",
                "content": "Your research findings here...",
                "source": "CoinDesk / on-chain data / etc",
                "provided_at": "2026-03-01",
                "tags": ["macro", "btc", "altseason"],
            }],
        }, indent=2))
        report.append("```")
        report.append("")

    # ── Section 7: Research Requests (what Prometheus wants to know) ──
    report.append("## 8. Research Requests from Prometheus")
    report.append("")
    report.append("Prometheus is requesting deep research on the following topics. "
                  "Add your findings to `data/research_input.json` and Prometheus will "
                  "incorporate them into its decision-making.")
    report.append("")

    # Build market/avara state for research request generation
    try:
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from prometheus.infra.research import (
            generate_research_requests,
            format_requests_for_report,
        )

        market_state = {
            "regimes": prom.get("regimes_seen", {}),
            "dominant_regime": max(prom.get("regimes_seen", {"unknown": 1}),
                                  key=prom["regimes_seen"].get) if prom.get("regimes_seen") else "unknown",
        }

        avara_state_for_research = None
        if live.get("accounts"):
            avara_state_for_research = {
                "accounts": [
                    {
                        "name": a["name"],
                        "cash_pct": a.get("cash_pct", 0),
                        "cash_usd": a.get("cash_value", 0),
                        "total_usd": a.get("total_usd", 0),
                        "reallocation": {},
                    }
                    for a in live["accounts"]
                ],
            }

        prometheus_state = {
            "strategy_fitness": {},
            "top_assets": [
                {"asset": p["asset"], "value": p["value"], "pnl": p["pnl"]}
                for p in top_positions[:10] if p.get("pnl", 0) > 0
            ],
        }

        # Add fitness data from strategies.json
        for sid, meta in strategies.items():
            if meta.get("trade_count", 0) > 0:
                prometheus_state["strategy_fitness"][sid] = {
                    "trades": meta["trade_count"],
                    "win_rate": meta.get("win_rate", 0),
                    "fitness": meta.get("fitness_score", 0),
                }

        research_requests = generate_research_requests(
            market_state, avara_state_for_research, prometheus_state,
        )
        report.extend(format_requests_for_report(research_requests))

    except Exception as e:
        report.append(f"*(Research request generation failed: {e})*")
        report.append("")

    report.append("---")
    report.append(f"*Report generated by PROMETHEUS Intelligence System at {now}*")

    return "\n".join(report)


if __name__ == "__main__":
    report = generate_report()
    # Save to file
    report_path = Path("reports")
    report_path.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = report_path / f"prometheus_report_{ts}.md"
    with open(out_file, "w") as f:
        f.write(report)
    print(report)
    print(f"\nReport saved to: {out_file}")
