"""Market regime: Nifty 50 trend (50/200 DMA) + India VIX + breadth + FII flows
-> BULL (full size) / NEUTRAL (half size, 3 positions) / BEAR (no new buys)."""
import datetime as dt
import json
import os

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FII_FILE = os.path.join(ROOT, "data", "fii_history.json")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
      "Referer": "https://www.nseindia.com/", "Accept": "application/json"}


def fii_flows():
    """Latest FII/DII cash numbers from NSE, kept as a growing history in data/."""
    try:
        hist = json.load(open(FII_FILE))
    except Exception:
        hist = {}
    try:
        s = requests.Session()
        s.get("https://www.nseindia.com/", headers=UA, timeout=15)
        for r in s.get("https://www.nseindia.com/api/fiidiiTradeReact", headers=UA, timeout=20).json():
            day = str(dt.datetime.strptime(r["date"], "%d-%b-%Y").date())
            key = "fii" if r["category"].startswith("FII") else "dii"
            hist.setdefault(day, {})[key] = float(r["netValue"])
        json.dump(dict(sorted(hist.items())[-120:]), open(FII_FILE, "w"), indent=0)
    except Exception as e:
        print("FII fetch failed:", e)
    days = sorted(hist)[-5:]
    return {"fii_5d": round(sum(hist[d].get("fii", 0) for d in days)),
            "dii_5d": round(sum(hist[d].get("dii", 0) for d in days)), "days": len(days)}


def classify(n50, vix, breadth_pct, fii):
    """n50: Nifty 50 daily DataFrame. Returns dict with regime, size multiplier, slots."""
    c = n50["Close"]
    last = float(c.iloc[-1])
    sma50, sma200 = float(c.rolling(50).mean().iloc[-1]), float(c.rolling(200).mean().iloc[-1])
    trend = 2 if last > sma50 and last > sma200 else 1 if last > sma200 else 0
    pts = trend
    notes = [f"Nifty 50 {last:.0f} ({'above' if last > sma50 else 'below'} 50 DMA {sma50:.0f}, "
             f"{'above' if last > sma200 else 'below'} 200 DMA {sma200:.0f})"]
    if vix is not None:
        pts += 1 if vix < 16 else -1 if vix > 20 else 0
        notes.append(f"VIX {vix:.1f}")
    pts += 1 if breadth_pct > 60 else -1 if breadth_pct < 40 else 0
    notes.append(f"breadth {breadth_pct:.0f}% above 50 EMA")
    if fii and fii.get("days"):
        f5 = fii["fii_5d"]
        pts += 1 if f5 > 0 else -1 if f5 < -5000 else 0
        notes.append(f"FII 5-day ₹{f5:+,} Cr")
    if trend == 0 or pts <= 1:
        reg, size, slots = "BEAR", 0.0, 0
    elif trend == 2 and pts >= 4:
        reg, size, slots = "BULL", 1.0, 5
    else:
        reg, size, slots = "NEUTRAL", 0.5, 3
    return {"regime": reg, "size": size, "slots": slots, "points": pts, "trend": trend,
            "nifty50": round(last, 2), "sma50": round(sma50, 2), "sma200": round(sma200, 2),
            "notes": " · ".join(notes)}
