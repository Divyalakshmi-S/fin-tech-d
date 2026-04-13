import streamlit as st

from analysis import fetch_news


def render(holdings):
    st.title("📰 Market News — Quick Summary")
    st.caption(
        "Key headlines with short takeaways so you don't have to read everything"
    )

    news_tab1, news_tab2, news_tab3, news_tab4 = st.tabs(
        ["📊 Stocks", "🪙 Gold", "📈 Mutual Funds", "💡 Opportunities"]
    )

    categories = {
        "📊 Stocks": "Indian Stock Market",
        "🪙 Gold": "Gold Price India",
        "📈 Mutual Funds": "Mutual Funds India",
        "💡 Opportunities": "Investment Opportunities",
    }

    sentiment_labels = {
        "bullish": ("🟢", "Positive for markets"),
        "bearish": ("🔴", "Negative for markets"),
        "neutral": ("⚪", "Neutral"),
    }

    # Pre-fetch all categories once and reuse
    cached_news = {}
    for label, category in categories.items():
        try:
            cached_news[category] = fetch_news(category=category, max_items=8)
        except Exception:
            cached_news[category] = []

    for tab, (label, category) in zip(
        [news_tab1, news_tab2, news_tab3, news_tab4], categories.items()
    ):
        with tab:
            try:
                news_items = cached_news.get(category, [])
                if news_items:
                    # Quick sentiment summary at top
                    bull = sum(1 for n in news_items if n["sentiment"] == "bullish")
                    bear = sum(1 for n in news_items if n["sentiment"] == "bearish")
                    neutral = len(news_items) - bull - bear

                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("🟢 Positive", f"{bull} stories")
                    sc2.metric("🔴 Negative", f"{bear} stories")
                    sc3.metric("⚪ Neutral", f"{neutral} stories")

                    if bull > bear:
                        st.success(
                            "Overall mood: **Positive** — more good news than bad today"
                        )
                    elif bear > bull:
                        st.warning(
                            "Overall mood: **Negative** — more concerning news today"
                        )
                    else:
                        st.info(
                            "Overall mood: **Mixed** — no clear direction in the news"
                        )

                    st.divider()

                    for item in news_items:
                        icon, mood = sentiment_labels.get(
                            item["sentiment"], ("⚪", "Neutral")
                        )
                        summary = item.get("summary", "")

                        with st.container():
                            st.markdown(f"**{icon} {item['title']}**")
                            if summary:
                                st.caption(f"📝 {summary}")
                            col_link, col_mood = st.columns([3, 1])
                            with col_link:
                                pub = item.get("published", "")
                                if pub:
                                    st.caption(f"🕐 {pub}")
                            with col_mood:
                                st.caption(f"Mood: {mood}")
                            link = item.get("link", "")
                            if link and link.startswith("https://"):
                                st.markdown(f"[Read full article →]({link})")
                            st.markdown("---")
                else:
                    st.caption("No news available")
            except Exception:
                st.caption("Could not fetch news")

    # --- What Should I Do? section ---
    st.divider()
    st.subheader("🧭 What Should I Do Next?")
    st.caption("Suggestions based on today's news and your portfolio")

    try:
        # Reuse cached news from tabs above
        all_news = []
        for cat_query in categories.values():
            all_news.extend(cached_news.get(cat_query, [])[:5])

        total_bull = sum(1 for n in all_news if n["sentiment"] == "bullish")
        total_bear = sum(1 for n in all_news if n["sentiment"] == "bearish")
        news_titles_lower = " ".join(n["title"].lower() for n in all_news)

        suggestions = []

        # 1. Overall market mood → action
        if total_bear > total_bull + 3:
            suggestions.append(
                (
                    "🛡️",
                    "**Don't panic sell** — News is mostly negative today. Avoid making emotional decisions. If you have cash, this could be a buying opportunity for quality stocks.",
                )
            )
        elif total_bull > total_bear + 3:
            suggestions.append(
                (
                    "📈",
                    "**Markets look positive** — Good time to review your portfolio and consider adding to your winners. But don't chase prices that have already run up too much.",
                )
            )
        else:
            suggestions.append(
                (
                    "⏳",
                    "**Stay patient** — News is mixed today. No rush to buy or sell. Stick to your plan and wait for a clearer signal.",
                )
            )

        # --- Dynamic portfolio-matched suggestions ---
        # Build keyword → holdings mapping from actual portfolio
        if holdings:
            total_invested = sum(h["amount"] for h in holdings)

            # Map sector/keyword patterns to holdings
            keyword_map = {
                "gold": {
                    "keywords": [
                        "gold",
                        "yellow metal",
                        "precious metal",
                        "gold price",
                    ],
                    "rise_keywords": [
                        "gold rise",
                        "gold surge",
                        "gold high",
                        "gold rally",
                        "gold record",
                    ],
                    "fall_keywords": [
                        "gold fall",
                        "gold drop",
                        "gold crash",
                        "gold dip",
                        "gold decline",
                    ],
                    "icon": "🪙",
                    "sector": "gold",
                },
                "silver": {
                    "keywords": ["silver", "silver price"],
                    "rise_keywords": [
                        "silver rise",
                        "silver surge",
                        "silver high",
                        "silver rally",
                    ],
                    "fall_keywords": [
                        "silver fall",
                        "silver drop",
                        "silver crash",
                        "silver dip",
                    ],
                    "icon": "🥈",
                    "sector": "silver",
                },
                "auto": {
                    "keywords": [
                        "tata motors",
                        "auto",
                        "automobile",
                        "car sales",
                        "ev",
                        "maruti",
                        "mahindra",
                    ],
                    "icon": "🚗",
                    "sector": "auto",
                },
                "banking": {
                    "keywords": [
                        "bank",
                        "rbi",
                        "interest rate",
                        "rate cut",
                        "npa",
                        "credit",
                        "hdfc",
                        "icici",
                        "sbi",
                        "idfc",
                    ],
                    "icon": "🏦",
                    "sector": "banking",
                },
                "it": {
                    "keywords": [
                        "tcs",
                        "infosys",
                        "it sector",
                        "tech stock",
                        "wipro",
                        "hcl tech",
                    ],
                    "icon": "💻",
                    "sector": "it",
                },
                "mf": {
                    "keywords": [
                        "mutual fund",
                        "sip",
                        "nav",
                        "amfi",
                        "small cap",
                        "nifty",
                        "index fund",
                    ],
                    "icon": "📊",
                    "sector": "mf",
                },
                "energy": {
                    "keywords": [
                        "oil",
                        "ongc",
                        "reliance",
                        "energy",
                        "crude",
                        "petrol",
                        "gas",
                    ],
                    "icon": "⛽",
                    "sector": "energy",
                },
            }

            # Find which holdings match each sector
            def _find_holdings_for_sector(sector_key):
                """Find portfolio holdings related to a sector."""
                matches = []
                sector_tickers = {
                    "gold": ["goldbees", "gold"],
                    "silver": ["silverbees", "silver"],
                    "auto": ["tmcv", "tmpv", "tata motor", "maruti", "m&m"],
                    "banking": [
                        "bank",
                        "idfc",
                        "hdfc",
                        "icici",
                        "sbi",
                        "kotak",
                        "axis",
                    ],
                    "it": ["tcs", "infy", "hcl", "wipro", "techm", "infosys"],
                    "mf": [],  # handled separately via type
                    "energy": ["ongc", "reliance", "ntpc", "power", "coal"],
                }
                patterns = sector_tickers.get(sector_key, [])
                for h in holdings:
                    name_lower = h["name"].lower()
                    ticker_lower = (h.get("ticker") or "").lower()
                    if sector_key == "mf" and h["type"] == "mutual_fund":
                        matches.append(h)
                    elif any(p in name_lower or p in ticker_lower for p in patterns):
                        matches.append(h)
                return matches

            for sector_key, config in keyword_map.items():
                if not any(kw in news_titles_lower for kw in config["keywords"]):
                    continue

                matched = _find_holdings_for_sector(sector_key)
                icon = config["icon"]

                if matched:
                    names = ", ".join(
                        f"{h['name']} (₹{h['amount']:,.0f})" for h in matched[:3]
                    )
                    total_sector = sum(h["amount"] for h in matched)
                    pct = (total_sector / total_invested) * 100

                    # Check if it's rise or fall news for gold/silver
                    if "rise_keywords" in config and any(
                        kw in news_titles_lower for kw in config["rise_keywords"]
                    ):
                        if pct > 15:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} is rising** — You hold {names} ({pct:.0f}% of portfolio). Consider booking partial profits on your larger positions.",
                                )
                            )
                        else:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} is rising** — You hold {names}. Good news for your positions — hold and let gains grow.",
                                )
                            )
                    elif "fall_keywords" in config and any(
                        kw in news_titles_lower for kw in config["fall_keywords"]
                    ):
                        if total_sector < 2000:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} is dipping** — You hold {names}. Your position is small — could be a good time to add more at lower prices.",
                                )
                            )
                        else:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} is dipping** — You hold {names}. Watch closely — if fundamentals are strong, this dip is a buying opportunity.",
                                )
                            )
                    else:
                        # General news about sector
                        if sector_key == "mf":
                            sip_holdings = [
                                h for h in matched if h.get("sip_monthly", 0) > 0
                            ]
                            if sip_holdings:
                                sip_names = ", ".join(
                                    f"{h['name']} ₹{int(h['sip_monthly']):,}/month"
                                    for h in sip_holdings
                                )
                                suggestions.append(
                                    (
                                        icon,
                                        f"**Mutual fund news** — Your SIPs: {sip_names}. Continue regardless of short-term news — SIPs benefit from market dips.",
                                    )
                                )
                            else:
                                suggestions.append(
                                    (
                                        icon,
                                        f"**Mutual fund news** — You hold {names}. Consider starting a monthly SIP for consistent investing.",
                                    )
                                )
                        else:
                            suggestions.append(
                                (
                                    icon,
                                    f"**{sector_key.title()} sector news** — You hold {names} ({pct:.0f}% of portfolio). Check the news tab for details on how this affects your holdings.",
                                )
                            )
                else:
                    # User doesn't own this sector
                    if sector_key not in (
                        "mf",
                    ):  # Only suggest buying for stock sectors
                        suggestions.append(
                            (
                                icon,
                                f"**{sector_key.title()} sector news** — You don't own {sector_key} stocks. If news is negative and prices drop, it could be a buying opportunity.",
                            )
                        )

            # General diversification check
            top_holding = max(holdings, key=lambda h: h["amount"])
            top_pct = (top_holding["amount"] / total_invested) * 100
            if top_pct > 50:
                suggestions.append(
                    (
                        "⚖️",
                        f"**Diversify** — {top_holding['name']} is {top_pct:.0f}% of your portfolio. Regardless of news, consider spreading across more stocks or funds.",
                    )
                )

        if not suggestions:
            suggestions.append(
                (
                    "✅",
                    "**All good** — No major news affecting your portfolio today. Continue your SIPs and review again next week.",
                )
            )

        for icon, text in suggestions:
            st.markdown(f"{icon} {text}")
            st.markdown("")

    except Exception:
        st.info("Could not generate suggestions. Check back when markets are open.")
