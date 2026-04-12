import csv
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from analysis import (
    load_portfolio_extended,
    analyze_portfolio,
    compute_rsi,
    analyze_gold_trend,
    predict_gold_buy,
    save_gold_prediction,
    verify_gold_predictions,
    get_silver_price,
    analyze_silver_trend,
    predict_silver_buy,
    save_silver_prediction,
    verify_silver_predictions,
    fetch_news,
    fetch_ticker_news,
    fetch_portfolio_news_with_impact,
    analyze_news_impact,
    predict_stock_buy,
    get_prediction_learnings,
    scan_top_movers,
    scan_oversold_opportunities,
    scan_sector_performance,
    suggest_stock_swaps,
    fetch_mf_nav_batch,
    compute_diversification,
)
from datetime import datetime


def _metal_inr_series(metal_hist, fx_hist, premium=1.03):
    """Convert metal USD/oz history to INR/gram using forward-filled FX rates.
    Handles weekends/holidays where trading dates don't overlap."""
    if metal_hist.empty or fx_hist.empty:
        return None
    # Combine both into one DataFrame, forward-fill FX gaps
    combined = pd.DataFrame(
        {
            "metal_usd": metal_hist["Close"],
            "fx": fx_hist["Close"],
        }
    )
    combined["fx"] = combined["fx"].ffill().bfill()
    combined = combined.dropna(subset=["metal_usd"])
    if combined.empty:
        return None
    return (combined["metal_usd"] * combined["fx"]) / 31.1035 * premium


# --- Config ---

st.set_page_config(
    page_title="Finance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown(
    """
<style>
    /* Tighter spacing */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }

    /* Card-like containers */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
        border: 1px solid #3d3d5c;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    div[data-testid="stMetric"] label {
        font-size: 0.85rem !important;
        color: #a0a0b8 !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
        font-weight: 700 !important;
    }

    /* Section headers */
    h2 {
        border-bottom: 2px solid #4a4a6a;
        padding-bottom: 0.4rem;
        margin-top: 1.5rem !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }

    /* Expanders */
    details {
        border: 1px solid #3d3d5c !important;
        border-radius: 10px !important;
        margin-bottom: 0.5rem;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        font-weight: 600 !important;
    }

    /* Alert boxes */
    .stAlert { border-radius: 8px; }

    /* Hide default footer */
    footer { visibility: hidden; }
</style>
""",
    unsafe_allow_html=True,
)


# --- Sidebar Navigation ---
st.sidebar.title("📊 Finance Dashboard")
st.sidebar.caption(f"📅 {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    [
        "🏠 Overview",
        "🪙 Gold & Silver",
        "📁 My Portfolio",
        "🔬 Holdings Analysis",
        "🔎 Market Scanner",
        "📰 News",
        "💰 Budget",
    ],
    label_visibility="collapsed",
)


# Load data once
@st.cache_data(ttl=300)
def load_holdings():
    return load_portfolio_extended()


@st.cache_data(ttl=300)
def load_analysis(holdings_tuple):
    holdings = [
        dict(
            zip(
                [
                    "name",
                    "ticker",
                    "amount",
                    "type",
                    "sip_monthly",
                    "sip_date",
                    "amfi_code",
                ],
                h,
            )
        )
        for h in holdings_tuple
    ]
    return analyze_portfolio(holdings)


holdings = load_holdings()
holdings_tuple = None
results = None
if holdings:
    holdings_tuple = tuple(
        tuple(
            h[k]
            for k in [
                "name",
                "ticker",
                "amount",
                "type",
                "sip_monthly",
                "sip_date",
                "amfi_code",
            ]
        )
        for h in holdings
    )


# ============================================================
# PAGE: Overview
# ============================================================
if page == "🏠 Overview":
    st.title("🏠 Market Overview")

    # Nifty + Sensex side by side
    col1, col2 = st.columns(2)

    with col1:
        nifty = yf.Ticker("^NSEI")
        nifty_data = nifty.history(period="1mo")
        if not nifty_data.empty and len(nifty_data) >= 2:
            current = round(nifty_data["Close"].iloc[-1], 2)
            prev = round(nifty_data["Close"].iloc[-2], 2)
            change = round(current - prev, 2)
            pct = round((change / prev) * 100, 2)
            st.metric("Nifty 50", f"₹{current:,.2f}", f"{change:+,.2f} ({pct:+.2f}%)")
            st.line_chart(nifty_data["Close"], height=200)
        else:
            st.warning("Nifty data unavailable")

    with col2:
        sensex = yf.Ticker("^BSESN")
        sensex_data = sensex.history(period="1mo")
        if not sensex_data.empty and len(sensex_data) >= 2:
            current = round(sensex_data["Close"].iloc[-1], 2)
            prev = round(sensex_data["Close"].iloc[-2], 2)
            change = round(current - prev, 2)
            pct = round((change / prev) * 100, 2)
            st.metric("Sensex", f"₹{current:,.2f}", f"{change:+,.2f} ({pct:+.2f}%)")
            st.line_chart(sensex_data["Close"], height=200)
        else:
            st.warning("Sensex data unavailable")

    st.divider()

    # Quick portfolio snapshot
    if holdings:
        st.subheader("📁 Portfolio Snapshot")

        total = sum(h["amount"] for h in holdings)
        stocks = sum(h["amount"] for h in holdings if h["type"] == "stock")
        mfs = sum(h["amount"] for h in holdings if h["type"] == "mutual_fund")

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Total Invested", f"₹{total:,.0f}")
        p2.metric("Stocks", f"₹{stocks:,.0f}", f"{stocks/total*100:.0f}%")
        p3.metric("Mutual Funds", f"₹{mfs:,.0f}", f"{mfs/total*100:.0f}%")
        p4.metric("Holdings", f"{len(holdings)}")

    st.divider()

    # Quick alerts
    if holdings:
        with st.spinner("Analyzing holdings..."):
            results = analyze_portfolio(holdings)

        alerts = []
        for r in results:
            a = r["analysis"]
            if a is None:
                continue
            name = r["holding"]["name"]
            amt = r["holding"]["amount"]
            price = a.get("current_price", 0)
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


# ============================================================
# PAGE: Gold & Silver
# ============================================================
elif page == "🪙 Gold & Silver":
    st.title("🪙 Gold & Silver Prices")
    st.caption("Chennai approximate rates (international futures × USD/INR)")

    gold_tab, silver_tab = st.tabs(["🪙 Gold", "🥈 Silver"])

    with gold_tab:
        try:
            gold_ticker = yf.Ticker("GC=F")
            usd_inr_ticker = yf.Ticker("USDINR=X")
            gold_hist = gold_ticker.history(period="1mo")
            fx_hist = usd_inr_ticker.history(period="1mo")

            gold_inr_per_gram = _metal_inr_series(gold_hist, fx_hist, premium=1.03)

            if gold_inr_per_gram is not None and len(gold_inr_per_gram) > 0:
                latest_1g = round(gold_inr_per_gram.iloc[-1], 2)
                latest_8g = round(latest_1g * 8, 2)
                if len(gold_inr_per_gram) >= 2:
                    prev_1g = round(gold_inr_per_gram.iloc[-2], 2)
                    change_1g = round(latest_1g - prev_1g, 2)
                    pct_1g = round((change_1g / prev_1g) * 100, 2)
                else:
                    change_1g = 0.0
                    pct_1g = 0.0

                g1, g2 = st.columns(2)
                g1.metric(
                    "1 Gram (24K)",
                    f"₹{latest_1g:,.2f}",
                    f"{change_1g:+,.2f} ({pct_1g:+.2f}%)",
                )
                g2.metric(
                    "8 Grams (24K)", f"₹{latest_8g:,.2f}", f"₹{change_1g * 8:+,.2f}"
                )

                if gold_inr_per_gram is not None and len(gold_inr_per_gram) > 0:
                    st.line_chart(
                        pd.DataFrame({"Gold ₹/gram": gold_inr_per_gram}), height=300
                    )

                # Trend
                gold_trend = analyze_gold_trend()
                if gold_trend:
                    st.subheader("📊 Trend Analysis")
                    gt1, gt2, gt3, gt4 = st.columns(4)
                    gt1.metric("Weekly", f"{gold_trend['weekly_change']:+.2f}%")
                    gt2.metric("Monthly", f"{gold_trend['monthly_change']:+.2f}%")
                    gt3.metric("3M High", f"₹{gold_trend['high_3m']:,.2f}")
                    gt4.metric("3M Low", f"₹{gold_trend['low_3m']:,.2f}")

                    if gold_trend["monthly_change"] < -5:
                        st.success(
                            "💡 Gold corrected significantly — potential buying opportunity!"
                        )
                    elif gold_trend["monthly_change"] > 5:
                        st.info("📈 Gold on a strong uptrend — hold your positions!")

                # --- Should I Buy Gold? ---
                st.divider()
                st.subheader("🤔 Should I Buy Gold Now?")
                st.caption(
                    "Analysis based on RSI, moving averages, 3-month range, momentum, and news sentiment"
                )

                with st.spinner("Analyzing gold..."):
                    gold_pred = predict_gold_buy(use_news=True)

                if gold_pred:
                    signal = gold_pred["signal"]
                    conf = gold_pred["confidence"]

                    signal_map = {
                        "BUY": (
                            "🟢",
                            "#27ae60",
                            "Good time to buy gold",
                            "Buy now — most indicators are positive",
                        ),
                        "LEAN BUY": (
                            "🟢",
                            "#2ecc71",
                            "Slightly favourable",
                            "Buy a small amount now, add more if price dips",
                        ),
                        "SELL": (
                            "🔴",
                            "#e74c3c",
                            "Don't buy right now",
                            "Gold looks overpriced — wait for a correction",
                        ),
                        "LEAN SELL": (
                            "🟠",
                            "#f39c12",
                            "Wait a few days",
                            "Slightly unfavourable — a dip may be coming soon",
                        ),
                        "WAIT": (
                            "🟡",
                            "#f1c40f",
                            "No clear signal",
                            "Mixed signals — check again in a few days",
                        ),
                    }
                    signal_color, hex_color, signal_short, signal_action = (
                        signal_map.get(
                            signal, ("🟡", "#f1c40f", "Wait", "Check again later")
                        )
                    )

                    # Big verdict card
                    st.markdown(
                        f"""<div style="background: linear-gradient(135deg, {hex_color}22, {hex_color}11);
                        border-left: 5px solid {hex_color}; border-radius: 10px;
                        padding: 20px; margin: 10px 0;">
                        <h2 style="margin:0; color: {hex_color};">{signal_color} {signal}</h2>
                        <p style="font-size: 1.2em; margin: 8px 0 4px 0;"><strong>{signal_short}</strong></p>
                        <p style="margin: 0; opacity: 0.85;">{signal_action}</p>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                    pc1, pc2, pc3 = st.columns(3)
                    pc1.metric("Current Price", f"₹{gold_pred['current_price']:,.2f}/g")
                    pc2.metric("Confidence", f"{conf}%")
                    # Show what the score range means
                    buy_factors = sum(1 for _, s, _ in gold_pred["reasons"] if s > 0)
                    sell_factors = sum(1 for _, s, _ in gold_pred["reasons"] if s < 0)
                    pc3.metric("Factors", f"{buy_factors} Buy / {sell_factors} Sell")

                    st.info(f"📅 **Next 5-7 days:** {gold_pred['prediction']}")

                    # Signal scale legend
                    with st.expander("ℹ️ What do these signals mean?"):
                        st.markdown(
                            """
| Signal | Meaning | Action |
|---|---|---|
| 🟢 **BUY** | Most factors say gold is cheap | Buy now |
| 🟢 **LEAN BUY** | Slightly favourable conditions | Buy a small amount |
| 🟡 **WAIT** | Mixed signals, no clear direction | Don't act, check later |
| 🟠 **LEAN SELL** | Slightly unfavourable | Hold off, wait for a dip |
| 🔴 **SELL** | Most factors say gold is expensive | Don't buy, consider selling |
"""
                        )

                    # Show detailed breakdown
                    with st.expander("📊 Detailed Analysis — Why this signal?"):
                        for factor, score, reason in gold_pred["reasons"]:
                            if score > 0:
                                bar_color = "#27ae60"
                                icon = "🟢"
                                label = f"+{score} Buy"
                            elif score < 0:
                                bar_color = "#e74c3c"
                                icon = "🔴"
                                label = f"{score} Sell"
                            else:
                                bar_color = "#95a5a6"
                                icon = "⚪"
                                label = "Neutral"
                            # Visual bar showing score magnitude
                            bar_width = min(abs(score) * 3, 100)
                            st.markdown(
                                f"""<div style="margin: 8px 0;">
                                <strong>{icon} {factor}</strong> <span style="color: {bar_color}; font-size: 0.9em;">[{label}]</span>
                                <div style="background: #eee; border-radius: 4px; height: 6px; margin: 4px 0;">
                                    <div style="background: {bar_color}; width: {bar_width}%; height: 6px; border-radius: 4px;"></div>
                                </div>
                                <span style="font-size: 0.85em; opacity: 0.7;">{reason}</span>
                                </div>""",
                                unsafe_allow_html=True,
                            )

                        st.markdown("---")
                        score = gold_pred["total_score"]
                        score_color = (
                            "#27ae60"
                            if score > 0
                            else "#e74c3c" if score < 0 else "#95a5a6"
                        )
                        st.markdown(
                            f"**Total Score:** <span style='color: {score_color}; font-size: 1.2em;'>{score:+d}</span>"
                            f" &nbsp; (BUY > +25 · LEAN BUY > +10 · WAIT · LEAN SELL < -10 · SELL < -25)",
                            unsafe_allow_html=True,
                        )

                    # Save today's prediction
                    save_gold_prediction(gold_pred)

                    # Verify past predictions
                    past_preds = verify_gold_predictions()
                    verified = [p for p in past_preds if p.get("verified")]
                    if verified:
                        with st.expander(
                            f"📈 Prediction Track Record ({len(verified)} verified)"
                        ):
                            correct = sum(1 for p in verified if p.get("was_correct"))
                            accuracy = (
                                round((correct / len(verified)) * 100)
                                if verified
                                else 0
                            )

                            tr1, tr2, tr3 = st.columns(3)
                            tr1.metric("Predictions Made", len(verified))
                            tr2.metric("Correct", f"{correct} ✅")
                            tr3.metric("Accuracy", f"{accuracy}%")

                            if accuracy < 50 and len(verified) >= 3:
                                st.warning(
                                    "⚠️ Accuracy is below 50% — the model is being refined with each prediction. More data will improve results."
                                )

                            for p in reversed(verified[-10:]):
                                was = (
                                    "✅ Correct" if p.get("was_correct") else "❌ Wrong"
                                )
                                change = p.get("actual_change_pct", 0)
                                st.markdown(
                                    f"**{p['date']}** — Signal: {p['signal']} at ₹{p['price_at_prediction']:,.2f} → "
                                    f"₹{p.get('actual_price_after', 0):,.2f} ({change:+.2f}%) — {was}"
                                )

                    # --- Self-Learning: What I Learned from My Mistakes ---
                    gold_learnings = get_prediction_learnings("gold")
                    if gold_learnings and gold_learnings.get("learnings"):
                        with st.expander(
                            f"🧠 What I Learned from My Mistakes ({gold_learnings['total_verified']} predictions analysed)"
                        ):
                            st.markdown(
                                "I analyse my past predictions to find which factors led me astray and adjust accordingly:"
                            )
                            st.markdown("")

                            # Factor accuracy table
                            fa = gold_learnings["factor_accuracy"]
                            if fa:
                                for fname, fdata in fa.items():
                                    acc = fdata["accuracy"]
                                    acc_color = (
                                        "#27ae60"
                                        if acc >= 70
                                        else "#f39c12" if acc >= 50 else "#e74c3c"
                                    )
                                    bar_w = max(acc, 5)
                                    st.markdown(
                                        f"""<div style="margin: 6px 0;">
                                        <strong>{fname}</strong> — <span style="color: {acc_color};">{acc}% accurate</span> ({fdata['correct']}/{fdata['total']} correct)
                                        <div style="background: #eee; border-radius: 4px; height: 6px; margin: 4px 0;">
                                            <div style="background: {acc_color}; width: {bar_w}%; height: 6px; border-radius: 4px;"></div>
                                        </div>
                                        </div>""",
                                        unsafe_allow_html=True,
                                    )

                            st.markdown("---")
                            st.markdown("**Key Learnings:**")
                            for learning in gold_learnings["learnings"]:
                                st.markdown(learning)

                            if gold_learnings["worst_factors"]:
                                st.markdown("")
                                st.markdown(
                                    f"**Weakest factors:** {', '.join(gold_learnings['worst_factors'])} — I'm reducing their influence on future predictions."
                                )
                else:
                    st.warning("Could not generate gold prediction — data unavailable")

                # --- Gold Price History: Big Moves ---
                st.divider()
                st.subheader("📜 Gold Price History — Significant Moves")

                period_choice = st.radio(
                    "Period",
                    ["3 Months", "6 Months", "1 Year"],
                    horizontal=True,
                    key="gold_period",
                )
                period_map = {"3 Months": "3mo", "6 Months": "6mo", "1 Year": "1y"}

                gold_hist_long = yf.Ticker("GC=F").history(
                    period=period_map[period_choice]
                )
                fx_hist_long = yf.Ticker("USDINR=X").history(
                    period=period_map[period_choice]
                )

                gold_inr_hist = _metal_inr_series(
                    gold_hist_long, fx_hist_long, premium=1.03
                )
                if gold_inr_hist is not None and len(gold_inr_hist) > 1:
                    daily_pct = gold_inr_hist.pct_change() * 100
                    daily_pct = daily_pct.dropna()

                    # Long-term chart
                    st.line_chart(
                        pd.DataFrame({"Gold ₹/gram": gold_inr_hist}), height=300
                    )

                    # Stats row
                    hs1, hs2, hs3, hs4 = st.columns(4)
                    hs1.metric(f"{period_choice} High", f"₹{gold_inr_hist.max():,.2f}")
                    hs2.metric(f"{period_choice} Low", f"₹{gold_inr_hist.min():,.2f}")
                    total_change = (
                        (gold_inr_hist.iloc[-1] / gold_inr_hist.iloc[0]) - 1
                    ) * 100
                    hs3.metric("Total Change", f"{total_change:+.2f}%")
                    hs4.metric("Avg Daily Move", f"{daily_pct.abs().mean():.2f}%")

                    # Biggest drops
                    top_drops = daily_pct.nsmallest(5)
                    top_rises = daily_pct.nlargest(5)

                    dr_col, ri_col = st.columns(2)

                    with dr_col:
                        st.markdown("#### 📉 Biggest Drops")
                        for date, pct in top_drops.items():
                            price = gold_inr_hist.loc[date]
                            st.markdown(
                                f"🔴 **{date.strftime('%d %b %Y')}** — {pct:.2f}% (₹{price:,.2f}/g)"
                            )

                    with ri_col:
                        st.markdown("#### 📈 Biggest Rises")
                        for date, pct in top_rises.items():
                            price = gold_inr_hist.loc[date]
                            st.markdown(
                                f"🟢 **{date.strftime('%d %b %Y')}** — +{pct:.2f}% (₹{price:,.2f}/g)"
                            )

                    # Daily change distribution
                    st.subheader("📊 Daily Change Distribution")
                    change_df = pd.DataFrame({"Daily Change %": daily_pct})
                    st.bar_chart(change_df, height=200)
                else:
                    st.info("No history data available for this period")
            else:
                st.warning("Could not fetch gold data")
        except Exception as e:
            st.warning(f"Gold data unavailable: {e}")

    with silver_tab:
        try:
            silver_data = get_silver_price()
            if silver_data:
                change_str = (
                    f"{silver_data['change_pct']:+.2f}%"
                    if silver_data["change_pct"] is not None
                    else "N/A"
                )

                s1, s2, s3 = st.columns(3)
                s1.metric("1 Gram", f"₹{silver_data['per_gram']:,.2f}", change_str)
                s2.metric("100 Grams", f"₹{silver_data['per_100gram']:,.2f}")
                s3.metric("1 Kg", f"₹{silver_data['per_kg']:,.2f}")

                silver_trend = analyze_silver_trend()
                if silver_trend:
                    st.subheader("📊 Trend Analysis")
                    st1, st2, st3, st4 = st.columns(4)
                    st1.metric("Weekly", f"{silver_trend['weekly_change']:+.2f}%")
                    st2.metric("Monthly", f"{silver_trend['monthly_change']:+.2f}%")
                    st3.metric("3M High", f"₹{silver_trend['high_3m']:,.2f}")
                    st4.metric("3M Low", f"₹{silver_trend['low_3m']:,.2f}")

                # Chart
                sv_ticker = yf.Ticker("SI=F")
                usd_inr_sv = yf.Ticker("USDINR=X")
                sv_hist = sv_ticker.history(period="1mo")
                fx_sv = usd_inr_sv.history(period="1mo")
                sv_inr_1mo = _metal_inr_series(sv_hist, fx_sv, premium=1.05)
                if sv_inr_1mo is not None and len(sv_inr_1mo) > 0:
                    st.line_chart(
                        pd.DataFrame({"Silver ₹/gram": sv_inr_1mo}), height=300
                    )

                # --- Should I Buy Silver? ---
                st.divider()
                st.subheader("🤔 Should I Buy Silver Now?")
                st.caption(
                    "Analysis based on RSI, moving averages, 3-month range, momentum, and news"
                )

                with st.spinner("Analyzing silver..."):
                    silver_pred = predict_silver_buy(use_news=True)

                if silver_pred:
                    sig = silver_pred["signal"]
                    conf = silver_pred["confidence"]

                    sig_map = {
                        "BUY": (
                            "🟢",
                            "#27ae60",
                            "Good time to buy silver",
                            "Buy now — most indicators are positive",
                        ),
                        "LEAN BUY": (
                            "🟢",
                            "#2ecc71",
                            "Slightly favourable",
                            "Buy a small amount now, add more if price dips",
                        ),
                        "SELL": (
                            "🔴",
                            "#e74c3c",
                            "Don't buy right now",
                            "Silver looks overpriced — wait for a correction",
                        ),
                        "LEAN SELL": (
                            "🟠",
                            "#f39c12",
                            "Wait a few days",
                            "Slightly unfavourable — a dip may be coming soon",
                        ),
                        "WAIT": (
                            "🟡",
                            "#f1c40f",
                            "No clear signal",
                            "Mixed signals — check again in a few days",
                        ),
                    }
                    sig_color, hex_c, sig_short, sig_action = sig_map.get(
                        sig, ("🟡", "#f1c40f", "Wait", "Check again later")
                    )

                    st.markdown(
                        f"""<div style="background: linear-gradient(135deg, {hex_c}22, {hex_c}11);
                        border-left: 5px solid {hex_c}; border-radius: 10px;
                        padding: 20px; margin: 10px 0;">
                        <h2 style="margin:0; color: {hex_c};">{sig_color} {sig}</h2>
                        <p style="font-size: 1.2em; margin: 8px 0 4px 0;"><strong>{sig_short}</strong></p>
                        <p style="margin: 0; opacity: 0.85;">{sig_action}</p>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                    sp1, sp2, sp3 = st.columns(3)
                    sp1.metric(
                        "Current Price", f"₹{silver_pred['current_price']:,.2f}/g"
                    )
                    sp2.metric("Confidence", f"{conf}%")
                    buy_f = sum(1 for _, s, _ in silver_pred["reasons"] if s > 0)
                    sell_f = sum(1 for _, s, _ in silver_pred["reasons"] if s < 0)
                    sp3.metric("Factors", f"{buy_f} Buy / {sell_f} Sell")

                    st.info(f"📅 **Next 5-7 days:** {silver_pred['prediction']}")

                    with st.expander("📊 Detailed Analysis — Why this signal?"):
                        for factor, score, reason in silver_pred["reasons"]:
                            if score > 0:
                                bar_color = "#27ae60"
                                icon = "🟢"
                                label = f"+{score} Buy"
                            elif score < 0:
                                bar_color = "#e74c3c"
                                icon = "🔴"
                                label = f"{score} Sell"
                            else:
                                bar_color = "#95a5a6"
                                icon = "⚪"
                                label = "Neutral"
                            bar_width = min(abs(score) * 3, 100)
                            st.markdown(
                                f"""<div style="margin: 8px 0;">
                                <strong>{icon} {factor}</strong> <span style="color: {bar_color}; font-size: 0.9em;">[{label}]</span>
                                <div style="background: #eee; border-radius: 4px; height: 6px; margin: 4px 0;">
                                    <div style="background: {bar_color}; width: {bar_width}%; height: 6px; border-radius: 4px;"></div>
                                </div>
                                <span style="font-size: 0.85em; opacity: 0.7;">{reason}</span>
                                </div>""",
                                unsafe_allow_html=True,
                            )

                        sv_score = silver_pred["total_score"]
                        sv_sc = (
                            "#27ae60"
                            if sv_score > 0
                            else "#e74c3c" if sv_score < 0 else "#95a5a6"
                        )
                        st.markdown(
                            f"**Total Score:** <span style='color: {sv_sc}; font-size: 1.2em;'>{sv_score:+d}</span>"
                            f" &nbsp; (BUY > +25 · LEAN BUY > +10 · WAIT · LEAN SELL < -10 · SELL < -25)",
                            unsafe_allow_html=True,
                        )

                    # Save and verify silver predictions
                    save_silver_prediction(silver_pred)

                    sv_past = verify_silver_predictions()
                    sv_verified = [p for p in sv_past if p.get("verified")]
                    if sv_verified:
                        with st.expander(
                            f"📈 Prediction Track Record ({len(sv_verified)} verified)"
                        ):
                            sv_correct = sum(
                                1 for p in sv_verified if p.get("was_correct")
                            )
                            sv_accuracy = (
                                round((sv_correct / len(sv_verified)) * 100)
                                if sv_verified
                                else 0
                            )

                            svr1, svr2, svr3 = st.columns(3)
                            svr1.metric("Predictions Made", len(sv_verified))
                            svr2.metric("Correct", f"{sv_correct} ✅")
                            svr3.metric("Accuracy", f"{sv_accuracy}%")

                            for p in reversed(sv_verified[-10:]):
                                was = (
                                    "✅ Correct" if p.get("was_correct") else "❌ Wrong"
                                )
                                change = p.get("actual_change_pct", 0)
                                st.markdown(
                                    f"**{p['date']}** — Signal: {p['signal']} at ₹{p['price_at_prediction']:,.2f} → "
                                    f"₹{p.get('actual_price_after', 0):,.2f} ({change:+.2f}%) — {was}"
                                )

                    # Self-learning for silver
                    silver_learnings = get_prediction_learnings("silver")
                    if silver_learnings and silver_learnings.get("learnings"):
                        with st.expander(
                            f"🧠 What I Learned from Silver Mistakes ({silver_learnings['total_verified']} analysed)"
                        ):
                            fa = silver_learnings["factor_accuracy"]
                            if fa:
                                for fname, fdata in fa.items():
                                    acc = fdata["accuracy"]
                                    acc_color = (
                                        "#27ae60"
                                        if acc >= 70
                                        else "#f39c12" if acc >= 50 else "#e74c3c"
                                    )
                                    st.markdown(
                                        f"""<div style="margin: 6px 0;">
                                        <strong>{fname}</strong> — <span style="color: {acc_color};">{acc}% accurate</span> ({fdata['correct']}/{fdata['total']})
                                        <div style="background: #eee; border-radius: 4px; height: 6px; margin: 4px 0;">
                                            <div style="background: {acc_color}; width: {max(acc, 5)}%; height: 6px; border-radius: 4px;"></div>
                                        </div>
                                        </div>""",
                                        unsafe_allow_html=True,
                                    )
                            for learning in silver_learnings["learnings"]:
                                st.markdown(learning)

                else:
                    st.warning(
                        "Could not generate silver prediction — data unavailable"
                    )

                # --- Silver Price History: Big Moves ---
                st.divider()
                st.subheader("📜 Silver Price History — Significant Moves")

                sv_period = st.radio(
                    "Period",
                    ["3 Months", "6 Months", "1 Year"],
                    horizontal=True,
                    key="silver_period",
                )
                sv_period_map = {"3 Months": "3mo", "6 Months": "6mo", "1 Year": "1y"}

                sv_hist_long = yf.Ticker("SI=F").history(
                    period=sv_period_map[sv_period]
                )
                fx_sv_long = yf.Ticker("USDINR=X").history(
                    period=sv_period_map[sv_period]
                )

                if not sv_hist_long.empty and not fx_sv_long.empty:
                    sv_inr_hist = _metal_inr_series(
                        sv_hist_long, fx_sv_long, premium=1.05
                    )
                    if sv_inr_hist is not None and len(sv_inr_hist) > 1:
                        sv_daily_pct = sv_inr_hist.pct_change() * 100
                        sv_daily_pct = sv_daily_pct.dropna()

                        # Long-term chart
                        st.line_chart(
                            pd.DataFrame({"Silver ₹/gram": sv_inr_hist}), height=300
                        )

                        # Stats row
                        ss1, ss2, ss3, ss4 = st.columns(4)
                        ss1.metric(f"{sv_period} High", f"₹{sv_inr_hist.max():,.2f}")
                        ss2.metric(f"{sv_period} Low", f"₹{sv_inr_hist.min():,.2f}")
                        sv_total_change = (
                            (sv_inr_hist.iloc[-1] / sv_inr_hist.iloc[0]) - 1
                        ) * 100
                        ss3.metric("Total Change", f"{sv_total_change:+.2f}%")
                        ss4.metric(
                            "Avg Daily Move", f"{sv_daily_pct.abs().mean():.2f}%"
                        )

                        # Biggest drops and rises
                        sv_top_drops = sv_daily_pct.nsmallest(5)
                        sv_top_rises = sv_daily_pct.nlargest(5)

                        sv_dr, sv_ri = st.columns(2)

                        with sv_dr:
                            st.markdown("#### 📉 Biggest Drops")
                            for date, pct in sv_top_drops.items():
                                price = sv_inr_hist.loc[date]
                                st.markdown(
                                    f"🔴 **{date.strftime('%d %b %Y')}** — {pct:.2f}% (₹{price:,.2f}/g)"
                                )

                        with sv_ri:
                            st.markdown("#### 📈 Biggest Rises")
                            for date, pct in sv_top_rises.items():
                                price = sv_inr_hist.loc[date]
                                st.markdown(
                                    f"🟢 **{date.strftime('%d %b %Y')}** — +{pct:.2f}% (₹{price:,.2f}/g)"
                                )

                        # Daily change distribution
                        st.subheader("📊 Daily Change Distribution")
                        sv_change_df = pd.DataFrame({"Daily Change %": sv_daily_pct})
                        st.bar_chart(sv_change_df, height=200)
                    else:
                        st.info("No history data available for this period")
            else:
                st.warning("Could not fetch silver data")
        except Exception as e:
            st.warning(f"Silver data unavailable: {e}")


# ============================================================
# PAGE: My Portfolio
# ============================================================
elif page == "📁 My Portfolio":
    st.title("📁 My Portfolio")

    if not holdings:
        st.info("No portfolio data. Add investments to `data/portfolio.csv`.")
    else:
        # Summary cards
        total = sum(h["amount"] for h in holdings)
        stocks = [h for h in holdings if h["type"] == "stock"]
        mfs = [h for h in holdings if h["type"] == "mutual_fund"]
        active_sips = [h for h in holdings if h["sip_monthly"] > 0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Invested", f"₹{total:,.0f}")
        c2.metric(
            "Stocks", f"{len(stocks)}", f"₹{sum(h['amount'] for h in stocks):,.0f}"
        )
        c3.metric(
            "Mutual Funds", f"{len(mfs)}", f"₹{sum(h['amount'] for h in mfs):,.0f}"
        )
        c4.metric(
            "Active SIPs",
            f"{len(active_sips)}",
            f"₹{sum(h['sip_monthly'] for h in active_sips):,.0f}/mo",
        )

        st.divider()

        # Holdings table
        st.subheader("📋 All Holdings")
        portfolio_df = pd.DataFrame(
            [
                {
                    "Name": h["name"],
                    "Ticker": h["ticker"],
                    "Invested (₹)": f"{h['amount']:,.0f}",
                    "Type": h["type"].replace("_", " ").title(),
                    "SIP/mo": (
                        f"₹{h['sip_monthly']:,.0f}" if h["sip_monthly"] > 0 else "—"
                    ),
                    "Weight": f"{h['amount']/total*100:.1f}%",
                }
                for h in holdings
            ]
        )
        st.dataframe(portfolio_df, use_container_width=True, hide_index=True)

        st.divider()

        # Allocation charts
        a1, a2 = st.columns(2)

        with a1:
            st.subheader("📊 By Type")
            type_data = {}
            for h in holdings:
                t = h["type"].replace("_", " ").title()
                type_data[t] = type_data.get(t, 0) + h["amount"]
            st.bar_chart(pd.Series(type_data, name="₹"), height=250)

        with a2:
            st.subheader("📊 Top Holdings")
            top = sorted(holdings, key=lambda x: x["amount"], reverse=True)[:5]
            top_data = {h["name"][:20]: h["amount"] for h in top}
            st.bar_chart(pd.Series(top_data, name="₹"), height=250)

        st.divider()

        # MF NAVs
        mf_codes = [h["amfi_code"] for h in holdings if h.get("amfi_code")]
        if mf_codes:
            st.subheader("📊 Mutual Fund NAVs")
            with st.spinner("Fetching NAVs from AMFI India..."):
                try:
                    mf_navs = fetch_mf_nav_batch(mf_codes)
                    if mf_navs:
                        nav_rows = []
                        for code, info in mf_navs.items():
                            matching = [
                                h for h in holdings if h.get("amfi_code") == code
                            ]
                            invested = matching[0]["amount"] if matching else 0
                            nav_rows.append(
                                {
                                    "Scheme": info["scheme_name"][:50],
                                    "NAV (₹)": f"{info['nav']:.4f}",
                                    "Date": info["date"],
                                    "Invested": f"₹{invested:,.0f}",
                                }
                            )
                        st.dataframe(
                            pd.DataFrame(nav_rows),
                            use_container_width=True,
                            hide_index=True,
                        )
                except Exception as e:
                    st.warning(f"NAV fetch failed: {e}")

        st.divider()

        # Diversification
        st.subheader("🎯 Diversification Score")
        tickers_for_div = [h for h in holdings if h["ticker"]]
        div_results = analyze_portfolio(holdings) if tickers_for_div else []
        div_data = compute_diversification(holdings, div_results)

        if div_data:
            score = div_data["score"]
            score_emoji = "🟢" if score >= 60 else "🟡" if score >= 40 else "🔴"
            score_label = (
                "Well Diversified"
                if score >= 60
                else "Moderate" if score >= 40 else "Concentrated"
            )

            d1, d2, d3 = st.columns(3)
            d1.metric("Score", f"{score_emoji} {score}/100", score_label)
            d2.metric("Holdings", f"{len(holdings)}")
            d3.metric("HHI Index", f"{div_data['hhi']:.0f}", "Lower = better")

            if div_data["warnings"]:
                st.subheader("⚠️ Alerts")
                for w in div_data["warnings"]:
                    warn_text = w[0] if isinstance(w, tuple) else w
                    fix_text = w[1] if isinstance(w, tuple) else ""
                    st.warning(warn_text)
                    if fix_text:
                        with st.expander("💡 How to fix this"):
                            st.markdown(fix_text)


# ============================================================
# PAGE: Holdings Analysis
# ============================================================
elif page == "🔬 Holdings Analysis":
    st.title("🔬 Holdings Deep Analysis")

    if not holdings:
        st.info("No holdings to analyze.")
    else:
        tickers_with_data = [h for h in holdings if h["ticker"]]

        if not tickers_with_data:
            st.info("Add ticker symbols for live analysis.")
        else:
            with st.spinner("Fetching live data..."):
                results = analyze_portfolio(holdings)

            # Summary comparison table first
            st.subheader("📋 Quick Comparison")
            summary_rows = []
            for r in results:
                a = r["analysis"]
                if a is None:
                    continue
                h = r["holding"]
                daily_color = "🟢" if a["daily_change_pct"] >= 0 else "🔴"
                rsi_val = f"{a['rsi']:.0f}" if a["rsi"] else "—"
                rsi_signal = a.get("rsi_signal", "") if a["rsi"] else ""
                if a["rsi"]:
                    rsi_num = a["rsi"]
                    if rsi_num >= 70:
                        momentum = f"{rsi_val} (Expensive)"
                    elif rsi_num <= 30:
                        momentum = f"{rsi_val} (Cheap)"
                    else:
                        momentum = f"{rsi_val} (Normal)"
                else:
                    momentum = "—"
                summary_rows.append(
                    {
                        "Name": h["name"],
                        "Price": f"₹{a['price']:,.2f}",
                        "Today": f"{daily_color} {a['daily_change_pct']:+.2f}%",
                        "Momentum": momentum,
                        "Direction": a["trend"],
                        "vs Best Price": f"{a['from_high_pct']:+.1f}%",
                        "This Year": (
                            f"{a['ytd_return']:+.1f}%"
                            if a["ytd_return"] is not None
                            else "—"
                        ),
                        "1 Year": f"{a['one_yr_return']:+.1f}%",
                    }
                )

            if summary_rows:
                st.dataframe(
                    pd.DataFrame(summary_rows),
                    use_container_width=True,
                    hide_index=True,
                    height=min(len(summary_rows) * 40 + 40, 450),
                )

            st.divider()

            # --- Portfolio News Monitor ---
            st.subheader("📰 News Affecting Your Holdings")
            st.caption("Latest news about companies you own and why it matters to you")

            with st.spinner("Scanning news for your holdings..."):
                try:
                    portfolio_news = fetch_portfolio_news_with_impact(
                        holdings, max_per_stock=3
                    )
                    if portfolio_news:
                        # Summary row: which stocks have concerning news
                        bearish_stocks = [
                            pn
                            for pn in portfolio_news
                            if pn["overall_sentiment"] == "bearish"
                        ]
                        bullish_stocks = [
                            pn
                            for pn in portfolio_news
                            if pn["overall_sentiment"] == "bullish"
                        ]

                        if bearish_stocks or bullish_stocks:
                            nc1, nc2 = st.columns(2)
                            if bullish_stocks:
                                with nc1:
                                    names = ", ".join(
                                        pn["holding"]["name"]
                                        for pn in bullish_stocks[:3]
                                    )
                                    st.success(f"🟢 **Positive news for:** {names}")
                            if bearish_stocks:
                                with nc2:
                                    names = ", ".join(
                                        pn["holding"]["name"]
                                        for pn in bearish_stocks[:3]
                                    )
                                    st.warning(f"🔴 **Concerning news for:** {names}")

                        for pn in portfolio_news:
                            h_info = pn["holding"]
                            sentiment_icon = {
                                "bullish": "🟢",
                                "bearish": "🔴",
                                "neutral": "⚪",
                            }.get(pn["overall_sentiment"], "⚪")
                            with st.expander(
                                f"{sentiment_icon} **{h_info['name']}** — {pn['bull_count']} good, {pn['bear_count']} bad news"
                            ):
                                for ni in pn["news_items"]:
                                    impact = ni["impact"]
                                    s_label = impact["sentiment_label"]
                                    if s_label == "Good news":
                                        box_color = "#27ae60"
                                    elif s_label == "Bad news":
                                        box_color = "#e74c3c"
                                    else:
                                        box_color = "#95a5a6"
                                    st.markdown(
                                        f"""<div style="border-left: 4px solid {box_color}; padding: 8px 12px; margin: 8px 0; border-radius: 4px; background: {box_color}11;">
                                        <strong>{ni['title'][:120]}</strong>
                                        <span style="color: {box_color}; font-size: 0.85em;"> — {s_label}</span>
                                        <br><span style="font-size: 0.9em;">{impact['summary']}</span>
                                        <br><span style="font-size: 0.85em; opacity: 0.8;">👉 {impact['action']}</span>
                                        </div>""",
                                        unsafe_allow_html=True,
                                    )
                    else:
                        st.info("No recent news found for your holdings.")
                except Exception:
                    st.info("Could not fetch portfolio news. Try again later.")

            st.divider()

            # Per-stock detailed cards
            st.subheader("📌 Detailed Analysis")

            for r in results:
                h = r["holding"]
                a = r["analysis"]
                sv = r["sip_value"]

                if a is None:
                    continue

                daily_icon = "🟢" if a["daily_change_pct"] >= 0 else "🔴"
                with st.expander(
                    f"{daily_icon} **{h['name']}** — ₹{a['price']:,.2f} ({a['daily_change_pct']:+.2f}%)",
                    expanded=False,
                ):
                    # Key metrics row
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric(
                        "Today's Price",
                        f"₹{a['price']:,.2f}",
                        f"{a['daily_change_pct']:+.2f}% today",
                    )
                    m2.metric(
                        "Best Price (1 Year)",
                        f"₹{a['high_52w']:,.2f}",
                        f"{a['from_high_pct']:+.1f}% from best",
                    )
                    m3.metric(
                        "Worst Price (1 Year)",
                        f"₹{a['low_52w']:,.2f}",
                        f"{a['from_low_pct']:+.1f}% from worst",
                    )
                    if a["rsi"] is not None:
                        rsi_val = a["rsi"]
                        if rsi_val >= 70:
                            rsi_text = "Expensive zone"
                        elif rsi_val <= 30:
                            rsi_text = "Cheap zone"
                        elif rsi_val >= 60:
                            rsi_text = "Getting expensive"
                        elif rsi_val <= 40:
                            rsi_text = "Getting cheap"
                        else:
                            rsi_text = "Normal range"
                        m4.metric("Momentum", f"{rsi_val:.0f}/100", rsi_text)
                    else:
                        m4.metric("Momentum", "—")

                    # Trend & MA
                    t1, t2, t3, t4 = st.columns(4)
                    t1.metric("Direction", a["trend"])
                    if a["sma50"]:
                        t2.metric("50-Day Avg Price", f"₹{a['sma50']:,.2f}")
                    if a["sma200"]:
                        t3.metric("200-Day Avg Price", f"₹{a['sma200']:,.2f}")
                    if a["ytd_return"] is not None:
                        t4.metric("Return This Year", f"{a['ytd_return']:+.1f}%")

                    # Alerts inline
                    if a["crossover"]:
                        if "Golden" in str(a["crossover"]):
                            st.success(
                                "📈 Good sign! The price trend is turning positive — this stock may continue going up"
                            )
                        elif "Death" in str(a["crossover"]):
                            st.warning(
                                "📉 Warning! The price trend is turning negative — this stock may continue falling"
                            )
                        else:
                            st.warning(a["crossover"])
                    if a["vol_ratio"] and a["vol_ratio"] > 1.5:
                        st.info(
                            f"📊 This stock is being traded {a['vol_ratio']:.1f}x more than usual today — something big might be happening"
                        )

                    # Fundamentals for stocks
                    if h["type"] == "stock":
                        f_cols = st.columns(4)
                        idx = 0
                        if a["pe_ratio"]:
                            pe_hint = (
                                "Expensive"
                                if a["pe_ratio"] > 40
                                else "Cheap" if a["pe_ratio"] < 15 else "Fair"
                            )
                            f_cols[idx].metric(
                                f"Value ({pe_hint})", f"{a['pe_ratio']:.1f}x earnings"
                            )
                            idx += 1
                        if a["forward_pe"]:
                            f_cols[idx].metric(
                                "Expected Value",
                                f"{a['forward_pe']:.1f}x future earnings",
                            )
                            idx += 1
                        if a["dividend_yield"]:
                            f_cols[idx].metric(
                                "Yearly Dividend",
                                f"{a['dividend_yield']:.2f}% of price",
                            )
                            idx += 1
                        if a["sector"]:
                            f_cols[min(idx, 3)].metric("Industry", a["sector"])

                    # SIP performance
                    if sv:
                        st.caption("💰 SIP Performance")
                        sc1, sc2, sc3 = st.columns(3)
                        sc1.metric("Invested", f"₹{sv['invested']:,.0f}")
                        sc2.metric("Current", f"₹{sv['current_value']:,.0f}")
                        sc3.metric(
                            "Returns",
                            f"₹{sv['profit']:,.0f}",
                            f"{sv['returns_pct']:+.1f}%",
                        )

                    # Chart
                    try:
                        chart_data = yf.Ticker(h["ticker"]).history(period="1y")
                        if not chart_data.empty:
                            closes = chart_data["Close"]
                            chart_df = pd.DataFrame({"Price": closes})
                            if len(closes) >= 50:
                                chart_df["50-day MA"] = closes.rolling(50).mean()
                            st.line_chart(chart_df, height=250)
                    except Exception:
                        pass

                    # News with impact analysis
                    try:
                        ticker_news = fetch_ticker_news(
                            h["ticker"], h["name"], max_items=4
                        )
                        if ticker_news:
                            st.caption("📰 Recent News")
                            for ni in ticker_news:
                                impact = analyze_news_impact(
                                    ni, h["ticker"], h["name"], h["amount"]
                                )
                                s_label = impact["sentiment_label"]
                                if s_label == "Good news":
                                    box_color = "#27ae60"
                                elif s_label == "Bad news":
                                    box_color = "#e74c3c"
                                else:
                                    box_color = "#95a5a6"
                                st.markdown(
                                    f"""<div style="border-left: 4px solid {box_color}; padding: 8px 12px; margin: 6px 0; border-radius: 4px; background: {box_color}11;">
                                    <strong>{ni['title'][:100]}</strong>
                                    <span style="color: {box_color}; font-size: 0.85em;"> — {s_label}</span>
                                    <br><span style="font-size: 0.9em;">{impact['summary']}</span>
                                    <br><span style="font-size: 0.85em; opacity: 0.8;">👉 {impact['action']}</span>
                                    </div>""",
                                    unsafe_allow_html=True,
                                )
                    except Exception:
                        pass

                    # --- Should I Buy/Sell this stock? ---
                    st.caption("🤔 Should I Buy or Sell?")
                    try:
                        stock_pred = predict_stock_buy(h["ticker"], h["name"])
                        if stock_pred:
                            sig = stock_pred["signal"]
                            sig_colors = {
                                "BUY": ("#27ae60", "🟢"),
                                "LEAN BUY": ("#2ecc71", "🟢"),
                                "SELL": ("#e74c3c", "🔴"),
                                "LEAN SELL": ("#f39c12", "🟠"),
                                "WAIT": ("#f1c40f", "🟡"),
                            }
                            hex_c, sig_icon = sig_colors.get(sig, ("#f1c40f", "🟡"))
                            st.markdown(
                                f"""<div style="background: linear-gradient(135deg, {hex_c}22, {hex_c}11);
                                border-left: 4px solid {hex_c}; border-radius: 8px;
                                padding: 12px 16px; margin: 8px 0;">
                                <strong style="color: {hex_c};">{sig_icon} {sig}</strong> — {stock_pred['prediction']}
                                <br><span style="opacity: 0.7;">Confidence: {stock_pred['confidence']}%</span>
                                </div>""",
                                unsafe_allow_html=True,
                            )
                            with st.expander("📊 Detailed Buy/Sell Analysis"):
                                for factor, score, reason in stock_pred["reasons"]:
                                    if score > 0:
                                        bar_color = "#27ae60"
                                        f_icon = "🟢"
                                        label = f"+{score} Buy"
                                    elif score < 0:
                                        bar_color = "#e74c3c"
                                        f_icon = "🔴"
                                        label = f"{score} Sell"
                                    else:
                                        bar_color = "#95a5a6"
                                        f_icon = "⚪"
                                        label = "Neutral"
                                    bar_width = min(abs(score) * 3, 100)
                                    st.markdown(
                                        f"""<div style="margin: 6px 0;">
                                        <strong>{f_icon} {factor}</strong> <span style="color: {bar_color}; font-size: 0.9em;">[{label}]</span>
                                        <div style="background: #eee; border-radius: 4px; height: 6px; margin: 4px 0;">
                                            <div style="background: {bar_color}; width: {bar_width}%; height: 6px; border-radius: 4px;"></div>
                                        </div>
                                        <span style="font-size: 0.85em; opacity: 0.7;">{reason}</span>
                                        </div>""",
                                        unsafe_allow_html=True,
                                    )
                                st_score = stock_pred["total_score"]
                                st_sc = (
                                    "#27ae60"
                                    if st_score > 0
                                    else "#e74c3c" if st_score < 0 else "#95a5a6"
                                )
                                st.markdown(
                                    f"**Total Score:** <span style='color: {st_sc}; font-size: 1.2em;'>{st_score:+d}</span>",
                                    unsafe_allow_html=True,
                                )
                    except Exception:
                        pass

            # Action alerts at bottom
            st.divider()
            alerts = []
            for r in results:
                a = r["analysis"]
                if a is None:
                    continue
                name = r["holding"]["name"]
                if a["rsi"] is not None and a["rsi"] <= 30:
                    alerts.append(
                        f"🟢 **{name}** has been falling a lot and looks cheap — could be a good time to buy more"
                    )
                if a["rsi"] is not None and a["rsi"] >= 70:
                    alerts.append(
                        f"⚠️ **{name}** has been rising fast and may be too expensive — consider selling some to lock in gains"
                    )
                if a["from_high_pct"] and a["from_high_pct"] < -20:
                    alerts.append(
                        f"📉 **{name}** is {abs(a['from_high_pct']):.0f}% lower than its best price in the last year — it has dropped a lot"
                    )

            if alerts:
                st.subheader("⚡ Action Alerts")
                for alert in alerts:
                    st.markdown(alert)


# ============================================================
# PAGE: Market Scanner
# ============================================================
elif page == "🔎 Market Scanner":
    st.title("🔎 Market Opportunity Scanner")

    scan_tab1, scan_tab2, scan_tab3, scan_tab4 = st.tabs(
        [
            "🚀 Top Movers",
            "💡 What Should I Buy?",
            "🔄 Sell & Replace",
            "🏭 Sector Heatmap",
        ]
    )

    with scan_tab1:
        st.caption("⏱️ **Short-term** — based on today's price change vs yesterday")
        with st.spinner("Scanning top Indian stocks..."):
            try:
                gainers, losers = scan_top_movers(top_n=5)

                g_col, l_col = st.columns(2)

                with g_col:
                    st.subheader("🟢 Top Gainers")
                    if gainers:
                        for g in gainers:
                            st.markdown(
                                f"**{g['name']}** — ₹{g['price']:,.2f} `{g['change_pct']:+.2f}%`"
                            )
                            # Context: why did it move and is it sustainable?
                            hints = []
                            rsi = g.get("rsi")
                            vol = g.get("vol_ratio")
                            streak = g.get("streak", 0)
                            if rsi and rsi >= 70:
                                hints.append("⚠️ Already overbought — risky to chase")
                            elif rsi and rsi >= 60:
                                hints.append("Getting expensive — be cautious")
                            elif rsi and rsi <= 40:
                                hints.append(
                                    "Was undervalued — this bounce could continue"
                                )
                            if vol and vol >= 2:
                                hints.append(
                                    f"Volume {vol}x higher than usual — strong interest"
                                )
                            if streak >= 3:
                                hints.append(
                                    f"Up {streak} days in a row — may need a breather"
                                )
                            if hints:
                                st.caption(" · ".join(hints))
                            else:
                                st.caption(
                                    "Normal move — watch for a few days before acting"
                                )
                    else:
                        st.caption("No data")

                with l_col:
                    st.subheader("🔴 Top Losers")
                    if losers:
                        for l in losers:
                            st.markdown(
                                f"**{l['name']}** — ₹{l['price']:,.2f} `{l['change_pct']:+.2f}%`"
                            )
                            hints = []
                            rsi = l.get("rsi")
                            vol = l.get("vol_ratio")
                            if rsi and rsi <= 30:
                                hints.append("🟢 Oversold — could bounce back soon")
                            elif rsi and rsi <= 40:
                                hints.append("Getting cheap — watch for reversal")
                            elif rsi and rsi >= 60:
                                hints.append("Was expensive — correction may continue")
                            if vol and vol >= 2:
                                hints.append(f"Volume {vol}x higher — heavy selling")
                            if hints:
                                st.caption(" · ".join(hints))
                            else:
                                st.caption(
                                    "Short-term drop — could bounce back or fall further"
                                )
                    else:
                        st.caption("No data")
            except Exception as e:
                st.warning(f"Could not scan: {e}")

    with scan_tab2:
        st.caption("Stocks that have fallen significantly and could be good buys")
        with st.spinner("Analyzing stocks..."):
            try:
                opps = scan_oversold_opportunities()
                if opps:
                    for o in opps:
                        urgency_colors = {
                            "high": "#27ae60",
                            "medium": "#f39c12",
                            "low": "#95a5a6",
                        }
                        urgency_labels = {
                            "high": "🟢 Good time to buy",
                            "medium": "🟡 Okay to buy, but can wait",
                            "low": "⚪ Wait for a better price",
                        }
                        u_color = urgency_colors.get(o["urgency"], "#95a5a6")
                        u_label = urgency_labels.get(o["urgency"], "")

                        with st.expander(
                            f"{'🟢' if o['urgency'] == 'high' else '🟡' if o['urgency'] == 'medium' else '⚪'} "
                            f"**{o['name']}** — ₹{o['price']:,.2f}"
                        ):
                            # Price context
                            p1, p2, p3 = st.columns(3)
                            p1.metric("Current Price", f"₹{o['price']:,.2f}")
                            p2.metric(
                                "Yearly High",
                                f"₹{o['high_52w']:,.2f}",
                                f"{o['from_high_pct']:+.1f}%",
                            )
                            p3.metric("Yearly Low", f"₹{o['low_52w']:,.2f}")

                            # Why is it cheap?
                            st.markdown("**Why is it cheap right now?**")
                            for reason in o["why_cheap"]:
                                st.markdown(f"• {reason}")

                            # Buy verdict
                            st.markdown(
                                f"""<div style="border-left: 4px solid {u_color}; padding: 10px 14px; margin: 10px 0;
                                border-radius: 4px; background: {u_color}11;">
                                <strong>Should I buy today?</strong> {o['buy_verdict']}
                                <br><span style="font-size: 0.85em; opacity: 0.8;">{' · '.join(o['buy_reasoning'])}</span>
                                </div>""",
                                unsafe_allow_html=True,
                            )

                            if o["pe_ratio"]:
                                pe_hint = (
                                    "Cheap"
                                    if o["pe_ratio"] < 15
                                    else "Fair" if o["pe_ratio"] < 25 else "Expensive"
                                )
                                st.caption(
                                    f"Valuation: PE {o['pe_ratio']:.0f}x ({pe_hint}) · Sector: {o['sector'] or 'N/A'}"
                                )
                else:
                    st.info(
                        "No cheap stocks found right now — the market looks fairly priced."
                    )
            except Exception as e:
                st.warning(f"Error: {e}")

    with scan_tab3:
        st.caption(
            "Want to sell a stock? See what you could buy instead with that money."
        )

        # Load portfolio for the dropdown
        try:
            swap_holdings = load_portfolio_extended()
            stock_holdings = [
                h for h in swap_holdings if h["type"] == "stock" and h["ticker"]
            ]

            if stock_holdings:
                stock_options = {
                    f"{h['name']} (₹{h['amount']:,.0f})": h for h in stock_holdings
                }
                selected = st.selectbox(
                    "Which stock do you want to sell?",
                    options=list(stock_options.keys()),
                    index=None,
                    placeholder="Pick a stock from your portfolio...",
                )

                if selected:
                    sell_holding = stock_options[selected]
                    sell_amount = sell_holding["amount"]

                    st.info(
                        f"If you sell **{sell_holding['name']}**, you'll have approximately **₹{sell_amount:,.0f}** to invest elsewhere."
                    )

                    with st.spinner(
                        f"Finding stocks you can buy with ₹{sell_amount:,.0f}..."
                    ):
                        swaps = suggest_stock_swaps(
                            sell_holding["ticker"], sell_amount, swap_holdings
                        )

                        if swaps:
                            st.subheader(
                                f"💡 Stocks you can buy with ₹{sell_amount:,.0f}"
                            )

                            for s in swaps[:8]:
                                score_color = (
                                    "#27ae60"
                                    if s["score"] >= 3
                                    else "#f39c12" if s["score"] >= 1 else "#95a5a6"
                                )
                                score_label = (
                                    "Strong pick"
                                    if s["score"] >= 3
                                    else "Decent pick" if s["score"] >= 1 else "Okay"
                                )

                                with st.expander(
                                    f"{'🟢' if s['score'] >= 3 else '🟡' if s['score'] >= 1 else '⚪'} "
                                    f"**{s['name']}** — ₹{s['price']:,.2f}/share · Buy {s['shares']} shares"
                                ):
                                    m1, m2, m3 = st.columns(3)
                                    m1.metric(
                                        "You'd invest", f"₹{s['investment']:,.0f}"
                                    )
                                    m2.metric("Shares you get", f"{s['shares']}")
                                    m3.metric(
                                        "Money left over", f"₹{s['leftover']:,.0f}"
                                    )

                                    if s["pros"]:
                                        st.markdown("**Why this stock?**")
                                        for pro in s["pros"]:
                                            st.markdown(f"✅ {pro}")
                                    if s["cons"]:
                                        for con in s["cons"]:
                                            st.markdown(f"⚠️ {con}")

                                    extra = []
                                    if s["pe_ratio"]:
                                        pe_hint = (
                                            "Cheap"
                                            if s["pe_ratio"] < 15
                                            else (
                                                "Fair"
                                                if s["pe_ratio"] < 25
                                                else "Expensive"
                                            )
                                        )
                                        extra.append(
                                            f"PE {s['pe_ratio']:.0f}x ({pe_hint})"
                                        )
                                    if s["sector"]:
                                        extra.append(f"Sector: {s['sector']}")
                                    if extra:
                                        st.caption(" · ".join(extra))
                        else:
                            st.info(
                                "No good replacement stocks found at this price range right now."
                            )
            else:
                st.info("No stocks in your portfolio to sell.")
        except Exception as e:
            st.warning(f"Could not load portfolio: {e}")

    with scan_tab4:
        st.caption(
            "⏱️ **Short-term** — today's average change across stocks in each sector"
        )
        with st.spinner("Analyzing sectors..."):
            try:
                sector_perf = scan_sector_performance()
                if sector_perf:
                    # Bar chart of sector averages
                    chart_data = {s: d["avg_change"] for s, d in sector_perf.items()}
                    sorted_chart = dict(
                        sorted(chart_data.items(), key=lambda x: x[1], reverse=True)
                    )
                    st.bar_chart(
                        pd.Series(sorted_chart, name="Daily Change %"), height=350
                    )

                    for sector, data in sector_perf.items():
                        change = data["avg_change"]
                        stocks = data["stocks"]
                        icon = "🟢" if change >= 0 else "🔴"
                        if abs(change) >= 2:
                            strength = "Big move today"
                        elif abs(change) >= 1:
                            strength = "Moderate move"
                        else:
                            strength = "Quiet day"

                        with st.expander(
                            f"{icon} **{sector}**: {change:+.2f}% — {strength}"
                        ):
                            # Top gainer
                            best = stocks[0]
                            worst = stocks[-1]
                            bc, wc = st.columns(2)
                            with bc:
                                st.markdown(f"🟢 **Top Gainer**")
                                st.metric(
                                    best["name"],
                                    f"₹{best['price']:,.2f}",
                                    f"{best['change_pct']:+.2f}%",
                                )
                            with wc:
                                st.markdown(f"🔴 **Top Loser**")
                                st.metric(
                                    worst["name"],
                                    f"₹{worst['price']:,.2f}",
                                    f"{worst['change_pct']:+.2f}%",
                                )

                            # All stocks in sector
                            if len(stocks) > 2:
                                st.markdown("**All stocks:**")
                                for s in stocks:
                                    s_icon = "🟢" if s["change_pct"] >= 0 else "🔴"
                                    st.markdown(
                                        f"{s_icon} {s['name']} — ₹{s['price']:,.2f} `{s['change_pct']:+.2f}%`"
                                    )
                else:
                    st.caption("No sector data")
            except Exception as e:
                st.warning(f"Error: {e}")


# ============================================================
# PAGE: News
# ============================================================
elif page == "📰 News":
    st.title("📰 Market News — Quick Summary")
    st.caption(
        "Key headlines with short takeaways so you don't have to read everything"
    )

    news_tab1, news_tab2, news_tab3, news_tab4 = st.tabs(
        ["📊 Stocks", "🪙 Gold", "📈 Mutual Funds", "💡 Opportunities"]
    )

    categories = {
        "📊 Stocks": "Indian Stock Market",
        "🪙 Gold": "Gold Price India",
        "📈 Mutual Funds": "Mutual Funds India",
        "💡 Opportunities": "Investment Opportunities",
    }

    sentiment_labels = {
        "bullish": ("🟢", "Positive for markets"),
        "bearish": ("🔴", "Negative for markets"),
        "neutral": ("⚪", "Neutral"),
    }

    for tab, (label, category) in zip(
        [news_tab1, news_tab2, news_tab3, news_tab4], categories.items()
    ):
        with tab:
            try:
                news_items = fetch_news(category=category, max_items=8)
                if news_items:
                    # Quick sentiment summary at top
                    bull = sum(1 for n in news_items if n["sentiment"] == "bullish")
                    bear = sum(1 for n in news_items if n["sentiment"] == "bearish")
                    neutral = len(news_items) - bull - bear

                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("🟢 Positive", f"{bull} stories")
                    sc2.metric("🔴 Negative", f"{bear} stories")
                    sc3.metric("⚪ Neutral", f"{neutral} stories")

                    if bull > bear:
                        st.success(
                            "Overall mood: **Positive** — more good news than bad today"
                        )
                    elif bear > bull:
                        st.warning(
                            "Overall mood: **Negative** — more concerning news today"
                        )
                    else:
                        st.info(
                            "Overall mood: **Mixed** — no clear direction in the news"
                        )

                    st.divider()

                    for item in news_items:
                        icon, mood = sentiment_labels.get(
                            item["sentiment"], ("⚪", "Neutral")
                        )
                        summary = item.get("summary", "")

                        with st.container():
                            st.markdown(f"**{icon} {item['title']}**")
                            if summary:
                                st.caption(f"📝 {summary}")
                            col_link, col_mood = st.columns([3, 1])
                            with col_link:
                                pub = item.get("published", "")
                                if pub:
                                    st.caption(f"🕐 {pub}")
                            with col_mood:
                                st.caption(f"Mood: {mood}")
                            st.markdown(f"[Read full article →]({item['link']})")
                            st.markdown("---")
                else:
                    st.caption("No news available")
            except Exception:
                st.caption("Could not fetch news")

    # --- What Should I Do? section ---
    st.divider()
    st.subheader("🧭 What Should I Do Next?")
    st.caption("Suggestions based on today's news and your portfolio")

    try:
        # Gather all news across categories
        all_news = []
        for cat_query in categories.values():
            all_news.extend(fetch_news(category=cat_query, max_items=5))

        total_bull = sum(1 for n in all_news if n["sentiment"] == "bullish")
        total_bear = sum(1 for n in all_news if n["sentiment"] == "bearish")
        news_titles_lower = " ".join(n["title"].lower() for n in all_news)

        suggestions = []

        # 1. Overall market mood → action
        if total_bear > total_bull + 3:
            suggestions.append(
                (
                    "🛡️",
                    "**Don't panic sell** — News is mostly negative today. Avoid making emotional decisions. If you have cash, this could be a buying opportunity for quality stocks.",
                )
            )
        elif total_bull > total_bear + 3:
            suggestions.append(
                (
                    "📈",
                    "**Markets look positive** — Good time to review your portfolio and consider adding to your winners. But don't chase prices that have already run up too much.",
                )
            )
        else:
            suggestions.append(
                (
                    "⏳",
                    "**Stay patient** — News is mixed today. No rush to buy or sell. Stick to your plan and wait for a clearer signal.",
                )
            )

        # --- Dynamic portfolio-matched suggestions ---
        # Build keyword → holdings mapping from actual portfolio
        if holdings:
            total_invested = sum(h["amount"] for h in holdings)

            # Map sector/keyword patterns to holdings
            keyword_map = {
                "gold": {
                    "keywords": [
                        "gold",
                        "yellow metal",
                        "precious metal",
                        "gold price",
                    ],
                    "rise_keywords": [
                        "gold rise",
                        "gold surge",
                        "gold high",
                        "gold rally",
                        "gold record",
                    ],
                    "fall_keywords": [
                        "gold fall",
                        "gold drop",
                        "gold crash",
                        "gold dip",
                        "gold decline",
                    ],
                    "icon": "🪙",
                    "sector": "gold",
                },
                "silver": {
                    "keywords": ["silver", "silver price"],
                    "rise_keywords": [
                        "silver rise",
                        "silver surge",
                        "silver high",
                        "silver rally",
                    ],
                    "fall_keywords": [
                        "silver fall",
                        "silver drop",
                        "silver crash",
                        "silver dip",
                    ],
                    "icon": "🥈",
                    "sector": "silver",
                },
                "auto": {
                    "keywords": [
                        "tata motors",
                        "auto",
                        "automobile",
                        "car sales",
                        "ev",
                        "maruti",
                        "mahindra",
                    ],
                    "icon": "🚗",
                    "sector": "auto",
                },
                "banking": {
                    "keywords": [
                        "bank",
                        "rbi",
                        "interest rate",
                        "rate cut",
                        "npa",
                        "credit",
                        "hdfc",
                        "icici",
                        "sbi",
                        "idfc",
                    ],
                    "icon": "🏦",
                    "sector": "banking",
                },
                "it": {
                    "keywords": [
                        "tcs",
                        "infosys",
                        "it sector",
                        "tech stock",
                        "wipro",
                        "hcl tech",
                    ],
                    "icon": "💻",
                    "sector": "it",
                },
                "mf": {
                    "keywords": [
                        "mutual fund",
                        "sip",
                        "nav",
                        "amfi",
                        "small cap",
                        "nifty",
                        "index fund",
                    ],
                    "icon": "📊",
                    "sector": "mf",
                },
                "energy": {
                    "keywords": [
                        "oil",
                        "ongc",
                        "reliance",
                        "energy",
                        "crude",
                        "petrol",
                        "gas",
                    ],
                    "icon": "⛽",
                    "sector": "energy",
                },
            }

            # Find which holdings match each sector
            def _find_holdings_for_sector(sector_key):
                """Find portfolio holdings related to a sector."""
                matches = []
                sector_tickers = {
                    "gold": ["goldbees", "gold"],
                    "silver": ["silverbees", "silver"],
                    "auto": ["tmcv", "tmpv", "tata motor", "maruti", "m&m"],
                    "banking": [
                        "bank",
                        "idfc",
                        "hdfc",
                        "icici",
                        "sbi",
                        "kotak",
                        "axis",
                    ],
                    "it": ["tcs", "infy", "hcl", "wipro", "techm", "infosys"],
                    "mf": [],  # handled separately via type
                    "energy": ["ongc", "reliance", "ntpc", "power", "coal"],
                }
                patterns = sector_tickers.get(sector_key, [])
                for h in holdings:
                    name_lower = h["name"].lower()
                    ticker_lower = (h.get("ticker") or "").lower()
                    if sector_key == "mf" and h["type"] == "mutual_fund":
                        matches.append(h)
                    elif any(p in name_lower or p in ticker_lower for p in patterns):
                        matches.append(h)
                return matches

            for sector_key, config in keyword_map.items():
                if not any(kw in news_titles_lower for kw in config["keywords"]):
                    continue

                matched = _find_holdings_for_sector(sector_key)
                icon = config["icon"]

                if matched:
                    names = ", ".join(
                        f"{h['name']} (₹{h['amount']:,.0f})" for h in matched[:3]
                    )
                    total_sector = sum(h["amount"] for h in matched)
                    pct = (total_sector / total_invested) * 100

                    # Check if it's rise or fall news for gold/silver
                    if "rise_keywords" in config and any(
                        kw in news_titles_lower for kw in config["rise_keywords"]
                    ):
                        if pct > 15:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} is rising** — You hold {names} ({pct:.0f}% of portfolio). Consider booking partial profits on your larger positions.",
                                )
                            )
                        else:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} is rising** — You hold {names}. Good news for your positions — hold and let gains grow.",
                                )
                            )
                    elif "fall_keywords" in config and any(
                        kw in news_titles_lower for kw in config["fall_keywords"]
                    ):
                        if total_sector < 2000:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} is dipping** — You hold {names}. Your position is small — could be a good time to add more at lower prices.",
                                )
                            )
                        else:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} is dipping** — You hold {names}. Watch closely — if fundamentals are strong, this dip is a buying opportunity.",
                                )
                            )
                    else:
                        # General news about sector
                        if sector_key == "mf":
                            sip_holdings = [
                                h for h in matched if h.get("sip_monthly", 0) > 0
                            ]
                            if sip_holdings:
                                sip_names = ", ".join(
                                    f"{h['name']} ₹{int(h['sip_monthly']):,}/month"
                                    for h in sip_holdings
                                )
                                suggestions.append(
                                    (
                                        icon,
                                        f"**Mutual fund news** — Your SIPs: {sip_names}. Continue regardless of short-term news — SIPs benefit from market dips.",
                                    )
                                )
                            else:
                                suggestions.append(
                                    (
                                        icon,
                                        f"**Mutual fund news** — You hold {names}. Consider starting a monthly SIP for consistent investing.",
                                    )
                                )
                        else:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} sector news** — You hold {names} ({pct:.0f}% of portfolio). Check the news tab for details on how this affects your holdings.",
                                )
                            )
                else:
                    # User doesn't own this sector
                    if sector_key not in (
                        "mf",
                    ):  # Only suggest buying for stock sectors
                        suggestions.append(
                            (
                                icon,
                                f"**{sector_key.title()} sector news** — You don't own {sector_key} stocks. If news is negative and prices drop, it could be a buying opportunity.",
                            )
                        )

            # General diversification check
            top_holding = max(holdings, key=lambda h: h["amount"])
            top_pct = (top_holding["amount"] / total_invested) * 100
            if top_pct > 50:
                suggestions.append(
                    (
                        "⚖️",
                        f"**Diversify** — {top_holding['name']} is {top_pct:.0f}% of your portfolio. Regardless of news, consider spreading across more stocks or funds.",
                    )
                )

        if not suggestions:
            suggestions.append(
                (
                    "✅",
                    "**All good** — No major news affecting your portfolio today. Continue your SIPs and review again next week.",
                )
            )

        for icon, text in suggestions:
            st.markdown(f"{icon} {text}")
            st.markdown("")

    except Exception:
        st.info("Could not generate suggestions. Check back when markets are open.")


# ============================================================
# PAGE: Budget
# ============================================================
elif page == "💰 Budget":
    st.title("💰 Monthly Budget Tracker")

    col_x, col_y, col_z = st.columns(3)
    income = col_x.number_input("Monthly Income (₹)", value=109000, step=1000)
    expenses = col_y.number_input("Monthly Expenses (₹)", value=47800, step=1000)
    investments = col_z.number_input("Monthly Investments (₹)", value=19475, step=1000)

    remaining = income - expenses - investments
    savings_rate = round((investments / income) * 100, 1) if income > 0 else 0

    st.divider()

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Remaining", f"₹{remaining:,.0f}")
    r2.metric("Savings Rate", f"{savings_rate}%")
    r3.metric(
        "Expense Ratio",
        f"{round((expenses / income) * 100, 1)}%" if income > 0 else "0%",
    )
    r4.metric(
        "Investment Ratio",
        f"{round((investments / income) * 100, 1)}%" if income > 0 else "0%",
    )

    if remaining > 20000:
        st.warning(f"⚠️ ₹{remaining:,.0f} unused — consider investing more!")
    elif remaining < 0:
        st.error(f"🚨 Overspending by ₹{abs(remaining):,.0f}!")
    else:
        st.success("✅ Budget looks healthy!")

    st.divider()

    # Visual breakdown
    st.subheader("📊 Breakdown")
    breakdown = {
        "Expenses": expenses,
        "Investments": investments,
        "Remaining": max(remaining, 0),
    }
    st.bar_chart(pd.Series(breakdown, name="₹"), height=300)


# --- Sidebar Footer ---
st.sidebar.divider()
st.sidebar.caption("Data: Yahoo Finance, AMFI India, Google News")
st.sidebar.caption("Built with Streamlit")
