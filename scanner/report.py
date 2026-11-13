"""Markdown, HTML dashboard (GitHub Pages) and Telegram text."""
import html as H

DISCLAIMER = ("Educational screener, not investment advice. No system wins 99% of the time; "
              "always use the stop-loss and size positions so one loss is small.")


def _top(out):
    good = [p for p in out["picks"] if p["setup"] != "Uptrend"]
    return (good or out["picks"])[:1]


def markdown(o):
    r, b = o["regime"], o["breadth"]
    L = [f"# Nifty 500 Swing & BTST Scan — {o['data_date']}", "",
         f"_Generated {o['generated']}_", "",
         f"**Market:** {r['label']} (Nifty 500 {r['close']}, 1M {r['ret21']}%, RSI {r['rsi']}) · "
         f"{b['above_ema50']}% stocks above 50 EMA · {b['above_ema200']}% above 200 EMA · "
         f"{b['new_52w_high']} at 52W high", ""]
    for p in _top(o):
        L += ["## ⭐ Top pick (simple answer: buy this one)", "",
              f"**{p['symbol']}** – {p['name']} · {p['stars']} {p['label']} · score {p['score']}/100",
              f"Setup: {p['setup']} · Buy ~₹{p['entry']} · Stop ₹{p['stop']} (-{p['risk_pct']}%) · "
              f"T1 ₹{p['target1']} (+5%) · T2 ₹{p['target2']} (+10%) · {p['hold']}", ""]
    L += ["## Swing picks (hold up to 60 days, target 5–10%)", "",
          "| # | Stock | Rating | Score | Setup | Buy | Stop | T1 | T2 | Hist win% | Notes |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, p in enumerate(o["picks"][:25], 1):
        L.append(f"| {i} | **{p['symbol']}** | {p['stars']} {p['label']} | {p['score']} | {p['setup']} | "
                 f"{p['entry']} | {p['stop']} | {p['target1']} | {p['target2']} | "
                 f"{p['hist_win5'] if p['hist_win5'] is not None else '-'} | {'; '.join(p['warnings'])} |")
    L += ["", "## BTST (buy near close today, sell tomorrow)", ""]
    if o["btst"]:
        L += ["| Stock | Rating | Close | Day % | Vol x | Stop | Target |", "|---|---|---|---|---|---|---|"]
        for p in o["btst"]:
            L.append(f"| **{p['symbol']}** | {p['stars']} | {p['close']} | {p['chg']} | {p['vol_x']} | "
                     f"{p['stop']} | {p['target']} |")
    else:
        L.append("No BTST setups today.")
    L += ["", "## Backtest (last ~3 years, all Nifty 500)", "",
          "| Setup | Trades | Hit +5% before stop | Hit +10% | Profitable % | Avg result % | Stopped % |",
          "|---|---|---|---|---|---|---|"]
    for k, s in o["swing_backtest"].items():
        L.append(f"| {k} | {s['n']} | {s.get('win5')} | {s.get('win10')} | {s.get('profit')} | {s.get('avg')} | {s.get('stop_rate')} |")
    bb = o["btst_backtest"]
    if bb.get("n"):
        L += ["", f"BTST: {bb['n']} trades · gap-up next day {bb['gap_up']}% · touched +1% next day "
              f"{bb['hit1']}% · avg open {bb['avg_open']}% · avg best {bb['avg_best']}%"]
    lv = o.get("live") or {}
    if lv.get("closed"):
        L += ["", f"## Live track record: {lv['closed']} closed picks · win {lv['win_rate']}% · "
              f"avg {lv['avg_ret']}% · {lv.get('open', 0)} open"]
    L += ["", f"> {DISCLAIMER}", ""]
    return "\n".join(L)


def _spark(vals, w=110, h=30):
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - (v - lo) / rng * h:.1f}" for i, v in enumerate(vals))
    col = "#22c55e" if vals[-1] >= vals[0] else "#ef4444"
    return f'<svg width="{w}" height="{h}"><polyline fill="none" stroke="{col}" stroke-width="1.6" points="{pts}"/></svg>'


def _card(p, top=False):
    e = H.escape
    f = p.get("fund") or {}
    fund = " · ".join(x for x in [
        f"Profit YoY {f['profit_yoy']}%" if f.get("profit_yoy") is not None else "",
        f"Sales YoY {f['sales_yoy']}%" if f.get("sales_yoy") is not None else "",
        f"ROE {f['roe']}%" if f.get("roe") is not None else "",
        f"PE {f['pe']}" if f.get("pe") is not None else "",
        f"D/E {f['de']}" if f.get("de") is not None else ""] if x)
    news = "".join(f'<li><a href="{e(n["link"])}">{e(n["title"][:110])}</a></li>' for n in p.get("news", []))
    parts = " ".join(f'<span class="chip">{e(k)} {v}</span>' for k, v in p["parts"].items())
    warn = "".join(f'<div class="warn">⚠ {e(w)}</div>' for w in p["warnings"])
    cls = "card top" if top else "card"
    return f"""<div class="{cls}"><div class="row"><div><b class="sym">{e(p['symbol'])}</b>
<span class="muted">{e(p['name'])}</span><br><span class="stars">{p['stars']}</span>
<span class="lab l{p['label'][:2]}">{p['label']}</span> <b>{p['score']}</b>/100</div>{_spark(p['spark'])}</div>
<div class="muted">{e(p['setup'])} · {e(str(p['industry']))} · ₹{p['close']} ({p['chg']}%)</div>
<div class="plan"><span>Buy <b>₹{p['entry']}</b></span><span class="red">Stop ₹{p['stop']} (-{p['risk_pct']}%)</span>
<span class="green">T1 ₹{p['target1']}</span><span class="green">T2 ₹{p['target2']}</span></div>
<div class="muted">RSI {p['rsi']} · ADX {p['adx']} · Vol {p['vol_x']}x · {p['from_high']}% from 52W high ·
RS rank {p['rs_rank']} · Hist win {p['hist_win5'] if p['hist_win5'] is not None else '-'}%</div>
<div>{parts}</div><div class="muted">{e(fund)}</div>{warn}<ul>{news}</ul></div>"""


def html(o):
    r, b = o["regime"], o["breadth"]
    top = _top(o)
    top_html = _card(top[0], True) if top else ""
    cards = "".join(_card(p) for p in o["picks"][:25])
    btst = "".join(
        f"<tr><td><b>{p['symbol']}</b></td><td>{p['stars']}</td><td>{p['close']}</td><td>{p['chg']}%</td>"
        f"<td>{p['vol_x']}x</td><td class='red'>{p['stop']}</td><td class='green'>{p['target']}</td></tr>"
        for p in o["btst"]) or "<tr><td colspan=7>No BTST setups today</td></tr>"
    bt = "".join(
        f"<tr><td>{k}</td><td>{s['n']}</td><td>{s.get('win5')}%</td><td>{s.get('win10')}%</td><td>{s.get('profit')}%</td><td>{s.get('avg')}%</td></tr>"
        for k, s in o["swing_backtest"].items())
    bb = o["btst_backtest"]
    bbt = (f"<p class='muted'>BTST history: {bb['n']} trades · next-day gap-up {bb['gap_up']}% · "
           f"touched +1% {bb['hit1']}%</p>") if bb.get("n") else ""
    lv = o.get("live") or {}
    live = (f"<p>Closed {lv['closed']} · Win {lv['win_rate']}% · Avg {lv['avg_ret']}% · Open {lv.get('open', 0)}</p>"
            if lv.get("closed") else f"<p class='muted'>Tracking {lv.get('open', 0)} open picks — results appear as they close.</p>")
    trk = "".join(
        f"<tr><td>{t['date']}</td><td>{t['symbol']}</td><td>{t['entry']}</td><td>{t['status']}</td><td>{t['ret']}</td></tr>"
        for t in reversed(o.get("tracker", [])))
    regcol = {"BULLISH": "green", "POSITIVE": "green", "NEUTRAL": "amber"}.get(r["label"], "red")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Swing Scanner {o['data_date']}</title>
<style>body{{background:#0b1220;color:#e5e7eb;font:14px system-ui,sans-serif;margin:0;padding:12px;max-width:860px;margin:auto}}
h1{{font-size:20px}}h2{{font-size:16px;margin-top:22px;border-bottom:1px solid #1f2937;padding-bottom:4px}}
.card{{background:#111a2e;border:1px solid #1f2937;border-radius:12px;padding:12px;margin:10px 0}}
.top{{border:2px solid #facc15}}.row{{display:flex;justify-content:space-between;align-items:center}}
.sym{{font-size:17px}}.muted{{color:#94a3b8;font-size:12.5px;margin:4px 0}}.stars{{color:#facc15}}
.lab{{padding:1px 6px;border-radius:6px;font-size:11px;background:#334155}}.lST{{background:#15803d}}.lBU{{background:#16a34a}}
.lAC{{background:#0e7490}}.lWA{{background:#475569}}.plan{{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0}}.green{{color:#4ade80}}.red{{color:#f87171}}.amber{{color:#fbbf24}}
.chip{{display:inline-block;background:#1e293b;border-radius:6px;padding:1px 6px;margin:2px;font-size:11.5px}}
.warn{{color:#fbbf24;font-size:12.5px}}ul{{padding-left:18px;margin:4px 0}}li{{font-size:12.5px}}a{{color:#93c5fd}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}td,th{{padding:5px;border-bottom:1px solid #1f2937;text-align:left}}
.box{{display:flex;gap:8px;flex-wrap:wrap}}.box div{{background:#111a2e;border-radius:10px;padding:8px 10px}}</style></head><body>
<h1>📈 Nifty 500 Swing & BTST Scanner</h1><div class="muted">Data {o['data_date']} · generated {o['generated']} · {o['universe']} stocks scanned</div>
<div class="box"><div>Market <b class="{regcol}">{r['label']}</b></div><div>Nifty 500 {r['close']} ({r['ret21']}% 1M)</div>
<div>&gt;50 EMA {b['above_ema50']}%</div><div>&gt;200 EMA {b['above_ema200']}%</div><div>52W highs {b['new_52w_high']}</div></div>
<h2>⭐ Top pick today</h2>{top_html}
<h2>Swing picks · hold ≤60 days · target +5% / +10%</h2>{cards}
<h2>⚡ BTST · buy near 3:20 PM, sell next morning</h2><table><tr><th>Stock</th><th>Rating</th><th>Close</th><th>Day</th><th>Vol</th><th>Stop</th><th>Target</th></tr>{btst}</table>
<h2>🧪 Backtest (3 yrs, Nifty 500)</h2><table><tr><th>Setup</th><th>Trades</th><th>+5% before stop</th><th>+10%</th><th>Profitable</th><th>Avg</th></tr>{bt}</table>{bbt}
<h2>📒 Live track record</h2>{live}<table><tr><th>Date</th><th>Stock</th><th>Entry</th><th>Status</th><th>Ret %</th></tr>{trk}</table>
<p class="muted">{DISCLAIMER}</p></body></html>"""


def telegram_text(o):
    r = o["regime"]
    L = [f"<b>📈 Swing scan {o['data_date']}</b> · Market {r['label']}"]
    for p in o["picks"][:8]:
        L.append(f"{p['stars']} <b>{p['symbol']}</b> {p['score']} {p['label']} · {p['setup']}\n"
                 f"   Buy {p['entry']} SL {p['stop']} T1 {p['target1']} T2 {p['target2']}")
    if o["btst"]:
        L.append("\n<b>⚡ BTST</b>")
        for p in o["btst"][:5]:
            L.append(f"{p['symbol']} {p['close']} ({p['chg']}%) SL {p['stop']} T {p['target']}")
    L.append("\n" + DISCLAIMER)
    return "\n".join(L)
