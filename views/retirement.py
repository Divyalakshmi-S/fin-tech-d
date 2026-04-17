"""Retirement planning view — NPS/EPF/PPF tracking and projection."""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

import db
import auth


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
        user_id = auth.get_user_id()
    except Exception:
        pass  # auth unavailable in headless/bot mode

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

        # Load budget for FIRE calculation
        budget_data = db.load_budget(user_id)
        budget_expenses = budget_data.get("expenses", 0)
        budget_investments = budget_data.get("investments", 0)
        budget_income = budget_data.get("income", 0)

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
            h.get("amount", 0)
            for h in (holdings or [])
            if h.get("type") == "mutual_fund"
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("EPF", f"₹{epf_total:,.0f}")
        col2.metric("PPF", f"₹{ppf_total:,.0f}")
        col3.metric("NPS", f"₹{nps_total:,.0f}")
        col4.metric("📊 Total Retirement", f"₹{total_retirement:,.0f}")

        if total_retirement > 0 or mf_equity > 0 or (holdings and len(holdings) > 0):
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

            # === Comprehensive Retirement Planner ===
            st.divider()
            st.markdown("##### 🔥 Retirement & FIRE Planner")

            # --- Personal Inputs ---
            p1, p2, p3 = st.columns(3)
            current_age = p1.number_input(
                "Current Age", min_value=18, max_value=70, value=30, key="uv_age"
            )
            retirement_age = p2.number_input(
                "Retirement Age",
                min_value=current_age + 1,
                max_value=80,
                value=60,
                key="uv_ret_age",
            )
            life_expectancy = p3.number_input(
                "Life Expectancy",
                min_value=retirement_age + 1,
                max_value=100,
                value=85,
                key="uv_life",
            )

            # --- Expense & Rate Inputs ---
            if budget_expenses > 0:
                st.caption(
                    f"📋 Monthly expenses pre-filled from your **Budget Plan**: ₹{budget_expenses:,}"
                )

            e1, e2, e3 = st.columns(3)
            monthly_expenses = e1.number_input(
                "Monthly Expenses (₹)",
                min_value=0,
                value=budget_expenses if budget_expenses > 0 else 50000,
                step=5000,
                key="uv_expenses",
                help="Pre-filled from Budget" if budget_expenses > 0 else None,
            )
            inflation_rate = e2.number_input(
                "Inflation Rate (%)",
                min_value=1.0,
                max_value=15.0,
                value=6.0,
                step=0.5,
                key="uv_inflation",
            )
            post_ret_return = e3.number_input(
                "Post-Retirement Return (%)",
                min_value=1.0,
                max_value=15.0,
                value=7.0,
                step=0.5,
                key="uv_post_ret",
                help="Expected return on corpus after retirement",
            )

            # --- Savings & SIP Inputs ---
            # Auto-calculate current savings from instruments + holdings
            stock_equity = sum(
                h.get("amount", 0) for h in (holdings or []) if h.get("type") == "stock"
            )
            grand_total_now = total_retirement + mf_equity + stock_equity

            # Detect actual SIPs from portfolio
            active_sips = [h for h in (holdings or []) if h.get("sip_monthly", 0) > 0]
            portfolio_sip_total = sum(h["sip_monthly"] for h in active_sips)

            # Show portfolio breakdown
            if grand_total_now > 0:
                with st.expander(
                    f"📋 Your savings breakdown: ₹{grand_total_now:,.0f} total",
                    expanded=False,
                ):
                    if epf_total > 0:
                        st.caption(f"• **EPF** — ₹{epf_total:,.0f}")
                    if ppf_total > 0:
                        st.caption(f"• **PPF** — ₹{ppf_total:,.0f}")
                    if nps_total > 0:
                        st.caption(f"• **NPS** — ₹{nps_total:,.0f}")
                    if mf_equity > 0:
                        st.caption(f"• **Equity MFs** — ₹{mf_equity:,.0f}")
                    if stock_equity > 0:
                        st.caption(f"• **Stocks** — ₹{stock_equity:,.0f}")
                    if active_sips:
                        st.caption(
                            f"**Active SIPs:** {len(active_sips)} totalling ₹{portfolio_sip_total:,.0f}/mo"
                        )
                        for h in active_sips:
                            st.caption(f"  ↳ {h['name']} — ₹{h['sip_monthly']:,.0f}/mo")

            # Choose best SIP default: portfolio SIPs > budget investments > 20000
            sip_default = 20000
            sip_source = None
            if portfolio_sip_total > 0:
                sip_default = int(portfolio_sip_total)
                sip_source = "portfolio SIPs"
            elif budget_investments > 0:
                sip_default = int(budget_investments)
                sip_source = "Budget"

            s1, s2, s3 = st.columns(3)
            current_savings = s1.number_input(
                "Total Current Savings (₹)",
                min_value=0,
                step=100000,
                value=int(grand_total_now),
                key="uv_savings",
                help="Auto-filled from your instruments + portfolio",
            )
            pre_ret_return = s2.number_input(
                "Pre-Retirement Return (%)",
                min_value=1.0,
                max_value=20.0,
                value=12.0,
                step=0.5,
                key="uv_pre_ret",
            )
            monthly_sip = s3.number_input(
                "Current Monthly SIP (₹)",
                min_value=0,
                step=5000,
                value=sip_default,
                key="uv_sip",
                help=f"Pre-filled from {sip_source}" if sip_source else None,
            )

            # --- Calculations ---
            years_to_retire = retirement_age - current_age
            years_in_retirement = life_expectancy - retirement_age

            # Future monthly expenses at retirement (inflation-adjusted)
            future_monthly_exp = monthly_expenses * (
                (1 + inflation_rate / 100) ** years_to_retire
            )
            future_annual_exp = future_monthly_exp * 12

            # Corpus needed using real return (post-retirement return minus inflation)
            real_return = (
                (1 + post_ret_return / 100) / (1 + inflation_rate / 100) - 1
            ) * 100
            if real_return > 0:
                corpus_needed = future_annual_exp * (
                    (1 - (1 + real_return / 100) ** (-years_in_retirement))
                    / (real_return / 100)
                )
            else:
                corpus_needed = future_annual_exp * years_in_retirement

            # Projected corpus from current savings + SIP
            r_pre = pre_ret_return / 100 / 12
            n_months = years_to_retire * 12
            future_savings = current_savings * ((1 + r_pre) ** n_months)
            if r_pre > 0:
                future_sip = (
                    monthly_sip * (((1 + r_pre) ** n_months - 1) / r_pre) * (1 + r_pre)
                )
            else:
                future_sip = monthly_sip * n_months
            projected_corpus = future_savings + future_sip

            shortfall = max(corpus_needed - projected_corpus, 0)
            surplus = max(projected_corpus - corpus_needed, 0)

            # FIRE number (simple 25x today's expenses)
            fire_number = monthly_expenses * 12 * 25

            # --- Results Display ---
            st.divider()

            corpus_color = "#27ae60" if projected_corpus >= corpus_needed else "#e74c3c"
            st.markdown(
                f"""<div style="background: linear-gradient(135deg, {corpus_color}22, {corpus_color}11);
                border-left: 5px solid {corpus_color}; border-radius: 10px; padding: 20px; margin: 10px 0;">
                <h3 style="margin:0;">🏖️ Retirement Corpus Needed: ₹{corpus_needed:,.0f}</h3>
                <p style="font-size: 1.1em; margin: 8px 0;">Your projected corpus: <strong style="color: {corpus_color};">₹{projected_corpus:,.0f}</strong></p>
                <p style="margin: 0; opacity: 0.8;">Monthly expenses at retirement: ₹{future_monthly_exp:,.0f}/month (today's ₹{monthly_expenses:,.0f} after {inflation_rate}% inflation)</p>
                </div>""",
                unsafe_allow_html=True,
            )

            rr1, rr2, rr3, rr4 = st.columns(4)
            rr1.metric("Years to Retire", f"{years_to_retire}")
            rr2.metric("Corpus Needed", f"₹{corpus_needed / 10000000:.2f} Cr")
            rr3.metric("Projected Corpus", f"₹{projected_corpus / 10000000:.2f} Cr")
            if shortfall > 0:
                rr4.metric("Shortfall", f"₹{shortfall:,.0f}")
            else:
                rr4.metric("Surplus", f"₹{surplus:,.0f}")

            if shortfall > 0:
                # Calculate extra SIP needed
                if r_pre > 0 and n_months > 0:
                    extra_sip = shortfall / (
                        (((1 + r_pre) ** n_months - 1) / r_pre) * (1 + r_pre)
                    )
                else:
                    extra_sip = shortfall / n_months if n_months > 0 else 0
                st.warning(
                    f"⚠️ You need an additional **₹{extra_sip:,.0f}/month** SIP to bridge the gap. "
                    f"Total required: ₹{monthly_sip + extra_sip:,.0f}/month."
                )
            else:
                early_years = (
                    int(surplus / future_annual_exp) if future_annual_exp > 0 else 0
                )
                st.success(
                    f"✅ You're on track for retirement! You can even retire "
                    f"**{max(0, years_to_retire - early_years):.0f} years earlier** if you maintain this pace."
                )

            # FIRE number section
            st.divider()
            st.markdown("##### 🔥 FIRE Number (Financial Independence)")
            fire_inflation_adjusted = fire_number * (
                (1 + inflation_rate / 100) ** years_to_retire
            )
            f1, f2, f3 = st.columns(3)
            f1.metric("FIRE Corpus (25× annual)", f"₹{fire_number:,.0f}")
            f2.metric(
                f"Inflation-adjusted (age {retirement_age})",
                f"₹{fire_inflation_adjusted:,.0f}",
            )
            fire_progress = (
                min(100, round((grand_total_now / fire_number) * 100, 1))
                if fire_number > 0
                else 0
            )
            f3.metric("Current FIRE Progress", f"{fire_progress}%")

            st.progress(min(fire_progress / 100, 1.0))

            # Growth projection chart
            st.divider()
            st.markdown("##### 📊 Corpus Growth Projection")
            years_range = list(range(1, years_to_retire + 1))
            corpus_series = []
            for y in years_range:
                m = y * 12
                fv_s = current_savings * ((1 + r_pre) ** m)
                if r_pre > 0:
                    fv_sip = (
                        monthly_sip * (((1 + r_pre) ** m - 1) / r_pre) * (1 + r_pre)
                    )
                else:
                    fv_sip = monthly_sip * m
                corpus_series.append(fv_s + fv_sip)

            chart_df = pd.DataFrame(
                {
                    "Your Corpus": corpus_series,
                    "Target Corpus": [corpus_needed] * len(years_range),
                },
                index=[f"Age {current_age + y}" for y in years_range],
            )
            chart_step = max(1, len(years_range) // 15)
            st.line_chart(chart_df.iloc[::chart_step], height=300)

            # Budget context
            if budget_income > 0 and budget_expenses > 0:
                st.divider()
                st.markdown("##### 💰 Your Budget Context")
                b1, b2, b3 = st.columns(3)
                b1.metric("Monthly Income", f"₹{budget_income:,}")
                b2.metric("Monthly Expenses", f"₹{budget_expenses:,}")
                b3.metric(
                    "Monthly Investments",
                    f"₹{budget_investments:,}" if budget_investments > 0 else "—",
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
