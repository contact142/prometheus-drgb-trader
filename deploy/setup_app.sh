#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/contact142/prometheus-drgb-trader.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/prometheus-drgb}"
PYTHON="${PYTHON:-python3.11}"

echo "=== PROMETHEUS: Setting up application ==="

# Clone or pull
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Repo exists, pulling latest..."
    cd "$INSTALL_DIR" && git pull origin main
else
    echo "Cloning repo..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Create venv
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
fi
source venv/bin/activate

# Install deps
pip install --upgrade pip
pip install -r requirements.txt

# Create runtime dirs
mkdir -p data logs

# Run tests
echo "=== Running tests ==="
pip install pytest
python -m pytest tests/ -v

echo "=== Setup complete. App installed at $INSTALL_DIR ==="
