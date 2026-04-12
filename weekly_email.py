"""
Weekly summary email — sends a recap every Sunday via SMTP.
Can also be triggered manually: python weekly_email.py

Requires these environment variables:
  EMAIL_FROM     — sender email (e.g. yourname@gmail.com)
  EMAIL_PASSWORD — app password (NOT your main password)
  EMAIL_TO       — recipient email
  EMAIL_SMTP     — SMTP server (default: smtp.gmail.com)
  EMAIL_PORT     — SMTP port (default: 587)
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import yfinance as yf

from analysis import (
    load_portfolio_extended,
    analyze_portfolio,
    fetch_news,
    scan_top_movers,
    scan_oversold_opportunities,
)


def _metal_price_inr(ticker, premium=1.03):
    """Get metal price in INR/gram with weekly change."""
    try:
        metal = yf.Ticker(ticker)
        fx = yf.Ticker("USDINR=X")
        m_hist = metal.history(period="2wk")
        f_hist = fx.history(period="2wk")
        if m_hist.empty or f_hist.empty:
            return None, None

        common = m_hist.index.intersection(f_hist.index)
        m_c = m_hist.loc[common, "Close"]
        f_c = f_hist.loc[common, "Close"]
        inr_g = (m_c * f_c) / 31.1035 * premium

        current = round(inr_g.iloc[-1], 2)
        week_ago = (
            round(inr_g.iloc[-6], 2) if len(inr_g) >= 6 else round(inr_g.iloc[0], 2)
        )
        change = round(((current - week_ago) / week_ago) * 100, 2)
        return current, change
    except Exception:
        return None, None


def build_weekly_html():
    """Build a concise HTML email with only key highlights."""
    today = datetime.now()
    week_start = (today - timedelta(days=7)).strftime("%d %b")
    week_end = today.strftime("%d %b %Y")

    # --- Market ---
    nifty_price, nifty_wk = None, None
    try:
        n = yf.Ticker("^NSEI").history(period="2wk")
        if len(n) >= 6:
            nifty_price = round(n["Close"].iloc[-1], 2)
            nifty_wk = round(
                ((n["Close"].iloc[-1] - n["Close"].iloc[-6]) / n["Close"].iloc[-6])
                * 100,
                2,
            )
    except Exception:
        pass

    # --- Metals ---
    gold_g, gold_wk = _metal_price_inr("GC=F", 1.03)
    silver_g, silver_wk = _metal_price_inr("SI=F", 1.05)

    # --- Portfolio ---
    holdings = load_portfolio_extended()
    results = analyze_portfolio(holdings) if holdings else []

    # --- Top movers ---
    try:
        gainers, losers = scan_top_movers(top_n=3)
    except Exception:
        gainers, losers = [], []

    # --- Oversold ---
    try:
        opps = scan_oversold_opportunities()
    except Exception:
        opps = []

    # --- News ---
    try:
        news = fetch_news(max_items=3)
    except Exception:
        news = []

    # --- BUILD HTML ---
    def _color(val):
        if val is None:
            return "#666"
        return "#27ae60" if val >= 0 else "#e74c3c"

    def _arrow(val):
        if val is None:
            return ""
        return "▲" if val >= 0 else "▼"

    html = f"""
    <html><body style="font-family: -apple-system, Arial, sans-serif; max-width: 600px; margin: auto; padding: 16px;">
    <div style="background: #1a1a2e; color: white; padding: 16px 20px; border-radius: 10px 10px 0 0;">
        <h2 style="margin:0;">📊 Weekly Recap</h2>
        <p style="margin:4px 0 0; opacity:0.7; font-size:14px;">{week_start} — {week_end}</p>
    </div>

    <div style="background: white; padding: 16px 20px; border-radius: 0 0 10px 10px;">

    <table style="width:100%; border-collapse:collapse; margin-bottom:16px;">
        <tr style="border-bottom:1px solid #eee;">
            <td style="padding:6px;"><b>Nifty 50</b></td>
            <td style="padding:6px; text-align:right;">₹{nifty_price:,.0f}</td>
            <td style="padding:6px; text-align:right; color:{_color(nifty_wk)};">{_arrow(nifty_wk)} {nifty_wk:+.1f}%</td>
        </tr>
        <tr style="border-bottom:1px solid #eee;">
            <td style="padding:6px;"><b>Gold</b></td>
            <td style="padding:6px; text-align:right;">₹{gold_g:,.0f}/g</td>
            <td style="padding:6px; text-align:right; color:{_color(gold_wk)};">{_arrow(gold_wk)} {gold_wk:+.1f}%</td>
        </tr>
        <tr>
            <td style="padding:6px;"><b>Silver</b></td>
            <td style="padding:6px; text-align:right;">₹{silver_g:,.0f}/g</td>
            <td style="padding:6px; text-align:right; color:{_color(silver_wk)};">{_arrow(silver_wk)} {silver_wk:+.1f}%</td>
        </tr>
    </table>
    """

    # --- Holdings: only show alerts (big moves, oversold, overbought) ---
    holding_alerts = []
    for r in results:
        a = r["analysis"]
        h = r["holding"]
        if a is None:
            continue
        name = h["name"]
        # Weekly change
        try:
            t = yf.Ticker(h["ticker"])
            wk_hist = t.history(period="2wk")
            wk_chg = (
                round(
                    (
                        (wk_hist["Close"].iloc[-1] - wk_hist["Close"].iloc[-6])
                        / wk_hist["Close"].iloc[-6]
                    )
                    * 100,
                    1,
                )
                if len(wk_hist) >= 6
                else None
            )
        except Exception:
            wk_chg = None

        # Only show if something notable happened
        if wk_chg is not None and abs(wk_chg) >= 3:
            direction = "up" if wk_chg > 0 else "down"
            color = _color(wk_chg)
            holding_alerts.append(
                f'<li><b>{name}</b> — <span style="color:{color};">{wk_chg:+.1f}% this week</span></li>'
            )
        if a["rsi"] is not None and a["rsi"] <= 30:
            holding_alerts.append(
                f"<li>🟢 <b>{name}</b> is oversold — could be a buying opportunity</li>"
            )
        if a["rsi"] is not None and a["rsi"] >= 70:
            holding_alerts.append(
                f"<li>⚠️ <b>{name}</b> is overbought — consider booking profits</li>"
            )
        if a["crossover"]:
            cross_type = "positive" if "Golden" in str(a["crossover"]) else "negative"
            holding_alerts.append(
                f"<li>🚨 <b>{name}</b> — trend turning {cross_type}</li>"
            )

    if holding_alerts:
        html += "<h3>⚡ Your Holdings — Key Alerts</h3><ul>"
        html += "".join(holding_alerts)
        html += "</ul>"
    else:
        html += '<p style="color:#666;">✅ Your holdings had a quiet week — nothing unusual.</p>'

    # --- Top Movers: just top 2 each ---
    if gainers or losers:
        html += "<h3>🚀 Biggest Moves</h3>"
        html += '<table style="width:100%; border-collapse:collapse;">'
        for g in gainers[:2]:
            html += f'<tr style="border-bottom:1px solid #eee;"><td style="padding:4px;">🟢 {g["name"]}</td><td style="text-align:right; padding:4px; color:#27ae60;">{g["change_pct"]:+.2f}%</td></tr>'
        for l in losers[:2]:
            html += f'<tr style="border-bottom:1px solid #eee;"><td style="padding:4px;">🔴 {l["name"]}</td><td style="text-align:right; padding:4px; color:#e74c3c;">{l["change_pct"]:+.2f}%</td></tr>'
        html += "</table>"

    # --- Buy Opportunities: only strong signals ---
    strong_opps = [o for o in opps if o.get("urgency") == "high"]
    if strong_opps:
        html += "<h3>💡 Worth Buying</h3><ul>"
        for o in strong_opps[:3]:
            html += f'<li><b>{o["name"]}</b> — ₹{o["price"]:,.0f} — {o.get("buy_verdict", "")}</li>'
        html += "</ul>"

    # --- News: 3 headlines max ---
    if news:
        icons = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}
        html += "<h3>📰 Headlines</h3><ul style='padding-left:16px;'>"
        for item in news[:3]:
            icon = icons.get(item["sentiment"], "⚪")
            html += f'<li>{icon} {item["title"][:70]}</li>'
        html += "</ul>"

    html += """
    <hr style="border:none; border-top:1px solid #eee; margin:16px 0;">
    <p style="color:#999; font-size:11px;">Finance Bot • Data: Yahoo Finance & AMFI India</p>
    </div></body></html>
    """
    return html


def send_weekly_email():
    """Send the weekly summary email."""
    email_from = os.getenv("EMAIL_FROM")
    email_pass = os.getenv("EMAIL_PASSWORD")
    email_to = os.getenv("EMAIL_TO")
    smtp_server = os.getenv("EMAIL_SMTP", "smtp.gmail.com")
    smtp_port = int(os.getenv("EMAIL_PORT", "587"))

    if not all([email_from, email_pass, email_to]):
        print("⚠️  Missing email credentials. Set EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO.")
        # Save HTML preview locally
        html = build_weekly_html()
        preview_path = "data/weekly_preview.html"
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"📄 Preview saved to {preview_path}")
        return

    html = build_weekly_html()

    msg = MIMEMultipart("alternative")
    today = datetime.now().strftime("%d %b %Y")
    msg["Subject"] = f"📊 Weekly Finance Recap — {today}"
    msg["From"] = email_from
    msg["To"] = email_to
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(email_from, email_pass)
        server.sendmail(email_from, email_to, msg.as_string())

    print("✅ Weekly email sent!")


if __name__ == "__main__":
    send_weekly_email()
