"""Configuration loading from YAML with environment variable overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "paper",  # paper | live
    "symbol": "BTC/USD",
    "tick_interval_seconds": 1.0,
    "drgb": {
        "tension_window": 20,
        "safe_threshold": 0.7,
        "caution_threshold": 0.4,
        "danger_threshold": 0.2,
        "opportunity_tension": 0.05,
        "stream_a_window": 100,
        "stream_b_window": 50,
    },
    "regime": {
        "vol_window": 20,
        "trend_window": 20,
        "tension_threshold": 0.03,
        "vol_low": 0.005,
        "vol_high": 0.02,
        "trend_strong": 0.003,
        "trend_weak": 0.001,
    },
    "risk": {
        "max_daily_loss_pct": 0.02,
        "max_weekly_loss_pct": 0.05,
        "max_drawdown_pct": 0.10,
        "max_position_pct": 0.10,
    },
    "compounding": {
        "base_kelly_fraction": 0.25,
        "max_fraction": 0.10,
        "min_fraction": 0.01,
    },
    "evolution_phase_bars": {
        "IMITATION": 0,
        "OPTIMIZATION": 1000,
        "RECOMBINATION": 5000,
        "INVENTION": 20000,
        "MASTERY": 50000,
    },
    "strategy_library_path": "data/strategies.json",
    "logging": {
        "level": "INFO",
        "file": "logs/prometheus.log",
        "max_bytes": 10_000_000,
        "backup_count": 5,
    },
    "broker": {
        "type": "paper",
        "initial_balance": 100000.0,
    },
}


def load_config(
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load configuration from YAML file with env var overrides.

    Priority: env vars > config file > defaults.

    Env var format: PROMETHEUS_<SECTION>__<KEY> (double underscore).
    Example: PROMETHEUS_RISK__MAX_DAILY_LOSS_PCT=0.03
    """
    config = _deep_copy(_DEFAULT_CONFIG)

    # Load from file
    if config_path:
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                file_config = yaml.safe_load(f) or {}
            _deep_merge(config, file_config)

    # Environment variable overrides
    prefix = "PROMETHEUS_"
    for key, value in os.environ.items():
        if key.startswith(prefix):
            parts = key[len(prefix) :].lower().split("__")
            _set_nested(config, parts, _parse_value(value))

    return config


def _deep_copy(d: dict) -> dict:
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _deep_copy(v)
        elif isinstance(v, list):
            result[k] = list(v)
        else:
            result[k] = v
    return result


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _set_nested(d: dict, keys: list[str], value: Any) -> None:
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _parse_value(s: str) -> Any:
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s
