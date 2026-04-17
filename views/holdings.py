import streamlit as st
import pandas as pd
import json
import yfinance as yf

from analysis import (
    analyze_portfolio,
    analyze_existing_stock_holdings,
    analyze_existing_mf_holdings,
    predict_stock_buy,
    save_stock_prediction,
    verify_stock_predictions,
    fetch_ticker_news,
    analyze_news_impact,
    calculate_rebalancing,
    DEFAULT_TARGET_ALLOCATION,
)
from ui_helpers import (
    SIGNAL_MAP,
    render_verdict_card,
    render_factor_bars,
    render_total_score,
    render_news_card,
)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_health_analysis(holdings_key):
    """Cached stock + MF health analysis."""
    holdings = json.loads(holdings_key)
    return analyze_existing_stock_holdings(holdings), analyze_existing_mf_holdings(
        holdings
    )


@st.cache_data(ttl=300, show_spinner=False)
def _cached_analyze_portfolio(holdings_key):
    """Cached portfolio analysis."""
    holdings = json.loads(holdings_key)
    return analyze_portfolio(holdings)


def _render_health_card(item, show_pe=False):
    """Render a single holding health verdict card."""
    verdict = item["verdict"]
    verdict_colors = {
        "ADD MORE": "#27ae60",
        "HOLD": "#3498db",
        "HOLD & WATCH": "#f39c12",
        "REDUCE": "#e67e22",
        "CONSIDER SELLING": "#e74c3c",
    }
    verdict_icons = {
        "ADD MORE": "🟢",
        "HOLD": "🔵",
        "HOLD & WATCH": "🟡",
        "REDUCE": "🟠",
        "CONSIDER SELLING": "🔴",
    }
    vc = verdict_colors.get(verdict, "#95a5a6")
    vi = verdict_icons.get(verdict, "⚪")

    pnl = item["current_value"] - item["invested"]
    pnl_color = "#27ae60" if pnl >= 0 else "#e74c3c"
    risk = item.get("risk_level", "")
    risk_tag = f" · Risk: {risk}" if risk else ""

    with st.expander(f"{vi} **{item['name']}** — {verdict}{risk_tag}"):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Invested", f"₹{item['invested']:,.0f}")
        m2.metric(
            "Current Value",
            f"₹{item['current_value']:,.0f}",
            f"{item['total_return_pct']:+.1f}%",
        )
        m3.metric("Price", f"₹{item['current_price']:,.2f}")
        if show_pe and item.get("pe_ratio"):
            m4.metric("PE Ratio", f"{item['pe_ratio']:.1f}")
        elif item.get("rsi"):
            m4.metric("RSI", f"{item['rsi']:.0f}")
        else:
            m4.metric("Category", item.get("category", item.get("sector", "—")))

        # Returns row
        ret = item.get("returns", {})
        if ret:
            ret_cols = st.columns(min(len(ret) + 2, 5))
            col_idx = 0
            for label, key in [("1M", "1m"), ("6M", "6m"), ("1Y", "1y")]:
                if key in ret:
                    ret_cols[col_idx].metric(f"{label} Return", f"{ret[key]:+.1f}%")
                    col_idx += 1
            if item.get("from_high_pct") is not None:
                ret_cols[min(col_idx, 4)].metric(
                    "From 52W High", f"{item['from_high_pct']:+.1f}%"
                )

        # Verdict banner
        st.markdown(
            f"""<div style="border-left: 4px solid {vc}; padding: 10px 14px; margin: 10px 0;
            border-radius: 4px; background: {vc}11;">
            <strong style="color: {vc};">{vi} {verdict}</strong> — {item['verdict_detail']}
            </div>""",
            unsafe_allow_html=True,
        )

        # Reasons
        for reason in item["reasons"]:
            st.caption(f"• {reason}")


def render(holdings):
    st.title("🔬 Holdings Deep Analysis")

    if not holdings:
        st.info(
            "No holdings to analyze. Go to **⚙️ Manage Portfolio** to add investments."
        )
    else:
        tickers_with_data = [h for h in holdings if h["ticker"]]

        if not tickers_with_data:
            st.info("Add ticker symbols for live analysis.")
        else:
            # ===== PORTFOLIO HEALTH MONITOR =====
            st.subheader("🩺 Portfolio Health Monitor")
            st.caption("Should you add more, hold, or reduce each investment?")

            with st.spinner("Analyzing all holdings..."):
                holdings_key = json.dumps(holdings, sort_keys=True, default=str)
                stock_health, mf_health = _cached_health_analysis(holdings_key)

            # Summary counters
            all_items = stock_health + mf_health
            if all_items:
                add_count = sum(1 for x in all_items if x["verdict"] == "ADD MORE")
                hold_count = sum(
                    1 for x in all_items if x["verdict"] in ("HOLD", "HOLD & WATCH")
                )
                reduce_count = sum(
                    1
                    for x in all_items
                    if x["verdict"] in ("REDUCE", "CONSIDER SELLING")
                )

                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Total Monitored", f"{len(all_items)}")
                s2.metric("🟢 Add More", f"{add_count}")
                s3.metric("🔵 Hold", f"{hold_count}")
                s4.metric("🔴 Reduce/Sell", f"{reduce_count}")

                # Urgent alerts
                urgent = [
                    x
                    for x in all_items
                    if x["verdict"] in ("REDUCE", "CONSIDER SELLING")
                ]
                if urgent:
                    names = ", ".join(x["name"] for x in urgent[:4])
                    st.warning(f"⚠️ **Needs attention:** {names}")

                strong = [x for x in all_items if x["verdict"] == "ADD MORE"]
                if strong:
                    names = ", ".join(x["name"] for x in strong[:4])
                    st.success(f"💪 **Performing well:** {names}")

                # Stock holdings
                if stock_health:
                    st.markdown("##### 📈 Stocks")
                    for item in stock_health:
                        _render_health_card(item, show_pe=True)

                # MF holdings
                if mf_health:
                    st.markdown("##### 📊 Mutual Funds")
                    for item in mf_health:
                        _render_health_card(item, show_pe=False)
            else:
                st.info("Could not fetch data for your holdings. Try again later.")

            st.divider()

            # ===== EXISTING ANALYSIS =====
            with st.spinner("Fetching live data..."):
                results = _cached_analyze_portfolio(holdings_key)

            # Summary comparison table first
            st.subheader("📋 Quick Comparison")

            # Sort control
            sort_col = st.selectbox(
                "Sort by",
                ["Name", "Today %", "RSI", "vs Best Price", "1 Year Return"],
                index=1,
                key="holdings_sort",
            )

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
                        "Volume": (
                            f"{a['vol_ratio']:.1f}x" if a.get("vol_ratio") else "—"
                        ),
                        "Signal": (
                            str(a.get("crossover", "")) if a.get("crossover") else "—"
                        ),
                        "_sort_today": a["daily_change_pct"],
                        "_sort_rsi": a["rsi"] if a["rsi"] else 50,
                        "_sort_high": a["from_high_pct"] if a["from_high_pct"] else 0,
                        "_sort_1y": a["one_yr_return"] if a["one_yr_return"] else 0,
                    }
                )

            if summary_rows:
                # Sort
                sort_key_map = {
                    "Name": lambda x: x["Name"],
                    "Today %": lambda x: x["_sort_today"],
                    "RSI": lambda x: x["_sort_rsi"],
                    "vs Best Price": lambda x: x["_sort_high"],
                    "1 Year Return": lambda x: x["_sort_1y"],
                }
                reverse = sort_col != "Name"
                summary_rows.sort(
                    key=sort_key_map.get(sort_col, lambda x: x["Name"]), reverse=reverse
                )

                # Remove internal sort keys before display
                display_rows = [
                    {k: v for k, v in row.items() if not k.startswith("_")}
                    for row in summary_rows
                ]
                st.dataframe(
                    pd.DataFrame(display_rows),
                    width="stretch",
                    hide_index=True,
                    height=min(len(display_rows) * 40 + 40, 450),
                )

                # Best/Worst quick callout
                best = max(summary_rows, key=lambda x: x["_sort_today"])
                worst = min(summary_rows, key=lambda x: x["_sort_today"])
                bw1, bw2 = st.columns(2)
                bw1.success(f"🏆 **Best today:** {best['Name']} ({best['Today']})")
                bw2.error(f"📉 **Worst today:** {worst['Name']} ({worst['Today']})")

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

                    # Tax status
                    if h.get("is_ltcg") is not None:
                        days_held = h.get("days_held", 0)
                        if h["is_ltcg"]:
                            st.caption(
                                f"📋 Held {days_held} days — **LTCG** (taxed at 10% above ₹1L)"
                            )
                        else:
                            st.caption(
                                f"📋 Held {days_held} days — **STCG** (taxed at 15%). Hold {365 - days_held} more days for LTCG."
                            )

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

                    # Chart, technicals, news, and predictions load on demand
                    load_key = f"load_detail_{h['ticker']}"
                    if st.button("📊 Load chart, news & analysis", key=load_key):
                        st.session_state[f"detail_loaded_{h['ticker']}"] = True

                    if st.session_state.get(f"detail_loaded_{h['ticker']}", False):
                        # Chart with timeframe selector
                        try:
                            period_options = {
                                "1W": "5d",
                                "1M": "1mo",
                                "3M": "3mo",
                                "6M": "6mo",
                                "1Y": "1y",
                                "5Y": "5y",
                            }
                            period_labels = list(period_options.keys())
                            selected_period = st.radio(
                                "Chart Period",
                                period_labels,
                                index=4,  # default 1Y
                                horizontal=True,
                                key=f"chart_period_{h['ticker']}",
                            )
                            yf_period = period_options[selected_period]
                            chart_data = yf.Ticker(h["ticker"]).history(
                                period=yf_period
                            )
                            if not chart_data.empty:
                                closes = chart_data["Close"]
                                chart_df = pd.DataFrame({"Price": closes})
                                if len(closes) >= 50:
                                    chart_df["50-day MA"] = closes.rolling(50).mean()
                                if len(closes) >= 20:
                                    bb_sma = closes.rolling(20).mean()
                                    bb_std = closes.rolling(20).std()
                                    chart_df["Bollinger Upper"] = bb_sma + 2 * bb_std
                                    chart_df["Bollinger Lower"] = bb_sma - 2 * bb_std
                                if chart_df.index.tz is not None:
                                    chart_df.index = chart_df.index.tz_localize(None)
                                st.line_chart(chart_df, height=250)
                        except Exception:
                            pass

                        # --- Technical Indicators ---
                        macd_data = a.get("macd")
                        bb_data = a.get("bollinger")
                        candle_data = a.get("candlestick_patterns")
                        sl_data = a.get("stop_loss")
                        atr_data = a.get("atr")

                        has_technicals = macd_data or bb_data or candle_data
                        if has_technicals:
                            with st.expander("📐 Technical Indicators"):
                                if macd_data:
                                    mc1, mc2, mc3 = st.columns(3)
                                    hist_color = (
                                        "🟢" if macd_data["histogram"] >= 0 else "🔴"
                                    )
                                    mc1.metric("MACD Line", f"{macd_data['macd']:+.2f}")
                                    mc2.metric(
                                        "Signal Line", f"{macd_data['signal']:+.2f}"
                                    )
                                    mc3.metric(
                                        "Histogram",
                                        f"{hist_color} {macd_data['histogram']:+.2f}",
                                    )
                                    if macd_data.get("crossover") == "BULLISH":
                                        st.success(
                                            "📈 **MACD Bullish Crossover** — MACD crossed above signal line. Buying momentum increasing."
                                        )
                                    elif macd_data.get("crossover") == "BEARISH":
                                        st.warning(
                                            "📉 **MACD Bearish Crossover** — MACD crossed below signal line. Selling pressure building."
                                        )

                                if bb_data:
                                    bc1, bc2, bc3, bc4 = st.columns(4)
                                    bc1.metric(
                                        "Upper Band", f"₹{bb_data['upper']:,.2f}"
                                    )
                                    bc2.metric(
                                        "Middle (SMA20)", f"₹{bb_data['middle']:,.2f}"
                                    )
                                    bc3.metric(
                                        "Lower Band", f"₹{bb_data['lower']:,.2f}"
                                    )
                                    pct_b = bb_data["pct_b"]
                                    if pct_b > 1:
                                        bb_label = "Above upper band — overbought"
                                    elif pct_b < 0:
                                        bb_label = "Below lower band — oversold"
                                    elif pct_b > 0.8:
                                        bb_label = "Near upper band"
                                    elif pct_b < 0.2:
                                        bb_label = "Near lower band"
                                    else:
                                        bb_label = "Mid-range"
                                    bc4.metric("%B Position", f"{pct_b:.2f}", bb_label)

                                if candle_data:
                                    st.markdown("**Candlestick Patterns Detected:**")
                                    for name, desc, direction in candle_data:
                                        st.markdown(f"- **{name}**: {desc}")

                        # --- Risk Management ---
                        if sl_data and h["type"] == "stock":
                            with st.expander("🛡️ Risk Management"):
                                rc1, rc2, rc3 = st.columns(3)
                                rc1.metric(
                                    "Stop Loss",
                                    f"₹{sl_data['stop_loss']:,.2f}",
                                    f"-{sl_data['risk_pct']:.1f}% from price",
                                )
                                rc2.metric(
                                    "Target 1 (1:1)", f"₹{sl_data['target_1']:,.2f}"
                                )
                                rc3.metric(
                                    "Target 2 (1:2)", f"₹{sl_data['target_2']:,.2f}"
                                )
                                if atr_data:
                                    st.caption(
                                        f"ATR(14): ₹{atr_data:,.2f} — average daily movement range. Stop loss is set at 2× ATR below price."
                                    )
                                st.caption(
                                    "💡 Never risk more than 1-2% of your total capital on a single trade."
                                )

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
                                    render_news_card(
                                        ni["title"],
                                        impact["sentiment_label"],
                                        impact["summary"],
                                        impact["action"],
                                    )
                        except Exception:
                            pass

                        # --- Should I add more or sell? ---
                        st.caption("🤔 Should I add more or sell this stock?")
                        try:
                            stock_pred = predict_stock_buy(h["ticker"], h["name"])
                            if stock_pred:
                                sig = stock_pred["signal"]
                                sig_icon, hex_c, _, _ = SIGNAL_MAP.get(
                                    sig, ("🟡", "#f1c40f", "", "")
                                )
                                st.markdown(
                                    f"""<div style="background: linear-gradient(135deg, {hex_c}22, {hex_c}11);
                                    border-left: 4px solid {hex_c}; border-radius: 8px;
                                    padding: 12px 16px; margin: 8px 0;">
                                    <strong style="color: {hex_c};">{sig_icon} {sig}</strong> — {stock_pred['prediction']}
                                    <br><span style="opacity: 0.7;">Confidence: {stock_pred['confidence']}%</span>
                                    </div>""",
                                    unsafe_allow_html=True,
                                )
                                # Risk warning for stock prediction
                                stk_risk = stock_pred.get("risk_level", "")
                                stk_warn = stock_pred.get("risk_warning", "")
                                if stk_risk in ("Very High", "High"):
                                    st.warning(f"**Risk: {stk_risk}** — {stk_warn}")
                                elif stk_risk == "Moderate" and stk_warn:
                                    st.info(f"**Risk: {stk_risk}** — {stk_warn}")
                                if stock_pred.get("stop_loss"):
                                    sl_info = stock_pred["stop_loss"]
                                    st.caption(
                                        f"🛡️ Suggested stop-loss: ₹{sl_info['stop_loss']:.2f} | Targets: ₹{sl_info['target_1']:.2f} → ₹{sl_info['target_2']:.2f} → ₹{sl_info['target_3']:.2f}"
                                    )
                                with st.expander("📊 Detailed Buy/Sell Analysis"):
                                    render_factor_bars(stock_pred["reasons"])
                                    render_total_score(stock_pred["total_score"])

                                # Save prediction & verify past ones (silent self-learning)
                                save_stock_prediction(stock_pred, h["ticker"])
                                verify_stock_predictions()
                        except Exception:
                            pass

            # ===== PORTFOLIO REBALANCING =====
            st.divider()
            st.subheader("⚖️ Portfolio Rebalancing")
            st.caption(
                "Compare your current allocation against target and get drift alerts"
            )

            with st.expander("🎯 Customise Target Allocation", expanded=False):
                st.caption("Adjust target percentages (must sum to 100%)")
                cols = st.columns(3)
                custom_targets = {}
                for i, (ac, config) in enumerate(DEFAULT_TARGET_ALLOCATION.items()):
                    with cols[i % 3]:
                        pct = st.number_input(
                            config["label"],
                            min_value=0.0,
                            max_value=100.0,
                            value=config["target_pct"],
                            step=5.0,
                            key=f"rebal_target_{ac}",
                        )
                        tol = st.number_input(
                            f"Tolerance %",
                            min_value=1.0,
                            max_value=20.0,
                            value=config["tolerance_pct"],
                            step=1.0,
                            key=f"rebal_tol_{ac}",
                        )
                        custom_targets[ac] = {
                            "target_pct": pct,
                            "tolerance_pct": tol,
                            "label": config["label"],
                        }

                total_target = sum(t["target_pct"] for t in custom_targets.values())
                if abs(total_target - 100.0) > 0.1:
                    st.warning(
                        f"Target allocation sums to {total_target}% — should be 100%"
                    )

            result = calculate_rebalancing(
                holdings,
                analysis_results=None,
                targets=custom_targets,
            )

            if result:
                if result["needs_rebalancing"]:
                    st.error(f"⚠️ **Rebalancing needed** — {result['summary']}")
                else:
                    st.success(f"✅ **Portfolio is balanced** — {result['summary']}")

                st.metric("Total Portfolio Value", f"₹{result['total_value']:,.0f}")

                df_data = []
                for a in result["allocations"]:
                    action_icon = {
                        "ADD": "🟢 Add",
                        "REDUCE": "🔴 Reduce",
                        "OK": "✅ OK",
                    }.get(a["action"], a["action"])
                    df_data.append(
                        {
                            "Asset Class": a["label"],
                            "Current %": a["current_pct"],
                            "Target %": a["target_pct"],
                            "Drift %": a["drift_pct"],
                            "Action": action_icon,
                            "Amount (₹)": (
                                f"₹{a['rebalance_amount']:,}"
                                if a["action"] != "OK"
                                else "—"
                            ),
                            "Holdings": ", ".join(a["holdings_in_class"][:5]) or "None",
                        }
                    )

                df = pd.DataFrame(df_data)
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Drift %": st.column_config.NumberColumn(format="%.1f%%"),
                        "Current %": st.column_config.NumberColumn(format="%.1f%%"),
                        "Target %": st.column_config.NumberColumn(format="%.1f%%"),
                    },
                )

                chart_data = pd.DataFrame(
                    {
                        "Asset Class": [a["label"] for a in result["allocations"]],
                        "Current %": [a["current_pct"] for a in result["allocations"]],
                        "Target %": [a["target_pct"] for a in result["allocations"]],
                    }
                ).set_index("Asset Class")
                st.bar_chart(chart_data)

                actions_needed = [
                    a for a in result["allocations"] if a["action"] != "OK"
                ]
                if actions_needed:
                    st.markdown("##### 📋 Suggested Actions")
                    for a in actions_needed:
                        if a["action"] == "REDUCE":
                            st.markdown(
                                f"🔴 **{a['label']}**: Over-allocated by {a['drift_pct']:+.1f}%. "
                                f"Consider moving ~₹{a['rebalance_amount']:,} to under-allocated classes."
                            )
                        elif a["action"] == "ADD":
                            st.markdown(
                                f"🟢 **{a['label']}**: Under-allocated by {a['drift_pct']:+.1f}%. "
                                f"Consider adding ~₹{a['rebalance_amount']:,} through SIP or lumpsum."
                            )
            else:
                st.info("Unable to calculate rebalancing — check portfolio data.")
