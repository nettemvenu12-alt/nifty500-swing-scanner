# Angel One auto-order bot (optional)

Exchanges now accept API orders only from a **registered static IP**, so this part runs on your own
small server, not on GitHub. The scanner, reports and report bot keep running on GitHub for free.

## Safety
- Separate Telegram bot; answers only your chat id.
- Every order: `/order` → preview → `/approve CODE` (10-minute, one-time code).
- Master switch `/trading on|off` (starts OFF), `MAX_ORDER_VALUE`, `MAX_ORDERS_PER_DAY`.
- LIMIT + DELIVERY orders only; every buy gets a broker-side **GTT stop-loss**.
- Credentials live only in `trader/.env` on your server (never in GitHub).

## Setup (about 30 min, once)
1. **Server with static IP** – e.g. Oracle Cloud *Always Free* VM (Ubuntu) + *reserved public IP*,
   or any ₹400–800/month VPS. Open its SSH console.
2. Run: `curl -sL https://raw.githubusercontent.com/nettemvenu12-alt/nifty500-swing-scanner/main/trader/setup_vps.sh | bash`
   It prints the server's public IP.
3. **Angel One SmartAPI** – log in at smartapi.angelone.in → *Create an App* (Trading API) → enter the
   server IP as Static IP → copy the **API key**. Enable **TOTP** and copy the **TOTP secret**.
4. **Trade bot** – @BotFather → /newbot → copy token.
5. `nano ~/nifty500-swing-scanner/trader/.env` → fill the values → `sudo systemctl restart trader`.
6. In the new bot: `/funds` to test login, then `/trading on` when ready.

Logs: `journalctl -u trader -f`. Update: `cd ~/nifty500-swing-scanner && git pull && sudo systemctl restart trader`.
