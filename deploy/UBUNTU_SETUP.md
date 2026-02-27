# PROMETHEUS Ubuntu Server Setup Guide

## Prerequisites
- Ubuntu 22.04+ server
- SSH access with sudo privileges
- Internet connectivity

## Quick Setup

```bash
# 1. Install system dependencies
sudo bash deploy/install_dependencies.sh

# 2. Setup application (clone, venv, install, test)
sudo REPO_URL=https://github.com/contact142/prometheus-drgb-trader.git bash deploy/setup_app.sh

# 3. Install systemd service
sudo cp /opt/prometheus-drgb/deploy/prometheus.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable prometheus
sudo systemctl start prometheus
```

## Verify

```bash
# Check status
sudo systemctl status prometheus

# Stream logs
journalctl -u prometheus -f

# Check recent logs
journalctl -u prometheus --since "1 hour ago"
```

## Configuration

Edit `/opt/prometheus-drgb/config/prometheus.yaml` to customize:
- Trading pair, intervals
- DRGB thresholds
- Risk limits
- Strategy library path

Restart after config changes:
```bash
sudo systemctl restart prometheus
```

## Update

```bash
cd /opt/prometheus-drgb
sudo git pull origin main
sudo venv/bin/pip install -r requirements.txt
sudo systemctl restart prometheus
```
