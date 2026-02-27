# Claude Code on Ubuntu - Quick Reference

## Install Claude Code

```bash
curl -fsSL https://claude.ai/install.sh | bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
claude --version
```

## First-Time Authentication

```bash
claude
# Follow the URL prompt to authenticate via browser
```

## Basic Usage

```bash
# Interactive chat
claude

# One-off question
claude -p "explain this function"

# Pipe input
cat error.log | claude -p "what's wrong here"

# Continue last conversation
claude -c

# Work on a specific project
cd ~/prometheus-drgb
claude
```

## Access Mac SMB Share (GVFS)

```bash
cd "/run/user/1000/gvfs/smb-share:server=derek-macbook.local,share=derek"
cd prometheus-drgb-trader
claude
```

> **Note:** GVFS mounts require an active desktop session. If the server reboots
> or you're not logged into the GUI, the mount disappears. For 24/7 access,
> use a proper CIFS mount in `/etc/fstab` instead.

## Persistent CIFS Mount (Optional)

```bash
# Install cifs-utils
sudo apt install cifs-utils

# Create mount point
sudo mkdir -p /mnt/mac

# Add to /etc/fstab for permanent mount
echo '//derek-macbook.local/Derek /mnt/mac cifs username=Derek,password=YOUR_PASSWORD,uid=derek,gid=derek 0 0' | sudo tee -a /etc/fstab

# Mount it
sudo mount /mnt/mac

# Then use it
cd /mnt/mac/prometheus-drgb-trader
claude
```
