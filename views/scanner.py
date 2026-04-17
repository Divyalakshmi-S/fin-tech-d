import streamlit as st
import pandas as pd
import yfinance as yf

from analysis import (
    scan_top_movers,
    scan_oversold_opportunities,
    scan_sector_performance,
    suggest_stock_swaps,
    save_scanner_suggestion,
    auto_resolve_ticker,
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
    """Fragment — top movers section."""
    st.caption("⏱️ **Short-term** — based on today's price change vs yesterday")
    with st.spinner("Scanning top movers..."):
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
    """Fragment — oversold opportunities scan."""
    st.caption("Stocks that have fallen significantly and could be good buys")
    with st.spinner("Scanning for cheap stocks..."):
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
def _sell_replace_fragment(holdings):
    """Fragment — sell & replace section re-runs independently."""
    st.caption("Want to sell a stock? See what you could buy instead with that money.")

    try:
        swap_holdings = holdings or []
        stock_holdings = [
            h for h in swap_holdings if h["type"] == "stock" and h.get("ticker")
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
    """Fragment — sector scan."""
    st.caption("⏱️ **Short-term** — today's average change across stocks in each sector")
    with st.spinner("Scanning sectors..."):
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


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_watchlist_data(tickers_tuple):
    """Fetch live data for watchlist tickers."""
    results = []
    for ticker in tickers_tuple:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if hist.empty or len(hist) < 2:
                continue
            price = round(hist["Close"].iloc[-1], 2)
            prev = round(hist["Close"].iloc[-2], 2)
            chg = round(((price - prev) / prev) * 100, 2)
            vol = hist["Volume"].iloc[-1]
            avg_vol = hist["Volume"].mean()
            vol_ratio = round(vol / avg_vol, 1) if avg_vol > 0 else 1.0
            info = t.info or {}
            results.append(
                {
                    "ticker": ticker,
                    "name": info.get("shortName", ticker.replace(".NS", "")),
                    "price": price,
                    "change_pct": chg,
                    "vol_ratio": vol_ratio,
                    "pe": info.get("trailingPE"),
                    "sector": info.get("sector", ""),
                }
            )
        except Exception:
            continue
    return results


@st.fragment()
def _watchlist_fragment():
    """Fragment — watchlist tracker with custom tickers."""
    st.caption("Track stocks you're interested in but haven't bought yet")

    # Initialize watchlist in session state
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = []

    # Add stock by name
    wc1, wc2 = st.columns([3, 1])
    with wc1:
        stock_name = st.text_input(
            "Add stock (e.g. Reliance, TCS, Infosys)",
            placeholder="Reliance",
            key="watchlist_input",
        )
    with wc2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Add", key="watchlist_add") and stock_name.strip():
            if len(st.session_state["watchlist"]) >= 20:
                st.warning("Watchlist limited to 20 stocks.")
            else:
                with st.spinner(f"Finding {stock_name.strip()}..."):
                    result = auto_resolve_ticker(stock_name.strip(), "stock")
                if result["ticker"] and not result["error"]:
                    ticker = result["ticker"]
                    if ticker not in st.session_state["watchlist"]:
                        st.session_state["watchlist"].append(ticker)
                        st.rerun()
                    else:
                        st.info(f"{result['name']} is already in your watchlist.")
                else:
                    st.error(
                        f"Could not find '{stock_name.strip()}'. Try a different name."
                    )

    # Quick add popular stocks
    popular = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS"]
    not_added = [t for t in popular if t not in st.session_state["watchlist"]]
    if not_added:
        st.caption("Quick add:")
        qcols = st.columns(len(not_added))
        for qc, ticker in zip(qcols, not_added):
            if qc.button(ticker.replace(".NS", ""), key=f"qa_{ticker}"):
                st.session_state["watchlist"].append(ticker)
                st.rerun()

    # Display watchlist
    watchlist = st.session_state["watchlist"]
    if watchlist:
        with st.spinner("Fetching watchlist data..."):
            wl_data = _fetch_watchlist_data(tuple(watchlist))

        if wl_data:
            wl_rows = []
            for w in wl_data:
                icon = "🟢" if w["change_pct"] >= 0 else "🔴"
                vol_tag = "🔥" if w["vol_ratio"] >= 2 else ""
                pe_str = f"{w['pe']:.1f}" if w["pe"] else "—"
                wl_rows.append(
                    {
                        "": icon,
                        "Name": w["name"],
                        "Price": f"₹{w['price']:,.2f}",
                        "Change": f"{w['change_pct']:+.2f}%",
                        "Volume": f"{vol_tag}{w['vol_ratio']}x",
                        "PE": pe_str,
                        "Sector": w["sector"],
                    }
                )
            st.dataframe(pd.DataFrame(wl_rows), hide_index=True, width="stretch")

        # Remove buttons
        st.caption("Remove from watchlist:")
        rem_cols = st.columns(min(len(watchlist), 5))
        for i, ticker in enumerate(watchlist):
            col = rem_cols[i % len(rem_cols)]
            if col.button(f"❌ {ticker.replace('.NS', '')}", key=f"rem_{ticker}"):
                st.session_state["watchlist"].remove(ticker)
                st.rerun()
    else:
        st.info("Your watchlist is empty. Add tickers above to start tracking.")


def render(holdings):
    st.title("🔎 Market Opportunity Scanner")

    scan_tab1, scan_tab2, scan_tab3, scan_tab4, scan_tab5 = st.tabs(
        [
            "🚀 Top Movers",
            "💡 What Should I Buy?",
            "🔄 Sell & Replace",
            "🏭 Sector Heatmap",
            "👀 Watchlist",
        ]
    )

    with scan_tab1:
        _top_movers_fragment()

    with scan_tab2:
        _cheap_stocks_fragment(holdings)

    with scan_tab3:
        _sell_replace_fragment(holdings)

    with scan_tab4:
        _sector_heatmap_fragment()

    with scan_tab5:
        _watchlist_fragment()
