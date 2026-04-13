import streamlit as st
import pandas as pd
import json
import os

BUDGET_PATH = "data/budget.json"


def _load_budget():
    try:
        with open(BUDGET_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"income": 0, "expenses": 0, "investments": 0}


def _save_budget(data):
    os.makedirs(os.path.dirname(BUDGET_PATH), exist_ok=True)
    tmp_path = BUDGET_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, BUDGET_PATH)


def render(holdings):
    st.title("💰 Monthly Budget Tracker")
    st.caption("Enter your numbers below — they are saved automatically")

    budget = _load_budget()

    col_x, col_y, col_z = st.columns(3)
    income = col_x.number_input(
        "Monthly Income (₹)",
        value=budget["income"],
        step=1000,
        key="budget_income_input",
        min_value=0,
    )
    expenses = col_y.number_input(
        "Monthly Expenses (₹)",
        value=budget["expenses"],
        step=1000,
        key="budget_expenses_input",
        min_value=0,
    )
    investments = col_z.number_input(
        "Monthly Investments (₹)",
        value=budget["investments"],
        step=1000,
        key="budget_investments_input",
        min_value=0,
    )

    # Save to file
    _save_budget({"income": income, "expenses": expenses, "investments": investments})

    if income == 0:
        st.info(
            "👆 Enter your monthly income, expenses, and investments above to see your budget breakdown."
        )
    else:
        remaining = income - expenses - investments
        savings_rate = round((investments / income) * 100, 1) if income > 0 else 0

        st.divider()

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Remaining", f"₹{remaining:,.0f}")
        r2.metric("Savings Rate", f"{savings_rate}%")
        r3.metric(
            "Expense Ratio",
            f"{round((expenses / income) * 100, 1)}%" if income > 0 else "0%",
        )
        r4.metric(
            "Investment Ratio",
            f"{round((investments / income) * 100, 1)}%" if income > 0 else "0%",
        )

        if remaining > 20000:
            st.warning(f"⚠️ ₹{remaining:,.0f} unused — consider investing more!")
        elif remaining < 0:
            st.error(f"🚨 Overspending by ₹{abs(remaining):,.0f}!")
        else:
            st.success("✅ Budget looks healthy!")

        st.divider()

        # Visual breakdown
        st.subheader("📊 Breakdown")
        breakdown = {
            "Expenses": expenses,
            "Investments": investments,
            "Remaining": max(remaining, 0),
        }
        st.bar_chart(pd.Series(breakdown, name="₹"), height=300)
