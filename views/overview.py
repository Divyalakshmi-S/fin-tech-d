import streamlit as st
import yfinance as yf

from analysis import analyze_portfolio


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_index_data(ticker_symbol):
    """Cached index data fetch — avoids re-downloading on every rerun."""
    try:
        data = yf.Ticker(ticker_symbol).history(period="1mo")
        return data
    except Exception:
        return None


def render(holdings):
    st.title("🏠 Market Overview")

    # Nifty + Sensex side by side
    col1, col2 = st.columns(2)

    with col1:
        nifty_data = _fetch_index_data("^NSEI")
        if nifty_data is not None and not nifty_data.empty and len(nifty_data) >= 2:
            current = round(nifty_data["Close"].iloc[-1], 2)
            prev = round(nifty_data["Close"].iloc[-2], 2)
            change = round(current - prev, 2)
            pct = round((change / prev) * 100, 2)
            st.metric("Nifty 50", f"₹{current:,.2f}", f"{change:+,.2f} ({pct:+.2f}%)")
            chart_series = nifty_data["Close"].copy()
            chart_series.index = chart_series.index.tz_localize(None)
            st.line_chart(chart_series, height=200)
        else:
            st.warning("Nifty data unavailable")

    with col2:
        sensex_data = _fetch_index_data("^BSESN")
        if sensex_data is not None and not sensex_data.empty and len(sensex_data) >= 2:
            current = round(sensex_data["Close"].iloc[-1], 2)
            prev = round(sensex_data["Close"].iloc[-2], 2)
            change = round(current - prev, 2)
            pct = round((change / prev) * 100, 2)
            st.metric("Sensex", f"₹{current:,.2f}", f"{change:+,.2f} ({pct:+.2f}%)")
            chart_series = sensex_data["Close"].copy()
            chart_series.index = chart_series.index.tz_localize(None)
            st.line_chart(chart_series, height=200)
        else:
            st.warning("Sensex data unavailable")

    st.divider()

    # Quick alerts
    if holdings:
        _alerts_fragment(holdings)


@st.fragment()
def _alerts_fragment(holdings):
    """Fragment — alerts re-run independently without re-fetching index data."""
    with st.spinner("Analyzing holdings..."):
        results = analyze_portfolio(holdings)

    alerts = []
    for r in results:
        a = r["analysis"]
        if a is None:
            continue
        name = r["holding"]["name"]
        amt = r["holding"]["amount"]
        price = a.get("price", 0)
        if a["rsi"] is not None and a["rsi"] <= 30:
            buy_amt = round(amt * 0.25, -2) or 500
            alerts.append(
                (
                    "🟢",
                    f"**{name}** has been falling a lot recently and looks cheap right now — could be a good time to buy",
                    f"Consider buying ~₹{buy_amt:,.0f} more of {name} to average down your cost. "
                    f"Current price is ₹{price:,.2f}. Set a stop-loss 10% below if you buy.",
                )
            )
        if a["rsi"] is not None and a["rsi"] >= 70:
            sell_pct = 20
            sell_amt = round(amt * sell_pct / 100, -2) or 500
            alerts.append(
                (
                    "⚠️",
                    f"**{name}** has been rising fast lately and may be too expensive right now — consider selling some to lock in your gains",
                    f"Sell ~₹{sell_amt:,.0f} ({sell_pct}% of your holding) to lock in profits. "
                    f"You can reinvest into an index fund or a stock that's currently undervalued.",
                )
            )
        if a["from_high_pct"] and a["from_high_pct"] < -20:
            drop = abs(a["from_high_pct"])
            alerts.append(
                (
                    "📉",
                    f"**{name}** is currently {drop:.0f}% lower than its best price in the last 1 year — it has dropped significantly",
                    f"If {name} is fundamentally strong, this dip is a buying opportunity — add ₹{round(amt * 0.15, -2) or 500:,.0f}. "
                    f"If you're unsure, wait and watch for a trend reversal before adding more.",
                )
            )
        if a["crossover"]:
            if "Golden" in str(a["crossover"]):
                alerts.append(
                    (
                        "🚨",
                        f"**{name}**: The short-term trend just crossed above the long-term trend — this is a bullish signal, the price may keep going up",
                        f"Hold your position in {name} — the momentum is positive. "
                        f"You could add ₹{round(amt * 0.1, -2) or 500:,.0f} more if you believe in the stock long-term.",
                    )
                )
            elif "Death" in str(a["crossover"]):
                alerts.append(
                    (
                        "🚨",
                        f"**{name}**: The short-term trend just crossed below the long-term trend — this is a warning signal, the price may keep falling",
                        f"Consider setting a stop-loss at ₹{price * 0.9:,.2f} (10% below current price) to limit losses. "
                        f"If it breaks below that, sell to protect your capital.",
                    )
                )
            else:
                alerts.append(("🚨", f"**{name}**: {a['crossover']}", ""))

    if alerts:
        st.subheader("⚡ Action Alerts")
        for item in alerts:
            icon, msg = item[0], item[1]
            fix = item[2] if len(item) > 2 else ""
            st.markdown(f"{icon} {msg}")
            if fix:
                with st.expander("💡 What should I do?"):
                    st.markdown(fix)
    else:
        st.success("✅ No urgent alerts — portfolio looks stable!")
