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
    iv = p.get("intra")
    intra = (f" · VWAP ₹{iv['vwap']} {'✅ above' if iv['above_vwap'] else '❌ below'} · ORB {iv['orb']}"
             if iv else "")
    pats = (" · 🕯 " + ", ".join(e(x) for x in p["patterns"])) if p.get("patterns") else ""
    why = "".join(f"<span>✔ {e(w)}</span>" for w in p.get("why", []))
    return f"""<div class="{cls}"><div class="row"><div><b class="sym">{e(p['symbol'])}</b>{' <span class="lab lST">NEW</span>' if p.get('new') else ''}{' <span class="lab hc">🔥 HIGH CONVICTION</span>' if p.get('high_conviction') else ''}{' <span class="lab lST">🎯 90% MODE</span>' if p.get('mode90') else ' <span class="lab lST">🎯 85% MODE</span>' if p.get('mode85') else ''}
<span class="muted">{e(p['name'])}</span><br><span class="stars">{p['stars']}</span>
<span class="lab l{p['label'][:2]}">{p['label']}</span> <b>{p['score']}</b>/100</div>{_spark(p['spark'])}</div>
<div class="muted">{e(p['setup'])} · {e(str(p['industry']))} · ₹{p['close']} ({p['chg']}%)</div>
<div class="plan"><span>Buy <b>₹{p['entry']}</b></span><span class="red">Stop ₹{p['stop']} (-{p['risk_pct']}%)</span>
<span class="green">T1 ₹{p['target1']}</span><span class="green">T2 ₹{p['target2']}</span></div>
<div class="muted">RSI {p['rsi']} · ADX {p['adx']} · Vol {p['vol_x']}x · {p['from_high']}% from 52W high ·
RS rank {p['rs_rank']} · Hist win {p['hist_win5'] if p['hist_win5'] is not None else '-'}%</div>
<div class="muted">🤖 AI win chance <b>{p.get('ml_prob') if p.get('ml_prob') is not None else '-'}%</b> ·
Qty <b>{p.get('qty', '-')}</b> (₹{p.get('invest', '-')}, max loss ₹{p.get('max_loss', '-')}) ·
Weekly {'✅' if p.get('weekly_up') else '❌'}{intra}{pats}</div>
<div class="muted">Limit-buy option ₹{p.get('dip_buy', '-')} · Exit: T1 → sell half, SL to cost; rest on close below 20 EMA (₹{p.get('ema20', '-')})</div>
{f'<div class="green">🎯 90% mode plan: buy ₹{p["entry"]} · sell all at ₹{p["m90_target"]} (+4%) · SL ₹{p["m90_stop"]} (-25%) · qty {p["m90_qty"]}</div>' if p.get('mode90') else ''}
{f'<div class="green">🎯 85% mode plan: buy ₹{p["entry"]} · sell all at ₹{p["m85_target"]} (+5%) · SL ₹{p["m85_stop"]} (-15%) · qty {p["m85_qty"]}</div>' if p.get('mode85') else ''}
{f'<div class="green">💰 Big investors bought ₹{p["smart"]["net_cr"]} Cr in bulk/block deals (10 days): {e(", ".join(p["smart"]["buyers"]))}</div>' if (p.get("smart") or {}).get("tag") == "buy" else ''}
<div class="why">{why}</div><div>{parts}</div><div class="muted">{e(fund)}</div>{warn}<ul>{news}</ul></div>"""


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
    setsec = "<h2>🧠 Setup health (last 12 months)</h2><table><tr><th>Setup</th><th>Trades</th><th>+5% hit</th><th>Avg</th><th>Status</th></tr>" + "".join(
        f"<tr><td>{H.escape(k)}</td><td>{v['recent_n']}</td><td>{v['recent_win']}%</td><td>{v['recent_avg']}%</td>"
        f"<td>{'✅ active' if v['active'] else '⏸ paused – ' + v['why']}</td></tr>"
        for k, v in (o.get("setup_status") or {}).items()) + "</table>"
    segsec = ""
    bysym = {p["symbol"]: p for p in o["picks"]}
    for name, v in (o.get("segments") or {}).items():
        note = " <span class='warn'>(extra strict, half qty)</span>" if name == "Smallcap 250" else ""
        rows_ = "".join(f"<tr><td><b>{H.escape(s)}</b></td><td>{bysym[s]['stars']}</td><td>{bysym[s]['score']}</td>"
                        f"<td>{H.escape(bysym[s]['setup'])}</td><td>{bysym[s]['entry']}</td><td class='red'>{bysym[s]['stop']}</td>"
                        f"<td class='green'>{bysym[s]['target1']}</td><td>{bysym[s].get('qty')}</td></tr>" for s in v["buy"])
        rows_ = rows_ or "<tr><td colspan=8>No clean buy setup today</td></tr>"
        watch = ""
        segsec += (f"<h2>{H.escape(name)}{note}</h2><table><tr><th>Stock</th><th>Rating</th><th>Score</th><th>Setup</th>"
                   f"<th>Buy</th><th>SL</th><th>T1</th><th>Qty</th></tr>{rows_}</table>{watch}")
    m = o.get("ml") or {}
    mlsec = ""
    if m.get("auc"):
        q = " · ".join(f"Q{i + 1} {v}%" for i, v in enumerate(m.get("quintiles", [])))
        mlsec = (f"<h2>🤖 AI model (gradient boosting, walk-forward tested)</h2><p class='muted'>"
                 f"Trained on {m['train_n']} past setups, tested on {m['test_n']} newer ones (from {m['test_from']}). "
                 f"Test AUC {m['auc']} · normal win {m['base_rate']}% → top-20% AI picks win {m['top20_win']}% "
                 f"(avg {m['top20_avg_ret']}% vs {m['all_avg_ret']}%). Win rate by AI score: {q}. "
                 f"{'Model is used in the score.' if m.get('useful') else 'Model did not beat baseline, so it is ignored.'}</p>")
    lv = o.get("live") or {}
    live = (f"<p>Closed {lv['closed']} · Win {lv['win_rate']}% · Avg {lv['avg_ret']}% · Open {lv.get('open', 0)}</p>"
            if lv.get("closed") else f"<p class='muted'>Tracking {lv.get('open', 0)} open picks — results appear as they close.</p>")
    trk = "".join(
        f"<tr><td>{t['date']}</td><td>{t['symbol']}</td><td>{t['entry']}</td><td>{t['status']}</td><td>{t['ret']}</td></tr>"
        for t in reversed(o.get("tracker", [])))
    live_badge = (f"<p class='amber'>⏱ LIVE intraday view ({o.get('session_min', 0)} min into session) – "
                  "today's candle is still forming; final signals at 5 PM.</p>") if o.get("intraday") else ""
    sectors = ("<h2>🏭 Leading sectors</h2><table><tr><th>Sector</th><th>RS rank</th><th>Today</th></tr>" + "".join(
        f"<tr><td>{H.escape(x['name'])}</td><td>{x['rs']}</td><td>{x['day']:+.2f}%</td></tr>"
        for x in o.get("sectors", [])) + "</table>") if o.get("sectors") else ""
    regcol = {"BULLISH": "green", "POSITIVE": "green", "NEUTRAL": "amber"}.get(r["label"], "red")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Swing Scanner {o['data_date']}</title>
<style>body{{background:#0b1220;color:#e5e7eb;font:14px system-ui,sans-serif;margin:0;padding:12px;max-width:860px;margin:auto}}
h1{{font-size:20px}}h2{{font-size:16px;margin-top:22px;border-bottom:1px solid #1f2937;padding-bottom:4px}}
.card{{background:#111a2e;border:1px solid #1f2937;border-radius:12px;padding:12px;margin:10px 0}}
.top{{border:2px solid #facc15}}.row{{display:flex;justify-content:space-between;align-items:center}}
.sym{{font-size:17px}}.muted{{color:#94a3b8;font-size:12.5px;margin:4px 0}}.stars{{color:#facc15}}
.lab{{padding:1px 6px;border-radius:6px;font-size:11px;background:#334155}}.lST{{background:#15803d}}.lBU{{background:#16a34a}}
.lAC{{background:#0e7490}}.hc{{background:#b45309}}.lWA{{background:#475569}}.plan{{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0}}.green{{color:#4ade80}}.red{{color:#f87171}}.amber{{color:#fbbf24}}
.chip{{display:inline-block;background:#1e293b;border-radius:6px;padding:1px 6px;margin:2px;font-size:11.5px}}
.why span{{display:inline-block;font-size:12px;color:#a7f3d0;margin-right:8px}}.warn{{color:#fbbf24;font-size:12.5px}}ul{{padding-left:18px;margin:4px 0}}li{{font-size:12.5px}}a{{color:#93c5fd}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}td,th{{padding:5px;border-bottom:1px solid #1f2937;text-align:left}}
.box{{display:flex;gap:8px;flex-wrap:wrap}}.box div{{background:#111a2e;border-radius:10px;padding:8px 10px}}</style></head><body>
<h1>📈 Nifty 500 Swing & BTST Scanner</h1><div class="muted">Data {o['data_date']} · generated {o['generated']} · {o['universe']} stocks scanned</div>
<div class="box"><div>Market <b class="{regcol}">{r['label']}</b></div><div>Nifty 500 {r['close']} ({r['ret21']}% 1M)</div>
<div>&gt;50 EMA {b['above_ema50']}%</div><div>&gt;200 EMA {b['above_ema200']}%</div><div>52W highs {b['new_52w_high']}</div></div>
{live_badge}<h2>⭐ Top pick today</h2>{top_html}{segsec}{sectors}
<h2>Swing picks · hold ≤60 days · target +5% / +10%</h2>{cards}
<h2>⚡ BTST · buy near 3:20 PM, sell next morning</h2><table><tr><th>Stock</th><th>Rating</th><th>Close</th><th>Day</th><th>Vol</th><th>Stop</th><th>Target</th></tr>{btst}</table>
<h2>🧪 Backtest (3 yrs, Nifty 500)</h2><table><tr><th>Setup</th><th>Trades</th><th>+5% before stop</th><th>+10%</th><th>Profitable</th><th>Avg</th></tr>{bt}</table>{bbt}
{mlsec}{setsec}<h2>📒 Live track record</h2>{live}<table><tr><th>Date</th><th>Stock</th><th>Entry</th><th>Status</th><th>Ret %</th></tr>{trk}</table>
<p class="muted">{DISCLAIMER}</p></body></html>"""


PAGES = "https://nettemvenu12-alt.github.io/nifty500-swing-scanner/"


def _esc(x):
    return H.escape(str(x), quote=False)


SEG_ICONS = {"Nifty 50": "🏛", "Nifty Next 50": "🏢", "Midcap 150": "📈", "Smallcap 250": "⚠️"}


def simple_list(o, title="🛒 <b>BUY LIST – swing (hold up to 60 days)</b>", skip=()):
    """Numbered buy list per index segment: 1. MCX, 2. PAYTM ... (no watchlist)."""
    bysym = {p["symbol"]: p for p in o["picks"]}
    L, n = [f"\n{title}"], 0
    if o.get("pause_new"):
        L.append("⏸ Market regime is BEAR (Nifty 50 below 200 DMA or weak signals) – no new buys, protect capital.")
        return "\n".join(L)
    for name, v in (o.get("segments") or {}).items():
        L.append(f"\n{SEG_ICONS.get(name, '•')} <b>{name}</b>"
                 + (" (strict rules, half qty)" if name == "Smallcap 250" else ""))
        buy = [x for x in v["buy"] if x not in skip]
        if not buy:
            L.append("   No buy today" if not v["buy"] else "   (already in the list above)")
            continue
        for sym in buy:
            p = bysym[sym]
            n += 1
            L.append(f"<b>{n}. {_esc(sym)}</b>  {p['stars']}  {p['score']:.0f}/100"
                     f"{'  🎯90%' if p.get('mode90') else '  🎯85%' if p.get('mode85') else '  🔥' if p.get('high_conviction') else ''}"
                     f"{'  💰' if (p.get('smart') or {}).get('tag') == 'buy' else ''}\n"
                     f"   Buy ₹{p['entry']} · SL ₹{p['stop']} · Target ₹{p['target1']} / ₹{p['target2']} · Qty {p.get('qty')}")
    if any((bysym[s].get("smart") or {}).get("tag") == "buy" for v in (o.get("segments") or {}).values() for s in v["buy"]):
        L.append("\n💰 = big investors bought in bulk/block deals (last 10 days)")
    if n == 0:
        L.append("\nNo stock passes all checks today. Waiting is also a good trade.")
    else:
        L.append("\nRule: at Target 1 sell half + move SL to buy price; sell rest when a day closes below 20 EMA.")
    return "\n".join(L)


def telegram_text(o):
    """Short, simple Telegram report: market line, your holdings, numbered buy list, BTST."""
    r, b = o["regime"], o["breadth"]
    live = o.get("intraday")
    head = (f"⏱ <b>LIVE {o['generated'][-9:-4]} report</b>" if live
            else f"📈 <b>Swing report {o['data_date']}</b>")
    L = [head, f"Market <b>{r['label']}</b> · Nifty 500 {r['close']} ({r.get('day', 0):+.2f}%)"
               + (f" · VIX {r['vix']} ({r['vix_note']})" if r.get("vix") else "")]
    if o.get("alerts"):
        L.append("\n🔔 <b>Tracked picks – updates</b>")
        for a in o["alerts"]:
            L.append(f"• <b>{_esc(a['symbol'])}</b> {_esc(a['status'])} ({a['ret']}%)")
    hr = o.get("holdings") or []
    if hr:
        tot = sum(h["pnl_rs"] for h in hr)
        L.append(f"\n💼 <b>Your holdings</b> · P&amp;L ₹{tot:+,}")
        for h in hr:
            L.append(f"• <b>{_esc(h['symbol'])}</b> {h['pnl']:+.2f}% · {_esc(h['action'])}")
    m = o.get("ml") or {}
    # a Qty of 0 means the share price is too high for the configured capital / risk
    m90 = [p for p in o["picks"] if p.get("mode90") and p.get("m90_qty", 0) > 0][:5]
    m85 = [p for p in o["picks"] if p.get("mode85") and p not in m90 and p.get("m85_qty", 0) > 0][:5]
    if not o.get("pause_new"):
        if m90:
            L.append(f"\n🎯 <b>FIRST BUY THESE – 90% MODE</b> (highest winning chance, tested {m.get('m90_win')}% wins)\n"
                     "Sell ALL at +4% · SL -25% (far, so buy only the Qty shown)")
            for k, p in enumerate(m90, 1):
                L.append(f"{k}. <b>{_esc(p['symbol'])}</b> Buy ₹{p['entry']} · Target ₹{p['m90_target']} · SL ₹{p['m90_stop']} · Qty {p['m90_qty']}")
        if m85:
            L.append(f"\n🎯 <b>{'NEXT' if m90 else 'FIRST BUY THESE'} – 85% MODE</b> (tested {m.get('m85_win')}% wins) – sell ALL at +5%, SL -15%")
            for k, p in enumerate(m85, 1):
                L.append(f"{k}. <b>{_esc(p['symbol'])}</b> Buy ₹{p['entry']} · Target ₹{p['m85_target']} · SL ₹{p['m85_stop']} · Qty {p['m85_qty']}")
        if not m90 and not m85:
            L.append("\n🎯 <b>90% / 85% MODE</b>: no stock qualifies right now – wait, or use the list below (lower winning chance).")
    L.append(simple_list(o, "🛒 <b>REMAINING BUY LIST – swing (hold up to 60 days)</b>",
                         skip={p["symbol"] for p in m90 + m85} if not o.get("pause_new") else ()))
    if o["btst"]:
        L.append("\n⚡ <b>BTST</b> (buy ~3:20 PM, sell next morning)" + (" – forming, confirm at 3:15" if live else ""))
        for k, p in enumerate(o["btst"][:3], 1):
            L.append(f"{k}. <b>{_esc(p['symbol'])}</b> ₹{p['close']} ({p['chg']:+.1f}%) · SL ₹{p['stop']} · Target ₹{p['target']}")
    w = o.get("weekly")
    if w:
        L.append(f"\n📊 <b>WEEKLY REPORT</b> – how the picks did")
        L.append(f"New picks this week: {w['week_new']} · tracked so far: {w['total']}")
        L.append(f"🎯 Target 1 hit: {w['target_hit']} · 🛑 Stop hit: {w['stopped']} · ⏳ Running: {w['running']}")
        if w.get("avg_ret") is not None:
            L.append(f"Average return per pick: {w['avg_ret']:+.2f}%"
                     + (f" · closed trades won {w['win_rate']}% ({w['closed']})" if w.get("closed") else ""))
        if w.get("best"):
            L.append("Best: " + ", ".join(f"{_esc(b['symbol'])} {b['ret']:+.1f}%" for b in w["best"]))
        if w.get("worst"):
            L.append("Worst: " + ", ".join(f"{_esc(b['symbol'])} {b['ret']:+.1f}%" for b in w["worst"]))
    if live:
        L.append("\n<i>Live: today's candle not closed yet.</i>")
    L.append(f'\n<a href="{PAGES}">Full details</a> · Not advice – always use SL.')
    return "\n".join(L)
