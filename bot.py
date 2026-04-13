import os
import csv
from datetime import datetime
import yfinance as yf
from twilio.rest import Client
from analysis import (
    load_portfolio_extended,
    analyze_portfolio,
    calculate_portfolio_pnl,
    analyze_gold_trend,
    get_silver_price,
    analyze_silver_trend,
    fetch_news,
    scan_top_movers,
    scan_oversold_opportunities,
    fetch_mf_nav_batch,
    compute_diversification,
    metal_price_inr,
    is_market_open_today,
    load_goals,
    calculate_goal_progress,
    is_sip_currently_paused,
    predict_stock_buy,
)


# --- Data Fetching ---


def get_stock_data():
    """Fetch latest Nifty 50 close price."""
    nifty = yf.Ticker("^NSEI")
    data = nifty.history(period="1d")
    if not data.empty:
        return round(data["Close"].iloc[-1], 2)
    return None


def get_nifty_change():
    """Fetch Nifty 50 daily percentage change."""
    nifty = yf.Ticker("^NSEI")
    data = nifty.history(period="5d")
    if len(data) >= 2:
        prev = data["Close"].iloc[-2]
        curr = data["Close"].iloc[-1]
        return round(((curr - prev) / prev) * 100, 2)
    return None


def get_gold_price():
    """Fetch gold price in INR per gram using consolidated metal_price_inr."""
    return metal_price_inr("GC=F")


# --- Portfolio ---


def load_portfolio():
    """Load portfolio from JSON (user-managed via dashboard forms)."""
    return load_portfolio_extended()


# --- Smart Features ---


def sip_reminder(portfolio=None):
    """Remind about SIPs on their due dates (skip paused SIPs)."""
    if not portfolio:
        return ""
    today = datetime.now().day
    reminders = []
    for h in portfolio:
        sip_date = h.get("sip_date", 0)
        sip_amount = h.get("sip_monthly", 0)
        if sip_date and sip_amount and int(sip_date) == today:
            if is_sip_currently_paused(h):
                reminders.append(
                    f"⏸️ {h['name']} SIP ₹{int(sip_amount):,} is paused. Resume from Manage Portfolio when ready."
                )
            else:
                reminders.append(
                    f"🔔 Reminder: {h['name']} SIP ₹{int(sip_amount):,} due today!"
                )
    return "\n" + "\n".join(reminders) if reminders else ""


def market_suggestion(change):
    """Suggest action based on market movement."""
    if change is None:
        return ""
    if change < -2:
        return "\n📉 Market down significantly — good time to invest!"
    elif change < -1:
        return "\n📉 Market dipped — consider adding positions."
    elif change > 2:
        return "\n📈 Market up big — review your stop-losses."
    return ""


# --- Message ---


def generate_message():
    """Build a concise daily WhatsApp message with only key highlights."""
    today = datetime.now().strftime("%d-%m-%Y")
    nifty = get_stock_data()
    change = get_nifty_change()
    gold = get_gold_price()
    portfolio = load_portfolio()

    # Holiday detection
    market_open = is_market_open_today()

    change_str = f" ({change:+.2f}%)" if change is not None else ""

    parts = [
        f"📅 {today} — Daily Update",
        f"",
    ]

    if market_open is False:
        parts.append("🏖️ Market was closed today (holiday/weekend)")
        parts.append(f"📊 Nifty 50 (last close): {nifty}")
    else:
        parts.append(f"📊 Nifty 50: {nifty}{change_str}")

    # Gold — just price and direction
    if gold:
        g_change = (
            f" ({gold['change_pct']:+.2f}%)" if gold["change_pct"] is not None else ""
        )
        parts.append(f"🪙 Gold: ₹{gold['per_gram']:,.0f}/g{g_change}")

    # Silver — just price
    silver = metal_price_inr("SI=F")
    if silver:
        s_change = (
            f" ({silver['change_pct']:+.2f}%)"
            if silver["change_pct"] is not None
            else ""
        )
        parts.append(f"🥈 Silver: ₹{silver['per_gram']:,.0f}/g{s_change}")

    # Holdings — only show stocks that need attention (alerts)
    analysis_results = analyze_portfolio(portfolio)
    alerts = []
    for r in analysis_results:
        a = r["analysis"]
        if a is None:
            continue
        name = r["holding"]["name"]
        if a["rsi"] is not None and a["rsi"] <= 30:
            alerts.append(
                f"🟢 {name} is oversold (RSI {a['rsi']:.0f}) — consider buying more"
            )
        if a["rsi"] is not None and a["rsi"] >= 70:
            alerts.append(
                f"⚠️ {name} is overbought (RSI {a['rsi']:.0f}) — consider booking profits"
            )
        if a["crossover"]:
            cross_type = "positive" if "Golden" in str(a["crossover"]) else "negative"
            alerts.append(f"🚨 {name} trend turning {cross_type}")
        if a["daily_change_pct"] <= -3:
            alerts.append(f"📉 {name} fell {a['daily_change_pct']:.1f}% today")
        elif a["daily_change_pct"] >= 3:
            alerts.append(f"📈 {name} up {a['daily_change_pct']:.1f}% today")

    if alerts:
        parts.append("")
        parts.append("⚡ Your Holdings:")
        parts.extend(alerts)

    # Stock predictions — signal for each stock holding
    try:
        stock_holdings = [
            h for h in portfolio if h.get("type") == "stock" and h.get("ticker")
        ]
        if stock_holdings:
            pred_lines = []
            for h in stock_holdings[:5]:  # limit to 5 to keep message concise
                pred = predict_stock_buy(h["ticker"], h["name"])
                if pred:
                    sig = pred["signal"]
                    sig_icon = {
                        "BUY": "🟢",
                        "LEAN BUY": "🟡",
                        "WAIT": "⚪",
                        "LEAN SELL": "🟠",
                        "SELL": "🔴",
                    }.get(sig, "⚪")
                    pred_lines.append(
                        f"  {sig_icon} {h['name']}: {sig} ({pred['confidence']}%)"
                    )
            if pred_lines:
                parts.append("")
                parts.append("🔮 Stock Signals:")
                parts.extend(pred_lines)
    except Exception:
        pass

    # Portfolio P&L summary
    try:
        pnl = calculate_portfolio_pnl(portfolio, analysis_results)
        if pnl["total_invested"] > 0:
            sign = "📈" if pnl["total_pnl"] >= 0 else "📉"
            parts.append("")
            parts.append(
                f"{sign} Portfolio: ₹{pnl['total_current']:,.0f} "
                f"({pnl['total_pnl']:+,.0f} | {pnl['total_pnl_pct']:+.1f}%)"
            )
    except Exception:
        pass

    # Top movers — only the top 1 gainer and loser
    try:
        gainers, losers = scan_top_movers(top_n=3)
        if gainers:
            g = gainers[0]
            parts.append(f"\n🚀 Top gainer: {g['name']} {g['change_pct']:+.2f}%")
        if losers:
            l = losers[0]
            parts.append(f"📉 Top loser: {l['name']} {l['change_pct']:+.2f}%")
    except Exception:
        pass

    # Buy opportunities — only if strong signal
    try:
        opps = scan_oversold_opportunities()
        strong = [o for o in opps if o.get("urgency") == "high"]
        if strong:
            parts.append("")
            parts.append("💡 Buy opportunity:")
            for o in strong[:2]:
                parts.append(f"  {o['name']} ₹{o['price']:,.0f} — {o['buy_verdict']}")
    except Exception:
        pass

    # News — only 2 headlines
    try:
        news = fetch_news(max_items=2)
        if news:
            parts.append("")
            icons = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}
            for item in news[:2]:
                icon = icons.get(item["sentiment"], "⚪")
                parts.append(f"{icon} {item['title'][:70]}")
    except Exception:
        pass

    parts.append(sip_reminder(portfolio))
    parts.append(market_suggestion(change))

    # Goal progress alerts — only warn if off-track
    try:
        saved_goals = load_goals()
        if saved_goals and portfolio:
            total_invested = sum(h["amount"] for h in portfolio)
            monthly_sips = sum(
                h["sip_monthly"] for h in portfolio if h["sip_monthly"] > 0
            )
            off_track = []
            for goal in saved_goals:
                g_years = goal.get("years", 10)
                g_created = goal.get("created_date", "")
                years_remaining = g_years
                if g_created:
                    try:
                        created_dt = datetime.strptime(g_created, "%Y-%m-%d")
                        elapsed = (datetime.now() - created_dt).days / 365.25
                        years_remaining = max(1, round(g_years - elapsed, 1))
                    except Exception:
                        pass
                progress = calculate_goal_progress(
                    total_invested,
                    goal.get("target", 0),
                    years_remaining,
                    monthly_sips,
                    goal.get("expected_return", 12),
                )
                if progress and not progress["on_track"]:
                    off_track.append(
                        f"⚠️ {goal['name']}: shortfall ₹{progress['shortfall']:,.0f}"
                    )
            if off_track:
                parts.append("")
                parts.append("🎯 Goals:")
                parts.extend(off_track[:3])
    except Exception:
        pass

    return "\n".join(part for part in parts if part)


# --- WhatsApp via Twilio ---


def send_whatsapp(msg):
    """Send message via Twilio WhatsApp sandbox."""
    sid = os.getenv("TWILIO_SID")
    auth = os.getenv("TWILIO_AUTH")
    to_number = os.getenv("TO_NUMBER")

    if not all([sid, auth, to_number]):
        print("⚠️  Missing Twilio credentials. Set TWILIO_SID, TWILIO_AUTH, TO_NUMBER.")
        print("\n--- Message Preview ---")
        print(msg)
        return

    # WhatsApp has a ~1600 char limit; truncate if needed
    if len(msg) > 1550:
        msg = msg[:1500] + "\n\n... (truncated — see dashboard for full details)"

    try:
        client = Client(sid, auth)
        client.messages.create(
            from_="whatsapp:+14155238886",
            body=msg,
            to=to_number,
        )
        print("✅ WhatsApp message sent!")
    except Exception as e:
        print(f"❌ Twilio error: {e}")
        print("\n--- Message Preview ---")
        print(msg)


if __name__ == "__main__":
    message = generate_message()
    send_whatsapp(message)
