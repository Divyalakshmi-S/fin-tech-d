"""Technical indicators — RSI, MACD, Bollinger Bands, ATR, candlestick patterns, etc."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


def compute_rsi(prices: ArrayLike, period: int = 14) -> float | None:
    """Compute RSI from a price series."""
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def rsi_signal(rsi: float | None) -> str:
    if rsi is None:
        return "N/A"
    if rsi >= 70:
        return "⚠️ Overbought"
    elif rsi <= 30:
        return "🟢 Oversold (buy zone)"
    elif rsi <= 40:
        return "👀 Near oversold"
    elif rsi >= 60:
        return "📈 Strong momentum"
    return "➡️ Neutral"


def trend_signal(price: float, sma50: float | None, sma200: float | None) -> str:
    """Determine trend from moving averages."""
    if sma50 is None or sma200 is None:
        return "N/A"
    if sma50 > sma200 and price > sma50:
        return "🟢 Strong Uptrend"
    elif sma50 > sma200:
        return "📈 Uptrend"
    elif sma50 < sma200 and price < sma50:
        return "🔴 Strong Downtrend"
    elif sma50 < sma200:
        return "📉 Downtrend"
    return "➡️ Sideways"


def ma_crossover(
    sma50_prev: float | None,
    sma200_prev: float | None,
    sma50_now: float | None,
    sma200_now: float | None,
) -> str | None:
    """Detect golden cross / death cross."""
    if None in (sma50_prev, sma200_prev, sma50_now, sma200_now):
        return None
    if sma50_prev <= sma200_prev and sma50_now > sma200_now:
        return "✨ GOLDEN CROSS — bullish signal!"
    elif sma50_prev >= sma200_prev and sma50_now < sma200_now:
        return "💀 DEATH CROSS — bearish signal!"
    return None


def compute_ema(prices: ArrayLike, period: int) -> float | None:
    """Compute Exponential Moving Average (Varsity Module 2)."""
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = np.mean(prices[:period])
    for p in prices[period:]:
        ema = (p - ema) * multiplier + ema
    return round(ema, 2)


def compute_macd(prices: ArrayLike) -> dict | None:
    """Compute MACD indicator (Varsity Module 2 - Moving Averages).

    MACD = EMA(12) - EMA(26), Signal = EMA(9) of MACD line.
    Returns dict with macd, signal, histogram, crossover.
    """
    if len(prices) < 35:
        return None

    def _ema_series(data, period):
        mult = 2 / (period + 1)
        ema = [np.mean(data[:period])]
        for p in data[period:]:
            ema.append((p - ema[-1]) * mult + ema[-1])
        return ema

    ema12 = _ema_series(prices, 12)
    ema26 = _ema_series(prices, 26)

    offset = 26 - 12  # 14
    macd_line = [e12 - e26 for e12, e26 in zip(ema12[offset:], ema26)]

    if len(macd_line) < 9:
        return None

    signal_line = _ema_series(macd_line, 9)
    s_offset = 9
    histogram = [m - s for m, s in zip(macd_line[s_offset - 1 :], signal_line)]

    macd_val = round(macd_line[-1], 2)
    signal_val = round(signal_line[-1], 2)
    hist_val = round(histogram[-1], 2)

    crossover = None
    if len(macd_line) >= 2 and len(signal_line) >= 2:
        prev_diff = macd_line[-2] - signal_line[-2]
        curr_diff = macd_line[-1] - signal_line[-1]
        if prev_diff <= 0 and curr_diff > 0:
            crossover = "BULLISH"
        elif prev_diff >= 0 and curr_diff < 0:
            crossover = "BEARISH"

    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": hist_val,
        "crossover": crossover,
    }


def compute_bollinger_bands(
    prices: ArrayLike, period: int = 20, std_dev: int = 2
) -> dict | None:
    """Compute Bollinger Bands (Varsity Module 2 - Volatility).

    Returns dict with upper, middle (SMA), lower, %B, bandwidth.
    """
    if len(prices) < period:
        return None

    sma = np.mean(prices[-period:])
    std = np.std(prices[-period:])
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    current = prices[-1]
    pct_b = (current - lower) / (upper - lower) if upper != lower else 0.5
    bandwidth = ((upper - lower) / sma) * 100 if sma > 0 else 0

    return {
        "upper": round(upper, 2),
        "middle": round(sma, 2),
        "lower": round(lower, 2),
        "pct_b": round(pct_b, 2),
        "bandwidth": round(bandwidth, 2),
        "current": round(current, 2),
    }


def compute_atr(
    highs: ArrayLike, lows: ArrayLike, closes: ArrayLike, period: int = 14
) -> float | None:
    """Compute Average True Range (Varsity Module 9 - Risk Management)."""
    if len(closes) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr = np.mean(true_ranges[:period])
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period

    return round(atr, 2)


def detect_candlestick_patterns(
    opens: ArrayLike, highs: ArrayLike, lows: ArrayLike, closes: ArrayLike
) -> list[tuple[str, str, str]]:
    """Detect key candlestick patterns (Varsity Module 2 - Candlesticks)."""
    if len(closes) < 3:
        return []

    patterns = []
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    body = abs(c - o)
    total_range = h - l if h != l else 0.001
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l

    o1, h1, l1, c1 = opens[-2], highs[-2], lows[-2], closes[-2]
    body1 = abs(c1 - o1)

    if body < total_range * 0.1:
        patterns.append(("Doji", "⚪ Indecision — trend may reverse", "NEUTRAL"))

    if lower_shadow > body * 2 and upper_shadow < body * 0.5 and c >= o:
        patterns.append(
            ("Hammer", "🟢 Bullish reversal — buyers stepped in at lows", "BULLISH")
        )

    if upper_shadow > body * 2 and lower_shadow < body * 0.5 and c <= o:
        patterns.append(
            ("Shooting Star", "🔴 Bearish reversal — sellers rejected highs", "BEARISH")
        )

    if c1 < o1 and c > o and o <= c1 and c >= o1:
        patterns.append(
            ("Bullish Engulfing", "🟢 Strong buying — reversal signal", "BULLISH")
        )

    if c1 > o1 and c < o and o >= c1 and c <= o1:
        patterns.append(
            ("Bearish Engulfing", "🔴 Strong selling — reversal signal", "BEARISH")
        )

    if len(closes) >= 3:
        o2, c2 = opens[-3], closes[-3]
        if c2 < o2 and body1 < abs(c2 - o2) * 0.3 and c > o and c > (o2 + c2) / 2:
            patterns.append(
                ("Morning Star", "🟢 Bullish reversal — dawn after darkness", "BULLISH")
            )

    if len(closes) >= 3:
        o2, c2 = opens[-3], closes[-3]
        if c2 > o2 and body1 < abs(c2 - o2) * 0.3 and c < o and c < (o2 + c2) / 2:
            patterns.append(
                ("Evening Star", "🔴 Bearish reversal — sunset after rally", "BEARISH")
            )

    return patterns


def compute_stop_loss(price: float, atr: float | None, method: str = "atr") -> dict:
    """Calculate stop-loss and targets (Varsity Module 9)."""
    if method == "atr" and atr:
        stop = round(price - 2 * atr, 2)
    else:
        stop = round(price * 0.95, 2)

    risk = round(price - stop, 2)
    risk_pct = round((risk / price) * 100, 2) if price > 0 else 0

    return {
        "stop_loss": stop,
        "risk_per_share": risk,
        "risk_pct": risk_pct,
        "target_1": round(price + risk, 2),
        "target_2": round(price + 2 * risk, 2),
        "target_3": round(price + 3 * risk, 2),
    }


def position_size(
    capital: float, risk_pct_of_capital: float, price: float, stop_loss: float
) -> dict:
    """Calculate how many shares to buy based on risk (Varsity Module 9)."""
    risk_amount = capital * risk_pct_of_capital / 100
    risk_per_share = price - stop_loss
    if risk_per_share <= 0:
        return {"qty": 0, "amount": 0, "risk_amount": 0}

    qty = int(risk_amount / risk_per_share)
    return {
        "qty": qty,
        "amount": round(qty * price, 2),
        "risk_amount": round(qty * risk_per_share, 2),
    }
