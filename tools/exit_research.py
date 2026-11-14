"""90% mode: does a different EXIT make more money than "sell all at +4%"? (dev tool)
Uses the walk-forward signals cached by tools/mode90_research.py."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd

from scanner import data, indicators as ind

S = pd.read_pickle("/tmp/mode90_signals.pkl")
S = S[S.complete & S.prob.notna() & (S.p_rank >= 0.9) & (S.wk_up > 0) & (S.rs63 > 15) & (S.rsi_ < 75)]
px = data.download(sorted(S.sym.unique()), period="10y")
HOLD, SL = 60, 0.75


def run(d, i, rule):
    hi, lo, cl, e20 = d.High.values, d.Low.values, d.Close.values, d.ema20.values
    e, end = cl[i], min(i + HOLD, len(d) - 1)
    stop, half = e * SL, None
    for j in range(i + 1, end + 1):
        if lo[j] <= stop:
            r = (stop / e - 1) * 100
            return r if half is None else (half + r) / 2
        if rule == "all at +4%" and hi[j] >= e * 1.04:
            return 4.0
        if rule == "all at +5%" and hi[j] >= e * 1.05:
            return 5.0
        if rule.startswith("half") and half is None and hi[j] >= e * 1.04:
            half, stop = 4.0, e  # rest: stop moves to cost
            continue
        if half is not None:
            if rule == "half at +4%, rest at +10%" and hi[j] >= e * 1.10:
                return (half + 10) / 2
            if rule == "half at +4%, rest trails 20 EMA" and cl[j] < e20[j]:
                return (half + (max(cl[j], stop) / e - 1) * 100) / 2
    r = (cl[end] / e - 1) * 100
    return r if half is None else (half + r) / 2


RULES = ["all at +4%", "all at +5%", "half at +4%, rest at +10%", "half at +4%, rest trails 20 EMA"]
rows = []
for _, s in S.iterrows():
    raw = px.get(s.sym)
    if raw is None:
        continue
    d = ind.add_all(raw)
    if s.date not in d.index:
        continue
    i = d.index.get_loc(s.date)
    rows.append({"year": s.year, **{r: run(d, i, r) for r in RULES}})
R = pd.DataFrame(rows)
print(f"90% mode trades: {len(R)}")
for r in RULES:
    yr = R.groupby("year")[r].mean()
    print(f"{r:34s} win {(R[r] > 0).mean()*100:5.1f}% | avg {R[r].mean():+.2f}%/trade | "
          f"worst year avg {yr.min():+.2f}% ({yr.idxmin()}) | full -25% stop {(R[r] <= -24.9).mean()*100:.1f}%")
