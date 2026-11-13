"""Quarterly results, valuation and quality checks (Yahoo Finance)."""
import datetime as dt

import numpy as np
import yfinance as yf


def _f(x):
    try:
        x = float(x)
        return None if np.isnan(x) else x
    except Exception:
        return None


def _growth(stmt, row_names):
    """YoY growth of latest quarter vs same quarter last year, and QoQ."""
    for name in row_names:
        if stmt is not None and name in stmt.index:
            s = stmt.loc[name].dropna()
            if len(s) >= 2:
                qoq = (s.iloc[0] / s.iloc[1] - 1) * 100 if s.iloc[1] > 0 else None
                yoy = (s.iloc[0] / s.iloc[4] - 1) * 100 if len(s) >= 5 and s.iloc[4] > 0 else None
                return qoq, yoy, float(s.iloc[0])
    return None, None, None


def fetch(symbol):
    t = yf.Ticker(f"{symbol}.NS")
    out = {"pe": None, "roe": None, "de": None, "mcap_cr": None, "sales_yoy": None,
           "profit_yoy": None, "profit_qoq": None, "eps_growth": None,
           "results_in_days": None, "sector": None}
    try:
        info = t.info or {}
        out["pe"] = _f(info.get("trailingPE"))
        roe = _f(info.get("returnOnEquity"))
        out["roe"] = roe * 100 if roe is not None else None
        out["de"] = _f(info.get("debtToEquity"))
        m = _f(info.get("marketCap"))
        out["mcap_cr"] = m / 1e7 if m else None
        eg = _f(info.get("earningsQuarterlyGrowth"))
        out["eps_growth"] = eg * 100 if eg is not None else None
        out["sector"] = info.get("sector")
    except Exception:
        pass
    try:
        q = t.quarterly_income_stmt
        _, out["sales_yoy"], _ = _growth(q, ["Total Revenue", "Operating Revenue"])
        out["profit_qoq"], out["profit_yoy"], _ = _growth(
            q, ["Net Income", "Net Income Common Stockholders"])
        if out["profit_yoy"] is None:
            out["profit_yoy"] = out["eps_growth"]
    except Exception:
        pass
    try:
        cal = t.calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if dates:
            d0 = dates[0] if isinstance(dates, list) else dates
            days = (d0 - dt.date.today()).days
            if -5 <= days <= 90:
                out["results_in_days"] = days
    except Exception:
        pass
    return out


def score(f):
    """0-15 points."""
    s = 0.0
    py, sy = f.get("profit_yoy"), f.get("sales_yoy")
    if py is not None:
        s += 6 if py >= 25 else 4 if py >= 10 else 2 if py >= 0 else 0
    else:
        s += 2
    if sy is not None:
        s += 3 if sy >= 15 else 2 if sy >= 5 else 0
    else:
        s += 1
    roe = f.get("roe")
    if roe is not None:
        s += 3 if roe >= 18 else 2 if roe >= 12 else 0
    de = f.get("de")
    if de is not None:
        s += 2 if de <= 50 else 1 if de <= 100 else 0
    pe = f.get("pe")
    if pe is not None and 0 < pe <= 60:
        s += 1
    return min(s, 15.0)
