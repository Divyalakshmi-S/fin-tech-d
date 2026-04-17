import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
from html import escape as html_escape


# ---------------------------------------------------------------------------
# Signal map — single source of truth for all prediction displays
# Framed as educational analysis (not investment advice) for SEBI compliance
# ---------------------------------------------------------------------------
SIGNAL_MAP = {
    "BUY": (
        "🟢",
        "#27ae60",
        "Indicators are bullish",
        "Most technical factors favour upside — conditions look favourable",
    ),
    "LEAN BUY": (
        "🟢",
        "#2ecc71",
        "Slightly bullish outlook",
        "Some indicators lean positive — could improve further on a dip",
    ),
    "SELL": (
        "🔴",
        "#e74c3c",
        "Indicators are bearish",
        "Looks stretched — technical signals suggest waiting for a correction",
    ),
    "LEAN SELL": (
        "🟠",
        "#f39c12",
        "Slightly bearish outlook",
        "Mildly unfavourable — momentum may soften in the near term",
    ),
    "WAIT": (
        "🟡",
        "#f1c40f",
        "No clear direction",
        "Mixed signals — review again in a few days",
    ),
}

# ---------------------------------------------------------------------------
# Disclaimer — rendered on every page
# ---------------------------------------------------------------------------
_DISCLAIMER_HTML = """
<div style="position: fixed; bottom: 0; left: 0; right: 0; z-index: 9999;
     background: rgba(30,30,30,0.95); color: #999; font-size: 0.7rem;
     text-align: center; padding: 4px 12px; border-top: 1px solid #444;">
⚠️ <strong>Educational tool only — not investment advice.</strong>
Analysis is based on publicly available data and technical indicators.
Past performance does not guarantee future results. Consult a SEBI-registered
investment adviser before making financial decisions.
</div>
"""


def render_disclaimer():
    """Render the fixed-position compliance disclaimer footer."""
    import streamlit as st

    st.markdown(_DISCLAIMER_HTML, unsafe_allow_html=True)


def metal_inr_series(metal_hist, fx_hist, premium=1.03):
    """Convert metal USD/oz history to INR/gram using forward-filled FX rates.
    Handles weekends/holidays where trading dates don't overlap.
    Calibrates to actual Chennai retail rates from livechennai.com."""
    if metal_hist.empty or fx_hist.empty:
        return None
    combined = pd.DataFrame(
        {
            "metal_usd": metal_hist["Close"],
            "fx": fx_hist["Close"],
        }
    )
    combined["fx"] = combined["fx"].ffill().bfill()
    combined = combined.dropna(subset=["metal_usd"])
    if combined.empty:
        return None
    series = (combined["metal_usd"] * combined["fx"]) / 31.1035 * premium

    # Calibrate to actual Chennai rate
    try:
        from analysis import get_gold_calibration_factor, get_silver_calibration_factor

        is_gold = premium <= 1.04  # gold premium ~1.03, silver ~1.05+
        if is_gold:
            factor, _ = get_gold_calibration_factor()
        else:
            factor, _ = get_silver_calibration_factor()
        if factor != 1.0:
            series = series / premium * factor
    except Exception:
        pass  # fallback to uncalibrated
    return series


def generate_portfolio_pdf(holdings, pnl_data):
    """Generate a portfolio report PDF. Returns bytes or None."""
    try:
        from fpdf import FPDF
    except ImportError:
        return None

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Portfolio Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        8,
        f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C",
    )
    pdf.ln(8)

    # Summary
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 7, f"Total Invested: Rs {pnl_data['total_invested']:,.0f}")
    pdf.cell(
        95,
        7,
        f"Current Value: Rs {pnl_data['total_current']:,.0f}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pnl_label = "Profit" if pnl_data["total_pnl"] >= 0 else "Loss"
    pdf.cell(
        95,
        7,
        f"{pnl_label}: Rs {abs(pnl_data['total_pnl']):,.0f} ({pnl_data['total_pnl_pct']:+.1f}%)",
    )
    if pnl_data.get("xirr") is not None:
        pdf.cell(
            95, 7, f"XIRR: {pnl_data['xirr']:+.1f}%", new_x="LMARGIN", new_y="NEXT"
        )
    else:
        pdf.ln(7)
    pdf.ln(6)

    # Holdings table
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "Holdings", new_x="LMARGIN", new_y="NEXT")

    # Table header
    pdf.set_font("Helvetica", "B", 9)
    col_widths = [55, 25, 30, 30, 25, 25]
    headers = ["Name", "Type", "Invested", "Current", "P&L", "Return"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=1)
    pdf.ln()

    # Table rows
    pdf.set_font("Helvetica", "", 9)
    for hp in pnl_data["holdings_pnl"]:
        name = hp["name"][:25]
        type_label = hp["type"].replace("_", " ").title()
        pdf.cell(col_widths[0], 7, name, border=1)
        pdf.cell(col_widths[1], 7, type_label, border=1)
        pdf.cell(col_widths[2], 7, f"Rs {hp['invested']:,.0f}", border=1)
        pdf.cell(col_widths[3], 7, f"Rs {hp['current_value']:,.0f}", border=1)
        pdf.cell(col_widths[4], 7, f"Rs {hp['pnl']:+,.0f}", border=1)
        pdf.cell(col_widths[5], 7, f"{hp['pnl_pct']:+.1f}%", border=1)
        pdf.ln()

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(
        0,
        6,
        "Data: Yahoo Finance, AMFI India | Prices may be delayed 15-20 min",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C",
    )

    return pdf.output()


def render_verdict_card(signal, prediction_text=None):
    """Render the big gradient verdict card for any prediction signal."""
    icon, color, short, action = SIGNAL_MAP.get(
        signal, ("🟡", "#f1c40f", "Wait", "Check again later")
    )
    st.markdown(
        f"""<div style="background: linear-gradient(135deg, {color}22, {color}11);
        border-left: 5px solid {color}; border-radius: 10px;
        padding: 20px; margin: 10px 0;">
        <h2 style="margin:0; color: {color};">{icon} {signal}</h2>
        <p style="font-size: 1.2em; margin: 8px 0 4px 0;"><strong>{short}</strong></p>
        <p style="margin: 0; opacity: 0.85;">{action}</p>
        </div>""",
        unsafe_allow_html=True,
    )
    if prediction_text:
        st.info(f"📅 **Next 5-7 days:** {prediction_text}")


def render_factor_bars(reasons):
    """Render the factor score bars used in all prediction detail views."""
    for factor, score, reason in reasons:
        if score > 0:
            bar_color = "#27ae60"
            icon = "🟢"
            label = f"+{score} Buy"
        elif score < 0:
            bar_color = "#e74c3c"
            icon = "🔴"
            label = f"{score} Sell"
        else:
            bar_color = "#95a5a6"
            icon = "⚪"
            label = "Neutral"
        bar_width = min(abs(score) * 3, 100)
        st.markdown(
            f"""<div style="margin: 8px 0;">
            <strong>{icon} {factor}</strong> <span style="color: {bar_color}; font-size: 0.9em;">[{label}]</span>
            <div style="background: #eee; border-radius: 4px; height: 6px; margin: 4px 0;">
                <div style="background: {bar_color}; width: {bar_width}%; height: 6px; border-radius: 4px;"></div>
            </div>
            <span style="font-size: 0.85em; opacity: 0.7;">{reason}</span>
            </div>""",
            unsafe_allow_html=True,
        )


def render_total_score(total_score):
    """Render the total score summary line."""
    sc = "#27ae60" if total_score > 0 else "#e74c3c" if total_score < 0 else "#95a5a6"
    st.markdown(
        f"**Total Score:** <span style='color: {sc}; font-size: 1.2em;'>{total_score:+d}</span>",
        unsafe_allow_html=True,
    )


def render_signal_legend():
    """Render the signal scale explanation table."""
    st.markdown(
        """
| Signal | Meaning | Action |
|---|---|---|
| 🟢 **BUY** | Most factors say it's cheap | Buy now |
| 🟢 **LEAN BUY** | Slightly favourable conditions | Buy a small amount |
| 🟡 **WAIT** | Mixed signals, no clear direction | Don't act, check later |
| 🟠 **LEAN SELL** | Slightly unfavourable | Hold off, wait for a dip |
| 🔴 **SELL** | Most factors say it's expensive | Don't buy, consider selling |
"""
    )


def render_news_card(title, sentiment_label, summary, action):
    """Render a single news impact card."""
    if sentiment_label == "Good news":
        box_color = "#27ae60"
    elif sentiment_label == "Bad news":
        box_color = "#e74c3c"
    else:
        box_color = "#95a5a6"
    st.markdown(
        f"""<div style="border-left: 4px solid {box_color}; padding: 8px 12px; margin: 6px 0; border-radius: 4px; background: {box_color}11;">
        <strong>{html_escape(title[:120])}</strong>
        <span style="color: {box_color}; font-size: 0.85em;"> — {html_escape(sentiment_label)}</span>
        <br><span style="font-size: 0.9em;">{html_escape(summary)}</span>
        <br><span style="font-size: 0.85em; opacity: 0.8;">👉 {html_escape(action)}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def render_track_record(verified_preds, metal_name):
    """Render prediction track record for gold or silver."""
    correct = sum(1 for p in verified_preds if p.get("was_correct"))
    accuracy = round((correct / len(verified_preds)) * 100) if verified_preds else 0

    tr1, tr2, tr3 = st.columns(3)
    tr1.metric("Predictions Made", len(verified_preds))
    tr2.metric("Correct", f"{correct} ✅")
    tr3.metric("Accuracy", f"{accuracy}%")

    if accuracy < 50 and len(verified_preds) >= 3:
        st.warning(
            "⚠️ Accuracy is below 50% — the model is being refined with each prediction. More data will improve results."
        )

    for p in reversed(verified_preds[-10:]):
        was = "✅ Correct" if p.get("was_correct") else "❌ Wrong"
        change = p.get("actual_change_pct", 0)
        st.markdown(
            f"**{p['date']}** — Signal: {p['signal']} at ₹{p['price_at_prediction']:,.2f} → "
            f"₹{p.get('actual_price_after', 0):,.2f} ({change:+.2f}%) — {was}"
        )


def render_learnings(learnings_data, metal_name):
    """Render self-learning section for a metal."""
    st.markdown(
        "I analyse my past predictions to find which factors led me astray and adjust accordingly:"
    )
    st.markdown("")

    fa = learnings_data.get("factor_accuracy", {})
    if fa:
        for fname, fdata in fa.items():
            acc = fdata["accuracy"]
            acc_color = (
                "#27ae60" if acc >= 70 else "#f39c12" if acc >= 50 else "#e74c3c"
            )
            bar_w = max(acc, 5)
            st.markdown(
                f"""<div style="margin: 6px 0;">
                <strong>{fname}</strong> — <span style="color: {acc_color};">{acc}% accurate</span> ({fdata['correct']}/{fdata['total']} correct)
                <div style="background: #eee; border-radius: 4px; height: 6px; margin: 4px 0;">
                    <div style="background: {acc_color}; width: {bar_w}%; height: 6px; border-radius: 4px;"></div>
                </div>
                </div>""",
                unsafe_allow_html=True,
            )

    if learnings_data.get("learnings"):
        st.markdown("---")
        st.markdown("**Key Learnings:**")
        for learning in learnings_data["learnings"]:
            st.markdown(learning)

    if learnings_data.get("worst_factors"):
        st.markdown("")
        st.markdown(
            f"**Weakest factors:** {', '.join(learnings_data['worst_factors'])} — I'm reducing their influence on future predictions."
        )


def render_price_history(metal_name, ticker, premium, period_key):
    """Render price history with big moves for gold or silver."""
    period_map = {"3 Months": "3mo", "6 Months": "6mo", "1 Year": "1y"}
    period_choice = st.radio(
        "Period",
        list(period_map.keys()),
        horizontal=True,
        key=period_key,
    )

    hist_long = yf.Ticker(ticker).history(period=period_map[period_choice])
    fx_long = yf.Ticker("USDINR=X").history(period=period_map[period_choice])
    inr_hist = metal_inr_series(hist_long, fx_long, premium=premium)

    if inr_hist is not None and len(inr_hist) > 1:
        daily_pct = inr_hist.pct_change().dropna() * 100

        hist_chart = pd.DataFrame({f"{metal_name} ₹/gram": inr_hist})
        if hist_chart.index.tz is not None:
            hist_chart.index = hist_chart.index.tz_localize(None)
        st.line_chart(hist_chart, height=300)

        hs1, hs2, hs3, hs4 = st.columns(4)
        hs1.metric(f"{period_choice} High", f"₹{inr_hist.max():,.2f}")
        hs2.metric(f"{period_choice} Low", f"₹{inr_hist.min():,.2f}")
        total_change = ((inr_hist.iloc[-1] / inr_hist.iloc[0]) - 1) * 100
        hs3.metric("Total Change", f"{total_change:+.2f}%")
        hs4.metric("Avg Daily Move", f"{daily_pct.abs().mean():.2f}%")

        top_drops = daily_pct.nsmallest(5)
        top_rises = daily_pct.nlargest(5)

        dr_col, ri_col = st.columns(2)
        with dr_col:
            st.markdown("#### 📉 Biggest Drops")
            for date, pct in top_drops.items():
                price = inr_hist.loc[date]
                st.markdown(
                    f"🔴 **{date.strftime('%d %b %Y')}** — {pct:.2f}% (₹{price:,.2f}/g)"
                )
        with ri_col:
            st.markdown("#### 📈 Biggest Rises")
            for date, pct in top_rises.items():
                price = inr_hist.loc[date]
                st.markdown(
                    f"🟢 **{date.strftime('%d %b %Y')}** — +{pct:.2f}% (₹{price:,.2f}/g)"
                )

        st.subheader("📊 Daily Change Distribution")
        dist_chart = pd.DataFrame({"Daily Change %": daily_pct})
        if dist_chart.index.tz is not None:
            dist_chart.index = dist_chart.index.tz_localize(None)
        st.bar_chart(dist_chart, height=200)
    else:
        st.info("No history data available for this period")
