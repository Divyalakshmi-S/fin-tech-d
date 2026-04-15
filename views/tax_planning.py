"""F6: Tax Planning Dashboard — 80C tracker, regime comparison, tax optimization."""

import streamlit as st
import pandas as pd

import db
import auth


def _load_tax_data(user_id):
    """Load tax planning data."""
    data = db.load_tax_planning(user_id)
    if not data:
        data = {
            "gross_income": 0,
            "hra_received": 0,
            "rent_paid": 0,
            "metro_city": True,
            "section_80c_elss": 0,
            "section_80c_ppf": 0,
            "section_80c_epf": 0,
            "section_80c_lic": 0,
            "section_80c_tuition": 0,
            "section_80c_nsc": 0,
            "section_80c_home_loan_principal": 0,
            "section_80d_self": 0,
            "section_80d_parents": 0,
            "section_80ccd_nps": 0,
            "home_loan_interest": 0,
            "other_deductions": 0,
        }
    return data


def _calc_old_regime_tax(taxable_income):
    """Calculate tax under old regime (FY 2025-26)."""
    tax = 0
    if taxable_income <= 250000:
        tax = 0
    elif taxable_income <= 500000:
        tax = (taxable_income - 250000) * 0.05
    elif taxable_income <= 1000000:
        tax = 12500 + (taxable_income - 500000) * 0.20
    else:
        tax = 112500 + (taxable_income - 1000000) * 0.30
    # Cess
    tax = tax * 1.04
    return round(tax)


def _calc_new_regime_tax(gross_income):
    """Calculate tax under new regime (FY 2025-26). Standard deduction of 75000."""
    taxable = max(gross_income - 75000, 0)
    tax = 0
    slabs = [
        (400000, 0),
        (400000, 0.05),
        (400000, 0.10),
        (400000, 0.15),
        (400000, 0.20),
        (float("inf"), 0.30),
    ]
    remaining = taxable
    for slab_amount, rate in slabs:
        if remaining <= 0:
            break
        taxable_in_slab = min(remaining, slab_amount)
        tax += taxable_in_slab * rate
        remaining -= taxable_in_slab

    # Section 87A rebate for income up to 12 lakh (new regime)
    if taxable <= 1200000:
        tax = 0

    tax = tax * 1.04  # Cess
    return round(tax)


def render(holdings):
    st.title("📋 Tax Planning Dashboard")
    st.caption("Optimize your taxes — compare old vs new regime, track 80C investments")

    user_id = auth.get_user_id()
    tax_data = _load_tax_data(user_id)

    tax_tab1, tax_tab2, tax_tab3 = st.tabs(
        [
            "📊 Tax Calculator",
            "🏷️ 80C Tracker",
            "💡 Tax Saving Tips",
        ]
    )

    with tax_tab1:
        st.subheader("📊 Old vs New Regime Comparison")

        with st.form("tax_form"):
            gross_income = st.number_input(
                "Gross Annual Income (₹)",
                min_value=0,
                step=100000,
                value=tax_data.get("gross_income", 0),
                key="tax_gross",
            )

            st.markdown("##### 🏠 HRA Details")
            h1, h2, h3 = st.columns(3)
            hra_received = h1.number_input(
                "HRA Received (₹/year)",
                min_value=0,
                step=10000,
                value=tax_data.get("hra_received", 0),
                key="tax_hra",
            )
            rent_paid = h2.number_input(
                "Rent Paid (₹/year)",
                min_value=0,
                step=10000,
                value=tax_data.get("rent_paid", 0),
                key="tax_rent",
            )
            metro_city = h3.checkbox(
                "Metro City?", value=tax_data.get("metro_city", True), key="tax_metro"
            )

            st.markdown("##### 📋 Section 80C Deductions (Max ₹1,50,000)")
            c1, c2, c3, c4 = st.columns(4)
            sec80c_elss = c1.number_input(
                "ELSS (₹)",
                min_value=0,
                step=10000,
                value=tax_data.get("section_80c_elss", 0),
                key="tax_elss",
            )
            sec80c_ppf = c2.number_input(
                "PPF (₹)",
                min_value=0,
                step=10000,
                value=tax_data.get("section_80c_ppf", 0),
                key="tax_ppf",
            )
            sec80c_epf = c3.number_input(
                "EPF (₹)",
                min_value=0,
                step=10000,
                value=tax_data.get("section_80c_epf", 0),
                key="tax_epf",
            )
            sec80c_lic = c4.number_input(
                "LIC/Insurance (₹)",
                min_value=0,
                step=5000,
                value=tax_data.get("section_80c_lic", 0),
                key="tax_lic",
            )

            c5, c6, c7 = st.columns(3)
            sec80c_tuition = c5.number_input(
                "Children Tuition (₹)",
                min_value=0,
                step=10000,
                value=tax_data.get("section_80c_tuition", 0),
                key="tax_tuition",
            )
            sec80c_nsc = c6.number_input(
                "NSC/Tax-saving FD (₹)",
                min_value=0,
                step=10000,
                value=tax_data.get("section_80c_nsc", 0),
                key="tax_nsc",
            )
            sec80c_hlp = c7.number_input(
                "Home Loan Principal (₹)",
                min_value=0,
                step=10000,
                value=tax_data.get("section_80c_home_loan_principal", 0),
                key="tax_hlp",
            )

            st.markdown("##### 🏥 Other Deductions")
            d1, d2, d3 = st.columns(3)
            sec80d_self = d1.number_input(
                "80D Health Insurance - Self (₹)",
                min_value=0,
                step=5000,
                value=tax_data.get("section_80d_self", 0),
                key="tax_80d_self",
            )
            sec80d_parents = d2.number_input(
                "80D Health Insurance - Parents (₹)",
                min_value=0,
                step=5000,
                value=tax_data.get("section_80d_parents", 0),
                key="tax_80d_par",
            )
            sec80ccd_nps = d3.number_input(
                "80CCD(1B) NPS (₹, max 50K)",
                min_value=0,
                max_value=50000,
                step=5000,
                value=tax_data.get("section_80ccd_nps", 0),
                key="tax_nps",
            )

            h1_2, h2_2 = st.columns(2)
            home_loan_interest = h1_2.number_input(
                "Home Loan Interest (₹, 24b max 2L)",
                min_value=0,
                step=10000,
                value=tax_data.get("home_loan_interest", 0),
                key="tax_hli",
            )
            other_deductions = h2_2.number_input(
                "Other Deductions (₹)",
                min_value=0,
                step=10000,
                value=tax_data.get("other_deductions", 0),
                key="tax_other",
            )

            if st.form_submit_button("💾 Save & Calculate"):
                save_data = {
                    "gross_income": gross_income,
                    "hra_received": hra_received,
                    "rent_paid": rent_paid,
                    "metro_city": metro_city,
                    "section_80c_elss": sec80c_elss,
                    "section_80c_ppf": sec80c_ppf,
                    "section_80c_epf": sec80c_epf,
                    "section_80c_lic": sec80c_lic,
                    "section_80c_tuition": sec80c_tuition,
                    "section_80c_nsc": sec80c_nsc,
                    "section_80c_home_loan_principal": sec80c_hlp,
                    "section_80d_self": sec80d_self,
                    "section_80d_parents": sec80d_parents,
                    "section_80ccd_nps": sec80ccd_nps,
                    "home_loan_interest": home_loan_interest,
                    "other_deductions": other_deductions,
                }
                db.save_tax_planning(save_data, user_id)
                st.success("✅ Tax data saved!")

        if gross_income > 0:
            # Old regime calculations
            total_80c = min(
                sec80c_elss
                + sec80c_ppf
                + sec80c_epf
                + sec80c_lic
                + sec80c_tuition
                + sec80c_nsc
                + sec80c_hlp,
                150000,
            )

            # HRA exemption
            hra_exemption = 0
            if hra_received > 0 and rent_paid > 0:
                basic = gross_income * 0.4  # approximate
                hra_1 = hra_received
                hra_2 = rent_paid - 0.1 * basic
                hra_3 = (0.5 if metro_city else 0.4) * basic
                hra_exemption = max(min(hra_1, hra_2, hra_3), 0)

            total_deductions_old = (
                50000  # standard deduction
                + total_80c
                + min(sec80d_self, 25000)
                + min(sec80d_parents, 50000)
                + sec80ccd_nps
                + min(home_loan_interest, 200000)
                + hra_exemption
                + other_deductions
            )
            taxable_old = max(gross_income - total_deductions_old, 0)
            tax_old = _calc_old_regime_tax(taxable_old)

            # New regime
            tax_new = _calc_new_regime_tax(gross_income)

            st.divider()
            st.subheader("📊 Tax Comparison")

            better_regime = "New Regime" if tax_new <= tax_old else "Old Regime"
            savings = abs(tax_old - tax_new)
            better_color = "#27ae60"

            st.markdown(
                f"""<div style="background: linear-gradient(135deg, {better_color}22, {better_color}11);
                border-left: 5px solid {better_color}; border-radius: 10px; padding: 20px; margin: 10px 0;">
                <h3 style="margin:0; color: {better_color};">✅ {better_regime} saves you ₹{savings:,.0f}</h3>
                </div>""",
                unsafe_allow_html=True,
            )

            t1, t2, t3 = st.columns(3)
            t1.metric("Old Regime Tax", f"₹{tax_old:,.0f}")
            t2.metric("New Regime Tax", f"₹{tax_new:,.0f}")
            t3.metric("You Save", f"₹{savings:,.0f}", f"with {better_regime}")

            # Detailed breakdown
            with st.expander("📋 Old Regime Breakdown"):
                rows = [
                    {"Item": "Gross Income", "Amount": f"₹{gross_income:,.0f}"},
                    {"Item": "Standard Deduction", "Amount": f"- ₹50,000"},
                    {"Item": "Section 80C", "Amount": f"- ₹{total_80c:,.0f}"},
                    {"Item": "HRA Exemption", "Amount": f"- ₹{hra_exemption:,.0f}"},
                    {
                        "Item": "80D (Health)",
                        "Amount": f"- ₹{min(sec80d_self, 25000) + min(sec80d_parents, 50000):,.0f}",
                    },
                    {"Item": "80CCD NPS", "Amount": f"- ₹{sec80ccd_nps:,.0f}"},
                    {
                        "Item": "Home Loan Interest",
                        "Amount": f"- ₹{min(home_loan_interest, 200000):,.0f}",
                    },
                    {"Item": "Taxable Income", "Amount": f"₹{taxable_old:,.0f}"},
                    {"Item": "Tax Payable", "Amount": f"₹{tax_old:,.0f}"},
                ]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    with tax_tab2:
        st.subheader("🏷️ Section 80C Utilization")

        total_80c_invested = (
            sec80c_elss
            + sec80c_ppf
            + sec80c_epf
            + sec80c_lic
            + sec80c_tuition
            + sec80c_nsc
            + sec80c_hlp
        )
        limit = 150000
        utilized_pct = min((total_80c_invested / limit) * 100, 100) if limit > 0 else 0
        remaining = max(limit - total_80c_invested, 0)

        bar_color = (
            "#27ae60"
            if utilized_pct >= 100
            else "#f39c12" if utilized_pct >= 50 else "#e74c3c"
        )

        st.markdown(
            f"""<div style="margin: 10px 0;">
            <strong>₹{total_80c_invested:,.0f} / ₹{limit:,.0f} utilized ({utilized_pct:.0f}%)</strong>
            <div style="background: #eee; border-radius: 8px; height: 20px; margin: 6px 0;">
            <div style="background: {bar_color}; width: {utilized_pct}%; height: 20px; border-radius: 8px;
            text-align: center; color: white; font-size: 0.8em; line-height: 20px;">{utilized_pct:.0f}%</div>
            </div>
            </div>""",
            unsafe_allow_html=True,
        )

        if remaining > 0:
            st.warning(
                f"⚠️ ₹{remaining:,.0f} of 80C limit unused! Invest in ELSS or PPF before March 31."
            )
        else:
            st.success("✅ Section 80C limit fully utilized!")

        # Breakdown
        breakdown = {
            "ELSS": sec80c_elss,
            "PPF": sec80c_ppf,
            "EPF": sec80c_epf,
            "LIC/Insurance": sec80c_lic,
            "Tuition Fees": sec80c_tuition,
            "NSC/Tax FD": sec80c_nsc,
            "Home Loan Principal": sec80c_hlp,
        }
        breakdown = {k: v for k, v in breakdown.items() if v > 0}
        if breakdown:
            st.bar_chart(pd.Series(breakdown, name="₹"), height=250)

    with tax_tab3:
        st.subheader("💡 Tax Saving Tips")
        st.markdown(
            """
#### For Old Regime
1. **Max out 80C (₹1.5L)** — ELSS gives best returns (equity + tax saving)
2. **80CCD(1B) NPS (₹50K extra)** — Above and beyond 80C limit
3. **80D Health Insurance** — ₹25K self + ₹50K parents (if senior citizen)
4. **Home Loan Interest (24b)** — Up to ₹2L deduction on interest paid
5. **HRA Exemption** — Submit rent receipts if living on rent

#### For New Regime
1. Only **₹75,000 standard deduction** available
2. No 80C, 80D, HRA deductions
3. **Better for:** High income + few investments + no home loan
4. **Section 87A rebate** for income up to ₹12L — zero tax!

#### General Tips
- **ELSS vs PPF**: ELSS has 3-year lock-in, PPF has 15 years. ELSS gives ~12% returns, PPF ~7.1%
- **NPS extra ₹50K**: Often overlooked — gives additional deduction above 80C
- **Health insurance**: Not just tax saving — essential financial protection
- **Harvest LTCG**: Sell and rebuy equity investments to reset cost basis (₹1.25L LTCG exempt)
"""
        )
