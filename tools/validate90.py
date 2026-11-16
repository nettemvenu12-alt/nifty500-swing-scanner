"""Robustness check of 90% MODE (dev tool), the "don't trust the first backtest" list:
real Indian delivery costs, parameter sensitivity, regime split, year by year (walk-forward
AI already), and a Monte Carlo of losing streaks / drawdown for the real position size.

Needs /tmp/mode90_signals.pkl from tools/mode90_research.py.
python tools/validate90.py   -> prints + writes reports/validation_90.md
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd

from scanner import data, indicators as ind

HOLD = 60
COST = 0.35   # % per trade: STT 0.1%+0.1%, stamp, exchange, GST, DP + ~0.1% slippage
RISK_OF_CAPITAL = 1.5  # a full stop loses ~1.5% of capital with the report's Qty

S = pd.read_pickle("/tmp/mode90_signals.pkl")
S = S[S.complete & S.prob.notna() & (S.p_rank >= 0.9) & (S.wk_up > 0) & (S.rs63 > 15) & (S.rsi_ < 75)]
px = data.download(sorted(S.sym.unique()), period="10y")


def run(d, i, tgt, sl):
    """Half at +tgt%, SL to cost, rest trails a close below 20 EMA; SL -sl%; max 60 days."""
    hi, lo, cl, e20 = d.High.values, d.Low.values, d.Close.values, d.ema20.values
    e, end = cl[i], min(i + HOLD, len(d) - 1)
    stop, half = e * (1 - sl / 100), None
    for j in range(i + 1, end + 1):
        if lo[j] <= stop:
            r = (stop / e - 1) * 100
            return r if half is None else (half + r) / 2
        if half is None and hi[j] >= e * (1 + tgt / 100):
            half, stop = float(tgt), e
            continue
        if half is not None and cl[j] < e20[j]:
            return (half + (max(cl[j], stop) / e - 1) * 100) / 2
    r = (cl[end] / e - 1) * 100
    return r if half is None else (half + r) / 2


GRID = [(t, s) for t in (3, 4, 5) for s in (20, 25, 30)]
rows = []
for _, s in S.iterrows():
    raw = px.get(s.sym)
    if raw is None:
        continue
    d = ind.add_all(raw)
    if s.date not in d.index:
        continue
    i = d.index.get_loc(s.date)
    rows.append({"date": s.date, "year": s.year, "bull": s.bull,
                 **{f"{t}/{sl}": run(d, i, t, sl) - COST for t, sl in GRID}})
R = pd.DataFrame(rows).sort_values("date")
main = "4/25"
out = []
p = out.append
p("# 90% MODE – robustness check\n")
p(f"{len(R)} trades {R.date.min().date()} → {R.date.max().date()}, AI walk-forward (trained only on past years). "
  f"All numbers AFTER {COST}% costs per trade (STT, stamp, exchange, GST, DP, slippage).\n")
p("Uses today's Nifty 500 list (survivorship bias) – real results somewhat lower.\n")

p("\n## 1. Result after costs (rule used: half at +4%, rest trails 20 EMA, SL -25%)\n")
r = R[main]
pf = r[r > 0].sum() / -r[r < 0].sum()
p(f"- Win rate: **{(r > 0).mean()*100:.1f}%**")
p(f"- Average per trade: **{r.mean():+.2f}%** · profit factor {pf:.2f}")
p(f"- Full -25% stop hit: {(r <= -25).mean()*100:.1f}% of trades")

p("\n## 2. Year by year\n")
for y, g in R.groupby("year"):
    p(f"- {y}: {len(g)} trades · win {(g[main] > 0).mean()*100:.0f}% · avg {g[main].mean():+.2f}%")

p("\n## 3. Parameter sensitivity (target / stop) – a robust rule has no single lucky spike\n")
for c in [f"{t}/{s}" for t, s in GRID]:
    p(f"- +{c.split('/')[0]}% / -{c.split('/')[1]}%: win {(R[c] > 0).mean()*100:.1f}% · avg {R[c].mean():+.2f}%")

p("\n## 4. Regime (Nifty 500 trend on the buy day)\n")
for name, g in (("Bull (Nifty 500 > 50 > 200 EMA)", R[R.bull == 1]), ("Not bull", R[R.bull != 1])):
    p(f"- {name}: {len(g)} trades · win {(g[main] > 0).mean()*100:.0f}% · avg {g[main].mean():+.2f}%")

p("\n## 5. Monte Carlo (10,000 reshuffles of the real trades, 100 trades each)\n")
p(f"Position size as in the report: a full -25% stop costs ~{RISK_OF_CAPITAL}% of capital, "
  f"so each trade's capital effect = return × {RISK_OF_CAPITAL / 25:.2f}.\n")
rng = np.random.default_rng(7)
x = r.values * RISK_OF_CAPITAL / 25
dd, streak, total = [], [], []
for _ in range(10000):
    s_ = rng.choice(x, 100, replace=True)
    eq = np.cumprod(1 + s_ / 100)
    dd.append(((eq / np.maximum.accumulate(eq)) - 1).min() * 100)
    total.append((eq[-1] - 1) * 100)
    m = c_ = 0
    for v in s_:
        c_ = c_ + 1 if v <= 0 else 0
        m = max(m, c_)
    streak.append(m)
dd, total, streak = np.array(dd), np.array(total), np.array(streak)
p(f"- Capital change after 100 trades: median {np.median(total):+.1f}%, bad case (5%) {np.percentile(total, 5):+.1f}%")
p(f"- Worst fall from a peak: median {np.median(dd):.1f}%, bad case (5%) {np.percentile(dd, 5):.1f}%")
p(f"- Longest losing streak: median {np.median(streak):.0f}, bad case (5%) {np.percentile(streak, 95):.0f} in a row")
p(f"- Chance of ending 100 trades with a loss: {(total < 0).mean()*100:.1f}%")
txt = "\n".join(out)
print(txt)
open(os.path.join(ROOT, "reports", "validation_90.md"), "w").write(txt + "\n")
