"""F1: Net Worth Dashboard — unified view of all assets."""

import streamlit as st
import pandas as pd
from datetime import datetime

import db
import auth


def _load_net_worth_data(user_id):
    """Load all asset data for net worth calculation."""
    data = db.load_net_worth(user_id)
    if not data:
        data = {
            "bank_balance": 0,
            "fd_amount": 0,
            "ppf_balance": 0,
            "nps_balance": 0,
            "epf_balance": 0,
            "real_estate_value": 0,
            "gold_physical_value": 0,
            "other_assets": 0,
            "home_loan": 0,
            "car_loan": 0,
            "personal_loan": 0,
            "credit_card_debt": 0,
            "other_liabilities": 0,
        }
    return data


def render(holdings):
    st.title("💎 Net Worth Dashboard")
    st.caption(
        "Track your complete financial picture — all assets and liabilities in one place"
    )

    user_id = auth.get_user_id()
    nw_data = _load_net_worth_data(user_id)

    # --- Assets Section ---
    st.subheader("📈 Assets")

    with st.form("net_worth_form"):
        st.markdown("##### 🏦 Bank & Deposits")
        a1, a2, a3 = st.columns(3)
        bank_balance = a1.number_input(
            "Bank Balance (₹)",
            value=nw_data.get("bank_balance", 0),
            min_value=0,
            step=10000,
            key="nw_bank",
        )
        fd_amount = a2.number_input(
            "Fixed Deposits (₹)",
            value=nw_data.get("fd_amount", 0),
            min_value=0,
            step=10000,
            key="nw_fd",
        )
        epf_balance = a3.number_input(
            "EPF/PF Balance (₹)",
            value=nw_data.get("epf_balance", 0),
            min_value=0,
            step=10000,
            key="nw_epf",
        )

        st.markdown("##### 🏛️ Government Schemes")
        g1, g2 = st.columns(2)
        ppf_balance = g1.number_input(
            "PPF Balance (₹)",
            value=nw_data.get("ppf_balance", 0),
            min_value=0,
            step=10000,
            key="nw_ppf",
        )
        nps_balance = g2.number_input(
            "NPS Balance (₹)",
            value=nw_data.get("nps_balance", 0),
            min_value=0,
            step=10000,
            key="nw_nps",
        )

        st.markdown("##### 🏠 Other Assets")
        o1, o2, o3 = st.columns(3)
        real_estate_value = o1.number_input(
            "Real Estate Value (₹)",
            value=nw_data.get("real_estate_value", 0),
            min_value=0,
            step=100000,
            key="nw_re",
        )
        gold_physical_value = o2.number_input(
            "Physical Gold/Jewellery (₹)",
            value=nw_data.get("gold_physical_value", 0),
            min_value=0,
            step=10000,
            key="nw_gold",
        )
        other_assets = o3.number_input(
            "Other Assets (₹)",
            value=nw_data.get("other_assets", 0),
            min_value=0,
            step=10000,
            key="nw_other",
        )

        st.divider()
        st.markdown("##### 💳 Liabilities")
        l1, l2, l3, l4 = st.columns(4)
        home_loan = l1.number_input(
            "Home Loan (₹)",
            value=nw_data.get("home_loan", 0),
            min_value=0,
            step=50000,
            key="nw_hl",
        )
        car_loan = l2.number_input(
            "Car Loan (₹)",
            value=nw_data.get("car_loan", 0),
            min_value=0,
            step=10000,
            key="nw_cl",
        )
        personal_loan = l3.number_input(
            "Personal Loan (₹)",
            value=nw_data.get("personal_loan", 0),
            min_value=0,
            step=10000,
            key="nw_pl",
        )
        credit_card_debt = l4.number_input(
            "Credit Card Debt (₹)",
            value=nw_data.get("credit_card_debt", 0),
            min_value=0,
            step=5000,
            key="nw_cc",
        )
        other_liabilities = st.number_input(
            "Other Liabilities (₹)",
            value=nw_data.get("other_liabilities", 0),
            min_value=0,
            step=10000,
            key="nw_ol",
        )

        if st.form_submit_button("💾 Save Net Worth Data"):
            save_data = {
                "bank_balance": bank_balance,
                "fd_amount": fd_amount,
                "ppf_balance": ppf_balance,
                "nps_balance": nps_balance,
                "epf_balance": epf_balance,
                "real_estate_value": real_estate_value,
                "gold_physical_value": gold_physical_value,
                "other_assets": other_assets,
                "home_loan": home_loan,
                "car_loan": car_loan,
                "personal_loan": personal_loan,
                "credit_card_debt": credit_card_debt,
                "other_liabilities": other_liabilities,
            }
            db.save_net_worth(save_data, user_id)
            st.success("✅ Net worth data saved!")
            st.rerun()

    # --- Calculate totals ---
    # Portfolio value from holdings
    portfolio_value = sum(h["amount"] for h in holdings) if holdings else 0

    total_assets = (
        bank_balance
        + fd_amount
        + ppf_balance
        + nps_balance
        + epf_balance
        + real_estate_value
        + gold_physical_value
        + other_assets
        + portfolio_value
    )
    total_liabilities = (
        home_loan + car_loan + personal_loan + credit_card_debt + other_liabilities
    )
    net_worth = total_assets - total_liabilities

    st.divider()
    st.subheader("📊 Net Worth Summary")

    nw_color = "#27ae60" if net_worth >= 0 else "#e74c3c"
    st.markdown(
        f"""<div style="background: linear-gradient(135deg, {nw_color}22, {nw_color}11);
        border-left: 5px solid {nw_color}; border-radius: 10px;
        padding: 20px; margin: 10px 0;">
        <h2 style="margin:0; color: {nw_color};">💎 Net Worth: ₹{net_worth:,.0f}</h2>
        <p style="font-size: 1.1em; margin: 8px 0 0 0;">
        Assets: ₹{total_assets:,.0f} — Liabilities: ₹{total_liabilities:,.0f}</p>
        </div>""",
        unsafe_allow_html=True,
    )

    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Total Assets", f"₹{total_assets:,.0f}")
    n2.metric("Total Liabilities", f"₹{total_liabilities:,.0f}")
    n3.metric("Net Worth", f"₹{net_worth:,.0f}")
    debt_ratio = (
        round((total_liabilities / total_assets) * 100, 1) if total_assets > 0 else 0
    )
    n4.metric("Debt-to-Asset Ratio", f"{debt_ratio}%")

    # --- Asset allocation breakdown ---
    st.divider()
    st.subheader("📊 Asset Allocation")

    breakdown = {}
    if portfolio_value > 0:
        breakdown["Stocks & MFs"] = portfolio_value
    if bank_balance > 0:
        breakdown["Bank Balance"] = bank_balance
    if fd_amount > 0:
        breakdown["Fixed Deposits"] = fd_amount
    if ppf_balance > 0:
        breakdown["PPF"] = ppf_balance
    if nps_balance > 0:
        breakdown["NPS"] = nps_balance
    if epf_balance > 0:
        breakdown["EPF"] = epf_balance
    if real_estate_value > 0:
        breakdown["Real Estate"] = real_estate_value
    if gold_physical_value > 0:
        breakdown["Gold/Jewellery"] = gold_physical_value
    if other_assets > 0:
        breakdown["Other Assets"] = other_assets

    if breakdown:
        st.bar_chart(pd.Series(breakdown, name="₹"), height=300)

        # Percentage table
        rows = []
        for name, val in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            pct = (val / total_assets) * 100 if total_assets > 0 else 0
            rows.append(
                {"Asset": name, "Value": f"₹{val:,.0f}", "% of Total": f"{pct:.1f}%"}
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    # --- Insights ---
    st.divider()
    st.subheader("💡 Insights")

    insights = []
    budget = db.load_budget(user_id)
    if total_assets > 0:
        equity_pct = (portfolio_value / total_assets) * 100
        if equity_pct > 80:
            insights.append(
                "⚠️ Over 80% of your assets are in stocks/MFs. Consider diversifying into FDs, PPF, or gold."
            )
        elif equity_pct < 20 and total_assets > 500000:
            insights.append(
                "📊 Less than 20% in equities. For long-term wealth creation, consider increasing equity allocation."
            )

        if debt_ratio > 50:
            insights.append(
                "🚨 Your debt-to-asset ratio is above 50%. Focus on reducing high-interest debt first."
            )
        elif debt_ratio > 30:
            insights.append(
                "⚠️ Debt-to-asset ratio is above 30%. Try to pay down loans faster."
            )

        if bank_balance > total_assets * 0.3 and total_assets > 200000:
            insights.append(
                f"💰 ₹{bank_balance:,.0f} sitting in bank. Move excess to FDs, liquid funds, or short-term debt funds for better returns."
            )

        if ppf_balance == 0 and nps_balance == 0 and total_assets > 300000:
            insights.append(
                "🏛️ No PPF or NPS investments. These offer tax benefits under Section 80C and 80CCD(1B)."
            )

        emergency_fund_needed = 0
        if budget and budget.get("expenses", 0) > 0:
            emergency_fund_needed = budget["expenses"] * 6
            liquid_assets = bank_balance + fd_amount
            if liquid_assets < emergency_fund_needed:
                gap = emergency_fund_needed - liquid_assets
                insights.append(
                    f"🆘 Emergency fund gap: ₹{gap:,.0f}. You need 6 months expenses (₹{emergency_fund_needed:,.0f}) in liquid form."
                )

        if credit_card_debt > 0:
            insights.append(
                f"🔴 Credit card debt of ₹{credit_card_debt:,.0f} at ~36% APR is very expensive. Pay this off immediately before investing."
            )

    if not insights:
        insights.append(
            "✅ Your financial position looks balanced. Keep tracking and reviewing monthly!"
        )

    for insight in insights:
        st.markdown(insight)

    # Cross-links to detailed pages
    st.divider()
    st.info(
        "🏖️ See **🏦 Retirement** for your Financial Freedom / FIRE progress.  \n📊 See **📁 My Portfolio** for diversification analysis."
    )
