"""F7: Insurance Needs Calculator, F8: NPS/PPF/FD Tracker, F9: Portfolio Health Score,
F10: Discipline & Behavior Score."""

import streamlit as st
import pandas as pd
from datetime import datetime

import db
import auth
from analysis import compute_diversification, analyze_portfolio


def render(holdings):
    st.title("🛡️ Financial Health & Protection")
    st.caption(
        "Insurance needs, government schemes tracking, portfolio health score, and investor discipline"
    )

    health_tabs = st.tabs(
        [
            "🛡️ Insurance Needs",
            "🏛️ NPS/PPF/FD Tracker",
            "📊 Portfolio Health Score",
            "🎯 Discipline Score",
        ]
    )

    user_id = auth.get_user_id()

    # =====================================================================
    # F7: Insurance Needs Calculator
    # =====================================================================
    with health_tabs[0]:
        st.subheader("🛡️ Insurance Needs Calculator")
        st.caption("How much life and health cover do you need?")

        st.markdown("##### 👤 Life Insurance")
        i1, i2, i3 = st.columns(3)
        annual_income = i1.number_input(
            "Annual Income (₹)",
            min_value=0,
            step=100000,
            value=1000000,
            key="ins_income",
        )
        existing_life_cover = i2.number_input(
            "Existing Life Cover (₹)",
            min_value=0,
            step=500000,
            value=0,
            key="ins_cover",
        )
        num_dependents = i3.number_input(
            "Number of Dependents", min_value=0, max_value=10, value=2, key="ins_dep"
        )

        i4, i5 = st.columns(2)
        total_loans = i4.number_input(
            "Outstanding Loans (₹)", min_value=0, step=100000, value=0, key="ins_loans"
        )
        years_to_retire = i5.number_input(
            "Years to Retirement", min_value=1, max_value=40, value=25, key="ins_yrs"
        )

        # Life cover calculation (Human Life Value method simplified)
        recommended_cover = max(
            annual_income * 10,  # 10x income rule
            annual_income * years_to_retire * 0.6
            + total_loans,  # Income replacement + loans
        )
        cover_gap = max(recommended_cover - existing_life_cover, 0)

        cover_color = "#27ae60" if cover_gap == 0 else "#e74c3c"
        st.markdown(
            f"""<div style="background: linear-gradient(135deg, {cover_color}22, {cover_color}11);
            border-left: 5px solid {cover_color}; border-radius: 10px; padding: 20px; margin: 10px 0;">
            <h3 style="margin:0; color: {cover_color};">Recommended Life Cover: ₹{recommended_cover:,.0f}</h3>
            <p style="margin: 8px 0;">Current Cover: ₹{existing_life_cover:,.0f} · Gap: ₹{cover_gap:,.0f}</p>
            </div>""",
            unsafe_allow_html=True,
        )

        if cover_gap > 0:
            # Approximate term plan premium
            est_premium = cover_gap * 0.003  # ~₹3 per ₹1000 cover per year
            st.warning(
                f"⚠️ You need ₹{cover_gap:,.0f} more life cover. "
                f"A term plan for this amount costs roughly ₹{est_premium:,.0f}/year."
            )
        else:
            st.success("✅ Your life insurance cover looks adequate!")

        st.divider()
        st.markdown("##### 🏥 Health Insurance")

        h1, h2 = st.columns(2)
        existing_health_cover = h1.number_input(
            "Current Health Cover (₹)",
            min_value=0,
            step=100000,
            value=0,
            key="ins_health",
        )
        family_size = h2.number_input(
            "Family Size", min_value=1, max_value=10, value=4, key="ins_fam"
        )

        recommended_health = max(
            family_size * 500000, 1000000
        )  # ₹5L per member, min ₹10L

        health_gap = max(recommended_health - existing_health_cover, 0)
        health_color = "#27ae60" if health_gap == 0 else "#f39c12"

        c1, c2, c3 = st.columns(3)
        c1.metric("Recommended Cover", f"₹{recommended_health:,.0f}")
        c2.metric("Current Cover", f"₹{existing_health_cover:,.0f}")
        c3.metric("Gap", f"₹{health_gap:,.0f}")

        if health_gap > 0:
            st.warning(
                f"⚠️ Consider a top-up or super top-up plan for ₹{health_gap:,.0f} additional cover."
            )
        else:
            st.success("✅ Health insurance cover looks adequate!")

        st.divider()
        st.markdown("##### 💡 Insurance Tips")
        st.markdown(
            """
- **Term insurance** is the best value — pure protection at lowest cost
- **Buy early** — premiums increase with age; a 25-year-old pays ~50% less than a 35-year-old
- **Avoid ULIPs and endowment plans** — they mix insurance and investment poorly
- **Get a personal health plan** even if you have employer coverage — job changes leave you uninsured
- **Critical illness rider** — consider adding it to your term plan for cancer/heart attack coverage
"""
        )

    # =====================================================================
    # F8: NPS/PPF/FD Tracker
    # =====================================================================
    with health_tabs[1]:
        st.subheader("🏛️ Government Schemes & Fixed Income Tracker")

        instruments = db.load_fixed_instruments(user_id)
        if not instruments:
            instruments = []

        # Add new instrument
        with st.expander("➕ Add New Instrument"):
            with st.form("add_instrument_form"):
                fi_cols = st.columns(4)
                fi_type = fi_cols[0].selectbox(
                    "Type",
                    ["PPF", "NPS", "FD", "RD", "SSY", "NSC", "KVP", "SCSS"],
                    key="fi_type",
                )
                fi_name = fi_cols[1].text_input(
                    "Name/Bank", placeholder="e.g., SBI PPF", key="fi_name"
                )
                fi_amount = fi_cols[2].number_input(
                    "Current Value (₹)", min_value=0, step=10000, key="fi_amount"
                )
                fi_rate = fi_cols[3].number_input(
                    "Interest Rate (%)",
                    min_value=0.0,
                    max_value=15.0,
                    step=0.1,
                    value=7.1,
                    key="fi_rate",
                )

                fi_cols2 = st.columns(3)
                fi_start = fi_cols2[0].date_input("Start Date", key="fi_start")
                fi_maturity = fi_cols2[1].date_input("Maturity Date", key="fi_maturity")
                fi_monthly = fi_cols2[2].number_input(
                    "Monthly Contribution (₹)",
                    min_value=0,
                    step=1000,
                    value=0,
                    key="fi_monthly",
                )

                if st.form_submit_button("Add Instrument"):
                    if fi_name and fi_amount > 0:
                        new_instrument = {
                            "type": fi_type,
                            "name": fi_name.strip(),
                            "current_value": fi_amount,
                            "interest_rate": fi_rate,
                            "start_date": fi_start.strftime("%Y-%m-%d"),
                            "maturity_date": fi_maturity.strftime("%Y-%m-%d"),
                            "monthly_contribution": fi_monthly,
                        }
                        instruments.append(new_instrument)
                        db.save_fixed_instruments(instruments, user_id)
                        st.success(f"✅ Added {fi_type}: {fi_name}")
                        st.rerun()

        # Display instruments
        if instruments:
            total_fixed_income = sum(i.get("current_value", 0) for i in instruments)
            total_monthly = sum(i.get("monthly_contribution", 0) for i in instruments)

            f1, f2, f3 = st.columns(3)
            f1.metric("Total Fixed Income", f"₹{total_fixed_income:,.0f}")
            f2.metric("Instruments", f"{len(instruments)}")
            f3.metric("Monthly Contributions", f"₹{total_monthly:,.0f}")

            for idx, inst in enumerate(instruments):
                maturity_str = inst.get("maturity_date", "")
                days_to_maturity = ""
                if maturity_str:
                    try:
                        mat_date = datetime.strptime(maturity_str, "%Y-%m-%d")
                        days_left = (mat_date - datetime.now()).days
                        if days_left > 0:
                            days_to_maturity = f" · Matures in {days_left // 30} months"
                        elif days_left <= 0:
                            days_to_maturity = " · 🔴 MATURED"
                    except ValueError:
                        pass

                with st.expander(
                    f"**{inst['type']}** — {inst.get('name', '')} · ₹{inst.get('current_value', 0):,.0f}{days_to_maturity}"
                ):
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Current Value", f"₹{inst.get('current_value', 0):,.0f}")
                    m2.metric("Interest Rate", f"{inst.get('interest_rate', 0)}%")
                    m3.metric(
                        "Monthly Deposit",
                        f"₹{inst.get('monthly_contribution', 0):,.0f}",
                    )
                    m4.metric("Start Date", inst.get("start_date", "—"))

                    if st.button(f"🗑️ Remove", key=f"del_fi_{idx}"):
                        instruments.pop(idx)
                        db.save_fixed_instruments(instruments, user_id)
                        st.rerun()
        else:
            st.info(
                "No fixed-income instruments added yet. Use the form above to track your PPF, NPS, FDs, etc."
            )

        st.divider()
        st.markdown("##### 📊 Current Interest Rates (Approximate)")
        rates_data = {
            "Instrument": [
                "PPF",
                "NPS (Equity)",
                "NPS (Govt Bonds)",
                "FD (5yr)",
                "SSY",
                "NSC",
                "SCSS",
                "RD",
            ],
            "Rate": [
                "7.1%",
                "~12% (market)",
                "~8% (market)",
                "6.5-7.5%",
                "8.2%",
                "7.7%",
                "8.2%",
                "6.5-7%",
            ],
            "Lock-in": [
                "15 years",
                "Till 60",
                "Till 60",
                "5 years",
                "21 years",
                "5 years",
                "5 years",
                "5 years",
            ],
            "Tax Benefit": [
                "80C",
                "80C + 80CCD",
                "80C + 80CCD",
                "80C (tax-saving)",
                "80C",
                "80C",
                "—",
                "—",
            ],
        }
        st.dataframe(pd.DataFrame(rates_data), hide_index=True, width="stretch")

    # =====================================================================
    # F9: Portfolio Health Score
    # =====================================================================
    with health_tabs[2]:
        st.subheader("📊 Portfolio Health Score")
        st.caption("Composite score based on diversification, risk, and quality")

        if not holdings:
            st.info("Add investments in Manage Portfolio to see your health score.")
        else:
            # Calculate component scores
            total_invested = sum(h["amount"] for h in holdings)
            num_holdings = len(holdings)
            stocks = [h for h in holdings if h["type"] == "stock"]
            mfs = [h for h in holdings if h["type"] == "mutual_fund"]
            active_sips = [h for h in holdings if h.get("sip_monthly", 0) > 0]

            # 1. Diversification score (reuse existing)
            try:
                import json

                holdings_key = json.dumps(holdings, sort_keys=True, default=str)
                results = analyze_portfolio(holdings)
                div_data = compute_diversification(holdings, results)
                div_score = div_data["score"] if div_data else 50
            except Exception:
                div_score = 50

            # 2. Asset mix score (equity + debt balance)
            equity_pct = (
                (sum(h["amount"] for h in stocks) / total_invested * 100)
                if total_invested > 0
                else 0
            )
            mf_pct = (
                (sum(h["amount"] for h in mfs) / total_invested * 100)
                if total_invested > 0
                else 0
            )
            # Ideal: 60-80% equity for young investors
            if 40 <= equity_pct + mf_pct <= 90:
                mix_score = 80
            elif equity_pct + mf_pct > 90:
                mix_score = 60  # too aggressive
            elif equity_pct + mf_pct < 20:
                mix_score = 40  # too conservative
            else:
                mix_score = 70

            # 3. SIP consistency score
            sip_score = min(len(active_sips) * 20, 100)

            # 4. Holdings count score
            if 5 <= num_holdings <= 20:
                count_score = 90
            elif num_holdings < 5:
                count_score = 50
            else:
                count_score = 70  # too many

            # 5. Concentration score
            top_holding_pct = (
                max(h["amount"] for h in holdings) / total_invested * 100
                if total_invested > 0
                else 100
            )
            if top_holding_pct < 20:
                conc_score = 90
            elif top_holding_pct < 35:
                conc_score = 70
            elif top_holding_pct < 50:
                conc_score = 50
            else:
                conc_score = 30

            # Composite score
            composite = round(
                div_score * 0.25
                + mix_score * 0.20
                + sip_score * 0.20
                + count_score * 0.15
                + conc_score * 0.20
            )

            score_color = (
                "#27ae60"
                if composite >= 70
                else "#f39c12" if composite >= 50 else "#e74c3c"
            )
            score_label = (
                "Excellent"
                if composite >= 80
                else (
                    "Good"
                    if composite >= 70
                    else "Needs Improvement" if composite >= 50 else "Poor"
                )
            )

            st.markdown(
                f"""<div style="background: linear-gradient(135deg, {score_color}22, {score_color}11);
                border-left: 5px solid {score_color}; border-radius: 10px; padding: 20px; margin: 10px 0; text-align: center;">
                <h1 style="margin:0; color: {score_color}; font-size: 3em;">{composite}/100</h1>
                <h3 style="margin: 4px 0; color: {score_color};">{score_label}</h3>
                </div>""",
                unsafe_allow_html=True,
            )

            # Component breakdown
            components = [
                ("Diversification", div_score),
                ("Asset Mix", mix_score),
                ("SIP Consistency", sip_score),
                ("Holdings Count", count_score),
                ("Concentration", conc_score),
            ]

            st.markdown("##### Component Scores")
            for name, score in components:
                c = (
                    "#27ae60"
                    if score >= 70
                    else "#f39c12" if score >= 50 else "#e74c3c"
                )
                st.markdown(
                    f"""<div style="margin: 6px 0;">
                    <strong>{name}</strong> — <span style="color: {c};">{score}/100</span>
                    <div style="background: #eee; border-radius: 4px; height: 8px; margin: 4px 0;">
                    <div style="background: {c}; width: {score}%; height: 8px; border-radius: 4px;"></div>
                    </div></div>""",
                    unsafe_allow_html=True,
                )

            # Recommendations
            st.divider()
            st.markdown("##### 💡 Recommendations")
            if div_score < 60:
                st.markdown(
                    "- 📊 **Improve diversification** — spread investments across more sectors and asset types"
                )
            if sip_score < 60:
                st.markdown(
                    "- 📈 **Start more SIPs** — systematic investing reduces timing risk"
                )
            if conc_score < 50:
                st.markdown(
                    "- ⚖️ **Reduce concentration** — your top holding is too large a portion of portfolio"
                )
            if mix_score < 60:
                st.markdown(
                    "- 🎯 **Rebalance asset mix** — consider adding debt/gold for stability"
                )
            if composite >= 80:
                st.success(
                    "✅ Your portfolio is in great shape! Keep monitoring quarterly."
                )

    # =====================================================================
    # F10: Discipline & Behavior Score
    # =====================================================================
    with health_tabs[3]:
        st.subheader("🎯 Investor Discipline Score")
        st.caption("Track your investing habits and behavior patterns")

        if not holdings:
            st.info("Add investments to see your discipline score.")
        else:
            total_invested = sum(h["amount"] for h in holdings)
            active_sips = [h for h in holdings if h.get("sip_monthly", 0) > 0]
            total_sip = sum(h["sip_monthly"] for h in active_sips)

            # Discipline metrics
            metrics = []

            # 1. SIP adherence
            sip_count = len(active_sips)
            if sip_count >= 3:
                metrics.append(
                    (
                        "SIP Consistency",
                        95,
                        "You have 3+ active SIPs — excellent discipline",
                    )
                )
            elif sip_count >= 1:
                metrics.append(
                    (
                        "SIP Consistency",
                        70,
                        "You have SIPs running — add more for better consistency",
                    )
                )
            else:
                metrics.append(
                    (
                        "SIP Consistency",
                        20,
                        "No active SIPs — start at least one for disciplined investing",
                    )
                )

            # 2. Diversification discipline
            num_types = len(set(h["type"] for h in holdings))
            if num_types >= 2:
                metrics.append(
                    (
                        "Asset Diversity",
                        85,
                        "Investing across multiple asset types — good diversification thinking",
                    )
                )
            else:
                metrics.append(
                    (
                        "Asset Diversity",
                        40,
                        "Only one asset type — consider diversifying into MFs or stocks",
                    )
                )

            # 3. Investment regularity (check if transactions exist)
            has_transactions = any(h.get("transactions") for h in holdings)
            if has_transactions:
                metrics.append(
                    (
                        "Regular Investing",
                        80,
                        "You have transaction history showing regular activity",
                    )
                )
            else:
                metrics.append(
                    (
                        "Regular Investing",
                        50,
                        "Start tracking transactions for better discipline monitoring",
                    )
                )

            # 4. Goal alignment
            goals = db.load_goals(user_id)
            if goals and len(goals) >= 2:
                metrics.append(
                    (
                        "Goal Setting",
                        90,
                        f"You have {len(goals)} goals defined — purpose-driven investing",
                    )
                )
            elif goals:
                metrics.append(
                    (
                        "Goal Setting",
                        65,
                        "1 goal defined — set more specific goals for better focus",
                    )
                )
            else:
                metrics.append(
                    (
                        "Goal Setting",
                        20,
                        "No goals yet — define clear financial goals in the Goals section",
                    )
                )

            # 5. Budget tracking
            budget = db.load_budget(user_id)
            if budget and budget.get("income", 0) > 0:
                savings_rate = (
                    budget.get("investments", 0) / budget["income"] * 100
                    if budget["income"] > 0
                    else 0
                )
                if savings_rate >= 30:
                    metrics.append(
                        (
                            "Savings Rate",
                            95,
                            f"Saving {savings_rate:.0f}% of income — outstanding!",
                        )
                    )
                elif savings_rate >= 20:
                    metrics.append(
                        (
                            "Savings Rate",
                            80,
                            f"Saving {savings_rate:.0f}% of income — good discipline",
                        )
                    )
                elif savings_rate >= 10:
                    metrics.append(
                        (
                            "Savings Rate",
                            60,
                            f"Saving {savings_rate:.0f}% of income — try to increase to 20%+",
                        )
                    )
                else:
                    metrics.append(
                        (
                            "Savings Rate",
                            30,
                            f"Saving only {savings_rate:.0f}% — aim for at least 20% of income",
                        )
                    )
            else:
                metrics.append(
                    (
                        "Savings Rate",
                        30,
                        "Set up budget tracking to monitor savings rate",
                    )
                )

            # Calculate overall discipline score
            discipline_score = round(sum(s for _, s, _ in metrics) / len(metrics))
            d_color = (
                "#27ae60"
                if discipline_score >= 70
                else "#f39c12" if discipline_score >= 50 else "#e74c3c"
            )
            d_label = (
                "Disciplined Investor"
                if discipline_score >= 80
                else "Good Habits" if discipline_score >= 60 else "Needs Work"
            )

            st.markdown(
                f"""<div style="background: linear-gradient(135deg, {d_color}22, {d_color}11);
                border-left: 5px solid {d_color}; border-radius: 10px; padding: 20px; margin: 10px 0; text-align: center;">
                <h1 style="margin:0; color: {d_color}; font-size: 3em;">🎯 {discipline_score}/100</h1>
                <h3 style="margin: 4px 0; color: {d_color};">{d_label}</h3>
                </div>""",
                unsafe_allow_html=True,
            )

            for name, score, detail in metrics:
                c = (
                    "#27ae60"
                    if score >= 70
                    else "#f39c12" if score >= 50 else "#e74c3c"
                )
                st.markdown(
                    f"""<div style="margin: 8px 0;">
                    <strong>{name}</strong> — <span style="color: {c};">{score}/100</span>
                    <div style="background: #eee; border-radius: 4px; height: 8px; margin: 4px 0;">
                    <div style="background: {c}; width: {score}%; height: 8px; border-radius: 4px;"></div>
                    </div>
                    <span style="font-size: 0.85em; opacity: 0.7;">{detail}</span>
                    </div>""",
                    unsafe_allow_html=True,
                )
