"""Nifty 500 Swing + BTST scanner.

python main.py                # full scan (swing + BTST + tracker + report)
python main.py --limit 50     # quick test on first 50 stocks
python main.py --no-news      # skip news / fundamentals (faster)
"""
import argparse
import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from scanner import backtest as bt
from scanner import data, fundamentals, news, report
from scanner import indicators as ind
from scanner import strategies as stg

ROOT = os.path.dirname(os.path.abspath(__file__))
IST = ZoneInfo("Asia/Kolkata")
TOP_N_ENRICH = 40
LOG = os.path.join(ROOT, "data", "pick_log.csv")


def market_regime(bench):
    b = ind.add_all(bench)
    r = b.iloc[-1]
    pts = int(r.Close > r.ema50) + int(r.ema50 > r.ema200) + int(r.Close > r.ema20) + int(r.st > 0)
    label = {4: "BULLISH", 3: "POSITIVE", 2: "NEUTRAL"}.get(pts, "BEARISH")
    mult = {4: 1.0, 3: 1.0, 2: 0.95}.get(pts, 0.9)
    return {"label": label, "mult": mult, "close": round(float(r.Close), 2),
            "ret21": round(float(r.ret21), 2), "rsi": round(float(r.rsi), 1)}


def rating(score):
    if score >= 80:
        return "★★★★★", "STRONG BUY"
    if score >= 70:
        return "★★★★☆", "BUY"
    if score >= 60:
        return "★★★☆☆", "ACCUMULATE"
    if score >= 50:
        return "★★☆☆☆", "WATCH"
    return "★☆☆☆☆", "AVOID"


def update_tracker(prices, today_picks, today):
    """Keeps a live record of every past pick and how it actually did."""
    cols = ["date", "symbol", "setup", "score", "entry", "stop", "target1", "target2"]
    log = pd.read_csv(LOG) if os.path.exists(LOG) else pd.DataFrame(columns=cols)
    log = log[[c for c in cols if c in log.columns]]
    new = pd.DataFrame([{**{k: p[k] for k in cols if k in p}, "date": today} for p in today_picks],
                       columns=cols)
    log = pd.concat([log[log.date != today], new], ignore_index=True)
    log.to_csv(LOG, index=False)

    rows = []
    for _, p in log.iterrows():
        d = prices.get(p.symbol)
        if d is None:
            continue
        fwd = d[d.index.date > dt.date.fromisoformat(str(p.date))].head(bt.HOLD)
        # Same management as the backtest: half booked at T1, stop moved to cost.
        status, ret, stop, t1 = "OPEN", None, p.stop, False
        for _, bar in fwd.iterrows():
            if bar.Low <= stop:
                rest = (stop / p.entry - 1) * 100
                status = "T1 + EXIT AT COST" if t1 else "STOP"
                ret = 2.5 + 0.5 * rest if t1 else rest
                break
            if not t1 and bar.High >= p.target1:
                t1, stop = True, p.entry
            if bar.High >= p.target2:
                status, ret = "TARGET 2", 7.5
                break
        if ret is None and len(fwd):
            rest = (fwd.Close.iloc[-1] / p.entry - 1) * 100
            ret = 2.5 + 0.5 * rest if t1 else rest
            status = "T1 HIT (running)" if t1 else "OPEN"
            if len(fwd) >= bt.HOLD:
                status = "EXPIRED"
        rows.append({**p.to_dict(), "status": status, "days": len(fwd),
                     "ret": round(ret, 2) if ret is not None else None})
    t = pd.DataFrame(rows)
    stats = {}
    if len(t):
        closed = t[t.status.isin(["STOP", "TARGET 2", "T1 + EXIT AT COST", "EXPIRED"])]
        if len(closed):
            stats = {"closed": len(closed),
                     "win_rate": round((closed.ret > 0).mean() * 100, 1),
                     "avg_ret": round(closed.ret.mean(), 2)}
        stats["open"] = int(t.status.isin(["OPEN", "T1 HIT (running)"]).sum())
    return t, stats


def telegram(text):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      data={"chat_id": chat, "text": text[:4000], "parse_mode": "HTML",
                            "disable_web_page_preview": "true"}, timeout=20)
    except Exception as e:
        print("telegram failed", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-news", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now(IST)
    universe = data.load_universe()
    if args.limit:
        universe = universe.head(args.limit)
    meta = universe.set_index("Symbol").to_dict("index")
    print(f"Universe: {len(universe)} stocks")

    bench = data.download([data.BENCH]).get(data.BENCH)
    if bench is None:
        bench = data.download([data.NIFTY]).get(data.NIFTY)
    regime = market_regime(bench)
    print("Market:", regime)

    prices = data.download(universe.Symbol.tolist())
    print(f"Downloaded {len(prices)} stocks")
    last_date = max(d.index[-1] for d in prices.values()).date()

    rows, swing_bt, btst_bt = [], {k: [] for k in stg.SWING}, []
    for sym, raw in prices.items():
        try:
            d = ind.add_all(raw, bench["Close"])
        except Exception as e:
            print("indicator error", sym, e)
            continue
        if d.index[-1].date() < last_date - dt.timedelta(days=5):
            continue  # stale / suspended
        sigs, per_stock = {}, {}
        for name, fn in stg.SWING.items():
            s = fn(d)
            trades = bt.swing_trades(d, s)
            swing_bt[name] += trades
            per_stock[name] = bt.summarize_swing(trades)
            sigs[name] = bool(s.iloc[-1])
        b = stg.btst(d)
        btst_bt += bt.btst_trades(d, b)
        r = d.iloc[-1].copy()
        r["ema200_up"] = d.ema200.iloc[-1] > d.ema200.iloc[-22]
        r["macd_hist_prev"] = d.macd_hist.iloc[-2]
        rows.append({
            "symbol": sym, "name": meta[sym]["Name"], "industry": meta[sym]["Industry"],
            "row": r, "signals": [k for k, v in sigs.items() if v], "btst": bool(b.iloc[-1]),
            "trend": bool(stg.trend_template(d).iloc[-1]), "bt": per_stock,
            "tech": stg.tech_score(r),
            "spark": [round(x, 2) for x in d.Close.tail(60).tolist()],
        })

    swing_stats = {k: bt.summarize_swing(v) for k, v in swing_bt.items()}
    btst_stats = bt.summarize_btst(btst_bt)
    print("Backtest swing:", swing_stats)
    print("Backtest BTST:", btst_stats)

    # Relative strength percentile across the whole universe (0-10 pts)
    df = pd.DataFrame(rows)
    rsraw = [0.4 * x["row"].ret63 + 0.2 * x["row"].ret126 + 0.2 * x["row"].ret21
             + 0.2 * (x["row"].get("rs63", 0) or 0) for x in rows]
    df["rs_rank"] = pd.Series(rsraw).rank(pct=True).fillna(0).values * 100
    df["rs_pts"] = df.rs_rank / 10

    def edge(x):
        """Backtest edge 0-5: win rate (target +5% before stop) of this stock's
        own setups, or the universe-wide rate for its setup when few samples."""
        names = x.signals or ["Breakout"]
        rates = []
        for n in names:
            ps = x.bt[n]
            rates.append(ps["win5"] if ps["n"] >= 4 else swing_stats[n]["win5"])
        w = np.nanmean(rates) if rates else np.nan
        return 0 if np.isnan(w) else float(np.clip((w - 40) / 30 * 5, 0, 5)), w

    e = df.apply(edge, axis=1, result_type="expand")
    df["edge_pts"], df["hist_win"] = e[0], e[1]
    df["pre"] = df.tech + df.rs_pts + df.edge_pts + 5 * (df.signals.str.len() > 0)

    cand = df[(df.signals.str.len() > 0) | (df.trend & (df.tech >= 45))]
    cand = cand.sort_values("pre", ascending=False).head(TOP_N_ENRICH).copy()
    btst_c = df[df.btst].copy()
    enrich = set(cand.symbol) | set(btst_c.symbol)

    fund, nws = {}, {}
    for sym in enrich:
        if args.no_news:
            fund[sym], nws[sym] = {}, []
            continue
        fund[sym] = fundamentals.fetch(sym)
        nws[sym] = news.headlines(meta[sym]["Name"], sym)

    picks = []
    for _, x in cand.iterrows():
        f, h = fund.get(x.symbol, {}), nws.get(x.symbol, [])
        sent = news.sentiment(h)
        fpts = fundamentals.score(f) if f else 7.5
        npts = news.score(sent)
        total = (x.tech + x.rs_pts + x.edge_pts + fpts + npts) * regime["mult"]
        warn = []
        rid = f.get("results_in_days")
        if rid is not None and 0 <= rid <= 7:
            total -= 5
            warn.append(f"Results in {rid} days – event risk")
        if x.row.rsi > 75:
            warn.append("RSI overbought – wait for dip")
        if x.row.ret5 > 12:
            warn.append("Up >12% in 5 days – extended")
        total = round(float(np.clip(total, 0, 100)), 1)
        stars, label = rating(total)
        if not x.signals and total >= 60:
            label = "WATCHLIST"  # strong trend but no entry trigger today
        plan = stg.trade_plan(x.row)
        picks.append({
            "symbol": x.symbol, "name": x["name"], "industry": x.industry,
            "setup": ", ".join(x.signals) or "Uptrend",
            "score": total, "stars": stars, "label": label, **plan,
            "close": round(x.row.Close, 2), "chg": round(x.row.day_chg, 2),
            "rsi": round(x.row.rsi, 1), "adx": round(x.row.adx, 1),
            "vol_x": round(x.row.vol_ratio, 2), "from_high": round(x.row.from_high, 1),
            "rs_rank": round(x.rs_rank), "hist_win5": None if np.isnan(x.hist_win) else round(x.hist_win, 1),
            "parts": {"Technical": round(x.tech), "Rel. Strength": round(x.rs_pts, 1),
                      "Fundamentals": round(fpts, 1), "News": npts, "Backtest": round(x.edge_pts, 1)},
            "fund": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in f.items()},
            "news": h[:3], "sentiment": round(sent, 2), "warnings": warn, "spark": x.spark,
        })
    picks.sort(key=lambda p: (p["label"] == "WATCHLIST", -p["score"], p["symbol"]))

    btst = []
    for _, x in btst_c.iterrows():
        h = nws.get(x.symbol, [])
        sent = news.sentiment(h)
        sc = min(100, 40 + 10 * min(x.row.vol_ratio, 4) / 2 + 20 * x.row.close_pos
                 + x.rs_pts + 5 * sent * 2) * regime["mult"]
        btst.append({
            "symbol": x.symbol, "name": x["name"], "score": round(sc, 1),
            "stars": rating(sc)[0], "close": round(x.row.Close, 2),
            "chg": round(x.row.day_chg, 2), "vol_x": round(x.row.vol_ratio, 2),
            "stop": round(x.row.Low, 2), "target": round(x.row.Close * 1.02, 2),
            "news": h[:2], "sentiment": round(sent, 2),
        })
    btst.sort(key=lambda p: -p["score"])

    today = str(last_date)
    tracked = [p for p in picks if p["score"] >= 70 and p["setup"] != "Uptrend"][:10]
    track, live = update_tracker(prices, tracked, today)

    breadth = {
        "above_ema50": round((df.row.apply(lambda r: r.Close > r.ema50)).mean() * 100, 1),
        "above_ema200": round((df.row.apply(lambda r: r.Close > r.ema200)).mean() * 100, 1),
        "new_52w_high": int(df.row.apply(lambda r: r.from_high >= -2).sum()),
        "signals": int((df.signals.str.len() > 0).sum()),
    }
    out = {
        "generated": now.strftime("%Y-%m-%d %H:%M IST"), "data_date": today,
        "regime": regime, "breadth": breadth, "universe": len(df),
        "swing_backtest": swing_stats, "btst_backtest": btst_stats,
        "picks": picks, "btst": btst[:15], "live": live,
        "tracker": track.tail(40).to_dict("records") if len(track) else [],
    }
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "docs", "picks.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    with open(os.path.join(ROOT, "docs", "index.html"), "w") as fh:
        fh.write(report.html(out))
    md = report.markdown(out)
    for name in ("latest.md", f"{today}.md"):
        with open(os.path.join(ROOT, "reports", name), "w") as fh:
            fh.write(md)
    telegram(report.telegram_text(out))
    print(md[:3000])


if __name__ == "__main__":
    main()
