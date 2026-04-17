"""F11: Financial Health Checkup Wizard — step-by-step financial assessment."""

import streamlit as st
import json
from datetime import datetime

import db
import auth


def render(holdings):
    st.title("🏥 Financial Health Checkup")
    st.caption("A step-by-step assessment of your complete financial health")

    user_id = auth.get_user_id()

    # Initialize wizard state
    if "checkup_step" not in st.session_state:
        st.session_state["checkup_step"] = 0
    if "checkup_data" not in st.session_state:
        # Pre-fill from Budget if available
        prefill = {}
        budget = db.load_budget(user_id)
        if budget:
            if budget.get("income", 0) > 0:
                prefill["monthly_income"] = budget["income"]
            if budget.get("expenses", 0) > 0:
                prefill["monthly_expenses"] = budget["expenses"]
            if budget.get("investments", 0) > 0:
                prefill["monthly_investments"] = budget["investments"]
        # Pre-fill from Net Worth if available
        nw = db.load_net_worth(user_id)
        if nw:
            if nw.get("bank_balance", 0) > 0:
                prefill["bank_savings"] = nw["bank_balance"]
            if nw.get("fd_amount", 0) > 0:
                prefill["fd_rd"] = nw["fd_amount"]
            ppf_nps_total = (
                nw.get("ppf_balance", 0)
                + nw.get("nps_balance", 0)
                + nw.get("epf_balance", 0)
            )
            if ppf_nps_total > 0:
                prefill["ppf_nps"] = ppf_nps_total
            if nw.get("gold_physical_value", 0) > 0:
                prefill["gold_value"] = nw["gold_physical_value"]
            if nw.get("real_estate_value", 0) > 0:
                prefill["real_estate"] = nw["real_estate_value"]
            loan_total = (
                nw.get("home_loan", 0)
                + nw.get("car_loan", 0)
                + nw.get("personal_loan", 0)
                + nw.get("credit_card_debt", 0)
                + nw.get("other_debt", 0)
            )
            if loan_total > 0:
                prefill["total_loans"] = loan_total
        st.session_state["checkup_data"] = prefill

    step = st.session_state["checkup_step"]
    data = st.session_state["checkup_data"]

    steps = [
        "👤 Basic Info",
        "💰 Income & Expenses",
        "🏦 Savings & Investments",
        "🛡️ Insurance & Protection",
        "🎯 Goals & Planning",
        "📊 Results & Recommendations",
    ]

    # Progress bar
    progress = (step / (len(steps) - 1)) * 100
    st.markdown(
        f"""<div style="background: #eee; border-radius: 8px; height: 12px; margin: 10px 0;">
        <div style="background: #3498db; width: {progress}%; height: 12px; border-radius: 8px;"></div>
        </div>
        <div style="text-align: center; font-size: 0.85em; opacity: 0.7;">Step {step + 1} of {len(steps)}: {steps[step]}</div>""",
        unsafe_allow_html=True,
    )

    st.divider()

    # =====================================================================
    # Step 0: Basic Info
    # =====================================================================
    if step == 0:
        st.subheader("👤 Tell us about yourself")

        data["age"] = st.number_input(
            "Your Age",
            min_value=18,
            max_value=80,
            value=data.get("age", 30),
            key="chk_age",
        )
        data["marital_status"] = st.selectbox(
            "Marital Status",
            ["Single", "Married", "Married with kids"],
            index=["Single", "Married", "Married with kids"].index(
                data.get("marital_status", "Single")
            ),
            key="chk_marital",
        )
        data["dependents"] = st.number_input(
            "Number of Dependents",
            min_value=0,
            max_value=10,
            value=data.get("dependents", 0),
            key="chk_dep",
        )
        data["employment"] = st.selectbox(
            "Employment Type",
            ["Salaried", "Self-employed", "Freelancer", "Retired"],
            index=["Salaried", "Self-employed", "Freelancer", "Retired"].index(
                data.get("employment", "Salaried")
            ),
            key="chk_emp",
        )

    # =====================================================================
    # Step 1: Income & Expenses
    # =====================================================================
    elif step == 1:
        st.subheader("💰 Income & Expenses")

        budget = db.load_budget(user_id)
        if budget and budget.get("income", 0) > 0:
            st.caption("💡 Pre-filled from your **Budget** page. Adjust if needed.")

        data["monthly_income"] = st.number_input(
            "Monthly Income (₹)",
            min_value=0,
            step=10000,
            value=int(data.get("monthly_income", 50000)),
            key="chk_income",
        )
        data["monthly_expenses"] = st.number_input(
            "Monthly Expenses (₹)",
            min_value=0,
            step=5000,
            value=int(data.get("monthly_expenses", 30000)),
            key="chk_expenses",
        )
        data["monthly_emi"] = st.number_input(
            "Monthly EMIs (₹)",
            min_value=0,
            step=5000,
            value=int(data.get("monthly_emi", 0)),
            key="chk_emi",
        )
        data["monthly_investments"] = st.number_input(
            "Monthly Investments/SIPs (₹)",
            min_value=0,
            step=5000,
            value=int(data.get("monthly_investments", 10000)),
            key="chk_inv",
        )

    # =====================================================================
    # Step 2: Savings & Investments
    # =====================================================================
    elif step == 2:
        st.subheader("🏦 Savings & Investments")

        nw = db.load_net_worth(user_id)
        if nw and nw.get("bank_balance", 0) > 0:
            st.caption("💡 Pre-filled from saved data. Adjust if needed.")

        data["bank_savings"] = st.number_input(
            "Bank Savings (₹)",
            min_value=0,
            step=50000,
            value=int(data.get("bank_savings", 0)),
            key="chk_bank",
        )
        data["fd_rd"] = st.number_input(
            "FD/RD Total (₹)",
            min_value=0,
            step=50000,
            value=int(data.get("fd_rd", 0)),
            key="chk_fd",
        )
        data["equity_value"] = st.number_input(
            "Stocks & Mutual Funds (₹)",
            min_value=0,
            step=50000,
            value=int(
                data.get(
                    "equity_value",
                    sum(h["amount"] for h in holdings) if holdings else 0,
                )
            ),
            key="chk_equity",
        )
        data["ppf_nps"] = st.number_input(
            "PPF/NPS/EPF Total (₹)",
            min_value=0,
            step=50000,
            value=int(data.get("ppf_nps", 0)),
            key="chk_ppf",
        )
        data["gold_value"] = st.number_input(
            "Gold/Silver Holdings (₹)",
            min_value=0,
            step=10000,
            value=int(data.get("gold_value", 0)),
            key="chk_gold",
        )
        data["real_estate"] = st.number_input(
            "Real Estate Value (₹)",
            min_value=0,
            step=500000,
            value=int(data.get("real_estate", 0)),
            key="chk_re",
        )
        data["total_loans"] = st.number_input(
            "Total Outstanding Loans (₹)",
            min_value=0,
            step=100000,
            value=int(data.get("total_loans", 0)),
            key="chk_loans",
        )

    # =====================================================================
    # Step 3: Insurance & Protection
    # =====================================================================
    elif step == 3:
        st.subheader("🛡️ Insurance & Protection")

        data["has_life_insurance"] = st.checkbox(
            "I have life insurance (term plan)",
            value=data.get("has_life_insurance", False),
            key="chk_life_ins",
        )
        if data["has_life_insurance"]:
            data["life_cover"] = st.number_input(
                "Life Insurance Cover (₹)",
                min_value=0,
                step=500000,
                value=int(data.get("life_cover", 0)),
                key="chk_life_cover",
            )
        else:
            data["life_cover"] = 0

        data["has_health_insurance"] = st.checkbox(
            "I have health insurance",
            value=data.get("has_health_insurance", False),
            key="chk_health_ins",
        )
        if data["has_health_insurance"]:
            data["health_cover"] = st.number_input(
                "Health Insurance Cover (₹)",
                min_value=0,
                step=100000,
                value=int(data.get("health_cover", 0)),
                key="chk_health_cover",
            )
        else:
            data["health_cover"] = 0

        data["has_emergency_fund"] = st.checkbox(
            "I have an emergency fund (3-6 months expenses)",
            value=data.get("has_emergency_fund", False),
            key="chk_ef",
        )
        data["has_will"] = st.checkbox(
            "I have a will/nomination for investments",
            value=data.get("has_will", False),
            key="chk_will",
        )

    # =====================================================================
    # Step 4: Goals & Planning
    # =====================================================================
    elif step == 4:
        st.subheader("🎯 Goals & Planning")

        data["has_retirement_plan"] = st.checkbox(
            "I have a retirement plan/target",
            value=data.get("has_retirement_plan", False),
            key="chk_ret_plan",
        )
        data["retirement_age_target"] = st.number_input(
            "Target Retirement Age",
            min_value=40,
            max_value=70,
            value=data.get("retirement_age_target", 60),
            key="chk_ret_age",
        )
        data["has_tax_plan"] = st.checkbox(
            "I actively plan tax savings (80C, 80D, etc.)",
            value=data.get("has_tax_plan", False),
            key="chk_tax",
        )
        data["reviews_portfolio"] = st.selectbox(
            "How often do you review your portfolio?",
            ["Never", "Annually", "Quarterly", "Monthly", "Weekly"],
            index=["Never", "Annually", "Quarterly", "Monthly", "Weekly"].index(
                data.get("reviews_portfolio", "Never")
            ),
            key="chk_review",
        )
        data["risk_tolerance"] = st.selectbox(
            "Your risk tolerance",
            ["Conservative", "Moderate", "Aggressive"],
            index=["Conservative", "Moderate", "Aggressive"].index(
                data.get("risk_tolerance", "Moderate")
            ),
            key="chk_risk",
        )

    # =====================================================================
    # Step 5: Results & Recommendations
    # =====================================================================
    elif step == 5:
        st.subheader("📊 Your Financial Health Report")

        # Calculate scores
        scores = {}
        recommendations = []

        # 1. Savings rate
        if data.get("monthly_income", 0) > 0:
            savings_rate = (
                (
                    data["monthly_income"]
                    - data.get("monthly_expenses", 0)
                    - data.get("monthly_emi", 0)
                )
                / data["monthly_income"]
            ) * 100
            if savings_rate >= 30:
                scores["Savings Rate"] = 95
            elif savings_rate >= 20:
                scores["Savings Rate"] = 75
            elif savings_rate >= 10:
                scores["Savings Rate"] = 55
            else:
                scores["Savings Rate"] = 25
                recommendations.append(
                    "🚨 **Increase savings rate** — aim for at least 20% of income"
                )
        else:
            scores["Savings Rate"] = 0

        # 2. Emergency fund
        monthly_exp = data.get("monthly_expenses", 0) + data.get("monthly_emi", 0)
        liquid_assets = data.get("bank_savings", 0) + data.get("fd_rd", 0)
        ef_months = liquid_assets / monthly_exp if monthly_exp > 0 else 0
        if ef_months >= 6:
            scores["Emergency Fund"] = 95
        elif ef_months >= 3:
            scores["Emergency Fund"] = 70
        elif ef_months >= 1:
            scores["Emergency Fund"] = 40
            recommendations.append(
                f"⚠️ **Build emergency fund** — you have only {ef_months:.1f} months covered. need 6 months (₹{monthly_exp * 6:,.0f})"
            )
        else:
            scores["Emergency Fund"] = 10
            recommendations.append(
                f"🚨 **No emergency fund!** Save ₹{monthly_exp * 6:,.0f} (6 months expenses) in liquid form"
            )

        # 3. Insurance
        recommended_life = data.get("monthly_income", 0) * 12 * 10
        if (
            data.get("has_life_insurance")
            and data.get("life_cover", 0) >= recommended_life * 0.7
        ):
            scores["Life Insurance"] = 90
        elif data.get("has_life_insurance"):
            scores["Life Insurance"] = 60
            recommendations.append(
                f"⚠️ **Increase life cover** — recommended: ₹{recommended_life:,.0f} (10x annual income)"
            )
        else:
            scores["Life Insurance"] = 10
            if data.get("dependents", 0) > 0:
                recommendations.append(
                    f"🚨 **Get term insurance immediately!** You have {data['dependents']} dependents. Cover: ₹{recommended_life:,.0f}"
                )

        if data.get("has_health_insurance") and data.get("health_cover", 0) >= 500000:
            scores["Health Insurance"] = 90
        elif data.get("has_health_insurance"):
            scores["Health Insurance"] = 60
            recommendations.append(
                "⚠️ **Increase health cover** — minimum ₹5L recommended per person"
            )
        else:
            scores["Health Insurance"] = 10
            recommendations.append(
                "🚨 **Get health insurance** — one medical emergency can wipe out years of savings"
            )

        # 4. Debt health
        if data.get("monthly_income", 0) > 0:
            emi_ratio = (data.get("monthly_emi", 0) / data["monthly_income"]) * 100
            if emi_ratio == 0:
                scores["Debt Management"] = 95
            elif emi_ratio <= 30:
                scores["Debt Management"] = 80
            elif emi_ratio <= 50:
                scores["Debt Management"] = 50
                recommendations.append(
                    "⚠️ **High EMI burden** — EMIs are consuming "
                    + f"{emi_ratio:.0f}% of income. Try to reduce to under 30%"
                )
            else:
                scores["Debt Management"] = 20
                recommendations.append(
                    f"🚨 **Dangerous debt level** — {emi_ratio:.0f}% of income goes to EMIs. Prioritize debt repayment."
                )
        else:
            scores["Debt Management"] = 50

        # 5. Investment discipline
        inv_score = 50
        if data.get("monthly_investments", 0) > 0:
            inv_score += 20
        if data.get("reviews_portfolio", "Never") in ("Monthly", "Quarterly"):
            inv_score += 15
        if data.get("has_retirement_plan"):
            inv_score += 10
        if data.get("has_tax_plan"):
            inv_score += 10
        scores["Investment Discipline"] = min(inv_score, 100)

        if not data.get("has_retirement_plan"):
            recommendations.append(
                "⚠️ **Set a retirement target** — define a clear corpus goal and timeline"
            )
        if not data.get("has_tax_plan"):
            recommendations.append(
                "💡 **Start tax planning** — use 80C (₹1.5L) and 80CCD (₹50K NPS) to save taxes"
            )
        if data.get("reviews_portfolio", "Never") == "Never":
            recommendations.append(
                "📊 **Review portfolio regularly** — at least quarterly to stay on track"
            )

        # 6. Net worth
        total_assets = sum(
            [
                data.get("bank_savings", 0),
                data.get("fd_rd", 0),
                data.get("equity_value", 0),
                data.get("ppf_nps", 0),
                data.get("gold_value", 0),
                data.get("real_estate", 0),
            ]
        )
        total_liabilities = data.get("total_loans", 0)
        net_worth = total_assets - total_liabilities

        if data.get("monthly_income", 0) > 0:
            nw_ratio = net_worth / (data["monthly_income"] * 12)
            age = data.get("age", 30)
            expected_ratio = max((age - 25) * 0.5, 0)  # Rough guideline
            if nw_ratio >= expected_ratio:
                scores["Net Worth"] = 85
            elif nw_ratio >= expected_ratio * 0.5:
                scores["Net Worth"] = 60
            else:
                scores["Net Worth"] = 35
                recommendations.append(
                    "📈 **Grow your net worth** — aim for net worth = (Age - 25) × 0.5 × annual income"
                )
        else:
            scores["Net Worth"] = 50

        # Overall score
        overall = round(sum(scores.values()) / len(scores)) if scores else 0
        overall_color = (
            "#27ae60" if overall >= 70 else "#f39c12" if overall >= 50 else "#e74c3c"
        )
        overall_label = (
            "Excellent"
            if overall >= 80
            else (
                "Good"
                if overall >= 70
                else "Fair" if overall >= 50 else "Needs Attention"
            )
        )

        st.markdown(
            f"""<div style="background: linear-gradient(135deg, {overall_color}22, {overall_color}11);
            border-left: 5px solid {overall_color}; border-radius: 10px; padding: 20px; margin: 10px 0; text-align: center;">
            <h1 style="margin:0; color: {overall_color}; font-size: 3.5em;">🏥 {overall}/100</h1>
            <h2 style="margin: 4px 0; color: {overall_color};">{overall_label}</h2>
            <p style="opacity: 0.7;">Financial Health Score</p>
            </div>""",
            unsafe_allow_html=True,
        )

        # Component scores
        st.markdown("##### 📊 Score Breakdown")
        for name, score in sorted(scores.items(), key=lambda x: x[1]):
            c = "#27ae60" if score >= 70 else "#f39c12" if score >= 50 else "#e74c3c"
            st.markdown(
                f"""<div style="margin: 8px 0;">
                <strong>{name}</strong> — <span style="color: {c};">{score}/100</span>
                <div style="background: #eee; border-radius: 4px; height: 8px; margin: 4px 0;">
                <div style="background: {c}; width: {score}%; height: 8px; border-radius: 4px;"></div>
                </div></div>""",
                unsafe_allow_html=True,
            )

        # Key metrics
        st.divider()
        st.markdown("##### 💰 Key Metrics")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Net Worth", f"₹{net_worth:,.0f}")
        k2.metric("Total Assets", f"₹{total_assets:,.0f}")
        savings_rate_val = (
            (
                (
                    data.get("monthly_income", 0)
                    - data.get("monthly_expenses", 0)
                    - data.get("monthly_emi", 0)
                )
                / data.get("monthly_income", 1)
            )
            * 100
            if data.get("monthly_income", 0) > 0
            else 0
        )
        k3.metric("Savings Rate", f"{savings_rate_val:.0f}%")
        k4.metric("Emergency Fund", f"{ef_months:.1f} months")

        # Recommendations
        if recommendations:
            st.divider()
            st.markdown("##### 🎯 Action Items (Priority Order)")
            for i, rec in enumerate(recommendations, 1):
                st.markdown(f"{i}. {rec}")
        else:
            st.success("✅ Your financial health is excellent! Keep up the good work.")

    # Navigation buttons
    st.divider()
    nav_cols = st.columns(3)
    with nav_cols[0]:
        if step > 0:
            if st.button("⬅️ Previous"):
                st.session_state["checkup_step"] = step - 1
                st.rerun()
    with nav_cols[1]:
        if step == 5:
            if st.button("🔄 Start Over"):
                st.session_state["checkup_step"] = 0
                st.session_state["checkup_data"] = {}
                st.rerun()
    with nav_cols[2]:
        if step < 5:
            if st.button("Next ➡️"):
                st.session_state["checkup_step"] = step + 1
                st.session_state["checkup_data"] = data
                st.rerun()
