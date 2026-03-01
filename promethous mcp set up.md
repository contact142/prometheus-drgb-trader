# PROMETHEUS — Full Claude Server Access Guide

Three independent layers give Claude direct, persistent access to your Ubuntu server. Each works standalone; together they provide redundancy and flexibility for different contexts.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        YOUR UBUNTU SERVER                           │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │  PROMETHEUS   │  │   MCP Server │  │    Web Terminal (ttyd)    │ │
│  │  Trading Sys  │  │   Port 8818  │  │    Port 7681             │ │
│  │  (systemd)    │  │  (systemd)   │  │    (systemd)             │ │
│  └──────────────┘  └──────┬───────┘  └──────────┬────────────────┘ │
│                           │                      │                  │
│                      SSH server (:22)            │                  │
└───────────────────────┬───┼──────────────────────┼──────────────────┘
                        │   │                      │
            ┌───────────┘   │                      │
            │               │                      │
  ┌─────────┴────────┐ ┌───┴────────────┐ ┌───────┴──────────────┐
  │ Desktop Commander │ │   Claude.ai    │ │  Claude in Chrome    │
  │ (Mac terminal)    │ │  (MCP native)  │ │  (browser terminal)  │
  │ ssh prometheus-   │ │  Direct tool   │ │  Navigate to URL,    │
  │ server "cmd"      │ │  calls in chat │ │  type commands       │
  └──────────────────┘ └────────────────┘ └──────────────────────┘
```

---

## Quick Start (5 minutes)

### On the Ubuntu server:

```bash
# Clone this access layer repo (or scp the files)
git clone <your-repo> /tmp/prometheus-access
cd /tmp/prometheus-access

# Run master setup (installs all 3 layers)
sudo ./setup_all_server.sh
```

Save the credentials shown at the end!

### On your Mac:

```bash
# Setup SSH bridge for Desktop Commander
chmod +x ssh-bridge/setup_ssh_bridge.sh
./ssh-bridge/setup_ssh_bridge.sh <SERVER_IP> <your_username>

# Install convenience command
cp ssh-bridge/prometheus-remote.sh /usr/local/bin/prometheus-remote
chmod +x /usr/local/bin/prometheus-remote
```

### In Claude.ai:

Add the MCP server URL in your Claude settings (under connectors or integrations):
```
http://<SERVER_IP>:8818/mcp
```

---

## Layer 1: MCP Server (Recommended — Most Powerful)

**What:** A custom MCP server running on your Ubuntu box that exposes PROMETHEUS-specific tools directly to Claude.ai.

**Why best:** Claude calls tools natively in conversation — no browser, no SSH, no copy-paste. Fastest and most reliable.

### Available Tools

| Tool | What it does |
|------|-------------|
| `prometheus_run_command` | Execute any shell command |
| `prometheus_service` | Start/stop/restart/status of PROMETHEUS |
| `prometheus_logs` | Tail logs from journald or log files |
| `prometheus_read_file` | Read any file in allowed directories |
| `prometheus_write_file` | Write/append to files |
| `prometheus_list_dir` | List directory contents |
| `prometheus_search_files` | Grep through source code |
| `prometheus_config_view` | View PROMETHEUS config |
| `prometheus_config_edit` | Edit config values by dot-path |
| `prometheus_git` | Git status/pull/log/diff |
| `prometheus_health` | Full system health check |
| `prometheus_run_backtest` | Run a backtest simulation |
| `prometheus_run_tests` | Run pytest suite |
| `prometheus_deploy_update` | Full deploy: pull → install → test → restart |

### Setup

The master script handles this, but if doing manually:

```bash
# On server
sudo mkdir -p /opt/prometheus-mcp
sudo cp mcp-server/prometheus_mcp.py /opt/prometheus-mcp/
sudo cp mcp-server/requirements.txt /opt/prometheus-mcp/

python3 -m venv /opt/prometheus-mcp/venv
/opt/prometheus-mcp/venv/bin/pip install -r /opt/prometheus-mcp/requirements.txt

# Test it
/opt/prometheus-mcp/venv/bin/python /opt/prometheus-mcp/prometheus_mcp.py --port 8818

# Install as service
sudo cp mcp-server/prometheus-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable prometheus-mcp
sudo systemctl start prometheus-mcp
```

### Connecting to Claude.ai

1. Go to **claude.ai** → **Settings** (or your profile)
2. Find **Integrations** or **MCP Servers** section
3. Add new MCP server with URL: `http://<SERVER_IP>:8818/mcp`
4. Claude will now have the PROMETHEUS tools available in every conversation

### Example conversation with Claude:

> You: "Check if PROMETHEUS is healthy and show me the last 20 log lines"
> 
> Claude: *calls prometheus_health, then prometheus_logs with lines=20*
> "The service is active, running for 3 days. Memory usage is fine at 2.1GB/16GB. Here are the recent logs..."

### Troubleshooting

```bash
# Check MCP server status
sudo systemctl status prometheus-mcp

# View MCP server logs
journalctl -u prometheus-mcp -f

# Test manually
curl http://localhost:8818/mcp
```

---

## Layer 2: SSH via Desktop Commander

**What:** Passwordless SSH from your Mac to the server, accessible through Desktop Commander MCP.

**Why useful:** Works when you're in the Claude desktop app. Also serves as a fallback and for interactive debugging sessions.

### Setup

```bash
# On your Mac
./ssh-bridge/setup_ssh_bridge.sh 192.168.1.XXX your_username
```

This creates:
- SSH key pair at `~/.ssh/prometheus_server`
- SSH config alias `prometheus-server`
- Passwordless access verified

### Usage

Once set up, Claude (via Desktop Commander) can run:

```bash
# Any single command
ssh prometheus-server "systemctl status prometheus"

# Multi-command
ssh prometheus-server "cd /opt/prometheus-drgb && git status && python -m pytest tests/ -v"

# File operations
ssh prometheus-server "cat /opt/prometheus-drgb/config/default.yaml"

# Interactive Python
ssh prometheus-server "cd /opt/prometheus-drgb && PYTHONPATH=src venv/bin/python -c 'from prometheus.agents import PrometheusAgent; print(\"OK\")'"
```

### Convenience Wrapper

Install the `prometheus-remote` command on your Mac:

```bash
cp ssh-bridge/prometheus-remote.sh /usr/local/bin/prometheus-remote
chmod +x /usr/local/bin/prometheus-remote
```

Then:
```bash
prometheus-remote status       # Service status
prometheus-remote logs 100     # Last 100 log lines
prometheus-remote deploy       # Full git pull + test + restart
prometheus-remote backtest 10000  # Run backtest
prometheus-remote health       # System health
prometheus-remote shell "df -h"   # Any command
```

---

## Layer 3: Web Terminal (Claude in Chrome)

**What:** A browser-based terminal (ttyd) that Claude in Chrome can navigate to and type commands.

**Why useful:** Visual feedback, works from any browser, good for tasks where Claude needs to see real-time output or navigate file systems interactively.

### Setup

Master script handles this, or manually:

```bash
sudo ./web-terminal/setup_web_terminal.sh
```

### Usage

Tell Claude in Chrome:
> "Navigate to http://192.168.1.XXX:7681 and log in with the web terminal credentials"

Claude will:
1. Open the URL in Chrome
2. See the ttyd login form
3. Enter username: `prometheus`, password: (from setup)
4. Get a full bash terminal in the browser
5. Type commands directly

### Security Notes

- Only accessible from local network (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
- Password-protected
- Max 3 concurrent clients
- NOT exposed to the internet

---

## Security Considerations

### Network

All three services are restricted to **local network only** via UFW firewall rules. They are NOT accessible from the internet.

If you need remote access (from outside your network):
- **Option A:** Use a VPN (Tailscale, WireGuard) to create a private network
- **Option B:** SSH tunnel: `ssh -L 8818:localhost:8818 your-vps` then connect to `localhost:8818`
- **Never** expose MCP or ttyd directly to the internet

### Authentication

| Layer | Auth method |
|-------|------------|
| MCP Server | Optional token (set `PROMETHEUS_MCP_AUTH_TOKEN` env var) |
| SSH | Ed25519 key pair (no password) |
| Web Terminal | Username + auto-generated password |

### Allowed Operations

The MCP server restricts file access to:
- `/opt/prometheus-drgb` (PROMETHEUS installation)
- `/tmp` (temporary files)
- User home directory

Destructive commands like `rm -rf /`, `mkfs`, etc. are blocked.

The `prometheus` user has passwordless sudo ONLY for:
- `systemctl start/stop/restart/status prometheus`
- `systemctl start/stop/restart prometheus-mcp`

---

## Service Management

```bash
# View all PROMETHEUS services
sudo systemctl status prometheus prometheus-mcp ttyd

# Restart everything
sudo systemctl restart prometheus prometheus-mcp ttyd

# View combined logs
journalctl -u prometheus -u prometheus-mcp -u ttyd -f
```

---

## What Claude Can Do With This

Once all layers are set up, Claude can:

- **Monitor** the trading system in real-time (logs, health checks)
- **Deploy** code updates (git pull, reinstall, restart)
- **Debug** issues (read files, search code, check errors)
- **Run backtests** with different parameters
- **Edit configuration** (risk limits, strategy params)
- **Manage the service** (start/stop/restart)
- **Write new code** and deploy it directly
- **Run tests** to verify changes
- **Investigate** system performance (CPU, memory, disk)

All without you having to SSH in manually or copy-paste commands.
