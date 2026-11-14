"""Can any honest rule reach ~90% wins? 10-year walk-forward grid (dev tool).

For every past signal: outcome of several target/stop pairs, the walk-forward AI rank
(trained only on earlier years), and market state on that day. Prints win %, average
return and the worst year for each filter x target/stop combination.

python tools/mode90_research.py   (caches signals in /tmp/mode90_signals.pkl)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd

from scanner import data, indicators as ind, model, strategies as stg

HOLD = 60
COMBOS = [(5, 15), (4, 15), (3, 15), (5, 20), (4, 20), (3, 20), (5, 25), (4, 25)]
CACHE = "/tmp/mode90_signals.pkl"


def outcome(hi, lo, cl, i, t, s):
    e, end = cl[i], min(i + HOLD, len(cl) - 1)
    for j in range(i + 1, end + 1):
        if lo[j] <= e * (1 - s / 100):
            return -float(s)
        if hi[j] >= e * (1 + t / 100):
            return float(t)
    return (cl[end] / e - 1) * 100


def build():
    u = data.load_universe()
    bench = data.download([data.BENCH], period="10y")[data.BENCH]
    B = ind.add_all(bench)
    bull = ((B.Close > B.ema50) & (B.ema50 > B.ema200)).astype(int)
    b_above200 = (B.Close > B.ema200).astype(int)
    px = data.download(u.Symbol.tolist(), period="10y")
    print(len(px), "stocks")
    rows = []
    for sym, raw in px.items():
        try:
            d = ind.add_all(raw, bench.Close)
        except Exception:
            continue
        sig = {k: fn(d).fillna(False).values for k, fn in stg.SWING.items()}
        union = np.zeros(len(d), bool)
        for v in sig.values():
            union |= v
        F = ind.features(d, B)
        hi, lo, cl = d.High.values, d.Low.values, d.Close.values
        last = -10
        for i in np.flatnonzero(union):
            if i - last < 10 or i + 2 >= len(d) or i < 250:
                continue
            last = i
            rec = F.iloc[i].to_dict()
            dt_ = d.index[i]
            rec.update(sym=sym, date=dt_, complete=i + HOLD < len(d),
                       exit_date=d.index[min(i + HOLD, len(d) - 1)],
                       bull=int(bull.asof(dt_)), above200=int(b_above200.asof(dt_)),
                       rsi_=float(d.rsi.iloc[i]), ret5_=float(d.ret5.iloc[i]),
                       from_high_=float(d.from_high.iloc[i]), atr_pct_=float(d.atr_pct.iloc[i]),
                       setups=",".join(k for k, v in sig.items() if v[i]))
            for t, s in COMBOS:
                rec[f"r{t}/{s}"] = outcome(hi, lo, cl, i, t, s)
            rec["win5"] = int(rec["r5/15"] == 5 or outcome(hi, lo, cl, i, 5, 8) == 5)
            rows.append(rec)
    S = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    S["year"] = S.date.dt.year
    extra = ["sym", "date", "exit_date", "complete", "setups", "year", "win5", "bull", "above200",
             "rsi_", "ret5_", "from_high_", "atr_pct_"] + [f"r{t}/{s}" for t, s in COMBOS]
    feats = [c for c in S.columns if c not in extra]
    S["prob"] = np.nan
    for y in sorted(S.year.unique()):
        start = pd.Timestamp(f"{y}-01-01")
        tr = S[(S.exit_date < start - pd.Timedelta(days=90)) & S.complete]
        if len(tr) < 1500:
            continue
        m = model._clf().fit(tr[feats], tr.win5)
        idx = S.year == y
        S.loc[idx, "prob"] = m.predict_proba(S.loc[idx, feats])[:, 1]
    S["p_rank"] = S.groupby("year").prob.rank(pct=True)
    S.to_pickle(CACHE)
    return S


def main():
    S = pd.read_pickle(CACHE) if os.path.exists(CACHE) else build()
    S = S[S.complete & S.prob.notna()]
    print(f"{len(S)} finished signals with walk-forward AI score, {S.year.min()}-{S.year.max()}")
    base = (S.p_rank >= 0.9) & (S.wk_up > 0) & (S.rs63 > 15)
    filters = {
        "all signals": S.index == S.index,
        "85% mode today (AI top10 + weekly + RS>15)": base,
        "+ bull market (N500 > 50 > 200 EMA)": base & (S.bull == 1),
        "+ N500 above 200 EMA": base & (S.above200 == 1),
        "AI top 5% + weekly + RS>15": (S.p_rank >= 0.95) & (S.wk_up > 0) & (S.rs63 > 15),
        "AI top 5% + weekly + RS>15 + bull": (S.p_rank >= 0.95) & (S.wk_up > 0) & (S.rs63 > 15) & (S.bull == 1),
        "base + RS>25": base & (S.rs63 > 25),
        "base + RSI<75": base & (S.rsi_ < 75),
        "base + not extended (5d < 10%)": base & (S.ret5_ < 10),
        "base + low volatility (ATR<3.5%)": base & (S.atr_pct_ < 3.5),
        "base + bull + ATR<3.5%": base & (S.bull == 1) & (S.atr_pct_ < 3.5),
        "base + within 10% of 52W high": base & (S.from_high_ > -10),
        "Results Gap setup + weekly": S.setups.str.contains("Results Gap") & (S.wk_up > 0),
    }
    for name, f in filters.items():
        g = S[f]
        if len(g) < 30:
            print(f"\n== {name}: only {len(g)} trades, skipped")
            continue
        print(f"\n== {name}  (n={len(g)}, {len(g) / S.year.nunique():.0f}/year)")
        for t, s in COMBOS:
            c = f"r{t}/{s}"
            yw = g.groupby("year")[c].apply(lambda x: (x > 0).mean() * 100)
            ya = g.groupby("year")[c].mean()
            print(f"  +{t}%/-{s}%: win {(g[c] > 0).mean() * 100:5.1f}% | avg {g[c].mean():+5.2f}% | "
                  f"worst year win {yw.min():3.0f}% ({yw.idxmin()}) avg {ya.min():+5.2f}% | full stop hit {(g[c] <= -s).mean() * 100:4.1f}%")


if __name__ == "__main__":
    main()
