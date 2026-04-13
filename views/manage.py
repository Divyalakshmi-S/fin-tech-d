import streamlit as st
import json
import os
from datetime import datetime, date

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
    """Write portfolio rows to JSON (atomic write to prevent corruption)."""
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
    """Load portfolio as list of dicts."""
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

    # ------ Portfolio Summary ------
    if portfolio_rows:
        tickers = [r.get("ticker", "") for r in portfolio_rows if r.get("ticker")]
        current_prices = _fetch_current_prices(tuple(tickers)) if tickers else {}

        total_invested = 0
        total_current = 0
        ltcg_count = 0
        stcg_count = 0
        sip_count = 0
        sip_total_monthly = 0
        for row in portfolio_rows:
            is_sip = row.get("investment_mode") == "sip"
            ticker = row.get("ticker", "")
            invested = _get_entry_invested(row)
            qty = _get_entry_quantity(row)
            sip_amt = float(row.get("sip_monthly", 0))

            if is_sip:
                sip_count += 1
                sip_total_monthly += sip_amt

            total_invested += invested

            if not is_sip and ticker and ticker in current_prices:
                total_current += current_prices[ticker] * qty
            else:
                total_current += invested

            # Tax status from earliest buy date
            transactions = row.get("transactions", [])
            if transactions:
                dates = []
                for txn in transactions:
                    try:
                        dates.append(
                            datetime.strptime(txn["buy_date"], "%Y-%m-%d").date()
                        )
                    except (ValueError, KeyError):
                        pass
                if dates:
                    earliest = min(dates)
                    days = (date.today() - earliest).days
                    if days > 365:
                        ltcg_count += 1
                    else:
                        stcg_count += 1
            else:
                bd_str = row.get("buy_date", "")
                if bd_str:
                    try:
                        bd = datetime.strptime(bd_str, "%Y-%m-%d").date()
                        days = (date.today() - bd).days
                        if days > 365:
                            ltcg_count += 1
                        else:
                            stcg_count += 1
                    except ValueError:
                        pass

        total_pnl = total_current - total_invested
        pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Holdings",
            f"{len(portfolio_rows)}",
            f"{sip_count} SIPs · ₹{sip_total_monthly:,.0f}/mo" if sip_count else None,
        )
        c2.metric("Invested", f"₹{total_invested:,.0f}")
        c3.metric("Current Value", f"₹{total_current:,.0f}", f"{pnl_pct:+.1f}%")
        c4.metric(
            "P&L", f"₹{total_pnl:+,.0f}", f"LTCG: {ltcg_count} · STCG: {stcg_count}"
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
