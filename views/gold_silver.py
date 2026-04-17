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
    predict_gold_buy_day,
    save_gold_buyday_prediction,
    verify_gold_buyday_predictions,
    learn_gold_buyday,
    analyze_gold_price_drivers,
    fetch_chennai_rates,
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


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_metal_and_fx(metal_ticker, period="1mo"):
    """Cached fetch of metal + USD/INR data — avoids redundant FX fetches."""
    try:
        metal_hist = yf.Ticker(metal_ticker).history(period=period)
        fx_hist = yf.Ticker("USDINR=X").history(period=period)
        return metal_hist, fx_hist
    except Exception:
        return None, None


@st.fragment()
def _gold_tab_fragment():
    """Fragment — gold section re-runs independently of silver."""
    try:
        # Timeframe selector for gold chart
        gold_periods = {"1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
        gold_period_label = st.radio(
            "Chart Period",
            list(gold_periods.keys()),
            index=1,
            horizontal=True,
            key="gold_chart_period",
        )
        gold_yf_period = gold_periods[gold_period_label]

        gold_hist, fx_hist = _fetch_metal_and_fx("GC=F", gold_yf_period)

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
            g2.metric("8 Grams (24K)", f"₹{latest_8g:,.2f}", f"₹{change_1g * 8:+,.2f}")

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
                "Based on 12 market indicators including momentum, trend, news, and global factors. "
                "*Prediction uses recent 1-month data regardless of chart timeframe above.*"
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


@st.fragment()
def _silver_tab_fragment():
    """Fragment — silver section re-runs independently of gold."""
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

            # Chart — reuse cached FX data with timeframe selector
            silver_periods = {
                "1W": "5d",
                "1M": "1mo",
                "3M": "3mo",
                "6M": "6mo",
                "1Y": "1y",
            }
            silver_period_label = st.radio(
                "Chart Period",
                list(silver_periods.keys()),
                index=1,
                horizontal=True,
                key="silver_chart_period",
            )
            silver_yf_period = silver_periods[silver_period_label]

            sv_hist, fx_sv = _fetch_metal_and_fx("SI=F", silver_yf_period)
            if sv_hist is not None and fx_sv is not None:
                sv_inr_1mo = metal_inr_series(sv_hist, fx_sv, premium=1.05)
            else:
                sv_inr_1mo = None
            if sv_inr_1mo is not None and len(sv_inr_1mo) > 0:
                silver_chart = pd.DataFrame({"Silver ₹/gram": sv_inr_1mo})
                if silver_chart.index.tz is not None:
                    silver_chart.index = silver_chart.index.tz_localize(None)
                st.line_chart(silver_chart, height=300)

            # --- Should I Buy Silver? ---
            st.divider()
            st.subheader("🤔 Should I Buy Silver Now?")
            st.caption(
                "Based on 12 market indicators including momentum, trend, news, and global factors. "
                "*Prediction uses recent 1-month data regardless of chart timeframe above.*"
            )

            with st.spinner("Analyzing silver..."):
                silver_pred = predict_silver_buy(use_news=True)

            if silver_pred:
                sig = silver_pred["signal"]
                conf = silver_pred["confidence"]

                render_verdict_card(sig, silver_pred["prediction"])

                sp1, sp2, sp3 = st.columns(3)
                sp1.metric("Current Price", f"₹{silver_pred['current_price']:,.2f}/g")
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
                st.warning("Could not generate silver prediction — data unavailable")

            # --- Silver Price History: Big Moves ---
            st.divider()
            st.subheader("📜 Silver Price History — Significant Moves")
            render_price_history("Silver", "SI=F", 1.05, "silver_period")
        else:
            st.warning("Could not fetch silver data")
    except Exception as e:
        st.warning(f"Silver data unavailable: {e}")


def render(holdings):
    st.title("🪙 Gold & Silver Prices")
    st.caption(
        "Chennai retail rates via livechennai.com · Fallback: international futures × USD/INR"
    )

    gold_tab, silver_tab, buyday_tab, ratio_tab = st.tabs(
        ["🪙 Gold", "🥈 Silver", "📅 Best Buy Day", "📊 Gold:Silver Ratio"]
    )

    with gold_tab:
        _gold_tab_fragment()

    with silver_tab:
        _silver_tab_fragment()

    with buyday_tab:
        _buyday_tab_fragment()

    with ratio_tab:
        _ratio_tab_fragment()


@st.fragment()
def _buyday_tab_fragment():
    """Fragment — gold buy-day prediction runs independently."""
    st.subheader("📅 Best Day of the Month to Buy Gold")
    st.caption(
        "Analyzes 3 years of price history + macro indicators (VIX, DXY, "
        "volatility regime, day-of-week) to find the optimal buy day. "
        "Self-improves every month."
    )

    with st.spinner("Analyzing 3 years of gold price patterns + macro data..."):
        prediction = predict_gold_buy_day()

    if prediction:
        # --- Top recommendation ---
        best = prediction["best_days"]
        confidence = prediction["confidence"]
        month = prediction["month"]

        st.success(
            f"🎯 **Recommended buy days for {month}:** "
            f"Day **{best[0]}**, **{best[1]}**, or **{best[2]}** "
            f"(Confidence: {confidence}%)"
        )

        # Buy window / strategy advice
        buy_window = prediction.get("buy_window", (best[0], best[0]))
        buy_strategy = prediction.get("buy_strategy", "flexible")
        if buy_strategy == "split":
            st.warning(
                f"📊 **High uncertainty detected** — consider splitting your purchase "
                f"across Day {buy_window[0]}–{buy_window[1]} to reduce timing risk"
            )
        elif buy_strategy == "target":
            st.info(
                f"🎯 **Low volatility** — market is calm, target Day {best[0]} "
                f"for the best price"
            )
        else:
            st.info(
                f"📅 **Flexible window:** Day {buy_window[0]}–{buy_window[1]} — "
                f"any day in this range should be close to the monthly low"
            )

        m1, m2, m3 = st.columns(3)
        m1.metric("Current Gold Price", f"₹{prediction['current_price']:,.2f}/g")
        m2.metric("Best Day (Top Pick)", f"Day {best[0]}")
        m3.metric("Confidence", f"{confidence}%")

        # --- Macro context indicators ---
        mc1, mc2, mc3, mc4 = st.columns(4)
        vol_regime = prediction.get("vol_regime", "—")
        vol_icon = {"low": "🟢", "mid": "🟡", "high": "🔴"}.get(vol_regime, "⚪")
        mc1.metric("Volatility", f"{vol_icon} {vol_regime.title()}")
        vix = prediction.get("vix_level", "—")
        mc2.metric("VIX", f"{vix}")
        dxy = prediction.get("dxy_trend", "—")
        dxy_icon = {"rising": "📈", "falling": "📉", "neutral": "➡️"}.get(dxy, "⚪")
        mc3.metric("Dollar Trend", f"{dxy_icon} {dxy.title()}")
        events = prediction.get("news_events", [])
        mc4.metric("Event Risk", f"{len(events)} active" if events else "None")

        # --- Reasoning ---
        st.divider()
        st.markdown("##### 📊 Why These Days?")
        for r in prediction["reasoning"]:
            st.markdown(f"• {r}")

        # --- Avoid days ---
        worst = prediction["worst_days"]
        st.divider()
        st.markdown("##### 🚫 Days to Avoid")
        worst_detail = prediction["worst_day_detail"]
        for wd in worst_detail:
            dow_note = f" ({wd.get('weekday', '')})" if wd.get("weekday") else ""
            st.caption(
                f"**Day {wd['day']}{dow_note}** — avg {wd['avg_pct_from_low']:.0f}% from monthly low, "
                f"only {wd['win_rate']:.0f}% chance of being cheap"
            )

        # --- Latest gold news ---
        news = prediction.get("news_headlines", [])
        if news:
            with st.expander(f"📰 Latest Gold News ({len(news)} headlines)"):
                for h in news:
                    src = f" — *{h['source']}*" if h.get("source") else ""
                    st.caption(f"• {h['title']}{src}")

        # --- Full day-wise analysis ---
        with st.expander("📈 All Days Analysis (1-31)"):
            analysis = prediction["analysis"]
            rows = sorted(analysis.values(), key=lambda x: x["composite_score"])
            chart_data = []
            for row in rows:
                chart_data.append(
                    {
                        "Day": row["day"],
                        "Weekday": row.get("weekday", ""),
                        "Avg Price (₹)": f"{row['avg_price']:,.2f}",
                        "Month Rank %ile": f"{row['median_price']:.1f}",
                        "Avg % from Low": f"{row['avg_pct_from_low']:.1f}%",
                        "Win Rate (%)": f"{row['win_rate']:.1f}%",
                        "Score": row["composite_score"],
                        "Data Points": row["data_points"],
                    }
                )
            df = pd.DataFrame(chart_data)
            st.dataframe(df, hide_index=True, use_container_width=True)

            # Bar chart of win rates by day
            win_data = {
                f"Day {r['day']}": r["win_rate"]
                for r in sorted(analysis.values(), key=lambda x: x["day"])
            }
            st.bar_chart(pd.Series(win_data, name="Win Rate %"), height=300)

        # --- Save prediction ---
        save_gold_buyday_prediction(prediction)

        # --- Verify past predictions ---
        st.divider()
        st.subheader("📈 Past Predictions Track Record")

        past = verify_gold_buyday_predictions()
        verified = [p for p in past if p.get("verified")]

        if verified:
            track_rows = []
            for v in verified:
                status = "✅" if v.get("was_correct") else "❌"
                track_rows.append(
                    {
                        "Month": v["month"],
                        "Predicted Days": ", ".join(
                            str(d) for d in v.get("predicted_days", [])
                        ),
                        "Best Predicted Price": (
                            f"₹{v['predicted_day_price']:,.2f}"
                            if v.get("predicted_day_price")
                            else "—"
                        ),
                        "Actual Best Day": v.get("actual_best_day", "—"),
                        "Actual Best Price": (
                            f"₹{v['actual_best_price']:,.2f}"
                            if v.get("actual_best_price")
                            else "—"
                        ),
                        "Deviation": (
                            f"{v.get('savings_pct', 0):+.1f}%"
                            if v.get("savings_pct") is not None
                            else "—"
                        ),
                        "Result": status,
                    }
                )
            st.dataframe(
                pd.DataFrame(track_rows),
                hide_index=True,
                use_container_width=True,
            )

            correct = sum(1 for v in verified if v.get("was_correct"))
            total = len(verified)
            st.metric(
                "Overall Accuracy",
                (
                    f"{correct}/{total} ({round(correct / total * 100)}%)"
                    if total > 0
                    else "—"
                ),
            )
        else:
            st.info(
                "No verified predictions yet. Predictions are verified at the "
                "end of each month — check back next month!"
            )

        # --- Self-learning ---
        learnings = learn_gold_buyday()
        if learnings and learnings.get("learnings"):
            with st.expander(
                f"🧠 What I Learned ({learnings['total_verified']} months analysed)"
            ):
                for l_text in learnings["learnings"]:
                    st.markdown(l_text)

                st.divider()
                st.caption("**Current Factor Weights (10-factor model):**")
                w = learnings.get("weights", {})
                st.caption("*Core pattern factors:*")
                wc1, wc2, wc3 = st.columns(3)
                wc1.metric("Month Rank", f"{w.get('month_rank', 1.0):.2f}")
                wc2.metric("% from Low", f"{w.get('pct_from_low', 1.5):.2f}")
                wc3.metric("Win Rate", f"{w.get('win_rate', 2.0):.2f}")
                wc4, wc5, wc6 = st.columns(3)
                wc4.metric("Recent % Low", f"{w.get('recent_pct', 1.0):.2f}")
                wc5.metric("Recent Win", f"{w.get('recent_win', 1.5):.2f}")
                wc6.metric("Avg Rank", f"{w.get('avg_rank', 0.5):.2f}")
                st.caption("*Macro-aware factors:*")
                wc7, wc8, wc9, wc10 = st.columns(4)
                wc7.metric("Day-of-Week", f"{w.get('dow_bias', 0.8):.2f}")
                wc8.metric("Volatility", f"{w.get('vol_regime', 0.6):.2f}")
                wc9.metric("VIX Shift", f"{w.get('vix_shift', 1.0):.2f}")
                wc10.metric("DXY Trend", f"{w.get('dxy_trend', 0.8):.2f}")

        # --- Gold Price Drivers ---
        st.divider()
        st.subheader("🔍 What Moved Gold Prices?")
        st.caption(
            "Macro factor analysis — matches past gold price movements with "
            "USD/INR, DXY, US yields, VIX, and seasonal patterns."
        )
        with st.spinner("Analysing 12 months of price drivers..."):
            driver_data = analyze_gold_price_drivers(months_back=12)

        if driver_data:
            # Overall insights
            for insight in driver_data.get("insights", []):
                st.markdown(f"• {insight}")

            st.markdown("")

            # Monthly breakdown
            for md in driver_data["months"]:
                chg = md["change_pct"]
                icon = "🟢" if chg > 1 else ("🔴" if chg < -1 else "⚪")
                with st.expander(
                    f"{icon} **{md['month']}** — {md['direction']} "
                    f"({chg:+.1f}%) | ₹{md['open']:,.0f} → ₹{md['close']:,.0f}"
                ):
                    # Price bar
                    pc1, pc2, pc3, pc4 = st.columns(4)
                    pc1.metric("Open", f"₹{md['open']:,.2f}")
                    pc2.metric("Close", f"₹{md['close']:,.2f}")
                    pc3.metric("High", f"₹{md['high']:,.2f}")
                    pc4.metric("Low", f"₹{md['low']:,.2f}")

                    # Macro indicators
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    if md.get("usd_inr_change") is not None:
                        mc1.metric("USD/INR", f"{md['usd_inr_change']:+.2f}%")
                    else:
                        mc1.metric("USD/INR", "—")
                    if md.get("dxy_change") is not None:
                        mc2.metric("DXY", f"{md['dxy_change']:+.2f}%")
                    else:
                        mc2.metric("DXY", "—")
                    if md.get("yield_change") is not None:
                        mc3.metric("10Y Yield Δ", f"{md['yield_change']:+.2f}%")
                    else:
                        mc3.metric("10Y Yield Δ", "—")
                    if md.get("avg_vix") is not None:
                        mc4.metric("Avg VIX", f"{md['avg_vix']:.1f}")
                    else:
                        mc4.metric("Avg VIX", "—")

                    # Extra row
                    ec1, ec2 = st.columns(2)
                    ec1.metric("Volatility", f"{md['volatility_pct']:.1f}%")
                    if md.get("gold_silver_ratio") is not None:
                        ec2.metric("Gold:Silver", f"{md['gold_silver_ratio']:.1f}x")
                    else:
                        ec2.metric("Gold:Silver", "—")

                    # Drivers
                    if md["drivers"]:
                        st.markdown("**Drivers:**")
                        for d in md["drivers"]:
                            st.markdown(f"- {d}")

                    # Likely events inferred
                    if md.get("likely_events"):
                        st.markdown(
                            "**Likely events:** "
                            + ", ".join(f"_{e}_" for e in md["likely_events"])
                        )
        else:
            st.info("Could not fetch price driver data — try again later.")
    else:
        st.warning(
            "Could not generate buy-day prediction — insufficient gold price data."
        )


@st.fragment()
def _ratio_tab_fragment():
    """Gold:Silver ratio analysis — useful for deciding which metal to buy."""
    st.subheader("📊 Gold to Silver Ratio")
    st.caption(
        "The ratio tells you how many grams of silver equals the price of 1 gram of gold. "
        "Higher ratio = silver is relatively cheaper."
    )

    try:
        # Fetch multi-timeframe data for ratio
        period_options = {"1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
        selected_period = st.radio(
            "Period",
            list(period_options.keys()),
            index=2,
            horizontal=True,
            key="ratio_period",
        )
        yf_period = period_options[selected_period]

        gold_hist, fx_hist = _fetch_metal_and_fx("GC=F", yf_period)
        silver_hist, _ = _fetch_metal_and_fx("SI=F", yf_period)

        if (
            gold_hist is not None
            and silver_hist is not None
            and not gold_hist.empty
            and not silver_hist.empty
        ):
            # Calculate ratio in USD (troy oz)
            combined = pd.DataFrame(
                {
                    "gold_usd": gold_hist["Close"],
                    "silver_usd": silver_hist["Close"],
                }
            )
            combined = combined.dropna()
            if not combined.empty:
                combined["ratio"] = combined["gold_usd"] / combined["silver_usd"]

                current_ratio = round(combined["ratio"].iloc[-1], 1)
                avg_ratio = round(combined["ratio"].mean(), 1)
                high_ratio = round(combined["ratio"].max(), 1)
                low_ratio = round(combined["ratio"].min(), 1)

                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Current Ratio", f"{current_ratio:.0f}:1")
                r2.metric("Period Average", f"{avg_ratio:.0f}:1")
                r3.metric("Period High", f"{high_ratio:.0f}:1")
                r4.metric("Period Low", f"{low_ratio:.0f}:1")

                # Chart
                ratio_chart = pd.DataFrame({"Gold to Silver Ratio": combined["ratio"]})
                if ratio_chart.index.tz is not None:
                    ratio_chart.index = ratio_chart.index.tz_localize(None)
                st.line_chart(ratio_chart, height=300)

                # Interpretation
                if current_ratio > avg_ratio * 1.1:
                    st.success(
                        f"📈 Ratio is above average ({current_ratio:.0f} vs avg {avg_ratio:.0f}) — "
                        f"**Silver is relatively cheap** compared to gold. Consider buying silver."
                    )
                elif current_ratio < avg_ratio * 0.9:
                    st.info(
                        f"📉 Ratio is below average ({current_ratio:.0f} vs avg {avg_ratio:.0f}) — "
                        f"**Gold is relatively cheap** compared to silver. Consider buying gold."
                    )
                else:
                    st.info(
                        f"⚖️ Ratio is near average ({current_ratio:.0f} vs avg {avg_ratio:.0f}) — "
                        f"no strong preference between gold and silver."
                    )

                st.divider()
                st.markdown("##### 📚 How to use the Gold:Silver Ratio")
                st.markdown(
                    """
- **Historical average** (modern era): ~65-70:1
- **Ratio above 80**: Silver is very cheap relative to gold → favor silver
- **Ratio below 50**: Gold is relatively cheap → favor gold
- **Reversion to mean**: The ratio tends to return to its long-term average
- **Strategy**: Buy the cheaper metal when the ratio is extreme, then swap when it normalizes
"""
                )
            else:
                st.warning("Could not compute ratio — insufficient data overlap")
        else:
            st.warning("Could not fetch metal data for ratio calculation")
    except Exception as e:
        st.warning(f"Ratio data unavailable: {e}")
