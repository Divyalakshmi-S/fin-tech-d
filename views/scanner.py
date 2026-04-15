import streamlit as st
import pandas as pd

from analysis import (
    scan_top_movers,
    scan_oversold_opportunities,
    scan_sector_performance,
    suggest_stock_swaps,
    load_portfolio_extended,
    save_scanner_suggestion,
)


@st.cache_data(ttl=900, show_spinner=False)
def _cached_scan_top_movers(top_n=5):
    """Cached scanner — avoids re-scanning on every page interaction."""
    return scan_top_movers(top_n=top_n)


@st.cache_data(ttl=900, show_spinner=False)
def _cached_scan_oversold():
    """Cached oversold opportunities scan."""
    return scan_oversold_opportunities()


@st.cache_data(ttl=900, show_spinner=False)
def _cached_scan_sectors():
    """Cached sector performance scan."""
    return scan_sector_performance()


@st.fragment()
def _top_movers_fragment():
    """Fragment — only this section re-runs when the scan button is clicked."""
    st.caption("⏱️ **Short-term** — based on today's price change vs yesterday")
    if st.button("🔍 Scan Top Movers", key="scan_movers"):
        try:
            gainers, losers = _cached_scan_top_movers(top_n=5)

            g_col, l_col = st.columns(2)

            with g_col:
                st.subheader("🟢 Top Gainers")
                if gainers:
                    for g in gainers:
                        st.markdown(
                            f"**{g['name']}** — ₹{g['price']:,.2f} `{g['change_pct']:+.2f}%`"
                        )
                        hints = []
                        rsi = g.get("rsi")
                        vol = g.get("vol_ratio")
                        streak = g.get("streak", 0)
                        if rsi and rsi >= 70:
                            hints.append("⚠️ Already overbought — risky to chase")
                        elif rsi and rsi >= 60:
                            hints.append("Getting expensive — be cautious")
                        elif rsi and rsi <= 40:
                            hints.append("Was undervalued — this bounce could continue")
                        if vol and vol >= 2:
                            hints.append(
                                f"Volume {vol}x higher than usual — strong interest"
                            )
                        if streak >= 3:
                            hints.append(
                                f"Up {streak} days in a row — may need a breather"
                            )
                        if hints:
                            st.caption(" · ".join(hints))
                        else:
                            st.caption(
                                "Normal move — watch for a few days before acting"
                            )
                else:
                    st.caption("No data")

            with l_col:
                st.subheader("🔴 Top Losers")
                if losers:
                    for l in losers:
                        st.markdown(
                            f"**{l['name']}** — ₹{l['price']:,.2f} `{l['change_pct']:+.2f}%`"
                        )
                        hints = []
                        rsi = l.get("rsi")
                        vol = l.get("vol_ratio")
                        if rsi and rsi <= 30:
                            hints.append("🟢 Oversold — could bounce back soon")
                        elif rsi and rsi <= 40:
                            hints.append("Getting cheap — watch for reversal")
                        elif rsi and rsi >= 60:
                            hints.append("Was expensive — correction may continue")
                        if vol and vol >= 2:
                            hints.append(f"Volume {vol}x higher — heavy selling")
                        if hints:
                            st.caption(" · ".join(hints))
                        else:
                            st.caption(
                                "Short-term drop — could bounce back or fall further"
                            )
                else:
                    st.caption("No data")
        except Exception as e:
            st.warning(f"Could not scan: {e}")


@st.fragment()
def _cheap_stocks_fragment(holdings):
    """Fragment — oversold opportunities scan re-runs independently."""
    st.caption("Stocks that have fallen significantly and could be good buys")
    if st.button("🔍 Find Cheap Stocks", key="scan_cheap"):
        try:
            opps = _cached_scan_oversold()
            if opps:
                for o in opps:
                    save_scanner_suggestion(o)

                portfolio_by_ticker = {}
                total_portfolio = 0
                if holdings:
                    total_portfolio = sum(h["amount"] for h in holdings)
                    for h in holdings:
                        if h.get("ticker"):
                            portfolio_by_ticker[h["ticker"]] = h

                for o in opps:
                    urgency_colors = {
                        "high": "#27ae60",
                        "medium": "#f39c12",
                        "low": "#95a5a6",
                    }
                    u_color = urgency_colors.get(o["urgency"], "#95a5a6")

                    opp_ticker = o["ticker"]
                    existing = portfolio_by_ticker.get(opp_ticker)
                    own_tag = " · 📌 You own this" if existing else ""

                    with st.expander(
                        f"{'🟢' if o['urgency'] == 'high' else '🟡' if o['urgency'] == 'medium' else '⚪'} "
                        f"**{o['name']}** — ₹{o['price']:,.2f}{own_tag}"
                    ):
                        p1, p2, p3 = st.columns(3)
                        p1.metric("Current Price", f"₹{o['price']:,.2f}")
                        p2.metric(
                            "Yearly High",
                            f"₹{o['high_52w']:,.2f}",
                            f"{o['from_high_pct']:+.1f}%",
                        )
                        p3.metric("Yearly Low", f"₹{o['low_52w']:,.2f}")

                        if existing and total_portfolio > 0:
                            existing_amt = existing["amount"]
                            existing_pct = (existing_amt / total_portfolio) * 100
                            existing_shares = (
                                int(existing_amt / o["price"]) if o["price"] > 0 else 0
                            )
                            max_pct = 15
                            max_amount = total_portfolio * (max_pct / 100)
                            room_to_buy = max(max_amount - existing_amt, 0)
                            additional_shares = (
                                int(room_to_buy / o["price"]) if o["price"] > 0 else 0
                            )

                            own_color = (
                                "#e67e22" if existing_pct >= max_pct else "#3498db"
                            )
                            st.markdown(
                                f"""<div style="border-left: 4px solid {own_color}; padding: 10px 14px; margin: 10px 0;
                                border-radius: 4px; background: {own_color}11;">
                                <strong>📌 You already own {o['name']}</strong>
                                <br>Current holding: <strong>₹{existing_amt:,.0f}</strong> (~{existing_shares} shares · {existing_pct:.1f}% of portfolio)
                                """,
                                unsafe_allow_html=True,
                            )
                            if existing_pct >= max_pct:
                                st.markdown(
                                    f"""<span style="color: #e74c3c;">⚠️ Already at {existing_pct:.0f}% of portfolio — buying more would over-concentrate. Max recommended: {max_pct}%</span>
                                    </div>""",
                                    unsafe_allow_html=True,
                                )
                            elif room_to_buy < o["price"]:
                                st.markdown(
                                    f"""<span style="color: #f39c12;">You're close to the {max_pct}% limit. Room for only ₹{room_to_buy:,.0f} more.</span>
                                    </div>""",
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown(
                                    f"""<span style="color: #27ae60;">✅ Safe to buy up to <strong>{additional_shares} more shares</strong> (₹{room_to_buy:,.0f}) to stay under {max_pct}% allocation</span>
                                    </div>""",
                                    unsafe_allow_html=True,
                                )

                        st.markdown("**Why is it cheap right now?**")
                        for reason in o["why_cheap"]:
                            st.markdown(f"• {reason}")

                        st.markdown(
                            f"""<div style="border-left: 4px solid {u_color}; padding: 10px 14px; margin: 10px 0;
                            border-radius: 4px; background: {u_color}11;">
                            <strong>Should I buy today?</strong> {o['buy_verdict']}
                            <br><span style="font-size: 0.85em; opacity: 0.8;">{' · '.join(o['buy_reasoning'])}</span>
                            </div>""",
                            unsafe_allow_html=True,
                        )

                        opp_risk = o.get("risk_level", "")
                        opp_warn = o.get("risk_warning", "")
                        if opp_warn:
                            risk_color = (
                                "#e74c3c"
                                if opp_risk in ("Very High", "High")
                                else "#f39c12"
                            )
                            st.markdown(
                                f"""<div style="border-left: 4px solid {risk_color}; padding: 8px 12px; margin: 6px 0;
                                border-radius: 4px; background: {risk_color}11; font-size: 0.9em;">
                                <strong>Risk: {opp_risk}</strong> — {opp_warn}
                                </div>""",
                                unsafe_allow_html=True,
                            )

                        if o["pe_ratio"]:
                            pe_hint = (
                                "Cheap"
                                if o["pe_ratio"] < 15
                                else "Fair" if o["pe_ratio"] < 25 else "Expensive"
                            )
                            st.caption(
                                f"Valuation: PE {o['pe_ratio']:.0f}x ({pe_hint}) · Sector: {o['sector'] or 'N/A'}"
                            )
            else:
                st.info(
                    "No cheap stocks found right now — the market looks fairly priced."
                )
        except Exception as e:
            st.warning(f"Error: {e}")


@st.fragment()
def _sell_replace_fragment():
    """Fragment — sell & replace section re-runs independently."""
    st.caption("Want to sell a stock? See what you could buy instead with that money.")

    try:
        swap_holdings = load_portfolio_extended()
        stock_holdings = [
            h for h in swap_holdings if h["type"] == "stock" and h["ticker"]
        ]

        if stock_holdings:
            stock_options = {
                f"{h['name']} (₹{h['amount']:,.0f})": h for h in stock_holdings
            }
            selected = st.selectbox(
                "Which stock do you want to sell?",
                options=list(stock_options.keys()),
                index=None,
                placeholder="Pick a stock from your portfolio...",
            )

            if selected:
                sell_holding = stock_options[selected]
                sell_amount = sell_holding["amount"]

                st.info(
                    f"If you sell **{sell_holding['name']}**, you'll have approximately **₹{sell_amount:,.0f}** to invest elsewhere."
                )

                with st.spinner(
                    f"Finding stocks you can buy with ₹{sell_amount:,.0f}..."
                ):
                    swaps = suggest_stock_swaps(
                        sell_holding["ticker"], sell_amount, swap_holdings
                    )

                    if swaps:
                        st.subheader(f"💡 Stocks you can buy with ₹{sell_amount:,.0f}")

                        for s in swaps[:8]:
                            score_color = (
                                "#27ae60"
                                if s["score"] >= 3
                                else "#f39c12" if s["score"] >= 1 else "#95a5a6"
                            )
                            score_label = (
                                "Strong pick"
                                if s["score"] >= 3
                                else "Decent pick" if s["score"] >= 1 else "Okay"
                            )

                            with st.expander(
                                f"{'🟢' if s['score'] >= 3 else '🟡' if s['score'] >= 1 else '⚪'} "
                                f"**{s['name']}** — ₹{s['price']:,.2f}/share · Buy {s['shares']} shares"
                            ):
                                m1, m2, m3 = st.columns(3)
                                m1.metric("You'd invest", f"₹{s['investment']:,.0f}")
                                m2.metric("Shares you get", f"{s['shares']}")
                                m3.metric("Money left over", f"₹{s['leftover']:,.0f}")

                                if s["pros"]:
                                    st.markdown("**Why this stock?**")
                                    for pro in s["pros"]:
                                        st.markdown(f"✅ {pro}")
                                if s["cons"]:
                                    for con in s["cons"]:
                                        st.markdown(f"⚠️ {con}")

                                extra = []
                                if s["pe_ratio"]:
                                    pe_hint = (
                                        "Cheap"
                                        if s["pe_ratio"] < 15
                                        else (
                                            "Fair"
                                            if s["pe_ratio"] < 25
                                            else "Expensive"
                                        )
                                    )
                                    extra.append(f"PE {s['pe_ratio']:.0f}x ({pe_hint})")
                                if s["sector"]:
                                    extra.append(f"Sector: {s['sector']}")
                                swap_risk = s.get("risk_level", "")
                                if swap_risk:
                                    risk_emoji = (
                                        "🔴"
                                        if swap_risk in ("Very High", "High")
                                        else ("🟡" if swap_risk == "Moderate" else "🟢")
                                    )
                                    extra.append(f"{risk_emoji} Risk: {swap_risk}")
                                if extra:
                                    st.caption(" · ".join(extra))
                    else:
                        st.info(
                            "No good replacement stocks found at this price range right now."
                        )
        else:
            st.info("No stocks in your portfolio to sell.")
    except Exception as e:
        st.warning(f"Could not load portfolio: {e}")


@st.fragment()
def _sector_heatmap_fragment():
    """Fragment — sector scan re-runs independently."""
    st.caption("⏱️ **Short-term** — today's average change across stocks in each sector")
    if st.button("🔍 Scan Sectors", key="scan_sectors"):
        try:
            sector_perf = _cached_scan_sectors()
            if sector_perf:
                chart_data = {s: d["avg_change"] for s, d in sector_perf.items()}
                sorted_chart = dict(
                    sorted(chart_data.items(), key=lambda x: x[1], reverse=True)
                )
                st.bar_chart(pd.Series(sorted_chart, name="Daily Change %"), height=350)

                for sector, data in sector_perf.items():
                    change = data["avg_change"]
                    stocks = data["stocks"]
                    icon = "🟢" if change >= 0 else "🔴"
                    if abs(change) >= 2:
                        strength = "Big move today"
                    elif abs(change) >= 1:
                        strength = "Moderate move"
                    else:
                        strength = "Quiet day"

                    with st.expander(
                        f"{icon} **{sector}**: {change:+.2f}% — {strength}"
                    ):
                        best = stocks[0]
                        worst = stocks[-1]
                        bc, wc = st.columns(2)
                        with bc:
                            st.markdown(f"🟢 **Top Gainer**")
                            st.metric(
                                best["name"],
                                f"₹{best['price']:,.2f}",
                                f"{best['change_pct']:+.2f}%",
                            )
                        with wc:
                            st.markdown(f"🔴 **Top Loser**")
                            st.metric(
                                worst["name"],
                                f"₹{worst['price']:,.2f}",
                                f"{worst['change_pct']:+.2f}%",
                            )

                        if len(stocks) > 2:
                            st.markdown("**All stocks:**")
                            for s in stocks:
                                s_icon = "🟢" if s["change_pct"] >= 0 else "🔴"
                                st.markdown(
                                    f"{s_icon} {s['name']} — ₹{s['price']:,.2f} `{s['change_pct']:+.2f}%`"
                                )
            else:
                st.caption("No sector data")
        except Exception as e:
            st.warning(f"Error: {e}")


def render(holdings):
    st.title("🔎 Market Opportunity Scanner")

    scan_tab1, scan_tab2, scan_tab3, scan_tab4 = st.tabs(
        [
            "🚀 Top Movers",
            "💡 What Should I Buy?",
            "🔄 Sell & Replace",
            "🏭 Sector Heatmap",
        ]
    )

    with scan_tab1:
        _top_movers_fragment()

    with scan_tab2:
        _cheap_stocks_fragment(holdings)

    with scan_tab3:
        _sell_replace_fragment()

    with scan_tab4:
        _sector_heatmap_fragment()
