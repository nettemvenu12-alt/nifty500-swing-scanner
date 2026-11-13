# 📈 Nifty 500 Swing + BTST Scanner

Scans all **Nifty 500** stocks every trading day on GitHub Actions and publishes a
mobile-friendly dashboard (GitHub Pages) with rated picks, trade plans, news and results.

## What it checks
| Area | Details |
|---|---|
| Price history | 3 years daily OHLCV (Yahoo Finance) |
| Trend | EMA 20/50/150/200, Stage-2 trend template, Supertrend, ADX |
| Momentum | RSI, MACD, 1/3/6-month returns |
| Breakouts | 55-day high, 52-week high, Bollinger squeeze, volatility contraction (VCP) |
| Volume | Volume surge vs 20-day avg, OBV trend, liquidity filter (≥ ₹10 Cr/day) |
| Relative strength | vs Nifty 500 index, percentile rank across all 500 |
| Results | Quarterly profit & sales growth YoY/QoQ, ROE, debt/equity, PE, next results date |
| News | Last 7 days Google News headlines + sentiment |
| Market regime | Nifty 500 trend + breadth (% stocks above 50/200 EMA) |
| Backtest | Every setup re-tested on 3 years of history across all stocks |
| AI model | Gradient-boosting model trained on ~5,000 past setups, walk-forward tested; gives each pick a win probability |
| Multi-timeframe | Weekly trend confirmation (last completed week) |
| Live intraday | Projected full-day volume, VWAP, opening-range breakout (15-min bars) |
| Candles | Bullish engulfing, hammer, inside-bar and NR7 breakouts |
| Sectors | Sector relative-strength ranking, bonus for leading sectors |
| Position size | Qty per pick from `config.json` (capital, 1% risk per trade) |
| Live tracker | Every pick is logged and its real outcome tracked (`data/pick_log.csv`) |

## Setups
- **A+ Momentum** – any setup + within 7% of 52W high + strong relative strength + stage-2 trend
- **Breakout** – close above 55-day high on 1.5× volume in an uptrend
- **52W High** – fresh 52-week-high close with volume
- **Squeeze** – volatility squeeze breaking out
- **Pullback** – uptrend stock bouncing off 20/50 EMA
- **BTST** – strong close near day high, 2× volume, 20-day breakout (buy ~3:20 PM, sell next morning)

## Score (0–100) → rating
Technical 65 · Relative strength 10 · Fundamentals 15 · News 5 · Backtest edge 5 · AI model 10 (scaled to 100), plus sector/candle/VWAP bonuses and weekly-trend/results-date penalties.
≥80 ★★★★★ STRONG BUY · ≥70 ★★★★ BUY · ≥60 ★★★ ACCUMULATE · ≥50 WATCH.
`WATCHLIST` = strong stock but no entry trigger today.

## Trade plan (swing, up to 60 days)
Buy near close · Stop = higher of 10-day low / 2.5×ATR (3–10% risk) ·
**T1 +5%: book half, move stop to cost** · rest exits on a daily close below the 20 EMA (max 60 days). Chosen by `tools/upgrade_research.py`: on unseen 2025-26 data this nearly doubled average profit vs a fixed +10% exit.

**🎯 85% mode** = entry trigger + AI probability in its top 10% + weekly uptrend + no results within 7 days. Plan: sell ALL at +5%, stop -15%, max 60 days. On unseen 2025-26 data: ~86% wins in ~100 trades, avg about +2.2% per trade. High win rate comes from the wide stop — one loss costs about three wins, so size small.

**🔥 High conviction** = entry trigger + AI probability in its top 30% + weekly uptrend + no results within 7 days + score ≥70 + above VWAP (live). On unseen data these won ~62% vs ~58% for all setups.

## Schedule
- 9:15, 10:15, 11:15, 12:15, 1:15, 2:30 IST — LIVE hourly Telegram report (new setups, BTST forming, target/SL alerts)
- 3:15 PM IST — BTST window scan
- 5:00 PM IST — final end-of-day swing scan
- Run any time: Actions → *Nifty 500 scan* → *Run workflow*

## Your capital
Edit `config.json` (`capital`, `risk_per_trade_pct`, `max_position_pct`) to get the right quantity per pick.

## Telegram alerts (optional)
Add repo secrets `TELEGRAM_BOT_TOKEN` (from @BotFather) and `TELEGRAM_CHAT_ID` (your id from @userinfobot; comma-separate several). Send /start to your bot once.

## Telegram commands (answered every ~10 min, 7:30 AM–11:30 PM)
| Command | What it does |
|---|---|
| `/check TATAMOTORS` | Full analysis + AI win chance + plan for any NSE stock |
| `/top` | Today's best picks |
| `/buy MCX 3720 3` | Save a real buy; SL/targets set automatically, hourly alerts |
| `/half MCX` | Mark half booked at T1 (SL moves to cost) |
| `/sell MCX [qty]` | Remove all or part of a holding |
| `/portfolio` | Live P&L and what to do for each holding |

Holdings are stored **encrypted** (`data/holdings.enc`, key derived from the bot token secret), and the bot only answers your own chat id.
Market risk also includes **India VIX** (≥20 = trade smaller). Friday's 5 PM report adds a **weekly summary**.

## Run locally
```
pip install -r requirements.txt
python main.py            # full scan
python main.py --no-news  # faster
```
`tools/` has research scripts used to compare filters and exits.

> ⚠️ Educational screener, not investment advice. No method wins 99% of the time —
> the backtest table on the dashboard shows the real historical hit rates. Always use the stop-loss
> and keep each position small.
