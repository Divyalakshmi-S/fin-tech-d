import streamlit as st


def render(holdings):
    st.title("📚 Stock Market Learning Hub")
    st.caption(
        "Concepts from Zerodha Varsity — the best free resource for Indian investors"
    )

    learn_tabs = st.tabs(
        [
            "📈 Technical Analysis",
            "📊 Fundamentals",
            "🛡️ Risk Management",
            "📖 Varsity Roadmap",
            "📗 Financial Glossary",
        ]
    )

    with learn_tabs[0]:
        st.subheader("📈 Technical Analysis")
        st.markdown(
            """
**Technical analysis** studies price patterns and indicators to predict future movement.
Your dashboard uses these indicators on every stock:
"""
        )
        st.markdown(
            """
#### RSI (Relative Strength Index)
- Measures if a stock is **overbought (>70)** or **oversold (<30)**
- RSI 50 = neutral, below 30 = potential buy, above 70 = potential sell
- **Your dashboard:** Shows RSI in Holdings Analysis → Momentum column

#### MACD (Moving Average Convergence Divergence)
- **MACD Line** = EMA(12) - EMA(26) — shows momentum direction
- **Signal Line** = EMA(9) of MACD — confirms trend
- **Bullish crossover**: MACD crosses above Signal → buying momentum
- **Bearish crossover**: MACD crosses below Signal → selling pressure
- **Your dashboard:** Shows in each stock's "Technical Indicators" section

#### Bollinger Bands
- **Upper Band** = SMA(20) + 2σ, **Lower Band** = SMA(20) - 2σ
- Price near upper band → expensive, near lower band → cheap
- **%B**: 0 = at lower band, 1 = at upper band
- Bands **squeezing** (getting narrow) → big move coming
- **Your dashboard:** Shown on price charts + Technical Indicators

#### Moving Average Crossovers
- **Golden Cross**: SMA50 crosses above SMA200 → long-term bullish
- **Death Cross**: SMA50 crosses below SMA200 → long-term bearish
- **Your dashboard:** Auto-detected and alerted in Holdings Analysis

#### Candlestick Patterns
| Pattern | Signal | What It Means |
|---|---|---|
| **Doji** | ⚪ Neutral | Indecision — trend may reverse |
| **Hammer** | 🟢 Bullish | Buyers stepped in at lows |
| **Shooting Star** | 🔴 Bearish | Sellers rejected highs |
| **Bullish Engulfing** | 🟢 Bullish | Strong buying overwhelmed selling |
| **Bearish Engulfing** | 🔴 Bearish | Strong selling overwhelmed buying |
| **Morning Star** | 🟢 Bullish | 3-candle reversal — dawn after darkness |
| **Evening Star** | 🔴 Bearish | 3-candle reversal — sunset after rally |
"""
        )
        st.info(
            "💡 **Rule:** Never rely on a single indicator. Look for **confluence** — multiple indicators agreeing."
        )

    with learn_tabs[1]:
        st.subheader("📊 Fundamental Analysis")
        st.markdown(
            """
**Fundamental analysis** evaluates a company's financial health to determine its true value.

#### Key Ratios
| Ratio | What It Tells You | Good | Bad |
|---|---|---|---|
| **P/E Ratio** | How much you pay per ₹1 of earnings | < 15 (cheap) | > 40 (expensive) |
| **P/B Ratio** | Price vs book value (assets - liabilities) | < 1 (below assets) | > 5 (premium) |
| **ROE** | Profit generated per ₹100 of equity | > 20% (excellent) | < 10% (poor) |
| **Debt/Equity** | How much debt vs equity | < 50% (safe) | > 150% (risky) |
| **Dividend Yield** | Annual dividend as % of price | > 2% (good income) | 0% (growth stock) |
| **EPS Growth** | Earnings per share year-over-year | Growing (good) | Shrinking (bad) |
| **Profit Margin** | % of revenue that's profit | > 15% (strong) | < 5% (tight) |

#### How to Read a Balance Sheet
1. **Revenue** → Is it growing year-over-year?
2. **Net Profit** → Is the company actually making money?
3. **Debt** → Can the company survive a downturn?
4. **Cash Flow** → Is real cash coming in, or just accounting profit?
5. **Promoter Holding** → Are insiders buying or selling?

#### Valuation Methods
- **DCF (Discounted Cash Flow)**: Present value of all future cash flows
- **Comparative**: Compare P/E, P/B with industry peers
- **Margin of Safety**: Only buy when price is 25%+ below estimated fair value
"""
        )
        st.info(
            "💡 **Benjamin Graham's rule:** The stock market is a voting machine in the short run but a weighing machine in the long run."
        )

    with learn_tabs[2]:
        st.subheader("🛡️ Risk Management")
        st.markdown(
            """
**Risk management** is more important than picking the right stock.

#### The 3 Rules
1. **Never risk more than 1-2% of capital per trade**
2. **Always set a stop-loss before entering**
3. **Risk-reward ratio should be at least 1:2**

#### Stop-Loss Methods
| Method | How It Works | When to Use |
|---|---|---|
| **ATR Stop** | Stop = Price - 2×ATR | Best for volatile stocks |
| **% Stop** | Stop = Price × 95% | Simple, works everywhere |
| **Support Stop** | Stop below nearest support level | For chart readers |
| **Trailing Stop** | Moves up as price rises, locks profit | For riding trends |

#### Position Sizing Formula
```
Shares to buy = (Capital × Risk%) ÷ (Entry Price - Stop Loss)
```
**Example:** ₹5,00,000 capital, 2% risk, stock at ₹100, stop at ₹95
→ Risk amount = ₹10,000 → Risk per share = ₹5 → Buy 2,000 shares (₹2,00,000)

#### ATR (Average True Range)
- Measures average daily price movement
- Higher ATR = more volatile = wider stop-loss needed
- **Your dashboard:** Shows ATR-based stop-loss and targets for every stock

#### Risk-Reward Targets
- **Target 1 (1:1)**: Price + 1× risk — conservative
- **Target 2 (1:2)**: Price + 2× risk — standard
- **Target 3 (1:3)**: Price + 3× risk — aggressive
"""
        )
        st.info(
            "💡 **Key insight:** A trader who wins 40% of trades but has 1:3 risk-reward is profitable. Win rate alone doesn't matter."
        )

    with learn_tabs[3]:
        st.subheader("📖 Zerodha Varsity — Complete Roadmap")
        st.markdown(
            """
**[Zerodha Varsity](https://zerodha.com/varsity/)** is India's best free stock market education.
All content is free — available on web and mobile app.

#### Recommended Learning Order

| # | Module | What You'll Learn | Your Dashboard Feature |
|---|---|---|---|
| 1 | **Introduction to Stock Markets** | How markets work, IPOs, indices | Overview page |
| 2 | **Technical Analysis** | Charts, RSI, MACD, candlesticks | Holdings Analysis → Technical Indicators |
| 3 | **Fundamental Analysis** | Balance sheets, P/E, ROE, valuations | Holdings Analysis → Fundamentals |
| 4 | **Futures Trading** | Derivatives, margin, hedging | — |
| 5 | **Options Theory** | Calls, puts, Greeks | — |
| 6 | **Option Strategies** | Spreads, strangles, iron condor | — |
| 7 | **Markets & Taxation** | STT, capital gains, ITR filing | — |
| 8 | **Currency & Commodity** | Gold, silver, crude oil | Gold & Silver page |
| 9 | **Risk Management** | Position sizing, stop losses | Holdings Analysis → Risk Management |
| 10 | **Trading Systems** | Backtesting strategies | Gold/Silver backtest |
| 11 | **Personal Finance** | MFs, insurance, goal planning | Goals page + SIP recommendations |

#### Start Here
1. Read **Module 1** (2-3 hours) — understand the basics
2. Read **Module 11** (personal finance) — most relevant for SIP investors
3. Then **Module 2** (technical) + **Module 3** (fundamental) — to understand your dashboard
4. **Module 9** (risk management) — before making any active trades
"""
        )
        st.markdown(
            """
#### Other Quality Resources
- **[Varsity App](https://play.google.com/store/apps/details?id=com.zerodha.varsity)** — Read offline on your phone
- **[MoneyControl](https://www.moneycontrol.com)** — News, charts, MF data
- **[Screener.in](https://www.screener.in)** — Fundamental screening
- **[Tijori Finance](https://www.tijorifinance.com)** — Visual financial data
- **[NSE India](https://www.nseindia.com)** — Official exchange data
"""
        )

    with learn_tabs[4]:
        st.subheader("📗 Financial Glossary")
        st.caption("Quick reference for financial terms used across this dashboard")

        glossary_search = st.text_input(
            "🔍 Search glossary", placeholder="Type a term...", key="glossary_search"
        )

        glossary = [
            (
                "CAGR",
                "Compound Annual Growth Rate — the average annual return of an investment over a period, smoothing out volatility.",
            ),
            (
                "XIRR",
                "Extended Internal Rate of Return — calculates annualized returns for irregular cash flows like SIPs or multiple investments.",
            ),
            (
                "SIP",
                "Systematic Investment Plan — investing a fixed amount regularly (monthly) into mutual funds. Averages out market volatility.",
            ),
            (
                "NAV",
                "Net Asset Value — the per-unit price of a mutual fund. Calculated daily as (Total Assets - Liabilities) ÷ Number of Units.",
            ),
            (
                "RSI",
                "Relative Strength Index — momentum indicator (0-100). Below 30 = oversold (cheap), above 70 = overbought (expensive).",
            ),
            (
                "MACD",
                "Moving Average Convergence Divergence — trend-following momentum indicator. Bullish when MACD crosses above signal line.",
            ),
            (
                "PE Ratio",
                "Price-to-Earnings Ratio — stock price divided by earnings per share. Lower PE = cheaper valuation (relative).",
            ),
            (
                "EPS",
                "Earnings Per Share — company's net profit divided by number of shares. Higher EPS = more profitable.",
            ),
            (
                "LTCG",
                "Long-Term Capital Gains — profits from selling assets held for more than 1 year (equity). Taxed at 10% above ₹1.25L.",
            ),
            (
                "STCG",
                "Short-Term Capital Gains — profits from selling equity held less than 1 year. Taxed at 15%.",
            ),
            (
                "Alpha",
                "Returns above the benchmark (e.g., Nifty 50). Positive alpha = you beat the market.",
            ),
            (
                "Beta",
                "Measure of volatility relative to the market. Beta > 1 = more volatile than market, < 1 = less volatile.",
            ),
            (
                "Sharpe Ratio",
                "Risk-adjusted return. (Return - Risk-free rate) ÷ Standard Deviation. Higher = better risk-adjusted performance.",
            ),
            (
                "ELSS",
                "Equity Linked Savings Scheme — tax-saving mutual fund with 3-year lock-in. Qualifies for Section 80C deduction.",
            ),
            (
                "Section 80C",
                "Income tax deduction up to ₹1,50,000/year for investments in PPF, ELSS, EPF, LIC, NSC, etc.",
            ),
            (
                "Section 80D",
                "Income tax deduction for health insurance premiums — ₹25,000 self + ₹50,000 parents (senior citizen).",
            ),
            (
                "NPS",
                "National Pension System — government retirement scheme. Extra ₹50,000 deduction under 80CCD(1B).",
            ),
            (
                "PPF",
                "Public Provident Fund — government savings scheme at 7.1% with 15-year lock-in. Tax-free returns.",
            ),
            (
                "HRA",
                "House Rent Allowance — salary component partially exempt from tax if you pay rent.",
            ),
            (
                "ATR",
                "Average True Range — measures average daily price movement volatility. Used to set stop-loss levels.",
            ),
            (
                "Stop Loss",
                "Pre-set price at which you sell to limit losses. Typically 2× ATR below entry price.",
            ),
            (
                "Golden Cross",
                "50-day moving average crosses above 200-day — bullish long-term signal.",
            ),
            (
                "Death Cross",
                "50-day moving average crosses below 200-day — bearish long-term signal.",
            ),
            (
                "Bollinger Bands",
                "Volatility bands at 2 standard deviations above/below 20-day SMA. Squeeze = big move coming.",
            ),
            (
                "FIRE",
                "Financial Independence, Retire Early — having 25× annual expenses invested (4% withdrawal rule).",
            ),
            (
                "Asset Allocation",
                "Spreading investments across asset classes (equity, debt, gold, real estate) to manage risk.",
            ),
            (
                "Rebalancing",
                "Periodically adjusting portfolio back to target allocation percentages.",
            ),
            (
                "Diversification",
                "Spreading investments across different stocks/sectors/assets to reduce risk.",
            ),
            (
                "AUM",
                "Assets Under Management — total market value of investments managed by a fund.",
            ),
            (
                "Expense Ratio",
                "Annual fee charged by mutual funds as % of AUM. Direct plans have lower expense ratios.",
            ),
            (
                "NFO",
                "New Fund Offer — initial offering of a new mutual fund scheme. Similar to IPO for stocks.",
            ),
        ]

        # Filter by search
        if glossary_search:
            filtered = [
                (t, d)
                for t, d in glossary
                if glossary_search.lower() in t.lower()
                or glossary_search.lower() in d.lower()
            ]
        else:
            filtered = glossary

        if filtered:
            for term, definition in filtered:
                st.markdown(
                    f"""<div style="border-left: 3px solid #3498db; padding: 8px 14px; margin: 6px 0;
                    border-radius: 4px; background: #3498db08;">
                    <strong>{term}</strong> — {definition}
                    </div>""",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No matching terms found. Try a different search.")
