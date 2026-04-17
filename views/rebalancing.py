"""Rebalancing view — shows current vs target allocation and drift alerts."""

import streamlit as st
import pandas as pd

from analysis import calculate_rebalancing, DEFAULT_TARGET_ALLOCATION
import db


def render(holdings):
    st.header("⚖️ Portfolio Rebalancing")
    st.caption("Compare your current allocation against target and get drift alerts")

    if not holdings:
        st.info("Add holdings in **⚙️ Manage Portfolio** to use rebalancing.")
        return

    # --- Target allocation editor ---
    with st.expander("🎯 Customise Target Allocation", expanded=False):
        st.caption("Adjust target percentages (must sum to 100%)")
        cols = st.columns(3)
        custom_targets = {}
        for i, (ac, config) in enumerate(DEFAULT_TARGET_ALLOCATION.items()):
            with cols[i % 3]:
                pct = st.number_input(
                    config["label"],
                    min_value=0.0,
                    max_value=100.0,
                    value=config["target_pct"],
                    step=5.0,
                    key=f"rebal_target_{ac}",
                )
                tol = st.number_input(
                    f"Tolerance %",
                    min_value=1.0,
                    max_value=20.0,
                    value=config["tolerance_pct"],
                    step=1.0,
                    key=f"rebal_tol_{ac}",
                )
                custom_targets[ac] = {
                    "target_pct": pct,
                    "tolerance_pct": tol,
                    "label": config["label"],
                }

        total_target = sum(t["target_pct"] for t in custom_targets.values())
        if abs(total_target - 100.0) > 0.1:
            st.warning(f"Target allocation sums to {total_target}% — should be 100%")

    # --- Calculate rebalancing ---
    result = calculate_rebalancing(
        holdings,
        analysis_results=None,
        targets=custom_targets,
    )

    if not result:
        st.warning("Unable to calculate rebalancing — check portfolio data.")
        return

    # --- Status banner ---
    if result["needs_rebalancing"]:
        st.error(f"⚠️ **Rebalancing needed** — {result['summary']}")
    else:
        st.success(f"✅ **Portfolio is balanced** — {result['summary']}")

    st.metric("Total Portfolio Value", f"₹{result['total_value']:,.0f}")

    # --- Allocation table ---
    st.subheader("Current vs Target Allocation")

    df_data = []
    for a in result["allocations"]:
        action_icon = {"ADD": "🟢 Add", "REDUCE": "🔴 Reduce", "OK": "✅ OK"}.get(
            a["action"], a["action"]
        )
        df_data.append(
            {
                "Asset Class": a["label"],
                "Current %": a["current_pct"],
                "Target %": a["target_pct"],
                "Drift %": a["drift_pct"],
                "Action": action_icon,
                "Amount (₹)": (
                    f"₹{a['rebalance_amount']:,}" if a["action"] != "OK" else "—"
                ),
                "Holdings": ", ".join(a["holdings_in_class"][:5]) or "None",
            }
        )

    df = pd.DataFrame(df_data)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Drift %": st.column_config.NumberColumn(format="%.1f%%"),
            "Current %": st.column_config.NumberColumn(format="%.1f%%"),
            "Target %": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    # --- Visual bar chart ---
    st.subheader("Allocation Comparison")

    chart_data = pd.DataFrame(
        {
            "Asset Class": [a["label"] for a in result["allocations"]],
            "Current %": [a["current_pct"] for a in result["allocations"]],
            "Target %": [a["target_pct"] for a in result["allocations"]],
        }
    ).set_index("Asset Class")

    st.bar_chart(chart_data)

    # --- Action items ---
    actions_needed = [a for a in result["allocations"] if a["action"] != "OK"]
    if actions_needed:
        st.subheader("📋 Suggested Actions")
        for a in actions_needed:
            if a["action"] == "REDUCE":
                st.markdown(
                    f"🔴 **{a['label']}**: Over-allocated by {a['drift_pct']:+.1f}%. "
                    f"Consider moving ~₹{a['rebalance_amount']:,} to under-allocated classes."
                )
            elif a["action"] == "ADD":
                st.markdown(
                    f"🟢 **{a['label']}**: Under-allocated by {a['drift_pct']:+.1f}%. "
                    f"Consider adding ~₹{a['rebalance_amount']:,} through SIP or lumpsum."
                )

        st.caption(
            "⚠️ This is a technical analysis tool, not investment advice. "
            "Consult a SEBI-registered adviser before making changes."
        )
