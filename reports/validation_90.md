# 90% MODE – robustness check

699 trades 2020-01-01 → 2026-08-10, AI walk-forward (trained only on past years). All numbers AFTER 0.35% costs per trade (STT, stamp, exchange, GST, DP, slippage).

Uses today's Nifty 500 list (survivorship bias) – real results somewhat lower.


## 1. Result after costs (rule used: half at +4%, rest trails 20 EMA, SL -25%)

- Win rate: **90.0%**
- Average per trade: **+2.76%** · profit factor 2.54
- Full -25% stop hit: 4.6% of trades

## 2. Year by year

- 2020: 69 trades · win 86% · avg +1.07%
- 2021: 143 trades · win 92% · avg +4.58%
- 2022: 58 trades · win 97% · avg +2.87%
- 2023: 125 trades · win 94% · avg +4.95%
- 2024: 122 trades · win 90% · avg +1.42%
- 2025: 80 trades · win 80% · avg -0.90%
- 2026: 102 trades · win 89% · avg +3.07%

## 3. Parameter sensitivity (target / stop) – a robust rule has no single lucky spike

- +3% / -20%: win 90.4% · avg +1.99%
- +3% / -25%: win 91.3% · avg +2.07%
- +3% / -30%: win 91.7% · avg +2.16%
- +4% / -20%: win 88.8% · avg +2.60%
- +4% / -25%: win 90.0% · avg +2.76%
- +4% / -30%: win 90.4% · avg +2.84%
- +5% / -20%: win 86.1% · avg +3.09%
- +5% / -25%: win 87.6% · avg +3.35%
- +5% / -30%: win 88.0% · avg +3.44%

## 4. Regime (Nifty 500 trend on the buy day)

- Bull (Nifty 500 > 50 > 200 EMA): 505 trades · win 90% · avg +2.71%
- Not bull: 194 trades · win 89% · avg +2.88%

## 5. Monte Carlo (10,000 reshuffles of the real trades, 100 trades each)

Position size as in the report: a full -25% stop costs ~1.5% of capital, so each trade's capital effect = return × 0.06.

- Capital change after 100 trades: median +17.3%, bad case (5%) +5.6%
- Worst fall from a peak: median -2.9%, bad case (5%) -5.5%
- Longest losing streak: median 2, bad case (5%) 3 in a row
- Chance of ending 100 trades with a loss: 0.7%
