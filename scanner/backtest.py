"""Walk-forward check of every setup on ~3 years of history.

For each historical signal: buy at that day's close, stop = same rule as live plan,
look forward up to HOLD days and record whether +5% / +10% was hit BEFORE the stop.
This gives an honest, data-based win rate instead of a promised one."""
import numpy as np
import pandas as pd

HOLD = 60
GAP = 10  # ignore repeat signals within 10 bars (avoid double counting)


def _stops(d):
    e = d["Close"]
    stop = np.maximum(d["ll10"], e - 2.5 * d["atr"])
    stop = np.minimum(stop, e * 0.97)
    return np.maximum(stop, e * 0.90)


def swing_trades(d, signal):
    idx = np.flatnonzero(signal.fillna(False).values)
    hi, lo, cl = d["High"].values, d["Low"].values, d["Close"].values
    e20 = d["ema20"].values
    stops = _stops(d).values
    res, last = [], -GAP
    for i in idx:
        if i - last < GAP or i + 1 >= len(d):
            continue
        last = i
        e, st = cl[i], stops[i]
        end = min(i + HOLD, len(d) - 1)
        if end - i < 5:
            continue
        # Trade management (same as live plan, chosen by tools/upgrade_research.py):
        # stop first; at +5% book half and move stop to cost; the rest rides the
        # trend and exits on a close below the 20 EMA (or at day 60).
        hit5 = hit10 = stopped = False
        rest = (cl[end] / e - 1) * 100
        for j in range(i + 1, end + 1):
            if lo[j] <= st:  # conservative: stop checked first on same bar
                stopped = not hit5
                rest = (st / e - 1) * 100
                break
            if not hit5 and hi[j] >= e * 1.05:
                hit5, st = True, e
            if hi[j] >= e * 1.10:
                hit10 = True
            if hit5 and cl[j] < e20[j]:
                rest = (max(cl[j], st) / e - 1) * 100
                break
        exit_ret = 0.5 * 5 + 0.5 * rest if hit5 else rest
        res.append({"date": d.index[i], "win5": hit5, "win10": hit10,
                    "stopped": stopped, "ret": exit_ret,
                    "complete": i + HOLD < len(d)})
    return res


def fixed_outcome(d, i, target=5, stop=15, hold=HOLD):
    """+target% before -stop% within hold bars (85% mode rule). Returns return %."""
    hi, lo, cl = d["High"].values, d["Low"].values, d["Close"].values
    e, end = cl[i], min(i + hold, len(d) - 1)
    for j in range(i + 1, end + 1):
        if lo[j] <= e * (1 - stop / 100):
            return -float(stop)
        if hi[j] >= e * (1 + target / 100):
            return float(target)
    return (cl[end] / e - 1) * 100


def btst_trades(d, signal):
    idx = np.flatnonzero(signal.fillna(False).values)
    o, h, c = d["Open"].values, d["High"].values, d["Close"].values
    res = []
    for i in idx:
        if i + 1 >= len(d):
            continue
        res.append({"date": d.index[i],
                    "gap": (o[i + 1] / c[i] - 1) * 100,
                    "best": (h[i + 1] / c[i] - 1) * 100,
                    "close": (c[i + 1] / c[i] - 1) * 100})
    return res


def summarize_swing(trades):
    if not trades:
        return {"n": 0, "win5": np.nan, "win10": np.nan, "avg": np.nan}
    t = pd.DataFrame(trades)
    return {"n": len(t), "win5": round(t.win5.mean() * 100, 1),
            "win10": round(t.win10.mean() * 100, 1), "avg": round(t.ret.mean(), 2),
            "profit": round((t.ret > 0).mean() * 100, 1),
            "stop_rate": round(t.stopped.mean() * 100, 1)}


def summarize_btst(trades):
    if not trades:
        return {"n": 0}
    t = pd.DataFrame(trades)
    return {"n": len(t), "gap_up": round((t.gap > 0).mean() * 100, 1),
            "hit1": round((t.best >= 1).mean() * 100, 1),
            "avg_open": round(t.gap.mean(), 2), "avg_best": round(t.best.mean(), 2)}
