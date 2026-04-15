"""Retirement planning view — NPS/EPF/PPF tracking and projection."""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

import db


# ---------------------------------------------------------------------------
# Projection helpers
# ---------------------------------------------------------------------------

# Current government-set rates (April 2026)
DEFAULT_RATES = {
    "EPF": 8.25,
    "PPF": 7.1,
    "NPS_EQUITY": 12.0,
    "NPS_CORPORATE_BOND": 9.0,
    "NPS_GOVT_BOND": 8.5,
    "SSY": 8.2,
    "SCSS": 8.2,
    "NPS_BLENDED": 10.0,
}


def _project_corpus(
    current_balance: float,
    monthly_contribution: float,
    annual_rate: float,
    years: int,
    employer_contribution: float = 0,
) -> dict:
    """Project future corpus with monthly compounding."""
    r = annual_rate / 100 / 12
    total_monthly = monthly_contribution + employer_contribution
    months = years * 12

    # Future value of existing balance
    fv_balance = current_balance * ((1 + r) ** months)

    # Future value of monthly contributions (annuity)
    if r > 0:
        fv_contributions = total_monthly * (((1 + r) ** months - 1) / r)
    else:
        fv_contributions = total_monthly * months

    total_corpus = fv_balance + fv_contributions
    total_invested = current_balance + (total_monthly * months)
    returns = total_corpus - total_invested

    return {
        "corpus": round(total_corpus),
        "total_invested": round(total_invested),
        "returns": round(returns),
        "monthly_pension_4pct": round(total_corpus * 0.04 / 12),  # 4% SWR
        "monthly_pension_3pct": round(total_corpus * 0.03 / 12),  # 3% conservative SWR
    }


def _project_ppf(
    current_balance: float, annual_deposit: float, years_remaining: int
) -> dict:
    """Project PPF with annual compounding (max ₹1.5L/year)."""
    annual_deposit = min(annual_deposit, 150000)
    rate = DEFAULT_RATES["PPF"] / 100
    balance = current_balance

    for _ in range(years_remaining):
        balance = (balance + annual_deposit) * (1 + rate)

    return {
        "corpus": round(balance),
        "total_invested": round(current_balance + annual_deposit * years_remaining),
        "returns": round(balance - current_balance - annual_deposit * years_remaining),
        "tax_benefit": "Tax-free (EEE)",
    }


def _project_nps(
    current_balance: float,
    monthly_contribution: float,
    equity_pct: float,
    years: int,
) -> dict:
    """Project NPS with blended returns based on equity/debt split."""
    equity_return = DEFAULT_RATES["NPS_EQUITY"]
    debt_return = DEFAULT_RATES["NPS_GOVT_BOND"]
    blended = (equity_pct / 100 * equity_return) + (
        (100 - equity_pct) / 100 * debt_return
    )

    proj = _project_corpus(current_balance, monthly_contribution, blended, years)

    # NPS rules: 60% lump sum (tax-free), 40% annuity
    lump_sum = round(proj["corpus"] * 0.6)
    annuity_corpus = round(proj["corpus"] * 0.4)
    annuity_monthly = round(annuity_corpus * 0.06 / 12)  # ~6% annuity rate

    return {
        **proj,
        "blended_rate": round(blended, 1),
        "lump_sum_at_60": lump_sum,
        "annuity_corpus": annuity_corpus,
        "annuity_monthly": annuity_monthly,
        "tax_benefit": "80C (₹1.5L) + 80CCD(1B) (₹50K)",
    }


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


def render(holdings):
    st.header("🏦 Retirement Planning")
    st.caption("Track and project EPF, PPF, NPS, and other retirement instruments")

    user_id = None
    try:
        import auth

        user_id = auth.get_user_id()
    except Exception:
        pass

    tabs = st.tabs(
        [
            "📊 My Instruments",
            "📈 EPF Projector",
            "📈 PPF Projector",
            "📈 NPS Projector",
            "🏁 Unified View",
        ]
    )

    # --- Tab 1: My Instruments ---
    with tabs[0]:
        st.subheader("Retirement Instruments")
        instruments = db.load_fixed_instruments(user_id)

        # Filter to retirement-type instruments
        retirement_types = {
            "EPF",
            "PPF",
            "NPS",
            "NPS_EQUITY",
            "NPS_CORPORATE_BOND",
            "NPS_GOVT_BOND",
            "SSY",
            "SCSS",
        }
        ret_instruments = [
            i for i in instruments if i.get("type", "").upper() in retirement_types
        ]

        if ret_instruments:
            df = pd.DataFrame(ret_instruments)
            display_cols = [
                c
                for c in [
                    "type",
                    "current_balance",
                    "monthly_contribution",
                    "interest_rate",
                ]
                if c in df.columns
            ]
            if display_cols:
                st.dataframe(
                    df[display_cols], use_container_width=True, hide_index=True
                )

            total = sum(i.get("current_balance", 0) for i in ret_instruments)
            st.metric("Total Retirement Corpus (Current)", f"₹{total:,.0f}")
        else:
            st.info(
                "No retirement instruments tracked yet. Add them below or in **⚙️ Manage Portfolio**."
            )

        # Quick add form
        with st.expander("➕ Add Retirement Instrument"):
            col1, col2 = st.columns(2)
            with col1:
                inst_type = st.selectbox(
                    "Type",
                    ["EPF", "PPF", "NPS", "SSY", "SCSS"],
                    key="ret_type",
                )
                balance = st.number_input(
                    "Current Balance (₹)",
                    min_value=0,
                    value=0,
                    step=10000,
                    key="ret_balance",
                )
            with col2:
                monthly = st.number_input(
                    "Monthly Contribution (₹)",
                    min_value=0,
                    value=0,
                    step=1000,
                    key="ret_monthly",
                )
                employer = st.number_input(
                    "Employer Contribution (₹/month)",
                    min_value=0,
                    value=0,
                    step=1000,
                    key="ret_employer",
                    help="Applicable for EPF",
                )

            if st.button("Add Instrument", key="ret_add"):
                new_inst = {
                    "type": inst_type,
                    "name": inst_type,
                    "current_balance": balance,
                    "monthly_contribution": monthly,
                    "employer_contribution": employer,
                    "interest_rate": DEFAULT_RATES.get(inst_type, 8.0),
                    "start_date": datetime.now().strftime("%Y-%m-%d"),
                }
                instruments.append(new_inst)
                db.save_fixed_instruments(instruments, user_id)
                st.success(f"Added {inst_type}")
                st.rerun()

    # --- Tab 2: EPF Projector ---
    with tabs[1]:
        st.subheader("EPF Corpus Projector")

        col1, col2, col3 = st.columns(3)
        with col1:
            epf_balance = st.number_input(
                "Current EPF Balance (₹)",
                min_value=0,
                value=500000,
                step=50000,
                key="epf_bal",
            )
        with col2:
            epf_monthly = st.number_input(
                "Your Monthly Contribution (₹)",
                min_value=0,
                value=7500,
                step=500,
                key="epf_monthly",
            )
            epf_employer = st.number_input(
                "Employer Monthly (₹)",
                min_value=0,
                value=7500,
                step=500,
                key="epf_employer",
            )
        with col3:
            epf_rate = st.number_input(
                "Interest Rate (%)",
                min_value=0.0,
                value=DEFAULT_RATES["EPF"],
                step=0.25,
                key="epf_rate",
            )
            epf_years = st.slider("Years to Retirement", 1, 40, 25, key="epf_years")

        proj = _project_corpus(
            epf_balance, epf_monthly, epf_rate, epf_years, epf_employer
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Projected Corpus", f"₹{proj['corpus']:,.0f}")
        c2.metric("Total Invested", f"₹{proj['total_invested']:,.0f}")
        c3.metric("Interest Earned", f"₹{proj['returns']:,.0f}")

        st.info(
            f"💡 Monthly pension (4% SWR): **₹{proj['monthly_pension_4pct']:,}** | Conservative (3%): **₹{proj['monthly_pension_3pct']:,}**"
        )

        # Growth chart
        yearly = []
        bal = epf_balance
        monthly_total = epf_monthly + epf_employer
        r = epf_rate / 100 / 12
        for y in range(1, epf_years + 1):
            for _ in range(12):
                bal = (bal + monthly_total) * (1 + r)
            yearly.append({"Year": y, "Corpus (₹)": round(bal)})
        st.line_chart(pd.DataFrame(yearly).set_index("Year"))

    # --- Tab 3: PPF Projector ---
    with tabs[2]:
        st.subheader("PPF Corpus Projector")

        col1, col2, col3 = st.columns(3)
        with col1:
            ppf_balance = st.number_input(
                "Current PPF Balance (₹)",
                min_value=0,
                value=200000,
                step=25000,
                key="ppf_bal",
            )
        with col2:
            ppf_annual = st.number_input(
                "Annual Deposit (₹)",
                min_value=500,
                max_value=150000,
                value=150000,
                step=10000,
                key="ppf_annual",
            )
        with col3:
            ppf_years = st.slider(
                "Years Remaining (min 15)", 1, 30, 15, key="ppf_years"
            )

        proj = _project_ppf(ppf_balance, ppf_annual, ppf_years)

        c1, c2, c3 = st.columns(3)
        c1.metric("Maturity Value", f"₹{proj['corpus']:,.0f}")
        c2.metric("Total Deposited", f"₹{proj['total_invested']:,.0f}")
        c3.metric("Interest Earned", f"₹{proj['returns']:,.0f}")

        st.success(f"🛡️ Tax status: **{proj['tax_benefit']}** — Exempt at all stages")

        # Growth chart
        yearly = []
        bal = ppf_balance
        rate = DEFAULT_RATES["PPF"] / 100
        for y in range(1, ppf_years + 1):
            bal = (bal + ppf_annual) * (1 + rate)
            yearly.append({"Year": y, "Corpus (₹)": round(bal)})
        st.line_chart(pd.DataFrame(yearly).set_index("Year"))

    # --- Tab 4: NPS Projector ---
    with tabs[3]:
        st.subheader("NPS Corpus Projector")

        col1, col2 = st.columns(2)
        with col1:
            nps_balance = st.number_input(
                "Current NPS Balance (₹)",
                min_value=0,
                value=300000,
                step=50000,
                key="nps_bal",
            )
            nps_monthly = st.number_input(
                "Monthly Contribution (₹)",
                min_value=0,
                value=5000,
                step=500,
                key="nps_monthly",
            )
        with col2:
            nps_equity = st.slider(
                "Equity Allocation (%)",
                0,
                75,
                50,
                key="nps_equity",
                help="Max 75% equity allowed in NPS Active Choice",
            )
            nps_years = st.slider("Years to 60", 1, 40, 25, key="nps_years")

        proj = _project_nps(nps_balance, nps_monthly, nps_equity, nps_years)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total NPS Corpus", f"₹{proj['corpus']:,.0f}")
        c2.metric("Lump Sum (60%)", f"₹{proj['lump_sum_at_60']:,.0f}")
        c3.metric("Annuity Monthly (~6%)", f"₹{proj['annuity_monthly']:,}")

        st.info(
            f"📊 Blended return: **{proj['blended_rate']}%** | Tax benefit: **{proj['tax_benefit']}**"
        )

        st.caption(
            "NPS rules: 60% tax-free lump sum at 60, 40% mandatory annuity purchase"
        )

    # --- Tab 5: Unified Retirement View ---
    with tabs[4]:
        st.subheader("🏁 Total Retirement Picture")

        instruments = db.load_fixed_instruments(user_id)
        net_worth_data = db.load_net_worth(user_id) or {}

        # Aggregate from instruments + net worth
        epf_total = net_worth_data.get("epf_balance", 0)
        ppf_total = net_worth_data.get("ppf_balance", 0)
        nps_total = net_worth_data.get("nps_balance", 0)

        # Override with tracked instruments if present
        for inst in instruments:
            t = inst.get("type", "").upper()
            bal = inst.get("current_balance", 0)
            if t == "EPF" and bal > 0:
                epf_total = bal
            elif t == "PPF" and bal > 0:
                ppf_total = bal
            elif t.startswith("NPS") and bal > 0:
                nps_total += bal

        total_retirement = epf_total + ppf_total + nps_total
        mf_equity = sum(
            h["holding"].get("amount", 0)
            for h in (holdings or [])
            if h["holding"].get("type") == "mutual_fund"
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("EPF", f"₹{epf_total:,.0f}")
        col2.metric("PPF", f"₹{ppf_total:,.0f}")
        col3.metric("NPS", f"₹{nps_total:,.0f}")
        col4.metric("📊 Total Retirement", f"₹{total_retirement:,.0f}")

        if total_retirement > 0:
            pie_data = {"EPF": epf_total, "PPF": ppf_total, "NPS": nps_total}
            if mf_equity > 0:
                pie_data["Equity MFs"] = mf_equity

            df = pd.DataFrame(
                [
                    {"Instrument": k, "Value (₹)": v}
                    for k, v in pie_data.items()
                    if v > 0
                ]
            )
            if not df.empty:
                st.bar_chart(df.set_index("Instrument"))

            # Quick FIRE check
            st.divider()
            monthly_expenses = st.number_input(
                "Monthly Expenses (₹)",
                min_value=0,
                value=50000,
                step=5000,
                key="fire_expenses",
            )
            annual_expenses = monthly_expenses * 12
            fire_corpus = annual_expenses * 25  # 4% rule

            grand_total = total_retirement + mf_equity
            progress = (
                min(100, round((grand_total / fire_corpus) * 100, 1))
                if fire_corpus > 0
                else 0
            )

            st.progress(progress / 100)
            st.metric(
                "FIRE Progress",
                f"{progress}%",
                delta=f"₹{fire_corpus - grand_total:,.0f} remaining",
            )

            if progress >= 100:
                st.success(
                    "🎉 You've crossed the FIRE number! You may have enough to retire early."
                )
            elif progress >= 70:
                st.info("💪 Good progress — stay the course.")
            else:
                st.warning(
                    f"📈 Target: ₹{fire_corpus:,.0f} (25× annual expenses). Keep investing!"
                )
        else:
            st.info(
                "Add your EPF/PPF/NPS balances above or in **💎 Net Worth** to see the unified view."
            )

        # Comparison table
        st.divider()
        st.subheader("📖 Retirement Instrument Comparison")
        comparison = pd.DataFrame(
            [
                {
                    "Instrument": "EPF",
                    "Rate": "8.25%",
                    "Lock-in": "Till retirement (58)",
                    "Tax Benefit": "Sec 80C (₹1.5L)",
                    "Tax on Returns": "Tax-free (if >5yr)",
                },
                {
                    "Instrument": "PPF",
                    "Rate": "7.1%",
                    "Lock-in": "15 years",
                    "Tax Benefit": "Sec 80C (₹1.5L)",
                    "Tax on Returns": "Tax-free (EEE)",
                },
                {
                    "Instrument": "NPS",
                    "Rate": "8-12%",
                    "Lock-in": "Till 60",
                    "Tax Benefit": "80C + 80CCD(1B) (₹2L)",
                    "Tax on Returns": "60% tax-free, 40% annuity taxable",
                },
                {
                    "Instrument": "SSY",
                    "Rate": "8.2%",
                    "Lock-in": "21 years",
                    "Tax Benefit": "Sec 80C (₹1.5L)",
                    "Tax on Returns": "Tax-free (EEE)",
                },
                {
                    "Instrument": "SCSS",
                    "Rate": "8.2%",
                    "Lock-in": "5 years",
                    "Tax Benefit": "Sec 80C (₹1.5L)",
                    "Tax on Returns": "Interest taxable",
                },
            ]
        )
        st.dataframe(comparison, use_container_width=True, hide_index=True)
