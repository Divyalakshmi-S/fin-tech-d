"""F2/F3/F4/F5/F14: Financial calculators — Retirement, Step-up SIP, Emergency Fund, Education, EMI."""

import streamlit as st
import pandas as pd
import math
from datetime import datetime


def _future_value_sip(monthly, rate_annual, years):
    """Future value of SIP with monthly compounding."""
    r = rate_annual / 100 / 12
    n = years * 12
    if r <= 0:
        return monthly * n
    return monthly * (((1 + r) ** n - 1) / r) * (1 + r)


def _future_value_lumpsum(principal, rate_annual, years):
    """Future value of lumpsum."""
    return principal * ((1 + rate_annual / 100) ** years)


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
    st.caption("Plan your retirement, education, emergency fund, and more")

    calc_tabs = st.tabs(
        [
            "🏖️ Retirement/FIRE",
            "📈 Step-up SIP",
            "🆘 Emergency Fund",
            "🎓 Education Goal",
            "💳 Loan/EMI Impact",
        ]
    )

    # =====================================================================
    # F2: Retirement / FIRE Calculator
    # =====================================================================
    with calc_tabs[0]:
        st.subheader("🏖️ Retirement / FIRE Calculator")
        st.caption(
            "How much do you need to retire? When can you be financially independent?"
        )

        rc1, rc2, rc3 = st.columns(3)
        current_age = rc1.number_input(
            "Current Age", min_value=18, max_value=70, value=30, key="ret_age"
        )
        retirement_age = rc2.number_input(
            "Retirement Age",
            min_value=current_age + 1,
            max_value=80,
            value=60,
            key="ret_retire_age",
        )
        life_expectancy = rc3.number_input(
            "Life Expectancy",
            min_value=retirement_age + 1,
            max_value=100,
            value=85,
            key="ret_life",
        )

        rc4, rc5, rc6 = st.columns(3)
        monthly_expenses = rc4.number_input(
            "Monthly Expenses (₹)",
            min_value=5000,
            step=5000,
            value=50000,
            key="ret_exp",
        )
        inflation_rate = rc5.number_input(
            "Inflation Rate (%)",
            min_value=1.0,
            max_value=15.0,
            value=6.0,
            step=0.5,
            key="ret_inf",
        )
        post_ret_return = rc6.number_input(
            "Post-Retirement Return (%)",
            min_value=1.0,
            max_value=15.0,
            value=7.0,
            step=0.5,
            key="ret_post_ret",
        )

        rc7, rc8, rc9 = st.columns(3)
        current_savings = rc7.number_input(
            "Current Savings/Investments (₹)",
            min_value=0,
            step=100000,
            value=0,
            key="ret_savings",
        )
        pre_ret_return = rc8.number_input(
            "Pre-Retirement Return (%)",
            min_value=1.0,
            max_value=20.0,
            value=12.0,
            step=0.5,
            key="ret_pre_ret",
        )
        monthly_sip = rc9.number_input(
            "Current Monthly SIP (₹)",
            min_value=0,
            step=5000,
            value=20000,
            key="ret_sip",
        )

        years_to_retire = retirement_age - current_age
        years_in_retirement = life_expectancy - retirement_age

        # Future monthly expenses at retirement
        future_monthly_exp = _inflation_adjusted(
            monthly_expenses, inflation_rate, years_to_retire
        )
        future_annual_exp = future_monthly_exp * 12

        # Corpus needed using 4% rule adjusted for Indian inflation
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

        # Current trajectory
        future_savings = _future_value_lumpsum(
            current_savings, pre_ret_return, years_to_retire
        )
        future_sip_value = _future_value_sip(
            monthly_sip, pre_ret_return, years_to_retire
        )
        projected_corpus = future_savings + future_sip_value

        shortfall = max(corpus_needed - projected_corpus, 0)
        surplus = max(projected_corpus - corpus_needed, 0)

        st.divider()

        # Results
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
            extra_sip = _required_sip(shortfall, pre_ret_return, years_to_retire)
            st.warning(
                f"⚠️ You need an additional **₹{extra_sip:,.0f}/month** SIP to bridge the gap. "
                f"Total required: ₹{monthly_sip + extra_sip:,.0f}/month."
            )
        else:
            st.success(
                f"✅ You're on track for retirement! You can even retire "
                f"**{max(0, years_to_retire - int(surplus / future_annual_exp)):.0f} years earlier** if you maintain this pace."
            )

        # FIRE number
        st.divider()
        st.markdown("##### 🔥 FIRE Number (Financial Independence)")
        fire_number = monthly_expenses * 12 * 25  # 4% rule on today's expenses
        fire_inflation_adjusted = _inflation_adjusted(
            fire_number, inflation_rate, years_to_retire
        )
        st.metric("FIRE Corpus (25x annual expenses)", f"₹{fire_number:,.0f}")
        st.caption(
            f"Inflation-adjusted FIRE corpus at age {retirement_age}: ₹{fire_inflation_adjusted:,.0f}"
        )

        # Growth projection chart
        st.divider()
        st.markdown("##### 📊 Corpus Growth Projection")
        years_range = list(range(1, years_to_retire + 1))
        corpus_series = []
        for y in years_range:
            fv_save = _future_value_lumpsum(current_savings, pre_ret_return, y)
            fv_sip = _future_value_sip(monthly_sip, pre_ret_return, y)
            corpus_series.append(fv_save + fv_sip)

        chart_df = pd.DataFrame(
            {
                "Your Corpus": corpus_series,
                "Target Corpus": [corpus_needed] * len(years_range),
            },
            index=[f"Age {current_age + y}" for y in years_range],
        )

        # Show only every few years for cleaner chart
        step = max(1, len(years_range) // 15)
        st.line_chart(chart_df.iloc[::step], height=300)

    # =====================================================================
    # F3: Step-up SIP Calculator
    # =====================================================================
    with calc_tabs[1]:
        st.subheader("📈 Step-up SIP Calculator")
        st.caption("See how increasing your SIP annually creates massive wealth")

        su1, su2, su3 = st.columns(3)
        base_sip = su1.number_input(
            "Starting Monthly SIP (₹)",
            min_value=500,
            step=1000,
            value=10000,
            key="su_sip",
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

    # =====================================================================
    # F4: Emergency Fund Advisor
    # =====================================================================
    with calc_tabs[2]:
        st.subheader("🆘 Emergency Fund Advisor")
        st.caption("Calculate your emergency fund requirement and track progress")

        ef1, ef2 = st.columns(2)
        ef_monthly_expenses = ef1.number_input(
            "Monthly Expenses (₹)", min_value=5000, step=5000, value=40000, key="ef_exp"
        )
        ef_months = ef2.number_input(
            "Emergency Fund (months)",
            min_value=3,
            max_value=12,
            value=6,
            key="ef_months",
            help="6 months is recommended, 9-12 if single income",
        )

        ef_target = ef_monthly_expenses * ef_months

        st.divider()

        ef3, ef4 = st.columns(2)
        ef_current_liquid = ef3.number_input(
            "Current Liquid Savings (₹)",
            min_value=0,
            step=10000,
            value=0,
            key="ef_liquid",
            help="Bank balance + liquid fund + FD that can be broken",
        )
        ef_monthly_save = ef4.number_input(
            "Monthly Savings Towards EF (₹)",
            min_value=0,
            step=2000,
            value=5000,
            key="ef_save",
        )

        ef_gap = max(ef_target - ef_current_liquid, 0)
        ef_progress = (
            min((ef_current_liquid / ef_target) * 100, 100) if ef_target > 0 else 0
        )
        ef_months_to_fill = (
            math.ceil(ef_gap / ef_monthly_save) if ef_monthly_save > 0 else float("inf")
        )

        ef_color = (
            "#27ae60"
            if ef_progress >= 100
            else "#f39c12" if ef_progress >= 50 else "#e74c3c"
        )

        st.markdown(
            f"""<div style="background: linear-gradient(135deg, {ef_color}22, {ef_color}11);
            border-left: 5px solid {ef_color}; border-radius: 10px; padding: 20px; margin: 10px 0;">
            <h3 style="margin:0; color: {ef_color};">🆘 Emergency Fund: {ef_progress:.0f}% funded</h3>
            <p style="margin: 8px 0;">Target: ₹{ef_target:,.0f} ({ef_months} months × ₹{ef_monthly_expenses:,.0f})</p>
            <p style="margin: 0;">Current: ₹{ef_current_liquid:,.0f} · Gap: ₹{ef_gap:,.0f}</p>
            </div>""",
            unsafe_allow_html=True,
        )

        # Progress bar
        st.markdown(
            f"""<div style="background: #eee; border-radius: 8px; height: 20px; margin: 10px 0;">
            <div style="background: {ef_color}; width: {ef_progress}%; height: 20px; border-radius: 8px;
            text-align: center; color: white; font-size: 0.8em; line-height: 20px;">{ef_progress:.0f}%</div>
            </div>""",
            unsafe_allow_html=True,
        )

        if ef_gap > 0 and ef_monthly_save > 0:
            st.info(
                f"⏰ At ₹{ef_monthly_save:,.0f}/month, your emergency fund will be full in **{ef_months_to_fill} months**."
            )
        elif ef_gap > 0:
            st.warning("⚠️ Set aside a monthly amount to build your emergency fund.")
        else:
            st.success("✅ Emergency fund fully funded! Great job!")

        st.divider()
        st.markdown("##### 💡 Where to park your Emergency Fund")
        st.markdown(
            """
| Option | Returns | Liquidity | Best For |
|---|---|---|---|
| **Savings Account** | 3-4% | Instant | 1 month expenses |
| **Liquid Mutual Fund** | 5-7% | T+1 | 2-3 months expenses |
| **Short-term FD** | 6-7% | 1-2 days | Remaining amount |
| **Sweep-in FD** | 6-7% | Instant | All-in-one option |
"""
        )

    # =====================================================================
    # F5: Children's Education Goal
    # =====================================================================
    with calc_tabs[3]:
        st.subheader("🎓 Children's Education Goal Planner")
        st.caption("Plan for education costs with education-specific inflation")

        ed1, ed2, ed3 = st.columns(3)
        child_age = ed1.number_input(
            "Child's Current Age", min_value=0, max_value=17, value=5, key="ed_age"
        )
        target_age = ed2.number_input(
            "Education Start Age",
            min_value=child_age + 1,
            max_value=25,
            value=18,
            key="ed_target_age",
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
            key="ed_type",
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
                key="ed_custom",
            )

        ed_inflation = st.number_input(
            "Education Inflation (%)",
            min_value=3.0,
            max_value=15.0,
            value=8.0,
            step=0.5,
            key="ed_inf",
            help="Education costs typically inflate at 8-10% in India",
        )
        ed_return = st.number_input(
            "Expected Investment Return (%)",
            min_value=4.0,
            max_value=20.0,
            value=12.0,
            step=0.5,
            key="ed_ret",
        )

        years_to_goal = target_age - child_age
        future_cost = _inflation_adjusted(today_cost, ed_inflation, years_to_goal)
        monthly_sip_needed = _required_sip(future_cost, ed_return, years_to_goal)

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
        years_list = list(range(1, years_to_goal + 1))
        sip_growth = [
            _future_value_sip(monthly_sip_needed, ed_return, y) for y in years_list
        ]
        cost_growth = [
            _inflation_adjusted(today_cost, ed_inflation, y) for y in years_list
        ]

        chart_df = pd.DataFrame(
            {
                "Your Investment": sip_growth,
                "Education Cost": cost_growth,
            },
            index=[f"Year {y}" for y in years_list],
        )
        st.line_chart(chart_df, height=300)

        st.info(
            f"💡 Start with ₹{monthly_sip_needed:,.0f}/mo SIP in equity mutual funds for {years_to_goal} years. "
            f"Switch to debt funds 2-3 years before the goal when {years_to_goal - 3} years remain."
        )

    # =====================================================================
    # F14: Loan/EMI Impact Calculator
    # =====================================================================
    with calc_tabs[4]:
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
