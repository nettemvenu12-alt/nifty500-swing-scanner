"""Compare entry / exit / filter variants on 3y Nifty 500 history (dev tool).

python tools/upgrade_research.py [limit]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from scanner import data, indicators as ind, model, strategies as stg, backtest as bt

HOLD = 60


def entries(d, i):
    """Yields (variant, entry_bar, entry_price, stop) for signal at bar i."""
    cl, lo, hi, atr = d.Close.values, d.Low.values, d.High.values, d.atr.values
    stop0 = bt._stops(d).values[i]
    yield "E0 close", i, cl[i], stop0
    # E1: wait up to 5 bars for a dip to (close - 0.5 ATR) or breakout level, tighter stop
    lvl = max(cl[i] - 0.5 * atr[i], np.nan_to_num(d.hh20.values[i], nan=0))
    lvl = min(lvl, cl[i])
    for j in range(i + 1, min(i + 6, len(d))):
        if lo[j] <= lvl:
            px = min(lvl, d.Open.values[j])
            yield "E1 dip", j, px, max(px - 1.75 * atr[i], px * 0.92)
            break
    # E2: next-day confirmation: buy only if next bar trades above signal high
    if i + 1 < len(d) and hi[i + 1] > hi[i]:
        px = max(hi[i], d.Open.values[i + 1])
        yield "E2 confirm", i + 1, px, max(min(lo[i], px * 0.97), px * 0.90)


def exits(d, j, e, stop):
    """Returns {variant: return%} for a position opened at bar j."""
    hi, lo, cl = d.High.values, d.Low.values, d.Close.values
    atr, e20 = d.atr.values, d.ema20.values
    end = min(j + HOLD, len(d) - 1)
    out = {}
    # X0: current (half at +5, stop->cost, rest +10 / day60)
    st, t1, rest = stop, False, None
    for k in range(j + 1, end + 1):
        if lo[k] <= st:
            rest = (st / e - 1) * 100; break
        if not t1 and hi[k] >= e * 1.05:
            t1, st = True, e
        if hi[k] >= e * 1.10:
            rest = 10.0; break
    rest = (cl[end] / e - 1) * 100 if rest is None else rest
    out["X0 half@5,10"] = 2.5 + 0.5 * rest if t1 else rest
    # X1: chandelier trail 3 ATR, stop -> cost after +5%, day-60 exit
    st, hh, r = stop, e, None
    for k in range(j + 1, end + 1):
        if lo[k] <= st:
            r = (st / e - 1) * 100; break
        hh = max(hh, hi[k])
        if hh >= e * 1.05:
            st = max(st, e)
        st = max(st, hh - 3 * atr[k])
    out["X1 ATR trail"] = (cl[end] / e - 1) * 100 if r is None else r
    # X2: half at +5%, rest trails EMA20 close
    st, t1, r = stop, False, None
    for k in range(j + 1, end + 1):
        if lo[k] <= st:
            r = (st / e - 1) * 100; break
        if not t1 and hi[k] >= e * 1.05:
            t1, st = True, e
        if t1 and cl[k] < e20[k]:
            r = (max(cl[k], st) / e - 1) * 100; break
    r = (cl[end] / e - 1) * 100 if r is None else r
    out["X2 half@5+EMA20"] = 2.5 + 0.5 * r if t1 else r
    # X3: full exit +5%
    r = None
    for k in range(j + 1, end + 1):
        if lo[k] <= stop:
            r = (stop / e - 1) * 100; break
        if hi[k] >= e * 1.05:
            r = 5.0; break
    out["X3 full@5"] = (cl[end] / e - 1) * 100 if r is None else r
    # X4: half at +5, rest ATR trail
    st, t1, hh, r = stop, False, e, None
    for k in range(j + 1, end + 1):
        if lo[k] <= st:
            r = (st / e - 1) * 100; break
        hh = max(hh, hi[k])
        if not t1 and hi[k] >= e * 1.05:
            t1, st = True, e
        if t1:
            st = max(st, hh - 2.5 * atr[k])
    r = (cl[end] / e - 1) * 100 if r is None else r
    out["X4 half@5+ATRtrail"] = 2.5 + 0.5 * r if t1 else r
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    u = data.load_universe()
    if n:
        u = u.head(n)
    bench = data.download([data.BENCH])[data.BENCH]
    B = ind.add_all(bench)
    px = data.download(u.Symbol.tolist())
    rows, samples = [], []
    for s, raw in px.items():
        d = ind.add_all(raw, bench.Close)
        union = None
        for fn in stg.SWING.values():
            x = fn(d)
            union = x if union is None else union | x
        aplus = stg.a_plus(d)
        F = ind.features(d, B)
        last = -10
        for i in np.flatnonzero(union.fillna(False).values):
            if i - last < 10 or i + HOLD + 6 >= len(d) or i < 30:
                continue
            last = i
            r = d.iloc[i]
            base = {"sym": s, "date": d.index[i], "aplus": bool(aplus.iloc[i]),
                    "wk_up": bool(r.wk_up), "rs63": r.rs63, "from_high": r.from_high,
                    "vol": r.vol_ratio, "rsi": r.rsi}
            for ev, j, e, stop in entries(d, i):
                for xv, ret in exits(d, j, e, stop).items():
                    rows.append({**base, "entry": ev, "exit": xv, "ret": ret,
                                 "risk": (1 - stop / e) * 100})
            # ML sample: label = +5% hit before the standard stop (same as live model)
            e0 = d.Close.values[i]
            x3 = exits(d, i, e0, bt._stops(d).values[i])["X3 full@5"]
            sm = F.iloc[[i]].copy()
            sm["date"], sm["win5"], sm["ret"], sm["sym"] = d.index[i], int(x3 == 5.0), x3, s
            samples.append(sm)
    R = pd.DataFrame(rows)
    S = pd.concat(samples)
    # Walk-forward ML probability for the test window only
    S = S.sort_values("date")
    cut = S.date.quantile(0.75)
    tr = S[S.date < cut - pd.Timedelta(days=model.EMBARGO_DAYS)]
    te = S[S.date >= cut]
    feats = [c for c in S.columns if c not in ("date", "win5", "ret", "sym")]
    m = model._clf().fit(tr[feats], tr.win5)
    te = te.assign(prob=m.predict_proba(te[feats])[:, 1])
    R = R.merge(te[["sym", "date", "prob"]], on=["sym", "date"], how="left")

    def summ(g):
        return pd.Series({"n": len(g), "win%": (g.ret > 0).mean() * 100, "avg%": g.ret.mean(),
                          "PF": g.ret[g.ret > 0].sum() / max(-g.ret[g.ret < 0].sum(), 1e-9),
                          "risk%": g.risk.mean()})

    pd.set_option("display.width", 200)
    print("\n=== ALL SIGNALS (full 3y) by entry x exit ===")
    print(R.groupby(["entry", "exit"]).apply(summ, include_groups=False).round(2))
    hc = R[R.aplus & R.wk_up & (R.vol >= 1.2)]
    print("\n=== RULE FILTER: A+ & weekly up & vol>=1.2 ===")
    print(hc.groupby(["entry", "exit"]).apply(summ, include_groups=False).round(2))
    T = R.dropna(subset=["prob"])
    print(f"\n=== OUT-OF-SAMPLE WINDOW (from {pd.Timestamp(cut).date()}) ===")
    print("all:"); print(T.groupby(["entry", "exit"]).apply(summ, include_groups=False).round(2))
    q = T.prob.quantile(0.7)
    print(f"ML top 30% (prob>={q:.2f}):")
    print(T[T.prob >= q].groupby(["entry", "exit"]).apply(summ, include_groups=False).round(2))
    print("ML top 30% + weekly up:")
    print(T[(T.prob >= q) & T.wk_up].groupby(["entry", "exit"]).apply(summ, include_groups=False).round(2))


if __name__ == "__main__":
    main()
