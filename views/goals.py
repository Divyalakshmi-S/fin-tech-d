import streamlit as st
import pandas as pd
from datetime import datetime

import db
import auth
from analysis import (
    calculate_sip_for_goal,
    calculate_goal_progress,
    recommend_sip_funds,
    analyze_existing_mf_holdings,
)


def render(holdings):
    st.title("🎯 Goal-Based Planning")
    st.caption("Plan your financial goals and track how much SIP you need")

    goal_tab1, goal_tab2, goal_tab3, goal_tab4 = st.tabs(
        [
            "🧮 SIP Calculator",
            "🎓 Education Goal",
            "📊 Track My Goals",
            "📐 Goal Asset Allocation",
        ]
    )

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

                    with st.expander(f"{vi} **{mf['name']}** — {verdict}{sip_tag}"):
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
                            db.save_goal(
                                {
                                    "name": goal_name.strip(),
                                    "target": target,
                                    "years": years,
                                    "expected_return": expected_return,
                                    "monthly_sip": goal_result["monthly_sip"],
                                },
                                user_id=auth.get_user_id(),
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
                        if st.button("💾 Save", key=f"preset_save_{label}"):
                            db.save_goal(
                                {
                                    "name": (
                                        label.split(" ", 1)[1]
                                        if " " in label
                                        else label
                                    ),
                                    "target": amt,
                                    "years": yrs,
                                    "expected_return": expected_return,
                                    "monthly_sip": pr["monthly_sip"],
                                },
                                user_id=auth.get_user_id(),
                            )
                            st.success("Saved!")
                            st.rerun()

            # Show allocation preview for selected preset
            st.divider()
            selected_preset = st.selectbox(
                "View allocation for a preset goal",
                ["— Select —"]
                + [f"{p[0]} — ₹{p[1]/100000:.0f}L in {p[2]}yr" for p in presets],
                key="preset_alloc_select",
            )
            if selected_preset != "— Select —":
                idx = [
                    f"{p[0]} — ₹{p[1]/100000:.0f}L in {p[2]}yr" for p in presets
                ].index(selected_preset)
                p_label, p_amt, p_yrs = presets[idx]
                p_sip = calculate_sip_for_goal(p_amt, p_yrs, expected_return)

                if p_yrs <= 2:
                    p_alloc = {
                        "Liquid/Ultra Short Debt": 80,
                        "Short-term Debt Fund": 20,
                    }
                    p_risk = "Conservative"
                elif p_yrs <= 5:
                    p_alloc = {
                        "Large Cap / Index Fund": 40,
                        "Balanced/Hybrid Fund": 30,
                        "Short-term Debt": 30,
                    }
                    p_risk = "Moderate"
                elif p_yrs <= 10:
                    p_alloc = {
                        "Large Cap / Index Fund": 40,
                        "Mid Cap Fund": 25,
                        "Balanced/Hybrid Fund": 20,
                        "Debt Fund": 15,
                    }
                    p_risk = "Moderate-Aggressive"
                else:
                    p_alloc = {
                        "Large Cap / Index Fund": 30,
                        "Mid Cap Fund": 25,
                        "Small Cap Fund": 20,
                        "International Fund": 15,
                        "Debt Fund": 10,
                    }
                    p_risk = "Aggressive"

                risk_color = {
                    "Conservative": "#27ae60",
                    "Moderate": "#3498db",
                    "Moderate-Aggressive": "#f39c12",
                    "Aggressive": "#e67e22",
                }.get(p_risk, "#95a5a6")

                st.markdown(
                    f"""<div style="border-left: 4px solid {risk_color}; padding: 10px 14px; margin: 8px 0;
                    border-radius: 4px; background: {risk_color}11;">
                    <strong>{p_label}</strong> — ₹{p_amt:,.0f} in {p_yrs} years
                    · SIP: ₹{p_sip['monthly_sip']:,.0f}/mo · <span style="color:{risk_color};">{p_risk}</span>
                    </div>""",
                    unsafe_allow_html=True,
                )

                alloc_cols = st.columns(len(p_alloc))
                for ac, (category, pct) in zip(alloc_cols, p_alloc.items()):
                    sip_share = round(p_sip["monthly_sip"] * pct / 100)
                    ac.markdown(
                        f"""<div style="text-align:center; padding:8px; border-radius:8px;
                        background: {risk_color}11; border: 1px solid {risk_color}33;">
                        <div style="font-size:1.3em; font-weight:bold; color:{risk_color};">{pct}%</div>
                        <div style="font-weight:bold; font-size:0.85em;">{category}</div>
                        <div style="font-size:0.8em; opacity:0.7;">₹{sip_share:,.0f}/mo</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                if p_yrs > 5:
                    st.caption(
                        f"📅 **Glide path:** When {max(1, p_yrs - 3)} years remain, start shifting 10% from equity to debt each year."
                    )

    # =====================================================================
    # Children's Education Goal Planner
    # =====================================================================
    with goal_tab2:
        st.subheader("🎓 Children's Education Goal Planner")
        st.caption("Plan for education costs with education-specific inflation")

        ed1, ed2, ed3 = st.columns(3)
        child_age = ed1.number_input(
            "Child's Current Age", min_value=0, max_value=17, value=5, key="goal_ed_age"
        )
        target_age = ed2.number_input(
            "Education Start Age",
            min_value=child_age + 1,
            max_value=25,
            value=18,
            key="goal_ed_target_age",
        )
        education_type = ed3.selectbox(
            "Education Type",
            [
                "Engineering (India)",
                "Medical (India)",
                "MBA (India)",
                "Engineering (Abroad)",
                "Medical (Abroad)",
                "MBA (Abroad)",
                "Custom Amount",
            ],
            key="goal_ed_type",
        )

        # Pre-set costs (2024 estimates)
        cost_map = {
            "Engineering (India)": 1500000,
            "Medical (India)": 5000000,
            "MBA (India)": 2500000,
            "Engineering (Abroad)": 5000000,
            "Medical (Abroad)": 10000000,
            "MBA (Abroad)": 8000000,
            "Custom Amount": 0,
        }

        today_cost = cost_map.get(education_type, 0)
        if education_type == "Custom Amount":
            today_cost = st.number_input(
                "Total Education Cost Today (₹)",
                min_value=100000,
                step=100000,
                value=2000000,
                key="goal_ed_custom",
            )

        edc1, edc2 = st.columns(2)
        ed_inflation = edc1.number_input(
            "Education Inflation (%)",
            min_value=3.0,
            max_value=15.0,
            value=8.0,
            step=0.5,
            key="goal_ed_inf",
            help="Education costs typically inflate at 8-10% in India",
        )
        ed_return = edc2.number_input(
            "Expected Investment Return (%)",
            min_value=4.0,
            max_value=20.0,
            value=12.0,
            step=0.5,
            key="goal_ed_ret",
        )

        years_to_goal = target_age - child_age

        # Calculate future cost and SIP needed
        future_cost = today_cost * ((1 + ed_inflation / 100) ** years_to_goal)
        r_monthly = ed_return / 100 / 12
        n_months = years_to_goal * 12
        if r_monthly > 0 and n_months > 0:
            monthly_sip_needed = future_cost / (
                (((1 + r_monthly) ** n_months - 1) / r_monthly) * (1 + r_monthly)
            )
        else:
            monthly_sip_needed = future_cost / n_months if n_months > 0 else 0

        st.divider()

        st.markdown(
            f"""<div style="background: linear-gradient(135deg, #3498db22, #3498db11);
            border-left: 5px solid #3498db; border-radius: 10px; padding: 20px; margin: 10px 0;">
            <h3 style="margin:0; color: #3498db;">🎓 Education Cost in {years_to_goal} years: ₹{future_cost:,.0f}</h3>
            <p style="margin: 8px 0;">Today's cost: ₹{today_cost:,.0f} → After {ed_inflation}% education inflation</p>
            <p style="margin: 0;">Monthly SIP needed: <strong>₹{monthly_sip_needed:,.0f}</strong></p>
            </div>""",
            unsafe_allow_html=True,
        )

        ed_r1, ed_r2, ed_r3 = st.columns(3)
        ed_r1.metric("Today's Cost", f"₹{today_cost:,.0f}")
        ed_r2.metric("Future Cost", f"₹{future_cost:,.0f}")
        ed_r3.metric("Monthly SIP", f"₹{monthly_sip_needed:,.0f}")

        # Growth chart
        def _fv_sip(monthly, rate_annual, yrs):
            r = rate_annual / 100 / 12
            n = yrs * 12
            if r <= 0:
                return monthly * n
            return monthly * (((1 + r) ** n - 1) / r) * (1 + r)

        years_list = list(range(1, years_to_goal + 1))
        sip_growth = [_fv_sip(monthly_sip_needed, ed_return, y) for y in years_list]
        cost_growth = [today_cost * ((1 + ed_inflation / 100) ** y) for y in years_list]

        chart_df = pd.DataFrame(
            {
                "Your Investment": sip_growth,
                "Education Cost": cost_growth,
            },
            index=[f"Year {y}" for y in years_list],
        )
        st.line_chart(chart_df, height=300)

        # Portfolio context
        mf_holdings = [h for h in (holdings or []) if h.get("type") == "mutual_fund"]
        if mf_holdings:
            mf_sip_total = sum(
                h.get("sip_monthly", 0)
                for h in mf_holdings
                if h.get("sip_monthly", 0) > 0
            )
            mf_value_total = sum(h.get("amount", 0) for h in mf_holdings)
            with st.expander(
                f"📋 Your existing MF portfolio: {len(mf_holdings)} funds · ₹{mf_value_total:,.0f} invested",
                expanded=False,
            ):
                for h in mf_holdings:
                    sip_tag = (
                        f" · SIP ₹{h['sip_monthly']:,.0f}/mo"
                        if h.get("sip_monthly", 0) > 0
                        else ""
                    )
                    st.caption(f"• **{h['name']}** — ₹{h['amount']:,.0f}{sip_tag}")

            if mf_sip_total > 0:
                if mf_sip_total >= monthly_sip_needed:
                    st.success(
                        f"✅ Your existing MF SIPs (₹{mf_sip_total:,.0f}/mo) already cover this goal's requirement (₹{monthly_sip_needed:,.0f}/mo). "
                        f"Consider earmarking part of them for this education goal."
                    )
                else:
                    additional = monthly_sip_needed - mf_sip_total
                    st.info(
                        f"💡 You already have ₹{mf_sip_total:,.0f}/mo in MF SIPs. "
                        f"Start an additional ₹{additional:,.0f}/mo SIP for this education goal."
                    )
            else:
                st.info(
                    f"💡 Start a ₹{monthly_sip_needed:,.0f}/mo SIP in equity mutual funds for {years_to_goal} years. "
                    f"Switch to debt funds 2-3 years before the goal."
                )
        else:
            st.info(
                f"💡 Start with ₹{monthly_sip_needed:,.0f}/mo SIP in equity mutual funds for {years_to_goal} years. "
                f"Switch to debt funds 2-3 years before the goal when {max(1, years_to_goal - 3)} years remain."
            )

        # Save as goal
        st.divider()
        with st.form("save_education_goal_form", clear_on_submit=True):
            ed_goal_name = st.text_input(
                "Save this as a goal (give it a name)",
                value=f"Child Education - {education_type}",
                placeholder="e.g. Son's Engineering, Daughter's Medical",
            )
            if st.form_submit_button("💾 Save Education Goal"):
                if ed_goal_name.strip():
                    db.save_goal(
                        {
                            "name": ed_goal_name.strip(),
                            "target": round(future_cost),
                            "years": years_to_goal,
                            "expected_return": ed_return,
                            "monthly_sip": round(monthly_sip_needed),
                        },
                        user_id=auth.get_user_id(),
                    )
                    st.success(
                        f"✅ Goal **{ed_goal_name.strip()}** saved! Track it in the **📊 Track My Goals** tab."
                    )
                    st.rerun()
                else:
                    st.error("Enter a name for your goal.")

    with goal_tab3:
        st.subheader("📊 Track My Goals")

        saved_goals = db.load_goals(user_id=auth.get_user_id())

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
                    # Progress bar with milestones
                    milestones = [25, 50, 75, 100]
                    milestone_markers = ""
                    for ms in milestones:
                        check = "✓" if prog_pct >= ms else ""
                        milestone_markers += (
                            f'<span style="position:absolute; left:{ms}%; transform:translateX(-50%); '
                            f'top: -16px; font-size:0.65em; color: {"#27ae60" if prog_pct >= ms else "#999"};">'
                            f"{check}{ms}%</span>"
                        )

                    st.markdown(
                        f"""<div style="margin: 20px 0 10px 0; position: relative;">
                        {milestone_markers}
                        <div style="background: #eee; border-radius: 8px; height: 20px;">
                            <div style="background: linear-gradient(90deg, {prog_color}, {prog_color}cc);
                            width: {prog_pct}%; height: 20px; border-radius: 8px;
                            text-align: center; color: white; font-size: 0.8em; line-height: 20px;
                            font-weight: bold; min-width: 40px;">
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
                    # Portfolio alignment check
                    if holdings:
                        mf_in_portfolio = [
                            h for h in holdings if h.get("type") == "mutual_fund"
                        ]
                        stock_in_portfolio = [
                            h for h in holdings if h.get("type") == "stock"
                        ]
                        goal_sip_total = sum(
                            h.get("sip_monthly", 0)
                            for h in mf_in_portfolio
                            if h.get("sip_monthly", 0) > 0
                        )
                        goal_invested = sum(h.get("amount", 0) for h in holdings)

                        with st.expander(
                            "📋 Portfolio Alignment Check", expanded=False
                        ):
                            # Check allocation by asset type
                            equity_val = sum(
                                h.get("amount", 0) for h in stock_in_portfolio
                            )
                            mf_val = sum(h.get("amount", 0) for h in mf_in_portfolio)
                            total_val = equity_val + mf_val

                            if total_val > 0:
                                equity_pct = (equity_val / total_val) * 100
                                mf_pct = (mf_val / total_val) * 100

                                ac1, ac2, ac3 = st.columns(3)
                                ac1.metric(
                                    "Stocks",
                                    f"₹{equity_val:,.0f}",
                                    f"{equity_pct:.0f}%",
                                )
                                ac2.metric(
                                    "Mutual Funds", f"₹{mf_val:,.0f}", f"{mf_pct:.0f}%"
                                )
                                ac3.metric("Active SIPs", f"₹{goal_sip_total:,.0f}/mo")

                                # Recommendation based on time horizon
                                if years_remaining <= 3:
                                    if equity_pct > 30:
                                        st.warning(
                                            f"⚠️ Goal is {years_remaining:.0f} years away but {equity_pct:.0f}% is in stocks. "
                                            f"Move ₹{equity_val * 0.7:,.0f} to debt/liquid funds to protect capital."
                                        )
                                    else:
                                        st.success(
                                            "✅ Conservative allocation suits this near-term goal."
                                        )
                                elif years_remaining <= 7:
                                    if mf_pct < 40:
                                        st.info(
                                            f"💡 For a {years_remaining:.0f}-year goal, consider allocating more to mutual funds (currently {mf_pct:.0f}%)."
                                        )
                                else:
                                    if (
                                        equity_pct + mf_pct > 0
                                        and mf_pct < 30
                                        and len(mf_in_portfolio) == 0
                                    ):
                                        st.info(
                                            "💡 Long-term goal — start SIPs in index/equity MFs for better compounding."
                                        )

                                # Check if SIPs cover the goal
                                if goal_sip_total > 0 and g_sip > 0:
                                    coverage = (goal_sip_total / g_sip) * 100
                                    if coverage >= 100:
                                        st.success(
                                            f"✅ Your SIPs (₹{goal_sip_total:,.0f}/mo) cover this goal's requirement."
                                        )
                                    elif coverage >= 50:
                                        gap = g_sip - goal_sip_total
                                        st.info(
                                            f"💡 SIPs cover {coverage:.0f}% of this goal. Add ₹{gap:,.0f}/mo more."
                                        )
                                    else:
                                        st.warning(
                                            f"⚠️ SIPs only cover {coverage:.0f}% — add ₹{g_sip - goal_sip_total:,.0f}/mo to stay on track."
                                        )

                                # List holdings contributing to this goal
                                if mf_in_portfolio:
                                    st.caption("**Your MF holdings:**")
                                    for h in mf_in_portfolio:
                                        sip_tag = (
                                            f" · SIP ₹{h['sip_monthly']:,.0f}/mo"
                                            if h.get("sip_monthly", 0) > 0
                                            else ""
                                        )
                                        pnl = (
                                            h.get("current_value", h["amount"])
                                            - h["amount"]
                                        )
                                        pnl_icon = "🟢" if pnl >= 0 else "🔴"
                                        st.caption(
                                            f"  {pnl_icon} **{h['name']}** — ₹{h['amount']:,.0f}{sip_tag}"
                                        )
                            else:
                                st.info(
                                    "No investments found. Start investing to track alignment with this goal."
                                )

                    # F13: Inflation-adjusted goal info
                    inflation_rate = 6.0  # default
                    future_target = g_target * (
                        (1 + inflation_rate / 100) ** years_remaining
                    )
                    st.caption(
                        f"Created: {g_created} · {g_years}yr horizon · {g_return}% expected return · "
                        f"Inflation-adjusted target: ₹{future_target:,.0f} (at {inflation_rate}% inflation)"
                    )
                    if st.button(f"🗑️ Remove Goal", key=f"del_goal_{g_id}"):
                        db.delete_goal(g_id, user_id=auth.get_user_id())
                        st.rerun()

    # =====================================================================
    # F12: Goal-based Asset Allocation
    # =====================================================================
    with goal_tab4:
        st.subheader("📐 Goal-Based Asset Allocation")
        st.caption(
            "Different goals need different investment strategies based on time horizon"
        )

        saved_goals = db.load_goals(user_id=auth.get_user_id())

        if not saved_goals:
            st.info(
                "Save some goals in the **SIP Calculator** tab first, then come back here for allocation advice."
            )
        else:
            # Track fund categories already assigned to goals to avoid reuse
            assigned_categories = {}  # category -> goal_name

            for goal in saved_goals:
                g_name = goal.get("name", "Unnamed")
                g_years = goal.get("years", 10)
                g_target = goal.get("target", 0)
                g_sip = goal.get("monthly_sip", 0)
                g_created = goal.get("created_date", "")

                # Calculate remaining years
                years_left = g_years
                if g_created:
                    try:
                        created_dt = datetime.strptime(g_created, "%Y-%m-%d")
                        elapsed = (datetime.now() - created_dt).days / 365.25
                        years_left = max(0.5, round(g_years - elapsed, 1))
                    except Exception:
                        pass

                # Determine allocation based on time horizon
                if years_left <= 2:
                    alloc = {"Liquid/Ultra Short Debt": 80, "Short-term Debt Fund": 20}
                    risk_label = "Conservative"
                    advice = "Goal is very close. Move to safe debt instruments to protect capital."
                elif years_left <= 5:
                    alloc = {
                        "Large Cap / Index Fund": 40,
                        "Balanced/Hybrid Fund": 30,
                        "Short-term Debt": 30,
                    }
                    risk_label = "Moderate"
                    advice = "Medium-term goal. Mix equity and debt for growth with stability."
                elif years_left <= 10:
                    alloc = {
                        "Large Cap / Index Fund": 40,
                        "Mid Cap Fund": 25,
                        "Balanced/Hybrid Fund": 20,
                        "Debt Fund": 15,
                    }
                    risk_label = "Moderate-Aggressive"
                    advice = "Good time horizon. Equity-heavy allocation for growth."
                else:
                    alloc = {
                        "Large Cap / Index Fund": 30,
                        "Mid Cap Fund": 25,
                        "Small Cap Fund": 20,
                        "International Fund": 15,
                        "Debt Fund": 10,
                    }
                    risk_label = "Aggressive"
                    advice = (
                        "Long time horizon. Maximize equity for compounding growth."
                    )

                risk_color = {
                    "Conservative": "#27ae60",
                    "Moderate": "#3498db",
                    "Moderate-Aggressive": "#f39c12",
                    "Aggressive": "#e67e22",
                }.get(risk_label, "#95a5a6")

                with st.expander(
                    f"🎯 **{g_name}** — {years_left:.0f} years left · {risk_label}"
                ):
                    st.markdown(
                        f"""<div style="border-left: 4px solid {risk_color}; padding: 10px 14px; margin: 8px 0;
                        border-radius: 4px; background: {risk_color}11;">
                        <strong>{risk_label} Strategy</strong> — {advice}
                        </div>""",
                        unsafe_allow_html=True,
                    )

                    # Show allocation — skip categories already assigned to other goals
                    conflicts = []
                    available_alloc = {}
                    for category, pct in alloc.items():
                        if category in assigned_categories:
                            conflicts.append(
                                f"**{category}** (already assigned to *{assigned_categories[category]}*)"
                            )
                        else:
                            available_alloc[category] = pct

                    # Redistribute percentages among available categories
                    if available_alloc and len(available_alloc) < len(alloc):
                        total_available = sum(available_alloc.values())
                        if total_available > 0:
                            scale = 100.0 / total_available
                            available_alloc = {
                                k: round(v * scale) for k, v in available_alloc.items()
                            }

                    if conflicts:
                        st.caption(
                            "⚠️ Skipped (used by other goals): " + ", ".join(conflicts)
                        )

                    display_alloc = available_alloc if available_alloc else alloc
                    alloc_cols = st.columns(len(display_alloc))
                    for col, (category, pct) in zip(alloc_cols, display_alloc.items()):
                        sip_share = round(g_sip * pct / 100)
                        col.markdown(
                            f"""<div style="text-align:center; padding:8px; border-radius:8px;
                            background: {risk_color}11; border: 1px solid {risk_color}33;">
                            <div style="font-size:1.3em; font-weight:bold; color:{risk_color};">{pct}%</div>
                            <div style="font-weight:bold; font-size:0.85em;">{category}</div>
                            <div style="font-size:0.8em; opacity:0.7;">₹{sip_share:,.0f}/mo</div>
                            </div>""",
                            unsafe_allow_html=True,
                        )

                    # Glide path reminder
                    if years_left > 5:
                        st.caption(
                            f"📅 **Glide path:** When {years_left - 3:.0f} years remain, start shifting 10% from equity to debt each year."
                        )

                    # Mark these categories as assigned to this goal
                    for category in display_alloc:
                        assigned_categories[category] = g_name
