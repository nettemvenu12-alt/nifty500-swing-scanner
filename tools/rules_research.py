"""Test the user's 6-rule checklist on 10 years of data (dev tool).

Compares exit variants (old stop vs swing-low/1.5xATR stop, with/without 15-day time stop)
and the effect of each entry filter.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from scanner import backtest as bt, data, indicators as ind, strategies as stg

HOLD = 60


def stop_old(d, i):
    return bt._stops(d).values[i]


def stop_new(d, i):
    e, a = d.Close.values[i], d.atr.values[i]
    swing = d.ll10.values[i] - 0.1 * a
    st = max(swing, e - 1.5 * a)          # tighter of swing low / 1.5 ATR
    return min(st, e * 0.98)              # at least 2% room


def manage(d, i, st, tstop=None):
    hi, lo, cl, e20 = d.High.values, d.Low.values, d.Close.values, d.ema20.values
    e, end, t1 = cl[i], min(i + HOLD, len(d) - 1), False
    for j in range(i + 1, end + 1):
        if lo[j] <= st:
            rest = (st / e - 1) * 100
            return (2.5 + 0.5 * rest if t1 else rest), j - i
        if not t1 and hi[j] >= e * 1.05:
            t1, st = True, e
        if t1 and cl[j] < e20[j]:
            return 2.5 + 0.5 * (max(cl[j], st) / e - 1) * 100, j - i
        if tstop and not t1 and j - i >= tstop and cl[j] < e * 1.02:
            return (cl[j] / e - 1) * 100, j - i
    rest = (cl[end] / e - 1) * 100
    return (2.5 + 0.5 * rest if t1 else rest), end - i


u = data.load_universe()
meta = u.set_index("Symbol").Industry.to_dict()
b500 = data.download([data.BENCH], period="10y")[data.BENCH]
n50 = data.download([data.NIFTY], period="10y")[data.NIFTY]
N = n50.Close
mkt_full = (N > N.rolling(50).mean()) & (N > N.rolling(200).mean())
mkt_part = (N > N.rolling(200).mean()) & ~mkt_full
n50_r63 = N.pct_change(63) * 100
px = data.download(u.Symbol.tolist(), period="10y")
rows, rs_tab = [], {}
for sym, raw in px.items():
    d = ind.add_all(raw, b500.Close)
    rs_tab[sym] = d.rs63
    brk = (stg.swing_breakout(d) | stg.high52_breakout(d) | stg.squeeze_breakout(d) | stg.results_gap(d)).fillna(False).values
    pb = stg.pullback_buy(d).fillna(False).values
    ap = stg.a_plus(d).fillna(False).values
    base = ((d.High.rolling(30).max().shift() - d.Low.rolling(30).min().shift()) / d.Close.shift() * 100).values
    gap = (d.Open / d.Close.shift() - 1).values * 100
    last = -10
    for i in np.flatnonzero(brk | pb | ap):
        if i - last < 10 or i < 250 or i + 2 >= len(d):
            continue
        last = i
        r = d.iloc[i]
        t = d.index[i]
        so, sn = stop_old(d, i), stop_new(d, i)
        rec = {"sym": sym, "date": t, "ind": meta.get(sym, "?"), "brk": bool(brk[i]), "pb": bool(pb[i]),
               "mkt_full": bool(mkt_full.get(t, False)), "mkt_part": bool(mkt_part.get(t, False)),
               "rs_n50": r.ret63 - n50_r63.get(t, np.nan), "ema_stack": r.ema20 > r.ema50 > r.ema200,
               "rsi": r.rsi, "base": base[i], "vol": r.vol_ratio, "gap": gap[i],
               "rr_new": 10 / max((1 - sn / r.Close) * 100, 0.01), "rr_old": 10 / max((1 - so / r.Close) * 100, 0.01)}
        for name, st, ts in [("A", so, None), ("B", sn, None), ("C", so, 15), ("D", sn, 15)]:
            rec[f"ret{name}"], rec[f"days{name}"] = manage(d, i, st, ts)
        rows.append(rec)
S = pd.DataFrame(rows)
RS = pd.DataFrame(rs_tab)
sec = RS.T.groupby(pd.Series(meta)).mean().T.rank(axis=1, pct=True, ascending=False)  # small = strong
S["sec_top"] = [sec.at[t, s] <= 0.5 if (t in sec.index and s in sec.columns) else False for t, s in zip(S.date, S.ind)]
print(f"{len(S)} signals {S.date.min().date()}..{S.date.max().date()}")


def show(name, g, v="A"):
    r, dd = g[f"ret{v}"], g[f"days{v}"]
    print(f"{name:52s} n={len(g):5d} profit {(r > 0).mean()*100:4.0f}%  avg {r.mean():+5.2f}%  days {dd.mean():4.1f}"
          f"  %/day {r.mean()/dd.mean():+.3f}")


print("\n== Exit variants (all signals) ==")
for v, lab in [("A", "old stop (10d low / 2.5 ATR)"), ("B", "new stop (swing low / 1.5 ATR)"),
               ("C", "old stop + 15-day time stop"), ("D", "new stop + 15-day time stop")]:
    show(lab, S, v)

user_ok = (S.mkt_full & (S.rs_n50 > 0) & S.sec_top & S.ema_stack & S.rsi.between(50, 70) & (S.gap <= 3)
           & (~S.brk | ((S.vol >= 1.5) & (S.base <= 20))))
print("\n== Entry filters (old exits A) ==")
show("baseline", S)
show("1 market: Nifty50 > 50 & 200 DMA", S[S.mkt_full])
show("1b market only above 200 (reduced)", S[S.mkt_part])
show("1c market below 200", S[~S.mkt_full & ~S.mkt_part])
show("2 RS > Nifty 50", S[S.rs_n50 > 0])
show("2 sector top half", S[S.sec_top])
show("2 EMA 20>50>200", S[S.ema_stack])
show("3 RSI 50-70", S[S.rsi.between(50, 70)])
show("3 breakout: vol>=1.5 & base<=20%", S[S.brk & (S.vol >= 1.5) & (S.base <= 20)])
show("3 breakout: other", S[S.brk & ~((S.vol >= 1.5) & (S.base <= 20))])
show("4 no gap-chase (gap <= 3%)", S[S.gap <= 3])
show("4 gap > 3%", S[S.gap > 3])
show("5 RR >= 2 (new stop)", S[S.rr_new >= 2])
show("ALL USER RULES", S[user_ok])
for v in "ABCD":
    show(f"ALL USER RULES, exit {v}", S[user_ok], v)
    show(f"ALL USER RULES + RR>=2, exit {v}", S[user_ok & (S.rr_new >= 2)], v)
print("\n== ALL USER RULES (exit D) per year ==")
g = S[user_ok].copy()
g["y"] = g.date.dt.year
print(g.groupby("y").agg(n=("retD", "size"), profit=("retD", lambda x: (x > 0).mean() * 100),
                          avg=("retD", "mean"), oldavg=("retA", "mean")).round(2))

print("\n== ADOPTED COMBO (rules that helped) ==")
adopt = (S.mkt_full & (S.rs_n50 > 0) & S.sec_top & S.ema_stack & (S.rsi < 80) & (~S.brk | (S.vol >= 1.5)))
for v in "AC":
    show(f"adopted, exit {v}", S[adopt], v)
g = S[adopt].copy(); g["y"] = g.date.dt.year
print(g.groupby("y").agg(n=("retA", "size"), profit=("retA", lambda x: (x > 0).mean() * 100),
                          avg=("retA", "mean")).round(2))
