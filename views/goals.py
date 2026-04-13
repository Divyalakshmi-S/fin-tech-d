import streamlit as st
import pandas as pd
from datetime import datetime

from analysis import (
    calculate_sip_for_goal,
    calculate_goal_progress,
    recommend_sip_funds,
    analyze_existing_mf_holdings,
    save_goal,
    load_goals,
    delete_goal,
)


def render(holdings):
    st.title("🎯 Goal-Based Planning")
    st.caption("Plan your financial goals and track how much SIP you need")

    goal_tab1, goal_tab2 = st.tabs(["🧮 SIP Calculator", "📊 Track My Goals"])

    with goal_tab1:
        st.subheader("How much SIP do I need?")
        st.caption("Enter your target and we'll tell you the monthly SIP required")

        gc1, gc2, gc3 = st.columns(3)
        target = gc1.number_input(
            "Target Amount (₹)",
            min_value=10000,
            step=50000,
            value=5000000,
            help="How much money you want to accumulate",
        )
        years = gc2.number_input(
            "Time Horizon (years)", min_value=1, max_value=40, step=1, value=10
        )
        expected_return = gc3.number_input(
            "Expected Annual Return (%)",
            min_value=1.0,
            max_value=30.0,
            step=0.5,
            value=12.0,
            help="12% for equity, 8% for debt, 10% for balanced",
        )

        goal_result = calculate_sip_for_goal(target, years, expected_return)

        if goal_result:
            st.divider()

            # Result card
            sip_color = "#27ae60"
            st.markdown(
                f"""<div style="background: linear-gradient(135deg, {sip_color}22, {sip_color}11);
                border-left: 5px solid {sip_color}; border-radius: 10px;
                padding: 20px; margin: 10px 0;">
                <h2 style="margin:0; color: {sip_color};">💰 You need ₹{goal_result['monthly_sip']:,.0f}/month SIP</h2>
                <p style="font-size: 1.1em; margin: 8px 0 0 0;">to reach <strong>₹{target:,.0f}</strong> in <strong>{years} years</strong></p>
                </div>""",
                unsafe_allow_html=True,
            )

            gr1, gr2, gr3 = st.columns(3)
            gr1.metric("Monthly SIP", f"₹{goal_result['monthly_sip']:,.0f}")
            gr2.metric("You'll Invest", f"₹{goal_result['total_invested']:,.0f}")
            gr3.metric("Returns Earned", f"₹{goal_result['total_returns']:,.0f}")

            # Growth projection chart
            r = expected_return / 100 / 12
            months_list = list(range(1, years * 12 + 1))
            invested_series = [goal_result["monthly_sip"] * m for m in months_list]
            if r > 0:
                value_series = [
                    goal_result["monthly_sip"] * (((1 + r) ** m - 1) / r) * (1 + r)
                    for m in months_list
                ]
            else:
                value_series = invested_series

            chart_df = pd.DataFrame(
                {
                    "Invested": invested_series,
                    "Projected Value": value_series,
                },
                index=[f"Year {m//12}" if m % 12 == 0 else "" for m in months_list],
            )
            # Show only yearly data points for cleaner chart
            yearly_df = chart_df.iloc[11::12]  # every 12th month
            yearly_df.index = [f"Year {i+1}" for i in range(len(yearly_df))]
            st.line_chart(yearly_df, height=300)

            # --- Your Existing MF/SIP Holdings ---
            st.divider()
            st.subheader("📋 Your Current Funds — Hold, Add, or Sell?")

            mf_analysis = analyze_existing_mf_holdings(holdings)
            if mf_analysis:
                for mf in mf_analysis:
                    verdict = mf["verdict"]
                    verdict_colors = {
                        "ADD MORE": "#27ae60",
                        "HOLD": "#3498db",
                        "HOLD & WATCH": "#f39c12",
                        "CONSIDER SELLING": "#e74c3c",
                    }
                    vc = verdict_colors.get(verdict, "#95a5a6")
                    verdict_icons = {
                        "ADD MORE": "🟢",
                        "HOLD": "🔵",
                        "HOLD & WATCH": "🟡",
                        "CONSIDER SELLING": "🔴",
                    }
                    vi = verdict_icons.get(verdict, "⚪")

                    pnl = mf["current_value"] - mf["invested"]
                    pnl_sign = "+" if pnl >= 0 else ""
                    pnl_color = "#27ae60" if pnl >= 0 else "#e74c3c"

                    sip_tag = (
                        f" · SIP ₹{mf['sip_monthly']:,.0f}/mo"
                        if mf["is_sip"] and mf["sip_monthly"] > 0
                        else ""
                    )

                    with st.expander(
                        f"{vi} **{mf['name']}** — {verdict}{sip_tag}"
                    ):
                        # Metrics row
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Invested", f"₹{mf['invested']:,.0f}")
                        m2.metric(
                            "Current Value",
                            f"₹{mf['current_value']:,.0f}",
                            f"{mf['total_return_pct']:+.1f}%",
                        )
                        m3.metric("Category", mf["category"])
                        m4.metric("NAV", f"₹{mf['current_price']:,.2f}")

                        # Returns
                        ret = mf["returns"]
                        if ret:
                            ret_cols = st.columns(len(ret) + 1)
                            col_idx = 0
                            for period_label, period_key in [
                                ("1M Return", "1m"),
                                ("6M Return", "6m"),
                                ("1Y Return", "1y"),
                            ]:
                                if period_key in ret:
                                    ret_cols[col_idx].metric(
                                        period_label,
                                        f"{ret[period_key]:+.1f}%",
                                    )
                                    col_idx += 1
                            if mf["rsi"] is not None:
                                ret_cols[col_idx].metric("RSI", f"{mf['rsi']:.0f}")

                        # Verdict card
                        st.markdown(
                            f"""<div style="border-left: 4px solid {vc}; padding: 10px 14px; margin: 10px 0;
                            border-radius: 4px; background: {vc}11;">
                            <strong style="color: {vc};">{vi} {verdict}</strong> — {mf['verdict_detail']}
                            </div>""",
                            unsafe_allow_html=True,
                        )

                        # Reasoning
                        for reason in mf["reasons"]:
                            st.caption(f"• {reason}")
            else:
                st.info(
                    "No mutual fund holdings found. Add MFs in the **Manage Portfolio** page "
                    "or use the recommendations below to start your first SIP."
                )

            # --- Recommended SIP Funds ---
            st.divider()
            st.subheader("📌 Which SIPs to Invest In")
            st.caption(
                f"Recommended fund allocation for a {years}-year, {expected_return:.0f}% return goal"
            )

            rec_result = recommend_sip_funds(
                years, expected_return, goal_result["monthly_sip"], holdings
            )
            if rec_result:
                recs = rec_result["funds"]
                trend_note = rec_result.get("trend_note")

                if trend_note:
                    st.markdown(f"**Market Trend:** {trend_note}")

                # Portfolio-aware notes
                portfolio_notes = rec_result.get("portfolio_notes", [])
                if portfolio_notes:
                    for pn in portfolio_notes:
                        st.caption(pn)

                # Allocation pie overview
                alloc_cols = st.columns(len(recs))
                for col, rec in zip(alloc_cols, recs):
                    risk_colors = {
                        "Low": "#27ae60",
                        "Moderate": "#f39c12",
                        "High": "#e67e22",
                        "Very High": "#e74c3c",
                    }
                    rc = risk_colors.get(rec["risk"], "#95a5a6")
                    col.markdown(
                        f"""<div style="text-align:center; padding:8px; border-radius:8px;
                        background: {rc}11; border: 1px solid {rc}33;">
                        <div style="font-size:1.5em; font-weight:bold; color:{rc};">{rec['allocation_pct']}%</div>
                        <div style="font-weight:bold; font-size:0.9em;">{rec['category']}</div>
                        <div style="font-size:0.8em; opacity:0.7;">₹{rec['sip_amount']:,.0f}/mo</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                st.write("")
                for rec in recs:
                    risk_colors = {
                        "Low": "#27ae60",
                        "Moderate": "#f39c12",
                        "High": "#e67e22",
                        "Very High": "#e74c3c",
                    }
                    rc = risk_colors.get(rec["risk"], "#95a5a6")
                    st.markdown(
                        f"""<div style="border-left: 4px solid {rc}; padding: 10px 14px; margin: 8px 0;
                        border-radius: 4px; background: {rc}08;">
                        <strong>{rec['category']}</strong> — <span style="color:{rc};">₹{rec['sip_amount']:,.0f}/month</span>
                        <span style="float:right; font-size:0.85em; color:{rc}; border:1px solid {rc};
                        padding:1px 8px; border-radius:10px;">{rec['risk']} Risk</span>
                        <br><span style="font-size:0.9em;">{rec['name']}</span>
                        <br><span style="font-size:0.85em; opacity:0.7;">AMFI: {rec['amfi_code']} · Returns: {rec['return_range']} · {rec['reason']}</span>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                st.info(
                    "💡 **Tip:** All recommendations are Direct Growth plans (lowest expense ratio). "
                    "Start SIPs through Groww, Kuvera, or your bank. Past returns don't guarantee future performance."
                )

                # Save this goal button
                st.divider()
                with st.form("save_goal_form", clear_on_submit=True):
                    goal_name = st.text_input(
                        "Save this as a goal (give it a name)",
                        placeholder="e.g. House Down Payment, Retirement, Child Education",
                    )
                    if st.form_submit_button("💾 Save Goal"):
                        if goal_name.strip():
                            save_goal(
                                {
                                    "name": goal_name.strip(),
                                    "target": target,
                                    "years": years,
                                    "expected_return": expected_return,
                                    "monthly_sip": goal_result["monthly_sip"],
                                }
                            )
                            st.success(
                                f"✅ Goal **{goal_name.strip()}** saved! Track it in the **📊 Track My Goals** tab."
                            )
                            st.rerun()
                        else:
                            st.error("Enter a name for your goal.")

            # Quick presets
            st.divider()
            st.subheader("📋 Quick Goal Presets")
            presets = [
                ("🏠 House Down Payment", 2000000, 5),
                ("🎓 Child Education", 3000000, 15),
                ("🏖️ Retirement", 10000000, 25),
                ("🚗 Car", 1000000, 3),
                ("✈️ Vacation Fund", 300000, 2),
            ]
            preset_cols = st.columns(len(presets))
            for col, (label, amt, yrs) in zip(preset_cols, presets):
                with col:
                    pr = calculate_sip_for_goal(amt, yrs, expected_return)
                    if pr:
                        st.metric(
                            label,
                            f"₹{pr['monthly_sip']:,.0f}/mo",
                            f"₹{amt/100000:.0f}L in {yrs}yr",
                        )

    with goal_tab2:
        st.subheader("📊 Track My Goals")

        saved_goals = load_goals()

        if not saved_goals:
            st.info(
                "No goals saved yet. Use the **🧮 SIP Calculator** tab to plan a goal and save it."
            )
        else:
            total_invested = sum(h["amount"] for h in holdings) if holdings else 0
            monthly_sips = (
                sum(h["sip_monthly"] for h in holdings if h["sip_monthly"] > 0)
                if holdings
                else 0
            )

            for goal in saved_goals:
                g_name = goal.get("name", "Unnamed Goal")
                g_target = goal.get("target", 0)
                g_years = goal.get("years", 10)
                g_return = goal.get("expected_return", 12)
                g_sip = goal.get("monthly_sip", 0)
                g_created = goal.get("created_date", "")
                g_id = goal.get("id", 0)

                # Calculate time elapsed since goal creation
                years_remaining = g_years
                if g_created:
                    try:
                        created_dt = datetime.strptime(g_created, "%Y-%m-%d")
                        elapsed_years = (datetime.now() - created_dt).days / 365.25
                        years_remaining = max(1, round(g_years - elapsed_years, 1))
                    except Exception:
                        pass

                # Track progress
                progress = calculate_goal_progress(
                    total_invested, g_target, years_remaining, monthly_sips, g_return
                )

                prog_pct = min(progress["progress_pct"], 100) if progress else 0
                prog_color = (
                    "#27ae60" if (progress and progress["on_track"]) else "#f39c12"
                )

                with st.expander(
                    f"🎯 **{g_name}** — ₹{g_target/100000:.0f}L in {g_years}yr ({prog_pct:.0f}% done)",
                    expanded=True,
                ):
                    # Progress bar
                    st.markdown(
                        f"""<div style="margin: 6px 0;">
                        <div style="background: #eee; border-radius: 8px; height: 16px;">
                            <div style="background: {prog_color}; width: {prog_pct}%; height: 16px; border-radius: 8px;
                            text-align: center; color: white; font-size: 0.75em; line-height: 16px;">
                            {prog_pct:.0f}%</div>
                        </div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                    # Metrics
                    gm1, gm2, gm3, gm4 = st.columns(4)
                    gm1.metric("Target", f"₹{g_target:,.0f}")
                    gm2.metric("SIP Needed", f"₹{g_sip:,.0f}/mo")
                    gm3.metric("Your SIPs", f"₹{monthly_sips:,.0f}/mo")
                    gm4.metric("Years Left", f"{years_remaining:.1f}")

                    if progress:
                        # Status + actionable suggestions
                        if progress["on_track"]:
                            st.success(
                                f"✅ On track! Projected ₹{progress['projected_total']:,.0f} "
                                f"(surplus ₹{progress['surplus']:,.0f})."
                            )
                        else:
                            needed = calculate_sip_for_goal(
                                progress["remaining"], years_remaining, g_return
                            )
                            extra_sip = (
                                needed["monthly_sip"] - monthly_sips if needed else 0
                            )

                            st.warning(
                                f"⚠️ Shortfall ₹{progress['shortfall']:,.0f}. "
                                f"Increase SIP by ~₹{max(extra_sip, 0):,.0f}/month."
                            )

                            # Actionable suggestions
                            suggestions = []
                            if extra_sip > 0:
                                suggestions.append(
                                    f"💰 **Increase SIP** to ₹{monthly_sips + extra_sip:,.0f}/month "
                                    f"(add ₹{extra_sip:,.0f} more)"
                                )
                            if g_return < 14 and years_remaining > 5:
                                higher_return = min(g_return + 2, 15)
                                higher_calc = calculate_sip_for_goal(
                                    g_target, years_remaining, higher_return
                                )
                                if higher_calc:
                                    suggestions.append(
                                        f"📈 **Switch to higher-growth funds** — at {higher_return:.0f}% return, "
                                        f"you need only ₹{higher_calc['monthly_sip']:,.0f}/month "
                                        f"(₹{g_sip - higher_calc['monthly_sip']:,.0f} less)"
                                    )
                            if years_remaining < g_years * 0.5:
                                suggestions.append(
                                    "⏰ **More than half your time is used** — "
                                    "consider a lump sum top-up from bonus/savings"
                                )
                            if monthly_sips == 0:
                                suggestions.append(
                                    "🚀 **No active SIPs!** Start one in Manage Portfolio "
                                    "to begin working towards this goal"
                                )

                            if suggestions:
                                st.markdown("**Suggested Actions:**")
                                for s in suggestions:
                                    st.markdown(f"- {s}")

                            # Recommend funds for the gap
                            if extra_sip > 0:
                                with st.expander(
                                    "📌 Recommended SIPs to bridge the gap"
                                ):
                                    rec_result = recommend_sip_funds(
                                        years_remaining, g_return, extra_sip
                                    )
                                    if rec_result:
                                        if rec_result.get("trend_note"):
                                            st.caption(rec_result["trend_note"])
                                        for rec in rec_result["funds"]:
                                            risk_colors = {
                                                "Low": "#27ae60",
                                                "Moderate": "#f39c12",
                                                "High": "#e67e22",
                                                "Very High": "#e74c3c",
                                            }
                                            rc = risk_colors.get(rec["risk"], "#95a5a6")
                                            st.markdown(
                                                f"""<div style="border-left: 3px solid {rc}; padding: 6px 10px; margin: 4px 0;
                                                border-radius: 3px; background: {rc}08; font-size: 0.9em;">
                                                <strong>{rec['category']}</strong> — ₹{rec['sip_amount']:,.0f}/mo ({rec['allocation_pct']}%)
                                                <br>{rec['name']}
                                                <span style="color:{rc}; font-size:0.85em;"> · {rec['risk']} risk · {rec['return_range']}</span>
                                                </div>""",
                                                unsafe_allow_html=True,
                                            )

                    # Meta info + delete
                    st.caption(
                        f"Created: {g_created} · {g_years}yr horizon · {g_return}% expected return"
                    )
                    if st.button(f"🗑️ Remove Goal", key=f"del_goal_{g_id}"):
                        delete_goal(g_id)
                        st.rerun()
