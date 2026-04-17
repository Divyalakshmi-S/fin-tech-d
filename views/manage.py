import streamlit as st
import json
import os
from datetime import datetime, date

import db
import auth
from analysis import (
    validate_ticker,
    auto_resolve_ticker,
    auto_resolve_amfi,
    _is_month_paused,
    is_sip_currently_paused,
    _aggregate_transactions,
)
import yfinance as yf

from views._manage_helpers import (
    _months_between,
    _fetch_current_prices,
    _save_portfolio,
    _get_entry_invested,
    _get_entry_quantity,
    _load_raw_portfolio,
    _COL_PATTERNS,
    _smart_detect_columns,
    _find_data_rows,
    _safe_float,
    _parse_row_smart,
)


def render(holdings):
    st.title("⚙️ Manage Portfolio")
    st.caption(
        "Add, edit, or remove investments. All data is entered by you — no files needed."
    )

    portfolio_rows = _load_raw_portfolio()

    # Auto-fix: resolve missing tickers for stock/MF entries
    _auto_fix_needed = False
    for row in portfolio_rows:
        if not row.get("ticker"):
            asset_type = row.get("type", "stock")
            result = auto_resolve_ticker(row["name"], asset_type)
            if result["ticker"]:
                row["ticker"] = result["ticker"]
                if result["name"]:
                    row["name"] = result["name"]
                _auto_fix_needed = True
    if _auto_fix_needed:
        _save_portfolio(portfolio_rows)

    if portfolio_rows:
        st.info(
            f"📁 **{len(portfolio_rows)} holdings** in your portfolio. See **📁 My Portfolio** for detailed summary & P&L."
        )
        st.divider()

    # ------ Add New Investment ------
    st.subheader("➕ Add New Investment")

    add_tab1, add_tab2, add_tab3 = st.tabs(
        ["💰 Lump Sum (Stock / One-time)", "🔄 SIP (Monthly)", "📁 Import CSV / Excel"]
    )

    with add_tab1:
        with st.form("add_lumpsum", clear_on_submit=True):
            ac1, ac2 = st.columns(2)
            new_name = ac1.text_input(
                "Name *", placeholder="e.g. ITC, HDFC Bank", key="ls_name"
            )
            new_type = ac2.selectbox(
                "Type *", ["stock", "mutual_fund"], index=0, key="ls_type"
            )

            ac3, ac4, ac5 = st.columns(3)
            new_buy_price = ac3.number_input(
                "Buy Price (₹) *", min_value=0.0, step=1.0, value=0.0, key="ls_price"
            )
            new_quantity = ac4.number_input(
                "Quantity *", min_value=0.0, step=1.0, value=0.0, key="ls_qty"
            )
            new_buy_date = ac5.date_input(
                "Buy Date *", value=date.today(), key="ls_date"
            )
            new_note = st.text_input(
                "Note (optional)",
                placeholder="e.g. bonus, merger, averaging down",
                key="ls_note",
            )

            submitted = st.form_submit_button(
                "➕ Add to Portfolio", use_container_width=True
            )
            if submitted:
                if not new_name.strip():
                    st.error("Name is required.")
                elif new_buy_price <= 0:
                    st.error("Buy price must be greater than 0.")
                elif new_quantity <= 0:
                    st.error("Quantity must be greater than 0.")
                else:
                    validated_name = new_name.strip()
                    resolved_ticker = ""
                    resolved_amfi = ""

                    if new_type == "stock":
                        with st.spinner(f"🔍 Finding ticker for '{validated_name}'..."):
                            result = auto_resolve_ticker(validated_name, "stock")
                        if result["ticker"]:
                            resolved_ticker = result["ticker"]
                            if result["name"]:
                                validated_name = result["name"]
                            st.success(
                                f"✅ Found: **{validated_name}** ({resolved_ticker})"
                            )
                        else:
                            st.warning(f"⚠️ {result['error']}. You can edit later.")

                    if new_type == "mutual_fund":
                        with st.spinner(f"🔍 Searching AMFI for '{validated_name}'..."):
                            amfi_result = auto_resolve_amfi(validated_name)
                        if amfi_result["amfi_code"]:
                            resolved_amfi = amfi_result["amfi_code"]
                            if amfi_result["scheme_name"]:
                                validated_name = amfi_result["scheme_name"]
                            st.success(f"✅ Found: **{validated_name}**")
                        else:
                            st.warning(f"⚠️ {amfi_result['error']}")

                    new_txn = {
                        "buy_price": new_buy_price,
                        "quantity": new_quantity,
                        "buy_date": new_buy_date.strftime("%Y-%m-%d"),
                        "note": new_note.strip(),
                    }

                    # Check if holding with same ticker or name already exists
                    existing_idx = None
                    match_ticker = resolved_ticker or ""
                    match_name = validated_name.lower()
                    for i, row in enumerate(portfolio_rows):
                        if row.get("investment_mode") == "sip":
                            continue
                        if (
                            match_ticker
                            and row.get("ticker", "").upper() == match_ticker.upper()
                        ):
                            existing_idx = i
                            break
                        if row["name"].lower() == match_name:
                            existing_idx = i
                            break

                    if existing_idx is not None:
                        # Add transaction to existing holding
                        existing = portfolio_rows[existing_idx]
                        txns = existing.get("transactions", [])
                        if not txns:
                            # Migrate existing single entry to transactions
                            old_bp = float(existing.get("buy_price", 0))
                            old_qty = float(existing.get("quantity", 0))
                            old_bd = existing.get("buy_date", "")
                            if old_bp > 0 and old_qty > 0:
                                txns.append(
                                    {
                                        "buy_price": old_bp,
                                        "quantity": old_qty,
                                        "buy_date": old_bd,
                                        "note": "",
                                    }
                                )
                        txns.append(new_txn)
                        existing["transactions"] = txns
                        agg = _aggregate_transactions(txns)
                        existing["buy_price"] = agg["weighted_avg_price"]
                        existing["quantity"] = agg["total_quantity"]
                        if agg["earliest_date"]:
                            existing["buy_date"] = agg["earliest_date"].strftime(
                                "%Y-%m-%d"
                            )
                        _save_portfolio(portfolio_rows)
                        amount = new_buy_price * new_quantity
                        st.success(
                            f"✅ Added transaction to **{existing['name']}** — "
                            f"{new_quantity:.0f} × ₹{new_buy_price:,.2f} = ₹{amount:,.0f} "
                            f"(now {agg['total_quantity']:.0f} units total)"
                        )
                    else:
                        # Create new holding
                        new_row = {
                            "name": validated_name,
                            "ticker": resolved_ticker,
                            "type": new_type,
                            "investment_mode": "lumpsum",
                            "buy_price": new_buy_price,
                            "quantity": new_quantity,
                            "buy_date": new_buy_date.strftime("%Y-%m-%d"),
                            "sip_monthly": 0,
                            "sip_date": 0,
                            "amfi_code": resolved_amfi,
                            "transactions": [new_txn],
                        }
                        portfolio_rows.append(new_row)
                        _save_portfolio(portfolio_rows)
                        amount = new_buy_price * new_quantity
                        st.success(
                            f"✅ Added **{validated_name}** — {new_quantity:.0f} × ₹{new_buy_price:,.2f} = ₹{amount:,.0f}"
                        )
                    st.rerun()

    with add_tab2:
        st.caption(
            "SIP = you invest a fixed ₹ amount every month. "
            "The app tracks how many months you've been investing and calculates total invested."
        )
        with st.form("add_sip", clear_on_submit=True):
            sc1, sc2 = st.columns(2)
            sip_name = sc1.text_input(
                "Fund / Stock Name *",
                placeholder="e.g. Nippon Small Cap Fund",
                key="sip_name",
            )
            sip_type = sc2.selectbox(
                "Type *", ["mutual_fund", "stock"], index=0, key="sip_type"
            )

            sc3, sc4, sc5 = st.columns(3)
            sip_amount = sc3.number_input(
                "Monthly Amount (₹) *", min_value=0, step=100, value=0, key="sip_amt"
            )
            sip_debit_date = sc4.number_input(
                "Debit Date (day of month) *",
                min_value=1,
                max_value=28,
                step=1,
                value=5,
                key="sip_dd",
                help="Day each month when SIP is debited",
            )
            sip_start = sc5.date_input(
                "SIP Start Date *", value=date.today(), key="sip_start"
            )

            sip_submitted = st.form_submit_button(
                "🔄 Add SIP", use_container_width=True
            )
            if sip_submitted:
                if not sip_name.strip():
                    st.error("Fund name is required.")
                elif sip_amount <= 0:
                    st.error("Monthly amount must be greater than 0.")
                else:
                    validated_name = sip_name.strip()
                    resolved_ticker = ""
                    resolved_amfi = ""

                    if sip_type == "stock":
                        with st.spinner(f"🔍 Finding ticker for '{validated_name}'..."):
                            result = auto_resolve_ticker(validated_name, "stock")
                        if result["ticker"]:
                            resolved_ticker = result["ticker"]
                            if result["name"]:
                                validated_name = result["name"]
                            st.success(
                                f"✅ Found: **{validated_name}** ({resolved_ticker})"
                            )
                        else:
                            st.warning(f"⚠️ {result['error']}. You can edit later.")

                    if sip_type == "mutual_fund":
                        with st.spinner(f"🔍 Searching AMFI for '{validated_name}'..."):
                            amfi_result = auto_resolve_amfi(validated_name)
                        if amfi_result["amfi_code"]:
                            resolved_amfi = amfi_result["amfi_code"]
                            if amfi_result["scheme_name"]:
                                validated_name = amfi_result["scheme_name"]
                            st.success(f"✅ Found: **{validated_name}**")
                        else:
                            st.warning(f"⚠️ {amfi_result['error']}")

                    # Calculate months invested so far
                    months_elapsed = _months_between(sip_start, date.today())
                    total_invested = sip_amount * max(months_elapsed, 1)

                    new_row = {
                        "name": validated_name,
                        "ticker": resolved_ticker,
                        "type": sip_type,
                        "investment_mode": "sip",
                        "buy_price": 0,
                        "quantity": 0,
                        "buy_date": sip_start.strftime("%Y-%m-%d"),
                        "sip_monthly": sip_amount,
                        "sip_date": sip_debit_date,
                        "amfi_code": resolved_amfi,
                    }
                    portfolio_rows.append(new_row)
                    _save_portfolio(portfolio_rows)
                    st.success(
                        f"✅ Added SIP: **{validated_name}** — ₹{sip_amount:,}/mo since {sip_start.strftime('%b %Y')} "
                        f"(~₹{total_invested:,} invested over {months_elapsed} months)"
                    )
                    st.rerun()

    with add_tab3:
        import pandas as pd
        import re as _re

        st.caption(
            "Upload a CSV or Excel file exported from **any** broker or app "
            "(Zerodha, Groww, INDMoney, Kite, Angel One, MFCentral, etc.). "
            "Columns are auto-detected — no specific format required."
        )

        uploaded = st.file_uploader(
            "Upload CSV or Excel file",
            type=["csv", "xlsx", "xls"],
            key="portfolio_upload",
        )

        if uploaded:
            try:
                is_excel = uploaded.name.endswith((".xlsx", ".xls"))
                df = _find_data_rows(uploaded, is_excel)

                # Drop fully empty rows/columns
                df = df.dropna(how="all").dropna(axis=1, how="all")

                if df.empty:
                    st.error("The file appears to be empty.")
                else:
                    st.markdown(f"**Found {len(df)} rows × {len(df.columns)} columns**")
                    st.dataframe(df.head(8), use_container_width=True, hide_index=True)

                    # --- Smart column detection ---
                    mapped = _smart_detect_columns(df)
                    _FIELD_LABELS = {
                        "name": "Name",
                        "buy_price": "Price",
                        "quantity": "Qty",
                        "buy_date": "Date",
                        "ticker": "Ticker",
                        "type": "Type",
                        "amount": "Amount",
                        "note": "Note",
                        "trade_type": "Buy/Sell",
                        "sell_price": "Sell Price",
                        "sell_value": "Sell Value",
                        "pnl": "P&L",
                        "holding_period": "Holding Period",
                        "charges": "Charges",
                    }
                    detected_summary = []
                    for field, col in mapped.items():
                        if col:
                            label = _FIELD_LABELS.get(field, field)
                            detected_summary.append(f"**{label}** ← `{col}`")

                    # Detect report format
                    _format_hints = []
                    if mapped.get("trade_type"):
                        _format_hints.append("Tradebook")
                    if mapped.get("pnl") or mapped.get("sell_value"):
                        _format_hints.append("P&L Report")
                    if mapped.get("holding_period"):
                        _format_hints.append("Tax Report")
                    if mapped.get("charges"):
                        _format_hints.append("includes charges")
                    format_label = (
                        " · ".join(_format_hints) if _format_hints else "Holdings"
                    )

                    if detected_summary:
                        st.success(
                            f"🔍 **{format_label}** format detected — "
                            + " · ".join(detected_summary)
                        )
                    else:
                        st.warning(
                            "Could not auto-detect columns. Please select manually below."
                        )

                    # Let user override mappings
                    with st.expander(
                        "🔧 Adjust column mappings", expanded=not mapped.get("name")
                    ):
                        all_cols = ["(not found)"] + list(df.columns)
                        mc1, mc2 = st.columns(2)
                        mapped["name"] = mc1.selectbox(
                            "Name / Script / Scheme *",
                            all_cols,
                            index=(
                                all_cols.index(mapped["name"])
                                if mapped.get("name") in all_cols
                                else 0
                            ),
                            key="map_name",
                        )
                        mapped["buy_price"] = mc2.selectbox(
                            "Buy Price / Avg Cost *",
                            all_cols,
                            index=(
                                all_cols.index(mapped["buy_price"])
                                if mapped.get("buy_price") in all_cols
                                else 0
                            ),
                            key="map_price",
                        )
                        mc3, mc4 = st.columns(2)
                        mapped["quantity"] = mc3.selectbox(
                            "Quantity / Units *",
                            all_cols,
                            index=(
                                all_cols.index(mapped["quantity"])
                                if mapped.get("quantity") in all_cols
                                else 0
                            ),
                            key="map_qty",
                        )
                        mapped["buy_date"] = mc4.selectbox(
                            "Date (optional)",
                            all_cols,
                            index=(
                                all_cols.index(mapped["buy_date"])
                                if mapped.get("buy_date") in all_cols
                                else 0
                            ),
                            key="map_date",
                        )
                        mc5, mc6 = st.columns(2)
                        mapped["ticker"] = mc5.selectbox(
                            "Ticker / Symbol (optional)",
                            all_cols,
                            index=(
                                all_cols.index(mapped["ticker"])
                                if mapped.get("ticker") in all_cols
                                else 0
                            ),
                            key="map_ticker",
                        )
                        mapped["type"] = mc6.selectbox(
                            "Type / Segment (optional)",
                            all_cols,
                            index=(
                                all_cols.index(mapped["type"])
                                if mapped.get("type") in all_cols
                                else 0
                            ),
                            key="map_type",
                        )
                        mc7, mc8 = st.columns(2)
                        mapped["amount"] = mc7.selectbox(
                            "Total Amount / Value (optional, used if price missing)",
                            all_cols,
                            index=(
                                all_cols.index(mapped["amount"])
                                if mapped.get("amount") in all_cols
                                else 0
                            ),
                            key="map_amount",
                        )
                        mapped["note"] = mc8.selectbox(
                            "Note / Remark (optional)",
                            all_cols,
                            index=(
                                all_cols.index(mapped["note"])
                                if mapped.get("note") in all_cols
                                else 0
                            ),
                            key="map_note",
                        )
                        mc9, mc10 = st.columns(2)
                        mapped["trade_type"] = mc9.selectbox(
                            "Buy/Sell column (for tradebook exports)",
                            all_cols,
                            index=(
                                all_cols.index(mapped["trade_type"])
                                if mapped.get("trade_type") in all_cols
                                else 0
                            ),
                            key="map_trade_type",
                            help="If your file has buy & sell rows, select the column. Sell rows will be skipped.",
                        )
                        mapped["sell_value"] = mc10.selectbox(
                            "Sell Value (for P&L reports)",
                            all_cols,
                            index=(
                                all_cols.index(mapped["sell_value"])
                                if mapped.get("sell_value") in all_cols
                                else 0
                            ),
                            key="map_sell_value",
                        )

                    # Show detected format hint
                    trade_type_col = mapped.get("trade_type")
                    if trade_type_col and trade_type_col != "(not found)":
                        st.info(
                            "📋 **Tradebook detected** — only BUY rows will be imported, SELL rows will be skipped."
                        )

                    # Validate minimum required columns
                    name_col = mapped.get("name")
                    price_col = mapped.get("buy_price")
                    qty_col = mapped.get("quantity")
                    amount_col = mapped.get("amount")
                    has_name = name_col and name_col != "(not found)"
                    has_price = price_col and price_col != "(not found)"
                    has_qty = qty_col and qty_col != "(not found)"
                    has_amount = amount_col and amount_col != "(not found)"

                    if not has_name:
                        st.error(
                            "❌ A **Name** column is required. Please select one above."
                        )
                    elif not has_price and not has_qty and not has_amount:
                        st.error(
                            "❌ Need at least one of: **Price**, **Quantity**, or **Amount**."
                        )
                    else:
                        if st.button(
                            "✅ Import All Rows",
                            use_container_width=True,
                            key="smart_import",
                        ):
                            imported = 0
                            skipped = 0
                            skip_reasons = []

                            for _, row in df.iterrows():
                                result = _parse_row_smart(row, mapped)
                                if result is None:
                                    skipped += 1
                                    continue

                                name = result["name"]
                                bp = result["buy_price"]
                                qty = result["quantity"]
                                bd = result["buy_date"]
                                asset_type = result["type"]
                                ticker = result["ticker"]
                                note = result["note"]

                                if bp <= 0 or qty <= 0:
                                    skipped += 1
                                    continue

                                txn = {
                                    "buy_price": bp,
                                    "quantity": qty,
                                    "buy_date": bd,
                                    "note": note,
                                }

                                # Check if holding already exists
                                existing_idx = None
                                for i, existing in enumerate(portfolio_rows):
                                    if existing.get("investment_mode") == "sip":
                                        continue
                                    if (
                                        ticker
                                        and existing.get("ticker", "").upper()
                                        == ticker.upper()
                                    ):
                                        existing_idx = i
                                        break
                                    if existing["name"].lower() == name.lower():
                                        existing_idx = i
                                        break

                                if existing_idx is not None:
                                    ex = portfolio_rows[existing_idx]
                                    txns = ex.get("transactions", [])
                                    if not txns:
                                        old_bp = float(ex.get("buy_price", 0))
                                        old_qty = float(ex.get("quantity", 0))
                                        old_bd = ex.get("buy_date", "")
                                        if old_bp > 0 and old_qty > 0:
                                            txns.append(
                                                {
                                                    "buy_price": old_bp,
                                                    "quantity": old_qty,
                                                    "buy_date": old_bd,
                                                    "note": "",
                                                }
                                            )
                                    txns.append(txn)
                                    ex["transactions"] = txns
                                    agg = _aggregate_transactions(txns)
                                    ex["buy_price"] = agg["weighted_avg_price"]
                                    ex["quantity"] = agg["total_quantity"]
                                    if agg["earliest_date"]:
                                        ex["buy_date"] = agg["earliest_date"].strftime(
                                            "%Y-%m-%d"
                                        )
                                else:
                                    new_entry = {
                                        "name": name,
                                        "ticker": ticker,
                                        "type": asset_type,
                                        "investment_mode": "lumpsum",
                                        "buy_price": bp,
                                        "quantity": qty,
                                        "buy_date": bd,
                                        "sip_monthly": 0,
                                        "sip_date": 0,
                                        "amfi_code": "",
                                        "transactions": [txn],
                                    }
                                    portfolio_rows.append(new_entry)
                                imported += 1

                            _save_portfolio(portfolio_rows)
                            if skipped > 0:
                                st.warning(
                                    f"⚠️ Skipped {skipped} rows (missing or invalid name/price/qty)"
                                )
                            st.success(f"✅ Imported {imported} entries successfully!")
                            st.rerun()

            except Exception as e:
                st.error(f"Error reading file: {e}")

    st.divider()

    # ------ Current Holdings ------
    st.subheader("📋 Current Holdings")

    if not portfolio_rows:
        st.info("Your portfolio is empty. Add your first investment above!")
    else:
        # Fetch prices once for all holdings
        all_tickers = [r.get("ticker", "") for r in portfolio_rows if r.get("ticker")]
        live_prices = _fetch_current_prices(tuple(all_tickers)) if all_tickers else {}

        for idx, row in enumerate(portfolio_rows):
            is_sip = row.get("investment_mode") == "sip"
            sip = float(row.get("sip_monthly", 0))
            transactions = row.get("transactions", [])
            type_label = row.get("type", "stock").replace("_", " ").title()
            ticker = row.get("ticker", "")

            # Compute amount and quantity using helpers
            amount = _get_entry_invested(row)
            quantity = _get_entry_quantity(row)
            buy_price = amount / quantity if quantity > 0 else 0

            # Determine earliest buy date for holding period
            if transactions:
                try:
                    dates = [
                        datetime.strptime(t["buy_date"], "%Y-%m-%d").date()
                        for t in transactions
                        if t.get("buy_date")
                    ]
                    earliest_date = min(dates) if dates else None
                except (ValueError, KeyError):
                    earliest_date = None
                buy_date_str = (
                    earliest_date.strftime("%Y-%m-%d") if earliest_date else ""
                )
            else:
                buy_date_str = row.get("buy_date", "")
                try:
                    earliest_date = (
                        datetime.strptime(buy_date_str, "%Y-%m-%d").date()
                        if buy_date_str
                        else None
                    )
                except ValueError:
                    earliest_date = None

            days_held = (date.today() - earliest_date).days if earliest_date else 0
            months_elapsed = (
                _months_between(earliest_date, date.today()) if earliest_date else 0
            )

            # Tax status
            tax_label = ""
            if days_held > 365:
                tax_label = "LTCG 10%"
            elif days_held > 0:
                remaining = 365 - days_held
                tax_label = f"STCG 15% ({remaining}d to LTCG)"

            # Header text
            if is_sip and sip > 0:
                sip_status = " ⏸️ PAUSED" if is_sip_currently_paused(row) else ""
                header_text = f"🔄 **{row['name']}** — ₹{sip:,.0f}/mo × {max(months_elapsed,1)} months = ₹{amount:,.0f} ({type_label}){sip_status}"
            elif transactions and len(transactions) > 1:
                header_text = f"**{row['name']}** — {quantity:.0f} units × ₹{buy_price:,.2f} avg = ₹{amount:,.0f} ({type_label} · {len(transactions)} txns)"
            else:
                header_text = f"**{row['name']}** — {quantity:.0f} × ₹{buy_price:,.2f} = ₹{amount:,.0f} ({type_label})"

            # Holding period
            if days_held > 365:
                header_text += f" · {days_held / 365.25:.1f}y"
            elif days_held > 0:
                header_text += f" · {days_held}d"

            # Live P&L
            if not is_sip and ticker and ticker in live_prices and amount > 0:
                cur_price = live_prices[ticker]
                cur_value = cur_price * quantity
                pnl = cur_value - amount
                pnl_pct = (pnl / amount * 100) if amount > 0 else 0
                pnl_icon = "🟢" if pnl >= 0 else "🔴"
                header_text += f" · {pnl_icon} ₹{pnl:+,.0f} ({pnl_pct:+.1f}%)"
            with st.expander(header_text):
                # --- Quick Delete ---
                del_col1, del_col2 = st.columns([5, 1])
                with del_col2:
                    if st.button(
                        "🗑️ Delete", key=f"quick_del_{idx}", help=f"Remove {row['name']}"
                    ):
                        st.session_state[f"confirm_del_{idx}"] = True
                if st.session_state.get(f"confirm_del_{idx}"):
                    st.warning(
                        f"Are you sure you want to remove **{row['name']}**? This cannot be undone."
                    )
                    cc1, cc2, _ = st.columns([1, 1, 4])
                    if cc1.button(
                        "✅ Yes, remove", key=f"yes_del_{idx}", type="primary"
                    ):
                        removed_name = portfolio_rows[idx]["name"]
                        portfolio_rows.pop(idx)
                        _save_portfolio(portfolio_rows)
                        st.session_state.pop(f"confirm_del_{idx}", None)
                        st.toast(f"🗑️ Removed **{removed_name}**")
                        st.rerun()
                    if cc2.button("Cancel", key=f"no_del_{idx}"):
                        st.session_state.pop(f"confirm_del_{idx}", None)
                        st.rerun()

                # --- Detail metrics ---
                if is_sip:
                    sip_paused = is_sip_currently_paused(row)
                    pause_periods = row.get("sip_pause_periods", [])
                    # Count paused months
                    paused_months = 0
                    if pause_periods and buy_date_str:
                        try:
                            bd = datetime.strptime(buy_date_str, "%Y-%m-%d").date()
                            cur = bd
                            for _ in range(max(months_elapsed, 1)):
                                if _is_month_paused(cur.year, cur.month, pause_periods):
                                    paused_months += 1
                                m = cur.month + 1
                                y = cur.year
                                if m > 12:
                                    m = 1
                                    y += 1
                                cur = cur.replace(year=y, month=m)
                        except ValueError:
                            pass
                    active_months = max(months_elapsed - paused_months, 0)

                    d1, d2, d3, d4 = st.columns(4)
                    sip_label = f"₹{sip:,.0f}" + (" ⏸️" if sip_paused else "")
                    d1.metric("Monthly SIP", sip_label)
                    d2.metric(
                        "Months Active",
                        f"{active_months}"
                        + (f" ({paused_months} paused)" if paused_months else ""),
                    )
                    d3.metric("Total Invested", f"₹{amount:,.0f}")
                    d4.metric("Tax Status", tax_label if tax_label else "—")
                    if buy_date_str:
                        status_text = "⏸️ PAUSED" if sip_paused else "▶️ Active"
                        st.caption(
                            f"📅 SIP started {buy_date_str} · {status_text} · {months_elapsed} months total ({days_held} days)"
                        )

                    # --- Pause / Resume buttons ---
                    p_col1, p_col2, _ = st.columns([1, 1, 4])
                    if sip_paused:
                        if p_col1.button("▶️ Resume SIP", key=f"resume_{idx}"):
                            periods = portfolio_rows[idx].setdefault(
                                "sip_pause_periods", []
                            )
                            if periods:
                                periods[-1]["resume_date"] = date.today().strftime(
                                    "%Y-%m-%d"
                                )
                            _save_portfolio(portfolio_rows)
                            st.toast(f"▶️ Resumed SIP for **{row['name']}**")
                            st.rerun()
                    else:
                        if p_col1.button("⏸️ Pause SIP", key=f"pause_{idx}"):
                            periods = portfolio_rows[idx].setdefault(
                                "sip_pause_periods", []
                            )
                            periods.append(
                                {
                                    "pause_date": date.today().strftime("%Y-%m-%d"),
                                    "resume_date": None,
                                }
                            )
                            _save_portfolio(portfolio_rows)
                            st.toast(f"⏸️ Paused SIP for **{row['name']}**")
                            st.rerun()

                    # Show pause history if any
                    if pause_periods:
                        with st.expander("📋 Pause History"):
                            for pi, pp in enumerate(pause_periods, 1):
                                p_start = pp.get("pause_date", "?")
                                p_end = pp.get("resume_date")
                                if p_end:
                                    st.caption(
                                        f"{pi}. Paused {p_start} → Resumed {p_end}"
                                    )
                                else:
                                    st.caption(
                                        f"{pi}. Paused since {p_start} (ongoing)"
                                    )

                elif ticker and ticker in live_prices:
                    cur_price = live_prices[ticker]
                    cur_value = cur_price * quantity
                    pnl = cur_value - amount
                    pnl_pct = (pnl / amount * 100) if amount > 0 else 0
                    d1, d2, d3, d4 = st.columns(4)
                    d1.metric("Current Price", f"₹{cur_price:,.2f}")
                    d2.metric("Current Value", f"₹{cur_value:,.0f}")
                    d3.metric("P&L", f"₹{pnl:+,.0f}", f"{pnl_pct:+.1f}%")
                    d4.metric("Tax Status", tax_label if tax_label else "—")
                    if days_held > 0:
                        st.caption(
                            f"📅 Bought on {buy_date_str} · Held for {days_held} days"
                        )

                # --- Transaction Summary (for multi-transaction lumpsum) ---
                if transactions and len(transactions) > 1 and not is_sip:
                    agg = _aggregate_transactions(transactions)
                    st.markdown("##### 📊 Overall Summary")
                    s1, s2, s3 = st.columns(3)
                    s1.metric("Total Units", f"{agg['total_quantity']:.0f}")
                    s2.metric("Total Invested", f"₹{agg['total_invested']:,.2f}")
                    s3.metric("Avg Price/Unit", f"₹{agg['weighted_avg_price']:,.2f}")

                    if agg["earliest_date"] and agg["latest_date"]:
                        span_text = f"📅 Purchases from {agg['earliest_date'].strftime('%d %b %Y')} to {agg['latest_date'].strftime('%d %b %Y')}"
                        st.caption(span_text)

                    if agg["largest_qty_txn"]:
                        t = agg["largest_qty_txn"]
                        st.caption(
                            f"📈 Largest purchase: {float(t['quantity']):.0f} units on {t.get('buy_date', '?')} "
                            f"at ₹{float(t['buy_price']):,.2f}"
                        )
                    if (
                        agg["highest_price_txn"]
                        and agg["highest_price_txn"] != agg["largest_qty_txn"]
                    ):
                        t = agg["highest_price_txn"]
                        st.caption(
                            f"💰 Highest price paid: ₹{float(t['buy_price']):,.2f} "
                            f"for {float(t['quantity']):.0f} unit(s) on {t.get('buy_date', '?')}"
                        )

                    # Transaction table
                    import pandas as pd

                    txn_data = []
                    for ti, txn in enumerate(transactions, 1):
                        txn_data.append(
                            {
                                "#": ti,
                                "Date": txn.get("buy_date", ""),
                                "Qty": float(txn.get("quantity", 0)),
                                "Price (₹)": float(txn.get("buy_price", 0)),
                                "Amount (₹)": round(
                                    float(txn.get("quantity", 0))
                                    * float(txn.get("buy_price", 0)),
                                    2,
                                ),
                                "Note": txn.get("note", ""),
                            }
                        )
                    st.dataframe(
                        pd.DataFrame(txn_data),
                        use_container_width=True,
                        hide_index=True,
                    )

                st.divider()

                # --- Edit form ---
                if is_sip:
                    # SIP edit form
                    with st.form(f"edit_{idx}", clear_on_submit=False):
                        ec1, ec2 = st.columns(2)
                        edit_name = ec1.text_input(
                            "Name", value=row["name"], key=f"en_{idx}"
                        )
                        edit_type = ec2.selectbox(
                            "Type",
                            ["mutual_fund", "stock"],
                            index=0 if row.get("type") == "mutual_fund" else 1,
                            key=f"et_{idx}",
                        )

                        ec3, ec4, ec5 = st.columns(3)
                        edit_sip = ec3.number_input(
                            "Monthly Amount (₹)",
                            min_value=0,
                            step=100,
                            value=int(sip),
                            key=f"es_{idx}",
                        )
                        edit_sip_date = ec4.number_input(
                            "Debit Date (day)",
                            min_value=1,
                            max_value=28,
                            step=1,
                            value=max(1, int(float(row.get("sip_date", 5)))),
                            key=f"esd_{idx}",
                        )
                        edit_start_date = ec5.date_input(
                            "Start Date",
                            value=(
                                datetime.strptime(buy_date_str, "%Y-%m-%d").date()
                                if buy_date_str
                                else date.today()
                            ),
                            key=f"ebd_{idx}",
                        )

                        with st.expander("Advanced"):
                            aec1, aec2 = st.columns(2)
                            edit_ticker = aec1.text_input(
                                "Ticker (auto-detected)",
                                value=row.get("ticker", ""),
                                key=f"etk_{idx}",
                            )
                            edit_amfi = aec2.text_input(
                                "AMFI Code (auto-detected)",
                                value=row.get("amfi_code", ""),
                                key=f"eam_{idx}",
                            )

                        btn_col1, btn_col2 = st.columns(2)
                        save_btn = btn_col1.form_submit_button("💾 Save Changes")
                        delete_btn = btn_col2.form_submit_button("🗑️ Remove")

                        if save_btn:
                            if not edit_name.strip():
                                st.error("Name cannot be empty.")
                            elif edit_sip <= 0:
                                st.error("Monthly amount must be greater than 0.")
                            else:
                                portfolio_rows[idx] = {
                                    "name": edit_name.strip(),
                                    "ticker": edit_ticker.strip(),
                                    "type": edit_type,
                                    "investment_mode": "sip",
                                    "buy_price": 0,
                                    "quantity": 0,
                                    "buy_date": edit_start_date.strftime("%Y-%m-%d"),
                                    "sip_monthly": edit_sip,
                                    "sip_date": edit_sip_date,
                                    "amfi_code": edit_amfi.strip(),
                                    "sip_pause_periods": row.get(
                                        "sip_pause_periods", []
                                    ),
                                }
                                _save_portfolio(portfolio_rows)
                                st.success(f"✅ Updated **{edit_name.strip()}**")
                                st.rerun()

                        if delete_btn:
                            removed_name = portfolio_rows[idx]["name"]
                            portfolio_rows.pop(idx)
                            _save_portfolio(portfolio_rows)
                            st.success(f"🗑️ Removed **{removed_name}**")
                            st.rerun()
                else:
                    # Lump-sum: Add another transaction form
                    if transactions:
                        with st.form(f"add_txn_{idx}", clear_on_submit=True):
                            st.markdown("**➕ Add Another Transaction**")
                            tc1, tc2, tc3 = st.columns(3)
                            txn_price = tc1.number_input(
                                "Buy Price (₹)",
                                min_value=0.0,
                                step=1.0,
                                value=0.0,
                                key=f"tp_{idx}",
                            )
                            txn_qty = tc2.number_input(
                                "Quantity",
                                min_value=0.0,
                                step=1.0,
                                value=0.0,
                                key=f"tq_{idx}",
                            )
                            txn_date = tc3.date_input(
                                "Buy Date", value=date.today(), key=f"td_{idx}"
                            )
                            txn_note = st.text_input("Note (optional)", key=f"tn_{idx}")
                            txn_submit = st.form_submit_button("➕ Add Transaction")
                            if txn_submit:
                                if txn_price <= 0 or txn_qty <= 0:
                                    st.error(
                                        "Price and quantity must be greater than 0."
                                    )
                                else:
                                    new_txn = {
                                        "buy_price": txn_price,
                                        "quantity": txn_qty,
                                        "buy_date": txn_date.strftime("%Y-%m-%d"),
                                        "note": txn_note.strip(),
                                    }
                                    portfolio_rows[idx]["transactions"].append(new_txn)
                                    agg = _aggregate_transactions(
                                        portfolio_rows[idx]["transactions"]
                                    )
                                    portfolio_rows[idx]["buy_price"] = agg[
                                        "weighted_avg_price"
                                    ]
                                    portfolio_rows[idx]["quantity"] = agg[
                                        "total_quantity"
                                    ]
                                    if agg["earliest_date"]:
                                        portfolio_rows[idx]["buy_date"] = agg[
                                            "earliest_date"
                                        ].strftime("%Y-%m-%d")
                                    _save_portfolio(portfolio_rows)
                                    st.success(
                                        f"✅ Added transaction: {txn_qty:.0f} × ₹{txn_price:,.2f} "
                                        f"(now {agg['total_quantity']:.0f} units total)"
                                    )
                                    st.rerun()

                        # Delete individual transactions
                        if len(transactions) > 1:
                            for ti, txn in enumerate(transactions):
                                tc1, tc2 = st.columns([4, 1])
                                tc1.caption(
                                    f"Txn {ti+1}: {float(txn.get('quantity',0)):.0f} × "
                                    f"₹{float(txn.get('buy_price',0)):,.2f} on {txn.get('buy_date','')} "
                                    f"{txn.get('note','')}"
                                )
                                if tc2.button("🗑️", key=f"del_txn_{idx}_{ti}"):
                                    portfolio_rows[idx]["transactions"].pop(ti)
                                    txns_left = portfolio_rows[idx]["transactions"]
                                    if txns_left:
                                        agg = _aggregate_transactions(txns_left)
                                        portfolio_rows[idx]["buy_price"] = agg[
                                            "weighted_avg_price"
                                        ]
                                        portfolio_rows[idx]["quantity"] = agg[
                                            "total_quantity"
                                        ]
                                        if agg["earliest_date"]:
                                            portfolio_rows[idx]["buy_date"] = agg[
                                                "earliest_date"
                                            ].strftime("%Y-%m-%d")
                                    _save_portfolio(portfolio_rows)
                                    st.rerun()

                    # Edit holding metadata
                    with st.form(f"edit_{idx}", clear_on_submit=False):
                        st.markdown("**✏️ Edit Holding**")
                        ec1, ec2 = st.columns(2)
                        edit_name = ec1.text_input(
                            "Name", value=row["name"], key=f"en_{idx}"
                        )
                        edit_type = ec2.selectbox(
                            "Type",
                            ["stock", "mutual_fund"],
                            index=0 if row.get("type", "stock") == "stock" else 1,
                            key=f"et_{idx}",
                        )

                        if not transactions:
                            ec3, ec4, ec5 = st.columns(3)
                            edit_buy_price = ec3.number_input(
                                "Buy Price (₹)",
                                min_value=0.0,
                                step=1.0,
                                value=float(row.get("buy_price", 0)),
                                key=f"ebp_{idx}",
                            )
                            edit_quantity = ec4.number_input(
                                "Quantity",
                                min_value=0.0,
                                step=1.0,
                                value=float(row.get("quantity", 1)),
                                key=f"eq_{idx}",
                            )
                            edit_buy_date = ec5.date_input(
                                "Buy Date",
                                value=(
                                    datetime.strptime(buy_date_str, "%Y-%m-%d").date()
                                    if buy_date_str
                                    else date.today()
                                ),
                                key=f"ebd_{idx}",
                            )

                        with st.expander("Advanced"):
                            aec1, aec2 = st.columns(2)
                            edit_ticker = aec1.text_input(
                                "Ticker (auto-detected)",
                                value=row.get("ticker", ""),
                                key=f"etk_{idx}",
                            )
                            edit_amfi = aec2.text_input(
                                "AMFI Code (auto-detected)",
                                value=row.get("amfi_code", ""),
                                key=f"eam_{idx}",
                            )

                        btn_col1, btn_col2 = st.columns(2)
                        save_btn = btn_col1.form_submit_button("💾 Save Changes")
                        delete_btn = btn_col2.form_submit_button("🗑️ Remove Holding")

                        if save_btn:
                            if not edit_name.strip():
                                st.error("Name cannot be empty.")
                            else:
                                portfolio_rows[idx]["name"] = edit_name.strip()
                                portfolio_rows[idx]["ticker"] = edit_ticker.strip()
                                portfolio_rows[idx]["type"] = edit_type
                                portfolio_rows[idx]["amfi_code"] = edit_amfi.strip()
                                if not transactions:
                                    portfolio_rows[idx]["buy_price"] = edit_buy_price
                                    portfolio_rows[idx]["quantity"] = edit_quantity
                                    portfolio_rows[idx]["buy_date"] = (
                                        edit_buy_date.strftime("%Y-%m-%d")
                                    )
                                _save_portfolio(portfolio_rows)
                                st.success(f"✅ Updated **{edit_name.strip()}**")
                                st.rerun()

                        if delete_btn:
                            removed_name = portfolio_rows[idx]["name"]
                            portfolio_rows.pop(idx)
                            _save_portfolio(portfolio_rows)
                            st.success(f"🗑️ Removed **{removed_name}**")
                            st.rerun()
