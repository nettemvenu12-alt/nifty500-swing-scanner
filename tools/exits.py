"""Compare exit rules on Breakout/52W signals (dev tool)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scanner import data, indicators as ind, strategies as stg

n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
u = data.load_universe().head(n)
bench = data.download([data.BENCH])[data.BENCH]
B = ind.add_all(bench); reg = (B.Close > B.ema50) & (B.ema50 > B.ema200)
px = data.download(u.Symbol.tolist())
rules = {"T5 full / SL8": (5, 8), "T5 full / SL10": (5, 10), "T7 full / SL8": (7, 8),
         "T10 full / SL10": (10, 10), "T5 / no SL": (5, 99), "T10 / no SL": (10, 99), "hold60 only": (999, 99)}
out = {k: [] for k in rules}
for s, raw in px.items():
    d = ind.add_all(raw, bench.Close)
    sig = (stg.swing_breakout(d) | stg.high52_breakout(d)) & reg.reindex(d.index).fillna(False)
    hi, lo, cl = d.High.values, d.Low.values, d.Close.values
    last = -10
    for i in np.flatnonzero(sig.values):
        if i - last < 10 or i + 60 >= len(d): continue
        last = i; e = cl[i]
        for k, (t, sl) in rules.items():
            r = (cl[i+60]/e-1)*100
            for j in range(i+1, i+61):
                if lo[j] <= e*(1-sl/100): r = -sl; break
                if hi[j] >= e*(1+t/100): r = t; break
            out[k].append(r)
for k, v in out.items():
    v = np.array(v); print(f"{k:16s} n={len(v)} win={np.mean(v>0)*100:.1f}% avg={v.mean():.2f}% median={np.median(v):.2f}")
