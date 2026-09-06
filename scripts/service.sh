#!/bin/sh
# Install the agent as a user service that starts at boot and restarts on crash (systemd, Linux).
set -e
cd "$(dirname "$0")/.."
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/businessai.service <<UNIT
[Unit]
Description=Business AI agent
After=network-online.target
[Service]
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/env python3 -m agent.core
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now businessai
loginctl enable-linger "$USER" 2>/dev/null || true
echo "service running. status: systemctl --user status businessai   logs: journalctl --user -u businessai -f"
