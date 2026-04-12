import os
import csv
from datetime import datetime
import yfinance as yf
from twilio.rest import Client
from analysis import (
    load_portfolio_extended,
    analyze_portfolio,
    analyze_gold_trend,
    get_silver_price,
    analyze_silver_trend,
    fetch_news,
    scan_top_movers,
    scan_oversold_opportunities,
    fetch_mf_nav_batch,
    compute_diversification,
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
    """Fetch gold price in INR per gram (international gold converted via USD/INR).
    Chennai gold ≈ international price + ~3% premium (GST + making).
    """
    try:
        gold = yf.Ticker("GC=F")  # Gold futures USD/troy oz
        usd_inr = yf.Ticker("USDINR=X")

        gold_data = gold.history(period="5d")
        fx_data = usd_inr.history(period="5d")

        if gold_data.empty or fx_data.empty:
            return None

        gold_usd = gold_data["Close"].iloc[-1]
        rate = fx_data["Close"].iloc[-1]

        # 1 troy ounce = 31.1035 grams
        gold_inr_per_gram = (gold_usd * rate) / 31.1035
        # ~3% premium for Chennai retail (GST + making charges)
        chennai_per_gram = gold_inr_per_gram * 1.03

        # Calculate daily change
        change_pct = None
        if len(gold_data) >= 2 and len(fx_data) >= 2:
            prev_gold = gold_data["Close"].iloc[-2]
            prev_fx = fx_data["Close"].iloc[-2]
            prev_per_gram = (prev_gold * prev_fx) / 31.1035 * 1.03
            change_pct = round(
                ((chennai_per_gram - prev_per_gram) / prev_per_gram) * 100, 2
            )

        return {
            "per_gram": round(chennai_per_gram, 2),
            "per_8gram": round(chennai_per_gram * 8, 2),
            "change_pct": change_pct,
        }
    except Exception:
        return None


# --- Portfolio ---


def load_portfolio(path="data/portfolio.csv"):
    """Load portfolio from CSV (supports both old and new format)."""
    return load_portfolio_extended(path)


# --- Smart Features ---


def sip_reminder(portfolio=None):
    """Remind about SIPs on their due dates. Reads from portfolio.csv."""
    if not portfolio:
        return ""
    today = datetime.now().day
    reminders = []
    for h in portfolio:
        sip_date = h.get("sip_date", 0)
        sip_amount = h.get("sip_monthly", 0)
        if sip_date and sip_amount and int(sip_date) == today:
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

    change_str = f" ({change:+.2f}%)" if change is not None else ""

    parts = [
        f"📅 {today} — Daily Update",
        f"",
        f"📊 Nifty 50: {nifty}{change_str}",
    ]

    # Gold — just price and direction
    if gold:
        g_change = (
            f" ({gold['change_pct']:+.2f}%)" if gold["change_pct"] is not None else ""
        )
        parts.append(f"🪙 Gold: ₹{gold['per_gram']:,.0f}/g{g_change}")

    # Silver — just price
    silver = get_silver_price()
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

    return "\n".join(part for part in parts if part)


# --- WhatsApp ---


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

    client = Client(sid, auth)
    client.messages.create(
        from_="whatsapp:+14155238886",
        body=msg,
        to=to_number,
    )
    print("✅ WhatsApp message sent!")


if __name__ == "__main__":
    message = generate_message()
    send_whatsapp(message)
