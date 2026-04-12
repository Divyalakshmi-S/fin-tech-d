"""
Holdings analysis engine.
Fetches live market data for each portfolio holding and computes:
- Current price, daily change
- 52-week high/low & distance from them
- 50-day & 200-day moving averages (trend detection)
- 14-day RSI (overbought/oversold)
- Volume spike detection
- YTD & 1-year return
- PE ratio (stocks only)
- SIP value estimation
"""

import csv
import json
import numpy as np
import yfinance as yf
import feedparser
import urllib.request
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Portfolio loader — defined later in file (after AMFI section)
# Re-exported here for import compatibility:
#   from analysis import load_portfolio_extended
# The actual implementation is below the AMFI NAV section.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------


def compute_rsi(prices, period=14):
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


def rsi_signal(rsi):
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


def trend_signal(price, sma50, sma200):
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


def ma_crossover(sma50_prev, sma200_prev, sma50_now, sma200_now):
    """Detect golden cross / death cross."""
    if None in (sma50_prev, sma200_prev, sma50_now, sma200_now):
        return None
    if sma50_prev <= sma200_prev and sma50_now > sma200_now:
        return "✨ GOLDEN CROSS — bullish signal!"
    elif sma50_prev >= sma200_prev and sma50_now < sma200_now:
        return "💀 DEATH CROSS — bearish signal!"
    return None


# ---------------------------------------------------------------------------
# Main analysis for a single ticker
# ---------------------------------------------------------------------------


def analyze_ticker(ticker_symbol):
    """Fetch and analyze a single ticker. Returns dict or None."""
    try:
        ticker = yf.Ticker(ticker_symbol)

        # 1-year history for moving averages & RSI
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 20:
            return None

        closes = hist["Close"].values
        volumes = hist["Volume"].values
        current_price = round(closes[-1], 2)

        # Daily change
        daily_change = round(closes[-1] - closes[-2], 2) if len(closes) >= 2 else 0
        daily_change_pct = (
            round((daily_change / closes[-2]) * 100, 2) if len(closes) >= 2 else 0
        )

        # 52-week high/low
        high_52w = round(closes.max(), 2)
        low_52w = round(closes.min(), 2)
        from_high = round(((current_price - high_52w) / high_52w) * 100, 2)
        from_low = round(((current_price - low_52w) / low_52w) * 100, 2)

        # Moving averages
        sma50 = round(np.mean(closes[-50:]), 2) if len(closes) >= 50 else None
        sma200 = round(np.mean(closes[-200:]), 2) if len(closes) >= 200 else None
        sma50_prev = round(np.mean(closes[-51:-1]), 2) if len(closes) >= 51 else None
        sma200_prev = round(np.mean(closes[-201:-1]), 2) if len(closes) >= 201 else None

        # RSI
        rsi = compute_rsi(closes)

        # Volume analysis
        avg_vol = int(np.mean(volumes[-20:])) if len(volumes) >= 20 else None
        latest_vol = int(volumes[-1])
        vol_ratio = round(latest_vol / avg_vol, 2) if avg_vol and avg_vol > 0 else None

        # YTD return
        ytd_start = hist.loc[hist.index >= f"{datetime.now().year}-01-01"]
        ytd_return = None
        if not ytd_start.empty:
            ytd_return = round(
                (
                    (current_price - ytd_start["Close"].iloc[0])
                    / ytd_start["Close"].iloc[0]
                )
                * 100,
                2,
            )

        # 1-year return
        one_yr_return = round(((current_price - closes[0]) / closes[0]) * 100, 2)

        # PE ratio (if available)
        info = ticker.info or {}
        pe_ratio = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        market_cap = info.get("marketCap")
        sector = info.get("sector", "")
        dividend_yield = info.get("dividendYield")

        trend = trend_signal(current_price, sma50, sma200)
        crossover = ma_crossover(sma50_prev, sma200_prev, sma50, sma200)

        return {
            "price": current_price,
            "daily_change": daily_change,
            "daily_change_pct": daily_change_pct,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "from_high_pct": from_high,
            "from_low_pct": from_low,
            "sma50": sma50,
            "sma200": sma200,
            "rsi": rsi,
            "rsi_signal": rsi_signal(rsi),
            "trend": trend,
            "crossover": crossover,
            "vol_ratio": vol_ratio,
            "ytd_return": ytd_return,
            "one_yr_return": one_yr_return,
            "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
            "forward_pe": round(forward_pe, 2) if forward_pe else None,
            "market_cap": market_cap,
            "sector": sector,
            "dividend_yield": (
                round(dividend_yield * 100, 2) if dividend_yield else None
            ),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# SIP value estimator
# ---------------------------------------------------------------------------


def estimate_sip_value(ticker_symbol, monthly_amount, months=12):
    """Estimate current value of SIP investments over N months using historical prices."""
    if monthly_amount <= 0:
        return None
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period=f"{months + 1}mo")
        if hist.empty:
            return None

        # Simulate monthly purchases using first trading day of each month
        hist_monthly = hist.resample("MS").first().dropna()
        if len(hist_monthly) < 2:
            return None

        current_price = hist["Close"].iloc[-1]
        total_units = 0
        total_invested = 0

        for _, row in hist_monthly.iterrows():
            buy_price = row["Close"]
            if buy_price > 0:
                units = monthly_amount / buy_price
                total_units += units
                total_invested += monthly_amount

        current_value = total_units * current_price
        returns_pct = (
            ((current_value - total_invested) / total_invested) * 100
            if total_invested > 0
            else 0
        )

        return {
            "invested": round(total_invested, 2),
            "current_value": round(current_value, 2),
            "returns_pct": round(returns_pct, 2),
            "profit": round(current_value - total_invested, 2),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Analyze full portfolio
# ---------------------------------------------------------------------------


def analyze_portfolio(holdings):
    """Run analysis on all holdings that have tickers."""
    results = []
    for h in holdings:
        if not h["ticker"]:
            results.append({"holding": h, "analysis": None, "sip_value": None})
            continue

        analysis = analyze_ticker(h["ticker"])
        sip_value = None
        if h["sip_monthly"] > 0:
            sip_value = estimate_sip_value(h["ticker"], h["sip_monthly"])

        results.append(
            {
                "holding": h,
                "analysis": analysis,
                "sip_value": sip_value,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Format for WhatsApp
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# NEWS FEED — Google News RSS (free, no API key)
# ---------------------------------------------------------------------------

NEWS_FEEDS = {
    "Indian Stock Market": "https://news.google.com/rss/search?q=indian+stock+market+nifty+sensex&hl=en-IN&gl=IN&ceid=IN:en",
    "Gold Price India": "https://news.google.com/rss/search?q=gold+price+india&hl=en-IN&gl=IN&ceid=IN:en",
    "Mutual Funds India": "https://news.google.com/rss/search?q=mutual+funds+india+SIP&hl=en-IN&gl=IN&ceid=IN:en",
    "Investment Opportunities": "https://news.google.com/rss/search?q=investment+opportunities+india+stocks+2026&hl=en-IN&gl=IN&ceid=IN:en",
}

# Keywords that signal actionable news
BULLISH_KEYWORDS = [
    "rally",
    "surge",
    "bull",
    "record high",
    "breakout",
    "upgrade",
    "buy",
    "outperform",
    "growth",
    "positive",
    "gains",
    "boom",
    "recovery",
]
BEARISH_KEYWORDS = [
    "crash",
    "fall",
    "bear",
    "plunge",
    "downgrade",
    "sell",
    "correction",
    "decline",
    "loss",
    "warning",
    "risk",
    "slump",
    "weak",
]


def _simple_sentiment(text):
    """Quick keyword-based sentiment: 'bullish', 'bearish', or 'neutral'."""
    text_lower = text.lower()
    bull_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
    bear_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)
    if bull_count > bear_count:
        return "bullish"
    elif bear_count > bull_count:
        return "bearish"
    return "neutral"


def _extract_summary(entry):
    """Extract a short summary from RSS entry, stripping HTML."""
    import re

    raw = entry.get("summary", entry.get("description", ""))
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", "", raw).strip()
    # Take first 200 chars
    if len(clean) > 200:
        clean = clean[:200].rsplit(" ", 1)[0] + "..."
    return clean


def fetch_news(category=None, max_items=5):
    """Fetch news from Google News RSS. Returns list of dicts."""
    feeds = NEWS_FEEDS if category is None else {category: NEWS_FEEDS.get(category, "")}
    all_news = []

    for cat, url in feeds.items():
        if not url:
            continue
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                sentiment = _simple_sentiment(entry.title)
                all_news.append(
                    {
                        "category": cat,
                        "title": entry.title,
                        "link": entry.link,
                        "published": entry.get("published", ""),
                        "sentiment": sentiment,
                        "summary": _extract_summary(entry),
                    }
                )
        except Exception:
            continue

    return all_news


def fetch_ticker_news(ticker_symbol, company_name="", max_items=5):
    """Fetch news for a specific stock/MF ticker."""
    search_term = company_name or ticker_symbol.replace(".NS", "").replace("^", "")
    url = f"https://news.google.com/rss/search?q={search_term}+stock+india&hl=en-IN&gl=IN&ceid=IN:en"
    results = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
            sentiment = _simple_sentiment(entry.title)
            results.append(
                {
                    "title": entry.title,
                    "link": entry.link,
                    "published": entry.get("published", ""),
                    "sentiment": sentiment,
                    "summary": _extract_summary(entry),
                }
            )
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Per-stock NEWS IMPACT ANALYSIS — why it matters for your holding
# ---------------------------------------------------------------------------

# Keyword → impact category mapping
_NEWS_IMPACT_CATEGORIES = {
    "earnings": {
        "keywords": [
            "earnings",
            "profit",
            "revenue",
            "quarterly results",
            "q1",
            "q2",
            "q3",
            "q4",
            "net income",
            "topline",
            "bottomline",
            "EPS",
        ],
        "good": "{name}'s earnings or profits look strong — the stock price usually goes up when a company makes more money.",
        "bad": "{name}'s earnings or profits disappointed — the stock price usually drops when a company makes less money than expected.",
    },
    "management": {
        "keywords": [
            "CEO",
            "management",
            "leadership",
            "board",
            "resign",
            "appoint",
            "chairman",
            "director",
        ],
        "good": "Positive leadership news for {name} — new or strong management usually means the company is headed in a good direction.",
        "bad": "There's leadership trouble at {name} — when top people leave or there's controversy, the stock often dips until things settle.",
    },
    "regulation": {
        "keywords": [
            "regulation",
            "SEBI",
            "RBI",
            "government",
            "policy",
            "tax",
            "ban",
            "approval",
            "licence",
            "compliance",
            "fine",
            "penalty",
        ],
        "good": "Government or regulatory news is working in {name}'s favour — approvals or policy support help the stock go up.",
        "bad": "{name} is facing regulatory trouble (fines, bans, or stricter rules) — this can hurt the stock price.",
    },
    "expansion": {
        "keywords": [
            "expansion",
            "new plant",
            "acquisition",
            "merger",
            "partnership",
            "deal",
            "contract",
            "order",
            "launch",
            "capacity",
        ],
        "good": "{name} is growing — new deals, products, or expansion means more money coming in, which is good for the stock.",
        "bad": "A deal or expansion for {name} didn't go well — failed deals or overspending can drag the stock down.",
    },
    "sector": {
        "keywords": [
            "sector",
            "industry",
            "market",
            "competition",
            "demand",
            "supply",
            "commodity",
            "crude",
            "metal",
        ],
        "good": "{name}'s industry is doing well right now — when the whole sector goes up, your stock usually goes up too.",
        "bad": "{name}'s industry is struggling — even good companies can fall when their whole sector is going down.",
    },
    "analyst": {
        "keywords": [
            "upgrade",
            "downgrade",
            "target price",
            "analyst",
            "rating",
            "buy rating",
            "sell rating",
            "outperform",
            "underperform",
        ],
        "good": "Experts are recommending {name} — when analysts say 'buy', big investors usually follow, pushing the price up.",
        "bad": "Experts are warning about {name} — when analysts downgrade a stock, big investors often sell, pushing the price down.",
    },
    "dividend": {
        "keywords": ["dividend", "buyback", "bonus", "stock split", "payout"],
        "good": "{name} is sharing profits with investors (dividend/buyback) — this means the company is doing well and is confident about its future.",
        "bad": "{name} cut or reduced its dividend — this usually means the company is short on cash, which is a warning sign.",
    },
    "macro": {
        "keywords": [
            "inflation",
            "interest rate",
            "GDP",
            "recession",
            "global",
            "FII",
            "FDI",
            "dollar",
            "rupee",
            "trade war",
            "tariff",
        ],
        "good": "The economy is looking good (lower interest rates, growth) — this helps all stocks including {name}.",
        "bad": "The economy is facing problems (inflation, global tensions) — this can pull down {name}'s price even if the company is fine.",
    },
}


def analyze_news_impact(news_item, ticker_symbol="", company_name="", holding_amount=0):
    """Analyze why a news item matters for a specific holding.

    Returns dict with:
      - category: the type of news (earnings, regulation, etc.)
      - summary: one plain-English sentence explaining what this means for you
      - action: short, direct recommendation
      - sentiment_label: "Good news" / "Bad news" / "Just info"
    """
    title_lower = news_item["title"].lower()
    summary_lower = news_item.get("summary", "").lower()
    full_text = f"{title_lower} {summary_lower}"
    sentiment = news_item.get("sentiment", "neutral")

    # Identify the news category
    matched_category = None
    max_matches = 0
    for cat_key, cat_info in _NEWS_IMPACT_CATEGORIES.items():
        matches = sum(1 for kw in cat_info["keywords"] if kw.lower() in full_text)
        if matches > max_matches:
            max_matches = matches
            matched_category = cat_key

    if matched_category is None:
        matched_category = "sector"  # default fallback

    cat = _NEWS_IMPACT_CATEGORIES[matched_category]
    name = company_name or ticker_symbol.replace(".NS", "")

    # Build one clear summary + short action
    if sentiment == "bullish":
        summary = cat["good"].format(name=name)
        sentiment_label = "Good news"
        if holding_amount > 0:
            action = f"You can hold {name}. Your ₹{holding_amount:,.0f} investment looks safe."
        else:
            action = (
                f"Could be a good time to buy {name} — but watch for 1-2 days first."
            )
    elif sentiment == "bearish":
        summary = cat["bad"].format(name=name)
        sentiment_label = "Bad news"
        if holding_amount > 0:
            action = f"Keep an eye on {name}. Don't panic sell — wait and see if this gets worse."
        else:
            action = f"Wait before buying {name}. Let the price settle first."
    else:
        summary = f"This news about {name} doesn't clearly help or hurt the stock. No need to worry."
        sentiment_label = "Just info"
        action = "No action needed."

    return {
        "category": matched_category,
        "summary": summary,
        "action": action,
        "sentiment": sentiment,
        "sentiment_label": sentiment_label,
    }


def fetch_portfolio_news_with_impact(holdings, max_per_stock=3):
    """Fetch news for all portfolio holdings with impact analysis.

    Returns list of dicts: {holding, news_items: [{...news, impact: {...}}]}
    """
    results = []
    for h in holdings:
        if not h.get("ticker"):
            continue

        news_items = fetch_ticker_news(h["ticker"], h["name"], max_items=max_per_stock)
        enriched = []
        for item in news_items:
            impact = analyze_news_impact(
                item,
                ticker_symbol=h["ticker"],
                company_name=h["name"],
                holding_amount=h["amount"],
            )
            enriched.append({**item, "impact": impact})

        if enriched:
            # Count sentiments for this stock
            bull = sum(1 for n in enriched if n["sentiment"] == "bullish")
            bear = sum(1 for n in enriched if n["sentiment"] == "bearish")
            if bull > bear:
                overall = "bullish"
            elif bear > bull:
                overall = "bearish"
            else:
                overall = "neutral"

            results.append(
                {
                    "holding": h,
                    "news_items": enriched,
                    "overall_sentiment": overall,
                    "bull_count": bull,
                    "bear_count": bear,
                }
            )

    return results


# ---------------------------------------------------------------------------
# MARKET OPPORTUNITY SCANNER — Top Gainers/Losers + Sector Screening
# ---------------------------------------------------------------------------

# Major Indian stocks to scan for opportunities
WATCHLIST_TICKERS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "HINDUNILVR.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "HCLTECH.NS",
    "AXISBANK.NS",
    "ASIANPAINT.NS",
    "MARUTI.NS",
    "SUNPHARMA.NS",
    "TITAN.NS",
    "ULTRACEMCO.NS",
    "WIPRO.NS",
    "ADANIENT.NS",
    "BAJFINANCE.NS",
    "TMCV.NS",
    "TATASTEEL.NS",
    "POWERGRID.NS",
    "NTPC.NS",
    "JSWSTEEL.NS",
    "M&M.NS",
    "TECHM.NS",
    "INDUSINDBK.NS",
    "COALINDIA.NS",
]

SECTOR_TICKERS = {
    "IT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS"],
    "Banking": [
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "SBIN.NS",
        "KOTAKBANK.NS",
        "AXISBANK.NS",
    ],
    "Auto": ["MARUTI.NS", "TMCV.NS", "TMPV.NS", "M&M.NS"],
    "Pharma": ["SUNPHARMA.NS"],
    "Energy": ["RELIANCE.NS", "NTPC.NS", "POWERGRID.NS", "COALINDIA.NS"],
    "Metals": ["TATASTEEL.NS", "JSWSTEEL.NS"],
    "FMCG": ["HINDUNILVR.NS", "ITC.NS"],
    "Infrastructure": ["LT.NS", "ULTRACEMCO.NS", "ADANIENT.NS"],
    "Finance": ["BAJFINANCE.NS"],
    "Consumer": ["TITAN.NS", "ASIANPAINT.NS"],
}


def scan_top_movers(tickers=None, top_n=5):
    """Find top gainers and losers from a watchlist."""
    tickers = tickers or WATCHLIST_TICKERS
    movers = []

    for sym in tickers:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1mo")
            if len(hist) < 2:
                continue
            curr = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2]
            pct = round(((curr - prev) / prev) * 100, 2)

            # RSI for context
            closes = hist["Close"].values
            rsi = compute_rsi(closes) if len(closes) >= 15 else None

            # Volume spike
            vol_ratio = None
            if len(hist) >= 6 and hist["Volume"].iloc[-1] > 0:
                avg_vol = hist["Volume"].iloc[-6:-1].mean()
                if avg_vol > 0:
                    vol_ratio = round(hist["Volume"].iloc[-1] / avg_vol, 1)

            # 5-day streak
            streak = 0
            if len(hist) >= 5:
                for i in range(-1, -5, -1):
                    if hist["Close"].iloc[i] > hist["Close"].iloc[i - 1]:
                        streak += 1
                    else:
                        break

            movers.append(
                {
                    "ticker": sym,
                    "name": sym.replace(".NS", ""),
                    "price": round(curr, 2),
                    "change_pct": pct,
                    "rsi": rsi,
                    "vol_ratio": vol_ratio,
                    "streak": streak,
                }
            )
        except Exception:
            continue

    movers.sort(key=lambda x: x["change_pct"], reverse=True)
    gainers = movers[:top_n]
    losers = movers[-top_n:][::-1]  # worst first
    return gainers, losers


def scan_oversold_opportunities(tickers=None):
    """Find stocks that are oversold or near 52-week lows with clear buy reasoning."""
    tickers = tickers or WATCHLIST_TICKERS
    opportunities = []

    for sym in tickers:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            if len(hist) < 50:
                continue

            closes = hist["Close"].values
            curr = closes[-1]
            high_52 = float(closes.max())
            low_52 = float(closes.min())
            from_high = ((curr - high_52) / high_52) * 100
            from_low = ((curr - low_52) / low_52) * 100
            range_pct = (
                ((curr - low_52) / (high_52 - low_52)) * 100
                if high_52 != low_52
                else 50
            )

            rsi = compute_rsi(closes)
            info = t.info or {}
            pe_ratio = info.get("trailingPE")
            sector = info.get("sector", "")

            # Check if this is an opportunity
            is_opp = False
            if rsi is not None and rsi < 35:
                is_opp = True
            if from_high < -25:
                is_opp = True
            if from_low < 10:
                is_opp = True

            if not is_opp:
                continue

            # Build simple explanation
            why_cheap = []
            if rsi is not None and rsi < 35:
                why_cheap.append(
                    f"Momentum shows it's oversold (RSI {rsi:.0f}) — sellers may be exhausted"
                )
            if from_high < -25:
                why_cheap.append(
                    f"Dropped {abs(from_high):.0f}% from its best price this year"
                )
            if from_low < 10:
                why_cheap.append("Trading near its lowest price this year")

            # Should you buy today?
            buy_now_score = 0
            buy_reasoning = []
            if rsi is not None and rsi < 30:
                buy_now_score += 2
                buy_reasoning.append("Very oversold — bounce likely soon")
            elif rsi is not None and rsi < 35:
                buy_now_score += 1
                buy_reasoning.append("Oversold — could bounce")
            if from_high < -30:
                buy_now_score += 2
                buy_reasoning.append("Big discount from yearly high")
            elif from_high < -25:
                buy_now_score += 1
                buy_reasoning.append("Good discount from yearly high")
            if pe_ratio and pe_ratio < 15:
                buy_now_score += 1
                buy_reasoning.append(f"Cheap valuation (PE {pe_ratio:.0f}x)")
            elif pe_ratio and pe_ratio > 40:
                buy_now_score -= 1
                buy_reasoning.append(f"Expensive valuation (PE {pe_ratio:.0f}x)")

            # 5-day trend — is it still falling or stabilizing?
            if len(closes) >= 6:
                change_5d = ((curr - closes[-6]) / closes[-6]) * 100
                if change_5d > 0:
                    buy_now_score += 1
                    buy_reasoning.append("Started recovering this week")
                elif change_5d < -3:
                    buy_now_score -= 1
                    buy_reasoning.append("Still falling — might get cheaper")

            if buy_now_score >= 3:
                buy_verdict = "Yes, today looks like a good entry"
                urgency = "high"
            elif buy_now_score >= 1:
                buy_verdict = (
                    "Decent price, but you can wait 1-2 days for a better entry"
                )
                urgency = "medium"
            else:
                buy_verdict = "Not yet — wait for the price to stabilize or drop more"
                urgency = "low"

            opportunities.append(
                {
                    "ticker": sym,
                    "name": sym.replace(".NS", ""),
                    "price": round(curr, 2),
                    "rsi": rsi,
                    "from_high_pct": round(from_high, 1),
                    "high_52w": round(high_52, 2),
                    "low_52w": round(low_52, 2),
                    "range_pct": round(range_pct, 1),
                    "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
                    "sector": sector,
                    "why_cheap": why_cheap,
                    "buy_verdict": buy_verdict,
                    "buy_reasoning": buy_reasoning,
                    "urgency": urgency,
                }
            )
        except Exception:
            continue

    # Sort by urgency (high first)
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    opportunities.sort(key=lambda x: urgency_order.get(x["urgency"], 3))
    return opportunities


def suggest_stock_swaps(sell_ticker, sell_amount, holdings, tickers=None):
    """Suggest stocks to buy if you sell a holding.

    Args:
        sell_ticker: ticker of stock to sell (e.g. "ONGC.NS")
        sell_amount: how much money you'd get from selling
        holdings: user's current portfolio (to exclude already-owned stocks)
        tickers: watchlist to scan (default: WATCHLIST_TICKERS)

    Returns list of suggestions sorted by buy score.
    """
    tickers = tickers or WATCHLIST_TICKERS
    owned_tickers = {h["ticker"] for h in holdings if h.get("ticker")}
    sell_name = sell_ticker.replace(".NS", "")

    suggestions = []
    for sym in tickers:
        if sym == sell_ticker or sym in owned_tickers:
            continue
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            if len(hist) < 30:
                continue

            closes = hist["Close"].values
            curr = float(closes[-1])
            info = t.info or {}
            name = sym.replace(".NS", "")
            sector = info.get("sector", "")
            pe_ratio = info.get("trailingPE")

            # How many shares can you buy?
            shares = int(sell_amount / curr) if curr > 0 else 0
            if shares < 1:
                continue

            investment = round(shares * curr, 2)
            leftover = round(sell_amount - investment, 2)

            # Quick health check
            rsi = compute_rsi(closes)
            high_52 = float(closes.max())
            low_52 = float(closes.min())
            from_high = ((curr - high_52) / high_52) * 100

            score = 0
            pros = []
            cons = []

            if rsi is not None and rsi < 35:
                score += 2
                pros.append("Oversold — good entry point")
            elif rsi is not None and rsi < 50:
                score += 1
                pros.append("Price momentum is in your favour")
            elif rsi is not None and rsi > 70:
                score -= 2
                cons.append("Overbought — price may drop soon")

            if from_high < -25:
                score += 2
                pros.append(
                    f"Down {abs(from_high):.0f}% from yearly high — big discount"
                )
            elif from_high < -15:
                score += 1
                pros.append(f"Down {abs(from_high):.0f}% from yearly high")
            elif from_high > -5:
                score -= 1
                cons.append("Near yearly high — limited upside")

            if pe_ratio and pe_ratio < 15:
                score += 1
                pros.append(f"Cheap valuation (PE {pe_ratio:.0f}x)")
            elif pe_ratio and pe_ratio > 50:
                score -= 1
                cons.append(f"Expensive (PE {pe_ratio:.0f}x)")

            if score < 0:
                continue  # Skip bad options

            suggestions.append(
                {
                    "ticker": sym,
                    "name": name,
                    "price": round(curr, 2),
                    "sector": sector,
                    "shares": shares,
                    "investment": investment,
                    "leftover": leftover,
                    "score": score,
                    "pros": pros,
                    "cons": cons,
                    "rsi": rsi,
                    "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
                    "from_high_pct": round(from_high, 1),
                }
            )
        except Exception:
            continue

    suggestions.sort(key=lambda x: x["score"], reverse=True)
    return suggestions


def scan_sector_performance():
    """Calculate average daily change per sector and return per-stock data.

    Returns dict: {sector: {"avg_change": float, "stocks": [{"name", "price", "change_pct"}, ...]}}
    """
    sector_perf = {}
    for sector, tickers in SECTOR_TICKERS.items():
        stocks = []
        for sym in tickers:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="5d")
                if len(hist) >= 2:
                    curr = hist["Close"].iloc[-1]
                    prev = hist["Close"].iloc[-2]
                    pct = round(((curr - prev) / prev) * 100, 2)
                    stocks.append(
                        {
                            "ticker": sym,
                            "name": sym.replace(".NS", ""),
                            "price": round(curr, 2),
                            "change_pct": pct,
                        }
                    )
            except Exception:
                continue
        if stocks:
            avg = round(sum(s["change_pct"] for s in stocks) / len(stocks), 2)
            stocks.sort(key=lambda x: x["change_pct"], reverse=True)
            sector_perf[sector] = {"avg_change": avg, "stocks": stocks}

    return dict(
        sorted(sector_perf.items(), key=lambda x: x[1]["avg_change"], reverse=True)
    )


# ---------------------------------------------------------------------------
# GOLD TREND ANALYSIS — weekly & monthly context
# ---------------------------------------------------------------------------


def _gold_inr_series(gold_hist, fx_hist, premium=1.03):
    """Combine gold futures + FX into INR/gram series, handling timezone mismatches."""
    import pandas as pd

    g = gold_hist["Close"].copy()
    f = fx_hist["Close"].copy()
    g.index = g.index.tz_localize(None)
    f.index = f.index.tz_localize(None)
    df = pd.DataFrame({"gold": g, "fx": f}).ffill().dropna()
    if df.empty:
        return None
    return (df["gold"] * df["fx"]) / 31.1035 * premium


def analyze_gold_trend():
    """Analyze gold price trend over multiple timeframes."""
    try:
        gold = yf.Ticker("GC=F")
        usd_inr = yf.Ticker("USDINR=X")

        gold_hist = gold.history(period="3mo")
        fx_hist = usd_inr.history(period="3mo")

        if gold_hist.empty or fx_hist.empty:
            return None

        inr_per_gram = _gold_inr_series(gold_hist, fx_hist)
        if inr_per_gram is None or len(inr_per_gram) < 5:
            return None

        current = inr_per_gram.iloc[-1]

        # Weekly change (5 trading days)
        week_ago = (
            inr_per_gram.iloc[-6] if len(inr_per_gram) >= 6 else inr_per_gram.iloc[0]
        )
        weekly_change = round(((current - week_ago) / week_ago) * 100, 2)

        # Monthly change (~22 trading days)
        month_ago = (
            inr_per_gram.iloc[-23] if len(inr_per_gram) >= 23 else inr_per_gram.iloc[0]
        )
        monthly_change = round(((current - month_ago) / month_ago) * 100, 2)

        # 3-month high/low
        high_3m = round(inr_per_gram.max(), 2)
        low_3m = round(inr_per_gram.min(), 2)

        return {
            "weekly_change": weekly_change,
            "monthly_change": monthly_change,
            "high_3m": high_3m,
            "low_3m": low_3m,
        }
    except Exception:
        return None


def predict_gold_buy(use_news=True):
    """Analyze gold price data and predict if it's a good time to buy.

    Returns dict with:
      - signal: 'BUY', 'WAIT', or 'SELL'
      - confidence: 0-100
      - reasons: list of (factor, score, explanation) tuples
      - prediction: expected direction for next 5-7 days
      - current_price: current gold price INR/gram
    """
    try:
        gold = yf.Ticker("GC=F")
        usd_inr = yf.Ticker("USDINR=X")

        gold_hist = gold.history(period="6mo")
        fx_hist = usd_inr.history(period="6mo")

        if gold_hist.empty or fx_hist.empty:
            return None

        inr_per_gram = _gold_inr_series(gold_hist, fx_hist)
        if inr_per_gram is None or len(inr_per_gram) < 30:
            return None

        prices = inr_per_gram.values
        current = prices[-1]

        # --- Factor 1: RSI (14-day) ---
        rsi = compute_rsi(prices)
        rsi_score = 0
        rsi_reason = ""
        if rsi is not None:
            if rsi <= 25:
                rsi_score = 30
                rsi_reason = (
                    f"RSI is {rsi:.0f} — gold is deeply oversold, strong buying zone"
                )
            elif rsi <= 35:
                rsi_score = 20
                rsi_reason = f"RSI is {rsi:.0f} — oversold territory, good entry point"
            elif rsi <= 45:
                rsi_score = 8
                rsi_reason = (
                    f"RSI is {rsi:.0f} — leaning towards cheap, slight buy signal"
                )
            elif rsi <= 55:
                rsi_score = 0
                rsi_reason = f"RSI is {rsi:.0f} — perfectly neutral, no momentum edge"
            elif rsi <= 65:
                rsi_score = -8
                rsi_reason = f"RSI is {rsi:.0f} — leaning towards expensive"
            elif rsi <= 75:
                rsi_score = -20
                rsi_reason = f"RSI is {rsi:.0f} — getting overbought, wait for a dip"
            else:
                rsi_score = -30
                rsi_reason = f"RSI is {rsi:.0f} — heavily overbought, high risk of drop"

        # --- Factor 2: Price vs moving averages ---
        ma10 = np.mean(prices[-10:]) if len(prices) >= 10 else None
        ma20 = np.mean(prices[-20:]) if len(prices) >= 20 else None
        ma50 = np.mean(prices[-50:]) if len(prices) >= 50 else None
        ma_score = 0
        ma_reason = ""
        if ma20 and ma50:
            pct_from_ma20 = ((current - ma20) / ma20) * 100
            pct_from_ma50 = ((current - ma50) / ma50) * 100

            if current < ma20 and current < ma50:
                ma_score = 20
                ma_reason = f"Price is {abs(pct_from_ma20):.1f}% below 20-day and {abs(pct_from_ma50):.1f}% below 50-day avg — dip buying zone"
            elif current < ma20:
                ma_score = 10
                ma_reason = f"Price is {abs(pct_from_ma20):.1f}% below 20-day avg — short-term dip"
            elif current > ma20 and current > ma50 and ma20 > ma50:
                if pct_from_ma20 > 5:
                    ma_score = -15
                    ma_reason = f"Price is {pct_from_ma20:.1f}% above 20-day avg and in strong uptrend — stretched, wait for pullback"
                else:
                    ma_score = -8
                    ma_reason = (
                        f"Price is above both averages — uptrend, slightly expensive"
                    )
            elif ma10 and ma10 < ma20:
                ma_score = 8
                ma_reason = f"Short-term avg just crossed below medium-term — possible dip forming, could be an entry soon"
            else:
                ma_score = 0
                ma_reason = f"Price is near moving averages — no clear trend"

        # --- Factor 3: Position in 3-month range ---
        high_3m = prices[-66:].max() if len(prices) >= 66 else prices.max()
        low_3m = prices[-66:].min() if len(prices) >= 66 else prices.min()
        range_pct = (
            ((current - low_3m) / (high_3m - low_3m)) * 100 if high_3m != low_3m else 50
        )
        range_score = 0
        if range_pct <= 15:
            range_score = 25
            range_reason = f"Price is near the 3-month low (bottom {range_pct:.0f}%) — strong buying level"
        elif range_pct <= 30:
            range_score = 15
            range_reason = f"Price is in the lower third of 3-month range ({range_pct:.0f}%) — good value"
        elif range_pct <= 45:
            range_score = 5
            range_reason = (
                f"Price is in the lower-mid range ({range_pct:.0f}%) — slightly cheap"
            )
        elif range_pct <= 55:
            range_score = 0
            range_reason = (
                f"Price is mid-range ({range_pct:.0f}%) — fair value, no edge"
            )
        elif range_pct <= 70:
            range_score = -5
            range_reason = f"Price is in the upper-mid range ({range_pct:.0f}%) — slightly expensive"
        elif range_pct <= 85:
            range_score = -15
            range_reason = (
                f"Price is in the upper third ({range_pct:.0f}%) — expensive territory"
            )
        else:
            range_score = -25
            range_reason = f"Price is near 3-month high (top {100 - range_pct:.0f}%) — risky to buy now"

        # --- Factor 4: Recent momentum (5-day vs 20-day) ---
        change_5d = (
            ((current - prices[-6]) / prices[-6]) * 100 if len(prices) >= 6 else 0
        )
        change_20d = (
            ((current - prices[-21]) / prices[-21]) * 100 if len(prices) >= 21 else 0
        )
        momentum_score = 0
        if change_5d < -3 and change_20d < -5:
            momentum_score = 20
            momentum_reason = f"Gold fell {change_5d:.1f}% in 5 days, {change_20d:.1f}% in 20 days — sharp correction, strong bounce likely"
        elif change_5d < -2 and change_20d < -3:
            momentum_score = 12
            momentum_reason = f"Gold fell {change_5d:.1f}% in 5 days — decent pullback, potential entry"
        elif change_5d < -1:
            momentum_score = 5
            momentum_reason = f"Gold dipped {change_5d:.1f}% in 5 days — minor pullback"
        elif change_5d > 4:
            momentum_score = -20
            momentum_reason = f"Gold surged {change_5d:+.1f}% in 5 days — very overheated, pullback imminent"
        elif change_5d > 2:
            momentum_score = -12
            momentum_reason = (
                f"Gold rose {change_5d:+.1f}% in 5 days — overheated, wait for cooling"
            )
        elif change_5d > 1:
            momentum_score = -5
            momentum_reason = f"Gold rose {change_5d:+.1f}% in 5 days — mild uptrend, slightly expensive"
        else:
            # Stable — check if 20d trend gives direction
            if change_20d < -3:
                momentum_score = 8
                momentum_reason = f"Gold stable this week but down {change_20d:.1f}% over 20 days — broader dip, could be entry"
            elif change_20d > 5:
                momentum_score = -8
                momentum_reason = f"Gold stable this week but up {change_20d:+.1f}% over 20 days — extended rally"
            else:
                momentum_score = 0
                momentum_reason = f"Gold moved {change_5d:+.1f}% in 5 days, {change_20d:+.1f}% in 20 days — sideways, no edge"

        # --- Factor 5: Volatility (10-day std dev) ---
        vol_score = 0
        vol_reason = ""
        if len(prices) >= 11:
            daily_returns = np.diff(prices[-11:]) / prices[-11:-1] * 100
            volatility = np.std(daily_returns)
            avg_vol = (
                np.std(np.diff(prices[-60:]) / prices[-60:-1] * 100)
                if len(prices) >= 60
                else volatility
            )

            if volatility > avg_vol * 1.5:
                vol_score = -8
                vol_reason = f"Gold is very choppy right now (volatility {volatility:.2f}% vs avg {avg_vol:.2f}%) — risky entry, wait for calmer market"
            elif volatility > avg_vol * 1.2:
                vol_score = -3
                vol_reason = f"Slightly elevated volatility ({volatility:.2f}% vs avg {avg_vol:.2f}%) — somewhat risky"
            elif volatility < avg_vol * 0.7:
                vol_score = 5
                vol_reason = f"Gold is calm right now (volatility {volatility:.2f}% vs avg {avg_vol:.2f}%) — good time for a stable entry"
            else:
                vol_score = 0
                vol_reason = f"Normal volatility ({volatility:.2f}%) — no extra risk"

        # --- Factor 6: Trend consistency (last 10 days) ---
        trend_score = 0
        trend_reason = ""
        if len(prices) >= 11:
            last_10 = prices[-10:]
            up_days = sum(
                1 for i in range(1, len(last_10)) if last_10[i] > last_10[i - 1]
            )
            down_days = 10 - 1 - up_days
            if down_days >= 7:
                trend_score = 12
                trend_reason = f"{down_days}/9 recent days were down — sustained selling, could be near a bottom"
            elif down_days >= 6:
                trend_score = 6
                trend_reason = f"{down_days}/9 recent days were down — consistent weakness, possible entry forming"
            elif up_days >= 7:
                trend_score = -12
                trend_reason = f"{up_days}/9 recent days were up — sustained buying, may be overextended"
            elif up_days >= 6:
                trend_score = -6
                trend_reason = f"{up_days}/9 recent days were up — consistent strength, slightly expensive"
            else:
                trend_score = 0
                trend_reason = f"Mixed recent days ({up_days} up, {down_days} down) — no clear pattern"

        # --- Factor 7: News sentiment ---
        news_score = 0
        news_reason = "News not analyzed"
        if use_news:
            try:
                gold_news = fetch_news("Gold Price India", max_items=8)
                if gold_news:
                    bull = sum(1 for n in gold_news if n["sentiment"] == "bullish")
                    bear = sum(1 for n in gold_news if n["sentiment"] == "bearish")
                    total = len(gold_news)
                    if bear > bull and bear >= 4:
                        news_score = 12
                        news_reason = f"News is heavily negative ({bear}/{total} bearish) — fear creates buying opportunities"
                    elif bear > bull and bear >= 2:
                        news_score = 6
                        news_reason = f"News is leaning negative ({bear}/{total} bearish) — could mean prices dip further (buy opportunity)"
                    elif bull > bear and bull >= 4:
                        news_score = -8
                        news_reason = f"News is very positive ({bull}/{total} bullish) — gold rally may already be priced in"
                    elif bull > bear and bull >= 2:
                        news_score = -4
                        news_reason = f"News is leaning positive ({bull}/{total} bullish) — some upside likely priced in"
                    else:
                        news_score = 0
                        news_reason = f"News sentiment is mixed ({bull} positive, {bear} negative) — no clear direction from news"
            except Exception:
                news_reason = "Could not fetch gold news"

        # --- Combine scores ---
        reasons = []
        if rsi is not None:
            reasons.append(("RSI", rsi_score, rsi_reason))
        if ma_reason:
            reasons.append(("Moving Averages", ma_score, ma_reason))
        reasons.append(("3M Range Position", range_score, range_reason))
        reasons.append(("Momentum", momentum_score, momentum_reason))
        if vol_reason:
            reasons.append(("Volatility", vol_score, vol_reason))
        if trend_reason:
            reasons.append(("Trend Consistency", trend_score, trend_reason))
        reasons.append(("News Sentiment", news_score, news_reason))

        total_score = sum(s for _, s, _ in reasons)

        # --- Signal determination ---
        if total_score >= 25:
            signal = "BUY"
        elif total_score >= 10:
            signal = "LEAN BUY"
        elif total_score <= -25:
            signal = "SELL"
        elif total_score <= -10:
            signal = "LEAN SELL"
        else:
            signal = "WAIT"

        # --- Confidence: how many factors agree on the direction ---
        positive_factors = sum(1 for _, s, _ in reasons if s > 0)
        negative_factors = sum(1 for _, s, _ in reasons if s < 0)
        neutral_factors = sum(1 for _, s, _ in reasons if s == 0)
        total_factors = len(reasons)

        if signal in ("BUY", "LEAN BUY"):
            agreement = positive_factors / total_factors
            score_strength = min(abs(total_score) / 50, 1.0)
        elif signal in ("SELL", "LEAN SELL"):
            agreement = negative_factors / total_factors
            score_strength = min(abs(total_score) / 50, 1.0)
        else:
            # WAIT — confidence is high when factors are genuinely neutral/mixed
            agreement = (
                neutral_factors + min(positive_factors, negative_factors)
            ) / total_factors
            score_strength = 1.0 - min(abs(total_score) / 30, 1.0)

        confidence = max(
            15, min(95, round((agreement * 0.5 + score_strength * 0.5) * 100))
        )

        # --- Prediction text ---
        if signal == "BUY":
            if change_5d < -2:
                prediction = f"Gold dropped {change_5d:.1f}% recently — expect a bounce in the next 5-7 days. Good time to buy."
            else:
                prediction = "Multiple factors favour buying — gold is likely to hold or rise this week."
        elif signal == "LEAN BUY":
            prediction = "Slightly favourable conditions — consider buying a small amount now, and more if it dips."
        elif signal == "SELL":
            if change_5d > 3:
                prediction = f"Gold surged {change_5d:+.1f}% recently — expect a pullback in the next 5-7 days."
            else:
                prediction = "Most indicators suggest gold is expensive — wait for a correction before buying."
        elif signal == "LEAN SELL":
            prediction = "Conditions lean slightly against buying — wait a few days for a better price."
        else:
            if abs(total_score) <= 3:
                prediction = "All factors are neutral — no edge either way. Watch for a clear signal before acting."
            else:
                prediction = "Mixed signals — some say buy, some say wait. Hold off for now and check again in a few days."

        return {
            "signal": signal,
            "confidence": confidence,
            "total_score": total_score,
            "reasons": reasons,
            "prediction": prediction,
            "current_price": round(current, 2),
            "rsi": rsi,
            "range_pct": round(range_pct, 1),
            "change_5d": round(change_5d, 2),
            "change_20d": round(change_20d, 2),
        }
    except Exception:
        return None


def save_gold_prediction(prediction):
    """Log a gold prediction to data/gold_predictions.json for tracking accuracy."""
    import os

    log_path = os.path.join(os.path.dirname(__file__), "data", "gold_predictions.json")

    # Load existing predictions
    predictions = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                predictions = json.load(f)
        except (json.JSONDecodeError, OSError):
            predictions = []

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "signal": prediction["signal"],
        "confidence": prediction["confidence"],
        "price_at_prediction": prediction["current_price"],
        "total_score": prediction["total_score"],
        "prediction_text": prediction["prediction"],
        "factor_scores": [
            {"name": name, "score": score, "reason": reason}
            for name, score, reason in prediction["reasons"]
        ],
        "verified": False,
        "actual_price_after": None,
        "was_correct": None,
    }

    # Don't duplicate same-day predictions
    today = entry["date"]
    predictions = [p for p in predictions if p["date"] != today]
    predictions.append(entry)

    with open(log_path, "w") as f:
        json.dump(predictions, f, indent=2)

    return entry


def _analyze_prediction_mistakes(predictions):
    """Analyze past wrong predictions to find which factors consistently fail.

    Returns dict:
      - factor_accuracy: {factor_name: {correct: N, wrong: N, accuracy: %}}
      - worst_factors: list of factor names that are most inaccurate
      - learnings: list of plain-language lessons learned
      - suggested_weights: {factor_name: weight_multiplier} — factors to trust less/more
    """
    verified = [p for p in predictions if p.get("verified") and p.get("factor_scores")]
    if not verified:
        return None

    # Track per-factor accuracy
    factor_stats = {}
    for p in verified:
        was_correct = p.get("was_correct", False)
        actual_change = p.get("actual_change_pct", 0)

        for f in p["factor_scores"]:
            name = f["name"]
            score = f["score"]
            if name not in factor_stats:
                factor_stats[name] = {
                    "correct": 0,
                    "wrong": 0,
                    "total": 0,
                    "scores_when_wrong": [],
                }

            factor_stats[name]["total"] += 1

            # A factor is "correct" if its direction matched the actual outcome
            factor_said_buy = score > 0
            factor_said_sell = score < 0
            actual_up = actual_change > 0
            actual_down = actual_change < 0

            if factor_said_buy and actual_up:
                factor_stats[name]["correct"] += 1
            elif factor_said_sell and actual_down:
                factor_stats[name]["correct"] += 1
            elif score == 0:
                # Neutral factor — correct if price didn't move much
                if abs(actual_change) < 2:
                    factor_stats[name]["correct"] += 1
                else:
                    factor_stats[name]["wrong"] += 1
                    factor_stats[name]["scores_when_wrong"].append(score)
            else:
                factor_stats[name]["wrong"] += 1
                factor_stats[name]["scores_when_wrong"].append(score)

    # Compute accuracy per factor
    factor_accuracy = {}
    for name, stats in factor_stats.items():
        total = stats["total"]
        if total == 0:
            continue
        acc = round((stats["correct"] / total) * 100)
        factor_accuracy[name] = {
            "correct": stats["correct"],
            "wrong": stats["wrong"],
            "total": total,
            "accuracy": acc,
        }

    # Find worst-performing factors
    worst_factors = sorted(
        [f for f, d in factor_accuracy.items() if d["total"] >= 2],
        key=lambda f: factor_accuracy[f]["accuracy"],
    )[:3]

    # Generate learnings
    learnings = []
    suggested_weights = {}

    for name, data in factor_accuracy.items():
        if data["total"] < 2:
            suggested_weights[name] = 1.0
            continue

        acc = data["accuracy"]
        if acc >= 70:
            suggested_weights[name] = 1.2  # Trust more
            learnings.append(
                f"✅ **{name}** has been reliable ({acc}% accurate over {data['total']} predictions) — trusting it more."
            )
        elif acc >= 50:
            suggested_weights[name] = 1.0  # Keep as-is
        elif acc >= 30:
            suggested_weights[name] = 0.7  # Trust less
            learnings.append(
                f"⚠️ **{name}** has been unreliable ({acc}% accurate over {data['total']} predictions) — reducing its weight."
            )
        else:
            suggested_weights[name] = 0.5  # Trust much less
            learnings.append(
                f"🔴 **{name}** has been mostly wrong ({acc}% accurate over {data['total']} predictions) — severely reducing its influence."
            )

    # Analyze overall pattern of wrong predictions
    wrong_preds = [p for p in verified if not p.get("was_correct")]
    if wrong_preds:
        # Check if we're biased towards buy or sell
        wrong_buy = sum(1 for p in wrong_preds if p["signal"] in ("BUY", "LEAN BUY"))
        wrong_sell = sum(1 for p in wrong_preds if p["signal"] in ("SELL", "LEAN SELL"))
        if wrong_buy > wrong_sell + 2:
            learnings.append(
                f"📊 **Bias detected**: I called BUY/LEAN BUY incorrectly {wrong_buy} times vs SELL {wrong_sell} times — I may be too optimistic."
            )
        elif wrong_sell > wrong_buy + 2:
            learnings.append(
                f"📊 **Bias detected**: I called SELL/LEAN SELL incorrectly {wrong_sell} times vs BUY {wrong_buy} times — I may be too pessimistic."
            )

    return {
        "factor_accuracy": factor_accuracy,
        "worst_factors": worst_factors,
        "learnings": learnings,
        "suggested_weights": suggested_weights,
        "total_verified": len(verified),
        "total_correct": sum(1 for p in verified if p.get("was_correct")),
    }


def get_prediction_learnings(asset="gold"):
    """Get the self-learning analysis for a prediction model.

    Args:
        asset: 'gold' or 'silver'

    Returns the mistake analysis or None if not enough data.
    """
    import os

    log_path = os.path.join(
        os.path.dirname(__file__), "data", f"{asset}_predictions.json"
    )
    if not os.path.exists(log_path):
        return None

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    return _analyze_prediction_mistakes(predictions)


def verify_gold_predictions():
    """Check past predictions against actual prices. Returns list of verified predictions."""
    import os

    log_path = os.path.join(os.path.dirname(__file__), "data", "gold_predictions.json")
    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    # Get current gold price for verification
    try:
        gold = yf.Ticker("GC=F")
        usd_inr = yf.Ticker("USDINR=X")
        gold_hist = gold.history(period="1mo")
        fx_hist = usd_inr.history(period="1mo")
        if gold_hist.empty or fx_hist.empty:
            return predictions
        common = gold_hist.index.intersection(fx_hist.index)
        gold_c = gold_hist.loc[common, "Close"]
        fx_c = fx_hist.loc[common, "Close"]
        inr = (gold_c * fx_c) / 31.1035 * 1.03
        current_price = round(inr.iloc[-1], 2) if len(inr) > 0 else None
    except Exception:
        return predictions

    if current_price is None:
        return predictions

    updated = False
    today = datetime.now()
    for p in predictions:
        if p["verified"]:
            continue
        pred_date = datetime.strptime(p["date"], "%Y-%m-%d")
        days_since = (today - pred_date).days
        if days_since < 5:
            continue  # too early to verify

        p["actual_price_after"] = current_price
        p["verified"] = True
        price_change_pct = (
            (current_price - p["price_at_prediction"]) / p["price_at_prediction"]
        ) * 100

        if p["signal"] == "BUY":
            p["was_correct"] = price_change_pct > 0  # price went up = correct
        elif p["signal"] == "SELL":
            p["was_correct"] = price_change_pct < 0  # price went down = correct
        else:  # WAIT
            p["was_correct"] = abs(price_change_pct) < 2  # stayed flat = correct

        p["actual_change_pct"] = round(price_change_pct, 2)
        updated = True

    if updated:
        with open(log_path, "w") as f:
            json.dump(predictions, f, indent=2)

    return predictions


# ---------------------------------------------------------------------------
# INDIVIDUAL STOCK BUY/SELL PREDICTION — detailed multi-factor analysis
# ---------------------------------------------------------------------------


def predict_stock_buy(ticker_symbol, company_name="", use_news=True):
    """Analyze a stock and predict if it's a good time to buy/sell.

    Uses 8 factors: RSI, Moving Averages, 52W Range, Momentum, Volume,
    PE Valuation, Trend Consistency, News Sentiment.

    Returns dict similar to predict_gold_buy().
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 30:
            return None

        closes = hist["Close"].values
        volumes = hist["Volume"].values
        current = closes[-1]
        info = ticker.info or {}
        name = company_name or ticker_symbol.replace(".NS", "")

        # --- Factor 1: RSI (14-day) ---
        rsi = compute_rsi(closes)
        rsi_score = 0
        rsi_reason = ""
        if rsi is not None:
            if rsi <= 25:
                rsi_score = 30
                rsi_reason = f"RSI is {rsi:.0f} — deeply oversold, strong buying zone"
            elif rsi <= 35:
                rsi_score = 20
                rsi_reason = f"RSI is {rsi:.0f} — oversold territory, good entry point"
            elif rsi <= 45:
                rsi_score = 8
                rsi_reason = f"RSI is {rsi:.0f} — leaning cheap"
            elif rsi <= 55:
                rsi_score = 0
                rsi_reason = f"RSI is {rsi:.0f} — neutral, no momentum edge"
            elif rsi <= 65:
                rsi_score = -8
                rsi_reason = f"RSI is {rsi:.0f} — leaning expensive"
            elif rsi <= 75:
                rsi_score = -20
                rsi_reason = f"RSI is {rsi:.0f} — overbought, wait for a dip"
            else:
                rsi_score = -30
                rsi_reason = f"RSI is {rsi:.0f} — heavily overbought, high risk of drop"

        # --- Factor 2: Price vs Moving Averages ---
        sma20 = np.mean(closes[-20:]) if len(closes) >= 20 else None
        sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else None
        sma200 = np.mean(closes[-200:]) if len(closes) >= 200 else None
        ma_score = 0
        ma_reason = ""
        if sma20 and sma50:
            pct_from_20 = ((current - sma20) / sma20) * 100
            if sma200:
                if current < sma20 and current < sma50 and current < sma200:
                    ma_score = 25
                    ma_reason = f"Price is below all key moving averages — deep value zone if fundamentals are intact"
                elif current < sma20 and current < sma50:
                    ma_score = 15
                    ma_reason = f"Price {abs(pct_from_20):.1f}% below 20-day and below 50-day avg — dip buying zone"
                elif current > sma20 and current > sma50 and sma20 > sma50:
                    if pct_from_20 > 8:
                        ma_score = -15
                        ma_reason = f"Price {pct_from_20:.1f}% above 20-day avg in strong uptrend — stretched, wait for pullback"
                    else:
                        ma_score = -5
                        ma_reason = (
                            "Price above all averages in uptrend — slightly expensive"
                        )
                elif sma50 < sma200:
                    ma_score = 10
                    ma_reason = "Long-term trend is down but could be forming a bottom"
                else:
                    ma_score = 0
                    ma_reason = "Price near moving averages — no clear trend"
            else:
                if current < sma20 and current < sma50:
                    ma_score = 15
                    ma_reason = f"Below 20-day and 50-day averages — dip zone"
                elif current > sma20 and current > sma50:
                    ma_score = -8
                    ma_reason = "Above both averages — slightly expensive"
                else:
                    ma_score = 0
                    ma_reason = "Between moving averages — mixed signal"

        # --- Factor 3: 52-week Range Position ---
        high_52w = closes.max()
        low_52w = closes.min()
        range_pct = (
            ((current - low_52w) / (high_52w - low_52w)) * 100
            if high_52w != low_52w
            else 50
        )
        range_score = 0
        if range_pct <= 15:
            range_score = 25
            range_reason = f"Near 52-week low (bottom {range_pct:.0f}%) — strong value if company is fundamentally sound"
        elif range_pct <= 30:
            range_score = 15
            range_reason = f"In the lower third ({range_pct:.0f}%) — gives safety margin for further drops"
        elif range_pct <= 45:
            range_score = 5
            range_reason = f"Lower-mid range ({range_pct:.0f}%) — slightly cheap"
        elif range_pct <= 55:
            range_score = 0
            range_reason = f"Mid-range ({range_pct:.0f}%) — fair value"
        elif range_pct <= 70:
            range_score = -5
            range_reason = f"Upper-mid range ({range_pct:.0f}%) — limited upside unless strong catalyst"
        elif range_pct <= 85:
            range_score = -15
            range_reason = f"Upper third ({range_pct:.0f}%) — expensive, most gains already captured"
        else:
            range_score = -25
            range_reason = f"Near 52-week high (top {100 - range_pct:.0f}%) — very risky to buy at all-time highs"

        # --- Factor 4: Momentum (5-day + 20-day) ---
        change_5d = (
            ((current - closes[-6]) / closes[-6]) * 100 if len(closes) >= 6 else 0
        )
        change_20d = (
            ((current - closes[-21]) / closes[-21]) * 100 if len(closes) >= 21 else 0
        )
        momentum_score = 0
        if change_5d < -5 and change_20d < -10:
            momentum_score = 22
            momentum_reason = f"Fell {change_5d:.1f}% in 5 days, {change_20d:.1f}% in 20 days — sharp correction, strong bounce candidate"
        elif change_5d < -3 and change_20d < -5:
            momentum_score = 15
            momentum_reason = (
                f"Fell {change_5d:.1f}% in 5 days — decent pullback, potential entry"
            )
        elif change_5d < -1:
            momentum_score = 5
            momentum_reason = f"Dipped {change_5d:.1f}% in 5 days — minor pullback"
        elif change_5d > 6:
            momentum_score = -20
            momentum_reason = f"Surged {change_5d:+.1f}% in 5 days — very overheated, pullback imminent"
        elif change_5d > 3:
            momentum_score = -12
            momentum_reason = (
                f"Rose {change_5d:+.1f}% in 5 days — overheated, wait for cooling"
            )
        elif change_5d > 1:
            momentum_score = -5
            momentum_reason = f"Rose {change_5d:+.1f}% in 5 days — mild uptrend"
        else:
            if change_20d < -5:
                momentum_score = 8
                momentum_reason = f"Stable this week but down {change_20d:.1f}% over 20 days — could be entry point"
            elif change_20d > 10:
                momentum_score = -8
                momentum_reason = f"Stable this week but up {change_20d:+.1f}% over 20 days — extended rally"
            else:
                momentum_score = 0
                momentum_reason = f"Moved {change_5d:+.1f}% in 5d — sideways, no edge"

        # --- Factor 5: Volume Analysis ---
        vol_score = 0
        vol_reason = ""
        if len(volumes) >= 21:
            avg_vol_20 = np.mean(volumes[-21:-1])
            latest_vol = volumes[-1]
            vol_ratio = latest_vol / avg_vol_20 if avg_vol_20 > 0 else 1

            if vol_ratio > 3 and change_5d < -2:
                vol_score = 10
                vol_reason = f"Volume {vol_ratio:.1f}x higher during a drop — could be capitulation (buying opportunity)"
            elif vol_ratio > 2 and change_5d > 2:
                vol_score = -5
                vol_reason = f"Volume {vol_ratio:.1f}x higher during a rise — strong interest but may be exhaustion"
            elif vol_ratio < 0.5:
                vol_score = 0
                vol_reason = (
                    f"Very low volume today — no conviction in either direction"
                )
            else:
                vol_score = 0
                vol_reason = f"Normal volume ({vol_ratio:.1f}x of average)"

        # --- Factor 6: PE Valuation ---
        pe_score = 0
        pe_reason = ""
        pe_ratio = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        sector_name = info.get("sector", "")

        if pe_ratio:
            if pe_ratio < 10:
                pe_score = 20
                pe_reason = f"PE ratio {pe_ratio:.1f}x — very cheap valuation, market may be underpricing this company"
            elif pe_ratio < 15:
                pe_score = 12
                pe_reason = f"PE ratio {pe_ratio:.1f}x — attractively valued"
            elif pe_ratio < 25:
                pe_score = 0
                pe_reason = f"PE ratio {pe_ratio:.1f}x — fairly valued"
            elif pe_ratio < 40:
                pe_score = -8
                pe_reason = f"PE ratio {pe_ratio:.1f}x — expensive, needs strong growth to justify"
            elif pe_ratio < 60:
                pe_score = -15
                pe_reason = f"PE ratio {pe_ratio:.1f}x — very expensive, high expectations baked in"
            else:
                pe_score = -20
                pe_reason = f"PE ratio {pe_ratio:.1f}x — extremely expensive, any disappointment could cause a sharp fall"

            # Adjust if forward PE is much lower (expected earnings growth)
            if forward_pe and pe_ratio > 20 and forward_pe < pe_ratio * 0.7:
                pe_score += 5
                pe_reason += (
                    f" (but forward PE is {forward_pe:.1f}x — earnings growth expected)"
                )
        else:
            pe_reason = "No PE data available — cannot assess valuation"

        # --- Factor 7: Trend Consistency (last 10 days) ---
        trend_score = 0
        trend_reason = ""
        if len(closes) >= 11:
            last_10 = closes[-10:]
            up_days = sum(
                1 for i in range(1, len(last_10)) if last_10[i] > last_10[i - 1]
            )
            down_days = 9 - up_days
            if down_days >= 7:
                trend_score = 12
                trend_reason = f"{down_days}/9 recent days were down — sustained selling, could be near bottom"
            elif down_days >= 6:
                trend_score = 6
                trend_reason = f"{down_days}/9 days down — consistent weakness, possible entry forming"
            elif up_days >= 7:
                trend_score = -12
                trend_reason = (
                    f"{up_days}/9 days up — sustained buying, may be overextended"
                )
            elif up_days >= 6:
                trend_score = -6
                trend_reason = (
                    f"{up_days}/9 days up — consistent strength, slightly expensive"
                )
            else:
                trend_score = 0
                trend_reason = (
                    f"Mixed days ({up_days} up, {down_days} down) — no clear pattern"
                )

        # --- Factor 8: News Sentiment ---
        news_score = 0
        news_reason = "News not analyzed"
        if use_news:
            try:
                stock_news = fetch_ticker_news(ticker_symbol, company_name, max_items=8)
                if stock_news:
                    bull = sum(1 for n in stock_news if n["sentiment"] == "bullish")
                    bear = sum(1 for n in stock_news if n["sentiment"] == "bearish")
                    total = len(stock_news)
                    if bear > bull and bear >= 4:
                        news_score = 10
                        news_reason = f"News is heavily negative ({bear}/{total}) — fear creates buying opportunities for strong companies"
                    elif bear > bull and bear >= 2:
                        news_score = 5
                        news_reason = f"News leaning negative ({bear}/{total}) — could dip further (opportunity if fundamentals are strong)"
                    elif bull > bear and bull >= 4:
                        news_score = -6
                        news_reason = f"News very positive ({bull}/{total}) — good news may already be priced in"
                    elif bull > bear and bull >= 2:
                        news_score = -3
                        news_reason = f"News leaning positive ({bull}/{total}) — some upside may be priced in"
                    else:
                        news_score = 0
                        news_reason = f"Mixed news ({bull} positive, {bear} negative)"
                else:
                    news_reason = "No recent news found"
            except Exception:
                news_reason = "Could not fetch news"

        # --- Combine scores ---
        reasons = []
        if rsi is not None:
            reasons.append(("RSI", rsi_score, rsi_reason))
        if ma_reason:
            reasons.append(("Moving Averages", ma_score, ma_reason))
        reasons.append(("52W Range Position", range_score, range_reason))
        reasons.append(("Momentum", momentum_score, momentum_reason))
        if vol_reason:
            reasons.append(("Volume", vol_score, vol_reason))
        if pe_reason:
            reasons.append(("PE Valuation", pe_score, pe_reason))
        if trend_reason:
            reasons.append(("Trend Consistency", trend_score, trend_reason))
        reasons.append(("News Sentiment", news_score, news_reason))

        total_score = sum(s for _, s, _ in reasons)

        # Signal determination
        if total_score >= 25:
            signal = "BUY"
        elif total_score >= 10:
            signal = "LEAN BUY"
        elif total_score <= -25:
            signal = "SELL"
        elif total_score <= -10:
            signal = "LEAN SELL"
        else:
            signal = "WAIT"

        # Confidence
        positive_factors = sum(1 for _, s, _ in reasons if s > 0)
        negative_factors = sum(1 for _, s, _ in reasons if s < 0)
        neutral_factors = sum(1 for _, s, _ in reasons if s == 0)
        total_factors = len(reasons)

        if signal in ("BUY", "LEAN BUY"):
            agreement = positive_factors / total_factors
            score_strength = min(abs(total_score) / 60, 1.0)
        elif signal in ("SELL", "LEAN SELL"):
            agreement = negative_factors / total_factors
            score_strength = min(abs(total_score) / 60, 1.0)
        else:
            agreement = (
                neutral_factors + min(positive_factors, negative_factors)
            ) / total_factors
            score_strength = 1.0 - min(abs(total_score) / 30, 1.0)

        confidence = max(
            15, min(95, round((agreement * 0.5 + score_strength * 0.5) * 100))
        )

        # Prediction text
        if signal == "BUY":
            prediction = f"{name} looks undervalued right now — most indicators suggest it's a good time to buy."
        elif signal == "LEAN BUY":
            prediction = f"{name} is slightly favourable — consider buying a small amount now and more if it dips."
        elif signal == "SELL":
            prediction = f"{name} looks overvalued — consider booking profits or at least setting a stop-loss."
        elif signal == "LEAN SELL":
            prediction = (
                f"{name} is slightly unfavourable — wait for a better entry point."
            )
        else:
            prediction = f"Mixed signals for {name} — hold your position and wait for clearer direction."

        return {
            "signal": signal,
            "confidence": confidence,
            "total_score": total_score,
            "reasons": reasons,
            "prediction": prediction,
            "current_price": round(current, 2),
            "rsi": rsi,
            "range_pct": round(range_pct, 1),
            "change_5d": round(change_5d, 2),
            "change_20d": round(change_20d, 2),
            "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
            "sector": sector_name,
            "name": name,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# SILVER PRICE TRACKING — same approach as gold
# ---------------------------------------------------------------------------


def get_silver_price():
    """Fetch silver price in INR per gram (international silver converted via USD/INR).
    Chennai silver ≈ international price + ~5% premium (GST + making).
    """
    try:
        silver = yf.Ticker("SI=F")  # Silver futures USD/troy oz
        usd_inr = yf.Ticker("USDINR=X")

        silver_data = silver.history(period="5d")
        fx_data = usd_inr.history(period="5d")

        if silver_data.empty or fx_data.empty:
            return None

        silver_usd = silver_data["Close"].iloc[-1]
        rate = fx_data["Close"].iloc[-1]

        # 1 troy ounce = 31.1035 grams
        silver_inr_per_gram = (silver_usd * rate) / 31.1035
        chennai_per_gram = silver_inr_per_gram * 1.05  # ~5% premium

        # Daily change
        change_pct = None
        if len(silver_data) >= 2 and len(fx_data) >= 2:
            prev_silver = silver_data["Close"].iloc[-2]
            prev_fx = fx_data["Close"].iloc[-2]
            prev_per_gram = (prev_silver * prev_fx) / 31.1035 * 1.05
            change_pct = round(
                ((chennai_per_gram - prev_per_gram) / prev_per_gram) * 100, 2
            )

        return {
            "per_gram": round(chennai_per_gram, 2),
            "per_100gram": round(chennai_per_gram * 100, 2),
            "per_kg": round(chennai_per_gram * 1000, 2),
            "change_pct": change_pct,
        }
    except Exception:
        return None


def analyze_silver_trend():
    """Analyze silver price trend over multiple timeframes."""
    try:
        silver = yf.Ticker("SI=F")
        usd_inr = yf.Ticker("USDINR=X")

        silver_hist = silver.history(period="3mo")
        fx_hist = usd_inr.history(period="3mo")

        if silver_hist.empty or fx_hist.empty:
            return None

        inr_per_gram = _gold_inr_series(silver_hist, fx_hist, premium=1.05)
        if inr_per_gram is None or len(inr_per_gram) < 5:
            return None

        current = inr_per_gram.iloc[-1]
        week_ago = (
            inr_per_gram.iloc[-6] if len(inr_per_gram) >= 6 else inr_per_gram.iloc[0]
        )
        month_ago = (
            inr_per_gram.iloc[-23] if len(inr_per_gram) >= 23 else inr_per_gram.iloc[0]
        )

        return {
            "weekly_change": round(((current - week_ago) / week_ago) * 100, 2),
            "monthly_change": round(((current - month_ago) / month_ago) * 100, 2),
            "high_3m": round(inr_per_gram.max(), 2),
            "low_3m": round(inr_per_gram.min(), 2),
        }
    except Exception:
        return None


def predict_silver_buy(use_news=True):
    """Analyze silver price data and predict if it's a good time to buy.

    Uses same 7-factor approach as gold: RSI, MAs, range, momentum,
    volatility, trend consistency, news.
    """
    try:
        silver = yf.Ticker("SI=F")
        usd_inr = yf.Ticker("USDINR=X")

        silver_hist = silver.history(period="6mo")
        fx_hist = usd_inr.history(period="6mo")

        if silver_hist.empty or fx_hist.empty:
            return None

        inr_per_gram = _gold_inr_series(silver_hist, fx_hist, premium=1.05)
        if inr_per_gram is None or len(inr_per_gram) < 30:
            return None

        prices = inr_per_gram.values
        current = prices[-1]

        # --- Factor 1: RSI ---
        rsi = compute_rsi(prices)
        rsi_score = 0
        rsi_reason = ""
        if rsi is not None:
            if rsi <= 25:
                rsi_score = 30
                rsi_reason = (
                    f"RSI is {rsi:.0f} — silver is deeply oversold, strong buying zone"
                )
            elif rsi <= 35:
                rsi_score = 20
                rsi_reason = f"RSI is {rsi:.0f} — oversold territory, good entry point"
            elif rsi <= 45:
                rsi_score = 8
                rsi_reason = f"RSI is {rsi:.0f} — leaning towards cheap"
            elif rsi <= 55:
                rsi_score = 0
                rsi_reason = f"RSI is {rsi:.0f} — neutral zone"
            elif rsi <= 65:
                rsi_score = -8
                rsi_reason = f"RSI is {rsi:.0f} — leaning towards expensive"
            elif rsi <= 75:
                rsi_score = -20
                rsi_reason = f"RSI is {rsi:.0f} — getting overbought"
            else:
                rsi_score = -30
                rsi_reason = f"RSI is {rsi:.0f} — heavily overbought"

        # --- Factor 2: Moving averages ---
        ma10 = np.mean(prices[-10:]) if len(prices) >= 10 else None
        ma20 = np.mean(prices[-20:]) if len(prices) >= 20 else None
        ma50 = np.mean(prices[-50:]) if len(prices) >= 50 else None
        ma_score = 0
        ma_reason = ""
        if ma20 and ma50:
            pct_from_ma20 = ((current - ma20) / ma20) * 100
            if current < ma20 and current < ma50:
                ma_score = 20
                ma_reason = f"Price is {abs(pct_from_ma20):.1f}% below 20-day avg — dip buying zone"
            elif current < ma20:
                ma_score = 10
                ma_reason = f"Price is {abs(pct_from_ma20):.1f}% below 20-day avg — short-term dip"
            elif current > ma20 and current > ma50 and ma20 > ma50:
                if pct_from_ma20 > 5:
                    ma_score = -15
                    ma_reason = (
                        f"Price is {pct_from_ma20:.1f}% above 20-day avg — stretched"
                    )
                else:
                    ma_score = -8
                    ma_reason = "Price above both averages — slightly expensive"
            elif ma10 and ma10 < ma20:
                ma_score = 8
                ma_reason = (
                    "Short-term avg crossing below medium-term — possible dip forming"
                )
            else:
                ma_score = 0
                ma_reason = "Price is near moving averages — no clear trend"

        # --- Factor 3: 3-month range position ---
        high_3m = prices[-66:].max() if len(prices) >= 66 else prices.max()
        low_3m = prices[-66:].min() if len(prices) >= 66 else prices.min()
        range_pct = (
            ((current - low_3m) / (high_3m - low_3m)) * 100 if high_3m != low_3m else 50
        )
        range_score = 0
        if range_pct <= 15:
            range_score = 25
            range_reason = (
                f"Near 3-month low (bottom {range_pct:.0f}%) — strong buying level"
            )
        elif range_pct <= 30:
            range_score = 15
            range_reason = f"Lower third of range ({range_pct:.0f}%) — good value"
        elif range_pct <= 45:
            range_score = 5
            range_reason = f"Lower-mid range ({range_pct:.0f}%) — slightly cheap"
        elif range_pct <= 55:
            range_score = 0
            range_reason = f"Mid-range ({range_pct:.0f}%) — fair value"
        elif range_pct <= 70:
            range_score = -5
            range_reason = f"Upper-mid range ({range_pct:.0f}%) — slightly expensive"
        elif range_pct <= 85:
            range_score = -15
            range_reason = f"Upper third ({range_pct:.0f}%) — expensive"
        else:
            range_score = -25
            range_reason = f"Near 3-month high (top {100 - range_pct:.0f}%) — risky"

        # --- Factor 4: Momentum ---
        change_5d = (
            ((current - prices[-6]) / prices[-6]) * 100 if len(prices) >= 6 else 0
        )
        change_20d = (
            ((current - prices[-21]) / prices[-21]) * 100 if len(prices) >= 21 else 0
        )
        momentum_score = 0
        if change_5d < -3 and change_20d < -5:
            momentum_score = 20
            momentum_reason = f"Silver fell {change_5d:.1f}% in 5d, {change_20d:.1f}% in 20d — sharp correction"
        elif change_5d < -2:
            momentum_score = 12
            momentum_reason = (
                f"Silver fell {change_5d:.1f}% in 5 days — decent pullback"
            )
        elif change_5d < -1:
            momentum_score = 5
            momentum_reason = (
                f"Silver dipped {change_5d:.1f}% in 5 days — minor pullback"
            )
        elif change_5d > 4:
            momentum_score = -20
            momentum_reason = (
                f"Silver surged {change_5d:+.1f}% in 5 days — very overheated"
            )
        elif change_5d > 2:
            momentum_score = -12
            momentum_reason = f"Silver rose {change_5d:+.1f}% in 5 days — overheated"
        elif change_5d > 1:
            momentum_score = -5
            momentum_reason = f"Silver rose {change_5d:+.1f}% in 5 days — mild uptrend"
        else:
            if change_20d < -3:
                momentum_score = 8
                momentum_reason = f"Stable this week but down {change_20d:.1f}% over 20 days — broader dip"
            elif change_20d > 5:
                momentum_score = -8
                momentum_reason = f"Stable this week but up {change_20d:+.1f}% over 20 days — extended rally"
            else:
                momentum_score = 0
                momentum_reason = f"Silver moved {change_5d:+.1f}% in 5d — sideways"

        # --- Factor 5: Volatility ---
        vol_score = 0
        vol_reason = ""
        if len(prices) >= 11:
            daily_returns = np.diff(prices[-11:]) / prices[-11:-1] * 100
            volatility = np.std(daily_returns)
            avg_vol = (
                np.std(np.diff(prices[-60:]) / prices[-60:-1] * 100)
                if len(prices) >= 60
                else volatility
            )
            if volatility > avg_vol * 1.5:
                vol_score = -8
                vol_reason = f"Very choppy ({volatility:.2f}% vs avg {avg_vol:.2f}%) — risky entry"
            elif volatility < avg_vol * 0.7:
                vol_score = 5
                vol_reason = f"Calm market ({volatility:.2f}% vs avg {avg_vol:.2f}%) — stable entry"
            else:
                vol_score = 0
                vol_reason = f"Normal volatility ({volatility:.2f}%)"

        # --- Factor 6: Trend consistency ---
        trend_score = 0
        trend_reason = ""
        if len(prices) >= 11:
            last_10 = prices[-10:]
            up_days = sum(
                1 for i in range(1, len(last_10)) if last_10[i] > last_10[i - 1]
            )
            down_days = 9 - up_days
            if down_days >= 7:
                trend_score = 12
                trend_reason = f"{down_days}/9 recent days down — sustained selling, could be near bottom"
            elif down_days >= 6:
                trend_score = 6
                trend_reason = f"{down_days}/9 recent days down — consistent weakness"
            elif up_days >= 7:
                trend_score = -12
                trend_reason = f"{up_days}/9 recent days up — may be overextended"
            elif up_days >= 6:
                trend_score = -6
                trend_reason = f"{up_days}/9 recent days up — consistent strength"
            else:
                trend_score = 0
                trend_reason = f"Mixed recent days ({up_days} up, {down_days} down)"

        # --- Factor 7: News ---
        news_score = 0
        news_reason = "News not analyzed"
        if use_news:
            try:
                silver_news = fetch_news("Silver Price India", max_items=8)
                if silver_news:
                    bull = sum(1 for n in silver_news if n["sentiment"] == "bullish")
                    bear = sum(1 for n in silver_news if n["sentiment"] == "bearish")
                    total = len(silver_news)
                    if bear > bull and bear >= 4:
                        news_score = 12
                        news_reason = f"News is heavily negative ({bear}/{total}) — fear creates opportunities"
                    elif bear > bull and bear >= 2:
                        news_score = 6
                        news_reason = f"News leaning negative ({bear}/{total}) — possible dip opportunity"
                    elif bull > bear and bull >= 4:
                        news_score = -8
                        news_reason = f"News very positive ({bull}/{total}) — rally may be priced in"
                    elif bull > bear and bull >= 2:
                        news_score = -4
                        news_reason = f"News leaning positive ({bull}/{total}) — some upside priced in"
                    else:
                        news_score = 0
                        news_reason = f"Mixed news ({bull} positive, {bear} negative)"
            except Exception:
                news_reason = "Could not fetch silver news"

        # --- Combine ---
        reasons = []
        if rsi is not None:
            reasons.append(("RSI", rsi_score, rsi_reason))
        if ma_reason:
            reasons.append(("Moving Averages", ma_score, ma_reason))
        reasons.append(("3M Range Position", range_score, range_reason))
        reasons.append(("Momentum", momentum_score, momentum_reason))
        if vol_reason:
            reasons.append(("Volatility", vol_score, vol_reason))
        if trend_reason:
            reasons.append(("Trend Consistency", trend_score, trend_reason))
        reasons.append(("News Sentiment", news_score, news_reason))

        total_score = sum(s for _, s, _ in reasons)

        if total_score >= 25:
            signal = "BUY"
        elif total_score >= 10:
            signal = "LEAN BUY"
        elif total_score <= -25:
            signal = "SELL"
        elif total_score <= -10:
            signal = "LEAN SELL"
        else:
            signal = "WAIT"

        positive_factors = sum(1 for _, s, _ in reasons if s > 0)
        negative_factors = sum(1 for _, s, _ in reasons if s < 0)
        neutral_factors = sum(1 for _, s, _ in reasons if s == 0)
        total_factors = len(reasons)

        if signal in ("BUY", "LEAN BUY"):
            agreement = positive_factors / total_factors
            score_strength = min(abs(total_score) / 50, 1.0)
        elif signal in ("SELL", "LEAN SELL"):
            agreement = negative_factors / total_factors
            score_strength = min(abs(total_score) / 50, 1.0)
        else:
            agreement = (
                neutral_factors + min(positive_factors, negative_factors)
            ) / total_factors
            score_strength = 1.0 - min(abs(total_score) / 30, 1.0)

        confidence = max(
            15, min(95, round((agreement * 0.5 + score_strength * 0.5) * 100))
        )

        if signal == "BUY":
            prediction = (
                f"Silver dropped {change_5d:.1f}% recently — expect a bounce in the next 5-7 days."
                if change_5d < -2
                else "Conditions favour buying — silver likely to hold or rise this week."
            )
        elif signal == "LEAN BUY":
            prediction = "Slightly favourable — consider buying a small amount now."
        elif signal == "SELL":
            prediction = (
                f"Silver surged {change_5d:+.1f}% recently — expect a pullback."
                if change_5d > 3
                else "Most indicators say silver is expensive — wait."
            )
        elif signal == "LEAN SELL":
            prediction = "Conditions lean against buying — wait a few days for a dip."
        else:
            prediction = "Mixed signals — hold off and check again in a few days."

        return {
            "signal": signal,
            "confidence": confidence,
            "total_score": total_score,
            "reasons": reasons,
            "prediction": prediction,
            "current_price": round(current, 2),
            "rsi": rsi,
            "range_pct": round(range_pct, 1),
            "change_5d": round(change_5d, 2),
            "change_20d": round(change_20d, 2),
        }
    except Exception:
        return None


def save_silver_prediction(prediction):
    """Log a silver prediction to data/silver_predictions.json."""
    import os

    log_path = os.path.join(
        os.path.dirname(__file__), "data", "silver_predictions.json"
    )
    predictions = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                predictions = json.load(f)
        except (json.JSONDecodeError, OSError):
            predictions = []

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "signal": prediction["signal"],
        "confidence": prediction["confidence"],
        "price_at_prediction": prediction["current_price"],
        "total_score": prediction["total_score"],
        "prediction_text": prediction["prediction"],
        "factor_scores": [
            {"name": name, "score": score, "reason": reason}
            for name, score, reason in prediction["reasons"]
        ],
        "verified": False,
        "actual_price_after": None,
        "was_correct": None,
    }

    today = entry["date"]
    predictions = [p for p in predictions if p["date"] != today]
    predictions.append(entry)

    with open(log_path, "w") as f:
        json.dump(predictions, f, indent=2)

    return entry


def verify_silver_predictions():
    """Check past silver predictions against actual prices."""
    import os

    log_path = os.path.join(
        os.path.dirname(__file__), "data", "silver_predictions.json"
    )
    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    try:
        silver = yf.Ticker("SI=F")
        usd_inr = yf.Ticker("USDINR=X")
        silver_hist = silver.history(period="1mo")
        fx_hist = usd_inr.history(period="1mo")
        if silver_hist.empty or fx_hist.empty:
            return predictions
        inr_per_gram = _gold_inr_series(silver_hist, fx_hist, premium=1.05)
        current_price = (
            round(inr_per_gram.iloc[-1], 2)
            if inr_per_gram is not None and len(inr_per_gram) > 0
            else None
        )
    except Exception:
        return predictions

    if current_price is None:
        return predictions

    updated = False
    today = datetime.now()
    for p in predictions:
        if p.get("verified"):
            continue
        pred_date = datetime.strptime(p["date"], "%Y-%m-%d")
        if (today - pred_date).days < 5:
            continue

        p["actual_price_after"] = current_price
        p["verified"] = True
        price_change_pct = (
            (current_price - p["price_at_prediction"]) / p["price_at_prediction"]
        ) * 100

        if p["signal"] in ("BUY", "LEAN BUY"):
            p["was_correct"] = price_change_pct > 0
        elif p["signal"] in ("SELL", "LEAN SELL"):
            p["was_correct"] = price_change_pct < 0
        else:
            p["was_correct"] = abs(price_change_pct) < 2

        p["actual_change_pct"] = round(price_change_pct, 2)
        updated = True

    if updated:
        with open(log_path, "w") as f:
            json.dump(predictions, f, indent=2)

    return predictions


# ---------------------------------------------------------------------------
# MUTUAL FUND NAV TRACKING — AMFI India API (free, no key)
# ---------------------------------------------------------------------------

AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"


def fetch_mf_nav_batch(scheme_codes):
    """Fetch NAVs for multiple schemes in one download."""
    results = {}
    try:
        req = urllib.request.Request(
            AMFI_NAV_URL, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        code_set = set(str(c) for c in scheme_codes)
        for line in content.splitlines():
            parts = line.strip().split(";")
            if len(parts) >= 5 and parts[0].strip() in code_set:
                code = parts[0].strip()
                results[code] = {
                    "scheme_code": code,
                    "scheme_name": parts[3].strip(),
                    "nav": float(parts[4].strip()),
                    "date": parts[5].strip() if len(parts) > 5 else "",
                }
    except Exception:
        pass
    return results


def load_portfolio_extended(path="data/portfolio.csv"):
    """Load portfolio with optional ticker, SIP, and amfi_code columns."""
    holdings = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                holdings.append(
                    {
                        "name": row["name"],
                        "ticker": row.get("ticker", "").strip(),
                        "amount": float(row["amount"]),
                        "type": row["type"],
                        "sip_monthly": float(row.get("sip_monthly", 0) or 0),
                        "sip_date": int(row.get("sip_date", 0) or 0),
                        "amfi_code": row.get("amfi_code", "").strip(),
                    }
                )
    except FileNotFoundError:
        pass
    return holdings


# ---------------------------------------------------------------------------
# PORTFOLIO DIVERSIFICATION SCORE
# ---------------------------------------------------------------------------


def compute_diversification(holdings, analysis_results=None):
    """Compute portfolio diversification metrics and warnings.

    Returns dict with:
      - type_allocation: {type: percentage}
      - sector_allocation: {sector: percentage} (for stocks with analysis data)
      - hhi: Herfindahl-Hirschman Index (0-10000, lower = more diverse)
      - score: 0-100 (higher = better diversified)
      - warnings: list of warning strings
    """
    if not holdings:
        return None

    total = sum(h["amount"] for h in holdings)
    if total <= 0:
        return None

    # --- Type allocation ---
    type_alloc = {}
    for h in holdings:
        t = h["type"]
        type_alloc[t] = type_alloc.get(t, 0) + h["amount"]
    type_pct = {k: round((v / total) * 100, 1) for k, v in type_alloc.items()}

    # --- Sector allocation (from analysis results) ---
    sector_alloc = {}
    if analysis_results:
        for r in analysis_results:
            a = r.get("analysis")
            h = r["holding"]
            if a and a.get("sector"):
                sector_alloc[a["sector"]] = (
                    sector_alloc.get(a["sector"], 0) + h["amount"]
                )
    sector_pct = {k: round((v / total) * 100, 1) for k, v in sector_alloc.items()}

    # --- Individual holding concentration ---
    holding_pcts = [
        (h["name"], round((h["amount"] / total) * 100, 1)) for h in holdings
    ]

    # --- HHI (using individual holding weights) ---
    weights = [(h["amount"] / total) * 100 for h in holdings]
    hhi = round(sum(w**2 for w in weights), 0)

    # --- Score: 0-100, lower HHI = better ---
    # HHI ranges: 10000 (one holding) to ~100/n (perfectly equal)
    n = len(holdings)
    min_hhi = 10000 / n if n > 0 else 10000
    score = max(0, min(100, round(100 * (1 - (hhi - min_hhi) / (10000 - min_hhi)), 0)))

    # --- Warnings (each is a tuple: (warning_text, fix_text)) ---
    warnings = []

    # Find under-represented sectors for suggestions
    all_known_sectors = {
        "Technology",
        "Financial Services",
        "Healthcare",
        "Consumer Defensive",
        "Energy",
        "Industrials",
        "Basic Materials",
        "Communication Services",
        "Consumer Cyclical",
        "Utilities",
        "Real Estate",
    }
    present_sectors = set(sector_pct.keys())
    missing_sectors = all_known_sectors - present_sectors
    suggest_sectors = (
        sorted(missing_sectors)[:3] if missing_sectors else ["IT", "Healthcare", "FMCG"]
    )

    for name, pct in holding_pcts:
        amt = next((h["amount"] for h in holdings if h["name"] == name), 0)
        if pct > 40:
            sell_amt = round(amt * (pct - 20) / pct)
            warnings.append(
                (
                    f"🔴 {name} is {pct}% of portfolio — extremely concentrated!",
                    f"Sell ~₹{sell_amt:,} of {name} to bring it down to ~20%. "
                    f"Spread that amount across 2-3 holdings in different sectors "
                    f"like {', '.join(suggest_sectors[:2])}. "
                    f"Or start a ₹{round(sell_amt / 3, -2):,.0f}/month SIP in a Nifty 50 index fund.",
                )
            )
        elif pct > 25:
            sell_amt = round(amt * (pct - 15) / pct)
            warnings.append(
                (
                    f"⚠️ {name} is {pct}% of portfolio — consider rebalancing",
                    f"Reduce {name} by ~₹{sell_amt:,} to bring it to ~15%. "
                    f"Consider moving that into sectors you don't own yet: "
                    f"{', '.join(suggest_sectors[:3])}.",
                )
            )

    for sector, pct in sector_pct.items():
        if pct > 50:
            warnings.append(
                (
                    f"🔴 {sector} sector is {pct}% — very concentrated!",
                    f"You have too much in {sector}. "
                    f"Add stocks or funds from other sectors like {', '.join(suggest_sectors[:3])} "
                    f"to reduce this below 30%.",
                )
            )
        elif pct > 35:
            warnings.append(
                (
                    f"⚠️ {sector} sector is {pct}% — consider diversifying",
                    f"Your {sector} exposure is high. "
                    f"Next time you invest, pick from sectors like {', '.join(suggest_sectors[:2])} instead.",
                )
            )

    if len(holdings) < 5:
        warnings.append(
            (
                "💡 Only {0} holdings — consider adding more for diversification".format(
                    len(holdings)
                ),
                f"Aim for 10-15 holdings across different sectors. "
                f"Consider adding stocks from {', '.join(suggest_sectors[:3])} "
                f"or a diversified mutual fund.",
            )
        )

    if "mutual_fund" not in type_alloc and "stock" in type_alloc:
        warnings.append(
            (
                "💡 No mutual funds — consider adding index funds for stability",
                "Start a monthly SIP in a Nifty 50 index fund (e.g. UTI Nifty 50) "
                "for ₹500-1,000/month. Index funds give broad market exposure with low fees.",
            )
        )

    stock_pct = type_pct.get("stock", 0)
    if stock_pct > 80:
        warnings.append(
            (
                "⚠️ {0}% in direct stocks — high risk, consider adding MFs or debt".format(
                    stock_pct
                ),
                f"Move 20-30% of your portfolio to mutual funds or fixed deposits. "
                f"A Nifty 50 SIP or a balanced advantage fund can reduce your risk.",
            )
        )

    return {
        "type_pct": type_pct,
        "sector_pct": sector_pct,
        "holding_pcts": holding_pcts,
        "hhi": hhi,
        "score": score,
        "warnings": warnings,
    }
