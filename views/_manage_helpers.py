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


PORTFOLIO_PATH = "data/portfolio.json"


def _months_between(start_date, end_date):
    """Calculate number of months between two dates."""
    return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)


@st.cache_data(ttl=300)
def _fetch_current_prices(tickers_tuple):
    """Fetch current market prices for a list of tickers."""
    prices = {}
    for t in tickers_tuple:
        try:
            hist = yf.Ticker(t).history(period="1d")
            if not hist.empty:
                prices[t] = round(hist["Close"].iloc[-1], 2)
        except Exception:
            pass
    return prices


def _save_portfolio(rows):
    """Write portfolio rows to JSON or DB (atomic write to prevent corruption)."""
    user_id = auth.get_user_id()
    if db.is_db_available() and user_id:
        db.save_portfolio(rows, user_id)
        st.cache_data.clear()
        return
    os.makedirs(os.path.dirname(PORTFOLIO_PATH), exist_ok=True)
    tmp_path = PORTFOLIO_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)
    os.replace(tmp_path, PORTFOLIO_PATH)
    st.cache_data.clear()


def _get_entry_invested(row):
    """Get total invested for a portfolio entry (handles multi-txn and SIP, including pauses)."""
    is_sip = row.get("investment_mode") == "sip"
    transactions = row.get("transactions", [])

    if is_sip:
        sip_amt = float(row.get("sip_monthly", 0))
        bd_str = row.get("buy_date", "")
        pause_periods = row.get("sip_pause_periods", [])
        if sip_amt > 0 and bd_str:
            try:
                bd = datetime.strptime(bd_str, "%Y-%m-%d").date()
                months = _months_between(bd, date.today())
                if pause_periods:
                    # Count only active months
                    active_months = 0
                    cur = bd
                    for _ in range(max(months, 1)):
                        if not _is_month_paused(cur.year, cur.month, pause_periods):
                            active_months += 1
                        m = cur.month + 1
                        y = cur.year
                        if m > 12:
                            m = 1
                            y += 1
                        cur = cur.replace(year=y, month=m)
                    return sip_amt * max(active_months, 1)
                return sip_amt * max(months, 1)
            except ValueError:
                return sip_amt
        return sip_amt
    elif transactions:
        agg = _aggregate_transactions(transactions)
        return agg["total_invested"]
    else:
        return float(row.get("buy_price", 0)) * float(row.get("quantity", 1))


def _get_entry_quantity(row):
    """Get total quantity for a portfolio entry (handles multi-txn)."""
    transactions = row.get("transactions", [])
    if transactions:
        return sum(float(t.get("quantity", 0)) for t in transactions)
    return float(row.get("quantity", 1))


def _load_raw_portfolio():
    """Load portfolio as list of dicts from DB or JSON."""
    user_id = auth.get_user_id()
    if db.is_db_available() and user_id:
        return db.load_portfolio(user_id)
    try:
        with open(PORTFOLIO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


# --- Smart CSV/Excel column detection ---

# Keyword patterns for each target field (order = priority).
# Covers all major Indian broker P&L / holdings / tradebook export formats:
#   Zerodha (Console Tax P&L, tradebook, holdings)
#   Groww (Stocks P&L, holdings)
#   Upstox (P&L, tradebook, holdings)
#   ICICI Direct (Capital Gain Report, holdings, tradebook)
#   Angel One (P&L, holdings)
#   INDMoney (P&L, holdings)
#   MFCentral / CAMS / KFintech (MF statements)
#   Kuvera, Paytm Money, 5paisa, Motilal Oswal, HDFC Securities
_COL_PATTERNS = {
    "name": [
        # Zerodha Console: "scrip_name", "tradingsymbol"; Groww: "Stock Name"
        # INDMoney: "Script Name"; ICICI: "Stock/Contract"; Angel One: "Scrip Name"
        # Upstox: "Instrument Name", "Company Name"
        r"^(stock|scrip|script|scheme|fund|company|instrument|security|holding|contract)[\s_]?name",
        r"^(name|scrip|script|stock|scheme|company|instrument|security)$",
        r"^trading[\s_]?symbol$",
        r"^(scrip|script)[\s_]?(name|code)$",
        r"^stock[\s_]?/?[\s_]?contract$",
        # MF: CAMS/KFintech: "scheme_name", MFCentral: "Scheme Name"
        r"^(scheme|fund|amc|portfolio|folio)[\s_]?(name|desc)",
        r"^(description|particulars|narration|contract[\s_]?description)$",
        # Standalone matches
        r"^(stock|scrip|underlying)$",
    ],
    "buy_price": [
        # Zerodha: "buy_average", "buy_avg", "Avg. cost"
        # Groww: "Buy Price", "Avg. Buy Price"; INDMoney: "Buy Rate", "Avg Buy Price"
        # ICICI: "Purchase Price", "Buy Rate"; Upstox: "Buy Avg."
        # Angel One: "Buy Avg Price"
        r"(buy|purchase|acquisition)[\s_]?(price|rate|avg|average|cost)",
        r"^(avg|average)[\s_]?(cost|price|rate|buy[\s_]?price|buy[\s_]?rate)$",
        r"^(price|rate|nav|cost[\s_]?price|avg[\s_]?cost|average[\s_]?price)$",
        r"^buy[\s_]?avg\.?$",
        r"^(weighted[\s_]?avg|unit[\s_]?cost|per[\s_]?unit[\s_]?cost)$",
        r"^(purchase[\s_]?price|purchase[\s_]?rate|cost[\s_]?of[\s_]?acquisition)$",
        r"^cost[\s_]?per[\s_]?(unit|share)$",
        r"^buy[\s_]?rate$",
        # ICICI: "Buy Rate/Rs."
        r"^buy[\s_]?rate[\s_]?/?[\s_]?rs\.?$",
    ],
    "quantity": [
        # Zerodha: "quantity", "Qty."; Groww: "Quantity"
        # INDMoney: "Buy Qty"; ICICI: "Qty"; Upstox: "Qty"
        r"^(quantity|qty|units|shares|volume|bal[\s_]?qty)\.?$",
        r"(buy[\s_]?qty|sell[\s_]?qty|net[\s_]?qty|available[\s_]?qty|holding[\s_]?qty|balance[\s_]?units)",
        r"^no[\s_]?of[\s_]?(shares|units)$",
        r"^(total[\s_]?qty|total[\s_]?units|total[\s_]?shares)$",
    ],
    "buy_date": [
        # Zerodha: "trade_date"; Groww: "Buy Date"; ICICI: "Purchase Date"
        # Upstox: "Trade Date"; Angel One: "Buy Date"
        r"(buy|purchase|trade|transaction|order|acquisition)[\s_]?date",
        r"^(date|dt|trade[\s_]?dt|txn[\s_]?date|order[\s_]?date)$",
        r"^(settlement[\s_]?date|execution[\s_]?date|value[\s_]?date)$",
        # CAMS/KFintech/MFCentral: "Transaction Date"
        r"^(transaction|trans|trxn|txn)[\s_]?date$",
    ],
    "ticker": [
        # Zerodha: "tradingsymbol", "symbol"; Groww: "Symbol"; Upstox: "Symbol"
        # ICICI: "Symbol/Series"; Angel One: "Symbol"
        r"^(ticker|symbol|trading[\s_]?symbol|nse[\s_]?symbol|bse[\s_]?symbol)$",
        r"^symbol[\s_]?/?[\s_]?series$",
        r"^(scrip[\s_]?code|scrip[\s_]?id|script[\s_]?code|bse[\s_]?code|nse[\s_]?code)$",
        # ISIN — universal identifier across all brokers
        r"^(isin|isin[\s_]?code|isin[\s_]?number|isin[\s_]?no|instrument[\s_]?key)$",
        r"(symbol|ticker)$",
    ],
    "type": [
        # Zerodha: "segment" (EQ/FO/CDS/COM); Groww: "Segment"
        # ICICI: "Segment"; Upstox: "Segment"; Angel One: "Segment"
        r"^(type|asset[\s_]?type|segment|exchange|instrument[\s_]?type|asset[\s_]?class|category)$",
        r"^(market|series|product[\s_]?type|trade[\s_]?segment)$",
    ],
    "amount": [
        # Zerodha P&L: "buy_value"; Groww: "Invested Value", "Buy Value"
        # INDMoney: "Buy Value", "Invested"; ICICI: "Purchase Value"
        # Upstox: "Buy Value"
        r"^(buy[\s_]?value|invested[\s_]?value|invested|investment|cost[\s_]?value|purchase[\s_]?value)$",
        r"(invested|total)[\s_]?(amount|value|cost)",
        r"^(amount|value|market[\s_]?value|current[\s_]?value)$",
        r"(buy|purchase)[\s_]?(amount|value)",
        r"^(total[\s_]?cost|total[\s_]?investment|cost[\s_]?of[\s_]?acquisition)$",
    ],
    "sell_price": [
        # Zerodha: "sell_average"; Groww: "Sell Price"; ICICI: "Sell Rate"
        r"(sell|sale)[\s_]?(price|rate|avg|average|cost)",
        r"^sell[\s_]?avg\.?(erage)?$",
        r"^(ltp|last[\s_]?traded[\s_]?price|current[\s_]?price|cur[\s_]?price|cmp)$",
        r"^sell[\s_]?rate[\s_]?/?[\s_]?rs\.?$",
    ],
    "sell_value": [
        # Zerodha P&L: "sell_value"; Groww: "Sell Value"
        r"^sell[\s_]?value$",
        r"(sell|sale)[\s_]?(value|amount)",
    ],
    "pnl": [
        # Zerodha: "realized_pnl", "P&L"; Groww: "Returns"; Upstox: "Net P&L"
        # ICICI: "Profit/Loss"; INDMoney: "Realized P&L"; Angel One: "P&L"
        r"(realized|realised|unrealized|unrealised)?[\s_]?(p[\s_]?&?[\s_]?l|pnl|profit[\s_]?(&|and)?[\s_]?loss)",
        r"^(returns|return|net[\s_]?pnl|net[\s_]?profit|net[\s_]?gain|capital[\s_]?gain)s?$",
        r"^(profit|loss|gain|profit[\s_]?/?[\s_]?loss)$",
        r"^(stcg|ltcg|short[\s_]?term|long[\s_]?term)[\s_]?(gain|profit|p[\s_]?&?[\s_]?l)$",
    ],
    "trade_type": [
        # Zerodha tradebook: "trade_type" (buy/sell); All brokers: "Transaction Type"
        # ICICI: "Buy/Sell"; Groww: "Type" (in tradebook context)
        r"^(trade[\s_]?type|transaction[\s_]?type|order[\s_]?type|side|action)$",
        r"^(type[\s_]?of[\s_]?transaction|buy[\s_]?/?[\s_]?sell|b[\s_]?/?[\s_]?s)$",
    ],
    "holding_period": [
        # Groww: "Holding Period"; Zerodha Tax P&L: "holding_type" (STCG/LTCG)
        r"^(holding[\s_]?period|holding[\s_]?type|holding[\s_]?duration)$",
        r"^(short[\s_]?term|long[\s_]?term|stcg|ltcg|capital[\s_]?gain[\s_]?type)$",
    ],
    "charges": [
        # All brokers include charges in P&L: brokerage, STT, GST, SEBI, turnover charges
        r"^(charges|total[\s_]?charges|brokerage|stt|stamp[\s_]?duty|turnover[\s_]?charges)$",
        r"^(gst|sebi[\s_]?(charges|fees)|exchange[\s_]?charges|dp[\s_]?charges)$",
        r"^(transaction[\s_]?charges|other[\s_]?charges|statutory[\s_]?charges)$",
    ],
    "note": [
        r"^(note|notes|remark|remarks|comment|comments|memo|tag)s?$",
        # MF: Folio number — not useful for import but must be recognised
        # to prevent heuristic from treating it as buy_price
        r"^(folio[\s_]?no\.?|folio[\s_]?number|folio)$",
        # Other non-import columns that should be skipped by heuristics
        r"^(source|amc|sub[\s_-]?category|client[\s_]?(code|id|name))$",
    ],
}


def _smart_detect_columns(df):
    """Auto-detect which DataFrame columns map to portfolio fields.

    Works with exports from Zerodha, Groww, INDMoney, Angel One, MFCentral,
    CAMS, KFintech, Kuvera, ICICI Direct, HDFC Securities, and generic formats.
    """
    import re

    mapped = {k: None for k in _COL_PATTERNS}
    used_cols = set()

    for field, patterns in _COL_PATTERNS.items():
        for pattern in patterns:
            for col in df.columns:
                if col in used_cols:
                    continue
                col_clean = (
                    col.strip()
                    .lower()
                    .replace("-", " ")
                    .replace("_", " ")
                    .replace(".", " ")
                    .rstrip()
                )
                if re.search(pattern, col_clean, re.IGNORECASE):
                    mapped[field] = col
                    used_cols.add(col)
                    break
            if mapped[field]:
                break

    # --- Heuristic: detect if this is a tradebook (has buy/sell rows) ---
    # Zerodha tradebook has "trade_type" column with "buy"/"sell" values
    is_tradebook = mapped.get("trade_type") is not None

    # --- Heuristic: P&L report detection ---
    # Zerodha/Groww P&L reports have "buy_value" and "sell_value" but no per-unit "buy_price".
    # If we matched "buy_value" as "amount" but have no "buy_price", use amount÷qty in parse.
    # Also: Zerodha Tax P&L has segment column (EQ/FO/CDS) — skip F&O/commodity rows in parse.
    is_pnl_report = (
        mapped.get("pnl") is not None or mapped.get("sell_value") is not None
    )

    # --- Heuristic: if "holding_period" or "charges" detected, this is likely a P&L report ---
    if mapped.get("holding_period") or mapped.get("charges"):
        is_pnl_report = True

    # --- Heuristic fallback: find name column by data inspection ---
    if not mapped["name"]:
        for col in df.columns:
            if col in used_cols:
                continue
            sample = df[col].dropna().head(20)
            if len(sample) == 0:
                continue
            str_vals = sample.astype(str)
            avg_len = str_vals.str.len().mean()
            alpha_ratio = str_vals.str.replace(
                r"[^a-zA-Z]", "", regex=True
            ).str.len().sum() / max(str_vals.str.len().sum(), 1)
            if avg_len > 3 and alpha_ratio > 0.5:
                mapped["name"] = col
                used_cols.add(col)
                break

    # --- Heuristic fallback: find numeric columns for price/qty ---
    # Skip buy_price heuristic if amount and quantity are both mapped
    # (price can be derived as amount/qty in _parse_row_smart)
    need_price_heuristic = not mapped["buy_price"] and not (
        mapped.get("amount") and mapped.get("quantity")
    )
    if need_price_heuristic or not mapped["quantity"]:
        numeric_cols = []
        for c in df.columns:
            if c in used_cols:
                continue
            # Try to coerce to numeric
            try:
                nums = (
                    df[c]
                    .dropna()
                    .astype(str)
                    .str.replace(",", "")
                    .str.replace("₹", "")
                    .str.strip()
                )
                nums = nums[nums != ""]
                if len(nums) == 0:
                    continue
                converted = nums.astype(float)
                numeric_cols.append((c, converted.median(), converted))
            except (ValueError, TypeError):
                continue

        # Sort by median descending — higher medians are more likely prices
        numeric_cols.sort(key=lambda x: x[1], reverse=True)

        for col, median, vals in numeric_cols:
            if need_price_heuristic and not mapped["buy_price"] and median > 1:
                mapped["buy_price"] = col
                used_cols.add(col)
            elif not mapped["quantity"] and median > 0:
                mapped["quantity"] = col
                used_cols.add(col)

    # --- Heuristic: detect date columns by parsing sample values ---
    if not mapped["buy_date"]:
        import pandas as pd

        for col in df.columns:
            if col in used_cols:
                continue
            sample = df[col].dropna().head(10)
            if len(sample) == 0:
                continue
            try:
                parsed = pd.to_datetime(sample, dayfirst=True, errors="coerce")
                valid_ratio = parsed.notna().sum() / len(sample)
                if valid_ratio >= 0.7:
                    mapped["buy_date"] = col
                    used_cols.add(col)
                    break
            except Exception:
                continue

    return mapped


def _find_data_rows(file_obj, is_excel):
    """Pre-process a file to find the actual data table, skipping metadata headers.

    Many broker P&L exports (Groww, Zerodha Console, ICICI Direct) have metadata
    rows at the top (client name, summary, charges) before the real data table.
    Groww files also have TWO tables ("Realised trades" then "Unrealised trades")
    with separate header rows.

    Returns a single DataFrame with all data rows combined (both sections if present).
    """
    import pandas as pd
    import re

    # Known header keywords that indicate the start of a data table row
    _HEADER_KEYWORDS = {
        "stock name",
        "scrip name",
        "script name",
        "scheme name",
        "company name",
        "instrument name",
        "name",
        "stock",
        "tradingsymbol",
        "trading symbol",
        "scrip",
        "symbol",
        "stock/contract",
        "contract description",
    }

    if is_excel:
        raw = pd.read_excel(file_obj, header=None)
    else:
        try:
            raw = pd.read_csv(file_obj, header=None)
        except UnicodeDecodeError:
            file_obj.seek(0)
            raw = pd.read_csv(file_obj, header=None, encoding="latin-1")

    if raw.empty or len(raw) < 2:
        # Tiny file — just use pandas default
        file_obj.seek(0)
        if is_excel:
            return pd.read_excel(file_obj)
        return pd.read_csv(file_obj)

    # --- Find header row(s) ---
    # A header row is one where multiple cells are non-empty string values
    # that look like column names (not numeric, not too long),
    # and at least 3+ such cells exist in the row.
    header_rows = []
    for idx in range(min(50, len(raw))):
        row_vals = [
            str(v).strip() for v in raw.iloc[idx] if pd.notna(v) and str(v).strip()
        ]
        if len(row_vals) < 3:
            continue
        row_vals_lower = [v.lower() for v in row_vals]

        # Check if this looks like a header row:
        # - At least 3 non-empty cells
        # - Most cells are short strings (< 30 chars)
        # - No purely numeric values (headers are text labels)
        # - Contains at least one known header keyword
        short_count = sum(1 for v in row_vals if len(v) < 30)
        numeric_count = sum(1 for v in row_vals if re.match(r"^-?\d+\.?\d*$", v))

        if short_count >= 3 and numeric_count == 0:
            # Skip summary/aggregate header rows that aren't real data tables
            # e.g. "Total Investments | Current Portfolio Value | Profit/Loss | ..."
            _SUMMARY_KW = {
                "total investments",
                "portfolio value",
                "current portfolio value",
                "profit/loss",
                "profit/loss %",
                "total p&l",
                "net p&l",
                "overall returns",
                "overall p&l",
                "holding summary",
            }
            if any(v in _SUMMARY_KW for v in row_vals_lower):
                continue

            # Check for known keywords
            has_known = any(v in _HEADER_KEYWORDS for v in row_vals_lower)
            # Also match if it looks like a multi-column header (4+ text cells, none numeric)
            if has_known or len(row_vals) >= 4:
                header_rows.append(idx)

    if not header_rows:
        # No header rows found — fallback to pandas default
        file_obj.seek(0)
        if is_excel:
            return pd.read_excel(file_obj)
        return pd.read_csv(file_obj)

    # --- Extract data sections ---
    # For each header row, read until the next header row or empty row or end
    all_dfs = []
    for i, hdr_idx in enumerate(header_rows):
        header = [
            str(v).strip() if pd.notna(v) else f"col_{ci}"
            for ci, v in enumerate(raw.iloc[hdr_idx])
        ]

        # Find data end: next header row, or a row that looks like a section divider
        if i + 1 < len(header_rows):
            end_idx = header_rows[i + 1]
        else:
            end_idx = len(raw)

        # Collect data rows between header and end
        data_rows = []
        for ridx in range(hdr_idx + 1, end_idx):
            row_vals = raw.iloc[ridx].tolist()
            # Skip empty rows
            non_empty = [v for v in row_vals if pd.notna(v) and str(v).strip()]
            if not non_empty:
                continue
            # Skip section labels (single cell with text like "Unrealised trades", "Disclaimer:")
            first = str(row_vals[0]).strip().lower() if pd.notna(row_vals[0]) else ""
            if first in (
                "realised trades",
                "unrealised trades",
                "summary",
                "charges",
                "disclaimer:",
                "p&l",
                "total",
                "",
            ):
                continue
            if first.startswith("this report") or first.startswith("groww"):
                continue
            data_rows.append(row_vals)

        if data_rows:
            section_df = pd.DataFrame(data_rows, columns=header)
            # Drop columns that are all empty
            section_df = section_df.dropna(axis=1, how="all")
            # Drop columns with empty header
            section_df = section_df.loc[:, ~section_df.columns.str.startswith("col_")]
            all_dfs.append(section_df)

    if not all_dfs:
        file_obj.seek(0)
        if is_excel:
            return pd.read_excel(file_obj)
        return pd.read_csv(file_obj)

    # Combine all sections — they may have slightly different column names
    # (e.g. "Sell date" vs "Closing date", "Realised P&L" vs "Unrealised P&L")
    # Normalize column names across sections to enable concatenation
    combined = all_dfs[0]
    for extra_df in all_dfs[1:]:
        # Rename columns in extra_df to match first df where possible
        rename_map = {}
        for col in extra_df.columns:
            cl = col.lower().strip()
            if col not in combined.columns:
                # Try to match by meaning
                if "closing" in cl and "date" in cl:
                    for cc in combined.columns:
                        if "sell" in cc.lower() and "date" in cc.lower():
                            rename_map[col] = cc
                            break
                elif "closing" in cl and ("price" in cl or "value" in cl):
                    for cc in combined.columns:
                        if "sell" in cc.lower() and (
                            "price" in cc.lower() or "value" in cc.lower()
                        ):
                            rename_map[col] = cc
                            break
                elif "unrealised" in cl or "unrealized" in cl:
                    for cc in combined.columns:
                        if (
                            "realised" in cc.lower()
                            or "realized" in cc.lower()
                            or "p&l" in cc.lower()
                        ):
                            rename_map[col] = cc
                            break
        if rename_map:
            extra_df = extra_df.rename(columns=rename_map)

        # Deduplicate column names before concat
        seen = {}
        new_cols = []
        for c in extra_df.columns:
            if c in seen:
                seen[c] += 1
                new_cols.append(f"{c}_{seen[c]}")
            else:
                seen[c] = 0
                new_cols.append(c)
        extra_df.columns = new_cols

        # Also deduplicate combined columns
        seen = {}
        new_cols = []
        for c in combined.columns:
            if c in seen:
                seen[c] += 1
                new_cols.append(f"{c}_{seen[c]}")
            else:
                seen[c] = 0
                new_cols.append(c)
        combined.columns = new_cols

        combined = pd.concat([combined, extra_df], ignore_index=True)

    return combined


def _safe_float(val, default=0.0):
    """Convert value to float, stripping commas and currency symbols."""
    if val is None:
        return default
    try:
        import pandas as pd

        if pd.isna(val):
            return default
    except (TypeError, ValueError):
        pass
    s = (
        str(val)
        .strip()
        .replace(",", "")
        .replace("₹", "")
        .replace("$", "")
        .replace("INR", "")
        .strip()
    )
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _parse_row_smart(row, mapped):
    """Parse a single DataFrame row using the detected column mapping.

    Handles multiple broker formats:
    - Holdings exports (name, price, qty)
    - Tradebook exports (filters buy-only rows from Zerodha/Groww tradebooks)
    - P&L reports (derives price from buy_value/qty if needed)
    """
    import pandas as pd

    name_col = mapped.get("name")
    price_col = mapped.get("buy_price")
    qty_col = mapped.get("quantity")
    date_col = mapped.get("buy_date")
    ticker_col = mapped.get("ticker")
    type_col = mapped.get("type")
    amount_col = mapped.get("amount")
    note_col = mapped.get("note")
    trade_type_col = mapped.get("trade_type")
    pnl_col = mapped.get("pnl")
    holding_period_col = mapped.get("holding_period")

    # --- Tradebook: skip sell rows (only import buys) ---
    if trade_type_col and trade_type_col != "(not found)":
        tt = str(row.get(trade_type_col, "")).strip().lower()
        if tt in ("sell", "s", "sale", "sold", "redemption", "redeem"):
            return None

    # --- P&L / Tax Report: skip non-equity segments (F&O, currency, commodity, intraday) ---
    if type_col and type_col != "(not found)":
        seg = str(row.get(type_col, "")).strip().lower()
        # Skip futures, options, currency derivatives, commodity, intraday speculation
        if any(
            kw in seg
            for kw in (
                "f&o",
                "fo",
                "fut",
                "opt",
                "future",
                "option",
                "cds",
                "currency",
                "comm",
                "commodity",
                "mcx",
                "intraday",
                "speculation",
            )
        ):
            return None

    # --- Name ---
    if not name_col or name_col == "(not found)":
        return None
    name = str(row.get(name_col, "")).strip()
    if not name or name.lower() in ("nan", "none", "", "total", "grand total"):
        return None
    # Skip summary/subtotal rows common in broker P&L exports
    name_check = name.lower().strip()
    if name_check in (
        "total",
        "grand total",
        "sub total",
        "subtotal",
        "net total",
        "overall",
        "summary",
        "net p&l",
        "charges total",
    ) or name_check.startswith("total "):
        return None
    # Clean common suffixes from broker exports
    # Zerodha: "ITC - EQ", "RELIANCE - EQ"; BSE: "ITC - BE"
    # Groww: "ITC (NSE)"; ICICI: "ITC (BSE)"
    for suffix in (
        " - EQ",
        " - BE",
        " - MF",
        "-EQ",
        "-BE",
        "-MF",
        " EQ",
        " (NSE)",
        " (BSE)",
        " (MCX)",
        " - NSE",
        " - BSE",
    ):
        if name.upper().endswith(suffix):
            name = name[: -len(suffix)].strip()

    # --- Price & Quantity ---
    bp = (
        _safe_float(row.get(price_col))
        if price_col and price_col != "(not found)"
        else 0
    )
    qty = _safe_float(row.get(qty_col)) if qty_col and qty_col != "(not found)" else 0
    amt = (
        _safe_float(row.get(amount_col))
        if amount_col and amount_col != "(not found)"
        else 0
    )

    # Negative qty can appear in P&L reports for sold positions — take absolute
    qty = abs(qty)
    amt = abs(amt)

    # Derive missing price or quantity from amount
    if bp > 0 and qty <= 0 and amt > 0:
        qty = round(amt / bp, 4)
    elif qty > 0 and bp <= 0 and amt > 0:
        bp = round(amt / qty, 2)
    elif bp <= 0 and qty <= 0 and amt > 0:
        bp = amt
        qty = 1

    if bp <= 0 or qty <= 0:
        return None

    # --- Date ---
    bd = date.today().strftime("%Y-%m-%d")
    if date_col and date_col != "(not found)":
        bd_raw = row.get(date_col)
        try:
            if pd.notna(bd_raw):
                bd = pd.to_datetime(bd_raw, dayfirst=True).strftime("%Y-%m-%d")
        except Exception:
            pass

    # --- Ticker ---
    ticker = ""
    if ticker_col and ticker_col != "(not found)":
        t = str(row.get(ticker_col, "")).strip()
        if t.lower() not in ("nan", "none", ""):
            ticker = t
            # ISIN → keep as-is (12-char alphanumeric starting with IN)
            if len(ticker) == 12 and ticker[:2].upper() == "IN" and ticker.isalnum():
                pass  # ISIN, keep raw — auto_resolve_ticker will handle it
            # Append .NS if it looks like an NSE symbol without suffix
            elif "." not in ticker and len(ticker) <= 20:
                ticker = ticker.upper() + ".NS"

    # If no ticker but name looks like a trading symbol (all caps, short), use it
    if not ticker and name.isupper() and len(name) <= 20 and " " not in name:
        ticker = name + ".NS"

    # --- Type ---
    asset_type = "stock"
    if type_col and type_col != "(not found)":
        t = str(row.get(type_col, "")).strip().lower()
        if any(kw in t for kw in ("mf", "mutual", "fund", "scheme", "nav", "sip")):
            asset_type = "mutual_fund"
        elif any(kw in t for kw in ("eq", "stock", "nse", "bse", "share", "equity")):
            asset_type = "stock"
    # Also infer from name
    name_lower = name.lower()
    if any(
        kw in name_lower
        for kw in (
            "fund",
            "scheme",
            "growth",
            "direct plan",
            "regular plan",
            "idcw",
            "dividend",
            " nav",
            "flexi cap",
            "small cap",
            "large cap",
            "mid cap",
            "multi cap",
            "hybrid",
            "liquid",
            "gilt",
            "debt fund",
            "elss",
            "index fund",
            "nifty",
            "sensex",
            "etf",
        )
    ):
        asset_type = "mutual_fund"

    # --- Note ---
    note = ""
    if note_col and note_col != "(not found)":
        n = str(row.get(note_col, "")).strip()
        if n.lower() not in ("nan", "none", ""):
            note = n

    return {
        "name": name,
        "buy_price": round(bp, 2),
        "quantity": round(qty, 4),
        "buy_date": bd,
        "ticker": ticker,
        "type": asset_type,
        "note": note,
    }


