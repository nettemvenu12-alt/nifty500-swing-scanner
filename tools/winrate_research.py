"""Which target / stop / filter combos reach very high win rates? (dev tool)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scanner import data, indicators as ind, model, strategies as stg

u = data.load_universe()
bench = data.download([data.BENCH])[data.BENCH]
B = ind.add_all(bench)
px = data.download(u.Symbol.tolist())
COMBOS = [(t, s) for t in (2, 3, 4, 5) for s in (5, 8, 10, 15)]
rows, samples = [], []
for sym, raw in px.items():
    d = ind.add_all(raw, bench.Close)
    union = None
    for fn in stg.SWING.values():
        x = fn(d); union = x if union is None else union | x
    F = ind.features(d, B)
    hi, lo, cl = d.High.values, d.Low.values, d.Close.values
    last = -10
    for i in np.flatnonzero(union.fillna(False).values):
        if i - last < 10 or i + 61 >= len(d) or i < 30: continue
        last = i; e = cl[i]
        rec = {"sym": sym, "date": d.index[i], "wk_up": bool(d.wk_up.iloc[i])}
        for t, s in COMBOS:
            r = (cl[i + 60] / e - 1) * 100
            for j in range(i + 1, i + 61):
                if lo[j] <= e * (1 - s / 100): r = -s; break
                if hi[j] >= e * (1 + t / 100): r = t; break
            rec[f"{t}/{s}"] = r
        rows.append(rec)
        sm = F.iloc[[i]].copy(); sm["date"] = d.index[i]; sm["sym"] = sym
        sm["win5"] = int(rec["5/8"] == 5); sm["ret"] = rec["5/8"]; samples.append(sm)
R = pd.DataFrame(rows); S = pd.concat(samples).sort_values("date")
cut = S.date.quantile(0.75)
tr = S[S.date < cut - pd.Timedelta(days=90)]; te = S[S.date >= cut]
feats = [c for c in S.columns if c not in ("date", "win5", "ret", "sym")]
m = model._clf().fit(tr[feats], tr.win5)
te = te.assign(prob=m.predict_proba(te[feats])[:, 1])
T = R.merge(te[["sym", "date", "prob"]], on=["sym", "date"])
print("Out-of-sample signals:", len(T), "from", pd.Timestamp(cut).date())
for name, g in [("all", T), ("AI top 30%", T[T.prob >= T.prob.quantile(.7)]),
                ("AI top 10%", T[T.prob >= T.prob.quantile(.9)]),
                ("AI top 10% + weekly up", T[(T.prob >= T.prob.quantile(.9)) & T.wk_up])]:
    print(f"\n== {name} (n={len(g)}) ==  target/stop: win% | avg%")
    print("  ".join(f"{c}: {(g[c] > 0).mean()*100:.0f}%|{g[c].mean():+.2f}" for c in [f"{t}/{s}" for t, s in COMBOS]))
