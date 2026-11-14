"""After a 5%+ one-day fall: buy or avoid? (dev tool, 5 years, buy at that day's close)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd

from scanner import backtest as bt, data, indicators as ind, strategies as stg

u = data.load_universe()
seg = data.load_segments()
bench = data.download([data.BENCH])[data.BENCH]
B = ind.add_all(bench)
mkt_up = (B.Close > B.ema200)
px = data.download(u.Symbol.tolist())
rows = []
for sym, raw in px.items():
    try:
        d = ind.add_all(raw, bench.Close)
    except Exception:
        continue
    liq = stg._liquid(d).values
    for i in np.flatnonzero((d.day_chg <= -5).values):
        if i < 250 or i + 61 >= len(d) or not liq[i]:
            continue
        r = d.iloc[i]
        rows.append({"seg": seg.get(sym, "Other"), "year": d.index[i].year,
                     "up200": bool(r.Close > r.ema200), "stage2": bool(stg.trend_template(d).iloc[i - 1]),
                     "rs": float(r.rs63) if r.rs63 == r.rs63 else 0.0, "vol": float(r.vol_ratio),
                     "big": bool(r.day_chg <= -8), "mkt": bool(mkt_up.asof(d.index[i])),
                     "rsi": float(r.rsi),
                     "r515": bt.fixed_outcome(d, i), "r425": bt.fixed_outcome(d, i, 4, 25),
                     "r58": bt.fixed_outcome(d, i, 5, 8)})
R = pd.DataFrame(rows)


def show(name, g):
    if len(g) < 40:
        print(f"{name:55s} n={len(g)} (too few)"); return
    yw = g.groupby("year").r515.apply(lambda x: (x > 0).mean() * 100)
    print(f"{name:55s} n={len(g):5d} | +5/-15 win {(g.r515>0).mean()*100:4.1f}% avg {g.r515.mean():+.2f} (worst yr {yw.min():.0f}%)"
          f" | +4/-25 win {(g.r425>0).mean()*100:4.1f}% avg {g.r425.mean():+.2f} | +5/-8 win {(g.r58>0).mean()*100:4.1f}% avg {g.r58.mean():+.2f}")


show("all 5%+ falls", R)
show("stock above 200 EMA", R[R.up200])
show("stock below 200 EMA", R[~R.up200])
show("was stage-2 uptrend", R[R.stage2])
show("above 200 EMA + market above 200 EMA", R[R.up200 & R.mkt])
show("above 200 + mkt up + RS>0", R[R.up200 & R.mkt & (R.rs > 0)])
show("above 200 + mkt up + fall < 8%", R[R.up200 & R.mkt & ~R.big])
show("above 200 + mkt up + RS>0 + fall<8%", R[R.up200 & R.mkt & (R.rs > 0) & ~R.big])
show("above 200 + mkt up + RSI<30", R[R.up200 & R.mkt & (R.rsi < 30)])
show("fall 8%+ (big)", R[R.big])
show("high volume fall (vol>2x)", R[R.vol > 2])
show("market below 200 EMA", R[~R.mkt])
for s, g in R.groupby("seg"):
    show(f"  {s}: all", g)
    show(f"  {s}: above 200 + mkt up + RS>0", g[g.up200 & g.mkt & (g.rs > 0)])
