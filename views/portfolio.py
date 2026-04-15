import streamlit as st
import pandas as pd
import json
import io
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
import db
import auth


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

        st.divider()

        # =====================================================================
        # Portfolio Value History + Benchmark Comparison
        # =====================================================================
        st.subheader("📈 Portfolio Value Over Time")

        # Save today's snapshot
        if pnl_data:
            try:
                nifty_close = None
                sensex_close = None
                try:
                    nd = yf.Ticker("^NSEI").history(period="1d")
                    if not nd.empty:
                        nifty_close = round(float(nd["Close"].iloc[-1]), 2)
                    sd = yf.Ticker("^BSESN").history(period="1d")
                    if not sd.empty:
                        sensex_close = round(float(sd["Close"].iloc[-1]), 2)
                except Exception:
                    pass

                snapshot = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "total_invested": round(pnl_data["total_invested"], 2),
                    "total_current": round(pnl_data["total_current"], 2),
                    "total_pnl": round(pnl_data["total_pnl"], 2),
                    "total_pnl_pct": round(pnl_data["total_pnl_pct"], 2),
                    "holdings_count": len(holdings),
                    "nifty_close": nifty_close,
                    "sensex_close": sensex_close,
                    "snapshot_json": json.dumps(
                        [
                            {"name": hp["name"], "value": round(hp["current_value"], 2)}
                            for hp in pnl_data["holdings_pnl"][:20]
                        ],
                        default=str,
                    ),
                }
                user_id = auth.get_user_id()
                db.save_portfolio_snapshot(snapshot, user_id)
            except Exception:
                pass

        # Load and display history
        try:
            user_id = auth.get_user_id()
            history = db.load_portfolio_history(user_id, limit=365)
            if history and len(history) >= 2:
                hist_df = pd.DataFrame(history)
                hist_df["date"] = pd.to_datetime(hist_df["date"])
                hist_df = hist_df.sort_values("date").set_index("date")

                # Portfolio value chart
                chart_data = pd.DataFrame(
                    {
                        "Portfolio Value": hist_df["total_current"],
                        "Amount Invested": hist_df["total_invested"],
                    }
                )
                st.line_chart(chart_data, height=300)

                # Benchmark comparison
                if hist_df["nifty_close"].notna().sum() >= 2:
                    st.subheader("📊 Portfolio vs Benchmark")
                    st.caption("Normalized returns comparison (base = 100)")

                    first_valid = hist_df.dropna(subset=["nifty_close"]).iloc[0]
                    base_portfolio = first_valid["total_current"]
                    base_nifty = first_valid["nifty_close"]

                    valid_hist = hist_df.dropna(subset=["nifty_close"])
                    benchmark_df = pd.DataFrame(
                        {
                            "Your Portfolio": (
                                valid_hist["total_current"] / base_portfolio
                            )
                            * 100,
                            "Nifty 50": (valid_hist["nifty_close"] / base_nifty) * 100,
                        }
                    )
                    if valid_hist["sensex_close"].notna().sum() >= 2:
                        base_sensex = valid_hist["sensex_close"].dropna().iloc[0]
                        benchmark_df["Sensex"] = (
                            valid_hist["sensex_close"] / base_sensex
                        ) * 100

                    st.line_chart(benchmark_df, height=300)

                    # Performance summary
                    latest = hist_df.iloc[-1]
                    first = hist_df.iloc[0]
                    portfolio_return = (
                        ((latest["total_current"] / first["total_current"]) - 1) * 100
                        if first["total_current"] > 0
                        else 0
                    )
                    b1, b2, b3 = st.columns(3)
                    b1.metric("Your Returns", f"{portfolio_return:+.1f}%")
                    if (
                        pd.notna(latest.get("nifty_close"))
                        and pd.notna(first.get("nifty_close"))
                        and first["nifty_close"] > 0
                    ):
                        nifty_return = (
                            (latest["nifty_close"] / first["nifty_close"]) - 1
                        ) * 100
                        b2.metric("Nifty 50 Returns", f"{nifty_return:+.1f}%")
                        alpha = portfolio_return - nifty_return
                        b3.metric(
                            "Alpha (vs Nifty)",
                            f"{alpha:+.1f}%",
                            (
                                "Beating the market! 🎉"
                                if alpha > 0
                                else "Underperforming index"
                            ),
                        )
            else:
                st.info(
                    "Portfolio history will appear here after a few days of tracking. Check back tomorrow!"
                )
        except Exception:
            st.info("Portfolio history tracking will start from today.")

        st.divider()

        # =====================================================================
        # Tax-Loss Harvesting Suggestions
        # =====================================================================
        if pnl_data and pnl_data.get("holdings_pnl"):
            st.subheader("💸 Tax-Loss Harvesting Opportunities")
            st.caption(
                "Holdings in loss that you could sell to offset capital gains tax"
            )

            losers = [hp for hp in pnl_data["holdings_pnl"] if hp["pnl"] < 0]
            winners = [hp for hp in pnl_data["holdings_pnl"] if hp["pnl"] > 0]
            total_gains = sum(hp["pnl"] for hp in winners)
            total_losses = sum(abs(hp["pnl"]) for hp in losers)

            if losers and total_gains > 0:
                harvestable = min(total_losses, total_gains)
                # Estimate tax saved (15% STCG rate as conservative)
                tax_saved = harvestable * 0.15

                tc1, tc2, tc3 = st.columns(3)
                tc1.metric("Total Gains", f"₹{total_gains:,.0f}")
                tc2.metric("Harvestable Losses", f"₹{total_losses:,.0f}")
                tc3.metric("Potential Tax Savings", f"~₹{tax_saved:,.0f}")

                with st.expander(
                    "📋 Holdings you could sell for tax benefit", expanded=False
                ):
                    for hp in sorted(losers, key=lambda x: x["pnl"]):
                        h_match = {h["name"]: h for h in holdings}.get(hp["name"], {})
                        tax_type = ""
                        if h_match.get("is_ltcg") is not None:
                            tax_type = "LTCG" if h_match["is_ltcg"] else "STCG"
                        st.markdown(
                            f"🔴 **{hp['name']}** — Loss: ₹{hp['pnl']:,.0f} ({hp['pnl_pct']:+.1f}%) "
                            f"{'· ' + tax_type if tax_type else ''}"
                        )
                    st.caption(
                        "💡 Sell losing positions before March 31 to offset gains. "
                        "You can re-buy after 30 days to maintain your position."
                    )
            elif losers:
                st.info(
                    "You have losing positions but no gains to offset. No harvesting needed right now."
                )
            else:
                st.success("✅ No losing positions — nothing to harvest!")

        st.divider()

        # =====================================================================
        # Dividend Tracking
        # =====================================================================
        st.subheader("💰 Dividend Income")
        user_id = auth.get_user_id()
        dividends = db.load_dividends(user_id)

        with st.expander("➕ Record a Dividend", expanded=False):
            with st.form("add_dividend_form"):
                div_cols = st.columns(3)
                div_ticker = div_cols[0].selectbox(
                    "Stock/MF",
                    options=[h["name"] for h in holdings] if holdings else ["—"],
                    key="div_ticker_select",
                )
                div_amount = div_cols[1].number_input(
                    "Amount (₹)", min_value=0.0, step=100.0, key="div_amt"
                )
                div_date = div_cols[2].date_input(
                    "Date", value=datetime.now(), key="div_date"
                )
                div_submit = st.form_submit_button("Add Dividend")

                if div_submit and div_amount > 0 and div_ticker != "—":
                    matching_h = next(
                        (h for h in holdings if h["name"] == div_ticker), None
                    )
                    db.save_dividend(
                        {
                            "ticker": matching_h["ticker"] if matching_h else "",
                            "name": div_ticker,
                            "amount": div_amount,
                            "date": div_date.strftime("%Y-%m-%d"),
                        },
                        user_id,
                    )
                    st.success(f"Added ₹{div_amount:,.0f} dividend from {div_ticker}")
                    st.rerun()

        if dividends:
            total_divs = sum(d.get("amount", 0) for d in dividends)
            div_this_year = sum(
                d.get("amount", 0)
                for d in dividends
                if d.get("date", "").startswith(str(datetime.now().year))
            )
            dc1, dc2, dc3 = st.columns(3)
            dc1.metric("Total Dividends", f"₹{total_divs:,.0f}")
            dc2.metric("This Year", f"₹{div_this_year:,.0f}")
            if pnl_data and pnl_data["total_current"] > 0:
                div_yield = (div_this_year / pnl_data["total_current"]) * 100
                dc3.metric("Dividend Yield", f"{div_yield:.2f}%")

            div_df = pd.DataFrame(
                [
                    {
                        "Date": d.get("date", ""),
                        "Stock": d.get("name", ""),
                        "Amount": f"₹{d.get('amount', 0):,.0f}",
                    }
                    for d in dividends[:20]
                ]
            )
            st.dataframe(div_df, hide_index=True, width="stretch")
        else:
            st.caption("No dividends recorded yet. Add your first one above!")

        st.divider()

        # =====================================================================
        # Rebalancing Calculator
        # =====================================================================
        st.subheader("⚖️ Rebalancing Calculator")
        st.caption("Set target allocation and see what trades to make")

        if pnl_data and holdings:
            total_value = pnl_data["total_current"]
            stock_value = sum(
                hp["current_value"]
                for hp in pnl_data["holdings_pnl"]
                if any(
                    h["name"] == hp["name"] and h["type"] == "stock" for h in holdings
                )
            )
            mf_value = sum(
                hp["current_value"]
                for hp in pnl_data["holdings_pnl"]
                if any(
                    h["name"] == hp["name"] and h["type"] == "mutual_fund"
                    for h in holdings
                )
            )

            if total_value > 0:
                current_stock_pct = (stock_value / total_value) * 100
                current_mf_pct = (mf_value / total_value) * 100

                rc1, rc2 = st.columns(2)
                target_stock = rc1.slider(
                    "Target Stock Allocation %", 0, 100, 60, key="target_stock_pct"
                )
                target_mf = rc2.slider(
                    "Target MF Allocation %",
                    0,
                    100,
                    100 - target_stock,
                    key="target_mf_pct",
                )

                rb1, rb2, rb3, rb4 = st.columns(4)
                rb1.metric(
                    "Current Stocks",
                    f"{current_stock_pct:.0f}%",
                    f"₹{stock_value:,.0f}",
                )
                rb2.metric(
                    "Target Stocks",
                    f"{target_stock}%",
                    f"₹{total_value * target_stock / 100:,.0f}",
                )
                rb3.metric("Current MFs", f"{current_mf_pct:.0f}%", f"₹{mf_value:,.0f}")
                rb4.metric(
                    "Target MFs",
                    f"{target_mf}%",
                    f"₹{total_value * target_mf / 100:,.0f}",
                )

                stock_diff = (total_value * target_stock / 100) - stock_value
                mf_diff = (total_value * target_mf / 100) - mf_value

                if abs(stock_diff) > 1000 or abs(mf_diff) > 1000:
                    st.markdown("**Trades needed to rebalance:**")
                    if stock_diff > 1000:
                        st.markdown(f"📈 **Buy** ₹{stock_diff:,.0f} more in stocks")
                    elif stock_diff < -1000:
                        st.markdown(f"📉 **Sell** ₹{abs(stock_diff):,.0f} from stocks")
                    if mf_diff > 1000:
                        st.markdown(f"📈 **Buy** ₹{mf_diff:,.0f} more in mutual funds")
                    elif mf_diff < -1000:
                        st.markdown(
                            f"📉 **Sell** ₹{abs(mf_diff):,.0f} from mutual funds"
                        )
                else:
                    st.success(
                        "✅ Portfolio is already well-balanced for your target allocation!"
                    )

        st.divider()

        # =====================================================================
        # Export (CSV / JSON / PDF)
        # =====================================================================
        st.subheader("📥 Export Data")
        exp_cols = st.columns(3)

        with exp_cols[0]:
            if st.button("📄 Download PDF Report"):
                with st.spinner("Generating PDF..."):
                    pdf_bytes = generate_portfolio_pdf(holdings, pnl_data)
                    if pdf_bytes:
                        st.download_button(
                            "⬇️ Download PDF",
                            data=pdf_bytes,
                            file_name=f"portfolio_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                        )

        with exp_cols[1]:
            if pnl_data:
                csv_rows = []
                for hp in pnl_data["holdings_pnl"]:
                    h_match = {h["name"]: h for h in holdings}.get(hp["name"], {})
                    csv_rows.append(
                        {
                            "Name": hp["name"],
                            "Type": hp["type"],
                            "Invested": hp["invested"],
                            "Current Value": hp["current_value"],
                            "P&L": hp["pnl"],
                            "Return %": hp["pnl_pct"],
                            "Daily Change %": hp["daily_change_pct"],
                            "Tax Status": (
                                "LTCG"
                                if h_match.get("is_ltcg")
                                else (
                                    "STCG" if h_match.get("is_ltcg") is not None else ""
                                )
                            ),
                        }
                    )
                csv_df = pd.DataFrame(csv_rows)
                csv_buffer = io.StringIO()
                csv_df.to_csv(csv_buffer, index=False)
                st.download_button(
                    "📊 Download CSV",
                    data=csv_buffer.getvalue(),
                    file_name=f"portfolio_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )

        with exp_cols[2]:
            if pnl_data:
                export_data = {
                    "generated": datetime.now().isoformat(),
                    "summary": {
                        "total_invested": pnl_data["total_invested"],
                        "total_current": pnl_data["total_current"],
                        "total_pnl": pnl_data["total_pnl"],
                        "total_pnl_pct": pnl_data["total_pnl_pct"],
                        "xirr": pnl_data.get("xirr"),
                    },
                    "holdings": pnl_data["holdings_pnl"],
                }
                st.download_button(
                    "📋 Download JSON",
                    data=json.dumps(export_data, indent=2, default=str),
                    file_name=f"portfolio_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json",
                )
