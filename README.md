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

## Quickstart

```bash
# Clone
git clone https://github.com/contact142/prometheus-drgb-trader.git
cd prometheus-drgb-trader

# Install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run tests
PYTHONPATH=src pytest tests/ -v

# Run backtest (synthetic data)
PYTHONPATH=src python -m prometheus.backtest_runner

# Run live paper mode
PYTHONPATH=src python -m prometheus.live_runner
```

## Configuration

Edit `config/prometheus.yaml` or use environment variables:
```bash
export PROMETHEUS_RISK__MAX_DAILY_LOSS_PCT=0.03
export PROMETHEUS_MODE=live
```

## Plug-in Points

| Component | File | What to replace |
|-----------|------|----------------|
| **Data Feed** | `src/prometheus/live_runner.py` | `_get_tick()` method |
| **Broker** | `src/prometheus/infra/broker.py` | Implement `BrokerInterface` |
| **Convergence Math** | `src/prometheus/drgb/convergence.py` | New `ConvergenceStrategy` class |
| **RL Agents** | `src/prometheus/agents/sub_agents.py` | Replace heuristic `select()`/`tune()` methods |
| **Strategy Logic** | `src/prometheus/strategies/` | Add new `BaseStrategy` subclasses |

## Deployment

See `deploy/UBUNTU_SETUP.md` for Ubuntu server deployment guide.

## License

MIT
