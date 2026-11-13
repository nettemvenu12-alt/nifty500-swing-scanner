#!/usr/bin/env bash
# One-time setup on an Ubuntu server with a static public IP.
#   curl -sL https://raw.githubusercontent.com/nettemvenu12-alt/nifty500-swing-scanner/main/trader/setup_vps.sh | bash
set -euo pipefail
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv git
cd ~
[ -d nifty500-swing-scanner ] || git clone https://github.com/nettemvenu12-alt/nifty500-swing-scanner.git
cd nifty500-swing-scanner && git pull
python3 -m venv ~/trader-venv
~/trader-venv/bin/pip install -q -r trader/requirements.txt
[ -f trader/.env ] || cp trader/.env.example trader/.env
chmod 600 trader/.env
sudo tee /etc/systemd/system/trader.service >/dev/null <<UNIT
[Unit]
Description=Angel One Telegram trader bot
After=network-online.target

[Service]
User=$USER
WorkingDirectory=$HOME/nifty500-swing-scanner
ExecStart=$HOME/trader-venv/bin/python trader/trader.py
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable trader
echo
echo "Public IP of this server (register it in SmartAPI):"; curl -s https://api.ipify.org; echo
echo "Next: nano ~/nifty500-swing-scanner/trader/.env   then:  sudo systemctl restart trader"
