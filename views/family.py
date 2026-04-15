"""Family account management — multi-profile portfolio tracking."""

import streamlit as st
import pandas as pd

from analysis import load_portfolio_extended, calculate_portfolio_pnl
import auth
import db


def render(holdings):
    st.header("👨‍👩‍👧‍👦 Family Accounts")
    st.caption("Manage portfolios for family members and see combined net worth")

    user_id = auth.get_user_id()

    # Load family members
    members = db.load_family_members(user_id)

    tabs = st.tabs(["👥 Members", "📊 Combined View"])

    # --- Tab 1: Manage Members ---
    with tabs[0]:
        # Add member form
        with st.expander("➕ Add Family Member", expanded=not bool(members)):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input(
                    "Name", placeholder="e.g., Spouse, Child 1", key="fam_name"
                )
            with col2:
                profile_type = st.selectbox(
                    "Relationship",
                    ["Spouse", "Child", "Parent", "Sibling", "Other"],
                    key="fam_type",
                )

            if st.button("Add Member", key="fam_add") and name:
                db.save_family_member(
                    {"name": name, "profile_type": profile_type.lower()},
                    user_id,
                )
                st.success(f"Added {name}")
                st.rerun()

        if not members:
            st.info(
                "No family members added yet. Add members above to track their portfolios separately."
            )
            return

        # List members with their portfolio summaries
        for member in members:
            mid = member["id"]
            mname = member.get("name", "Unknown")
            mtype = member.get("profile_type", "").title()

            with st.expander(f"👤 {mname} ({mtype})", expanded=False):
                # Load member's portfolio
                member_portfolio = db.load_family_portfolio(mid, user_id)

                if member_portfolio:
                    st.caption(f"{len(member_portfolio)} holdings")

                    # Quick summary
                    total_invested = sum(
                        r.get("buy_price", 0) * r.get("quantity", 0)
                        for r in member_portfolio
                    )
                    st.metric("Total Invested", f"₹{total_invested:,.0f}")

                    # Show holdings table
                    df = pd.DataFrame(
                        [
                            {
                                "Name": r.get("name", ""),
                                "Type": r.get("type", ""),
                                "Qty": r.get("quantity", 0),
                                "Buy Price": f"₹{r.get('buy_price', 0):,.2f}",
                                "Invested": f"₹{r.get('buy_price', 0) * r.get('quantity', 0):,.0f}",
                            }
                            for r in member_portfolio
                        ]
                    )
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.caption("No holdings tracked for this member")

                # Add holding for member
                with st.form(f"add_holding_{mid}"):
                    st.caption("Quick Add Holding")
                    hc1, hc2, hc3 = st.columns(3)
                    with hc1:
                        h_name = st.text_input("Stock/MF Name", key=f"fh_name_{mid}")
                        h_ticker = st.text_input(
                            "Ticker (e.g., TCS.NS)", key=f"fh_ticker_{mid}"
                        )
                    with hc2:
                        h_price = st.number_input(
                            "Buy Price (₹)",
                            min_value=0.0,
                            step=10.0,
                            key=f"fh_price_{mid}",
                        )
                        h_qty = st.number_input(
                            "Quantity", min_value=0.0, step=1.0, key=f"fh_qty_{mid}"
                        )
                    with hc3:
                        h_type = st.selectbox(
                            "Type",
                            ["stock", "mutual_fund", "etf", "gold_bond"],
                            key=f"fh_type_{mid}",
                        )
                        h_date = st.date_input("Buy Date", key=f"fh_date_{mid}")

                    if st.form_submit_button("Add") and h_name and h_price > 0:
                        new_holding = {
                            "name": h_name,
                            "ticker": h_ticker,
                            "type": h_type,
                            "buy_price": h_price,
                            "quantity": h_qty,
                            "buy_date": h_date.strftime("%Y-%m-%d"),
                            "amount": h_price * h_qty,
                            "sip_monthly": 0,
                            "sip_date": 0,
                            "amfi_code": "",
                            "investment_mode": "lumpsum",
                            "transactions": [],
                            "sip_pause_periods": [],
                        }
                        member_portfolio.append(new_holding)
                        db.save_family_portfolio(member_portfolio, mid, user_id)
                        st.success(f"Added {h_name} for {mname}")
                        st.rerun()

                # Delete member
                if st.button(f"🗑️ Remove {mname}", key=f"del_{mid}"):
                    db.delete_family_member(mid, user_id)
                    st.success(f"Removed {mname}")
                    st.rerun()

    # --- Tab 2: Combined View ---
    with tabs[1]:
        st.subheader("Combined Family Portfolio")

        if not members:
            st.info("Add family members first to see the combined view.")
            return

        # Your (primary user) portfolio
        all_holdings = []
        portfolio_by_member = {}

        # Primary user
        primary_portfolio = db.load_portfolio(user_id)
        primary_invested = sum(
            r.get("buy_price", 0) * r.get("quantity", 0) for r in primary_portfolio
        )
        portfolio_by_member["You"] = primary_invested
        all_holdings.extend(primary_portfolio)

        # Family members
        for member in members:
            mid = member["id"]
            mname = member.get("name", "Unknown")
            member_portfolio = db.load_family_portfolio(mid, user_id)
            member_invested = sum(
                r.get("buy_price", 0) * r.get("quantity", 0) for r in member_portfolio
            )
            portfolio_by_member[mname] = member_invested
            all_holdings.extend(member_portfolio)

        # Summary metrics
        total_family = sum(portfolio_by_member.values())
        total_holdings = len(all_holdings)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Family Invested", f"₹{total_family:,.0f}")
        col2.metric("Total Holdings", total_holdings)
        col3.metric("Family Members", len(members) + 1)

        # Per-member breakdown
        if portfolio_by_member:
            df = pd.DataFrame(
                [
                    {
                        "Member": k,
                        "Invested (₹)": v,
                        "Share %": (
                            round(v / total_family * 100, 1) if total_family > 0 else 0
                        ),
                    }
                    for k, v in portfolio_by_member.items()
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.bar_chart(df.set_index("Member")["Invested (₹)"])

        # Combined type breakdown
        type_totals = {}
        for h in all_holdings:
            t = h.get("type", "stock")
            type_totals[t] = type_totals.get(t, 0) + h.get("buy_price", 0) * h.get(
                "quantity", 0
            )

        if type_totals:
            st.subheader("Asset Type Breakdown (Combined)")
            type_df = pd.DataFrame(
                [
                    {"Type": k.replace("_", " ").title(), "Value (₹)": v}
                    for k, v in type_totals.items()
                    if v > 0
                ]
            )
            st.bar_chart(type_df.set_index("Type"))
