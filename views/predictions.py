import streamlit as st
import json
import os
from datetime import datetime, date, timedelta

import db
from analysis import (
    verify_gold_predictions,
    verify_silver_predictions,
    verify_stock_predictions,
    verify_scanner_predictions,
    get_prediction_learnings,
    get_stock_prediction_learnings,
    get_scanner_prediction_learnings,
    backtest_metal_prediction,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _load_predictions(filename):
    table_name = filename.replace(".json", "")
    if db.is_db_available():
        return db.load_predictions(table_name)
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _filter_by_period(preds, days):
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    return [p for p in preds if p.get("date", "") >= cutoff]


def _accuracy_stats(preds):
    verified = [p for p in preds if p.get("verified")]
    if not verified:
        return {
            "total": 0,
            "verified": 0,
            "correct": 0,
            "wrong": 0,
            "pending": len(preds),
            "accuracy": None,
        }
    correct = sum(1 for p in verified if p.get("was_correct"))
    wrong = len(verified) - correct
    pending = len(preds) - len(verified)
    accuracy = round((correct / len(verified)) * 100) if verified else 0
    return {
        "total": len(preds),
        "verified": len(verified),
        "correct": correct,
        "wrong": wrong,
        "pending": pending,
        "accuracy": accuracy,
    }


def _signal_color(signal):
    if signal in ("BUY", "LEAN BUY"):
        return "#27ae60"
    elif signal in ("SELL", "LEAN SELL"):
        return "#e74c3c"
    return "#f39c12"


def _render_prediction_table(preds, show_ticker=False):
    if not preds:
        st.info("No predictions in this period.")
        return

    for p in reversed(preds):
        pred_date = p.get("date", "?")
        signal = p.get("signal", "?")
        confidence = p.get("confidence", 0)
        price_at = p.get("price_at_prediction", 0)
        verified = p.get("verified", False)
        was_correct = p.get("was_correct")
        actual_price = p.get("actual_price_after")
        change_pct = p.get("actual_change_pct", 0)
        name = p.get("name", "")
        ticker = p.get("ticker", "")

        sig_color = _signal_color(signal)

        if verified:
            if was_correct:
                icon = "✅"
                result_text = (
                    f"Correct — price moved {change_pct:+.2f}% to ₹{actual_price:,.2f}"
                )
            else:
                icon = "❌"
                result_text = (
                    f"Wrong — price moved {change_pct:+.2f}% to ₹{actual_price:,.2f}"
                )
        else:
            icon = "⏳"
            result_text = "Pending verification (< 5 days old)"

        label = f"**{pred_date}**"
        if show_ticker and name:
            label += f" · {name}"

        st.markdown(
            f"{icon} {label} — "
            f"<span style='color:{sig_color}; font-weight:600;'>{signal}</span> "
            f"(confidence {confidence}%) at ₹{price_at:,.2f} → {result_text}",
            unsafe_allow_html=True,
        )


def _render_accuracy_card(label, stats):
    if stats["verified"] == 0:
        st.metric(label, "No data", "No verified predictions yet")
        return
    acc = stats["accuracy"]
    color = "normal" if acc >= 50 else "inverse"
    st.metric(
        label,
        f"{acc}%",
        f"{stats['correct']}✅  {stats['wrong']}❌  {stats['pending']}⏳",
        delta_color="off",
    )


def render(holdings):
    st.title("📈 Prediction Scorecard")
    st.caption(
        "How accurate were past predictions? Track record for gold, silver, stocks, and scanner suggestions."
    )

    # Trigger verification of all predictions
    with st.spinner("Verifying predictions against actual prices..."):
        gold_preds = verify_gold_predictions()
        silver_preds = verify_silver_predictions()
        stock_preds = verify_stock_predictions()
        scanner_preds = verify_scanner_predictions()

    # --- Period selector ---
    period = st.radio(
        "Time period",
        ["Last 7 days", "Last 30 days", "Last 90 days", "All time"],
        horizontal=True,
        key="pred_period",
    )
    period_days = {
        "Last 7 days": 7,
        "Last 30 days": 30,
        "Last 90 days": 90,
        "All time": 9999,
    }[period]

    gold_filtered = _filter_by_period(gold_preds, period_days)
    silver_filtered = _filter_by_period(silver_preds, period_days)
    stock_filtered = _filter_by_period(stock_preds, period_days)
    scanner_filtered = _filter_by_period(scanner_preds, period_days)

    gold_stats = _accuracy_stats(gold_filtered)
    silver_stats = _accuracy_stats(silver_filtered)
    stock_stats = _accuracy_stats(stock_filtered)
    scanner_stats = _accuracy_stats(scanner_filtered)

    # --- Overall summary ---
    st.subheader("📊 Overall Accuracy")
    all_verified = (
        [p for p in gold_filtered if p.get("verified")]
        + [p for p in silver_filtered if p.get("verified")]
        + [p for p in stock_filtered if p.get("verified")]
        + [p for p in scanner_filtered if p.get("verified")]
    )
    all_correct = sum(1 for p in all_verified if p.get("was_correct"))
    all_wrong = len(all_verified) - all_correct
    all_pending = (
        len(gold_filtered)
        + len(silver_filtered)
        + len(stock_filtered)
        + len(scanner_filtered)
    ) - len(all_verified)
    overall_acc = (
        round((all_correct / len(all_verified)) * 100) if all_verified else None
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Total Predictions",
        len(gold_filtered)
        + len(silver_filtered)
        + len(stock_filtered)
        + len(scanner_filtered),
    )
    c2.metric("Verified", len(all_verified))
    c3.metric("Correct", f"{all_correct} ✅")
    c4.metric("Wrong", f"{all_wrong} ❌")
    if overall_acc is not None:
        acc_icon = "🟢" if overall_acc >= 60 else "🟡" if overall_acc >= 45 else "🔴"
        c5.metric("Accuracy", f"{acc_icon} {overall_acc}%")
    else:
        c5.metric("Accuracy", "—")

    st.divider()

    # --- Per-asset cards ---
    st.subheader("🏷️ Accuracy by Asset")
    ac1, ac2, ac3, ac4 = st.columns(4)
    with ac1:
        _render_accuracy_card("🪙 Gold", gold_stats)
    with ac2:
        _render_accuracy_card("🥈 Silver", silver_stats)
    with ac3:
        _render_accuracy_card("📈 Stocks", stock_stats)
    with ac4:
        _render_accuracy_card("🔎 Scanner", scanner_stats)

    st.divider()

    # --- Detailed tabs ---
    gold_tab, silver_tab, stock_tab, scanner_tab, backtest_tab, insights_tab = st.tabs(
        [
            "🪙 Gold",
            "🥈 Silver",
            "📈 Stocks",
            "🔎 Scanner",
            "🧪 Backtest",
            "🧠 Insights & Learnings",
        ]
    )

    with gold_tab:
        st.subheader("Gold Predictions")
        if not gold_filtered:
            st.info("No gold predictions in this period.")
        else:
            # Signal distribution
            buy_count = sum(
                1 for p in gold_filtered if p.get("signal") in ("BUY", "LEAN BUY")
            )
            sell_count = sum(
                1 for p in gold_filtered if p.get("signal") in ("SELL", "LEAN SELL")
            )
            wait_count = sum(1 for p in gold_filtered if p.get("signal") == "WAIT")
            g1, g2, g3 = st.columns(3)
            g1.metric("Buy Signals", buy_count)
            g2.metric("Sell Signals", sell_count)
            g3.metric("Wait Signals", wait_count)
            st.markdown("---")
            _render_prediction_table(gold_filtered)

    with silver_tab:
        st.subheader("Silver Predictions")
        if not silver_filtered:
            st.info("No silver predictions in this period.")
        else:
            buy_count = sum(
                1 for p in silver_filtered if p.get("signal") in ("BUY", "LEAN BUY")
            )
            sell_count = sum(
                1 for p in silver_filtered if p.get("signal") in ("SELL", "LEAN SELL")
            )
            wait_count = sum(1 for p in silver_filtered if p.get("signal") == "WAIT")
            g1, g2, g3 = st.columns(3)
            g1.metric("Buy Signals", buy_count)
            g2.metric("Sell Signals", sell_count)
            g3.metric("Wait Signals", wait_count)
            st.markdown("---")
            _render_prediction_table(silver_filtered)

    with stock_tab:
        st.subheader("Stock Predictions")
        if not stock_filtered:
            st.info("No stock predictions in this period.")
        else:
            # Group by ticker
            tickers_seen = {}
            for p in stock_filtered:
                tk = p.get("ticker", p.get("name", "Unknown"))
                tickers_seen.setdefault(tk, []).append(p)

            for tk, tk_preds in tickers_seen.items():
                tk_stats = _accuracy_stats(tk_preds)
                name = tk_preds[0].get("name", tk)
                acc_text = (
                    f" — {tk_stats['accuracy']}% accuracy"
                    if tk_stats["accuracy"] is not None
                    else ""
                )
                with st.expander(f"**{name}** ({len(tk_preds)} predictions{acc_text})"):
                    _render_prediction_table(tk_preds)

    with scanner_tab:
        st.subheader("Scanner Buy Suggestions")
        st.caption(
            "Tracks whether 'What Should I Buy?' suggestions actually went up. "
            "Verified at 7 days (short-term bounce) and 30 days (recovery)."
        )
        if not scanner_filtered:
            st.info(
                "No scanner suggestions in this period. "
                "Go to **🔎 Scanner → 💡 What Should I Buy?** to generate some."
            )
        else:
            # Summary by urgency
            high_count = sum(1 for p in scanner_filtered if p.get("urgency") == "high")
            med_count = sum(1 for p in scanner_filtered if p.get("urgency") == "medium")
            low_count = sum(1 for p in scanner_filtered if p.get("urgency") == "low")
            s1, s2, s3 = st.columns(3)
            s1.metric("🟢 High Urgency", high_count)
            s2.metric("🟡 Medium Urgency", med_count)
            s3.metric("⚪ Low Urgency", low_count)

            # 7-day vs 30-day accuracy
            v7 = [p for p in scanner_filtered if p.get("verified_7d")]
            v30 = [p for p in scanner_filtered if p.get("verified_30d")]
            if v7 or v30:
                st.markdown("---")
                st.markdown("**Verification Timeline**")
                t1, t2 = st.columns(2)
                if v7:
                    c7 = sum(1 for p in v7 if p.get("was_correct_7d"))
                    acc7 = round((c7 / len(v7)) * 100)
                    t1.metric(
                        "7-Day Accuracy",
                        f"{acc7}%",
                        f"{c7}/{len(v7)} bounced up",
                    )
                else:
                    t1.metric("7-Day Accuracy", "—", "No data yet")
                if v30:
                    c30 = sum(1 for p in v30 if p.get("was_correct_30d"))
                    acc30 = round((c30 / len(v30)) * 100)
                    t2.metric(
                        "30-Day Accuracy",
                        f"{acc30}%",
                        f"{c30}/{len(v30)} recovered",
                    )
                else:
                    t2.metric("30-Day Accuracy", "—", "No data yet")

            st.markdown("---")
            # Group by ticker
            scanner_by_ticker = {}
            for p in scanner_filtered:
                tk = p.get("ticker", p.get("name", "Unknown"))
                scanner_by_ticker.setdefault(tk, []).append(p)

            for tk, tk_preds in scanner_by_ticker.items():
                name = tk_preds[0].get("name", tk)
                urgency = tk_preds[0].get("urgency", "")
                urgency_icon = (
                    "🟢" if urgency == "high" else "🟡" if urgency == "medium" else "⚪"
                )
                price_at = tk_preds[0].get("price_at_prediction", 0)

                # Build result summary
                latest = tk_preds[-1]
                if latest.get("verified_30d"):
                    change = latest.get("change_pct_30d", 0)
                    icon = "✅" if latest.get("was_correct_30d") else "❌"
                    result = f"{icon} 30d: {change:+.1f}%"
                elif latest.get("verified_7d"):
                    change = latest.get("change_pct_7d", 0)
                    icon = "✅" if latest.get("was_correct_7d") else "❌"
                    result = f"{icon} 7d: {change:+.1f}%"
                else:
                    result = "⏳ Pending"

                with st.expander(
                    f"{urgency_icon} **{name}** — ₹{price_at:,.2f} · {result}"
                ):
                    for p in reversed(tk_preds):
                        sig_color = _signal_color(p.get("signal", ""))
                        lines = [
                            f"**{p.get('date', '?')}** — "
                            f"<span style='color:{sig_color};font-weight:600'>"
                            f"{p.get('signal', '?')}</span> "
                            f"at ₹{p.get('price_at_prediction', 0):,.2f}"
                        ]
                        if p.get("verified_7d"):
                            c7 = p.get("change_pct_7d", 0)
                            ok7 = "✅" if p.get("was_correct_7d") else "❌"
                            lines.append(
                                f" → 7d: {ok7} {c7:+.2f}% "
                                f"(₹{p.get('actual_price_7d', 0):,.2f})"
                            )
                        if p.get("verified_30d"):
                            c30 = p.get("change_pct_30d", 0)
                            ok30 = "✅" if p.get("was_correct_30d") else "❌"
                            lines.append(
                                f" → 30d: {ok30} {c30:+.2f}% "
                                f"(₹{p.get('actual_price_30d', 0):,.2f})"
                            )
                        if not p.get("verified_7d") and not p.get("verified_30d"):
                            lines.append(" → ⏳ Pending")
                        st.markdown("".join(lines), unsafe_allow_html=True)
                        if p.get("buy_reasoning"):
                            st.caption(" · ".join(p["buy_reasoning"][:3]))

    with backtest_tab:
        st.subheader("🧪 Backtest Prediction Engine")
        st.caption(
            "Test how the prediction model would have performed on historical data. "
            "Uses 7 core factors (excludes live-only factors like news and VIX)."
        )

        bt_col1, bt_col2, bt_col3 = st.columns(3)
        with bt_col1:
            bt_metal = st.selectbox("Metal", ["gold", "silver"], key="bt_metal")
        with bt_col2:
            bt_months = st.selectbox(
                "Lookback Period",
                [3, 6, 9, 12],
                index=1,
                key="bt_months",
                format_func=lambda x: f"{x} months",
            )
        with bt_col3:
            bt_hold = st.selectbox(
                "Hold Period",
                [5, 7, 14, 30],
                index=1,
                key="bt_hold",
                format_func=lambda x: f"{x} days",
            )

        if st.button("▶️ Run Backtest", key="run_backtest"):
            with st.spinner(f"Backtesting {bt_metal} over {bt_months} months..."):
                bt_result = backtest_metal_prediction(bt_metal, bt_months, bt_hold)

            if bt_result and bt_result.get("summary"):
                summary = bt_result["summary"]

                # Summary cards
                bc1, bc2, bc3, bc4 = st.columns(4)
                acc = summary["overall_accuracy"]
                acc_color = (
                    "#27ae60" if acc >= 60 else "#f39c12" if acc >= 45 else "#e74c3c"
                )
                bc1.metric("Overall Accuracy", f"{acc}%")
                bc2.metric("Signals Tested", f"{summary['total_tested']}")
                bc3.metric(
                    "BUY Accuracy",
                    f"{summary['buy_accuracy']}%",
                    f"{summary['buy_signals']} signals",
                )
                bc4.metric(
                    "SELL Accuracy",
                    f"{summary['sell_accuracy']}%",
                    f"{summary['sell_signals']} signals",
                )

                avg_ret = summary["avg_buy_return"]
                ret_color = "#27ae60" if avg_ret > 0 else "#e74c3c"
                st.markdown(
                    f"""<div style="background: {ret_color}11; border-left: 4px solid {ret_color};
                    padding: 12px 16px; border-radius: 6px; margin: 10px 0;">
                    <strong>Avg Return on BUY signals:</strong>
                    <span style="color: {ret_color}; font-weight: 600;">{avg_ret:+.2f}%</span>
                    over {bt_hold} days
                    </div>""",
                    unsafe_allow_html=True,
                )

                # Per-signal results
                results = bt_result.get("results", [])
                if results:
                    with st.expander(
                        f"📋 All {len(results)} Signal Results", expanded=False
                    ):
                        for r in reversed(results):
                            sig_color = _signal_color(r["signal"])
                            ok = "✅" if r["was_correct"] else "❌"
                            st.markdown(
                                f"{ok} **{r['date']}** — "
                                f"<span style='color:{sig_color};font-weight:600'>{r['signal']}</span> "
                                f"(score {r['score']:+d}) "
                                f"at ₹{r['price']:,.2f} → ₹{r['future_price']:,.2f} "
                                f"({r['actual_change_pct']:+.2f}%)",
                                unsafe_allow_html=True,
                            )
            else:
                st.warning(
                    "Backtest failed — not enough historical data. Try a shorter lookback period."
                )

    with insights_tab:
        st.subheader("🧠 What the Model Learned")
        st.caption("Analysis of which prediction factors performed well vs poorly.")

        gold_learnings = get_prediction_learnings("gold")
        silver_learnings = get_prediction_learnings("silver")
        stock_learnings = get_stock_prediction_learnings()
        scanner_learnings = get_scanner_prediction_learnings()

        has_any = False

        if gold_learnings and gold_learnings.get("total_verified", 0) > 0:
            has_any = True
            with st.expander(
                f"🪙 Gold — {gold_learnings['total_correct']}/{gold_learnings['total_verified']} correct",
                expanded=True,
            ):
                _render_factor_accuracy(gold_learnings)

        if silver_learnings and silver_learnings.get("total_verified", 0) > 0:
            has_any = True
            with st.expander(
                f"🥈 Silver — {silver_learnings['total_correct']}/{silver_learnings['total_verified']} correct"
            ):
                _render_factor_accuracy(silver_learnings)

        if stock_learnings and stock_learnings.get("total_verified", 0) > 0:
            has_any = True
            with st.expander(
                f"📈 Stocks — {stock_learnings['total_correct']}/{stock_learnings['total_verified']} correct"
            ):
                _render_factor_accuracy(stock_learnings)

        if scanner_learnings and scanner_learnings.get("total_verified", 0) > 0:
            has_any = True
            with st.expander(
                f"🔎 Scanner — {scanner_learnings['total_correct']}/{scanner_learnings['total_verified']} correct"
            ):
                _render_factor_accuracy(scanner_learnings)

        if not has_any:
            st.info(
                "Not enough verified predictions yet to generate insights. "
                "Predictions are verified after 5 days — check back later!"
            )


def _render_factor_accuracy(learnings_data):
    fa = learnings_data.get("factor_accuracy", {})
    if fa:
        # Sort by accuracy ascending so worst show first
        sorted_factors = sorted(fa.items(), key=lambda x: x[1]["accuracy"])
        for fname, fdata in sorted_factors:
            acc = fdata["accuracy"]
            acc_color = (
                "#27ae60" if acc >= 70 else "#f39c12" if acc >= 50 else "#e74c3c"
            )
            bar_w = max(acc, 5)
            st.markdown(
                f"""<div style="margin: 6px 0;">
                <strong>{fname}</strong> — <span style="color: {acc_color};">{acc}% accurate</span> ({fdata['correct']}/{fdata['total']} correct)
                <div style="background: #333; border-radius: 4px; height: 8px; margin: 4px 0;">
                    <div style="background: {acc_color}; width: {bar_w}%; height: 8px; border-radius: 4px;"></div>
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
        st.caption(
            f"Weakest factors: **{', '.join(learnings_data['worst_factors'])}** — their influence is reduced in future predictions."
        )
