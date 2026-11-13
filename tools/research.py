"""Compare filter/stop variants on history (dev tool)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scanner import data, indicators as ind, strategies as stg, backtest as bt

n = int(sys.argv[1]) if len(sys.argv) > 1 else 150
u = data.load_universe().head(n)
bench = data.download([data.BENCH])[data.BENCH]
B = ind.add_all(bench)
reg = (B.Close > B.ema50) & (B.ema50 > B.ema200)
px = data.download(u.Symbol.tolist())
res = {}
for s, raw in px.items():
    d = ind.add_all(raw, bench.Close)
    r = reg.reindex(d.index).fillna(False)
    rs = d.rs63 > 0
    for name, fn in stg.SWING.items():
        sig = fn(d)
        for tag, m in [("raw", sig), ("regime", sig & r), ("regime+rs", sig & r & rs)]:
            res.setdefault((name, tag), []).extend(bt.swing_trades(d, m))
for k, v in res.items():
    print(k, bt.summarize_swing(v))
