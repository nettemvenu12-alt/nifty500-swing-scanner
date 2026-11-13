"""Which extra filters / models raise the win rate on UNSEEN data? (dev tool)

Tests on the most recent 25% of 5y history (model trained only on older data):
  - HGB model vs. ensemble (HGB + random forest + logistic regression)
  - market breadth, index trend, sector strength and RS filters on top of 85% mode
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from scanner import backtest as bt, data, indicators as ind, model, strategies as stg

u = data.load_universe()
meta = u.set_index("Symbol").Industry.to_dict()
bench = data.download([data.BENCH])[data.BENCH]
B = ind.add_all(bench)
px = data.download(u.Symbol.tolist())
above50, rs_tab, rows = {}, {}, []
for sym, raw in px.items():
    d = ind.add_all(raw, bench.Close)
    above50[sym] = (d.Close > d.ema50).astype(float)
    rs_tab[sym] = d.rs63
    union = None
    for fn in stg.SWING.values():
        x = fn(d)
        union = x if union is None else union | x
    F = ind.features(d, B)
    last = -10
    for i in np.flatnonzero(union.fillna(False).values):
        if i - last < 10 or i + 61 >= len(d) or i < 30:
            continue
        last = i
        rec = F.iloc[i].to_dict()
        rec.update(sym=sym, date=d.index[i], ind=meta.get(sym, "?"),
                   r515=bt.fixed_outcome(d, i, 5, 15), r58=bt.fixed_outcome(d, i, 5, 8),
                   r310=bt.fixed_outcome(d, i, 3, 10))
        rows.append(rec)
S = pd.DataFrame(rows).sort_values("date")
breadth = pd.DataFrame(above50).mean(axis=1) * 100
RS = pd.DataFrame(rs_tab)
sec_rank = RS.T.groupby(pd.Series(meta)).mean().T.rank(axis=1, ascending=False)  # 1 = strongest sector
S["breadth"] = S.date.map(breadth)
S["sec_rank"] = [sec_rank.at[t, s] if s in sec_rank.columns and t in sec_rank.index else np.nan
                 for t, s in zip(S.date, S.ind)]
S["win"] = (S.r58 == 5).astype(int)

feats = [c for c in ind.features.__code__.co_varnames if False]  # placeholder
feats = [c for c in S.columns if c not in ("sym", "date", "ind", "r515", "r58", "r310", "win", "breadth", "sec_rank")]
cut = S.date.quantile(0.75)
tr = S[S.date < cut - pd.Timedelta(days=90)]
te = S[S.date >= cut].copy()
print(f"train {len(tr)}  test {len(te)}  (test from {pd.Timestamp(cut).date()})")

hgb = model._clf().fit(tr[feats], tr.win)
rf = make_pipeline(SimpleImputer(), RandomForestClassifier(n_estimators=300, min_samples_leaf=40,
                                                           max_features=0.4, n_jobs=-1, random_state=7)).fit(tr[feats], tr.win)
lr = make_pipeline(SimpleImputer(), StandardScaler(), LogisticRegression(C=0.3, max_iter=2000)).fit(tr[feats], tr.win)
te["p_hgb"] = hgb.predict_proba(te[feats])[:, 1]
te["p_rf"] = rf.predict_proba(te[feats])[:, 1]
te["p_lr"] = lr.predict_proba(te[feats])[:, 1]
te["p_ens"] = te[["p_hgb", "p_rf", "p_lr"]].rank(pct=True).mean(axis=1)
for c in ["p_hgb", "p_rf", "p_lr", "p_ens"]:
    print(f"AUC {c}: {roc_auc_score(te.win, te[c]):.3f}")


def show(name, g):
    if len(g) < 15:
        print(f"{name:45s} n={len(g):4d}  (too few)")
        return
    print(f"{name:45s} n={len(g):4d}  5/15 win {(g.r515 > 0).mean()*100:5.1f}% avg {g.r515.mean():+5.2f}%"
          f" | 5/8 win {(g.r58 > 0).mean()*100:5.1f}% avg {g.r58.mean():+5.2f}%"
          f" | 3/10 win {(g.r310 > 0).mean()*100:5.1f}% avg {g.r310.mean():+5.2f}%")


for pcol in ["p_hgb", "p_ens"]:
    print(f"\n===== model {pcol} =====")
    top10 = te[pcol] >= te[pcol].quantile(0.9)
    top20 = te[pcol] >= te[pcol].quantile(0.8)
    wk = te.wk_up > 0
    show("all signals", te)
    show("top20", te[top20])
    show("top10 + weekly (current 85% mode)", te[top10 & wk])
    show("  + breadth > 55%", te[top10 & wk & (te.breadth > 55)])
    show("  + breadth 40-70% (not overheated)", te[top10 & wk & te.breadth.between(40, 70)])
    show("  + index above 50 EMA", te[top10 & wk & (te.mkt_d_ema50 > 0)])
    show("  + sector rank <= 5", te[top10 & wk & (te.sec_rank <= 5)])
    show("  + rs63 > 15", te[top10 & wk & (te.rs63 > 15)])
    show("  + rsi < 70", te[top10 & wk & (te.rsi < 70)])
    show("top20 + weekly + sector<=5 + rsi<70", te[top20 & wk & (te.sec_rank <= 5) & (te.rsi < 70)])
