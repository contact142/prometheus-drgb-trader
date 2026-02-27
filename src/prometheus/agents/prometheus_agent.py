"""PROMETHEUS Agent: main coordination loop.

Orchestrates all sub-agents, DRGB, regime detection,
and the strategy library into a coherent decision pipeline.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..drgb import GuardianBridge, GuardianSignal
from ..drgb.reality_stream import StrategySignal, TickData
from ..regime import Regime, RegimeDetector
from ..strategies import (
    BaseStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    StrategyLibrary,
    StrategyMetadata,
)
from .sub_agents import (
    CompoundingAgent,
    EvolutionPhase,
    ParameterTunerAgent,
    RiskGuardianAgent,
    StrategyInventorAgent,
    StrategySelectorAgent,
)

logger = logging.getLogger(__name__)


@dataclass
class TradeInstruction:
    """Output from the agent decision loop."""

    timestamp: float
    strategy_id: str
    direction: float  # -1 to 1
    size_fraction: float
    confidence: float
    regime: str
    guardian_signal: str
    convergence: float
    metadata: dict[str, Any] = field(default_factory=dict)


class PrometheusAgent:
    """Main PROMETHEUS agent coordinating all sub-systems.

    Args:
        config: Configuration dict. Keys:
            - evolution_phase_bars: dict mapping phase -> bar threshold.
            - risk: risk parameters.
            - strategy_library_path: path to strategy JSON.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}

        # Core systems
        self.drgb = GuardianBridge(
            **config.get("drgb", {}),
        )
        self.regime_detector = RegimeDetector(
            **config.get("regime", {}),
        )

        # Sub-agents
        self.strategy_selector = StrategySelectorAgent(
            config.get("regime_strategy_map"),
        )
        self.parameter_tuner = ParameterTunerAgent(
            config.get("perturbation_scale", 0.05),
        )
        self.risk_guardian = RiskGuardianAgent(
            **config.get("risk", {}),
        )
        self.strategy_inventor = StrategyInventorAgent()
        self.compounding_agent = CompoundingAgent(
            **config.get("compounding", {}),
        )

        # Strategy library
        lib_path = config.get("strategy_library_path", "data/strategies.json")
        self.strategy_library = StrategyLibrary(lib_path)

        # Live strategy instances
        self._strategy_instances: dict[str, BaseStrategy] = {
            "momentum_v1": MomentumStrategy(),
            "mean_reversion_v1": MeanReversionStrategy(),
        }

        # Seed the library if empty
        if not self.strategy_library.list_all():
            self.strategy_library.register(
                StrategyMetadata(
                    strategy_id="momentum_v1",
                    name="Momentum V1",
                    origin="human_created",
                )
            )
            self.strategy_library.register(
                StrategyMetadata(
                    strategy_id="mean_reversion_v1",
                    name="Mean Reversion V1",
                    origin="human_created",
                )
            )

        # State
        self._tick_count = 0
        self._trade_history: list[TradeInstruction] = []
        self._risk_state: dict[str, float] = {
            "daily_pnl_pct": 0.0,
            "weekly_pnl_pct": 0.0,
            "drawdown_pct": 0.0,
        }

        # Evolution phase thresholds (configurable)
        self._phase_thresholds = config.get(
            "evolution_phase_bars",
            {
                "IMITATION": 0,
                "OPTIMIZATION": 1000,
                "RECOMBINATION": 5000,
                "INVENTION": 20000,
                "MASTERY": 50000,
            },
        )

    def process_tick(self, tick_data: TickData) -> TradeInstruction | None:
        """Main decision loop. Process one tick of market data.

        Steps:
        1. Update DRGB with tick + strategy signals.
        2. Detect regime.
        3. Select strategy.
        4. Tune parameters.
        5. Compute position size.
        6. Run risk check.
        7. Output trade instruction (if approved).
        8. Log and update learning buffers.
        9. Background evolution.

        Returns:
            TradeInstruction if a trade is generated, else None.
        """
        self._tick_count += 1

        # 1. Generate strategy signals from all active strategies
        # (using previous tick's market state for signals to avoid look-ahead)
        strategy_signals = self._generate_strategy_signals(tick_data)

        # 2. Update DRGB
        drgb_state = self.drgb.update(tick_data, strategy_signals)

        # 3. Detect regime
        a_state = drgb_state["a_state"]
        regime = self.regime_detector.detect(a_state, drgb_state)

        # 4. Select strategy
        strategy_id = self.strategy_selector.select(
            regime, drgb_state, self._recent_history()
        )

        # 5. Tune parameters
        strategy_instance = self._strategy_instances.get(strategy_id)
        if strategy_instance:
            current_params = strategy_instance.get_params()
            tuned_params = self.parameter_tuner.tune(
                current_params, drgb_state
            )
            strategy_instance.set_params(tuned_params)

            # Generate signal from selected strategy
            signal = strategy_instance.generate_signal(
                a_state, regime.value, drgb_state
            )
        else:
            signal = {"direction": 0.0, "confidence": 0.0}

        # 6. Compute position size
        size_fraction = self.compounding_agent.calculate_size(
            drgb_state, regime
        )

        # 7. Risk check
        approved = self.risk_guardian.approve(
            strategy_id,
            tuned_params if strategy_instance else {},
            size_fraction,
            drgb_state,
            self._risk_state,
        )

        trade: TradeInstruction | None = None

        if approved and abs(signal.get("direction", 0.0)) > 0.1:
            trade = TradeInstruction(
                timestamp=tick_data.timestamp,
                strategy_id=strategy_id,
                direction=signal["direction"],
                size_fraction=size_fraction,
                confidence=signal["confidence"],
                regime=regime.value,
                guardian_signal=drgb_state["signal"].value
                if isinstance(drgb_state["signal"], GuardianSignal)
                else str(drgb_state["signal"]),
                convergence=drgb_state["convergence"],
                metadata={
                    "tick_count": self._tick_count,
                    "divergence": drgb_state["divergence"],
                    "tension": drgb_state["tension"],
                },
            )
            self._trade_history.append(trade)
            logger.info(
                "Trade generated: %s %.2f @ size=%.4f (regime=%s, signal=%s)",
                strategy_id,
                signal["direction"],
                size_fraction,
                regime.value,
                drgb_state["signal"],
            )
        else:
            logger.debug(
                "No trade: approved=%s direction=%.2f (regime=%s, signal=%s)",
                approved,
                signal.get("direction", 0.0),
                regime.value,
                drgb_state["signal"],
            )

        # 9. Background evolution (periodic)
        if self._tick_count % 500 == 0:
            self._run_evolution(drgb_state)

        return trade

    def _generate_strategy_signals(
        self, tick_data: TickData
    ) -> list[StrategySignal]:
        """Run all active strategies to produce signals for DRGB StreamB."""
        signals = []
        a_state = self.drgb.stream_a.state()
        regime = (
            self.regime_detector.recent_regimes[-1].value
            if self.regime_detector.recent_regimes
            else "RANGE_TIGHT"
        )
        drgb_state = {
            "convergence": 0.5,
            "divergence": 0.5,
            "tension": 0.0,
            "signal": GuardianSignal.SAFE,
        }

        for sid, strategy in self._strategy_instances.items():
            sig = strategy.generate_signal(a_state, regime, drgb_state)
            signals.append(
                StrategySignal(
                    strategy_id=sid,
                    timestamp=tick_data.timestamp,
                    direction=sig.get("direction", 0.0),
                    confidence=sig.get("confidence", 0.0),
                )
            )
        return signals

    def _recent_history(self, n: int = 50) -> list[dict[str, Any]]:
        """Recent trade history as dicts."""
        return [
            {
                "strategy_id": t.strategy_id,
                "direction": t.direction,
                "confidence": t.confidence,
                "regime": t.regime,
            }
            for t in self._trade_history[-n:]
        ]

    def _get_evolution_phase(self) -> EvolutionPhase:
        """Determine current evolution phase based on tick count."""
        phase = EvolutionPhase.IMITATION
        for p_name, threshold in sorted(
            self._phase_thresholds.items(), key=lambda x: x[1]
        ):
            if self._tick_count >= threshold:
                phase = EvolutionPhase(p_name)
        return phase

    def _run_evolution(self, drgb_state: dict[str, Any]) -> None:
        """Run background strategy evolution."""
        phase = self._get_evolution_phase()
        library_data = [
            {
                "strategy_id": m.strategy_id,
                "fitness_score": m.fitness_score,
                "origin": m.origin,
            }
            for m in self.strategy_library.list_all()
        ]
        self.strategy_inventor.evolve_strategies(
            library_data, drgb_state, phase
        )
        logger.info(
            "Evolution step: phase=%s, library_size=%d",
            phase.value,
            len(library_data),
        )

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def update_risk_state(self, risk_state: dict[str, float]) -> None:
        """Update external risk metrics."""
        self._risk_state.update(risk_state)
