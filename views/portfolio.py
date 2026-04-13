import streamlit as st
import pandas as pd
import json
from datetime import datetime
import yfinance as yf

from analysis import (
    analyze_portfolio,
    calculate_portfolio_pnl,
    fetch_mf_nav_batch,
    compute_diversification,
    load_portfolio_extended,
    is_sip_currently_paused,
)
from ui_helpers import generate_portfolio_pdf


@st.cache_data(ttl=300, show_spinner=False)
def _cached_analyze_portfolio(holdings_key):
    """Cached wrapper — avoids re-fetching market data on every page load."""
    holdings = json.loads(holdings_key)
    return analyze_portfolio(holdings)


def render(holdings):
    st.title("📁 My Portfolio")

    if not holdings:
        st.info(
            "No portfolio data yet. Go to **⚙️ Manage Portfolio** from the sidebar to add your investments."
        )
    else:
        # Summary cards
        total = sum(h["amount"] for h in holdings)
        stocks = [h for h in holdings if h["type"] == "stock"]
        mfs = [h for h in holdings if h["type"] == "mutual_fund"]
        active_sips = [
            h
            for h in holdings
            if h["sip_monthly"] > 0 and not is_sip_currently_paused(h)
        ]
        paused_sips = [
            h for h in holdings if h["sip_monthly"] > 0 and is_sip_currently_paused(h)
        ]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Invested", f"₹{total:,.0f}")
        c2.metric(
            "Stocks", f"{len(stocks)}", f"₹{sum(h['amount'] for h in stocks):,.0f}"
        )
        c3.metric(
            "Mutual Funds", f"{len(mfs)}", f"₹{sum(h['amount'] for h in mfs):,.0f}"
        )
        sip_help = f"₹{sum(h['sip_monthly'] for h in active_sips):,.0f}/mo"
        if paused_sips:
            sip_help += f" · {len(paused_sips)} paused"
        c4.metric(
            "Active SIPs",
            f"{len(active_sips)}",
            sip_help,
        )

        st.divider()

        # --- P&L Tracking ---
        st.subheader("📈 Profit & Loss")
        with st.spinner("Calculating P&L..."):
            holdings_key = json.dumps(holdings, sort_keys=True, default=str)
            pnl_results = _cached_analyze_portfolio(holdings_key)
            pnl_data = calculate_portfolio_pnl(holdings, pnl_results)

        if pnl_data:
            pnl_color = "#27ae60" if pnl_data["total_pnl"] >= 0 else "#e74c3c"
            pnl_icon = "📈" if pnl_data["total_pnl"] >= 0 else "📉"

            # Big P&L summary card
            st.markdown(
                f"""<div style="background: linear-gradient(135deg, {pnl_color}22, {pnl_color}11);
                border-left: 5px solid {pnl_color}; border-radius: 10px;
                padding: 20px; margin: 10px 0;">
                <h3 style="margin:0;">{pnl_icon} Total Returns: <span style="color: {pnl_color};">₹{pnl_data['total_pnl']:+,.0f}</span>
                <span style="font-size: 0.7em; opacity: 0.8;">({pnl_data['total_pnl_pct']:+.1f}%)</span></h3>
                </div>""",
                unsafe_allow_html=True,
            )

            pl1, pl2, pl3, pl4 = st.columns(4)
            pl1.metric("Invested", f"₹{pnl_data['total_invested']:,.0f}")
            pl2.metric("Current Value", f"₹{pnl_data['total_current']:,.0f}")
            pl3.metric(
                "Returns",
                f"₹{pnl_data['total_pnl']:+,.0f}",
                f"{pnl_data['total_pnl_pct']:+.1f}%",
            )
            if pnl_data["xirr"] is not None:
                pl4.metric("XIRR (Annualized)", f"{pnl_data['xirr']:+.1f}%")
            else:
                pl4.metric("Absolute Return", f"{pnl_data['total_pnl_pct']:+.1f}%")

            # Per-holding P&L table
            with st.expander("📋 Per-Holding P&L", expanded=True):
                pnl_rows = []
                # Build a lookup for tax info from holdings
                holdings_by_name = {h["name"]: h for h in holdings}
                for hp in pnl_data["holdings_pnl"]:
                    pnl_sign = "🟢" if hp["pnl"] >= 0 else "🔴"
                    # Tax status from holdings data
                    h_match = holdings_by_name.get(hp["name"], {})
                    tax_label = ""
                    if h_match.get("is_ltcg") is not None:
                        if h_match["is_ltcg"]:
                            tax_label = "LTCG (10%)"
                        else:
                            tax_label = "STCG (15%)"
                    pnl_rows.append(
                        {
                            "": pnl_sign,
                            "Name": hp["name"],
                            "Invested": f"₹{hp['invested']:,.0f}",
                            "Current": f"₹{hp['current_value']:,.0f}",
                            "P&L": f"₹{hp['pnl']:+,.0f}",
                            "Return": f"{hp['pnl_pct']:+.1f}%",
                            "Tax": tax_label,
                            "Today": f"{hp['daily_change_pct']:+.1f}%",
                        }
                    )
                st.dataframe(pd.DataFrame(pnl_rows), width="stretch", hide_index=True)

            # PDF Export
            st.divider()
            if st.button("📄 Download Portfolio Report (PDF)"):
                with st.spinner("Generating PDF..."):
                    pdf_bytes = generate_portfolio_pdf(holdings, pnl_data)
                    if pdf_bytes:
                        st.download_button(
                            "⬇️ Download PDF",
                            data=pdf_bytes,
                            file_name=f"portfolio_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                        )

        st.divider()

        # Allocation charts
        a1, a2 = st.columns(2)

        with a1:
            st.subheader("📊 By Type")
            type_data = {}
            for h in holdings:
                t = h["type"].replace("_", " ").title()
                type_data[t] = type_data.get(t, 0) + h["amount"]
            st.bar_chart(pd.Series(type_data, name="₹"), height=250)

        with a2:
            st.subheader("📊 Top Holdings")
            top = sorted(holdings, key=lambda x: x["amount"], reverse=True)[:5]
            top_data = {h["name"][:20]: h["amount"] for h in top}
            st.bar_chart(pd.Series(top_data, name="₹"), height=250)

        st.divider()

        # MF NAVs
        mf_codes = [h["amfi_code"] for h in holdings if h.get("amfi_code")]
        if mf_codes:
            st.subheader("📊 Mutual Fund NAVs")
            with st.spinner("Fetching NAVs from AMFI India..."):
                try:
                    mf_navs = fetch_mf_nav_batch(mf_codes)
                    if mf_navs:
                        nav_rows = []
                        for code, info in mf_navs.items():
                            matching = [
                                h for h in holdings if h.get("amfi_code") == code
                            ]
                            invested = matching[0]["amount"] if matching else 0
                            nav_rows.append(
                                {
                                    "Scheme": info["scheme_name"][:50],
                                    "NAV (₹)": f"{info['nav']:.4f}",
                                    "Date": info["date"],
                                    "Invested": f"₹{invested:,.0f}",
                                }
                            )
                        st.dataframe(
                            pd.DataFrame(nav_rows),
                            width="stretch",
                            hide_index=True,
                        )
                except Exception as e:
                    st.warning(f"NAV fetch failed: {e}")

        st.divider()

        # Diversification
        st.subheader("🎯 Diversification Score")
        tickers_for_div = [h for h in holdings if h["ticker"]]
        div_results = _cached_analyze_portfolio(holdings_key) if tickers_for_div else []
        div_data = compute_diversification(holdings, div_results)

        if div_data:
            score = div_data["score"]
            score_emoji = "🟢" if score >= 60 else "🟡" if score >= 40 else "🔴"
            score_label = (
                "Well Diversified"
                if score >= 60
                else "Moderate" if score >= 40 else "Concentrated"
            )

            d1, d2, d3 = st.columns(3)
            d1.metric("Score", f"{score_emoji} {score}/100", score_label)
            d2.metric("Holdings", f"{len(holdings)}")
            d3.metric(
                "Concentration", f"{div_data['hhi']:.0f}", "Lower = more diversified"
            )

            if div_data["warnings"]:
                st.subheader("⚠️ Alerts")
                for w in div_data["warnings"]:
                    warn_text = w[0] if isinstance(w, tuple) else w
                    fix_text = w[1] if isinstance(w, tuple) else ""
                    st.warning(warn_text)
                    if fix_text:
                        with st.expander("💡 How to fix this"):
                            st.markdown(fix_text)
