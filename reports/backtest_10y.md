# 10-year backtest – Nifty 500 swing scanner

Data 2017-11-15 → 2026-11-11 · 491 stocks · 20128 signals.

Exit rule: half at +5% (SL to cost), rest on close below 20 EMA, max 60 days. AI is walk-forward (trained only on past years).

> Uses today's Nifty 500 list → survivorship bias; real results would be somewhat lower.


## All setups, year by year

| Year | Trades | Profitable % | Avg % / trade | AI-top-30% profitable | AI-top-30% avg | Nifty 500 year % |
|---|---|---|---|---|---|---|
| 2017 | 290 | 63% | +1.42 | – | – | +35.9 |
| 2018 | 1010 | 50% | -0.92 | – | – | -3.4 |
| 2019 | 869 | 54% | +0.61 | – | – | +7.7 |
| 2020 | 1361 | 66% | +2.12 | 67% | +2.04 | +16.7 |
| 2021 | 3238 | 65% | +1.78 | 69% | +2.36 | +30.2 |
| 2022 | 1964 | 57% | +0.39 | 67% | +0.98 | +3.0 |
| 2023 | 3189 | 66% | +3.26 | 74% | +4.01 | +25.8 |
| 2024 | 4058 | 61% | +0.79 | 67% | +0.63 | +15.2 |
| 2025 | 2297 | 52% | -0.14 | 57% | -0.36 | +6.7 |
| 2026 | 1852 | 53% | +0.18 | 62% | +0.42 | -0.6 |

## Each setup (10 years)

| Setup | Trades | Profitable % | Avg % | Best year avg | Worst year avg |
|---|---|---|---|---|---|
| A+ Momentum | 5793 | 62% | +1.33 | +3.52 (2023) | -0.93 (2018) |
| Results Gap | 190 | 73% | +2.17 | +8.09 (2017) | -0.83 (2019) |
| Breakout | 2564 | 67% | +1.71 | +3.58 (2023) | -1.59 (2018) |
| 52W High | 3499 | 67% | +1.55 | +3.54 (2023) | -1.11 (2018) |
| Squeeze | 2093 | 63% | +1.13 | +3.28 (2023) | -0.37 (2026) |
| Pullback | 14692 | 58% | +1.04 | +3.17 (2023) | -0.88 (2018) |

## 🎯 85% mode (AI top 10% + weekly up + RS>15; +5% target / -15% stop)

| Year | Trades | Win % | Avg % |
|---|---|---|---|
| 2020 | 76 | 82% | +1.41 |
| 2021 | 138 | 86% | +2.17 |
| 2022 | 89 | 84% | +2.05 |
| 2023 | 156 | 85% | +2.28 |
| 2024 | 120 | 77% | +0.33 |
| 2025 | 86 | 80% | +1.05 |
| 2026 | 108 | 81% | +1.29 |
| **All** | 773 | **82%** | +1.57 |

## ₹1,00,000 portfolio simulation (max 5 stocks × 20%, costs 0.25%/trade)

| Strategy | Start | Final value | CAGR | Max drawdown | Signals available |
|---|---|---|---|---|---|
| AI top 30% signals (live exit rule) | 2020-01-01 | ₹265,177 | +15.3% | -37.8% | 5392 |
| 🎯 85% mode (+5% / -15%) | 2020-01-01 | ₹453,660 | +24.6% | -34.3% | 773 |
| All signals (no AI) | 2020-01-01 | ₹265,691 | +15.3% | -33.9% | 17959 |
| Nifty 500 index (buy & hold) | 2020-01-01 | ₹240,017 | +13.6% | -38.3% | – |

Note: portfolio caps 5 open trades, so many signals are skipped; when slots are full, new signals wait. Drawdown is measured on closed trades.
