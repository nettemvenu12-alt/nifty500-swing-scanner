"""Risky-stock filters: NSE surveillance lists (ASM / GSM) + price-action red flags."""
import json
import os

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "surveillance.json")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
      "Referer": "https://www.nseindia.com/", "Accept": "application/json"}


def surveillance():
    """{symbol: reason} for stocks under NSE ASM/GSM. Falls back to the last cached list."""
    out = {}
    try:
        s = requests.Session()
        s.get("https://www.nseindia.com/", headers=UA, timeout=15)
        asm = s.get("https://www.nseindia.com/api/reportASM", headers=UA, timeout=20).json()
        for part in ("longterm", "shortterm"):
            for r in (asm.get(part) or {}).get("data", []):
                out[r["symbol"]] = r.get("survDesc") or "ASM"
        for r in s.get("https://www.nseindia.com/api/reportGSM", headers=UA, timeout=20).json():
            out[r["symbol"]] = r.get("survDesc") or "GSM"
        if out:
            json.dump(out, open(CACHE, "w"), indent=0)
            return out
    except Exception as e:
        print("NSE surveillance fetch failed, using cache:", e)
    try:
        return json.load(open(CACHE))
    except Exception:
        return {}


def red_flags(d):
    """Price-action warning signs on daily data with indicators."""
    flags = []
    r = d.iloc[-1]
    big = (d.day_chg.abs().tail(10) >= 9.5).sum()
    if big >= 2:
        flags.append("Circuit-like moves recently")
    if r.atr_pct > 6:
        flags.append("Very volatile (ATR > 6%)")
    if r.Close < 50:
        flags.append("Low price stock")
    return flags
