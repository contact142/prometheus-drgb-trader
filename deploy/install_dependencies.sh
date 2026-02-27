#!/usr/bin/env bash
set -euo pipefail

echo "=== PROMETHEUS: Installing system dependencies ==="

apt-get update && apt-get upgrade -y

# Python 3.11+
if ! command -v python3.11 &>/dev/null; then
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update
    apt-get install -y python3.11 python3.11-venv python3.11-dev
fi

apt-get install -y python3-pip python3-venv git curl

echo "=== Dependencies installed ==="
python3.11 --version || python3 --version
