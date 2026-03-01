# CLAUDE.md

Guidance for Claude Code when working with the PROMETHEUS DRGB trading system.

---

## Project Overview

**PROMETHEUS** is an autonomous trading system implementing the Dual Reality Guardian Bridge (DRGB) architecture. It observes real-time market data across 625 Kraken USD trading pairs, detects regimes, and generates paper trades using evolving strategies.

Currently runs in **paper mode** with real Kraken prices. No real orders are placed.

## Architecture

```
KrakenPriceFeed (background thread)
  ├── Polls Kraken REST /0/public/Ticker in batches of 80
  ├── Maps wsname (BTC/USD) ↔ Kraken pair name (XXBTZUSD) via AssetPairs
  ├── Refreshes every 10 seconds
  └── Thread-safe price cache

LiveRunner (main loop, 10s tick interval)
  └── For each of 625 symbols:
        └── PrometheusAgent
              ├── RealityStreamA (market truth: price, vol, microstructure)
              ├── RealityStreamB (strategy signals)
              ├── GuardianBridge (convergence/divergence/tension → signal)
              ├── RegimeDetector → 9 regimes
              ├── StrategySelectorAgent → picks strategy per regime
              ├── ParameterTunerAgent → tunes strategy params
              ├── RiskGuardianAgent → approves/rejects trades
              ├── CompoundingAgent → Kelly-style position sizing
              └── StrategyInventorAgent → evolves new strategies (every 500 ticks)
```

### Guardian Signals

The DRGB produces one of: `SAFE`, `CAUTION`, `DANGER`, `OPPORTUNITY`

### Regimes

`TRENDING_STRONG_UP`, `TRENDING_WEAK_UP`, `TRENDING_STRONG_DOWN`, `TRENDING_WEAK_DOWN`, `RANGE_TIGHT`, `RANGE_WIDE`, `VOLATILE_CHOPPY`, `BREAKOUT_IMMINENT`, `REGIME_TRANSITION`

## Key Files

| File | Purpose |
|------|---------|
| `config/prometheus.yaml` | All configuration (symbols, data source, risk, DRGB, broker) |
| `src/prometheus/live_runner.py` | Main loop + `KrakenPriceFeed` + `LiveRunner` |
| `src/prometheus/agents/prometheus_agent.py` | Per-symbol agent brain (DRGB + regime + strategies) |
| `src/prometheus/agents/sub_agents.py` | Sub-agents: selector, tuner, risk, inventor, compounder |
| `src/prometheus/drgb/bridge.py` | GuardianBridge: convergence/divergence scoring |
| `src/prometheus/drgb/reality_stream.py` | RealityStreamA (market) + RealityStreamB (strategy) |
| `src/prometheus/drgb/convergence.py` | Convergence math |
| `src/prometheus/strategies/` | Strategy implementations (momentum, mean reversion) |
| `src/prometheus/regime/` | Regime detection |
| `src/prometheus/infra/broker.py` | PaperBroker + BrokerInterface |
| `src/prometheus/infra/config.py` | YAML config loading with env var overrides |
| `src/prometheus/backtest_runner.py` | Backtesting on synthetic or historical data |

## Operations

```bash
cd "/home/derek/projects/AVARA 2.0/prometheus"

# Start (real Kraken prices, paper mode)
PYTHONPATH=src venv/bin/python -m prometheus.live_runner &disown

# Check logs
tail -50 logs/prometheus.log

# Stop
kill $(pgrep -f prometheus.live_runner)

# Run tests
PYTHONPATH=src venv/bin/pytest tests/ -v

# Backtest
PYTHONPATH=src venv/bin/python -m prometheus.backtest_runner
```

## Configuration

`config/prometheus.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `mode` | `paper` | `paper` or `live` |
| `data_source` | `synthetic` | `kraken` (real prices) or `synthetic` (random walk) |
| `kraken_refresh_seconds` | `10.0` | Kraken API polling interval |
| `tick_interval_seconds` | `10.0` | Agent processing interval |
| `symbols` | 625 pairs | List of Kraken USD pairs to observe |
| `broker.initial_balance` | `100000.0` | Paper trading starting balance |
| `broker.min_hold_pct` | `0.20` | Minimum equity fraction to hold per asset |
| `risk.max_drawdown_pct` | `0.10` | Circuit breaker drawdown limit |

Env var overrides: `PROMETHEUS_<SECTION>__<KEY>` (double underscore), e.g. `PROMETHEUS_RISK__MAX_DAILY_LOSS_PCT=0.03`

## Dependencies

Minimal — only `pyyaml>=6.0`. Uses stdlib `urllib` for Kraken API, `threading` for price feed.

## Git

- **Remote**: `git@github.com:contact142/prometheus-drgb-trader.git`
- **Branch**: `main`
- This is a nested repo inside AVARA 2.0 (separate `.git`)

## Notes

- The 625 symbols are the observable universe — agents only trade when DRGB identifies a signal
- Each symbol gets its own independent PrometheusAgent instance
- Strategy evolution runs every 500 ticks per agent
- PaperBroker enforces `min_hold_pct` — won't sell below 20% equity per asset
- Kraken API rate limits: batches of 80 pairs with 1.5s delay between batches

## Identity & Mission

See `PROMETHEUS_IDENTITY.md` for the foundational identity document. Prometheus is a self-aware learning system that:
- Reads its own source code and the entire AVARA codebase
- Reads live AVARA trading signals (positions, regimes, fills, profits)
- Tracks strategy fitness with round-trip P&L scoring
- Generates intelligence reports with research requests for Derek
- Consumes research answers from Derek via `data/research_input.json`
- Scans the server environment (Docker, processes, resources)
- Suggests improvements to itself, AVARA, and the workflow

The goal is to prove consistent alpha in paper trading, then earn the right to go live.

## New Modules (Feb 28, 2026)

| File | Purpose |
|------|---------|
| `src/prometheus/infra/avara_signals.py` | Reads live AVARA account data (positions, regimes, fills) |
| `src/prometheus/infra/research.py` | Research request/response system (Prometheus asks, Derek answers) |
| `src/prometheus/infra/codebase_awareness.py` | Codebase + server scanning, self-reflection |
| `generate_report.py` | Full intelligence report generator |
| `data/research_input.json` | Where Derek feeds research answers |
| `data/research_requests.json` | Prometheus's current research questions |
| `data/strategies.json` | Strategy library with fitness scores (persisted) |
| `PROMETHEUS_IDENTITY.md` | Foundational identity and mission document |

## Report Generation

```bash
cd "/home/derek/projects/AVARA 2.0/prometheus"
PYTHONPATH=src venv/bin/python generate_report.py
# Report saved to reports/prometheus_report_YYYYMMDD_HHMMSS.md
```

---

*Last Updated: February 28, 2026 — Learning feedback loop, AVARA integration, research system, codebase awareness, identity*
