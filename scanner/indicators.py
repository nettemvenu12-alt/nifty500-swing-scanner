"""Technical indicators (pure pandas, no TA-lib needed)."""
import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df, n=14):
    h, l = df["High"], df["Low"]
    up, dn = h.diff(), -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, n)
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi


def macd(close, f=12, s=26, sig=9):
    m = ema(close, f) - ema(close, s)
    signal = ema(m, sig)
    return m, signal, m - signal


def supertrend(df, n=10, mult=3.0):
    """Returns +1 when in uptrend, -1 in downtrend."""
    a = atr(df, n)
    hl2 = (df["High"] + df["Low"]) / 2
    upper = (hl2 + mult * a).values
    lower = (hl2 - mult * a).values
    close = df["Close"].values
    trend = np.ones(len(df))
    fu, fl = upper.copy(), lower.copy()
    for i in range(1, len(df)):
        fu[i] = upper[i] if (upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lower[i] if (lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1]) else fl[i - 1]
        if close[i] > fu[i - 1]:
            trend[i] = 1
        elif close[i] < fl[i - 1]:
            trend[i] = -1
        else:
            trend[i] = trend[i - 1]
    return pd.Series(trend, index=df.index)


def add_all(df, bench_close=None):
    """Adds every indicator column used by the strategies."""
    df = df.copy()
    c, v = df["Close"], df["Volume"]
    for n in (10, 20, 50, 100, 150, 200):
        df[f"ema{n}"] = ema(c, n)
    df["sma200"] = c.rolling(200).mean()
    df["rsi"] = rsi(c)
    df["atr"] = atr(df)
    df["atr_pct"] = df["atr"] / c * 100
    df["adx"], df["pdi"], df["mdi"] = adx(df)
    df["macd"], df["macd_sig"], df["macd_hist"] = macd(c)
    df["st"] = supertrend(df)
    df["vol20"] = v.rolling(20).mean()
    df["vol50"] = v.rolling(50).mean()
    df["vol_ratio"] = v / df["vol20"].shift()
    df["turnover_cr"] = (c * v).rolling(20).mean() / 1e7
    df["hh20"] = df["High"].rolling(20).max().shift()
    df["hh55"] = df["High"].rolling(55).max().shift()
    df["hh252"] = df["High"].rolling(252, min_periods=150).max()
    df["ll252"] = df["Low"].rolling(252, min_periods=150).min()
    df["ll10"] = df["Low"].rolling(10).min()
    df["from_high"] = (c / df["hh252"] - 1) * 100
    df["from_low"] = (c / df["ll252"] - 1) * 100
    df["ret5"] = c.pct_change(5) * 100
    df["ret21"] = c.pct_change(21) * 100
    df["ret63"] = c.pct_change(63) * 100
    df["ret126"] = c.pct_change(126) * 100
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    df["close_pos"] = (c - df["Low"]) / rng  # 1 = closed at day high
    df["day_chg"] = c.pct_change() * 100
    # Volatility contraction: short-term range vs longer-term range
    df["vcp"] = (df["High"].rolling(10).max() - df["Low"].rolling(10).min()) / \
                (df["High"].rolling(50).max() - df["Low"].rolling(50).min()).replace(0, np.nan)
    # Bollinger band width squeeze
    sd = c.rolling(20).std()
    df["bbw"] = 4 * sd / c.rolling(20).mean()
    df["bbw_rank"] = df["bbw"].rolling(126).rank(pct=True)
    # On-balance volume trend
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    df["obv_up"] = obv > ema(obv, 20)
    if bench_close is not None:
        b = bench_close.reindex(df.index).ffill()
        rs_line = c / b
        df["rs_line"] = rs_line
        df["rs_new_high"] = rs_line >= rs_line.rolling(126, min_periods=60).max() * 0.98
        df["rs63"] = (c.pct_change(63) - b.pct_change(63)) * 100
    add_weekly(df)
    add_candles(df)
    return df


def add_weekly(df):
    """Multi-timeframe: last COMPLETED week's trend mapped onto daily bars."""
    w = df["Close"].resample("W-FRI").last()
    e10, e30 = ema(w, 10), ema(w, 30)
    wk_up = ((w > e10) & (e10 > e30)).shift(1)  # previous completed week (no lookahead)
    wk_rsi = rsi(w).shift(1)
    df["wk_up"] = wk_up.reindex(df.index, method="ffill").fillna(False).astype(bool)
    df["wk_rsi"] = wk_rsi.reindex(df.index, method="ffill")
    return df


def add_candles(df):
    """Bullish candlestick / price-action patterns."""
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    po, pc = o.shift(), c.shift()
    df["engulf"] = (c > o) & (pc < po) & (c >= po) & (o <= pc)
    df["hammer"] = (body / rng < 0.35) & ((np.minimum(o, c) - l) / rng > 0.55) & (c >= o)
    df["inside_brk"] = (h.shift() < h.shift(2)) & (l.shift() > l.shift(2)) & (c > h.shift())
    nr = rng.rolling(7).min()
    df["nr7"] = (rng.shift() <= nr.shift()) & (c > h.shift())
    return df


def features(df, bench_ind=None):
    """Numeric feature matrix for the ML model (one row per day)."""
    c = df["Close"]
    f = pd.DataFrame(index=df.index)
    for col in ["rsi", "adx", "atr_pct", "from_high", "from_low", "vol_ratio", "ret5", "ret21",
                "ret63", "ret126", "vcp", "bbw_rank", "close_pos", "day_chg", "wk_rsi"]:
        f[col] = df[col]
    f["rs63"] = df.get("rs63", 0)
    for n in (20, 50, 200):
        f[f"d_ema{n}"] = (c / df[f"ema{n}"] - 1) * 100
    f["macd_n"] = df["macd_hist"] / c * 100
    f["st"] = df["st"]
    f["obv_up"] = df["obv_up"].astype(float)
    f["wk_up"] = df["wk_up"].astype(float)
    f["di_spread"] = df["pdi"] - df["mdi"]
    f["log_turnover"] = np.log1p(df["turnover_cr"])
    if bench_ind is not None:
        b = bench_ind.reindex(df.index).ffill()
        f["mkt_ret21"] = b["ret21"]
        f["mkt_d_ema50"] = (b["Close"] / b["ema50"] - 1) * 100
        f["mkt_rsi"] = b["rsi"]
    return f
