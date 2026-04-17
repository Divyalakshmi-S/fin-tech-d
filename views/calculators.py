"""F3/F5/F14: Financial calculators — Step-up SIP, Education Goal, Loan/EMI Impact."""

import streamlit as st
import pandas as pd
from datetime import datetime


def _future_value_sip(monthly, rate_annual, years):
    """Future value of SIP with monthly compounding."""
    r = rate_annual / 100 / 12
    n = years * 12
    if r <= 0:
        return monthly * n
    return monthly * (((1 + r) ** n - 1) / r) * (1 + r)


def _required_sip(target, rate_annual, years):
    """Monthly SIP needed to reach target."""
    r = rate_annual / 100 / 12
    n = years * 12
    if r <= 0:
        return target / n if n > 0 else 0
    return target / ((((1 + r) ** n - 1) / r) * (1 + r))


def _inflation_adjusted(amount, inflation_rate, years):
    """Future cost after inflation."""
    return amount * ((1 + inflation_rate / 100) ** years)


def render(holdings):
    st.title("🧮 Financial Calculators")
    st.caption("Step-up SIP and loan impact analysis")

    calc_tabs = st.tabs(
        [
            "📈 Step-up SIP",
            "💳 Loan/EMI Impact",
        ]
    )

    # =====================================================================
    # F3: Step-up SIP Calculator
    # =====================================================================
    # --- Pre-compute portfolio context once ---
    active_sips = [h for h in (holdings or []) if h.get("sip_monthly", 0) > 0]
    total_sip_monthly = sum(h["sip_monthly"] for h in active_sips)
    total_invested = sum(h.get("amount", 0) for h in (holdings or []))
    mf_holdings = [h for h in (holdings or []) if h.get("type") == "mutual_fund"]
    stock_holdings = [h for h in (holdings or []) if h.get("type") == "stock"]

    with calc_tabs[0]:
        st.subheader("📈 Step-up SIP Calculator")
        st.caption("See how increasing your SIP annually creates massive wealth")

        # Show current SIP context from portfolio
        if active_sips:
            with st.expander(
                f"📋 Your current SIPs: {len(active_sips)} active · ₹{total_sip_monthly:,.0f}/month",
                expanded=False,
            ):
                for h in active_sips:
                    st.caption(
                        f"• **{h['name']}** — ₹{h['sip_monthly']:,.0f}/mo ({h.get('type', 'stock')})"
                    )
            st.caption(
                f"💡 Your current total SIP is ₹{total_sip_monthly:,.0f}/mo. Use it as your starting base below."
            )

        su1, su2, su3 = st.columns(3)
        base_sip = su1.number_input(
            "Starting Monthly SIP (₹)",
            min_value=500,
            step=1000,
            value=max(int(total_sip_monthly), 500) if total_sip_monthly > 0 else 10000,
            key="su_sip",
            help=(
                "Pre-filled from your portfolio SIPs" if total_sip_monthly > 0 else None
            ),
        )
        annual_increase = su2.number_input(
            "Annual Increase (%)", min_value=0, max_value=50, value=10, key="su_inc"
        )
        su_years = su3.number_input(
            "Investment Period (years)",
            min_value=1,
            max_value=40,
            value=20,
            key="su_yrs",
        )

        su_return = st.number_input(
            "Expected Annual Return (%)",
            min_value=1.0,
            max_value=25.0,
            value=12.0,
            step=0.5,
            key="su_ret",
        )

        # Calculate step-up SIP
        r = su_return / 100 / 12
        total_invested_flat = 0
        total_invested_stepup = 0
        value_flat = 0
        value_stepup = 0

        flat_series = []
        stepup_series = []
        invested_flat_series = []
        invested_stepup_series = []

        current_sip = base_sip
        for year in range(1, su_years + 1):
            for month in range(12):
                total_invested_flat += base_sip
                total_invested_stepup += current_sip
                value_flat = value_flat * (1 + r) + base_sip
                value_stepup = value_stepup * (1 + r) + current_sip

            flat_series.append(value_flat)
            stepup_series.append(value_stepup)
            invested_flat_series.append(total_invested_flat)
            invested_stepup_series.append(total_invested_stepup)
            current_sip = current_sip * (1 + annual_increase / 100)

        extra_wealth = value_stepup - value_flat
        extra_invested = total_invested_stepup - total_invested_flat

        st.divider()

        # Results
        st.markdown(
            f"""<div style="background: linear-gradient(135deg, #27ae6022, #27ae6011);
            border-left: 5px solid #27ae60; border-radius: 10px; padding: 20px; margin: 10px 0;">
            <h3 style="margin:0; color: #27ae60;">Step-up SIP creates ₹{extra_wealth:,.0f} MORE wealth!</h3>
            <p style="margin: 8px 0;"><strong>Flat SIP:</strong> ₹{value_flat:,.0f} (invested ₹{total_invested_flat:,.0f})</p>
            <p style="margin: 0;"><strong>Step-up SIP:</strong> ₹{value_stepup:,.0f} (invested ₹{total_invested_stepup:,.0f})</p>
            </div>""",
            unsafe_allow_html=True,
        )

        sr1, sr2, sr3, sr4 = st.columns(4)
        sr1.metric("Flat SIP Final", f"₹{value_flat:,.0f}")
        sr2.metric("Step-up SIP Final", f"₹{value_stepup:,.0f}")
        sr3.metric("Extra Wealth", f"₹{extra_wealth:,.0f}")
        sr4.metric(f"SIP in Year {su_years}", f"₹{current_sip:,.0f}/mo")

        # Chart comparison
        chart_df = pd.DataFrame(
            {
                "Flat SIP": flat_series,
                "Step-up SIP": stepup_series,
                "Flat Invested": invested_flat_series,
                "Step-up Invested": invested_stepup_series,
            },
            index=[f"Year {y}" for y in range(1, su_years + 1)],
        )
        st.line_chart(chart_df[["Flat SIP", "Step-up SIP"]], height=300)

        st.info(
            f"💡 By increasing your SIP by just {annual_increase}% every year (e.g., matching your salary increment), "
            f"you invest ₹{extra_invested:,.0f} more but earn ₹{extra_wealth - extra_invested:,.0f} extra in returns!"
        )

        if active_sips:
            gap = base_sip - total_sip_monthly
            if gap > 0:
                st.warning(
                    f"⚠️ Your current SIPs total ₹{total_sip_monthly:,.0f}/mo but this plan uses ₹{base_sip:,.0f}/mo. "
                    f"You need ₹{gap:,.0f}/mo more in SIPs to match."
                )
            elif gap == 0:
                st.success(
                    "✅ This matches your current SIP amount. Just add a 10% annual step-up!"
                )

    # =====================================================================
    # F14: Loan/EMI Impact Calculator
    # =====================================================================
    with calc_tabs[1]:
        st.subheader("💳 Loan/EMI Impact Calculator")
        st.caption(
            "See how taking a loan affects your investment capacity and goal timelines"
        )

        lc1, lc2, lc3 = st.columns(3)
        loan_amount = lc1.number_input(
            "Loan Amount (₹)",
            min_value=50000,
            step=100000,
            value=3000000,
            key="loan_amt",
        )
        loan_rate = lc2.number_input(
            "Interest Rate (%)",
            min_value=1.0,
            max_value=25.0,
            value=8.5,
            step=0.25,
            key="loan_rate",
        )
        loan_tenure = lc3.number_input(
            "Tenure (years)", min_value=1, max_value=30, value=20, key="loan_tenure"
        )

        # EMI calculation
        r_monthly = loan_rate / 100 / 12
        n_months = loan_tenure * 12
        if r_monthly > 0:
            emi = (
                loan_amount
                * r_monthly
                * ((1 + r_monthly) ** n_months)
                / (((1 + r_monthly) ** n_months) - 1)
            )
        else:
            emi = loan_amount / n_months
        total_payment = emi * n_months
        total_interest = total_payment - loan_amount

        st.divider()

        st.markdown(
            f"""<div style="background: linear-gradient(135deg, #e74c3c22, #e74c3c11);
            border-left: 5px solid #e74c3c; border-radius: 10px; padding: 20px; margin: 10px 0;">
            <h3 style="margin:0; color: #e74c3c;">💳 Monthly EMI: ₹{emi:,.0f}</h3>
            <p style="margin: 8px 0;">Total Payment: ₹{total_payment:,.0f} · Interest: ₹{total_interest:,.0f}</p>
            <p style="margin: 0; opacity: 0.8;">You pay ₹{total_interest / loan_amount * 100:.0f}% extra in interest</p>
            </div>""",
            unsafe_allow_html=True,
        )

        lm1, lm2, lm3, lm4 = st.columns(4)
        lm1.metric("Monthly EMI", f"₹{emi:,.0f}")
        lm2.metric("Total Interest", f"₹{total_interest:,.0f}")
        lm3.metric("Total Payment", f"₹{total_payment:,.0f}")
        lm4.metric("Interest/Principal", f"{total_interest / loan_amount * 100:.0f}%")

        # Portfolio context for EMI impact
        if total_sip_monthly > 0 or total_invested > 0:
            st.divider()
            st.markdown("##### 📋 Your Current Investment Context")
            ctx1, ctx2, ctx3 = st.columns(3)
            ctx1.metric("Monthly SIPs", f"₹{total_sip_monthly:,.0f}")
            ctx2.metric("Portfolio Value", f"₹{total_invested:,.0f}")
            emi_to_sip_pct = (
                (emi / total_sip_monthly * 100) if total_sip_monthly > 0 else 0
            )
            ctx3.metric(
                "EMI as % of SIPs",
                f"{emi_to_sip_pct:.0f}%" if total_sip_monthly > 0 else "—",
            )
            if total_sip_monthly > 0 and emi > total_sip_monthly:
                st.warning(
                    f"⚠️ This EMI (₹{emi:,.0f}) is **{emi_to_sip_pct:.0f}%** of your total SIP (₹{total_sip_monthly:,.0f}). "
                    f"Taking this loan may force you to stop or reduce existing SIPs."
                )
            elif total_sip_monthly > 0 and emi > total_sip_monthly * 0.5:
                st.info(
                    f"💡 This EMI would consume {emi_to_sip_pct:.0f}% of your monthly SIP budget. "
                    f"Ensure you can maintain essential SIPs alongside."
                )

        # Investment impact
        st.divider()
        st.markdown("##### 📉 Impact on Your Investments")
        st.caption("What if you invested the EMI amount instead?")

        invest_return = st.number_input(
            "If EMI was invested at (%)",
            min_value=4.0,
            max_value=20.0,
            value=12.0,
            step=0.5,
            key="loan_inv_ret",
        )
        opportunity_cost = _future_value_sip(emi, invest_return, loan_tenure)

        st.warning(
            f"💰 If you invested ₹{emi:,.0f}/month for {loan_tenure} years at {invest_return}% return, "
            f"you'd have **₹{opportunity_cost:,.0f}**. The opportunity cost of this loan is "
            f"₹{opportunity_cost - total_payment:,.0f}."
        )

        # Prepayment impact
        st.divider()
        st.markdown("##### 🚀 Prepayment Benefit")
        extra_emi = st.number_input(
            "Extra Payment per Month (₹)",
            min_value=0,
            step=1000,
            value=5000,
            key="loan_extra",
        )

        if extra_emi > 0:
            # Simulate with extra payment
            balance = loan_amount
            months_with_extra = 0
            total_interest_with_extra = 0
            while balance > 0 and months_with_extra < n_months:
                interest_this_month = balance * r_monthly
                total_interest_with_extra += interest_this_month
                principal_paid = emi + extra_emi - interest_this_month
                if principal_paid <= 0:
                    break
                balance = max(balance - principal_paid, 0)
                months_with_extra += 1

            years_saved = (n_months - months_with_extra) / 12
            interest_saved = total_interest - total_interest_with_extra

            st.success(
                f"✅ Paying ₹{extra_emi:,.0f} extra/month saves **₹{interest_saved:,.0f}** in interest "
                f"and closes the loan **{years_saved:.1f} years earlier**!"
            )
