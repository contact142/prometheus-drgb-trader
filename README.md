# PROMETHEUS: Dual Reality Guardian Bridge Trading System

An autonomous trading system implementing the **Dual Reality Guardian Bridge (DRGB)** architecture—a framework for continuously aligning market truth with strategic models through real-time divergence monitoring and adaptive control.

## Architecture

### Dual Reality Guardian Bridge (DRGB)

```
RealityStreamA (Market Truth)          RealityStreamB (Strategic Models)
├─ Tick/OHLCV data                     ├─ Strategy signals
├─ Order book (if available)           ├─ Indicators
├─ Volume & microstructure             └─ Regime classification
└─ Raw market facts
         │                                      │
         └──────────────┬───────────────────────┘
                  GuardianBridge
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   Convergence     Divergence     Bridge Tension
   Score [0,1]    Score [0,1]    (2nd derivative)
        │               │               │
        └───────────────┼───────────────┘
                        │
                  Guardian Signal
            {SAFE | CAUTION | DANGER | OPPORTUNITY}
```

### Multi-Agent Brain

- **StrategySelectorAgent**: Chooses strategy based on regime + DRGB state
- **ParameterTunerAgent**: Continuous parameter optimization
- **RiskGuardianAgent**: Approves/rejects trades against risk limits
- **StrategyInventorAgent**: Evolves new strategies over time
- **CompoundingAgent**: Kelly-style position sizing

### Regime Detection

Classifies markets into: `TRENDING_STRONG_UP`, `TRENDING_WEAK_UP`, `TRENDING_STRONG_DOWN`, `TRENDING_WEAK_DOWN`, `RANGE_TIGHT`, `RANGE_WIDE`, `VOLATILE_CHOPPY`, `BREAKOUT_IMMINENT`, `REGIME_TRANSITION`.

## Data Sources

| Source | Config | Description |
|--------|--------|-------------|
| **Kraken** | `data_source: kraken` | Real-time prices from Kraken REST API (625 USD pairs) |
| **Synthetic** | `data_source: synthetic` | Random walk price generation for offline testing |

The Kraken feed fetches ticker data in batches every 10 seconds via a background thread. Each symbol gets real bid/ask/last/volume/high/low data. The system can observe all 625 Kraken USD pairs simultaneously—agents only trade when the DRGB identifies a signal worth acting on.

## Quickstart

```bash
# Clone
git clone git@github.com:contact142/prometheus-drgb-trader.git
cd prometheus-drgb-trader

# Install
python3 -m venv venv && source venv/bin/activate
pip install -e .

# Run tests
PYTHONPATH=src pytest tests/ -v

# Run backtest (synthetic data)
PYTHONPATH=src python -m prometheus.backtest_runner

# Run live paper mode (real Kraken prices, no real orders)
PYTHONPATH=src python -m prometheus.live_runner
```

## Configuration

Edit `config/prometheus.yaml`:

```yaml
mode: paper                    # paper | live
data_source: kraken            # kraken | synthetic
kraken_refresh_seconds: 10.0   # how often to poll Kraken REST API
tick_interval_seconds: 10.0    # agent processing interval

symbols:
  - BTC/USD
  - ETH/USD
  - XMR/USD
  # ... up to 625 Kraken USD pairs

broker:
  type: paper
  initial_balance: 100000.0
  min_hold_pct: 0.20           # always hold at least 20% equity per asset
```

Environment variable overrides:
```bash
export PROMETHEUS_RISK__MAX_DAILY_LOSS_PCT=0.03
export PROMETHEUS_MODE=live
export PROMETHEUS_DATA_SOURCE=kraken
```

## Plug-in Points

| Component | File | What to replace |
|-----------|------|----------------|
| **Data Feed** | `src/prometheus/live_runner.py` | `KrakenPriceFeed` or `_get_tick()` method |
| **Broker** | `src/prometheus/infra/broker.py` | Implement `BrokerInterface` for real execution |
| **Convergence Math** | `src/prometheus/drgb/convergence.py` | New `ConvergenceStrategy` class |
| **RL Agents** | `src/prometheus/agents/sub_agents.py` | Replace heuristic `select()`/`tune()` methods |
| **Strategy Logic** | `src/prometheus/strategies/` | Add new `BaseStrategy` subclasses |

## Deployment

See `deploy/UBUNTU_SETUP.md` for Ubuntu server deployment guide.

## License

MIT
