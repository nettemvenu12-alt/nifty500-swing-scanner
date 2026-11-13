"""Smart money (NSE bulk / block deals) and the NSE results calendar."""
import datetime as dt
import io
import json
import os

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEALS_FILE = os.path.join(ROOT, "data", "deals.json")
CAL_FILE = os.path.join(ROOT, "data", "results_calendar.json")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
      "Referer": "https://www.nseindia.com/", "Accept": "application/json"}
DEAL_URLS = {"bulk": "https://archives.nseindia.com/content/equities/bulk.csv",
             "block": "https://archives.nseindia.com/content/equities/block.csv"}
KEEP_DAYS = 45      # history kept in data/deals.json
WINDOW_DAYS = 10    # deals counted for the tag
MIN_CR = 5.0        # net value (₹ Cr) needed for a tag


def _fetch_deals():
    rows = []
    for kind, url in DEAL_URLS.items():
        try:
            r = requests.get(url, headers=UA, timeout=20)
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = [c.strip() for c in df.columns]
            for _, x in df.iterrows():
                day = dt.datetime.strptime(str(x["Date"]).strip().title(), "%d-%b-%Y").date()
                qty = float(str(x["Quantity Traded"]).replace(",", ""))
                px = float(str(x["Trade Price / Wght. Avg. Price"]).replace(",", ""))
                rows.append({"date": str(day), "symbol": str(x["Symbol"]).strip(), "kind": kind,
                             "client": str(x["Client Name"]).strip(),
                             "side": str(x["Buy/Sell"]).strip().upper(), "qty": qty, "price": px})
        except Exception as e:
            print(f"{kind} deals fetch failed:", e)
    return rows


def deals(today=None):
    """{symbol: {"net_cr", "buyers", "sellers"}} for the last WINDOW_DAYS days.

    A client that both bought and sold the same stock (HFT / jobbing) is counted
    only for its net position, and ignored when that net is under half of what it traded.
    """
    today = today or dt.date.today()
    try:
        hist = json.load(open(DEALS_FILE))
    except Exception:
        hist = []
    seen = {(h["date"], h["symbol"], h["kind"], h["client"], h["side"], h["qty"]) for h in hist}
    for r in _fetch_deals():
        k = (r["date"], r["symbol"], r["kind"], r["client"], r["side"], r["qty"])
        if k not in seen:
            seen.add(k)
            hist.append(r)
    cut = str(today - dt.timedelta(days=KEEP_DAYS))
    hist = sorted([h for h in hist if h["date"] >= cut], key=lambda h: (h["date"], h["symbol"]))
    try:
        json.dump(hist, open(DEALS_FILE, "w"), indent=0)
    except Exception as e:
        print("deals save failed:", e)

    win = str(today - dt.timedelta(days=WINDOW_DAYS))
    # The same trade can be reported as both a bulk and a block deal: count it once
    # (the larger of the two reports per day / stock / client / side).
    legs = {}
    for h in hist:
        if h["date"] < win:
            continue
        k = (h["date"], h["symbol"], h["client"], h["side"])
        legs.setdefault(k, {}).setdefault(h["kind"], 0.0)
        legs[k][h["kind"]] += h["qty"] * h["price"] / 1e7
    per = {}  # (symbol, client) -> [net value, gross value]
    for (_, sym, client, side), kinds in legs.items():
        val = max(kinds.values())
        a = per.setdefault((sym, client), [0.0, 0.0])
        a[0] += val if side == "BUY" else -val
        a[1] += val
    out = {}
    for (sym, client), (net, gross) in per.items():
        if gross <= 0 or abs(net) < 0.5 * gross:
            continue  # round-tripper
        o = out.setdefault(sym, {"net_cr": 0.0, "buyers": [], "sellers": []})
        o["net_cr"] += net
        (o["buyers"] if net > 0 else o["sellers"]).append((abs(net), client.title()))
    for o in out.values():
        o["net_cr"] = round(o["net_cr"], 1)
        o["buyers"] = [c for _, c in sorted(o["buyers"], reverse=True)[:3]]
        o["sellers"] = [c for _, c in sorted(o["sellers"], reverse=True)[:3]]
        o["tag"] = "buy" if o["net_cr"] >= MIN_CR else "sell" if o["net_cr"] <= -MIN_CR else ""
    return out


def results_calendar(today=None):
    """{symbol: days until its next board meeting for financial results} from NSE.
    Falls back to the last saved copy (dates re-counted from today)."""
    today = today or dt.date.today()
    dates = {}
    try:
        s = requests.Session()
        s.get("https://www.nseindia.com/", headers=UA, timeout=15)
        for r in s.get("https://www.nseindia.com/api/event-calendar", headers=UA, timeout=20).json():
            if "result" not in (str(r.get("purpose", "")) + " " + str(r.get("bm_desc", ""))).lower():
                continue
            day = str(dt.datetime.strptime(r["date"], "%d-%b-%Y").date())
            if day >= str(today) and day < dates.get(r["symbol"], "9999"):
                dates[r["symbol"]] = day
        if dates:
            json.dump(dates, open(CAL_FILE, "w"), indent=0, sort_keys=True)
    except Exception as e:
        print("results calendar fetch failed, using cache:", e)
    if not dates:
        try:
            dates = json.load(open(CAL_FILE))
        except Exception:
            dates = {}
    return {s: (dt.date.fromisoformat(d) - today).days for s, d in dates.items()
            if d >= str(today)}


CLOSED = ["STOP", "T1 + TRAIL EXIT", "T1 + EXIT AT COST", "EXPIRED"]


def weekly_summary(track, today):
    """How the tracked picks did: this week's new picks + everything so far."""
    if track is None or not len(track):
        return None
    t = track.copy()
    t["ret"] = pd.to_numeric(t.ret, errors="coerce")
    wk = t[pd.to_datetime(t.date) >= pd.Timestamp(today) - pd.Timedelta(days=6)]
    t1 = t.status.astype(str).str.startswith("T1")
    closed = t[t.status.isin(CLOSED)]
    rated = t.dropna(subset=["ret"])
    out = {"week_new": int(len(wk)), "total": int(len(t)),
           "target_hit": int(t1.sum()), "stopped": int((t.status == "STOP").sum()),
           "running": int((t.status == "OPEN").sum()), "closed": int(len(closed)),
           "win_rate": round(float((closed.ret > 0).mean() * 100), 1) if len(closed) else None,
           "avg_ret": round(float(rated.ret.mean()), 2) if len(rated) else None,
           "best": rated.sort_values("ret", ascending=False).head(3)[["symbol", "ret", "status"]].to_dict("records"),
           "worst": rated.sort_values("ret").head(3)[["symbol", "ret", "status"]].to_dict("records")}
    return out
