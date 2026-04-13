import streamlit as st
import pandas as pd
import yfinance as yf

from analysis import (
    analyze_gold_trend,
    predict_gold_buy,
    save_gold_prediction,
    verify_gold_predictions,
    get_silver_price,
    analyze_silver_trend,
    predict_silver_buy,
    save_silver_prediction,
    verify_silver_predictions,
    get_prediction_learnings,
)
from ui_helpers import (
    metal_inr_series,
    render_verdict_card,
    render_factor_bars,
    render_total_score,
    render_signal_legend,
    render_track_record,
    render_learnings,
    render_price_history,
)


def render(holdings):
    st.title("🪙 Gold & Silver Prices")
    st.caption("Chennai approximate rates (international futures × USD/INR)")

    gold_tab, silver_tab = st.tabs(["🪙 Gold", "🥈 Silver"])

    with gold_tab:
        try:
            gold_ticker = yf.Ticker("GC=F")
            usd_inr_ticker = yf.Ticker("USDINR=X")
            gold_hist = gold_ticker.history(period="1mo")
            fx_hist = usd_inr_ticker.history(period="1mo")

            gold_inr_per_gram = metal_inr_series(gold_hist, fx_hist, premium=1.03)

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
                    gold_chart = pd.DataFrame({"Gold ₹/gram": gold_inr_per_gram})
                    if gold_chart.index.tz is not None:
                        gold_chart.index = gold_chart.index.tz_localize(None)
                    st.line_chart(gold_chart, height=300)

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
                    "Based on 12 market indicators including momentum, trend, news, and global factors"
                )

                with st.spinner("Analyzing gold..."):
                    gold_pred = predict_gold_buy(use_news=True)

                if gold_pred:
                    signal = gold_pred["signal"]
                    conf = gold_pred["confidence"]

                    render_verdict_card(signal, gold_pred["prediction"])

                    pc1, pc2, pc3 = st.columns(3)
                    pc1.metric("Current Price", f"₹{gold_pred['current_price']:,.2f}/g")
                    pc2.metric("Confidence", f"{conf}%")
                    buy_factors = sum(1 for _, s, _ in gold_pred["reasons"] if s > 0)
                    sell_factors = sum(1 for _, s, _ in gold_pred["reasons"] if s < 0)
                    pc3.metric("Factors", f"{buy_factors} Buy / {sell_factors} Sell")

                    # Risk warning
                    risk_lvl = gold_pred.get("risk_level", "")
                    risk_warn = gold_pred.get("risk_warning", "")
                    if risk_lvl in ("Very High", "High"):
                        st.warning(f"**Risk Level: {risk_lvl}** — {risk_warn}")
                    elif risk_lvl == "Moderate" and risk_warn:
                        st.info(f"**Risk Level: {risk_lvl}** — {risk_warn}")

                    with st.expander("ℹ️ What do these signals mean?"):
                        render_signal_legend()

                    with st.expander("📊 Detailed Analysis — Why this signal?"):
                        render_factor_bars(gold_pred["reasons"])
                        st.markdown("---")
                        render_total_score(gold_pred["total_score"])

                    # Save today's prediction
                    save_gold_prediction(gold_pred)

                    # Verify past predictions
                    past_preds = verify_gold_predictions()
                    verified = [p for p in past_preds if p.get("verified")]
                    if verified:
                        with st.expander(
                            f"📈 Prediction Track Record ({len(verified)} verified)"
                        ):
                            render_track_record(verified, "gold")

                    # Self-learning
                    gold_learnings = get_prediction_learnings("gold")
                    if gold_learnings and gold_learnings.get("learnings"):
                        with st.expander(
                            f"🧠 What I Learned from My Mistakes ({gold_learnings['total_verified']} analysed)"
                        ):
                            render_learnings(gold_learnings, "gold")
                else:
                    st.warning("Could not generate gold prediction — data unavailable")

                # --- Gold Price History: Big Moves ---
                st.divider()
                st.subheader("📜 Gold Price History — Significant Moves")
                render_price_history("Gold", "GC=F", 1.03, "gold_period")
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
                sv_inr_1mo = metal_inr_series(sv_hist, fx_sv, premium=1.05)
                if sv_inr_1mo is not None and len(sv_inr_1mo) > 0:
                    silver_chart = pd.DataFrame({"Silver ₹/gram": sv_inr_1mo})
                    if silver_chart.index.tz is not None:
                        silver_chart.index = silver_chart.index.tz_localize(None)
                    st.line_chart(silver_chart, height=300)

                # --- Should I Buy Silver? ---
                st.divider()
                st.subheader("🤔 Should I Buy Silver Now?")
                st.caption(
                    "Based on 12 market indicators including momentum, trend, news, and global factors"
                )

                with st.spinner("Analyzing silver..."):
                    silver_pred = predict_silver_buy(use_news=True)

                if silver_pred:
                    sig = silver_pred["signal"]
                    conf = silver_pred["confidence"]

                    render_verdict_card(sig, silver_pred["prediction"])

                    sp1, sp2, sp3 = st.columns(3)
                    sp1.metric(
                        "Current Price", f"₹{silver_pred['current_price']:,.2f}/g"
                    )
                    sp2.metric("Confidence", f"{conf}%")
                    buy_f = sum(1 for _, s, _ in silver_pred["reasons"] if s > 0)
                    sell_f = sum(1 for _, s, _ in silver_pred["reasons"] if s < 0)
                    sp3.metric("Factors", f"{buy_f} Buy / {sell_f} Sell")

                    # Risk warning
                    sv_risk_lvl = silver_pred.get("risk_level", "")
                    sv_risk_warn = silver_pred.get("risk_warning", "")
                    if sv_risk_lvl in ("Very High", "High"):
                        st.warning(f"**Risk Level: {sv_risk_lvl}** — {sv_risk_warn}")
                    elif sv_risk_lvl == "Moderate" and sv_risk_warn:
                        st.info(f"**Risk Level: {sv_risk_lvl}** — {sv_risk_warn}")

                    with st.expander("📊 Detailed Analysis — Why this signal?"):
                        render_factor_bars(silver_pred["reasons"])
                        render_total_score(silver_pred["total_score"])

                    save_silver_prediction(silver_pred)

                    sv_past = verify_silver_predictions()
                    sv_verified = [p for p in sv_past if p.get("verified")]
                    if sv_verified:
                        with st.expander(
                            f"📈 Prediction Track Record ({len(sv_verified)} verified)"
                        ):
                            render_track_record(sv_verified, "silver")

                    silver_learnings = get_prediction_learnings("silver")
                    if silver_learnings and silver_learnings.get("learnings"):
                        with st.expander(
                            f"🧠 What I Learned from Silver Mistakes ({silver_learnings['total_verified']} analysed)"
                        ):
                            render_learnings(silver_learnings, "silver")

                else:
                    st.warning(
                        "Could not generate silver prediction — data unavailable"
                    )

                # --- Silver Price History: Big Moves ---
                st.divider()
                st.subheader("📜 Silver Price History — Significant Moves")
                render_price_history("Silver", "SI=F", 1.05, "silver_period")
            else:
                st.warning("Could not fetch silver data")
        except Exception as e:
            st.warning(f"Silver data unavailable: {e}")
