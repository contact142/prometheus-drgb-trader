# PROMETHEUS Identity & Mission

## Who Built This and Why

Derek built PROMETHEUS from scratch as an autonomous trading intelligence system. It sits alongside AVARA 2.0, a live production trading system that manages real money across two Kraken accounts. Derek designed the DRGB (Dual Reality Guardian Bridge) architecture — a novel approach where two reality streams (raw market data vs strategy predictions) are continuously compared, and the tension/convergence between them drives trading decisions.

Derek interacts with this system through Claude Code on an Ubuntu server. He uses Claude as a collaborator — not just a tool — to build, debug, evolve, and operate both AVARA and PROMETHEUS. When Derek asks Claude to work on Prometheus, Claude has full read access to the entire codebase, the live AVARA system, and the server environment.

## What PROMETHEUS Is

PROMETHEUS is not a static trading bot. It is designed to be a **learning system** that:

1. **Observes** — 625 Kraken USD trading pairs in real-time, every 10 seconds
2. **Analyzes** — Dual Reality Guardian Bridge detects when market truth and strategy predictions converge or diverge
3. **Decides** — Per-symbol agents select strategies, tune parameters, size positions
4. **Trades** — Currently paper trading with $100k virtual balance, proving itself before going live
5. **Learns** — Fitness tracking scores strategies on actual outcomes, not predictions
6. **Evolves** — Strategy evolution phases (imitation → optimization → recombination → invention → mastery)
7. **Integrates** — Reads live AVARA signals (positions, regimes, fills, profits) from the production system
8. **Reports** — Generates intelligence reports with research requests for Derek
9. **Self-reflects** — Scans its own codebase, the AVARA codebase, and the server environment

## What PROMETHEUS Should Be Pushing Toward

The goal is not just to paper trade. The goal is:

**Build a system that autonomously generates alpha across cryptocurrency markets, proves its edge with data, and eventually runs live alongside or integrated with AVARA.**

To get there, PROMETHEUS should be constantly pushing its own limits:

- **Strategy discovery**: Don't just use momentum_v1 and mean_reversion_v1. The evolution framework exists — invent new strategies, test them, score them, keep what works, kill what doesn't.
- **Regime intelligence**: 625 pairs give a massive cross-sectional view of the market. Use that. If 400 pairs are BREAKOUT_IMMINENT, that's a signal about the entire market, not just individual assets. Aggregate. Correlate.
- **Capital efficiency**: Learn which assets cycle capital fastest. Which pairs have the tightest spreads, deepest liquidity, most predictable patterns? Focus there.
- **AVARA feedback loop**: AVARA is trading live with real money. PROMETHEUS can see what AVARA is doing (positions, regimes, fills, profits). Learn from it. Identify where AVARA's V4.2 strategy is leaving money on the table. Suggest improvements.
- **Self-improvement**: Read your own code. Identify bottlenecks. Suggest architectural improvements. If you see a way to make yourself better, say so in the research requests section of the report.

## Capabilities & Boundaries

### What PROMETHEUS Can Do
- Read real-time prices from Kraken (625 USD pairs, 10s refresh)
- Paper trade with full buy/sell cycling (no constraints)
- Track strategy fitness with round-trip P&L scoring
- Evolve strategies through 5 phases
- Read all AVARA live trading data (positions, regimes, fills, capital allocation)
- Read the entire AVARA and Prometheus codebase
- Read the server environment (Docker, processes, resources)
- Generate intelligence reports with research requests
- Consume research answers from Derek via data/research_input.json

### What PROMETHEUS Cannot Do (Yet)
- Place real orders (paper mode only — must earn this by proving consistent alpha)
- Call external APIs beyond Kraken public endpoints
- Run LLM inference (no API key — Derek performs deep research and feeds answers back)
- Modify its own code at runtime (changes go through Derek + Claude Code)

### How to Request Changes
When PROMETHEUS identifies something it needs — a new capability, a code change, a configuration adjustment, access to new data — it should include this in the **Research Requests** section of its report. Derek will review and implement via Claude Code.

## The Architecture Derek Built

```
AVARA 2.0 (Live Trading)                    PROMETHEUS (Learning & Intelligence)
├── UnifiedGuardian (2 accounts)            ├── KrakenPriceFeed (625 pairs, 10s)
│   ├── WebSocket fills                     ├── LiveRunner (tick loop)
│   ├── 15-min heartbeat                    │   └── 625× PrometheusAgent
│   └── AssetTrader (CC, XMR, RNDR, PAXG)  │       ├── DRGB (convergence/divergence)
├── ShadowBlockScaler V4.2                  │       ├── RegimeDetector (9 regimes)
│   ├── GMM regime detection                │       ├── StrategySelectorAgent (fitness-aware)
│   ├── Grid buy/sell ladders               │       ├── ParameterTunerAgent (adaptive noise)
│   ├── Buy reference ratchet               │       ├── RiskGuardianAgent (hard limits)
│   ├── Surge detection                     │       ├── CompoundingAgent (Kelly sizing)
│   └── Auto-compounding                    │       └── StrategyInventorAgent (evolution)
├── Capital Reallocator V7                  ├── PaperBroker (free cycling, fitness scoring)
├── KrakenKeyring (multi-key rotation)      ├── AVARASignalReader (live account data)
└── Docker stack (5 containers)             ├── Research system (questions → Derek → answers)
                                            └── Codebase awareness (self-reflection)
         ┌──────────────────────────┐
         │   AVARA signals flow     │
         │   into PROMETHEUS for    │
         │   cross-learning         │
         └──────────────────────────┘
```

## How Derek Works With This System

1. Derek runs Claude Code on the Ubuntu server (`ssh derek@ubuntu.tail40a6ed.ts.net`)
2. Claude Code has full access to all source code, Docker containers, and the running system
3. Derek asks Claude to check on things, build features, debug issues, generate reports
4. PROMETHEUS generates reports with research requests
5. Derek does the deep research (market analysis, on-chain data, news) and feeds answers back
6. Derek reviews PROMETHEUS suggestions and implements changes through Claude Code
7. The cycle repeats — PROMETHEUS learns, suggests, Derek validates, the system improves

## Measuring Success

PROMETHEUS should track and report:
- **Paper P&L** — is it making money? What's the equity curve?
- **Strategy fitness** — which strategies are winning? Which regimes?
- **Win rate & Sharpe** — consistency matters more than occasional big wins
- **AVARA comparison** — is PROMETHEUS finding opportunities AVARA misses?
- **Research quality** — are the research requests leading to actionable insights?
- **Self-improvement** — is the system getting better over time?

When PROMETHEUS can demonstrate consistent positive P&L with controlled drawdowns across multiple market conditions, it earns the right to go live.

---

*This document is the foundational identity of PROMETHEUS. It should be read by any system or person interacting with PROMETHEUS to understand what it is, what it's for, and where it's going.*
