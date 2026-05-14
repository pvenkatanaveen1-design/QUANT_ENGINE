# Regime Engine

Regime detection runs before strategy routing. The output is a `regime_id` such as `Q1_M04`.

Base regimes:

- `Q1`: trend with controlled volatility.
- `Q2`: trend with elevated volatility.
- `Q3`: range with controlled volatility.
- `Q4`: chaos, transition, or no-trade.

Modifiers:

- `M01`: clean liquid market.
- `M02`: compression.
- `M03`: Asia session.
- `M04`: London open.
- `M05`: London-New York overlap.
- `M06`: late New York or rollover.
- `M07`: pre-news lock.
- `M08`: post-news.
- `M09`: liquidity sweep.
- `M10`: spread stress.
- `M11`: trend exhaustion.
- `M12`: multi-timeframe agreement.
- `M13`: USD/correlation shock.

Features currently implemented:

- True range and ATR.
- ATR percent of close.
- Volatility percentile.
- Trend efficiency.
- Simplified ADX.
- Slope score.
- Spread percentile.
- Jump z-score.
- Compression percentile.
- Candle body and wick ratios.
- Session classification.
- Liquidity sweep flags.

The detector only uses rows available at the decision point. No future candles are used.

