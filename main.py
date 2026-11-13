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
from scanner import data, fundamentals, model, news, portfolio, report
from scanner import indicators as ind
from scanner import strategies as stg

ROOT = os.path.dirname(os.path.abspath(__file__))
IST = ZoneInfo("Asia/Kolkata")
TOP_N_ENRICH = 40
LOG = os.path.join(ROOT, "data", "pick_log.csv")
CONFIG = os.path.join(ROOT, "config.json")


def load_config():
    cfg = {"capital": 100000, "risk_per_trade_pct": 1.0, "max_position_pct": 20}
    try:
        cfg.update(json.load(open(CONFIG)))
    except Exception:
        pass
    return cfg


def position_size(entry, stop, cfg):
    """Shares to buy so that hitting the stop loses only risk_per_trade_pct of capital."""
    risk_amt = cfg["capital"] * cfg["risk_per_trade_pct"] / 100
    per_share = max(entry - stop, 0.01)
    qty = int(min(risk_amt / per_share, cfg["capital"] * cfg["max_position_pct"] / 100 / entry))
    return {"qty": qty, "invest": round(qty * entry), "max_loss": round(qty * per_share)}


PATTERNS = {"engulf": "Bullish engulfing", "hammer": "Hammer", "inside_brk": "Inside-bar breakout",
            "nr7": "NR7 breakout"}


def reasons(r, signals, rs_rank, sector_top):
    why = []
    if "A+ Momentum" in signals:
        why.append("A+ setup: near 52W high with strong relative strength")
    if r.Close > r.hh55:
        why.append("Broke 55-day high")
    if r.vol_ratio >= 1.5:
        why.append(f"Volume {r.vol_ratio:.1f}x average")
    if r.ema50 > r.ema200 and r.Close > r.ema50:
        why.append("Price > 50 EMA > 200 EMA (uptrend)")
    if r.wk_up:
        why.append("Weekly trend up")
    if rs_rank >= 80:
        why.append(f"Top {100 - rs_rank:.0f}% relative strength in Nifty 500")
    if r.vcp < 0.5:
        why.append("Tight base (volatility contraction)")
    if sector_top:
        why.append("Sector is among market leaders")
    return why[:6]


def market_regime(bench):
    b = ind.add_all(bench)
    r = b.iloc[-1]
    pts = int(r.Close > r.ema50) + int(r.ema50 > r.ema200) + int(r.Close > r.ema20) + int(r.st > 0)
    label = {4: "BULLISH", 3: "POSITIVE", 2: "NEUTRAL"}.get(pts, "BEARISH")
    mult = {4: 1.0, 3: 1.0, 2: 0.95}.get(pts, 0.9)
    out = {"label": label, "mult": mult, "close": round(float(r.Close), 2),
           "ret21": round(float(r.ret21), 2), "rsi": round(float(r.rsi), 1),
           "day": round(float(r.day_chg), 2)}
    # India VIX (fear gauge): high VIX = bigger swings, stops hit more often
    try:
        v = data.download([data.VIX], period="1y").get(data.VIX)
        if v is not None:
            vix, avg = float(v.Close.iloc[-1]), float(v.Close.tail(50).mean())
            out["vix"] = round(vix, 2)
            out["vix_note"] = ("HIGH – trade smaller" if vix >= 20 else
                               "rising – be careful" if vix > avg * 1.15 else "calm")
            if vix >= 20:
                out["mult"] = round(out["mult"] * 0.95, 3)
    except Exception as e:
        print("vix failed", e)
    return out


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
        e20 = ind.ema(d.Close, 20)
        fwd = d[d.index.date > dt.date.fromisoformat(str(p.date))].head(bt.HOLD)
        # Same management as the backtest: half booked at T1, stop moved to cost,
        # rest exits on a close below the 20 EMA.
        status, ret, stop, t1 = "OPEN", None, p.stop, False
        for ts, bar in fwd.iterrows():
            if bar.Low <= stop:
                rest = (stop / p.entry - 1) * 100
                status = "T1 + EXIT AT COST" if t1 else "STOP"
                ret = 2.5 + 0.5 * rest if t1 else rest
                break
            if not t1 and bar.High >= p.target1:
                t1, stop = True, p.entry
            if t1 and bar.Close < e20[ts]:
                rest = (max(bar.Close, stop) / p.entry - 1) * 100
                status, ret = "T1 + TRAIL EXIT", 2.5 + 0.5 * rest
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
        closed = t[t.status.isin(["STOP", "T1 + TRAIL EXIT", "T1 + EXIT AT COST", "EXPIRED"])]
        if len(closed):
            stats = {"closed": len(closed),
                     "win_rate": round((closed.ret > 0).mean() * 100, 1),
                     "avg_ret": round(closed.ret.mean(), 2)}
        stats["open"] = int(t.status.isin(["OPEN", "T1 HIT (running)"]).sum())
    return t, stats


def telegram(text):
    """Sends to every chat id in TELEGRAM_CHAT_ID (comma separated), split into
    4000-char chunks on line breaks."""
    tok, chats = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID", "")
    if not (tok and chats):
        print("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) > 3900:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    parts.append(cur)
    for chat in [c.strip() for c in chats.split(",") if c.strip()]:
        for part in parts:
            try:
                r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                                  data={"chat_id": chat, "text": part, "parse_mode": "HTML",
                                        "disable_web_page_preview": "true"}, timeout=20)
                if not r.ok:
                    print("telegram error", r.status_code, r.text[:200])
            except Exception as e:
                print("telegram failed", e)


STATE = os.path.join(ROOT, "data", "state.json")


def load_state(today):
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    if st.get("date") != today:
        st = {"date": today, "seen": {}, "status": st.get("status", {})}
    return st


def market_session(now):
    """(is_open, minutes elapsed since 9:15 IST)."""
    if now.weekday() >= 5:
        return False, 0
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    mins = (now - start).total_seconds() / 60
    return 0 <= mins <= 375, mins


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
    bench_ind = ind.add_all(bench)
    cfg = load_config()
    print("Market:", regime)

    prices = data.download(universe.Symbol.tolist())
    print(f"Downloaded {len(prices)} stocks")
    last_date = max(d.index[-1] for d in prices.values()).date()
    is_open, mins = market_session(now)
    intraday = is_open and last_date == now.date()
    pace = 1.0
    if intraday:
        # Volume so far only covers part of the day: project full-day volume
        # (U-shaped intraday volume, so early hours get a softer multiplier).
        frac = min(1.0, max(mins, 15) / 375)
        pace = min(1 / (frac ** 0.85), 20.0)
        for d in prices.values():
            if d.index[-1].date() == last_date:
                d.iloc[-1, d.columns.get_loc("Volume")] *= pace
        print(f"Intraday run: {mins:.0f} min into session, volume pace x{pace:.2f}")

    rows, swing_bt, btst_bt, samples = [], {k: [] for k in stg.SWING}, [], []
    for sym, raw in prices.items():
        try:
            d = ind.add_all(raw, bench["Close"])
        except Exception as e:
            print("indicator error", sym, e)
            continue
        if d.index[-1].date() < last_date - dt.timedelta(days=5):
            continue  # stale / suspended
        sigs, per_stock, union = {}, {}, None
        for name, fn in stg.SWING.items():
            s = fn(d)
            union = s if union is None else (union | s)
            trades = bt.swing_trades(d, s)
            swing_bt[name] += trades
            per_stock[name] = bt.summarize_swing(trades)
            sigs[name] = bool(s.iloc[-1])
        b = stg.btst(d)
        btst_bt += bt.btst_trades(d, b)
        F = ind.features(d, bench_ind)
        done = [t for t in bt.swing_trades(d, union) if t["complete"]]
        if done:
            sm = F.loc[[t["date"] for t in done]].copy()
            sm["date"] = [t["date"] for t in done]
            sm["win5"] = [int(t["win5"]) for t in done]
            sm["ret"] = [t["ret"] for t in done]
            sm["ret85"] = [bt.fixed_outcome(d, d.index.get_loc(t["date"])) for t in done]
            samples.append(sm)
        r = d.iloc[-1].copy()
        r["ema200_up"] = d.ema200.iloc[-1] > d.ema200.iloc[-22]
        r["macd_hist_prev"] = d.macd_hist.iloc[-2]
        rows.append({
            "symbol": sym, "name": meta[sym]["Name"], "industry": meta[sym]["Industry"],
            "row": r, "signals": [k for k, v in sigs.items() if v], "btst": bool(b.iloc[-1]),
            "trend": bool(stg.trend_template(d).iloc[-1]), "bt": per_stock,
            "tech": stg.tech_score(r), "feat": F.iloc[-1],
            "patterns": [v for k, v in PATTERNS.items() if bool(r.get(k, False))],
            "spark": [round(x, 2) for x in d.Close.tail(60).tolist()],
        })

    swing_stats = {k: bt.summarize_swing(v) for k, v in swing_bt.items()}
    btst_stats = bt.summarize_btst(btst_bt)
    print("Backtest swing:", swing_stats)
    print("Backtest BTST:", btst_stats)

    ml, ml_rep = model.train(pd.concat(samples) if samples else pd.DataFrame())
    if ml is not None:
        import joblib
        joblib.dump(ml, os.path.join(ROOT, "data", "ml.pkl"))  # used by the Telegram /check command
    print("ML model:", ml_rep)

    # Relative strength percentile across the whole universe (0-10 pts)
    df = pd.DataFrame(rows)
    rsraw = [0.4 * x["row"].ret63 + 0.2 * x["row"].ret126 + 0.2 * x["row"].ret21
             + 0.2 * (x["row"].get("rs63", 0) or 0) for x in rows]
    df["rs_rank"] = pd.Series(rsraw).rank(pct=True).fillna(0).values * 100
    df["rs_pts"] = df.rs_rank / 10
    df["day"] = df.row.apply(lambda r: r.day_chg)
    df["ml_prob"] = model.predict(ml, pd.DataFrame(df.feat.tolist())) if ml is not None else np.nan
    sec = df.groupby("industry").agg(rs=("rs_rank", "mean"), day=("day", "mean"),
                                     n=("symbol", "size"))
    sec = sec[sec.n >= 3].sort_values("rs", ascending=False)
    top_sectors = list(sec.index[:5])
    sectors = [{"name": k, "rs": round(v.rs), "day": round(v.day, 2), "n": int(v.n)}
               for k, v in sec.head(8).iterrows()]

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
    # never drop a stock that could qualify for 85% mode
    m85c = df[(df.signals.str.len() > 0) & (df.ml_prob >= ml_rep.get("m85_threshold", 1))]
    cand = pd.concat([cand, m85c[~m85c.symbol.isin(cand.symbol)]])
    btst_c = df[df.btst].copy()
    enrich = set(cand.symbol) | set(btst_c.symbol)

    intra = data.intraday(sorted(enrich)) if intraday else {}
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
        mlpts = model.points(x.ml_prob, ml_rep)
        # weights: tech 65, RS 10, fundamentals 15, news 5, backtest 5, ML 10 -> scaled to 100
        total = (x.tech + x.rs_pts + x.edge_pts + fpts + npts + mlpts) / 110 * 100 * regime["mult"]
        if x.industry in top_sectors:
            total += 3  # leading sector tailwind
        if x.patterns:
            total += 2
        warn = []
        if not x.row.wk_up:
            total -= 3
            warn.append("Weekly trend not confirmed")
        iv = intra.get(x.symbol)
        if iv:
            if not iv["above_vwap"]:
                total -= 3
                warn.append("Trading below today's VWAP – wait")
            else:
                total += 1
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
        plan.update(position_size(plan["entry"], plan["stop"], cfg))
        picks.append({
            "symbol": x.symbol, "name": x["name"], "industry": x.industry,
            "setup": ", ".join(x.signals) or "Uptrend",
            "score": total, "stars": stars, "label": label, **plan,
            "close": round(x.row.Close, 2), "chg": round(x.row.day_chg, 2),
            "rsi": round(x.row.rsi, 1), "adx": round(x.row.adx, 1),
            "vol_x": round(x.row.vol_ratio, 2), "from_high": round(x.row.from_high, 1),
            "rs_rank": round(x.rs_rank), "hist_win5": None if np.isnan(x.hist_win) else round(x.hist_win, 1),
            "parts": {"Technical": round(x.tech), "Rel. Strength": round(x.rs_pts, 1),
                      "Fundamentals": round(fpts, 1), "News": npts, "Backtest": round(x.edge_pts, 1),
                      "AI model": round(mlpts, 1)},
            "ml_prob": None if np.isnan(x.ml_prob) else round(float(x.ml_prob) * 100, 1),
            "patterns": x.patterns, "weekly_up": bool(x.row.wk_up), "intra": iv,
            "why": reasons(x.row, x.signals, x.rs_rank, x.industry in top_sectors),
            "mode85": bool(
                x.signals and ml_rep.get("m85_win", 0) >= 80 and not np.isnan(x.ml_prob)
                and x.ml_prob >= ml_rep.get("m85_threshold", 1) and x.row.wk_up
                and not (rid is not None and 0 <= rid <= 7)),
            "m85_target": round(x.row.Close * 1.05, 2), "m85_stop": round(x.row.Close * 0.85, 2),
            "m85_qty": position_size(x.row.Close, x.row.Close * 0.85, cfg)["qty"],
            "high_conviction": bool(
                x.signals and ml_rep.get("useful") and not np.isnan(x.ml_prob)
                and x.ml_prob >= ml_rep.get("hc_threshold", 1) and x.row.wk_up
                and not (rid is not None and 0 <= rid <= 7) and total >= 70
                and not (iv and not iv["above_vwap"])),
            "fund": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in f.items()},
            "news": h[:3], "sentiment": round(sent, 2), "warnings": warn, "spark": x.spark,
        })
    picks.sort(key=lambda p: (p["label"] == "WATCHLIST", not p["high_conviction"], -p["score"], p["symbol"]))

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

    # Your real holdings (saved via Telegram /buy) – reviewed every run
    hold_reviews = []
    for h in portfolio.load():
        d = prices.get(h["symbol"])
        if d is None:
            d = data.download([h["symbol"]]).get(h["symbol"])
        if d is not None:
            try:
                hold_reviews.append(portfolio.review(h, ind.add_all(d)))
            except Exception as e:
                print("holding review failed", h["symbol"], e)

    # Friday end-of-day: weekly summary of the picks tracker
    weekly = None
    if not intraday and now.weekday() == 4 and len(track):
        wk = track[pd.to_datetime(track.date) >= pd.Timestamp(now.date()) - pd.Timedelta(days=6)]
        weekly = {"new_picks": int(len(wk)),
                  "best": track.sort_values("ret", ascending=False).head(3)[["symbol", "ret", "status"]].to_dict("records"),
                  **live}

    # New-since-last-report flags and target / stop alerts for tracked picks
    state = load_state(today)
    stamp = now.strftime("%H:%M")
    for p in picks + btst:
        key = ("B:" if "target" in p and "target1" not in p else "S:") + p["symbol"]
        p["new"] = key not in state["seen"] and p.get("label") != "WATCHLIST"
        state["seen"].setdefault(key, stamp)
    alerts = []
    for t in (track.to_dict("records") if len(track) else []):
        k = f"{t['date']}:{t['symbol']}"
        prev = state["status"].get(k)
        if prev is not None and t["status"] != prev:
            alerts.append({**t, "prev": prev})
        state["status"][k] = t["status"]
    with open(STATE, "w") as fh:
        json.dump(state, fh, indent=1)

    breadth = {
        "above_ema50": round((df.row.apply(lambda r: r.Close > r.ema50)).mean() * 100, 1),
        "above_ema200": round((df.row.apply(lambda r: r.Close > r.ema200)).mean() * 100, 1),
        "new_52w_high": int(df.row.apply(lambda r: r.from_high >= -2).sum()),
        "signals": int((df.signals.str.len() > 0).sum()),
    }
    out = {
        "generated": now.strftime("%Y-%m-%d %H:%M IST"), "data_date": today,
        "intraday": intraday, "session_min": round(mins), "sectors": sectors,
        "alerts": alerts, "ml": ml_rep, "config": cfg, "holdings": hold_reviews,
        "weekly": weekly, "adv": int((df.day > 0).sum()), "dec": int((df.day < 0).sum()),
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
