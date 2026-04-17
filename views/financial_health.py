"""F7: Insurance Needs Calculator, F10: Discipline & Behavior Score."""

import streamlit as st

import db
import auth


def render(holdings):
    st.title("🛡️ Financial Health & Protection")
    st.caption("Insurance needs calculator and investor discipline tracking")

    health_tabs = st.tabs(
        [
            "🛡️ Insurance Needs",
            " Discipline Score",
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
    # F10: Discipline & Behavior Score
    # =====================================================================
    with health_tabs[1]:
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
