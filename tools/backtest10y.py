"""10-year backtest of the scanner's rules (dev tool).

- Every setup, year by year, with the live exit rule (half at +5%, SL to cost, rest
  on a close below 20 EMA, max 60 days).
- AI walk-forward: for each year Y the model is trained ONLY on signals that finished
  before Y (90-day gap), then scores Y's signals. No future data is used.
- 85% mode (AI top 10% + weekly up + RS > 15, +5% target / -15% stop) per year.
- Portfolio simulation: ₹1,00,000, max 5 positions x 20%, best AI signals first, vs Nifty 500.

Caveat: uses TODAY's Nifty 500 list (survivorship bias: stocks that crashed out of the
index are missing), so real results would have been somewhat worse.

python tools/backtest10y.py   -> prints + writes reports/backtest_10y.md
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd

from scanner import backtest as bt, data, indicators as ind, model, strategies as stg

HOLD = 60


def trade(d, i):
    """Live exit rule from bar i. Returns (exit_index, return %)."""
    hi, lo, cl, e20 = d.High.values, d.Low.values, d.Close.values, d.ema20.values
    e, st = cl[i], bt._stops(d).values[i]
    end = min(i + HOLD, len(d) - 1)
    t1 = False
    for j in range(i + 1, end + 1):
        if lo[j] <= st:
            rest = (st / e - 1) * 100
            return j, (2.5 + 0.5 * rest) if t1 else rest
        if not t1 and hi[j] >= e * 1.05:
            t1, st = True, e
        if t1 and cl[j] < e20[j]:
            return j, 2.5 + 0.5 * (max(cl[j], st) / e - 1) * 100
    rest = (cl[end] / e - 1) * 100
    return end, (2.5 + 0.5 * rest) if t1 else rest


def fixed(d, i, t=5, s=15):
    hi, lo, cl = d.High.values, d.Low.values, d.Close.values
    e, end = cl[i], min(i + HOLD, len(d) - 1)
    for j in range(i + 1, end + 1):
        if lo[j] <= e * (1 - s / 100):
            return j, -float(s)
        if hi[j] >= e * (1 + t / 100):
            return j, float(t)
    return end, (cl[end] / e - 1) * 100


def main():
    u = data.load_universe()
    bench = data.download([data.BENCH], period="10y")[data.BENCH]
    B = ind.add_all(bench)
    px = data.download(u.Symbol.tolist(), period="10y")
    print(f"{len(px)} stocks, {bench.index[0].date()} .. {bench.index[-1].date()}")
    rows = []
    for sym, raw in px.items():
        d = ind.add_all(raw, bench.Close)
        sig = {k: fn(d).fillna(False).values for k, fn in stg.SWING.items()}
        union = np.zeros(len(d), bool)
        for v in sig.values():
            union |= v
        F = ind.features(d, B)
        last = -10
        for i in np.flatnonzero(union):
            if i - last < 10 or i + 2 >= len(d) or i < 250:
                continue
            last = i
            xi, ret = trade(d, i)
            fx, f515 = fixed(d, i)
            rec = F.iloc[i].to_dict()
            rec.update(sym=sym, date=d.index[i], exit_date=d.index[xi], ret=ret,
                       r515=f515, exit85=d.index[fx],
                       win5=int(ret >= 2.5),  # T1 (+5%) was hit before the stop
                       complete=i + HOLD < len(d),
                       setups=",".join(k for k, v in sig.items() if v[i]))
            rows.append(rec)
    S = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    S["year"] = S.date.dt.year
    feats = [c for c in S.columns if c not in ("sym", "date", "exit_date", "ret", "r515", "exit85", "win5",
                                                "complete", "setups", "year")]
    # ---- walk-forward AI ----
    S["prob"] = np.nan
    years = sorted(S.year.unique())
    for y in years:
        start = pd.Timestamp(f"{y}-01-01")
        tr = S[(S.exit_date < start - pd.Timedelta(days=90)) & S.complete]
        if len(tr) < 1500:
            continue
        m = model._clf().fit(tr[feats], tr.win5)
        idx = S.year == y
        S.loc[idx, "prob"] = m.predict_proba(S.loc[idx, feats])[:, 1]
    # yearly thresholds from the training-time distribution (top 10% / 30% within year)
    S["p_rank"] = S.groupby("year").prob.rank(pct=True)
    S["mode85"] = (S.p_rank >= 0.9) & (S.wk_up > 0) & (S.rs63 > 15)

    out = []
    p = out.append
    p("# 10-year backtest – Nifty 500 swing scanner\n")
    p(f"Data {S.date.min().date()} → {S.date.max().date()} · {len(px)} stocks · {len(S)} signals.\n")
    p("Exit rule: half at +5% (SL to cost), rest on close below 20 EMA, max 60 days. "
      "AI is walk-forward (trained only on past years).\n")
    p("> Uses today's Nifty 500 list → survivorship bias; real results would be somewhat lower.\n")

    nifty_y = bench.Close.resample("YE").last().pct_change() * 100
    p("\n## All setups, year by year\n")
    p("| Year | Trades | Profitable % | Avg % / trade | AI-top-30% profitable | AI-top-30% avg | Nifty 500 year % |")
    p("|---|---|---|---|---|---|---|")
    for y in years:
        g = S[S.year == y]
        t = g[g.p_rank >= 0.7]
        ny = nifty_y.get(pd.Timestamp(f"{y}-12-31"), np.nan)
        ny = nifty_y[nifty_y.index.year == y].iloc[0] if (nifty_y.index.year == y).any() else np.nan
        p(f"| {y} | {len(g)} | {(g.ret > 0).mean()*100:.0f}% | {g.ret.mean():+.2f} | "
          + (f"{(t.ret > 0).mean()*100:.0f}% | {t.ret.mean():+.2f}" if len(t) else "– | –")
          + f" | {ny:+.1f} |")

    p("\n## Each setup (10 years)\n")
    p("| Setup | Trades | Profitable % | Avg % | Best year avg | Worst year avg |")
    p("|---|---|---|---|---|---|")
    for k in stg.SWING:
        g = S[S.setups.str.contains(k, regex=False)]
        if len(g):
            yy = g.groupby("year").ret.mean()
            p(f"| {k} | {len(g)} | {(g.ret > 0).mean()*100:.0f}% | {g.ret.mean():+.2f} | {yy.max():+.2f} ({yy.idxmax()}) | {yy.min():+.2f} ({yy.idxmin()}) |")

    p("\n## 🎯 85% mode (AI top 10% + weekly up + RS>15; +5% target / -15% stop)\n")
    p("| Year | Trades | Win % | Avg % |")
    p("|---|---|---|---|")
    m85 = S[S.mode85]
    for y in years:
        g = m85[m85.year == y]
        if len(g):
            p(f"| {y} | {len(g)} | {(g.r515 > 0).mean()*100:.0f}% | {g.r515.mean():+.2f} |")
    if len(m85):
        p(f"| **All** | {len(m85)} | **{(m85.r515 > 0).mean()*100:.0f}%** | {m85.r515.mean():+.2f} |")

    # ---- portfolio simulation ----
    def simulate(cands, retcol, exitcol, slots=5, cap=100000.0, cost=0.25):
        """Equity (at cost for open trades) recorded after every closed trade."""
        cash, open_, pts = cap, [], [(cands.date.min(), cap)]

        def close_until(t):
            nonlocal cash, open_
            open_.sort(key=lambda x: x[0])
            while open_ and open_[0][0] <= t:
                xd, amt, rr, _ = open_.pop(0)
                cash += amt * (1 + (rr - cost) / 100)
                pts.append((xd, cash + sum(a for _, a, _, _ in open_)))

        for _, r in cands.sort_values(["date", "prob"], ascending=[True, False]).iterrows():
            close_until(r.date)
            if len(open_) >= slots or any(sym == r.sym for _, _, _, sym in open_):
                continue
            amt = min((cash + sum(a for _, a, _, _ in open_)) / slots, cash)
            if amt <= 0:
                continue
            cash -= amt
            open_.append((r[exitcol], amt, r[retcol], r.sym))
        close_until(pd.Timestamp.max)
        e = pd.Series([v for _, v in pts], index=[t for t, _ in pts]).sort_index()
        return e[~e.index.duplicated(keep="last")]

    p("\n## ₹1,00,000 portfolio simulation (max 5 stocks × 20%, costs 0.25%/trade)\n")
    p("| Strategy | Start | Final value | CAGR | Max drawdown | Signals available |")
    p("|---|---|---|---|---|---|")
    first = S.dropna(subset=["prob"]).date.min()
    variants = {
        "AI top 30% signals (live exit rule)": (S[(S.p_rank >= 0.7) & (S.date >= first)], "ret", "exit_date"),
        "🎯 85% mode (+5% / -15%)": (S[S.mode85 & (S.date >= first)], "r515", "exit85"),
        "All signals (no AI)": (S[S.date >= first].assign(prob=0), "ret", "exit_date"),
    }
    for name, (c, rc, xc) in variants.items():
        if len(c) < 10:
            continue
        e = simulate(c, rc, xc)
        yrs = (e.index[-1] - first).days / 365.25
        cagr = ((e.iloc[-1] / 100000) ** (1 / yrs) - 1) * 100
        dd = ((e / e.cummax()) - 1).min() * 100
        p(f"| {name} | {first.date()} | ₹{e.iloc[-1]:,.0f} | {cagr:+.1f}% | {dd:.1f}% | {len(c)} |")
    b0 = bench.Close[bench.index >= first]
    yrs = (b0.index[-1] - b0.index[0]).days / 365.25
    bc = ((b0.iloc[-1] / b0.iloc[0]) ** (1 / yrs) - 1) * 100
    bdd = ((b0 / b0.cummax()) - 1).min() * 100
    p(f"| Nifty 500 index (buy & hold) | {first.date()} | ₹{100000 * b0.iloc[-1] / b0.iloc[0]:,.0f} | {bc:+.1f}% | {bdd:.1f}% | – |")
    p("\nNote: portfolio caps 5 open trades, so many signals are skipped; when slots are full, "
      "new signals wait. Drawdown is measured on closed trades.")
    txt = "\n".join(out)
    print(txt)
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    open(os.path.join(ROOT, "reports", "backtest_10y.md"), "w").write(txt + "\n")


if __name__ == "__main__":
    main()
