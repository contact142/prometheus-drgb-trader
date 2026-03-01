# PROMETHEUS Ubuntu Server Setup Guide

## Prerequisites
- Ubuntu 22.04+ server
- Python 3.10+
- SSH access with sudo privileges
- Internet connectivity (for Kraken price feed)

## Quick Setup

```bash
# 1. Install system dependencies
sudo bash deploy/install_dependencies.sh

# 2. Setup application (clone, venv, install, test)
sudo REPO_URL=git@github.com:contact142/prometheus-drgb-trader.git bash deploy/setup_app.sh

# 3. Install systemd service
sudo cp /opt/prometheus-drgb/deploy/prometheus.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable prometheus
sudo systemctl start prometheus
```

## Manual Setup (inside AVARA project)

```bash
cd "/home/derek/projects/AVARA 2.0/prometheus"
python3 -m venv venv && source venv/bin/activate
pip install -e .

# Run in background
PYTHONPATH=src python -m prometheus.live_runner &disown
```

## Verify

```bash
# Check status
sudo systemctl status prometheus

# Stream logs
journalctl -u prometheus -f

# Check recent logs
tail -50 logs/prometheus.log

# Verify Kraken price feed
grep "symbols mapped" logs/prometheus.log
```

## Configuration

Edit `config/prometheus.yaml` to customize:
- `data_source`: `kraken` for real prices, `synthetic` for random walk
- `symbols`: List of Kraken USD pairs to observe (up to 625)
- `tick_interval_seconds`: Agent processing interval
- `kraken_refresh_seconds`: How often to poll Kraken API
- DRGB thresholds
- Risk limits

Restart after config changes:
```bash
sudo systemctl restart prometheus
# or if running manually:
kill $(pgrep -f prometheus.live_runner) && PYTHONPATH=src python -m prometheus.live_runner &disown
```

## Update

```bash
cd /opt/prometheus-drgb  # or wherever deployed
git pull origin main
pip install -e .
sudo systemctl restart prometheus
```
