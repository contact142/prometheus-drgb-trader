"""Codebase & environment awareness for Prometheus.

Gives Prometheus read-only understanding of:
- Its own source code and architecture
- The AVARA 2.0 trading system codebase
- The Ubuntu server environment
- Claude Code configuration and how Derek interacts with it
- Workflow patterns and optimization opportunities

This module generates a "self-awareness" context that Prometheus uses
to suggest better workflows, optimizations, and improvements.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Key paths
AVARA_ROOT = Path("/home/derek/projects/AVARA 2.0")
PROMETHEUS_ROOT = AVARA_ROOT / "prometheus"
HOME = Path("/home/derek")
CLAUDE_DIR = HOME / ".claude"


@dataclass
class CodebaseContext:
    """Full codebase and environment context for Prometheus."""

    # Identity & mission
    identity: str = ""  # PROMETHEUS_IDENTITY.md content

    # Self-awareness
    prometheus_files: dict[str, str] = field(default_factory=dict)  # path -> summary
    prometheus_config: dict[str, Any] = field(default_factory=dict)

    # AVARA awareness
    avara_files: dict[str, str] = field(default_factory=dict)
    avara_claude_md: str = ""
    avara_docker_status: dict[str, Any] = field(default_factory=dict)

    # Environment
    server_info: dict[str, Any] = field(default_factory=dict)
    claude_config: dict[str, Any] = field(default_factory=dict)

    # Workflow observations
    workflow_suggestions: list[str] = field(default_factory=list)


def scan_codebase() -> CodebaseContext:
    """Scan the full codebase and environment for context."""
    ctx = CodebaseContext()

    # ── Identity & mission ──
    identity_path = PROMETHEUS_ROOT / "PROMETHEUS_IDENTITY.md"
    if identity_path.exists():
        try:
            ctx.identity = identity_path.read_text()
        except Exception:
            pass

    # ── Prometheus self-awareness ──
    _scan_prometheus(ctx)

    # ── AVARA awareness ──
    _scan_avara(ctx)

    # ── Server environment ──
    _scan_server(ctx)

    # ── Claude Code config ──
    _scan_claude_config(ctx)

    # ── Generate workflow suggestions ──
    _generate_suggestions(ctx)

    return ctx


def _scan_prometheus(ctx: CodebaseContext) -> None:
    """Scan Prometheus's own codebase."""
    src = PROMETHEUS_ROOT / "src" / "prometheus"
    if not src.exists():
        return

    for py_file in sorted(src.rglob("*.py")):
        rel = str(py_file.relative_to(PROMETHEUS_ROOT))
        try:
            content = py_file.read_text()
            # Extract docstring as summary
            lines = content.split("\n")
            docstring = ""
            for line in lines[:10]:
                stripped = line.strip().strip('"').strip("'")
                if stripped and not stripped.startswith(("from ", "import ", "#!")):
                    docstring = stripped
                    break
            ctx.prometheus_files[rel] = docstring

        except Exception:
            ctx.prometheus_files[rel] = "(unreadable)"

    # Config
    config_path = PROMETHEUS_ROOT / "config" / "prometheus.yaml"
    if config_path.exists():
        try:
            import yaml
            ctx.prometheus_config = yaml.safe_load(config_path.read_text())
        except Exception:
            pass


def _scan_avara(ctx: CodebaseContext) -> None:
    """Scan AVARA 2.0 codebase for key files."""
    key_dirs = ["monitoring", "core", "orchestrator", "config", "examples", "workers"]

    for d in key_dirs:
        dir_path = AVARA_ROOT / d
        if not dir_path.exists():
            continue
        for py_file in sorted(dir_path.glob("*.py")):
            rel = str(py_file.relative_to(AVARA_ROOT))
            try:
                first_lines = py_file.read_text()[:500]
                # Extract docstring
                docstring = ""
                for line in first_lines.split("\n")[:10]:
                    stripped = line.strip().strip('"').strip("'")
                    if stripped and not stripped.startswith(("from ", "import ", "#!")):
                        docstring = stripped
                        break
                ctx.avara_files[rel] = docstring
            except Exception:
                ctx.avara_files[rel] = "(unreadable)"

    # AVARA CLAUDE.md
    claude_md = AVARA_ROOT / "CLAUDE.md"
    if claude_md.exists():
        try:
            ctx.avara_claude_md = claude_md.read_text()[:5000]  # first 5k chars
        except Exception:
            pass

    # Docker status
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=5,
        )
        containers = {}
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("\t")
                if len(parts) >= 2:
                    containers[parts[0]] = {
                        "status": parts[1],
                        "ports": parts[2] if len(parts) > 2 else "",
                    }
        ctx.avara_docker_status = containers
    except Exception:
        pass


def _scan_server(ctx: CodebaseContext) -> None:
    """Scan server environment."""
    ctx.server_info = {
        "hostname": _run_cmd("hostname"),
        "kernel": _run_cmd("uname -r"),
        "python": _run_cmd("python3 --version"),
        "docker": _run_cmd("docker --version"),
        "disk_free": _run_cmd("df -h / | tail -1"),
        "memory": _run_cmd("free -h | grep Mem"),
        "uptime": _run_cmd("uptime -p"),
        "cpu_cores": _run_cmd("nproc"),
    }

    # Check running trading processes
    try:
        result = subprocess.run(
            ["pgrep", "-af", "guardian|prometheus|vhunter"],
            capture_output=True, text=True, timeout=5,
        )
        ctx.server_info["trading_processes"] = [
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        ]
    except Exception:
        ctx.server_info["trading_processes"] = []


def _scan_claude_config(ctx: CodebaseContext) -> None:
    """Scan Claude Code configuration and interaction patterns."""
    # Claude settings
    settings_path = CLAUDE_DIR / "settings.json"
    if settings_path.exists():
        try:
            ctx.claude_config["settings"] = json.loads(settings_path.read_text())
        except Exception:
            pass

    # Project-level CLAUDE.md
    home_claude = HOME / "CLAUDE.md"
    if home_claude.exists():
        try:
            ctx.claude_config["home_claude_md"] = home_claude.read_text()[:3000]
        except Exception:
            pass

    # Memory files
    memory_dir = CLAUDE_DIR / "projects" / "-home-derek" / "memory"
    if memory_dir.exists():
        memory_files = list(memory_dir.glob("*.md"))
        ctx.claude_config["memory_files"] = [str(f.name) for f in memory_files]
        for mf in memory_files[:5]:
            try:
                ctx.claude_config[f"memory_{mf.name}"] = mf.read_text()[:2000]
            except Exception:
                pass


def _generate_suggestions(ctx: CodebaseContext) -> None:
    """Generate suggestions driven by Prometheus's mission and observations.

    These aren't just system health checks — they're strategic observations
    about what Prometheus should be doing to push its capabilities and
    move toward the goal of proving consistent alpha.
    """
    suggestions = []

    # ── Mission-driven: strategy evolution ──
    strategies_path = PROMETHEUS_ROOT / "data" / "strategies.json"
    if strategies_path.exists():
        try:
            strats = json.loads(strategies_path.read_text())
            zero_fitness = [s for s, m in strats.items() if m.get("fitness_score", 0) == 0]
            total_trades = sum(m.get("trade_count", 0) for m in strats.values())

            if len(zero_fitness) == len(strats):
                suggestions.append(
                    "LEARNING BLOCKED: All strategy fitness scores are 0.0. No round-trip "
                    "trades have completed yet. The direction threshold (0.1) may be too "
                    "low for sell signals to fire on held positions. Consider: (a) lowering "
                    "the threshold, (b) adding a time-based sell trigger for stale positions, "
                    "or (c) implementing a mean-reversion exit when momentum reverses."
                )

            if len(strats) <= 2:
                suggestions.append(
                    "EVOLUTION STALLED: Only 2 strategies in the library. The evolution "
                    "system should be generating variants. The IMITATION phase runs at "
                    "tick 1000 — have we reached it? If so, check why clones aren't being "
                    "registered in the library. This is critical for strategy discovery."
                )

            if total_trades > 100:
                # Enough data to start making strategic observations
                for sid, meta in strats.items():
                    tc = meta.get("trade_count", 0)
                    wr = meta.get("win_rate", 0)
                    if tc > 20 and wr < 0.35:
                        suggestions.append(
                            f"STRATEGY UNDERPERFORMING: {sid} has {wr*100:.0f}% win rate "
                            f"after {tc} trades. Consider restricting it to specific regimes "
                            f"or evolving a replacement via the StrategyInventorAgent."
                        )
        except Exception:
            pass

    # ── Mission-driven: cross-sectional intelligence ──
    suggestions.append(
        "CROSS-SECTIONAL OPPORTUNITY: Prometheus sees 625 pairs simultaneously. "
        "Aggregate regime detection across all pairs to build a 'market regime index' — "
        "e.g., if >60% of pairs are BREAKOUT_IMMINENT, that's a macro signal. "
        "This cross-sectional view is something AVARA's per-asset V4.2 cannot do. "
        "This is Prometheus's unique edge. Consider adding a MarketRegimeAggregator."
    )

    # ── Mission-driven: AVARA comparison ──
    suggestions.append(
        "AVARA COMPARISON: Compare Prometheus paper trading P&L against AVARA's "
        "live realized profits per asset. If Prometheus outperforms on specific "
        "assets or regimes, that's evidence for strategy improvements in AVARA. "
        "Track this over time to build a case for live deployment."
    )

    # ── Operational health ──
    research_path = PROMETHEUS_ROOT / "data" / "research_input.json"
    if research_path.exists():
        try:
            data = json.loads(research_path.read_text())
            if not data.get("entries"):
                suggestions.append(
                    "RESEARCH LOOP OPEN: Research input is empty. Prometheus has "
                    "questions in its reports that could improve decision-making. "
                    "Derek: run generate_report.py, answer the HIGH priority questions "
                    "in data/research_input.json, and restart the feedback loop."
                )
        except Exception:
            pass

    reports_dir = PROMETHEUS_ROOT / "reports"
    if reports_dir.exists():
        reports = list(reports_dir.glob("*.md"))
        if len(reports) > 10:
            suggestions.append(
                f"HOUSEKEEPING: {len(reports)} report files. Consider auto-cleaning "
                "old reports or adding rotation."
            )

    if ctx.avara_docker_status:
        for name, info in ctx.avara_docker_status.items():
            if "unhealthy" in info.get("status", "").lower():
                suggestions.append(
                    f"SYSTEM HEALTH: Container {name} is unhealthy: {info['status']}. "
                    "This may affect AVARA signal reading."
                )

    guardian_running = any(
        "guardian" in p for p in ctx.server_info.get("trading_processes", [])
    )
    if not guardian_running:
        suggestions.append(
            "AVARA OFFLINE: No guardian process detected. Live trading may not be "
            "running. This means Prometheus cannot learn from AVARA's live signals. "
            "Start: docker exec -d avara-orchestrator python3 /app/examples/guardian_dual_account.py"
        )

    prometheus_running = any(
        "prometheus.live_runner" in p for p in ctx.server_info.get("trading_processes", [])
    )
    if not prometheus_running:
        suggestions.append(
            "PROMETHEUS OFFLINE: live_runner is not detected. Paper trading and "
            "learning are paused. Start: cd prometheus && PYTHONPATH=src "
            "venv/bin/python -m prometheus.live_runner &disown"
        )

    # ── Self-improvement ──
    suggestions.append(
        "SELF-IMPROVEMENT REQUEST: Prometheus should track which of its suggestions "
        "Derek acts on and which are ignored. This feedback helps Prometheus learn "
        "what kinds of insights are actionable vs noise. Consider adding a "
        "'suggestion_outcomes.json' file where Derek can mark suggestions as "
        "'acted_on', 'deferred', or 'rejected' with a reason."
    )

    ctx.workflow_suggestions = suggestions


def get_codebase_summary() -> dict[str, Any]:
    """Get a compact summary for the report."""
    ctx = scan_codebase()

    return {
        "prometheus": {
            "files": len(ctx.prometheus_files),
            "file_list": list(ctx.prometheus_files.keys()),
        },
        "avara": {
            "files": len(ctx.avara_files),
            "file_list": list(ctx.avara_files.keys()),
        },
        "docker": ctx.avara_docker_status,
        "server": {
            k: v for k, v in ctx.server_info.items()
            if k != "trading_processes"
        },
        "trading_processes": ctx.server_info.get("trading_processes", []),
        "suggestions": ctx.workflow_suggestions,
    }


def format_for_report(ctx: CodebaseContext | None = None) -> list[str]:
    """Format codebase awareness as markdown for the report."""
    if ctx is None:
        ctx = scan_codebase()

    lines = []

    # System status
    lines.append("### System Status")
    lines.append("")
    si = ctx.server_info
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Hostname | {si.get('hostname', '?')} |")
    lines.append(f"| Uptime | {si.get('uptime', '?')} |")
    lines.append(f"| Kernel | {si.get('kernel', '?')} |")
    lines.append(f"| CPU Cores | {si.get('cpu_cores', '?')} |")
    lines.append(f"| Memory | {si.get('memory', '?')} |")
    lines.append(f"| Disk | {si.get('disk_free', '?')} |")
    lines.append("")

    # Docker
    if ctx.avara_docker_status:
        lines.append("### Docker Containers")
        lines.append("")
        lines.append("| Container | Status |")
        lines.append("|-----------|--------|")
        for name, info in sorted(ctx.avara_docker_status.items()):
            lines.append(f"| {name} | {info.get('status', '?')} |")
        lines.append("")

    # Trading processes
    procs = ctx.server_info.get("trading_processes", [])
    if procs:
        lines.append("### Active Trading Processes")
        lines.append("")
        for p in procs:
            # Trim long command lines
            lines.append(f"- `{p[:120]}`")
        lines.append("")

    # Codebase overview
    lines.append("### Codebase Awareness")
    lines.append("")
    lines.append(f"- **Prometheus source files**: {len(ctx.prometheus_files)}")
    lines.append(f"- **AVARA source files scanned**: {len(ctx.avara_files)}")
    lines.append("")

    # Workflow suggestions
    if ctx.workflow_suggestions:
        lines.append("### Workflow Suggestions")
        lines.append("")
        for i, sug in enumerate(ctx.workflow_suggestions, 1):
            lines.append(f"{i}. {sug}")
            lines.append("")

    return lines


def _run_cmd(cmd: str) -> str:
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd.split(), capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""
