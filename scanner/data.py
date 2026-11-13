"""Universe (Nifty 500) and price history download."""
import io
import os
import time

import pandas as pd
import requests
import yfinance as yf

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, "data", "nifty500.csv")
NSE_URLS = [
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
BENCH = "^CRSLDX"  # Nifty 500 index on Yahoo
NIFTY = "^NSEI"
VIX = "^INDIAVIX"


def load_universe():
    """Latest Nifty 500 list from NSE; falls back to the cached copy in data/."""
    for url in NSE_URLS:
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.ok and "Symbol" in r.text[:300]:
                df = pd.read_csv(io.StringIO(r.text))
                if len(df) > 400:
                    df.to_csv(CACHE, index=False)
                    break
        except Exception:
            pass
    df = pd.read_csv(CACHE)
    df.columns = [c.strip() for c in df.columns]
    return df[["Symbol", "Company Name", "Industry"]].rename(
        columns={"Company Name": "Name"})


def download(symbols, period="5y", chunk=100):
    """Returns {symbol: OHLCV DataFrame}. Symbols are NSE codes without .NS."""
    out = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        tickers = [s if s.startswith("^") else f"{s}.NS" for s in part]
        for attempt in range(3):
            try:
                raw = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                                  auto_adjust=True, threads=True, progress=False)
                break
            except Exception as e:  # network hiccup
                print("download retry", attempt, e)
                time.sleep(5)
        else:
            continue
        for s, t in zip(part, tickers):
            try:
                d = raw[t] if len(tickers) > 1 else raw
                if isinstance(d.columns, pd.MultiIndex):
                    d = d.droplevel(0, axis=1) if t in d.columns.get_level_values(0) else d.droplevel(1, axis=1)
                d = d.dropna(subset=["Close"])
                if len(d) >= 220:
                    out[s] = d[["Open", "High", "Low", "Close", "Volume"]].astype(float)
            except Exception:
                pass
    return out


def intraday(symbols):
    """Today's 15-min bars -> VWAP and opening-range (first 15 min) breakout status."""
    out = {}
    if not symbols:
        return out
    try:
        raw = yf.download([f"{s}.NS" for s in symbols], period="1d", interval="15m",
                          group_by="ticker", auto_adjust=False, threads=True, progress=False)
    except Exception as e:
        print("intraday download failed", e)
        return out
    for s in symbols:
        try:
            d = raw[f"{s}.NS"] if len(symbols) > 1 else raw
            if isinstance(d.columns, pd.MultiIndex):
                d = d.droplevel(0, axis=1)
            d = d.dropna(subset=["Close"])
            if d.empty or d.Volume.sum() == 0:
                continue
            tp = (d.High + d.Low + d.Close) / 3
            vwap = float((tp * d.Volume).sum() / d.Volume.sum())
            last = float(d.Close.iloc[-1])
            orb_h, orb_l = float(d.High.iloc[0]), float(d.Low.iloc[0])
            out[s] = {"vwap": round(vwap, 2), "last": round(last, 2),
                      "above_vwap": last > vwap,
                      "orb": "above" if last > orb_h else "below" if last < orb_l else "inside",
                      "day_high": round(float(d.High.max()), 2)}
        except Exception:
            pass
    return out
