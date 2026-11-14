"""Does buying BEFORE the breakout work? (dev tool)
Early = stage-2 uptrend, price within a few % under the 55-day high, tight base.
Compares buying at that day's close with the normal (after-breakout) setups."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd

from scanner import backtest as bt, data, indicators as ind, strategies as stg

u = data.load_universe()
bench = data.download([data.BENCH])[data.BENCH]
px = data.download(u.Symbol.tolist())
VAR = {
    "A within 3%, vcp<0.5": lambda d: (d.Close <= d.hh55) & (d.Close >= d.hh55 * 0.97) & (d.vcp < 0.5),
    "B within 3%, vcp<0.5, squeeze": lambda d: (d.Close <= d.hh55) & (d.Close >= d.hh55 * 0.97) & (d.vcp < 0.5) & (d.bbw_rank <= 0.35),
    "C within 2%, squeeze, RS>5": lambda d: (d.Close <= d.hh55) & (d.Close >= d.hh55 * 0.98) & (d.bbw_rank <= 0.35) & (d.rs63 > 5),
    "D within 3%, squeeze, RS>10, vol dry": lambda d: (d.Close <= d.hh55) & (d.Close >= d.hh55 * 0.97) & (d.bbw_rank <= 0.35) & (d.rs63 > 10) & (d.vol_ratio < 1),
    "E within 5%, vcp<0.4, RS>10": lambda d: (d.Close <= d.hh55) & (d.Close >= d.hh55 * 0.95) & (d.vcp < 0.4) & (d.rs63 > 10),
}
rows = []
for sym, raw in px.items():
    try:
        d = ind.add_all(raw, bench.Close)
    except Exception:
        continue
    base = stg._liquid(d) & stg.trend_template(d) & d.rsi.between(50, 70)
    union = None
    for fn in stg.SWING.values():
        x = fn(d)
        union = x if union is None else union | x
    sigs = {"normal setups (after breakout)": union.fillna(False)}
    for k, f in VAR.items():
        sigs[k] = (base & f(d)).fillna(False)
    cl, hh = d.Close.values, d.hh55.values
    for k, s in sigs.items():
        last = -10
        for i in np.flatnonzero(s.values):
            if i - last < 10 or i + 61 >= len(d) or i < 250:
                continue
            last = i
            brk = next((j - i for j in range(i + 1, i + 11) if cl[j] > hh[i]), None)
            rows.append({"k": k, "year": d.index[i].year, "r515": bt.fixed_outcome(d, i),
                         "r425": bt.fixed_outcome(d, i, 4, 25), "r58": bt.fixed_outcome(d, i, 5, 8),
                         "broke10": brk is not None})
R = pd.DataFrame(rows)
for k, g in R.groupby("k", sort=False):
    yw = g.groupby("year").r515.apply(lambda x: (x > 0).mean() * 100)
    print(f"{k:40s} n={len(g):5d} | +5/-15 win {(g.r515 > 0).mean()*100:4.1f}% avg {g.r515.mean():+.2f} (worst yr {yw.min():.0f}%) | "
          f"+4/-25 win {(g.r425 > 0).mean()*100:4.1f}% avg {g.r425.mean():+.2f} | +5/-8 win {(g.r58 > 0).mean()*100:4.1f}% avg {g.r58.mean():+.2f} | "
          f"broke out in 10d {g.broke10.mean()*100:4.1f}%")
