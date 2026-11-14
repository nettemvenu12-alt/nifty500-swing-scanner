"""Setup definitions. Each returns a boolean Series over the whole history, so the
same rule is used for today's scan AND for the historical backtest."""
import numpy as np

MIN_TURNOVER_CR = 10  # avg daily traded value, crores (liquidity filter)


def _liquid(d):
    return (d["turnover_cr"] >= MIN_TURNOVER_CR) & (d["Close"] >= 30)


def trend_template(d):
    """Stage-2 uptrend (Minervini-style trend template)."""
    return (
        (d["Close"] > d["ema50"]) & (d["ema50"] > d["ema150"]) & (d["ema150"] > d["ema200"])
        & (d["ema200"] > d["ema200"].shift(21))
        & (d["from_low"] >= 30) & (d["from_high"] >= -25)
    )


def swing_breakout(d):
    """Breakout above 55-day high on strong volume inside an uptrend."""
    return (
        _liquid(d) & trend_template(d)
        & (d["Close"] > d["hh55"]) & (d["vol_ratio"] >= 1.5)
        & d["rsi"].between(55, 78) & (d["adx"] >= 18) & (d["close_pos"] >= 0.6)
    )


def high52_breakout(d):
    """Fresh 52-week-high close with volume."""
    prev_high = d["hh252"].shift()
    return (
        _liquid(d) & (d["Close"] > prev_high) & (d["vol_ratio"] >= 1.3)
        & (d["ema50"] > d["ema200"]) & (d["rsi"] < 80)
    )


def squeeze_breakout(d):
    """Volatility squeeze (Bollinger width in bottom 25%) that breaks out up."""
    return (
        _liquid(d) & (d["bbw_rank"].shift() <= 0.25) & (d["Close"] > d["hh20"])
        & (d["vol_ratio"] >= 1.3) & (d["Close"] > d["ema50"]) & (d["ema50"] > d["ema200"])
    )


def pullback_buy(d):
    """Buy-the-dip: strong uptrend, price bounced off 20/50 EMA, momentum turning up."""
    touched = (d["Low"] <= d["ema20"] * 1.01) | (d["Low"] <= d["ema50"] * 1.01)
    touched3 = touched | touched.shift(1, fill_value=False) | touched.shift(2, fill_value=False)
    return (
        _liquid(d) & trend_template(d) & touched3
        & (d["Close"] > d["ema20"]) & (d["Close"] > d["Open"])
        & d["rsi"].between(42, 62) & (d["rsi"] > d["rsi"].shift())
        & (d["macd_hist"] > d["macd_hist"].shift())
    )


def btst(d):
    """Buy Today Sell Tomorrow: strong close near day high on heavy volume."""
    return (
        _liquid(d) & (d["day_chg"] >= 2) & (d["day_chg"] <= 9)
        & (d["close_pos"] >= 0.8) & (d["vol_ratio"] >= 2)
        & (d["Close"] > d["hh20"]) & (d["rsi"] < 78) & (d["st"] > 0)
        & (d["Close"] > d["ema20"])
    )


def results_gap(d):
    """Earnings-gap momentum: a big gap-up on 3x volume (usually results/news), then
    price holds above the gap-day low and breaks the gap-day high within 10 days."""
    gap = ((d["Open"] > d["High"].shift() * 1.02) & (d["Close"] > d["Open"])
           & (d["vol_ratio"] >= 3) & (d["close_pos"] >= 0.5))
    gh = d["High"].where(gap).ffill(limit=10)
    gl = d["Low"].where(gap).ffill(limit=10)
    recent = gap.astype(float).rolling(10, min_periods=1).max() > 0
    held = d["Low"].rolling(5).min() >= gl
    first = gap & (d["close_pos"] >= 0.75)
    follow = recent & ~gap & held & (d["Close"] > gh) & (d["Close"].shift() <= gh)
    return _liquid(d) & (d["ema50"] > d["ema200"]) & (first | follow)


def early_breakout(d):
    """BEFORE the breakout: stage-2 uptrend, tight 10-day base, price within 5% under the
    55-day high, stronger than the market. In tools/early_research.py (5 years) buying here
    did slightly better than buying after the breakout (+5%/-15%: 80.7% wins vs 78.3%)."""
    return (
        _liquid(d) & trend_template(d) & d["rsi"].between(50, 70)
        & (d["Close"] <= d["hh55"]) & (d["Close"] >= d["hh55"] * 0.95)
        & (d["vcp"] < 0.4) & (d["rs63"] > 10)
    )


def a_plus(d):
    """Best combo found in research: any setup + near 52W high + strong RS + stage 2."""
    any_setup = swing_breakout(d) | high52_breakout(d) | squeeze_breakout(d) | pullback_buy(d)
    return any_setup & (d["from_high"] >= -7) & (d["rs63"] >= 10) & trend_template(d)


SWING = {
    "A+ Momentum": a_plus,
    "Results Gap": results_gap,
    "Breakout": swing_breakout,
    "52W High": high52_breakout,
    "Squeeze": squeeze_breakout,
    "Pullback": pullback_buy,
}


def tech_score(row):
    """0-65 technical score for the latest bar (rest comes from RS, fundamentals,
    news and backtest edge)."""
    s = 0
    # Trend (25)
    s += 5 * (row.Close > row.ema50)
    s += 5 * (row.ema50 > row.ema200)
    s += 5 * (row.ema200_up)
    s += 5 * (row.st > 0)
    s += 5 * ((row.adx >= 25) and (row.pdi > row.mdi))
    # Momentum (15)
    if 55 <= row.rsi <= 70:
        s += 8
    elif 50 <= row.rsi < 55 or 70 < row.rsi <= 75:
        s += 4
    s += 7 * ((row.macd > row.macd_sig) and (row.macd_hist > row.macd_hist_prev))
    # Breakout & volume (15)
    s += 6 if row.Close > row.hh55 else (3 if row.Close > row.hh20 else 0)
    s += 5 * (row.vol_ratio >= 1.5)
    s += 4 * bool(row.obv_up)
    # Structure / risk (10)
    s += 5 if row.from_high >= -7 else (3 if row.from_high >= -15 else 0)
    s += 3 * (row.vcp < 0.5)
    s += 2 * (1.2 <= row.atr_pct <= 4.5)
    return float(s)


def trade_plan(row, hold_days=60):
    entry = row.Close
    stop = max(row.ll10, entry - 2.5 * row.atr)
    stop = min(stop, entry * 0.97)          # at least 3% room
    stop = max(stop, entry * 0.90)          # never risk more than 10%
    t1, t2 = entry * 1.05, entry * 1.10
    risk = entry - stop
    dip = min(entry, max(entry - 0.5 * row.atr, row.hh20 if row.hh20 == row.hh20 else 0))
    return {
        "entry": round(entry, 2), "stop": round(stop, 2), "dip_buy": round(dip, 2),
        "exit_rule": "At T1 book half + move SL to cost; exit rest on daily close below 20 EMA (max 60 days)",
        "ema20": round(row.ema20, 2),
        "target1": round(t1, 2), "target2": round(t2, 2),
        "risk_pct": round(risk / entry * 100, 1),
        "rr_t2": round((t2 - entry) / risk, 2) if risk > 0 else np.nan,
        "hold": f"up to {hold_days} days",
    }
