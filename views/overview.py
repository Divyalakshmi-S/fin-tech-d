import streamlit as st
import pandas as pd
import yfinance as yf


_PERIOD_OPTIONS = {
    "1W": "5d",
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "5Y": "5y",
}


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_index_data(ticker_symbol, period="1mo"):
    """Cached index data fetch — avoids re-downloading on every rerun."""
    try:
        data = yf.Ticker(ticker_symbol).history(period=period)
        if data is not None and not data.empty:
            return data
        return None
    except Exception:
        return None


def _render_index_card(label, ticker, period):
    """Render a single index metric + chart."""
    data = _fetch_index_data(ticker, period)
    if data is not None and not data.empty and len(data) >= 2:
        current = round(data["Close"].iloc[-1], 2)
        prev = round(data["Close"].iloc[-2], 2)
        change = round(current - prev, 2)
        pct = round((change / prev) * 100, 2)
        st.metric(label, f"₹{current:,.2f}", f"{change:+,.2f} ({pct:+.2f}%)")

        # Period high/low
        high = round(data["Close"].max(), 2)
        low = round(data["Close"].min(), 2)
        hl1, hl2 = st.columns(2)
        hl1.caption(f"High: ₹{high:,.2f}")
        hl2.caption(f"Low: ₹{low:,.2f}")

        chart_series = data["Close"].copy()
        chart_series.index = chart_series.index.tz_localize(None)
        st.line_chart(chart_series, height=200)
        return current, data
    else:
        st.warning(f"{label} data unavailable")
        return None, None


def render(holdings):
    st.title("🏠 Market Overview")

    # --- Timeframe selector ---
    selected_period_label = st.radio(
        "Timeframe",
        list(_PERIOD_OPTIONS.keys()),
        index=1,
        horizontal=True,
        label_visibility="collapsed",
    )
    yf_period = _PERIOD_OPTIONS[selected_period_label]

    # --- Nifty + Sensex side by side ---
    col1, col2 = st.columns(2)

    with col1:
        nifty_price, nifty_data = _render_index_card("Nifty 50", "^NSEI", yf_period)

    with col2:
        sensex_price, sensex_data = _render_index_card("Sensex", "^BSESN", yf_period)

    st.divider()

    # --- Market Pulse: VIX + Gold + USD/INR ---
    _market_pulse_fragment()

    st.divider()

    # --- Broader Market Indices ---
    _market_breadth_fragment()


@st.fragment()
def _market_pulse_fragment():
    """Fragment — market pulse loads independently so main indices render fast."""
    st.subheader("📡 Market Pulse")
    pulse1, pulse2, pulse3, pulse4 = st.columns(4)

    with pulse1:
        vix_data = _fetch_index_data("^INDIAVIX", "5d")
        if vix_data is not None and not vix_data.empty:
            vix = round(vix_data["Close"].iloc[-1], 2)
            vix_prev = (
                round(vix_data["Close"].iloc[-2], 2) if len(vix_data) >= 2 else vix
            )
            vix_change = round(vix - vix_prev, 2)
            vix_emoji = "🟢" if vix < 15 else "🟡" if vix < 20 else "🔴"
            vix_mood = (
                "Low Fear" if vix < 15 else "Moderate" if vix < 20 else "High Fear"
            )
            st.metric(f"{vix_emoji} India VIX", f"{vix:.2f}", f"{vix_change:+.2f}")
            st.caption(f"Market mood: **{vix_mood}**")
        else:
            st.metric("India VIX", "N/A")

    with pulse2:
        gold_data = _fetch_index_data("GC=F", "5d")
        if gold_data is not None and not gold_data.empty and len(gold_data) >= 2:
            gold = round(gold_data["Close"].iloc[-1], 2)
            gold_prev = round(gold_data["Close"].iloc[-2], 2)
            gold_chg = round(((gold - gold_prev) / gold_prev) * 100, 2)
            st.metric("Gold (USD/oz)", f"${gold:,.2f}", f"{gold_chg:+.2f}%")
        else:
            st.metric("Gold (USD/oz)", "N/A")

    with pulse3:
        fx_data = _fetch_index_data("USDINR=X", "5d")
        if fx_data is not None and not fx_data.empty and len(fx_data) >= 2:
            fx = round(fx_data["Close"].iloc[-1], 4)
            fx_prev = round(fx_data["Close"].iloc[-2], 4)
            fx_chg = round(fx - fx_prev, 4)
            st.metric("USD/INR", f"₹{fx:.2f}", f"{fx_chg:+.4f}")
        else:
            st.metric("USD/INR", "N/A")

    with pulse4:
        crude_data = _fetch_index_data("CL=F", "5d")
        if crude_data is not None and not crude_data.empty and len(crude_data) >= 2:
            crude = round(crude_data["Close"].iloc[-1], 2)
            crude_prev = round(crude_data["Close"].iloc[-2], 2)
            crude_chg = round(((crude - crude_prev) / crude_prev) * 100, 2)
            st.metric("Crude Oil (USD)", f"${crude:,.2f}", f"{crude_chg:+.2f}%")
        else:
            st.metric("Crude Oil", "N/A")


@st.fragment()
def _market_breadth_fragment():
    """Fragment — sector indices load independently."""
    st.subheader("📊 Market Breadth")
    breadth_indices = {
        "Bank Nifty": "^NSEBANK",
        "Nifty IT": "^CNXIT",
        "Nifty Midcap 50": "^NSEMDCP50",
    }
    bcols = st.columns(len(breadth_indices))
    for bcol, (idx_label, idx_ticker) in zip(bcols, breadth_indices.items()):
        with bcol:
            idx_data = _fetch_index_data(idx_ticker, "5d")
            if idx_data is not None and not idx_data.empty and len(idx_data) >= 2:
                cur = round(idx_data["Close"].iloc[-1], 2)
                prev = round(idx_data["Close"].iloc[-2], 2)
                chg_pct = round(((cur - prev) / prev) * 100, 2)
                st.metric(idx_label, f"₹{cur:,.2f}", f"{chg_pct:+.2f}%")
            else:
                st.metric(idx_label, "N/A")
