"""Research request/response system for Prometheus.

Prometheus generates research questions based on what it observes in the
market and AVARA's live trading. Derek performs the deep research and
feeds answers back via data/research_input.json.

Prometheus reads those answers and incorporates them into its decision-making.

Flow:
  1. Prometheus observes markets (625 pairs) + AVARA live signals
  2. generate_research_requests() produces questions for the report
  3. Derek researches and writes answers to data/research_input.json
  4. Prometheus reads answers via get_research_context()
  5. Answers inform regime detection, strategy selection, risk tuning
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_INPUT_PATH = Path("data/research_input.json")
RESEARCH_REQUESTS_PATH = Path("data/research_requests.json")


@dataclass
class ResearchRequest:
    """A question Prometheus wants researched."""

    question: str
    category: str  # "macro" | "asset" | "strategy" | "risk" | "technical"
    priority: str  # "high" | "medium" | "low"
    context: str  # why Prometheus is asking
    asset: str | None = None  # specific asset if relevant
    generated_at: float = field(default_factory=time.time)


@dataclass
class ResearchEntry:
    """An answer provided by Derek."""

    topic: str
    content: str
    source: str = ""  # where the info came from
    provided_at: str = ""
    expires_at: str | None = None  # optional TTL
    tags: list[str] = field(default_factory=list)


def get_research_context() -> list[dict[str, Any]]:
    """Read research answers provided by Derek.

    Returns list of research entries that Prometheus can use
    to inform its decisions.
    """
    path = RESEARCH_INPUT_PATH
    if not path.exists():
        return []

    try:
        with open(path) as f:
            data = json.load(f)
        entries = data.get("entries", [])
        if entries:
            logger.info("Loaded %d research entries from Derek", len(entries))
        return entries
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to read research input: %s", e)
        return []


def generate_research_requests(
    market_state: dict[str, Any],
    avara_state: dict[str, Any] | None = None,
    prometheus_state: dict[str, Any] | None = None,
) -> list[ResearchRequest]:
    """Generate research questions based on current observations.

    Prometheus looks at what's happening and asks about things
    it can't determine from price data alone.
    """
    requests: list[ResearchRequest] = []

    # ── Market-driven questions ──

    regimes = market_state.get("regimes", {})
    top_regime = market_state.get("dominant_regime", "")

    if top_regime == "BREAKOUT_IMMINENT":
        requests.append(ResearchRequest(
            question="Multiple assets showing BREAKOUT_IMMINENT regime across 625 pairs. "
                     "Is there a macro catalyst driving this? Fed announcement, ETF news, "
                     "major protocol upgrade, or broad market event?",
            category="macro",
            priority="high",
            context=f"Dominant regime is BREAKOUT_IMMINENT ({regimes.get('BREAKOUT_IMMINENT', 0)} observations). "
                    "Need to know if this is a real breakout or false signal to adjust position sizing.",
        ))

    if regimes.get("TRENDING_STRONG_DOWN", 0) > 50:
        requests.append(ResearchRequest(
            question="Seeing strong downtrends across multiple pairs. "
                     "Any specific bearish catalysts? Exchange hacks, regulatory news, "
                     "major liquidation events, or stablecoin depegs?",
            category="macro",
            priority="high",
            context="TRENDING_STRONG_DOWN is elevated. Need to assess if this is "
                    "systemic risk or isolated asset weakness.",
        ))

    # ── AVARA-driven questions ──

    if avara_state:
        for acct in avara_state.get("accounts", []):
            cash_pct = acct.get("cash_pct", 0)
            if cash_pct > 85:
                requests.append(ResearchRequest(
                    question=f"{acct['name']} is {cash_pct:.0f}% cash. The grid strategy "
                             f"is holding mostly USD despite bull regime detection. "
                             f"Should we be more aggressive deploying capital? "
                             f"What's the near-term outlook for CC, RNDR, XMR?",
                    category="strategy",
                    priority="medium",
                    context=f"Account {acct['name']} has ${acct.get('cash_usd', 0):,.0f} idle. "
                            f"AVARA regime: bull for CC/XMR/RNDR. Grid is conservative.",
                ))

            # Check for evacuating assets
            realloc = acct.get("reallocation", {})
            for asset, entry in realloc.get("entries", {}).items():
                if entry.get("state") == "evacuating":
                    requests.append(ResearchRequest(
                        question=f"{acct['name']} {asset} is being evacuated by the reallocator "
                                 f"(triggered at {entry.get('trigger_loss_pct', 0)*100:.1f}% loss). "
                                 f"Is this asset in a temporary dip or sustained downtrend? "
                                 f"Should we let the evacuation complete or intervene?",
                        category="risk",
                        priority="high",
                        asset=asset,
                        context=f"Capital reallocator auto-triggered evacuation. "
                                f"Regime at evac: {entry.get('source_regime_at_evac', 'unknown')}",
                    ))

    # ── Performance-driven questions ──

    if prometheus_state:
        fitness = prometheus_state.get("strategy_fitness", {})
        for sid, stats in fitness.items():
            if stats.get("trades", 0) > 50 and stats.get("win_rate", 0) < 0.4:
                requests.append(ResearchRequest(
                    question=f"Strategy '{sid}' has a {stats['win_rate']*100:.0f}% win rate "
                             f"after {stats['trades']} trades. Should we adjust its parameters, "
                             f"restrict it to specific regimes, or phase it out?",
                    category="strategy",
                    priority="medium",
                    context=f"Fitness: {stats.get('fitness', 0):.3f}, "
                            f"Avg P&L: ${stats.get('avg_pnl', 0):.4f}",
                ))

        # Top-performing assets
        top_assets = prometheus_state.get("top_assets", [])
        if top_assets:
            names = ", ".join(a["asset"] for a in top_assets[:5])
            requests.append(ResearchRequest(
                question=f"Prometheus paper trading top performers: {names}. "
                         f"Are any of these worth adding to the live AVARA portfolio? "
                         f"What's the liquidity, market cap, and risk profile?",
                category="asset",
                priority="medium",
                context="These assets showed positive P&L in paper trading across "
                        "625 Kraken USD pairs.",
            ))

    # ── Standing questions (always relevant) ──

    requests.append(ResearchRequest(
        question="What is the current macro crypto outlook? BTC dominance trend, "
                 "altcoin season indicators, DeFi TVL direction, stablecoin flows?",
        category="macro",
        priority="low",
        context="Standing question for overall market context.",
    ))

    # Save requests to file for the report
    _save_requests(requests)

    return requests


def _save_requests(requests: list[ResearchRequest]) -> None:
    """Persist research requests so the report generator can include them."""
    RESEARCH_REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": time.time(),
        "requests": [
            {
                "question": r.question,
                "category": r.category,
                "priority": r.priority,
                "context": r.context,
                "asset": r.asset,
            }
            for r in requests
        ],
    }
    with open(RESEARCH_REQUESTS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def format_requests_for_report(requests: list[ResearchRequest]) -> list[str]:
    """Format research requests as markdown lines for the report."""
    lines = []
    by_priority = {"high": [], "medium": [], "low": []}
    for r in requests:
        by_priority.get(r.priority, by_priority["low"]).append(r)

    for priority in ["high", "medium", "low"]:
        items = by_priority[priority]
        if items:
            lines.append(f"### {priority.upper()} Priority")
            lines.append("")
            for i, r in enumerate(items, 1):
                asset_tag = f" [{r.asset}]" if r.asset else ""
                lines.append(f"**{i}. [{r.category.upper()}]{asset_tag}** {r.question}")
                lines.append(f"   - *Context*: {r.context}")
                lines.append("")

    return lines
