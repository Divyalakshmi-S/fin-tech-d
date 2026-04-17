import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

import db
import auth


def _budget_path():
    """Return user-scoped budget JSON path."""
    return db._json_path("budget.json", user_id=auth.get_user_id())


def _load_budget():
    user_id = auth.get_user_id()
    if db.is_db_available() and user_id:
        return db.load_budget(user_id)
    path = _budget_path()
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "income": 0,
            "expenses": 0,
            "investments": 0,
            "expense_categories": {},
        }


def _save_budget(data):
    user_id = auth.get_user_id()
    if db.is_db_available() and user_id:
        db.save_budget(data, user_id)
        return
    path = _budget_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)


def _monthly_equivalent(amount, frequency):
    """Convert an amount to its monthly equivalent based on frequency."""
    freq_map = {
        "Monthly": 1,
        "Quarterly": 3,
        "Half-Yearly": 6,
        "Yearly": 12,
    }
    divisor = freq_map.get(frequency, 1)
    return round(amount / divisor, 2) if divisor else amount


def _compute_totals(items):
    """Compute expense, investment, debt, insurance totals from budget items."""
    totals = {"expense": 0, "investment": 0, "debt": 0, "insurance": 0}
    for item in items:
        t = item.get("type", "expense")
        freq = item.get("frequency", "Monthly")
        amt = item.get("amount", 0)
        if freq not in ("One-Time", "As Needed"):
            totals[t] = totals.get(t, 0) + _monthly_equivalent(amt, freq)
    return totals


def render(holdings):
    st.title("💰 Monthly Budget Tracker")
    st.caption("Enter your numbers below — they are saved automatically")

    budget = _load_budget()

    budget_tab1, budget_tab2, budget_tab3 = st.tabs(
        ["📊 Overview", "📝 My Budget Plan", "💡 Budget Rules"]
    )

    items = budget.get("budget_items", [])
    item_totals = _compute_totals(items) if items else None

    with budget_tab1:
        col_x, col_y, col_z = st.columns(3)
        income = col_x.number_input(
            "Monthly Income (₹)",
            value=budget.get("income", 0),
            step=1000,
            key="budget_income_input",
            min_value=0,
        )

        # Auto-calculate from budget items if available
        if item_totals:
            auto_expenses = round(item_totals["expense"] + item_totals["debt"])
            auto_investments = round(item_totals["investment"])
            auto_insurance = round(item_totals["insurance"])
            expenses = col_y.number_input(
                "Monthly Expenses (₹)",
                value=auto_expenses,
                step=1000,
                key="budget_expenses_input",
                min_value=0,
                help="Auto-calculated from Budget Plan items",
            )
            investments = col_z.number_input(
                "Monthly Investments (₹)",
                value=auto_investments,
                step=1000,
                key="budget_investments_input",
                min_value=0,
                help="Auto-calculated from Budget Plan items",
            )
            if auto_insurance > 0:
                st.caption(
                    f"🛡️ Insurance (monthly equiv.): ₹{auto_insurance:,.0f}/month"
                )
        else:
            expenses = col_y.number_input(
                "Monthly Expenses (₹)",
                value=budget.get("expenses", 0),
                step=1000,
                key="budget_expenses_input",
                min_value=0,
            )
            investments = col_z.number_input(
                "Monthly Investments (₹)",
                value=budget.get("investments", 0),
                step=1000,
                key="budget_investments_input",
                min_value=0,
            )

        # Save only on explicit action
        if st.button("💾 Save Budget", key="save_budget_overview"):
            save_data = {
                "income": income,
                "expenses": expenses,
                "investments": investments,
                "expense_categories": budget.get("expense_categories", {}),
                "budget_items": budget.get("budget_items", []),
            }
            _save_budget(save_data)
            st.success("✅ Budget saved!")
            st.rerun()

        if income == 0:
            st.info(
                "👆 Enter your monthly income, expenses, and investments above to see your budget breakdown."
            )
        else:
            insurance_mo = round(item_totals["insurance"]) if item_totals else 0
            debt_mo = round(item_totals["debt"]) if item_totals else 0
            total_outflow = expenses + investments + insurance_mo
            remaining = income - total_outflow
            savings_rate = round((investments / income) * 100, 1) if income > 0 else 0

            st.divider()

            if item_totals:
                r1, r2, r3, r4, r5 = st.columns(5)
                r1.metric("Remaining", f"₹{remaining:,.0f}")
                r2.metric("Savings Rate", f"{savings_rate}%")
                r3.metric(
                    "Expense Ratio",
                    f"{round((expenses / income) * 100, 1)}%" if income > 0 else "0%",
                )
                r4.metric(
                    "Investment Ratio",
                    (
                        f"{round((investments / income) * 100, 1)}%"
                        if income > 0
                        else "0%"
                    ),
                )
                r5.metric(
                    "Insurance",
                    f"₹{insurance_mo:,.0f}/mo",
                )
            else:
                remaining = income - expenses - investments
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Remaining", f"₹{remaining:,.0f}")
                r2.metric("Savings Rate", f"{savings_rate}%")
                r3.metric(
                    "Expense Ratio",
                    f"{round((expenses / income) * 100, 1)}%" if income > 0 else "0%",
                )
                r4.metric(
                    "Investment Ratio",
                    (
                        f"{round((investments / income) * 100, 1)}%"
                        if income > 0
                        else "0%"
                    ),
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
            if item_totals:
                breakdown = {
                    "Living Expenses": round(item_totals["expense"]),
                    "Debt / EMI": debt_mo,
                    "Investments": investments,
                    "Insurance": insurance_mo,
                    "Remaining": max(remaining, 0),
                }
            else:
                breakdown = {
                    "Expenses": expenses,
                    "Investments": investments,
                    "Remaining": max(remaining, 0),
                }
            st.bar_chart(pd.Series(breakdown, name="₹"), height=300)

            # Annual projection
            st.divider()
            st.subheader("📅 Annual Projection")
            if item_totals:
                ap1, ap2, ap3, ap4, ap5 = st.columns(5)
                ap1.metric("Annual Income", f"₹{income * 12:,.0f}")
                ap2.metric("Annual Expenses", f"₹{expenses * 12:,.0f}")
                ap3.metric("Annual Investment", f"₹{investments * 12:,.0f}")
                ap4.metric("Annual Insurance", f"₹{insurance_mo * 12:,.0f}")
                ap5.metric("Annual Remaining", f"₹{max(remaining, 0) * 12:,.0f}")
            else:
                ap1, ap2, ap3, ap4 = st.columns(4)
                ap1.metric("Annual Income", f"₹{income * 12:,.0f}")
                ap2.metric("Annual Expenses", f"₹{expenses * 12:,.0f}")
                ap3.metric("Annual Investment", f"₹{investments * 12:,.0f}")
                ap4.metric("Annual Savings", f"₹{max(remaining, 0) * 12:,.0f}")

    with budget_tab2:
        st.subheader("📝 My Budget Plan")
        st.caption(
            "Add custom expense, investment, debt, and insurance items to your budget"
        )

        # --- Add New Item ---
        # Predefined categories by type
        _SUGGESTED_CATS = {
            "Expense": [
                "Rental House",
                "Living Expenses",
                "Groceries",
                "Utilities",
                "Transport",
                "Family Support",
                "Household Help",
                "Child",
                "Education",
                "Healthcare",
                "Travel",
                "Dining Out",
                "Shopping",
                "Entertainment",
                "Subscriptions",
                "Donations",
                "Others",
            ],
            "Investment": [
                "Mutual Funds",
                "Stocks",
                "Gold",
                "Silver",
                "Savings",
                "Fixed Deposit",
                "Chit Fund",
                "PPF",
                "NPS",
                "Real Estate",
                "Crypto",
                "Child Education Fund",
                "Others",
            ],
            "Debt": [
                "Home Loan",
                "Car Loan",
                "Personal Loan",
                "Credit Card",
                "Education Loan",
                "Two-Wheeler Loan",
                "Others",
            ],
            "Insurance": [
                "Life Insurance",
                "Health Insurance",
                "Vehicle Insurance",
                "Home Insurance",
                "Child Plan",
                "Others",
            ],
        }

        with st.expander("➕ Add Budget Item", expanded=not items):
            c1, c2 = st.columns(2)
            with c1:
                item_type = st.selectbox(
                    "Type",
                    ["Expense", "Investment", "Debt", "Insurance"],
                    key="bi_type",
                )

                # Merge suggested + existing user categories
                suggested = _SUGGESTED_CATS.get(item_type, [])
                existing_cats = sorted(
                    set(i.get("category", "") for i in items if i.get("category"))
                )
                all_cats = list(dict.fromkeys(suggested + existing_cats))
                cat_options = all_cats + ["+ New Category"]

                cat_choice = st.selectbox("Category", cat_options, key="bi_cat")

                if cat_choice == "+ New Category":
                    category = st.text_input("Category Name", key="bi_new_cat")
                else:
                    category = cat_choice

                item_name = st.text_input("Item Name", key="bi_name")
                item_amount = st.number_input(
                    "Amount (₹)",
                    min_value=0,
                    step=500,
                    key="bi_amount",
                )
            with c2:
                item_freq = st.selectbox(
                    "Frequency",
                    [
                        "Monthly",
                        "Quarterly",
                        "Half-Yearly",
                        "Yearly",
                        "One-Time",
                        "As Needed",
                    ],
                    key="bi_freq",
                )
                item_due = st.text_input(
                    "Due Date / Schedule",
                    key="bi_due",
                    placeholder="e.g. 2nd of Every Month",
                )
                item_paid_by = st.text_input(
                    "Paid By", key="bi_paid_by", placeholder="e.g. Divya"
                )
                item_priority = st.selectbox(
                    "Priority", ["High", "Medium", "Low", "TBD"], key="bi_priority"
                )
                item_notes = st.text_area("Notes", key="bi_notes", height=80)

            if st.button("➕ Add Item", key="bi_add"):
                if item_name and item_amount >= 0:
                    if not category:
                        category = "Others"
                    new_item = {
                        "id": max((i.get("id", 0) for i in items), default=0) + 1,
                        "type": item_type.lower(),
                        "category": category,
                        "name": item_name,
                        "amount": item_amount,
                        "frequency": item_freq,
                        "due_date": item_due,
                        "paid_by": item_paid_by,
                        "priority": item_priority,
                        "notes": item_notes,
                    }
                    items.append(new_item)

                    totals = _compute_totals(items)
                    save_data = {
                        "income": budget.get("income", 0),
                        "expenses": round(totals["expense"] + totals["debt"]),
                        "investments": round(totals["investment"]),
                        "expense_categories": budget.get("expense_categories", {}),
                        "budget_items": items,
                    }
                    _save_budget(save_data)
                    st.success(f"Added: {item_name}")
                    st.rerun()
                else:
                    st.warning("Please enter an item name and amount")

        # --- Display Items by Type ---
        if items:
            # --- Filters ---
            st.divider()
            fc1, fc2, fc3 = st.columns(3)
            all_paid_by = sorted(
                set(
                    i.get("paid_by", "").strip()
                    for i in items
                    if i.get("paid_by", "").strip()
                )
            )
            paid_by_filter = fc1.selectbox(
                "👤 Filter by Paid By",
                ["All"] + all_paid_by,
                key="bi_filter_paid_by",
            )
            all_priorities = sorted(
                set(i.get("priority", "") for i in items if i.get("priority"))
            )
            priority_filter = fc2.selectbox(
                "🔥 Filter by Priority",
                ["All"] + all_priorities,
                key="bi_filter_priority",
            )
            all_types = sorted(set(i.get("type", "") for i in items))
            type_filter = fc3.selectbox(
                "📂 Filter by Type",
                ["All"] + [t.capitalize() for t in all_types],
                key="bi_filter_type",
            )

            filtered = items
            if paid_by_filter != "All":
                filtered = [
                    i for i in filtered if paid_by_filter in i.get("paid_by", "")
                ]
            if priority_filter != "All":
                filtered = [i for i in filtered if i.get("priority") == priority_filter]
            if type_filter != "All":
                filtered = [i for i in filtered if i.get("type") == type_filter.lower()]

            type_sections = [
                ("💸 Expenses", "expense"),
                ("📊 Investments", "investment"),
                ("💳 Debt / EMI", "debt"),
                ("🛡️ Insurance", "insurance"),
            ]
            for type_label, type_key in type_sections:
                type_items = [i for i in filtered if i.get("type") == type_key]
                if not type_items:
                    continue
                st.markdown(f"##### {type_label}")

                rows = []
                for item in type_items:
                    monthly = _monthly_equivalent(
                        item.get("amount", 0), item.get("frequency", "Monthly")
                    )
                    rows.append(
                        {
                            "Category": item.get("category", ""),
                            "Name": item.get("name", ""),
                            "Amount (₹)": f"{item.get('amount', 0):,}",
                            "Frequency": item.get("frequency", "Monthly"),
                            "Monthly (₹)": f"{monthly:,.0f}",
                            "Due": item.get("due_date", ""),
                            "Paid By": item.get("paid_by", ""),
                            "Priority": item.get("priority", ""),
                            "Notes": item.get("notes", ""),
                        }
                    )

                df = pd.DataFrame(rows)
                st.dataframe(df, hide_index=True, use_container_width=True)

                total = sum(
                    _monthly_equivalent(
                        i.get("amount", 0), i.get("frequency", "Monthly")
                    )
                    for i in type_items
                    if i.get("frequency") not in ("One-Time", "As Needed")
                )
                st.caption(f"**Monthly subtotal: ₹{total:,.0f}**")

            # --- Remove Item ---
            st.divider()
            with st.expander("🗑️ Remove Item"):
                item_labels = {
                    f"{i.get('category', '')} → {i.get('name', '')} (₹{i.get('amount', 0):,})": i.get(
                        "id"
                    )
                    for i in items
                }
                to_delete = st.selectbox(
                    "Select item to remove",
                    list(item_labels.keys()),
                    key="bi_delete_sel",
                )
                if st.button("🗑️ Remove", key="bi_remove_btn"):
                    del_id = item_labels[to_delete]
                    items = [i for i in items if i.get("id") != del_id]

                    totals = _compute_totals(items)
                    save_data = {
                        "income": budget.get("income", 0),
                        "expenses": round(totals["expense"] + totals["debt"]),
                        "investments": round(totals["investment"]),
                        "expense_categories": budget.get("expense_categories", {}),
                        "budget_items": items,
                    }
                    _save_budget(save_data)
                    st.success("Item removed!")
                    st.rerun()

            # --- Edit Item ---
            with st.expander("✏️ Edit Item"):
                edit_labels = {
                    f"{i.get('category', '')} → {i.get('name', '')} (₹{i.get('amount', 0):,})": idx
                    for idx, i in enumerate(items)
                }
                to_edit_label = st.selectbox(
                    "Select item to edit",
                    list(edit_labels.keys()),
                    key="bi_edit_sel",
                )
                if edit_labels:
                    edit_idx = edit_labels[to_edit_label]
                    edit_item = items[edit_idx]
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        edit_name = st.text_input(
                            "Name", value=edit_item.get("name", ""), key="bi_edit_name"
                        )
                        edit_amount = st.number_input(
                            "Amount (₹)",
                            min_value=0,
                            value=edit_item.get("amount", 0),
                            step=500,
                            key="bi_edit_amount",
                        )
                        edit_category = st.text_input(
                            "Category",
                            value=edit_item.get("category", ""),
                            key="bi_edit_cat",
                        )
                        edit_type = st.selectbox(
                            "Type",
                            ["expense", "investment", "debt", "insurance"],
                            index=["expense", "investment", "debt", "insurance"].index(
                                edit_item.get("type", "expense")
                            ),
                            key="bi_edit_type",
                        )
                    with ec2:
                        freq_list = [
                            "Monthly",
                            "Quarterly",
                            "Half-Yearly",
                            "Yearly",
                            "One-Time",
                            "As Needed",
                        ]
                        cur_freq = edit_item.get("frequency", "Monthly")
                        edit_freq = st.selectbox(
                            "Frequency",
                            freq_list,
                            index=(
                                freq_list.index(cur_freq)
                                if cur_freq in freq_list
                                else 0
                            ),
                            key="bi_edit_freq",
                        )
                        edit_due = st.text_input(
                            "Due Date",
                            value=edit_item.get("due_date", ""),
                            key="bi_edit_due",
                        )
                        edit_paid = st.text_input(
                            "Paid By",
                            value=edit_item.get("paid_by", ""),
                            key="bi_edit_paid",
                        )
                        prio_list = ["High", "Medium", "Low", "TBD"]
                        cur_prio = edit_item.get("priority", "Medium")
                        edit_prio = st.selectbox(
                            "Priority",
                            prio_list,
                            index=(
                                prio_list.index(cur_prio)
                                if cur_prio in prio_list
                                else 1
                            ),
                            key="bi_edit_prio",
                        )
                        edit_notes = st.text_area(
                            "Notes",
                            value=edit_item.get("notes", ""),
                            key="bi_edit_notes",
                            height=80,
                        )

                    if st.button("💾 Save Changes", key="bi_edit_save"):
                        items[edit_idx] = {
                            **edit_item,
                            "name": edit_name,
                            "amount": edit_amount,
                            "category": edit_category,
                            "type": edit_type,
                            "frequency": edit_freq,
                            "due_date": edit_due,
                            "paid_by": edit_paid,
                            "priority": edit_prio,
                            "notes": edit_notes,
                        }
                        totals = _compute_totals(items)
                        save_data = {
                            "income": budget.get("income", 0),
                            "expenses": round(totals["expense"] + totals["debt"]),
                            "investments": round(totals["investment"]),
                            "expense_categories": budget.get("expense_categories", {}),
                            "budget_items": items,
                        }
                        _save_budget(save_data)
                        st.success(f"Updated: {edit_name}")
                        st.rerun()

            # --- Person-wise Split ---
            if all_paid_by and len(all_paid_by) > 1:
                st.divider()
                st.subheader("👥 Person-wise Split")
                person_cols = st.columns(len(all_paid_by))
                for idx, person in enumerate(all_paid_by):
                    person_items = [
                        i
                        for i in items
                        if person in i.get("paid_by", "")
                        and i.get("frequency") not in ("One-Time", "As Needed")
                    ]
                    person_total = sum(
                        _monthly_equivalent(
                            i.get("amount", 0), i.get("frequency", "Monthly")
                        )
                        for i in person_items
                    )
                    with person_cols[idx]:
                        st.metric(f"{person}", f"₹{person_total:,.0f}/mo")
                        for i in person_items:
                            m = _monthly_equivalent(
                                i.get("amount", 0), i.get("frequency", "Monthly")
                            )
                            if m > 0:
                                st.caption(f"• {i.get('name', '')}: ₹{m:,.0f}")

            # --- Upcoming Payments ---
            yearly_items = [
                i
                for i in items
                if i.get("frequency") in ("Yearly", "Half-Yearly", "Quarterly")
                and i.get("amount", 0) > 0
            ]
            if yearly_items:
                st.divider()
                st.subheader("📅 Non-Monthly Payments")
                nmp_rows = []
                for i in yearly_items:
                    nmp_rows.append(
                        {
                            "Name": i.get("name", ""),
                            "Amount (₹)": f"{i.get('amount', 0):,}",
                            "Frequency": i.get("frequency", ""),
                            "Monthly Equiv (₹)": f"{_monthly_equivalent(i.get('amount', 0), i.get('frequency', 'Monthly')):,.0f}",
                            "Due": i.get("due_date", ""),
                            "Paid By": i.get("paid_by", ""),
                        }
                    )
                st.dataframe(
                    pd.DataFrame(nmp_rows),
                    hide_index=True,
                    use_container_width=True,
                )

            # --- Summary ---
            st.divider()
            st.subheader("📊 Budget Summary")
            totals = _compute_totals(items)
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Expenses", f"₹{totals['expense'] + totals['debt']:,.0f}/mo")
            s2.metric("Investments", f"₹{totals['investment']:,.0f}/mo")
            s3.metric("Insurance", f"₹{totals['insurance']:,.0f}/mo")
            grand = sum(totals.values())
            s4.metric("Total Outflow", f"₹{grand:,.0f}/mo")

            # Category-wise breakdown chart
            cat_totals = {}
            for item in items:
                cat = item.get("category", "Others")
                freq = item.get("frequency", "Monthly")
                if freq not in ("One-Time", "As Needed"):
                    cat_totals[cat] = cat_totals.get(cat, 0) + _monthly_equivalent(
                        item.get("amount", 0), freq
                    )
            if cat_totals:
                sorted_cats = dict(
                    sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
                )
                st.bar_chart(pd.Series(sorted_cats, name="₹/month"), height=300)
        else:
            st.info(
                "No budget items yet. Add your expenses, investments, debt, and "
                "insurance items above to build your custom budget plan!"
            )

    with budget_tab3:
        st.subheader("💡 Budget Rules & Benchmarks")

        actual_income = income if income else budget.get("income", 0)

        # Auto-derive from budget items when available
        if item_totals:
            actual_expenses = round(item_totals["expense"] + item_totals["debt"])
            actual_investments = round(item_totals["investment"])
            actual_insurance = round(item_totals["insurance"])
            total_outflow = actual_expenses + actual_investments + actual_insurance
            st.caption(
                f"📋 Using data from your **Budget Plan**: "
                f"Expenses ₹{actual_expenses:,} | "
                f"Investments ₹{actual_investments:,} | "
                f"Insurance ₹{actual_insurance:,}"
            )
        else:
            actual_expenses = expenses if expenses else budget.get("expenses", 0)
            actual_investments = (
                investments if investments else budget.get("investments", 0)
            )
            actual_insurance = 0
            total_outflow = actual_expenses + actual_investments

        if actual_income > 0:
            # 50-30-20 Rule
            st.markdown("##### 📏 50-30-20 Rule")
            st.caption("50% Needs, 30% Wants, 20% Savings & Investments")

            ideal_needs = actual_income * 0.5
            ideal_wants = actual_income * 0.3
            ideal_savings = actual_income * 0.2

            # Derive needs/wants from budget items if available
            needs_categories = {
                "Rental House",
                "Living Expenses",
                "Utilities",
                "Family Support",
                "Household Help",
                "Rent/EMI",
                "Groceries",
                "Transport",
                "Healthcare",
                "Education",
                "Child",
                "Donations",
                "Home Loan",
                "Education Loan",
            }
            wants_categories = {
                "Entertainment",
                "Shopping",
                "Dining Out",
                "Subscriptions",
                "Travel",
            }

            if items:
                actual_needs = sum(
                    _monthly_equivalent(
                        i.get("amount", 0), i.get("frequency", "Monthly")
                    )
                    for i in items
                    if i.get("type") in ("expense", "debt")
                    and i.get("category", "") in needs_categories
                    and i.get("frequency") not in ("One-Time", "As Needed")
                )
                actual_wants = sum(
                    _monthly_equivalent(
                        i.get("amount", 0), i.get("frequency", "Monthly")
                    )
                    for i in items
                    if i.get("type") == "expense"
                    and i.get("category", "") in wants_categories
                    and i.get("frequency") not in ("One-Time", "As Needed")
                )
                # Items not matching needs/wants categories count as needs
                unclassified = sum(
                    _monthly_equivalent(
                        i.get("amount", 0), i.get("frequency", "Monthly")
                    )
                    for i in items
                    if i.get("type") in ("expense", "debt")
                    and i.get("category", "") not in needs_categories
                    and i.get("category", "") not in wants_categories
                    and i.get("frequency") not in ("One-Time", "As Needed")
                )
                actual_needs += unclassified
            else:
                categories = budget.get("expense_categories", {})
                actual_needs = sum(
                    categories.get(c, 0)
                    for c in [
                        "Rent/EMI",
                        "Groceries",
                        "Utilities",
                        "Transport",
                        "Healthcare",
                        "Insurance",
                        "Education",
                    ]
                )
                actual_wants = sum(
                    categories.get(c, 0)
                    for c in [
                        "Dining Out",
                        "Shopping",
                        "Entertainment",
                        "Subscriptions",
                    ]
                )

            rule_data = pd.DataFrame(
                {
                    "Category": ["Needs (50%)", "Wants (30%)", "Savings (20%)"],
                    "Ideal (₹)": [ideal_needs, ideal_wants, ideal_savings],
                    "Actual (₹)": [actual_needs, actual_wants, actual_investments],
                    "Status": [
                        "✅" if actual_needs <= ideal_needs else "⚠️ Over",
                        "✅" if actual_wants <= ideal_wants else "⚠️ Over",
                        "✅" if actual_investments >= ideal_savings else "⚠️ Under",
                    ],
                }
            )
            st.dataframe(rule_data, hide_index=True, width="stretch")

            st.divider()

            # Key ratios
            st.markdown("##### 📊 Financial Ratios")

            fr1, fr2, fr3 = st.columns(3)
            savings_rate = ((actual_income - total_outflow) / actual_income) * 100
            investment_rate = (
                (actual_investments / actual_income) * 100 if actual_income else 0
            )

            # EMI/Rent burden from items or categories
            if items:
                rent_emi = sum(
                    _monthly_equivalent(
                        i.get("amount", 0), i.get("frequency", "Monthly")
                    )
                    for i in items
                    if i.get("type") in ("expense", "debt")
                    and i.get("category", "").lower()
                    in (
                        "rental house",
                        "rent/emi",
                        "debt",
                    )
                    and i.get("frequency") not in ("One-Time", "As Needed")
                )
            else:
                categories = budget.get("expense_categories", {})
                rent_emi = categories.get("Rent/EMI", 0)

            emi_ratio = (rent_emi / actual_income) * 100 if actual_income else 0

            fr1.metric(
                "Savings Rate",
                f"{savings_rate:.0f}%",
                "Good!" if savings_rate >= 20 else "Needs improvement",
            )
            fr2.metric(
                "Investment Rate",
                f"{investment_rate:.0f}%",
                "Strong!" if investment_rate >= 20 else "Consider increasing",
            )
            fr3.metric(
                "EMI/Rent Burden",
                f"{emi_ratio:.0f}%",
                "Safe" if emi_ratio <= 40 else "⚠️ High — should be under 40%",
            )

            st.divider()
            st.markdown("##### 💡 Tips")
            tips = []
            if savings_rate < 20:
                tips.append("📌 Aim to save at least 20% of your income")
            if investment_rate < 15:
                tips.append("📌 Try to invest at least 15% of income through SIPs")
            if emi_ratio > 40:
                tips.append(
                    "📌 EMI/Rent above 40% is risky — consider downsizing or increasing income"
                )
            if actual_wants > ideal_wants:
                tips.append(
                    f"📌 Wants spending is ₹{actual_wants - ideal_wants:,.0f} over budget — review discretionary spending"
                )
            if not tips:
                tips.append("✅ Your budget follows healthy financial principles!")
            for tip in tips:
                st.markdown(tip)
        else:
            st.info("Enter your income in the Overview tab to see budget analysis.")
