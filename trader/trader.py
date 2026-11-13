"""Angel One order bot — runs 24x7 on YOUR static-IP server (not on GitHub).

Uses a SEPARATE Telegram bot (TRADE_BOT_TOKEN) so it never clashes with the report bot.
Nothing is ever bought or sold without your /approve in Telegram.

Commands (only from TELEGRAM_CHAT_ID):
  /order SYMBOL [QTY]   preview a buy using the scanner's plan (limit price + stop-loss)
  /exit SYMBOL [QTY]    preview a sell
  /approve CODE         place the previewed order (code valid 10 minutes, one use)
  /cancel               drop any pending preview
  /funds                available cash
  /orders               today's orders
  /holdings             broker holdings
  /trading on|off       master switch (starts OFF)
  /help

Safety limits (in .env): MAX_ORDER_VALUE, MAX_ORDERS_PER_DAY. Orders are LIMIT + DELIVERY,
and every buy gets a broker-side GTT stop-loss so the stop works even if this server is down.
"""
import datetime as dt
import json
import os
import secrets
import sys
import time
import traceback

import pyotp
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from scanner import data, indicators as ind, strategies as stg  # noqa: E402

ENV = os.path.join(HERE, ".env")
STATE = os.path.join(HERE, "state.json")
SCRIP = os.path.join(HERE, "scrip_master.json")
SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
PICKS_URL = "https://nettemvenu12-alt.github.io/nifty500-swing-scanner/picks.json"


def load_env():
    if os.path.exists(ENV):
        for line in open(ENV):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()
TOK = os.environ.get("TRADE_BOT_TOKEN", "")
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
API = f"https://api.telegram.org/bot{TOK}"
MAX_VALUE = float(os.environ.get("MAX_ORDER_VALUE", "25000"))
MAX_PER_DAY = int(os.environ.get("MAX_ORDERS_PER_DAY", "5"))


# ---------- state ----------
def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"offset": 0, "trading": False, "pending": None, "day": "", "count": 0, "log": []}


def save_state(st):
    json.dump(st, open(STATE, "w"), indent=1)


def send(text):
    requests.post(f"{API}/sendMessage", data={"chat_id": CHAT, "text": text[:3900],
                  "parse_mode": "HTML", "disable_web_page_preview": "true"}, timeout=20)


# ---------- broker ----------
_api = {"obj": None, "at": 0}


def broker():
    """Logged-in SmartConnect, refreshed every 6 hours."""
    from SmartApi import SmartConnect
    if _api["obj"] is None or time.time() - _api["at"] > 6 * 3600:
        obj = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
        totp = pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now()
        r = obj.generateSession(os.environ["ANGEL_CLIENT_CODE"], os.environ["ANGEL_PIN"], totp)
        if not r or not r.get("status"):
            raise RuntimeError(f"Angel One login failed: {r and r.get('message')}")
        _api.update(obj=obj, at=time.time())
    return _api["obj"]


def token_for(sym):
    """NSE equity token from Angel's scrip master (cached for a day)."""
    if not os.path.exists(SCRIP) or time.time() - os.path.getmtime(SCRIP) > 86400:
        r = requests.get(SCRIP_URL, timeout=60)
        r.raise_for_status()
        open(SCRIP, "w").write(r.text)
    want = f"{sym}-EQ"
    for row in json.load(open(SCRIP)):
        if row.get("exch_seg") == "NSE" and row.get("symbol") == want:
            return want, row["token"]
    raise ValueError(f"{sym} not found on NSE (EQ series)")


def ltp(tsym, token):
    r = broker().ltpData("NSE", tsym, token)
    return float(r["data"]["ltp"])


def tick(x):
    return round(round(x / 0.05) * 0.05, 2)


# ---------- plan ----------
def plan(sym):
    """Scanner plan for this stock: today's pick if present, else computed fresh."""
    try:
        o = requests.get(PICKS_URL, timeout=20).json()
        for p in o.get("picks", []):
            if p["symbol"] == sym:
                return {"stop": p["stop"], "qty": p.get("qty", 0), "t1": p["target1"],
                        "src": f"scanner pick ({p['label']}, {p['score']}/100)"}
    except Exception:
        pass
    d = data.download([sym], period="2y").get(sym)
    if d is None:
        raise ValueError(f"No price data for {sym}")
    r = ind.add_all(d).iloc[-1]
    pl = stg.trade_plan(r)
    return {"stop": pl["stop"], "qty": 0, "t1": pl["target1"], "src": "fresh calculation (not in today's picks)"}


# ---------- commands ----------
def preview(st, side, sym, qty):
    tsym, token = token_for(sym)
    price = ltp(tsym, token)
    pl = plan(sym) if side == "BUY" else {}
    if side == "BUY":
        qty = qty or pl.get("qty") or 0
        if qty <= 0:
            return "Give a quantity: /order SYMBOL QTY"
        limit = tick(price * 1.003)   # small buffer so the limit fills, never a market order
    else:
        if not qty:
            return "Give a quantity: /exit SYMBOL QTY"
        limit = tick(price * 0.997)
    value = limit * qty
    if value > MAX_VALUE:
        return f"❌ Order value ₹{value:,.0f} is above your limit ₹{MAX_VALUE:,.0f} (MAX_ORDER_VALUE)."
    code = secrets.token_hex(2).upper()
    st["pending"] = {"code": code, "side": side, "sym": sym, "tsym": tsym, "token": token, "qty": int(qty),
                     "limit": limit, "stop": pl.get("stop"), "t1": pl.get("t1"), "at": time.time()}
    lines = [f"📝 <b>{side} {sym}</b> × {qty} @ LIMIT ₹{limit} (LTP {price})", f"Value ₹{value:,.0f}"]
    if side == "BUY":
        lines.append(f"Stop-loss GTT ₹{pl['stop']} · T1 ₹{pl['t1']} · plan from {pl['src']}")
    lines.append(f"\nTo place it send: <b>/approve {code}</b>  (valid 10 min)")
    if not st.get("trading"):
        lines.append("⚠️ Trading switch is OFF – send /trading on first.")
    return "\n".join(lines)


def approve(st, code):
    p = st.get("pending")
    if not p or p["code"] != code.upper():
        return "❌ No pending order with that code."
    if time.time() - p["at"] > 600:
        st["pending"] = None
        return "⌛ Preview expired. Send /order again."
    if not st.get("trading"):
        return "⚠️ Trading switch is OFF. Send /trading on, then /approve again."
    today = str(dt.date.today())
    if st.get("day") != today:
        st["day"], st["count"] = today, 0
    if st["count"] >= MAX_PER_DAY:
        return f"❌ Daily limit of {MAX_PER_DAY} orders reached."
    st["pending"] = None  # one use only, even if the broker call fails
    order = {"variety": "NORMAL", "tradingsymbol": p["tsym"], "symboltoken": p["token"],
             "transactiontype": p["side"], "exchange": "NSE", "ordertype": "LIMIT",
             "producttype": "DELIVERY", "duration": "DAY", "price": str(p["limit"]),
             "quantity": str(p["qty"])}
    resp = broker().placeOrderFullResponse(order)
    st["count"] += 1
    st["log"].append({"t": dt.datetime.now().isoformat(timespec="seconds"), **{k: p[k] for k in ("side", "sym", "qty", "limit")},
                      "resp": str(resp)[:300]})
    ok = resp and resp.get("status")
    msg = [f"{'✅' if ok else '❌'} {p['side']} {p['sym']} × {p['qty']} @ {p['limit']}: "
           f"{(resp or {}).get('message', 'no response')} (order {((resp or {}).get('data') or {}).get('orderid', '-')})"]
    if ok and p["side"] == "BUY" and p.get("stop"):
        try:
            gid = broker().gttCreateRule({
                "tradingsymbol": p["tsym"], "symboltoken": p["token"], "exchange": "NSE",
                "producttype": "DELIVERY", "transactiontype": "SELL",
                "price": str(tick(p["stop"] * 0.995)), "qty": str(p["qty"]),
                "triggerprice": str(tick(p["stop"])), "disclosedqty": str(p["qty"]), "timeperiod": 365})
            msg.append(f"🛡 Stop-loss GTT set at ₹{tick(p['stop'])} (rule {gid}). It triggers only after the buy fills.")
        except Exception as e:
            msg.append(f"⚠️ Could not create stop-loss GTT ({e}). SET THE STOP-LOSS MANUALLY in the Angel One app!")
    return "\n".join(msg)


def handle(st, text):
    parts = text.strip().split()
    cmd = parts[0].lower().split("@")[0]
    arg = lambda i: parts[i] if len(parts) > i else None  # noqa: E731
    sym = (arg(1) or "").upper().replace(".NS", "")
    qty = int(arg(2)) if arg(2) and arg(2).isdigit() else None
    if cmd in ("/start", "/help"):
        return __doc__.split("\n\n")[2]
    if cmd == "/trading" and arg(1) in ("on", "off"):
        st["trading"] = arg(1) == "on"
        return f"Trading switch is now {'ON ✅ (orders still need /approve)' if st['trading'] else 'OFF ⛔'}"
    if cmd == "/order" and sym:
        return preview(st, "BUY", sym, qty)
    if cmd == "/exit" and sym:
        return preview(st, "SELL", sym, qty)
    if cmd == "/approve" and arg(1):
        return approve(st, arg(1))
    if cmd == "/cancel":
        st["pending"] = None
        return "Pending preview cleared."
    if cmd == "/funds":
        r = broker().rmsLimit()
        d = (r or {}).get("data") or {}
        return f"💰 Available cash ₹{float(d.get('availablecash', 0)):,.0f} · net ₹{float(d.get('net', 0)):,.0f}"
    if cmd == "/orders":
        rows = (broker().orderBook() or {}).get("data") or []
        return "\n".join(f"{o['transactiontype']} {o['tradingsymbol']} ×{o['quantity']} @ {o['price']} · {o['orderstatus']}"
                         for o in rows[-15:]) or "No orders today."
    if cmd == "/holdings":
        rows = (broker().holding() or {}).get("data") or []
        return "\n".join(f"{h['tradingsymbol']} ×{h['quantity']} avg {h['averageprice']} ltp {h['ltp']} "
                         f"({float(h.get('profitandloss', 0)):+,.0f})" for h in rows) or "No holdings."
    return "Commands: /order SYMBOL [QTY] · /exit SYMBOL QTY · /approve CODE · /cancel · /funds · /orders · /holdings · /trading on|off"


def main():
    if not (TOK and CHAT):
        sys.exit("Set TRADE_BOT_TOKEN and TELEGRAM_CHAT_ID in trader/.env")
    st = load_state()
    print("Trader bot running. Trading switch:", st.get("trading"))
    while True:
        try:
            r = requests.get(f"{API}/getUpdates", params={"offset": st["offset"], "timeout": 50}, timeout=60).json()
            for u in r.get("result", []):
                st["offset"] = u["update_id"] + 1
                msg = u.get("message") or {}
                if str(msg.get("chat", {}).get("id")) != CHAT or not msg.get("text", "").startswith("/"):
                    continue  # strangers and plain text are ignored
                try:
                    reply = handle(st, msg["text"])
                except Exception as e:
                    traceback.print_exc()
                    reply = f"⚠️ Error: {e}"
                save_state(st)
                send(reply)
            save_state(st)
        except Exception as e:
            print("loop error", e)
            time.sleep(10)


if __name__ == "__main__":
    main()
