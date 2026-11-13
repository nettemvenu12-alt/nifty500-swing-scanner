"""ML layer: gradient-boosted model that estimates P(hit +5% before stop within 60 days)
for a stock showing one of the swing setups.

Validated walk-forward: trained on older signals, tested on the most recent ~25% of
dates (with a 60-day gap so no future data leaks into training). Only the honest
out-of-sample numbers are reported."""
import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
except Exception:  # sklearn missing -> model disabled, scanner still works
    HistGradientBoostingClassifier = None

EMBARGO_DAYS = 90  # calendar days ≈ 60 trading days


def _clf():
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=250,
                                          l2_regularization=1.0, min_samples_leaf=60,
                                          random_state=7)


def train(samples):
    """samples: DataFrame with feature columns + 'date', 'win5', 'ret'.
    Returns (fitted model or None, report dict)."""
    if HistGradientBoostingClassifier is None or len(samples) < 800:
        return None, {"enabled": False, "reason": "not enough data or sklearn missing"}
    s = samples.sort_values("date").reset_index(drop=True)
    feats = [c for c in s.columns if c not in ("date", "win5", "ret", "symbol")]
    cut = s.date.quantile(0.75)
    tr = s[s.date < cut - pd.Timedelta(days=EMBARGO_DAYS)]
    te = s[s.date >= cut]
    rep = {"enabled": True, "train_n": len(tr), "test_n": len(te),
           "test_from": str(pd.Timestamp(cut).date()), "base_rate": round(float(te.win5.mean()) * 100, 1)}
    if len(tr) > 400 and len(te) > 150 and te.win5.nunique() == 2:
        m = _clf().fit(tr[feats], tr.win5)
        p = m.predict_proba(te[feats])[:, 1]
        rep["auc"] = round(float(roc_auc_score(te.win5, p)), 3)
        q = np.quantile(p, 0.8)
        top = te[p >= q]
        rep["top20_win"] = round(float(top.win5.mean()) * 100, 1)
        rep["top20_avg_ret"] = round(float(top.ret.mean()), 2)
        rep["all_avg_ret"] = round(float(te.ret.mean()), 2)
        # calibration: map raw prob -> observed out-of-sample win rate by quintile
        bins = np.quantile(p, [0, .2, .4, .6, .8, 1])
        rep["quintiles"] = [round(float(te.win5[(p >= bins[i]) & (p <= bins[i + 1])].mean()) * 100, 1)
                            for i in range(5)]
        rep["useful"] = bool(rep["auc"] >= 0.55 and rep["top20_win"] > rep["base_rate"])
    else:
        rep["useful"] = False
    final = _clf().fit(s[feats], s.win5)
    final.feats_ = feats
    return final, rep


def predict(model, feat_rows):
    if model is None or not len(feat_rows):
        return np.full(len(feat_rows), np.nan)
    return model.predict_proba(feat_rows[model.feats_])[:, 1]


def points(prob, rep):
    """0-10 score points; neutral (5) if the model didn't prove itself out-of-sample."""
    if prob is None or np.isnan(prob) or not rep.get("useful"):
        return 5.0
    base = rep["base_rate"] / 100
    return float(np.clip(5 + (prob - base) / 0.15 * 5, 0, 10))
