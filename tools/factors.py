"""Which factors at signal time predict better 60-day outcomes? (dev tool)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scanner import data, indicators as ind, strategies as stg

u = data.load_universe()
bench = data.download([data.BENCH])[data.BENCH]
B = ind.add_all(bench); reg = (B.Close > B.ema50) & (B.ema50 > B.ema200)
px = data.download(u.Symbol.tolist())
rows = []
for s, raw in px.items():
    d = ind.add_all(raw, bench.Close)
    sig = (stg.swing_breakout(d) | stg.high52_breakout(d) | stg.squeeze_breakout(d) | stg.pullback_buy(d))
    hi, lo, cl = d.High.values, d.Low.values, d.Close.values
    last = -10
    for i in np.flatnonzero(sig.values):
        if i - last < 10 or i + 60 >= len(d) or i < 2: continue
        last = i; e = cl[i]; r = (cl[i+60]/e-1)*100
        for j in range(i+1, i+61):
            if lo[j] <= e*0.92: r = -8; break
            if hi[j] >= e*1.05: r = 5; break
        x = d.iloc[i].copy(); x["ema200_up"] = d.ema200.iloc[i] > d.ema200.iloc[i-21]; x["macd_hist_prev"] = d.macd_hist.iloc[i-1]
        rows.append({"r": r, "tech": stg.tech_score(x), "rs63": x.rs63, "reg": bool(reg.get(d.index[i], False)),
                     "rsi": x.rsi, "atr_pct": x.atr_pct, "from_high": x.from_high, "vol": x.vol_ratio,
                     "ret21": x.ret21, "vcp": x.vcp, "adx": x.adx})
t = pd.DataFrame(rows).dropna()
t["win"] = t.r > 0
print("all", len(t), t.win.mean().round(3), t.r.mean().round(2))
for c in ["tech", "rs63", "rsi", "atr_pct", "from_high", "vol", "ret21", "vcp", "adx"]:
    g = t.groupby(pd.qcut(t[c], 4, duplicates="drop"), observed=True).agg(n=("r","size"), win=("win","mean"), avg=("r","mean"))
    print("\n", c); print(g.round(3))
print(t.groupby("reg").agg(n=("r","size"), win=("win","mean"), avg=("r","mean")).round(3))
