"""Your real holdings, stored ENCRYPTED in the public repo (data/holdings.enc).
The key is derived from the TELEGRAM_BOT_TOKEN secret, so only the workflow can read it."""
import base64
import datetime as dt
import hashlib
import json
import os

import numpy as np

from scanner import indicators as ind

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "data", "holdings.enc")


def _fernet():
    from cryptography.fernet import Fernet
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not tok:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(("holdings:" + tok).encode()).digest())
    return Fernet(key)


def load():
    f = _fernet()
    if f is None or not os.path.exists(FILE):
        return []
    try:
        return json.loads(f.decrypt(open(FILE, "rb").read()))
    except Exception as e:
        print("holdings decrypt failed", e)
        return []


def save(h):
    f = _fernet()
    if f is None:
        return
    with open(FILE, "wb") as fh:
        fh.write(f.encrypt(json.dumps(h).encode()))


def plan_for(entry, d):
    """Initial stop and targets using the same rules as the scanner."""
    r = d.iloc[-1]
    stop = max(r.ll10, entry - 2.5 * r.atr)
    stop = max(min(stop, entry * 0.97), entry * 0.90)
    return round(float(stop), 2), round(entry * 1.05, 2), round(entry * 1.10, 2)


def review(h, d, bench_close=None):
    """Status + advice for one holding given its daily data with indicators."""
    since = d[d.index.date >= dt.date.fromisoformat(h["date"])]
    last = float(d.Close.iloc[-1])
    pnl = (last / h["price"] - 1) * 100
    hi = float(since.High.max()) if len(since) else last
    t1_hit = h.get("t1_done") or hi >= h["t1"]
    stop = h["price"] if t1_hit else h["stop"]
    e20 = float(d.ema20.iloc[-1])
    days = len(since)
    if last <= stop:
        act = "🛑 EXIT – stop-loss hit" if not t1_hit else "🛑 EXIT rest – back to cost"
    elif t1_hit and not h.get("t1_done"):
        act = f"🎯 T1 hit – sell half ({h['qty'] // 2}), move SL to cost {h['price']}"
    elif t1_hit and last < e20:
        act = "📉 Closed below 20 EMA – sell the rest"
    elif days >= 60:
        act = "⏰ 60 days done – exit"
    elif not t1_hit and days >= 15 and pnl < 2:
        act = "⏳ 15 days, no move – consider exiting (time stop)"
    elif (bench_close is not None and days >= 10 and
          pnl - (float(bench_close.iloc[-1]) / float(bench_close[bench_close.index.date >= dt.date.fromisoformat(h["date"])].iloc[0]) - 1) * 100 < -5):
        act = "📉 Weaker than Nifty by 5%+ since buy – consider exiting"
    elif t1_hit:
        act = f"✅ Hold rest · trail: exit on close below 20 EMA ({e20:.2f})"
    else:
        act = f"✅ Hold · SL {stop} · T1 {h['t1']}"
    return {"symbol": h["symbol"], "qty": h["qty"], "buy": h["price"], "last": round(last, 2),
            "pnl": round(pnl, 2), "pnl_rs": round((last - h["price"]) * h["qty"]),
            "days": days, "action": act, "stop": stop}


def text(reviews):
    if not reviews:
        return "No holdings saved. Add one with: /buy SYMBOL PRICE QTY"
    L = ["💼 <b>Your portfolio</b>"]
    tot = 0
    for r in reviews:
        tot += r["pnl_rs"]
        L.append(f"<b>{r['symbol']}</b> {r['qty']} @ {r['buy']} → {r['last']} "
                 f"({r['pnl']:+.2f}%, ₹{r['pnl_rs']:+,}) · day {r['days']}\n   {r['action']}")
    L.append(f"Total P&L: ₹{tot:+,}")
    return "\n".join(L)
