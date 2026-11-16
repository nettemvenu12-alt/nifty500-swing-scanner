"""Telegram command bot (run every ~10 min by .github/workflows/bot.yml).

Only messages from TELEGRAM_CHAT_ID are answered.
  /check SYMBOL          full analysis of any NSE stock
  /top                   today's best picks
  /buy SYMBOL PRICE QTY  save a real buy (stop/targets set automatically;
                         90% MODE picks get SL -25% / sell half at +4%; add "90" to force it)
  /sell SYMBOL [QTY]     remove (all or part of) a holding
  /half SYMBOL           mark that you booked half at T1
  /portfolio             your holdings with live P&L and what to do
  /report                latest 90% MODE robustness test (also sent automatically when it changes)
  /help
"""
import datetime as dt
import json
import os
import re
import sys

import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scanner import data, indicators as ind, portfolio, strategies as stg  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "data", "bot_state.json")
MODEL = os.path.join(ROOT, "data", "ml.pkl")
PICKS = os.path.join(ROOT, "docs", "picks.json")
TOK = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHATS = {c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if c.strip()}
API = f"https://api.telegram.org/bot{TOK}"


def send(chat, text):
    for i in range(0, len(text), 3900):
        requests.post(f"{API}/sendMessage", data={"chat_id": chat, "text": text[i:i + 3900],
                      "parse_mode": "HTML", "disable_web_page_preview": "true"}, timeout=20)


def _sym(s):
    s = s.upper().replace(".NS", "").strip()
    return s if re.fullmatch(r"[A-Z0-9&\-]{1,20}", s) else None


def _prices(sym):
    d = data.download([sym], period="3y").get(sym)
    if d is None:
        return None, None
    bench = data.download([data.BENCH], period="3y").get(data.BENCH)
    return ind.add_all(d, bench["Close"] if bench is not None else None), bench


def check(sym):
    d, bench = _prices(sym)
    if d is None:
        return f"❌ No NSE data for {sym}. Use the NSE symbol, e.g. /check TATAMOTORS"
    r = d.iloc[-1].copy()
    r["ema200_up"] = d.ema200.iloc[-1] > d.ema200.iloc[-22]
    r["macd_hist_prev"] = d.macd_hist.iloc[-2]
    tech = stg.tech_score(r)
    sigs = [k for k, fn in stg.SWING.items() if bool(fn(d).iloc[-1])]
    btst = bool(stg.btst(d).iloc[-1])
    prob = None
    try:
        import joblib
        m = joblib.load(MODEL)
        F = ind.features(d, ind.add_all(bench))
        prob = float(m.predict_proba(F.iloc[[-1]][m.feats_])[:, 1][0]) * 100
    except Exception as e:
        print("model unavailable", e)
    plan = stg.trade_plan(r)
    verdict = ("🟢 BUY setup active" if sigs and tech >= 45 else
               "🟡 Strong trend – wait for a trigger" if stg.trend_template(d).iloc[-1] else
               "🔴 Avoid for swing now")
    L = [f"🔎 <b>{sym}</b> ₹{r.Close:.2f} ({r.day_chg:+.2f}%)", verdict,
         f"Setups: {', '.join(sigs) or 'none'}{' · ⚡BTST' if btst else ''}",
         f"Tech score {tech:.0f}/65 · AI win chance {prob:.1f}%" if prob is not None else f"Tech score {tech:.0f}/65",
         f"RSI {r.rsi:.0f} · ADX {r.adx:.0f} · Vol {r.vol_ratio:.1f}x · {r.from_high:.1f}% from 52W high",
         f"Trend: {'above' if r.Close > r.ema50 else 'below'} 50 EMA, {'above' if r.Close > r.ema200 else 'below'} 200 EMA · weekly {'up ✅' if r.wk_up else 'not up ❌'}",
         f"Plan: buy ~{plan['entry']} · SL {plan['stop']} (-{plan['risk_pct']}%) · T1 {plan['target1']} · T2 {plan['target2']}"]
    return "\n".join(L)


def top():
    try:
        o = json.load(open(PICKS))
    except Exception:
        return "No scan yet."
    L = [f"📊 <b>Top picks</b> ({o['generated']})"]
    for p in [p for p in o["picks"] if p["label"] not in ("WATCHLIST", "AVOID")][:6]:
        tag = "🎯" if p.get("mode85") else "🔥" if p.get("high_conviction") else p["stars"]
        L.append(f"{tag} <b>{p['symbol']}</b> {p['score']} · Buy {p['entry']} SL {p['stop']} T1 {p['target1']} · AI {p.get('ml_prob')}%")
    return "\n".join(L)


def handle(text, holdings):
    parts = text.strip().split()
    cmd = parts[0].lower().split("@")[0] if parts else ""
    if cmd in ("/start", "/help"):
        return __doc__.split("\n", 3)[3], holdings
    if cmd == "/check" and len(parts) >= 2 and _sym(parts[1]):
        return check(_sym(parts[1])), holdings
    if cmd == "/top":
        return top(), holdings
    if cmd == "/buy" and len(parts) >= 4 and _sym(parts[1]):
        sym = _sym(parts[1])
        try:
            price, qty = float(parts[2]), int(parts[3])
        except ValueError:
            return "Format: /buy SYMBOL PRICE QTY  e.g. /buy MCX 3720 3", holdings
        d, _ = _prices(sym)
        if d is None:
            return f"❌ No NSE data for {sym}", holdings
        try:
            m90 = {p["symbol"] for p in json.load(open(PICKS))["picks"] if p.get("mode90")}
        except Exception:
            m90 = set()
        mode90 = sym in m90 or (len(parts) >= 5 and parts[4] == "90")
        if mode90:  # tools/exit_research.py: half at +4%, rest trails 20 EMA, SL -25%
            stop, t1, t2 = round(price * 0.75, 2), round(price * 1.04, 2), round(price * 1.10, 2)
        else:
            stop, t1, t2 = portfolio.plan_for(price, d)
        holdings.append({"symbol": sym, "price": price, "qty": qty, "stop": stop, "t1": t1, "t2": t2,
                         "date": str(dt.date.today()), "t1_done": False, "mode90": mode90})
        return (f"✅ Saved {sym} {qty} @ {price}{' (🎯 90% MODE)' if mode90 else ''}\n"
                f"SL {stop} · T1 {t1} (sell half) · then trail 20 EMA\n"
                f"I'll alert you every hour if something needs action."), holdings
    if cmd == "/sell" and len(parts) >= 2 and _sym(parts[1]):
        sym = _sym(parts[1])
        if not any(h["symbol"] == sym for h in holdings):
            return f"{sym} is not in your portfolio", holdings
        qty = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else None
        left = []
        for h in holdings:
            if h["symbol"] == sym:
                if qty is None:
                    continue
                h["qty"] -= qty
                if h["qty"] <= 0:
                    continue
            left.append(h)
        return f"✅ {sym} updated ({'all sold' if qty is None else f'sold {qty}'})", left
    if cmd == "/half" and len(parts) >= 2 and _sym(parts[1]):
        sym = _sym(parts[1])
        for h in holdings:
            if h["symbol"] == sym:
                h["t1_done"] = True
                h["qty"] = h["qty"] - h["qty"] // 2
        return f"✅ {sym}: half booked, SL moved to cost.", holdings
    if cmd == "/portfolio":
        return portfolio_text(holdings), holdings
    if cmd == "/report":
        return validation_text()[0] or "No test report yet.", holdings
    return "Commands: /check SYMBOL · /top · /buy SYMBOL PRICE QTY · /sell SYMBOL [QTY] · /half SYMBOL · /portfolio · /report", holdings


VALIDATION = os.path.join(ROOT, "reports", "validation_90.md")


def validation_text():
    """reports/validation_90.md as a plain Telegram message."""
    import hashlib
    import html
    try:
        md = open(VALIDATION).read()
    except Exception:
        return None, None
    t = html.escape(md, quote=False)
    t = re.sub(r"^# (.*)$", r"📊 <b>\1</b>", t, flags=re.M)
    t = re.sub(r"^## (.*)$", r"\n<b>\1</b>", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"^- ", "• ", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t, hashlib.sha1(md.encode()).hexdigest()


def portfolio_text(holdings):
    revs = []
    for h in holdings:
        d, _ = _prices(h["symbol"])
        if d is not None:
            revs.append(portfolio.review(h, d))
    return portfolio.text(revs)


def morning(st):
    """Once per weekday at ~8:40 IST: numbered buy list from last evening's final scan."""
    from zoneinfo import ZoneInfo
    from scanner import report
    now = dt.datetime.now(ZoneInfo("Asia/Kolkata"))
    today = str(now.date())
    if now.weekday() >= 5 or st.get("morning_sent") == today or not (8 * 60 + 40 <= now.hour * 60 + now.minute <= 9 * 60 + 40):
        return
    try:
        o = json.load(open(PICKS))
    except Exception:
        return
    text = (f"🌅 <b>Good morning!</b> Buy list from the final scan of {o['data_date']}\n"
            f"Market {o['regime']['label']} · VIX {o['regime'].get('vix', '-')}"
            + report.simple_list(o, "🛒 <b>Today's swing BUY LIST</b>")
            + "\n\nTip: buy after 9:30 if the stock is above its opening price. Live updates every hour.")
    for chat in CHATS:
        send(chat, text)
    st["morning_sent"] = today


def main():
    if not TOK or not CHATS:
        print("Telegram not configured")
        return
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {"offset": 0}
    r = requests.get(f"{API}/getUpdates", params={"offset": st["offset"], "timeout": 0}, timeout=30).json()
    holdings = portfolio.load()
    before = json.dumps(holdings)
    for u in r.get("result", []):
        st["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        chat = str(msg.get("chat", {}).get("id", ""))
        if chat not in CHATS or not msg.get("text", "").startswith("/"):
            continue  # ignore strangers and plain text
        try:
            reply, holdings = handle(msg["text"], holdings)
        except Exception as e:
            reply = f"⚠️ Error: {e}"
        send(chat, reply)
    if json.dumps(holdings) != before:
        portfolio.save(holdings)
    # New or updated 90% MODE test report -> send it once automatically
    vt, vh = validation_text()
    if vt and st.get("validation_sent") != vh:
        for chat in CHATS:
            send(chat, vt)
        st["validation_sent"] = vh
    # morning(st)  # disabled: user wants hourly lists 9:15–3:15 instead of an 8:40 message
    json.dump(st, open(STATE, "w"))


if __name__ == "__main__":
    main()
