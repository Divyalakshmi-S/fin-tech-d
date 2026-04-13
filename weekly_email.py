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
    calculate_portfolio_pnl,
    fetch_news,
    scan_top_movers,
    scan_oversold_opportunities,
    metal_price_inr_weekly,
    load_goals,
    calculate_goal_progress,
    calculate_sip_for_goal,
)


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
    gold_g, gold_wk = metal_price_inr_weekly("GC=F")
    silver_g, silver_wk = metal_price_inr_weekly("SI=F")

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

    def _fmt(val, fmt=",.0f"):
        """Safe format — returns 'N/A' if val is None."""
        if val is None:
            return "N/A"
        return format(val, fmt)

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
            <td style="padding:6px; text-align:right;">₹{_fmt(nifty_price)}</td>
            <td style="padding:6px; text-align:right; color:{_color(nifty_wk)};">{_arrow(nifty_wk)} {f'{nifty_wk:+.1f}%' if nifty_wk is not None else 'N/A'}</td>
        </tr>
        <tr style="border-bottom:1px solid #eee;">
            <td style="padding:6px;"><b>Gold</b></td>
            <td style="padding:6px; text-align:right;">₹{_fmt(gold_g)}/g</td>
            <td style="padding:6px; text-align:right; color:{_color(gold_wk)};">{_arrow(gold_wk)} {f'{gold_wk:+.1f}%' if gold_wk is not None else 'N/A'}</td>
        </tr>
        <tr>
            <td style="padding:6px;"><b>Silver</b></td>
            <td style="padding:6px; text-align:right;">₹{_fmt(silver_g)}/g</td>
            <td style="padding:6px; text-align:right; color:{_color(silver_wk)};">{_arrow(silver_wk)} {f'{silver_wk:+.1f}%' if silver_wk is not None else 'N/A'}</td>
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

    # --- Portfolio P&L ---
    try:
        pnl_data = calculate_portfolio_pnl(holdings, results)
        if pnl_data and pnl_data["total_invested"] > 0:
            pnl_color = _color(pnl_data["total_pnl"])
            pnl_arrow = _arrow(pnl_data["total_pnl"])
            html += f"""
            <h3>💰 Portfolio P&amp;L</h3>
            <table style="width:100%; border-collapse:collapse; margin-bottom:16px;">
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:6px;"><b>Invested</b></td>
                    <td style="padding:6px; text-align:right;">₹{pnl_data['total_invested']:,.0f}</td>
                </tr>
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:6px;"><b>Current Value</b></td>
                    <td style="padding:6px; text-align:right;">₹{pnl_data['total_current']:,.0f}</td>
                </tr>
                <tr>
                    <td style="padding:6px;"><b>Returns</b></td>
                    <td style="padding:6px; text-align:right; color:{pnl_color};">
                        {pnl_arrow} ₹{pnl_data['total_pnl']:+,.0f} ({pnl_data['total_pnl_pct']:+.1f}%)</td>
                </tr>
            </table>
            """
    except Exception:
        pass

    # --- Goal Progress ---
    try:
        saved_goals = load_goals()
        if saved_goals and holdings:
            total_invested = sum(h["amount"] for h in holdings)
            monthly_sips = sum(
                h["sip_monthly"] for h in holdings if h["sip_monthly"] > 0
            )
            goal_alerts = []
            for goal in saved_goals:
                g_name = goal.get("name", "Unnamed")
                g_target = goal.get("target", 0)
                g_years = goal.get("years", 10)
                g_return = goal.get("expected_return", 12)
                g_created = goal.get("created_date", "")
                years_remaining = g_years
                if g_created:
                    try:
                        from datetime import datetime as dt_

                        created_dt = dt_.strptime(g_created, "%Y-%m-%d")
                        elapsed = (dt_.now() - created_dt).days / 365.25
                        years_remaining = max(1, round(g_years - elapsed, 1))
                    except Exception:
                        pass
                progress = calculate_goal_progress(
                    total_invested, g_target, years_remaining, monthly_sips, g_return
                )
                if progress:
                    if progress["on_track"]:
                        goal_alerts.append(
                            f'<li>✅ <b>{g_name}</b> — on track ({progress["progress_pct"]:.0f}% done)</li>'
                        )
                    else:
                        needed = calculate_sip_for_goal(
                            progress["remaining"], years_remaining, g_return
                        )
                        extra = needed["monthly_sip"] - monthly_sips if needed else 0
                        goal_alerts.append(
                            f'<li>⚠️ <b>{g_name}</b> — shortfall ₹{progress["shortfall"]:,.0f}. '
                            f"Increase SIP by ~₹{max(extra, 0):,.0f}/mo</li>"
                        )
            if goal_alerts:
                html += "<h3>🎯 Goal Progress</h3><ul>"
                html += "".join(goal_alerts)
                html += "</ul>"
    except Exception:
        pass

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
    try:
        smtp_port = int(os.getenv("EMAIL_PORT", "587"))
    except (ValueError, TypeError):
        smtp_port = 587

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
