"""
Holdings analysis engine.
Fetches live market data for each portfolio holding and computes:
- Current price, daily change
- 52-week high/low & distance from them
- 50-day & 200-day moving averages (trend detection)
- 14-day RSI (overbought/oversold)
- Volume spike detection
- YTD & 1-year return
- PE ratio (stocks only)
- SIP value estimation
"""

import csv
import json
import numpy as np
import yfinance as yf
import feedparser
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, date


# ---------------------------------------------------------------------------
# Singleton ThreadPoolExecutor — shared across the module to avoid
# repeatedly creating/destroying thread pools.
# ---------------------------------------------------------------------------
_SHARED_POOL = ThreadPoolExecutor(max_workers=8)


# ---------------------------------------------------------------------------
# Portfolio loader — defined later in file (after AMFI section)
# Re-exported here for import compatibility:
#   from analysis import load_portfolio_extended
# The actual implementation is below the AMFI NAV section.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TROY_OZ_GRAMS = 31.1035
GOLD_PREMIUM = 1.03  # ~3% GST + making for Chennai retail
SILVER_PREMIUM = 1.05  # ~5% premium for Chennai retail


# ---------------------------------------------------------------------------
# Consolidated metal price helpers (single source of truth)
# ---------------------------------------------------------------------------


def metal_price_inr(ticker="GC=F", premium=None, period="5d"):
    """Fetch metal price in INR/gram.

    Args:
        ticker: Yahoo Finance metal futures ticker (GC=F for gold, SI=F for silver)
        premium: multiplier for GST+making. Defaults by ticker.
        period: yfinance period string

    Returns dict with per_gram, change_pct, or None on failure.
    """
    if premium is None:
        premium = GOLD_PREMIUM if "GC" in ticker else SILVER_PREMIUM
    try:
        metal = yf.Ticker(ticker)
        fx = yf.Ticker("USDINR=X")
        m_hist = metal.history(period=period)
        f_hist = fx.history(period=period)
        if m_hist.empty or f_hist.empty:
            return None

        # Timezone-safe merge
        import pandas as pd

        g = m_hist["Close"].copy()
        f2 = f_hist["Close"].copy()
        if g.index.tz is not None:
            g.index = g.index.tz_localize(None)
        if f2.index.tz is not None:
            f2.index = f2.index.tz_localize(None)
        df = pd.DataFrame({"metal": g, "fx": f2}).ffill().dropna()
        if df.empty:
            return None

        inr_g = (df["metal"] * df["fx"]) / TROY_OZ_GRAMS * premium
        current = round(float(inr_g.iloc[-1]), 2)

        change_pct = None
        if len(inr_g) >= 2:
            prev = float(inr_g.iloc[-2])
            if prev > 0:
                change_pct = round(((current - prev) / prev) * 100, 2)

        return {
            "per_gram": current,
            "per_8gram": round(current * 8, 2),
            "per_100gram": round(current * 100, 2),
            "per_kg": round(current * 1000, 2),
            "change_pct": change_pct,
        }
    except Exception:
        return None


def metal_price_inr_weekly(ticker="GC=F", premium=None):
    """Get metal price in INR/gram with weekly change. Used by email."""
    if premium is None:
        premium = GOLD_PREMIUM if "GC" in ticker else SILVER_PREMIUM
    try:
        import pandas as pd

        metal = yf.Ticker(ticker)
        fx = yf.Ticker("USDINR=X")
        m_hist = metal.history(period="2wk")
        f_hist = fx.history(period="2wk")
        if m_hist.empty or f_hist.empty:
            return None, None

        g = m_hist["Close"].copy()
        f2 = f_hist["Close"].copy()
        if g.index.tz is not None:
            g.index = g.index.tz_localize(None)
        if f2.index.tz is not None:
            f2.index = f2.index.tz_localize(None)
        df = pd.DataFrame({"metal": g, "fx": f2}).ffill().dropna()
        if df.empty:
            return None, None

        inr_g = (df["metal"] * df["fx"]) / TROY_OZ_GRAMS * premium
        current = round(float(inr_g.iloc[-1]), 2)
        week_ago = (
            round(float(inr_g.iloc[-6]), 2)
            if len(inr_g) >= 6
            else round(float(inr_g.iloc[0]), 2)
        )
        change = (
            round(((current - week_ago) / week_ago) * 100, 2) if week_ago > 0 else 0
        )
        return current, change
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Ticker validation & input sanitization (C5)
# ---------------------------------------------------------------------------

import re as _re


def sanitize_ticker(ticker):
    """Sanitize a ticker symbol: strip whitespace, uppercase, remove invalid chars."""
    if not ticker:
        return ""
    t = ticker.strip().upper()
    # Allow alphanumeric, dots, hyphens, =, ^, & (for M&M etc.)
    t = _re.sub(r"[^A-Z0-9.\-=^&]", "", t)
    # Max 30 chars
    return t[:30]


def sanitize_amount(value, min_val=0, max_val=100000000):
    """Sanitize a monetary amount: ensure positive and within reasonable range."""
    try:
        v = float(value)
        return max(min_val, min(v, max_val))
    except (TypeError, ValueError):
        return min_val


def sanitize_text(text, max_length=200):
    """Sanitize free-text input: strip, limit length."""
    if not text:
        return ""
    return str(text).strip()[:max_length]


def validate_ticker(ticker_symbol):
    """Validate that a Yahoo Finance ticker exists and returns data.

    Returns dict:
      - valid: bool
      - name: company name (if found)
      - error: error message (if invalid)
    """
    if not ticker_symbol or not ticker_symbol.strip():
        return {"valid": False, "name": None, "error": "Ticker is empty"}

    ticker_symbol = sanitize_ticker(ticker_symbol)

    # Check suffix for Indian stocks
    if (
        not any(ticker_symbol.endswith(s) for s in (".NS", ".BO", ".NS.NS", "=F", "=X"))
        and not ticker_symbol.startswith("^")
        and not ticker_symbol.startswith("0P")
    ):  # MF tickers start with 0P
        return {
            "valid": False,
            "name": None,
            "error": f"Indian stocks need .NS (NSE) or .BO (BSE) suffix. Try: {ticker_symbol}.NS",
        }

    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period="5d")
        if hist.empty:
            return {
                "valid": False,
                "name": None,
                "error": f"No data found for {ticker_symbol}. Check the symbol.",
            }
        info = t.info or {}
        name = info.get("shortName") or info.get("longName") or ticker_symbol
        return {"valid": True, "name": name, "error": None}
    except Exception as e:
        return {
            "valid": False,
            "name": None,
            "error": f"Could not verify {ticker_symbol}: {str(e)[:80]}",
        }


def auto_resolve_ticker(name, asset_type="stock"):
    """Auto-generate Yahoo Finance ticker from a stock/fund name.

    For stocks: tries NAME.NS then NAME.BO on Yahoo Finance.
    Returns dict with ticker, company_name, or error.
    """
    if not name or not name.strip():
        return {"ticker": None, "name": None, "error": "Name is empty"}

    clean = name.strip().upper().replace(" ", "").replace("&", "")

    if asset_type == "stock":
        # Try common NSE ticker patterns
        candidates = [f"{clean}.NS", f"{clean}.BO"]
        # Also try with common suffixes removed
        for suffix in ["LTD", "LIMITED", "IND", "INDIA"]:
            if clean.endswith(suffix):
                base = clean[: -len(suffix)]
                candidates.insert(0, f"{base}.NS")
                candidates.insert(1, f"{base}.BO")
        # Try each word from the name as a possible ticker
        words = [
            w.upper()
            for w in name.strip().split()
            if len(w) >= 3
            and w.upper() not in ("LTD", "LIMITED", "THE", "AND", "IND", "INDIA")
        ]
        for word in words:
            t_ns = f"{word}.NS"
            t_bo = f"{word}.BO"
            if t_ns not in candidates:
                candidates.insert(0, t_ns)
            if t_bo not in candidates:
                candidates.insert(1, t_bo)

        for ticker in candidates:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="5d")
                if not hist.empty:
                    info = t.info or {}
                    company_name = info.get("shortName") or info.get("longName") or name
                    return {"ticker": ticker, "name": company_name, "error": None}
            except Exception:
                continue

        # Last resort: use yfinance search
        try:
            search_result = yf.Search(name)
            quotes = getattr(search_result, "quotes", []) or []
            for q in quotes:
                symbol = q.get("symbol", "")
                if symbol.endswith(".NS") or symbol.endswith(".BO"):
                    t = yf.Ticker(symbol)
                    hist = t.history(period="5d")
                    if not hist.empty:
                        company_name = q.get("shortname") or q.get("longname") or name
                        return {"ticker": symbol, "name": company_name, "error": None}
        except Exception:
            pass

        return {
            "ticker": None,
            "name": None,
            "error": f"Could not find ticker for '{name}'. Try entering it manually (e.g. {clean}.NS)",
        }

    if asset_type == "mutual_fund":
        # Use Yahoo Finance search to find MF tickers (typically .BO)
        try:
            search_result = yf.Search(name)
            quotes = getattr(search_result, "quotes", []) or []
            for q in quotes:
                symbol = q.get("symbol", "")
                q_type = q.get("quoteType", "")
                if q_type == "MUTUALFUND" or symbol.startswith("0P"):
                    t = yf.Ticker(symbol)
                    hist = t.history(period="5d")
                    if not hist.empty:
                        fund_name = q.get("shortname") or q.get("longname") or name
                        return {"ticker": symbol, "name": fund_name, "error": None}
        except Exception:
            pass

        return {
            "ticker": None,
            "name": None,
            "error": f"Could not find ticker for mutual fund '{name}'. Try entering it manually.",
        }

    return {"ticker": None, "name": None, "error": "Unsupported asset type"}


# Cached AMFI NAV file — downloaded at most once per hour
_amfi_cache = {"content": None, "ts": 0}


def _cached_amfi_nav_file():
    """Download AMFI NAV file with 1-hour in-memory cache."""
    import time

    now = time.time()
    if _amfi_cache["content"] and (now - _amfi_cache["ts"]) < 3600:
        return _amfi_cache["content"]
    try:
        req = urllib.request.Request(
            "https://www.amfiindia.com/spages/NAVAll.txt",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        _amfi_cache["content"] = content
        _amfi_cache["ts"] = now
        return content
    except Exception:
        return _amfi_cache["content"]  # return stale if available


def auto_resolve_amfi(name):
    """Auto-lookup AMFI scheme code from a mutual fund name.

    Downloads the AMFI NAV file and fuzzy-matches fund name.
    Returns dict with amfi_code, scheme_name, or error.
    """
    if not name or not name.strip():
        return {"amfi_code": None, "scheme_name": None, "error": "Name is empty"}

    search_terms = name.strip().lower().split()

    try:
        content = _cached_amfi_nav_file()
        if content is None:
            return {
                "amfi_code": None,
                "scheme_name": None,
                "error": "Could not connect to AMFI. Enter the code manually.",
            }

        best_match = None
        best_score = 0

        for line in content.splitlines():
            parts = line.strip().split(";")
            if len(parts) >= 5:
                code = parts[0].strip()
                scheme_name = parts[3].strip().lower()
                if not code.isdigit():
                    continue

                # Score: how many search terms appear in scheme name
                score = sum(1 for term in search_terms if term in scheme_name)
                if score > best_score:
                    best_score = score
                    best_match = {
                        "amfi_code": code,
                        "scheme_name": parts[3].strip(),
                        "error": None,
                    }

        if best_match and best_score >= max(1, len(search_terms) // 2):
            return best_match

        return {
            "amfi_code": None,
            "scheme_name": None,
            "error": f"Could not find AMFI code for '{name}'. Enter it manually from amfiindia.com",
        }
    except Exception:
        return {
            "amfi_code": None,
            "scheme_name": None,
            "error": "Could not connect to AMFI. Enter the code manually.",
        }


# ---------------------------------------------------------------------------
# Market holiday detection
# ---------------------------------------------------------------------------


def is_market_open_today():
    """Check if Indian stock market (NSE) was open today by looking for trading data.

    Returns:
      - True if market had trades today
      - False if holiday/weekend
      - None if can't determine
    """
    try:
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="5d")
        if hist.empty:
            return None
        last_trade_date = hist.index[-1].date()
        today = datetime.now().date()
        return last_trade_date == today
    except Exception:
        return None


# ---------------------------------------------------------------------------
# P&L and XIRR calculation
# ---------------------------------------------------------------------------


def calculate_xirr(cashflows):
    """Calculate XIRR (annualized return) from a list of (date, amount) tuples.

    Negative amounts = investments, positive = current value.
    Returns annualized return as percentage, or None if can't compute.
    """
    if len(cashflows) < 2:
        return None

    try:
        from scipy.optimize import brentq
    except ImportError:
        return None

    dates = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    min_date = min(dates)
    day_fracs = [(d - min_date).days / 365.25 for d in dates]

    def npv(rate):
        return sum(a / (1 + rate) ** t for a, t in zip(amounts, day_fracs))

    try:
        result = brentq(npv, -0.99, 10.0, maxiter=200)
        return round(result * 100, 2)
    except (ValueError, RuntimeError):
        return None


def calculate_portfolio_pnl(holdings, analysis_results):
    """Calculate P&L for each holding and total portfolio.

    Returns dict with:
      - holdings_pnl: list of per-holding P&L dicts
      - total_invested: sum of all amounts
      - total_current: sum of current values
      - total_pnl: absolute profit/loss
      - total_pnl_pct: percentage return
      - xirr: annualized return (if scipy available)
    """
    holdings_pnl = []
    total_invested = 0
    total_current = 0
    cashflows = []

    for r in analysis_results:
        h = r["holding"]
        a = r["analysis"]
        invested = h["amount"]
        total_invested += invested

        if a is None or a.get("price", 0) <= 0:
            holdings_pnl.append(
                {
                    "name": h["name"],
                    "ticker": h["ticker"],
                    "type": h["type"],
                    "invested": invested,
                    "current_value": invested,  # fallback
                    "pnl": 0,
                    "pnl_pct": 0,
                    "daily_change_pct": 0,
                }
            )
            total_current += invested
            continue

        # Actual P&L from buy_price vs current market price
        current_price = a.get("price", 0) or 0
        quantity = h.get("quantity", 0)
        is_sip = h.get("investment_mode") == "sip"

        if is_sip and h.get("sip_monthly", 0) > 0 and h.get("ticker"):
            # For SIPs, use historical simulation to estimate current value
            sip_val = estimate_sip_value(
                h["ticker"], h["sip_monthly"], pause_periods=h.get("sip_pause_periods")
            )
            if sip_val:
                current_value = round(sip_val["current_value"], 2)
                invested = round(sip_val["invested"], 2)
            else:
                current_value = invested
        elif current_price > 0 and quantity > 0:
            current_value = round(current_price * quantity, 2)
        else:
            current_value = invested  # fallback
        pnl = round(current_value - invested, 2)
        pnl_pct = round((pnl / invested) * 100, 2) if invested > 0 else 0

        total_current += current_value

        holdings_pnl.append(
            {
                "name": h["name"],
                "ticker": h["ticker"],
                "type": h["type"],
                "invested": invested,
                "current_value": current_value,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "daily_change_pct": a.get("daily_change_pct", 0),
            }
        )

        # Build cashflow for XIRR
        buy_date_str = h.get("buy_date", "")
        if buy_date_str:
            try:
                invest_date = datetime.strptime(buy_date_str, "%Y-%m-%d").date()
            except ValueError:
                invest_date = datetime.now().date() - timedelta(days=365)
        else:
            invest_date = datetime.now().date() - timedelta(days=365)

        if is_sip and h.get("sip_monthly", 0) > 0:
            # SIP: add monthly cashflows from start date to today (skip paused months)
            sip_monthly = h["sip_monthly"]
            pause_periods = h.get("sip_pause_periods", [])
            cf_date = invest_date
            today = datetime.now().date()
            while cf_date <= today:
                if not _is_month_paused(cf_date.year, cf_date.month, pause_periods):
                    cashflows.append((cf_date, -sip_monthly))
                # Advance by ~1 month
                m = cf_date.month + 1
                y = cf_date.year
                if m > 12:
                    m = 1
                    y += 1
                cf_date = cf_date.replace(year=y, month=m)
        elif h.get("transactions"):
            # Multi-transaction: use each transaction's actual date & amount
            for txn in h["transactions"]:
                txn_date_str = txn.get("buy_date", "")
                txn_qty = float(txn.get("quantity", 0))
                txn_price = float(txn.get("buy_price", 0))
                if txn_date_str and txn_qty > 0 and txn_price > 0:
                    try:
                        txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d").date()
                        cashflows.append((txn_date, -(txn_price * txn_qty)))
                    except ValueError:
                        cashflows.append((invest_date, -(txn_price * txn_qty)))
        else:
            cashflows.append((invest_date, -invested))

    # Add current total as final cashflow (today)
    if cashflows:
        cashflows.append((datetime.now().date(), total_current))

    total_pnl = round(total_current - total_invested, 2)
    total_pnl_pct = (
        round((total_pnl / total_invested) * 100, 2) if total_invested > 0 else 0
    )
    xirr = calculate_xirr(cashflows)

    return {
        "holdings_pnl": holdings_pnl,
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "xirr": xirr,
    }


# ---------------------------------------------------------------------------
# Goal-based planning
# ---------------------------------------------------------------------------


def calculate_sip_for_goal(target_amount, years, expected_return_pct=12):
    """Calculate monthly SIP needed to reach a financial goal.

    Args:
        target_amount: target corpus in ₹
        years: time horizon
        expected_return_pct: expected annual return (default 12% for equity)

    Returns dict with monthly_sip, total_invested, total_returns, etc.
    """
    if target_amount <= 0 or years <= 0:
        return None

    r = expected_return_pct / 100 / 12  # monthly rate
    n = years * 12  # total months

    # SIP formula: FV = P × [(1+r)^n - 1] / r × (1+r)
    # P = FV × r / [(1+r)^n - 1] / (1+r)
    if r == 0:
        monthly_sip = target_amount / n
    else:
        monthly_sip = target_amount * r / (((1 + r) ** n - 1) * (1 + r))

    total_invested = monthly_sip * n
    total_returns = target_amount - total_invested

    return {
        "monthly_sip": round(monthly_sip, 0),
        "total_invested": round(total_invested, 0),
        "total_returns": round(total_returns, 0),
        "target": target_amount,
        "years": years,
        "return_pct": expected_return_pct,
    }


def calculate_goal_progress(
    current_value, target_amount, years_remaining, monthly_sip, expected_return_pct=12
):
    """Calculate progress towards a financial goal.

    Returns dict with progress_pct, on_track, shortfall/surplus, etc.
    """
    if target_amount <= 0:
        return None

    progress_pct = round((current_value / target_amount) * 100, 1)
    remaining = target_amount - current_value

    # Project what current SIP will give
    r = expected_return_pct / 100 / 12
    n = years_remaining * 12
    if r > 0 and n > 0:
        projected_from_sip = monthly_sip * (((1 + r) ** n - 1) / r) * (1 + r)
        projected_from_current = current_value * (
            (1 + expected_return_pct / 100) ** years_remaining
        )
        projected_total = projected_from_sip + projected_from_current
    else:
        projected_total = current_value + (monthly_sip * n)

    on_track = projected_total >= target_amount
    shortfall = round(target_amount - projected_total, 0) if not on_track else 0
    surplus = round(projected_total - target_amount, 0) if on_track else 0

    return {
        "progress_pct": progress_pct,
        "remaining": round(remaining, 0),
        "projected_total": round(projected_total, 0),
        "on_track": on_track,
        "shortfall": shortfall,
        "surplus": surplus,
    }


def recommend_sip_funds(years, expected_return_pct, monthly_sip, holdings=None):
    """Recommend mutual fund SIPs based on goal horizon, expected return, market trend,
    and existing portfolio composition.

    If holdings are provided, analyzes current portfolio allocation and adjusts
    recommendations to fill gaps and improve diversification.

    Returns a list of fund recommendations with allocation percentages.
    Each entry: {category, fund_name, amfi_code, allocation_pct, reason, risk}
    Also returns market_trend info and portfolio_notes for UI display.
    """
    # Curated list of top-performing Direct Growth funds across categories
    FUND_DB = {
        "large_cap": [
            {
                "name": "Nippon India Large Cap Fund - Direct Plan - Growth",
                "amfi_code": "118281",
                "risk": "Moderate",
                "return_range": "10-14%",
            },
            {
                "name": "ICICI Prudential Bluechip Fund - Direct Plan - Growth",
                "amfi_code": "120587",
                "risk": "Moderate",
                "return_range": "10-14%",
            },
        ],
        "flexi_cap": [
            {
                "name": "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
                "amfi_code": "122639",
                "risk": "Moderate",
                "return_range": "12-16%",
            },
            {
                "name": "HDFC Flexi Cap Fund - Direct Plan - Growth",
                "amfi_code": "118955",
                "risk": "Moderate",
                "return_range": "11-15%",
            },
        ],
        "mid_cap": [
            {
                "name": "Motilal Oswal Midcap Fund - Direct Plan - Growth",
                "amfi_code": "127042",
                "risk": "High",
                "return_range": "13-18%",
            },
            {
                "name": "HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth",
                "amfi_code": "118989",
                "risk": "High",
                "return_range": "12-17%",
            },
        ],
        "small_cap": [
            {
                "name": "Nippon India Small Cap Fund - Direct Plan - Growth",
                "amfi_code": "118778",
                "risk": "Very High",
                "return_range": "14-20%",
            },
            {
                "name": "Quant Small Cap Fund - Direct Plan - Growth",
                "amfi_code": "120828",
                "risk": "Very High",
                "return_range": "14-22%",
            },
        ],
        "elss": [
            {
                "name": "Quant ELSS Tax Saver Fund - Direct Plan - Growth",
                "amfi_code": "120823",
                "risk": "High",
                "return_range": "12-18%",
            },
            {
                "name": "Mirae Asset ELSS Tax Saver Fund - Direct Plan - Growth",
                "amfi_code": "130503",
                "risk": "High",
                "return_range": "11-16%",
            },
        ],
        "debt": [
            {
                "name": "HDFC Short Term Debt Fund - Direct Plan - Growth",
                "amfi_code": "119065",
                "risk": "Low",
                "return_range": "6-8%",
            },
            {
                "name": "ICICI Prudential Corporate Bond Fund - Direct Plan - Growth",
                "amfi_code": "120604",
                "risk": "Low",
                "return_range": "6-8%",
            },
        ],
        "balanced": [
            {
                "name": "ICICI Prudential Equity & Debt Fund - Direct Plan - Growth",
                "amfi_code": "120572",
                "risk": "Moderate",
                "return_range": "10-13%",
            },
        ],
        "index": [
            {
                "name": "UTI Nifty 50 Index Fund - Direct Plan - Growth",
                "amfi_code": "120716",
                "risk": "Moderate",
                "return_range": "10-13%",
            },
            {
                "name": "Motilal Oswal Nifty Midcap 150 Index Fund - Direct Plan - Growth",
                "amfi_code": "147622",
                "risk": "High",
                "return_range": "12-16%",
            },
        ],
    }

    recommendations = []

    if years <= 2:
        # Short-term: mostly debt + some balanced
        recommendations = [
            {
                "category": "Debt Fund",
                "allocation_pct": 60,
                "reason": "Capital safety for short horizon",
                **FUND_DB["debt"][0],
            },
            {
                "category": "Balanced Fund",
                "allocation_pct": 25,
                "reason": "Small equity tilt for better returns",
                **FUND_DB["balanced"][0],
            },
            {
                "category": "Large Cap",
                "allocation_pct": 15,
                "reason": "Blue-chip stability with upside",
                **FUND_DB["large_cap"][1],
            },
        ]
    elif years <= 5:
        # Medium-term: mixed across risk levels
        if expected_return_pct <= 10:
            recommendations = [
                {
                    "category": "Debt Fund",
                    "allocation_pct": 25,
                    "reason": "Stability anchor for medium horizon",
                    **FUND_DB["debt"][0],
                },
                {
                    "category": "Large Cap",
                    "allocation_pct": 30,
                    "reason": "Stable blue-chip companies",
                    **FUND_DB["large_cap"][0],
                },
                {
                    "category": "Flexi Cap",
                    "allocation_pct": 25,
                    "reason": "Diversified across market caps",
                    **FUND_DB["flexi_cap"][0],
                },
                {
                    "category": "Mid Cap",
                    "allocation_pct": 20,
                    "reason": "Growth kicker for higher returns",
                    **FUND_DB["mid_cap"][1],
                },
            ]
        else:
            recommendations = [
                {
                    "category": "Debt Fund",
                    "allocation_pct": 15,
                    "reason": "Stability buffer for medium horizon",
                    **FUND_DB["debt"][0],
                },
                {
                    "category": "Flexi Cap",
                    "allocation_pct": 30,
                    "reason": "Diversified across market caps",
                    **FUND_DB["flexi_cap"][0],
                },
                {
                    "category": "Large Cap",
                    "allocation_pct": 25,
                    "reason": "Stable blue-chip core",
                    **FUND_DB["large_cap"][0],
                },
                {
                    "category": "Mid Cap",
                    "allocation_pct": 30,
                    "reason": "Higher growth potential",
                    **FUND_DB["mid_cap"][0],
                },
            ]
    elif years <= 10:
        # Long-term: equity-heavy with risk spread
        if expected_return_pct <= 12:
            recommendations = [
                {
                    "category": "Debt Fund",
                    "allocation_pct": 10,
                    "reason": "Stability buffer — protects during crashes",
                    **FUND_DB["debt"][1],
                },
                {
                    "category": "Nifty 50 Index",
                    "allocation_pct": 25,
                    "reason": "Low-cost large-cap market exposure",
                    **FUND_DB["index"][0],
                },
                {
                    "category": "Flexi Cap",
                    "allocation_pct": 25,
                    "reason": "Active diversified fund across all caps",
                    **FUND_DB["flexi_cap"][0],
                },
                {
                    "category": "Mid Cap",
                    "allocation_pct": 20,
                    "reason": "Higher growth — 10yr horizon absorbs volatility",
                    **FUND_DB["mid_cap"][0],
                },
                {
                    "category": "Small Cap",
                    "allocation_pct": 10,
                    "reason": "High growth kicker for long horizon",
                    **FUND_DB["small_cap"][0],
                },
                {
                    "category": "ELSS (Tax Saver)",
                    "allocation_pct": 10,
                    "reason": "Save tax under 80C + equity growth",
                    **FUND_DB["elss"][1],
                },
            ]
        else:
            recommendations = [
                {
                    "category": "Debt Fund",
                    "allocation_pct": 5,
                    "reason": "Small safety net for rebalancing",
                    **FUND_DB["debt"][1],
                },
                {
                    "category": "Flexi Cap",
                    "allocation_pct": 20,
                    "reason": "Diversified core across all caps",
                    **FUND_DB["flexi_cap"][0],
                },
                {
                    "category": "Mid Cap",
                    "allocation_pct": 25,
                    "reason": "Strong mid-term growth engine",
                    **FUND_DB["mid_cap"][1],
                },
                {
                    "category": "Small Cap",
                    "allocation_pct": 25,
                    "reason": "Highest growth — time to recover dips",
                    **FUND_DB["small_cap"][0],
                },
                {
                    "category": "ELSS (Tax Saver)",
                    "allocation_pct": 15,
                    "reason": "Save tax + aggressive equity growth",
                    **FUND_DB["elss"][0],
                },
                {
                    "category": "Midcap Index",
                    "allocation_pct": 10,
                    "reason": "Low-cost mid-cap passive exposure",
                    **FUND_DB["index"][1],
                },
            ]
    else:
        # Very long-term (>10 years): aggressive but still diversified
        recommendations = [
            {
                "category": "Small Cap",
                "allocation_pct": 25,
                "reason": "Maximum growth for 10yr+ horizon",
                **FUND_DB["small_cap"][0],
            },
            {
                "category": "Mid Cap",
                "allocation_pct": 20,
                "reason": "Strong growth with time to recover dips",
                **FUND_DB["mid_cap"][0],
            },
            {
                "category": "Flexi Cap",
                "allocation_pct": 20,
                "reason": "Core diversified holding",
                **FUND_DB["flexi_cap"][0],
            },
            {
                "category": "Midcap Index",
                "allocation_pct": 15,
                "reason": "Low-cost mid-cap passive exposure",
                **FUND_DB["index"][1],
            },
            {
                "category": "ELSS (Tax Saver)",
                "allocation_pct": 10,
                "reason": "Tax savings + equity growth",
                **FUND_DB["elss"][1],
            },
            {
                "category": "Debt Fund",
                "allocation_pct": 10,
                "reason": "Rebalancing reserve — buy dips from here",
                **FUND_DB["debt"][0],
            },
        ]

    # Add SIP amounts based on allocation
    for rec in recommendations:
        rec["sip_amount"] = round(monthly_sip * rec["allocation_pct"] / 100, 0)

    # --- Fetch market trend and adjust allocations ---
    trend = _get_market_trend()
    trend_note = None

    if trend and years > 2:
        vix = trend.get("vix")
        nifty_rsi = trend.get("nifty_rsi")
        nifty_change_1m = trend.get("nifty_change_1m", 0)

        # Bearish / high-fear: shift 10% from riskiest to safest
        if (vix and vix > 25) or (nifty_rsi and nifty_rsi < 35):
            trend_note = "📉 Market is fearful"
            if vix and vix > 25:
                trend_note += f" (VIX: {vix:.0f})"
            if nifty_rsi and nifty_rsi < 35:
                trend_note += f" (Nifty RSI: {nifty_rsi:.0f})"
            trend_note += " — shifted allocation towards safer funds. Good time to start SIPs (buy the dip)."
            # Move 10% from highest-risk to lowest-risk
            if len(recommendations) >= 2:
                sorted_by_risk = sorted(
                    recommendations,
                    key=lambda x: {
                        "Low": 0,
                        "Moderate": 1,
                        "High": 2,
                        "Very High": 3,
                    }.get(x["risk"], 1),
                )
                safest = sorted_by_risk[0]
                riskiest = sorted_by_risk[-1]
                if safest != riskiest:
                    shift = min(10, riskiest["allocation_pct"] - 5)
                    if shift > 0:
                        riskiest["allocation_pct"] -= shift
                        safest["allocation_pct"] += shift

        # Bullish / overheated: shift 10% from riskiest equity to large-cap/index
        elif (nifty_rsi and nifty_rsi > 75) or (
            nifty_change_1m and nifty_change_1m > 8
        ):
            trend_note = "📈 Market is overheated"
            if nifty_rsi and nifty_rsi > 75:
                trend_note += f" (Nifty RSI: {nifty_rsi:.0f})"
            if nifty_change_1m and nifty_change_1m > 8:
                trend_note += f" (Nifty +{nifty_change_1m:.1f}% in 1 month)"
            trend_note += " — reduced small/mid-cap tilt. SIPs still fine (rupee cost averaging helps)."
            if len(recommendations) >= 2:
                sorted_by_risk = sorted(
                    recommendations,
                    key=lambda x: {
                        "Low": 0,
                        "Moderate": 1,
                        "High": 2,
                        "Very High": 3,
                    }.get(x["risk"], 1),
                )
                safest = sorted_by_risk[0]
                riskiest = sorted_by_risk[-1]
                if safest != riskiest:
                    shift = min(10, riskiest["allocation_pct"] - 5)
                    if shift > 0:
                        riskiest["allocation_pct"] -= shift
                        safest["allocation_pct"] += shift

        else:
            trend_note = "➡️ Market conditions are normal"
            if nifty_rsi:
                trend_note += f" (Nifty RSI: {nifty_rsi:.0f})"
            if vix:
                trend_note += f" (VIX: {vix:.0f})"
            trend_note += " — standard allocation applies."

        # Recalculate SIP amounts after adjustment
        for rec in recommendations:
            rec["sip_amount"] = round(monthly_sip * rec["allocation_pct"] / 100, 0)

    # --- Portfolio-aware adjustments ---
    portfolio_notes = []
    if holdings:
        total_invested = sum(h.get("amount", 0) for h in holdings)
        if total_invested > 0:
            # Categorize existing holdings
            stock_amt = sum(h["amount"] for h in holdings if h.get("type") == "stock")
            mf_amt = sum(
                h["amount"] for h in holdings if h.get("type") == "mutual_fund"
            )
            stock_pct = round((stock_amt / total_invested) * 100, 1)
            mf_pct = round((mf_amt / total_invested) * 100, 1)

            # Check existing SIPs
            existing_sip_names = set()
            existing_sip_amfis = set()
            existing_sip_total = 0
            for h in holdings:
                if h.get("investment_mode") == "sip" and h.get("sip_monthly", 0) > 0:
                    existing_sip_names.add(h["name"].lower())
                    if h.get("amfi_code"):
                        existing_sip_amfis.add(h["amfi_code"])
                    existing_sip_total += h["sip_monthly"]

            # Mark if already invested
            for rec in recommendations:
                rec_amfi = rec.get("amfi_code", "")
                rec_name = rec.get("name", "").lower()
                if rec_amfi in existing_sip_amfis:
                    rec["already_invested"] = True
                    rec["reason"] += " (✅ You already have a SIP here)"
                elif any(n in rec_name or rec_name in n for n in existing_sip_names):
                    rec["already_invested"] = True
                    rec["reason"] += " (✅ Similar fund in portfolio)"

            # Portfolio composition notes
            if stock_pct > 80:
                portfolio_notes.append(
                    f"📊 Your portfolio is {stock_pct:.0f}% direct stocks. "
                    "SIP in mutual funds will add professional management & diversification."
                )
            elif mf_pct > 80:
                portfolio_notes.append(
                    f"📊 Your portfolio is {mf_pct:.0f}% mutual funds. "
                    "Consider adding quality stocks for direct equity exposure."
                )

            if stock_pct > 0 and mf_pct > 0:
                portfolio_notes.append(
                    f"📊 Current split: {stock_pct:.0f}% stocks, {mf_pct:.0f}% mutual funds "
                    f"(₹{total_invested:,.0f} total invested)"
                )

            if existing_sip_total > 0:
                portfolio_notes.append(
                    f"💰 You already invest ₹{existing_sip_total:,.0f}/month in SIPs. "
                    f"New SIP of ₹{monthly_sip:,.0f}/mo brings total to ₹{existing_sip_total + monthly_sip:,.0f}/mo."
                )

            # Check for sector concentration (if many stocks in same sector)
            holding_count = len(holdings)
            if holding_count <= 3:
                portfolio_notes.append(
                    f"⚠️ Only {holding_count} holdings — portfolio is concentrated. "
                    "SIPs in diversified funds recommended."
                )

            # Suggest categories user is missing
            existing_categories = set()
            for h in holdings:
                name_lower = h["name"].lower()
                if "small cap" in name_lower:
                    existing_categories.add("small_cap")
                elif "mid cap" in name_lower or "midcap" in name_lower:
                    existing_categories.add("mid_cap")
                elif "large cap" in name_lower:
                    existing_categories.add("large_cap")
                elif "flexi" in name_lower:
                    existing_categories.add("flexi_cap")
                elif "index" in name_lower or "nifty" in name_lower:
                    existing_categories.add("index")
                elif "elss" in name_lower or "tax" in name_lower:
                    existing_categories.add("elss")
                elif "debt" in name_lower or "bond" in name_lower:
                    existing_categories.add("debt")

            category_map = {
                "small_cap": "Small Cap",
                "mid_cap": "Mid Cap",
                "large_cap": "Large Cap",
                "flexi_cap": "Flexi Cap",
                "index": "Index Fund",
                "elss": "ELSS (Tax Saver)",
                "debt": "Debt Fund",
            }
            all_cats = set(category_map.keys())
            missing = all_cats - existing_categories
            if missing and len(missing) < len(all_cats):
                missing_labels = sorted(
                    category_map[c] for c in missing if c in category_map
                )
                if missing_labels:
                    # Boost allocation for missing categories
                    for rec in recommendations:
                        rec_cat = rec.get("category", "")
                        if any(m in rec_cat for m in missing_labels):
                            rec["reason"] += " (🆕 New category for you)"

    return {
        "funds": recommendations,
        "trend_note": trend_note,
        "trend": trend,
        "portfolio_notes": portfolio_notes,
    }


def analyze_existing_mf_holdings(holdings):
    """Analyze user's existing mutual fund/SIP holdings and give HOLD/ADD MORE/SELL advice.

    For each MF holding, fetches:
    - Current NAV and returns (1m, 6m, 1y)
    - Category performance comparison
    - Risk metrics

    Returns list of dicts with advice for each holding.
    """
    mf_holdings = [h for h in (holdings or []) if h.get("type") == "mutual_fund"]
    if not mf_holdings:
        return []

    results = []

    def _analyze_one(h):
        name = h["name"]
        ticker = h.get("ticker", "")
        amfi_code = h.get("amfi_code", "")
        buy_price = h.get("buy_price", 0)
        quantity = h.get("quantity", 0)
        invested = h.get("amount", 0)
        is_sip = h.get("investment_mode") == "sip"
        sip_monthly = h.get("sip_monthly", 0)
        days_held = h.get("days_held", 0)

        # Fetch current price
        current_price = None
        hist = None
        try:
            if ticker:
                t = yf.Ticker(ticker)
                hist = t.history(period="1y")
                if not hist.empty:
                    current_price = float(hist["Close"].iloc[-1])
        except Exception:
            pass

        if current_price is None or current_price <= 0:
            return None

        # Current value
        current_value = current_price * quantity if quantity > 0 else 0
        total_return_pct = (
            ((current_value - invested) / invested) * 100 if invested > 0 else 0
        )

        # Returns at different periods
        closes = hist["Close"].values if hist is not None and not hist.empty else []
        returns = {}
        if len(closes) >= 22:
            returns["1m"] = ((closes[-1] - closes[-22]) / closes[-22]) * 100
        if len(closes) >= 126:
            returns["6m"] = ((closes[-1] - closes[-126]) / closes[-126]) * 100
        if len(closes) >= 240:
            returns["1y"] = ((closes[-1] - closes[0]) / closes[0]) * 100

        # RSI for momentum
        rsi = compute_rsi(closes) if len(closes) >= 14 else None

        # Volatility
        if len(closes) >= 30:
            daily_returns = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes))
            ]
            import statistics

            volatility = (
                statistics.stdev(daily_returns) * (252**0.5) * 100
            )  # annualized
        else:
            volatility = None

        # --- Verdict logic ---
        score = 0  # positive = hold/add, negative = sell
        reasons = []

        # Performance
        ret_1y = returns.get("1y")
        ret_6m = returns.get("6m")
        ret_1m = returns.get("1m")

        if ret_1y is not None:
            if ret_1y > 15:
                score += 2
                reasons.append(f"Strong 1Y return ({ret_1y:+.1f}%)")
            elif ret_1y > 8:
                score += 1
                reasons.append(f"Decent 1Y return ({ret_1y:+.1f}%)")
            elif ret_1y > 0:
                reasons.append(f"Modest 1Y return ({ret_1y:+.1f}%)")
            elif ret_1y > -5:
                score -= 1
                reasons.append(f"Slightly negative 1Y return ({ret_1y:+.1f}%)")
            else:
                score -= 2
                reasons.append(f"Poor 1Y return ({ret_1y:+.1f}%)")

        if ret_6m is not None:
            if ret_6m > 10:
                score += 1
                reasons.append(f"Strong 6M momentum ({ret_6m:+.1f}%)")
            elif ret_6m < -10:
                score -= 1
                reasons.append(f"Weak 6M momentum ({ret_6m:+.1f}%)")

        # RSI assessment
        if rsi is not None:
            if rsi < 30:
                reasons.append(f"Oversold (RSI {rsi:.0f}) — may bounce back")
            elif rsi > 70:
                score -= 1
                reasons.append(f"Overbought (RSI {rsi:.0f}) — could correct")

        # Holding period
        if days_held > 365:
            score += 1
            reasons.append(
                f"Held {days_held // 365}y+ — LTCG tax applies (10% above ₹1L)"
            )
        elif days_held > 0 and days_held <= 365:
            reasons.append(f"Held {days_held} days — STCG tax (15%) if sold now")

        # Overall return on investment
        if total_return_pct > 20:
            score += 1
            reasons.append(
                f"You're up {total_return_pct:+.1f}% overall — healthy position"
            )
        elif total_return_pct < -10:
            reasons.append(
                f"You're down {total_return_pct:+.1f}% — consider if fundamentals changed"
            )

        # SIP benefit
        if is_sip and sip_monthly > 0:
            if is_sip_currently_paused(h):
                reasons.append(
                    f"⏸️ SIP ₹{sip_monthly:,.0f}/mo is PAUSED — consider resuming to benefit from rupee cost averaging"
                )
            else:
                score += 1
                reasons.append(
                    f"Active SIP ₹{sip_monthly:,.0f}/mo — rupee cost averaging is working"
                )

        # Determine verdict
        if score >= 3:
            verdict = "ADD MORE"
            verdict_detail = (
                "Performing well — consider increasing SIP or making a lump sum top-up."
            )
        elif score >= 1:
            verdict = "HOLD"
            verdict_detail = "Steady performer — keep holding & let compounding work."
        elif score >= -1:
            verdict = "HOLD & WATCH"
            verdict_detail = (
                "Underperforming slightly — hold for now but review in 3 months."
            )
        else:
            verdict = "CONSIDER SELLING"
            verdict_detail = (
                "Consistent underperformer — evaluate if this fund fits your goals."
            )

        # Category detection from name
        name_lower = name.lower()
        category = "Equity"
        if "small cap" in name_lower:
            category = "Small Cap"
        elif "mid cap" in name_lower or "midcap" in name_lower:
            category = "Mid Cap"
        elif "large cap" in name_lower:
            category = "Large Cap"
        elif "flexi" in name_lower:
            category = "Flexi Cap"
        elif "index" in name_lower or "nifty" in name_lower or "sensex" in name_lower:
            category = "Index Fund"
        elif "elss" in name_lower or "tax" in name_lower:
            category = "ELSS"
        elif "debt" in name_lower or "bond" in name_lower or "liquid" in name_lower:
            category = "Debt"
        elif "hybrid" in name_lower or "balanced" in name_lower:
            category = "Hybrid"
        elif "etf" in name_lower:
            category = "ETF"
        elif "gold" in name_lower:
            category = "Gold ETF"
        elif "silver" in name_lower:
            category = "Silver ETF"

        return {
            "name": name,
            "ticker": ticker,
            "category": category,
            "is_sip": is_sip,
            "sip_monthly": sip_monthly,
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "quantity": quantity,
            "buy_price": buy_price,
            "current_price": round(current_price, 2),
            "total_return_pct": round(total_return_pct, 2),
            "returns": {k: round(v, 2) for k, v in returns.items()},
            "rsi": round(rsi, 1) if rsi else None,
            "volatility": round(volatility, 1) if volatility else None,
            "days_held": days_held,
            "verdict": verdict,
            "verdict_detail": verdict_detail,
            "reasons": reasons,
            "score": score,
        }

    raw_results = list(_SHARED_POOL.map(_analyze_one, mf_holdings))
    results = [r for r in raw_results if r is not None]

    # Sort: CONSIDER SELLING first, then HOLD & WATCH, HOLD, ADD MORE
    verdict_order = {"CONSIDER SELLING": 0, "HOLD & WATCH": 1, "HOLD": 2, "ADD MORE": 3}
    results.sort(key=lambda x: verdict_order.get(x["verdict"], 2))

    return results


def analyze_existing_stock_holdings(holdings):
    """Analyze user's stock holdings and give ADD MORE / HOLD / REDUCE advice.

    For each stock holding, evaluates:
    - P&L and return %
    - RSI momentum
    - Price vs moving averages (SMA50, SMA200)
    - 52-week range position
    - PE valuation
    - Volume activity
    - Holding period / tax implications
    - Concentration risk (% of portfolio)

    Returns list of dicts with verdict for each stock holding.
    """
    stock_holdings = [h for h in (holdings or []) if h.get("type") == "stock"]
    if not stock_holdings:
        return []

    total_portfolio = sum(h.get("amount", 0) for h in (holdings or []))
    results = []

    def _analyze_one(h):
        name = h["name"]
        ticker = h.get("ticker", "")
        buy_price = h.get("buy_price", 0)
        quantity = h.get("quantity", 0)
        invested = h.get("amount", 0)
        days_held = h.get("days_held", 0)

        if not ticker:
            return None

        # Fetch current price & history
        current_price = None
        hist = None
        info = {}
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")
            info = t.info or {}
            if not hist.empty:
                current_price = float(hist["Close"].iloc[-1])
        except Exception:
            pass

        if current_price is None or current_price <= 0:
            return None

        closes = hist["Close"].values if hist is not None and not hist.empty else []
        volumes = hist["Volume"].values if hist is not None and not hist.empty else []

        # Current value & P&L
        current_value = current_price * quantity if quantity > 0 else 0
        total_return_pct = (
            ((current_value - invested) / invested) * 100 if invested > 0 else 0
        )

        # Returns at different periods
        returns = {}
        if len(closes) >= 22:
            returns["1m"] = ((closes[-1] - closes[-22]) / closes[-22]) * 100
        if len(closes) >= 126:
            returns["6m"] = ((closes[-1] - closes[-126]) / closes[-126]) * 100
        if len(closes) >= 240:
            returns["1y"] = ((closes[-1] - closes[0]) / closes[0]) * 100

        # Technical indicators
        rsi = compute_rsi(closes) if len(closes) >= 14 else None
        sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
        sma200 = float(np.mean(closes[-200:])) if len(closes) >= 200 else None

        # 52-week range
        high_52w = float(closes.max()) if len(closes) > 0 else 0
        low_52w = float(closes.min()) if len(closes) > 0 else 0
        range_pct = (
            ((current_price - low_52w) / (high_52w - low_52w)) * 100
            if high_52w != low_52w
            else 50
        )
        from_high_pct = (
            ((current_price - high_52w) / high_52w) * 100 if high_52w > 0 else 0
        )

        # Fundamentals
        pe_ratio = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        sector = info.get("sector", "")
        dividend_yield = info.get("dividendYield")

        # Volatility
        volatility = None
        if len(closes) >= 30:
            daily_returns = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes))
            ]
            import statistics

            volatility = statistics.stdev(daily_returns) * (252**0.5) * 100

        # ATR for risk
        atr_val = None
        atr_pct = 0
        if hist is not None and not hist.empty:
            highs = hist["High"].values
            lows = hist["Low"].values
            atr_val = compute_atr(highs, lows, closes)
            atr_pct = (
                (atr_val / current_price * 100) if atr_val and current_price else 0
            )

        # --- Scoring ---
        score = 0
        reasons = []

        # 1. Overall P&L
        if total_return_pct > 30:
            score += 2
            reasons.append(
                f"Up {total_return_pct:+.1f}% — strong gainer, book partial profits or hold"
            )
        elif total_return_pct > 15:
            score += 1
            reasons.append(f"Up {total_return_pct:+.1f}% — healthy return")
        elif total_return_pct > 0:
            reasons.append(f"Up {total_return_pct:+.1f}% — modest gain")
        elif total_return_pct > -10:
            score -= 1
            reasons.append(
                f"Down {total_return_pct:+.1f}% — minor loss, hold if fundamentals intact"
            )
        elif total_return_pct > -25:
            score -= 2
            reasons.append(
                f"Down {total_return_pct:+.1f}% — significant loss, review if thesis still valid"
            )
        else:
            score -= 3
            reasons.append(
                f"Down {total_return_pct:+.1f}% — deep loss, consider exiting if fundamentals broken"
            )

        # 2. RSI momentum
        if rsi is not None:
            if rsi < 30:
                score += 1
                reasons.append(
                    f"RSI {rsi:.0f} — oversold, potential bounce (add more if thesis intact)"
                )
            elif rsi > 70:
                score -= 1
                reasons.append(
                    f"RSI {rsi:.0f} — overbought, may correct (consider trimming)"
                )
            elif rsi > 60:
                reasons.append(f"RSI {rsi:.0f} — strong momentum")
            elif rsi < 40:
                reasons.append(f"RSI {rsi:.0f} — weak momentum")

        # 3. Moving average trend
        if sma50 and sma200:
            if current_price > sma50 > sma200:
                score += 1
                reasons.append("Price above 50 & 200-day averages — bullish trend")
            elif current_price < sma50 < sma200:
                score -= 1
                reasons.append("Price below 50 & 200-day averages — bearish trend")
            elif sma50 < sma200:
                reasons.append("50-day MA below 200-day MA — downtrend in progress")
        elif sma50:
            if current_price > sma50:
                reasons.append("Price above 50-day average — short-term uptrend")
            else:
                reasons.append("Price below 50-day average — short-term weakness")

        # 4. 52-week range
        if range_pct <= 20:
            score += 1
            reasons.append(
                f"Near 52-week low ({range_pct:.0f}%) — value zone if fundamentals strong"
            )
        elif range_pct >= 85:
            score -= 1
            reasons.append(
                f"Near 52-week high ({range_pct:.0f}%) — risky to add more at these levels"
            )

        # 5. PE valuation
        if pe_ratio:
            if pe_ratio < 12:
                score += 1
                reasons.append(f"PE {pe_ratio:.1f} — undervalued, good for adding")
            elif pe_ratio < 25:
                reasons.append(f"PE {pe_ratio:.1f} — fairly valued")
            elif pe_ratio < 50:
                score -= 1
                reasons.append(
                    f"PE {pe_ratio:.1f} — expensive, be cautious adding more"
                )
            else:
                score -= 2
                reasons.append(f"PE {pe_ratio:.1f} — very expensive, consider reducing")

            if forward_pe and pe_ratio > 25 and forward_pe < pe_ratio * 0.7:
                score += 1
                reasons.append(
                    f"Forward PE {forward_pe:.1f} much lower — expected earnings growth"
                )

        # 6. Volume activity
        if len(volumes) >= 21:
            avg_vol_20 = float(np.mean(volumes[-21:-1]))
            latest_vol = float(volumes[-1])
            vol_ratio = latest_vol / avg_vol_20 if avg_vol_20 > 0 else 1
            if vol_ratio > 2.5:
                reasons.append(
                    f"Volume {vol_ratio:.1f}x average — unusual activity, monitor closely"
                )

        # 7. Holding period / tax
        if days_held > 365:
            score += 1
            reasons.append(f"Held {days_held // 365}y+ — LTCG (10% above ₹1L)")
        elif days_held > 0 and days_held <= 365:
            remaining = 365 - days_held
            reasons.append(f"Held {days_held}d — STCG (15%). {remaining}d to LTCG")

        # 8. Concentration risk
        if total_portfolio > 0 and invested > 0:
            pct_of_portfolio = (invested / total_portfolio) * 100
            if pct_of_portfolio > 25:
                score -= 1
                reasons.append(
                    f"⚠️ {pct_of_portfolio:.0f}% of portfolio — over-concentrated, consider reducing"
                )
            elif pct_of_portfolio > 15:
                reasons.append(
                    f"{pct_of_portfolio:.0f}% of portfolio — moderately concentrated"
                )

        # 9. Recent performance
        ret_1m = returns.get("1m")
        ret_6m = returns.get("6m")
        if ret_1m is not None:
            if ret_1m > 10:
                reasons.append(f"Strong 1M return ({ret_1m:+.1f}%)")
            elif ret_1m < -10:
                score -= 1
                reasons.append(f"Weak 1M ({ret_1m:+.1f}%) — short-term trouble")
        if ret_6m is not None:
            if ret_6m > 20:
                score += 1
                reasons.append(f"Strong 6M return ({ret_6m:+.1f}%)")
            elif ret_6m < -15:
                score -= 1
                reasons.append(f"Poor 6M return ({ret_6m:+.1f}%) — sustained decline")

        # 10. News sentiment (category-weighted)
        try:
            stock_news = fetch_ticker_news(ticker, name, max_items=5)
            if stock_news:
                _CAT_W = {
                    "earnings": 2.0,
                    "regulation": 1.5,
                    "analyst": 1.5,
                    "expansion": 1.2,
                    "management": 1.0,
                    "dividend": 1.0,
                    "sector": 0.8,
                    "macro": 0.7,
                }
                w_sent = 0
                top_cat = "general"
                cat_c = {}
                for n in stock_news:
                    imp = analyze_news_impact(n, ticker, name)
                    c = imp["category"]
                    cat_c[c] = cat_c.get(c, 0) + 1
                    w = _CAT_W.get(c, 1.0)
                    if imp["sentiment"] == "bearish":
                        w_sent -= w
                    elif imp["sentiment"] == "bullish":
                        w_sent += w
                if cat_c:
                    top_cat = max(cat_c, key=cat_c.get)

                if w_sent <= -4:
                    score -= 2
                    reasons.append(
                        f"📰 Heavily negative news ({top_cat}) — consider reducing exposure"
                    )
                elif w_sent <= -2:
                    score -= 1
                    reasons.append(
                        f"📰 Negative news trend ({top_cat}) — watch closely"
                    )
                elif w_sent >= 4:
                    score += 1
                    reasons.append(
                        f"📰 Strong positive news ({top_cat}) — sentiment supports holding"
                    )
                elif w_sent >= 2:
                    reasons.append(f"📰 Positive news trend ({top_cat})")
        except Exception:
            pass

        # 11. Company fundamentals track record
        try:
            eg = info.get("earningsGrowth")
            rg = info.get("revenueGrowth")
            roe_val = info.get("returnOnEquity")
            de = info.get("debtToEquity")

            if eg is not None:
                eg_pct = eg * 100
                if eg_pct > 20:
                    score += 1
                    reasons.append(
                        f"📈 Earnings growing {eg_pct:+.0f}% — strong business momentum"
                    )
                elif eg_pct < -15:
                    score -= 1
                    reasons.append(
                        f"📉 Earnings declining {eg_pct:+.0f}% — deteriorating profitability"
                    )

            if rg is not None and eg is not None:
                rg_pct = rg * 100
                if rg_pct < -5 and eg * 100 < -10:
                    score -= 1
                    reasons.append(
                        f"⚠️ Both revenue ({rg_pct:+.0f}%) and earnings declining — business weakening"
                    )

            if roe_val is not None:
                roe_pct = roe_val * 100
                if roe_pct > 20:
                    reasons.append(f"ROE {roe_pct:.0f}% — excellent capital efficiency")
                elif roe_pct < 5 and roe_pct > 0:
                    score -= 1
                    reasons.append(f"ROE {roe_pct:.0f}% — poor returns on capital")

            if de is not None and de > 150:
                score -= 1
                reasons.append(f"D/E {de:.0f}% — high leverage increases risk")
        except Exception:
            pass

        # --- Verdict ---
        if score >= 3:
            verdict = "ADD MORE"
            verdict_detail = (
                "Strong performer with good fundamentals — consider buying more."
            )
        elif score >= 1:
            verdict = "HOLD"
            verdict_detail = "Doing fine — continue holding and review quarterly."
        elif score >= -1:
            verdict = "HOLD & WATCH"
            verdict_detail = (
                "Some concerns — hold but monitor closely. Set a stop-loss."
            )
        elif score >= -3:
            verdict = "REDUCE"
            verdict_detail = (
                "Multiple warning signs — consider selling part of your position."
            )
        else:
            verdict = "CONSIDER SELLING"
            verdict_detail = (
                "Performing poorly on most metrics — seriously evaluate exiting."
            )

        # Risk level
        if atr_pct > 4 or (rsi is not None and (rsi < 25 or rsi > 80)):
            risk_level = "Very High"
        elif atr_pct > 2.5 or (rsi is not None and (rsi < 30 or rsi > 70)):
            risk_level = "High"
        elif atr_pct > 1.5:
            risk_level = "Moderate"
        else:
            risk_level = "Low"

        return {
            "name": name,
            "ticker": ticker,
            "sector": sector,
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "current_price": round(current_price, 2),
            "buy_price": round(buy_price, 2),
            "quantity": quantity,
            "total_return_pct": round(total_return_pct, 2),
            "returns": {k: round(v, 2) for k, v in returns.items()},
            "rsi": round(rsi, 1) if rsi else None,
            "sma50": round(sma50, 2) if sma50 else None,
            "sma200": round(sma200, 2) if sma200 else None,
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "range_pct": round(range_pct, 1),
            "from_high_pct": round(from_high_pct, 1),
            "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
            "forward_pe": round(forward_pe, 1) if forward_pe else None,
            "dividend_yield": (
                round(dividend_yield * 100, 2) if dividend_yield else None
            ),
            "volatility": round(volatility, 1) if volatility else None,
            "risk_level": risk_level,
            "days_held": days_held,
            "verdict": verdict,
            "verdict_detail": verdict_detail,
            "reasons": reasons,
            "score": score,
        }

    raw_results = list(_SHARED_POOL.map(_analyze_one, stock_holdings))
    results = [r for r in raw_results if r is not None]

    # Sort: worst verdict first
    verdict_order = {
        "CONSIDER SELLING": 0,
        "REDUCE": 1,
        "HOLD & WATCH": 2,
        "HOLD": 3,
        "ADD MORE": 4,
    }
    results.sort(key=lambda x: verdict_order.get(x["verdict"], 2))

    return results


def _get_market_trend():
    """Fetch current Nifty 50 RSI, VIX, and 1-month change for trend context."""
    try:
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="3mo")
        if hist.empty or len(hist) < 20:
            return None

        prices = hist["Close"].values
        nifty_rsi = compute_rsi(prices)
        change_1m = (
            ((prices[-1] - prices[-22]) / prices[-22]) * 100 if len(prices) >= 22 else 0
        )

        vix_val = None
        try:
            vix = yf.Ticker("^INDIAVIX")
            vix_hist = vix.history(period="5d")
            if not vix_hist.empty:
                vix_val = round(float(vix_hist["Close"].iloc[-1]), 1)
        except Exception:
            try:
                vix2 = yf.Ticker("^VIX")
                vix_hist2 = vix2.history(period="5d")
                if not vix_hist2.empty:
                    vix_val = round(float(vix_hist2["Close"].iloc[-1]), 1)
            except Exception:
                pass

        return {
            "nifty_rsi": round(nifty_rsi, 1) if nifty_rsi else None,
            "nifty_change_1m": round(change_1m, 1),
            "vix": vix_val,
            "nifty_price": round(float(prices[-1]), 0),
        }
    except Exception:
        return None


# --- Goal persistence ---


def save_goal(goal, user_id=None):
    """Save a financial goal to DB or data/goals.json.

    goal dict should have: name, target, years, expected_return, monthly_sip, created_date
    """
    import json, os

    try:
        import db as _db

        if _db.is_db_available():
            return _db.save_goal(goal, user_id=user_id)
    except ImportError:
        pass

    goals_path = os.path.join(os.path.dirname(__file__), "data", "goals.json")
    goals = load_goals()
    goal["id"] = max((g.get("id", 0) for g in goals), default=0) + 1
    if "created_date" not in goal:
        goal["created_date"] = datetime.now().strftime("%Y-%m-%d")
    goals.append(goal)
    tmp_path = goals_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(goals, f, indent=2)
    os.replace(tmp_path, goals_path)
    return goal["id"]


def load_goals(user_id=None):
    """Load saved goals from DB or data/goals.json."""
    import json, os

    try:
        import db as _db

        if _db.is_db_available() and user_id:
            return _db.load_goals(user_id=user_id)
    except ImportError:
        pass

    goals_path = os.path.join(os.path.dirname(__file__), "data", "goals.json")
    try:
        with open(goals_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def delete_goal(goal_id, user_id=None):
    """Delete a goal by ID."""
    import json, os

    try:
        import db as _db

        if _db.is_db_available() and user_id:
            _db.delete_goal(goal_id, user_id=user_id)
            return
    except ImportError:
        pass

    goals_path = os.path.join(os.path.dirname(__file__), "data", "goals.json")
    goals = load_goals()
    goals = [g for g in goals if g.get("id") != goal_id]
    tmp_path = goals_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(goals, f, indent=2)
    os.replace(tmp_path, goals_path)


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------


def compute_rsi(prices, period=14):
    """Compute RSI from a price series."""
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def rsi_signal(rsi):
    if rsi is None:
        return "N/A"
    if rsi >= 70:
        return "⚠️ Overbought"
    elif rsi <= 30:
        return "🟢 Oversold (buy zone)"
    elif rsi <= 40:
        return "👀 Near oversold"
    elif rsi >= 60:
        return "📈 Strong momentum"
    return "➡️ Neutral"


def trend_signal(price, sma50, sma200):
    """Determine trend from moving averages."""
    if sma50 is None or sma200 is None:
        return "N/A"
    if sma50 > sma200 and price > sma50:
        return "🟢 Strong Uptrend"
    elif sma50 > sma200:
        return "📈 Uptrend"
    elif sma50 < sma200 and price < sma50:
        return "🔴 Strong Downtrend"
    elif sma50 < sma200:
        return "📉 Downtrend"
    return "➡️ Sideways"


def ma_crossover(sma50_prev, sma200_prev, sma50_now, sma200_now):
    """Detect golden cross / death cross."""
    if None in (sma50_prev, sma200_prev, sma50_now, sma200_now):
        return None
    if sma50_prev <= sma200_prev and sma50_now > sma200_now:
        return "✨ GOLDEN CROSS — bullish signal!"
    elif sma50_prev >= sma200_prev and sma50_now < sma200_now:
        return "💀 DEATH CROSS — bearish signal!"
    return None


def compute_ema(prices, period):
    """Compute Exponential Moving Average (Varsity Module 2)."""
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = np.mean(prices[:period])
    for p in prices[period:]:
        ema = (p - ema) * multiplier + ema
    return round(ema, 2)


def compute_macd(prices):
    """Compute MACD indicator (Varsity Module 2 - Moving Averages).

    MACD = EMA(12) - EMA(26), Signal = EMA(9) of MACD line.
    Returns dict with macd, signal, histogram, crossover.
    """
    if len(prices) < 35:
        return None

    # Build EMA series
    def _ema_series(data, period):
        mult = 2 / (period + 1)
        ema = [np.mean(data[:period])]
        for p in data[period:]:
            ema.append((p - ema[-1]) * mult + ema[-1])
        return ema

    ema12 = _ema_series(prices, 12)
    ema26 = _ema_series(prices, 26)

    # Align: ema12 starts at index 12, ema26 at index 26
    # MACD starts at index 26: ema12[14:] vs ema26[0:]
    offset = 26 - 12  # 14
    macd_line = [e12 - e26 for e12, e26 in zip(ema12[offset:], ema26)]

    if len(macd_line) < 9:
        return None

    signal_line = _ema_series(macd_line, 9)
    # Align signal with macd
    s_offset = 9
    histogram = [m - s for m, s in zip(macd_line[s_offset - 1 :], signal_line)]

    macd_val = round(macd_line[-1], 2)
    signal_val = round(signal_line[-1], 2)
    hist_val = round(histogram[-1], 2)

    # Crossover detection
    crossover = None
    if len(macd_line) >= 2 and len(signal_line) >= 2:
        prev_diff = macd_line[-2] - signal_line[-2]
        curr_diff = macd_line[-1] - signal_line[-1]
        if prev_diff <= 0 and curr_diff > 0:
            crossover = "BULLISH"
        elif prev_diff >= 0 and curr_diff < 0:
            crossover = "BEARISH"

    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": hist_val,
        "crossover": crossover,
    }


def compute_bollinger_bands(prices, period=20, std_dev=2):
    """Compute Bollinger Bands (Varsity Module 2 - Volatility).

    Returns dict with upper, middle (SMA), lower, %B, bandwidth.
    %B: 0 = at lower band, 1 = at upper band, <0 = below, >1 = above.
    """
    if len(prices) < period:
        return None

    sma = np.mean(prices[-period:])
    std = np.std(prices[-period:])
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    current = prices[-1]
    pct_b = (current - lower) / (upper - lower) if upper != lower else 0.5
    bandwidth = ((upper - lower) / sma) * 100 if sma > 0 else 0

    return {
        "upper": round(upper, 2),
        "middle": round(sma, 2),
        "lower": round(lower, 2),
        "pct_b": round(pct_b, 2),
        "bandwidth": round(bandwidth, 2),
        "current": round(current, 2),
    }


def compute_atr(highs, lows, closes, period=14):
    """Compute Average True Range (Varsity Module 9 - Risk Management).

    ATR measures volatility — used for stop-loss placement and position sizing.
    """
    if len(closes) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr = np.mean(true_ranges[:period])
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period

    return round(atr, 2)


def detect_candlestick_patterns(opens, highs, lows, closes):
    """Detect key candlestick patterns (Varsity Module 2 - Candlesticks).

    Checks the last 3 candles for: Doji, Hammer, Shooting Star,
    Bullish/Bearish Engulfing, Morning/Evening Star.
    Returns list of detected patterns with signal direction.
    """
    if len(closes) < 3:
        return []

    patterns = []
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    body = abs(c - o)
    total_range = h - l if h != l else 0.001
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l

    # Previous candle
    o1, h1, l1, c1 = opens[-2], highs[-2], lows[-2], closes[-2]
    body1 = abs(c1 - o1)

    # Doji — tiny body relative to range
    if body < total_range * 0.1:
        patterns.append(("Doji", "⚪ Indecision — trend may reverse", "NEUTRAL"))

    # Hammer — small body at top, long lower shadow (bullish reversal)
    if lower_shadow > body * 2 and upper_shadow < body * 0.5 and c >= o:
        patterns.append(
            ("Hammer", "🟢 Bullish reversal — buyers stepped in at lows", "BULLISH")
        )

    # Shooting Star — small body at bottom, long upper shadow (bearish reversal)
    if upper_shadow > body * 2 and lower_shadow < body * 0.5 and c <= o:
        patterns.append(
            ("Shooting Star", "🔴 Bearish reversal — sellers rejected highs", "BEARISH")
        )

    # Bullish Engulfing — current green candle engulfs previous red
    if c1 < o1 and c > o and o <= c1 and c >= o1:
        patterns.append(
            ("Bullish Engulfing", "🟢 Strong buying — reversal signal", "BULLISH")
        )

    # Bearish Engulfing — current red candle engulfs previous green
    if c1 > o1 and c < o and o >= c1 and c <= o1:
        patterns.append(
            ("Bearish Engulfing", "🔴 Strong selling — reversal signal", "BEARISH")
        )

    # Morning Star (3-candle bullish reversal)
    if len(closes) >= 3:
        o2, c2 = opens[-3], closes[-3]
        if c2 < o2 and body1 < abs(c2 - o2) * 0.3 and c > o and c > (o2 + c2) / 2:
            patterns.append(
                ("Morning Star", "🟢 Bullish reversal — dawn after darkness", "BULLISH")
            )

    # Evening Star (3-candle bearish reversal)
    if len(closes) >= 3:
        o2, c2 = opens[-3], closes[-3]
        if c2 > o2 and body1 < abs(c2 - o2) * 0.3 and c < o and c < (o2 + c2) / 2:
            patterns.append(
                ("Evening Star", "🔴 Bearish reversal — sunset after rally", "BEARISH")
            )

    return patterns


def compute_stop_loss(price, atr, method="atr"):
    """Calculate stop-loss and position sizing (Varsity Module 9).

    Methods:
        atr: 2x ATR below price (Chandelier Exit)
        percent: Fixed 5% below price

    Returns dict with stop_loss, risk_per_share, risk_pct.
    """
    if method == "atr" and atr:
        stop = round(price - 2 * atr, 2)
    else:
        stop = round(price * 0.95, 2)

    risk = round(price - stop, 2)
    risk_pct = round((risk / price) * 100, 2) if price > 0 else 0

    return {
        "stop_loss": stop,
        "risk_per_share": risk,
        "risk_pct": risk_pct,
        "target_1": round(price + risk, 2),  # 1:1 risk-reward
        "target_2": round(price + 2 * risk, 2),  # 1:2 risk-reward
        "target_3": round(price + 3 * risk, 2),  # 1:3 risk-reward
    }


def position_size(capital, risk_pct_of_capital, price, stop_loss):
    """Calculate how many shares to buy based on risk (Varsity Module 9).

    Args:
        capital: total capital available
        risk_pct_of_capital: max % of capital to risk per trade (typically 1-2%)
        price: current share price
        stop_loss: stop-loss price

    Returns dict with qty, amount, risk_amount.
    """
    risk_amount = capital * risk_pct_of_capital / 100
    risk_per_share = price - stop_loss
    if risk_per_share <= 0:
        return {"qty": 0, "amount": 0, "risk_amount": 0}

    qty = int(risk_amount / risk_per_share)
    return {
        "qty": qty,
        "amount": round(qty * price, 2),
        "risk_amount": round(qty * risk_per_share, 2),
    }


def get_fundamental_metrics(ticker_symbol):
    """Fetch key fundamental metrics for a stock (Varsity Module 3).

    Returns P/E, P/B, ROE, debt-to-equity, market cap, dividend yield, etc.
    """
    try:
        t = yf.Ticker(ticker_symbol)
        info = t.info or {}

        pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        pb = info.get("priceToBook")
        roe = info.get("returnOnEquity")
        debt_equity = info.get("debtToEquity")
        market_cap = info.get("marketCap")
        dividend_yield = info.get("dividendYield")
        earnings_growth = info.get("earningsGrowth")
        revenue_growth = info.get("revenueGrowth")
        profit_margin = info.get("profitMargins")
        book_value = info.get("bookValue")
        eps = info.get("trailingEps")
        sector = info.get("sector", "")
        industry = info.get("industry", "")

        # Valuation signals (from Varsity Module 3 guidelines)
        signals = []
        if pe and pe < 15:
            signals.append(
                (
                    "P/E Ratio",
                    "🟢 Undervalued",
                    f"P/E {pe:.1f} — cheap relative to earnings",
                )
            )
        elif pe and pe > 40:
            signals.append(
                ("P/E Ratio", "🔴 Expensive", f"P/E {pe:.1f} — high valuation")
            )
        elif pe:
            signals.append(("P/E Ratio", "🟡 Fair", f"P/E {pe:.1f}"))

        if pb and pb < 1:
            signals.append(
                (
                    "P/B Ratio",
                    "🟢 Below book value",
                    f"P/B {pb:.1f} — trading below assets",
                )
            )
        elif pb and pb > 5:
            signals.append(("P/B Ratio", "🔴 Expensive", f"P/B {pb:.1f}"))
        elif pb:
            signals.append(("P/B Ratio", "🟡 Fair", f"P/B {pb:.1f}"))

        if roe and roe > 0.20:
            signals.append(
                (
                    "ROE",
                    "🟢 Excellent",
                    f"ROE {roe*100:.1f}% — efficient profit generation",
                )
            )
        elif roe and roe > 0.10:
            signals.append(("ROE", "🟡 Decent", f"ROE {roe*100:.1f}%"))
        elif roe:
            signals.append(
                ("ROE", "🔴 Low", f"ROE {roe*100:.1f}% — poor capital efficiency")
            )

        if debt_equity is not None and debt_equity < 50:
            signals.append(
                (
                    "Debt/Equity",
                    "🟢 Low debt",
                    f"D/E {debt_equity:.0f}% — financially strong",
                )
            )
        elif debt_equity is not None and debt_equity > 150:
            signals.append(
                (
                    "Debt/Equity",
                    "🔴 High debt",
                    f"D/E {debt_equity:.0f}% — risky leverage",
                )
            )
        elif debt_equity is not None:
            signals.append(("Debt/Equity", "🟡 Moderate", f"D/E {debt_equity:.0f}%"))

        return {
            "pe": pe,
            "forward_pe": forward_pe,
            "pb": pb,
            "roe": round(roe * 100, 1) if roe else None,
            "debt_equity": round(debt_equity, 1) if debt_equity else None,
            "market_cap": market_cap,
            "dividend_yield": (
                round(dividend_yield * 100, 2) if dividend_yield else None
            ),
            "earnings_growth": (
                round(earnings_growth * 100, 1) if earnings_growth else None
            ),
            "revenue_growth": (
                round(revenue_growth * 100, 1) if revenue_growth else None
            ),
            "profit_margin": round(profit_margin * 100, 1) if profit_margin else None,
            "book_value": book_value,
            "eps": eps,
            "sector": sector,
            "industry": industry,
            "signals": signals,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main analysis for a single ticker
# ---------------------------------------------------------------------------

# In-memory cache for analyze_ticker results (TTL = 5 min)
_ticker_cache = {}
_TICKER_CACHE_TTL = 300  # seconds


def analyze_ticker(ticker_symbol):
    """Fetch and analyze a single ticker. Returns dict or None. Cached 5 min."""
    now = datetime.now().timestamp()
    cached = _ticker_cache.get(ticker_symbol)
    if cached and (now - cached[0]) < _TICKER_CACHE_TTL:
        return cached[1]

    result = _analyze_ticker_impl(ticker_symbol)
    _ticker_cache[ticker_symbol] = (now, result)
    return result


def _analyze_ticker_impl(ticker_symbol):
    """Actual implementation of analyze_ticker."""
    try:
        ticker = yf.Ticker(ticker_symbol)

        # 1-year history for moving averages & RSI
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 20:
            return None

        closes = hist["Close"].values
        volumes = hist["Volume"].values
        current_price = round(closes[-1], 2)

        # Daily change
        daily_change = round(closes[-1] - closes[-2], 2) if len(closes) >= 2 else 0
        daily_change_pct = (
            round((daily_change / closes[-2]) * 100, 2) if len(closes) >= 2 else 0
        )

        # 52-week high/low
        high_52w = round(closes.max(), 2)
        low_52w = round(closes.min(), 2)
        from_high = round(((current_price - high_52w) / high_52w) * 100, 2)
        from_low = round(((current_price - low_52w) / low_52w) * 100, 2)

        # Moving averages
        sma50 = round(np.mean(closes[-50:]), 2) if len(closes) >= 50 else None
        sma200 = round(np.mean(closes[-200:]), 2) if len(closes) >= 200 else None
        sma50_prev = round(np.mean(closes[-51:-1]), 2) if len(closes) >= 51 else None
        sma200_prev = round(np.mean(closes[-201:-1]), 2) if len(closes) >= 201 else None

        # RSI
        rsi = compute_rsi(closes)

        # Volume analysis
        avg_vol = int(np.mean(volumes[-20:])) if len(volumes) >= 20 else None
        latest_vol = int(volumes[-1])
        vol_ratio = round(latest_vol / avg_vol, 2) if avg_vol and avg_vol > 0 else None

        # YTD return
        ytd_start = hist.loc[hist.index >= f"{datetime.now().year}-01-01"]
        ytd_return = None
        if not ytd_start.empty:
            ytd_return = round(
                (
                    (current_price - ytd_start["Close"].iloc[0])
                    / ytd_start["Close"].iloc[0]
                )
                * 100,
                2,
            )

        # 1-year return
        one_yr_return = round(((current_price - closes[0]) / closes[0]) * 100, 2)

        # PE ratio (if available)
        info = ticker.info or {}
        pe_ratio = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        market_cap = info.get("marketCap")
        sector = info.get("sector", "")
        dividend_yield = info.get("dividendYield")

        trend = trend_signal(current_price, sma50, sma200)
        crossover = ma_crossover(sma50_prev, sma200_prev, sma50, sma200)

        # New indicators (Varsity Module 2 & 9)
        macd = compute_macd(closes)
        bollinger = compute_bollinger_bands(closes)
        atr = compute_atr(hist["High"].values, hist["Low"].values, closes)
        candle_patterns = detect_candlestick_patterns(
            hist["Open"].values,
            hist["High"].values,
            hist["Low"].values,
            closes,
        )
        stop_loss_info = compute_stop_loss(current_price, atr) if atr else None

        return {
            "price": current_price,
            "daily_change": daily_change,
            "daily_change_pct": daily_change_pct,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "from_high_pct": from_high,
            "from_low_pct": from_low,
            "sma50": sma50,
            "sma200": sma200,
            "rsi": rsi,
            "rsi_signal": rsi_signal(rsi),
            "trend": trend,
            "crossover": crossover,
            "vol_ratio": vol_ratio,
            "ytd_return": ytd_return,
            "one_yr_return": one_yr_return,
            "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
            "forward_pe": round(forward_pe, 2) if forward_pe else None,
            "market_cap": market_cap,
            "sector": sector,
            "dividend_yield": (
                round(dividend_yield * 100, 2) if dividend_yield else None
            ),
            "macd": macd,
            "bollinger": bollinger,
            "atr": atr,
            "candlestick_patterns": candle_patterns,
            "stop_loss": stop_loss_info,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# SIP pause helpers
# ---------------------------------------------------------------------------


def _is_month_paused(year, month, pause_periods):
    """Check if a given year/month falls within any SIP pause period.

    Args:
        year: calendar year
        month: calendar month (1-12)
        pause_periods: list of {"pause_date": "YYYY-MM-DD", "resume_date": "YYYY-MM-DD" or None}

    Returns True if the month is inside a paused window.
    """
    if not pause_periods:
        return False
    check = date(year, month, 1)
    for pp in pause_periods:
        try:
            p_start = (
                datetime.strptime(pp["pause_date"], "%Y-%m-%d").date().replace(day=1)
            )
        except (KeyError, ValueError):
            continue
        p_end = None
        if pp.get("resume_date"):
            try:
                p_end = (
                    datetime.strptime(pp["resume_date"], "%Y-%m-%d")
                    .date()
                    .replace(day=1)
                )
            except ValueError:
                pass
        if p_end is None:
            # Still paused — everything from pause_date onward is paused
            if check >= p_start:
                return True
        else:
            if p_start <= check < p_end:
                return True
    return False


def is_sip_currently_paused(holding):
    """Return True if a SIP holding is currently paused (no resume_date on latest pause)."""
    periods = holding.get("sip_pause_periods", [])
    if not periods:
        return False
    latest = periods[-1]
    return not latest.get("resume_date")


# ---------------------------------------------------------------------------
# SIP value estimator
# ---------------------------------------------------------------------------


def estimate_sip_value(ticker_symbol, monthly_amount, months=12, pause_periods=None):
    """Estimate current value of SIP investments over N months using historical prices.

    If pause_periods is provided, months where the SIP was paused are skipped
    (no purchase made, but previously bought units continue to grow).
    """
    if monthly_amount <= 0:
        return None
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period=f"{months + 1}mo")
        if hist.empty:
            return None

        # Simulate monthly purchases using first trading day of each month
        hist_monthly = hist.resample("MS").first().dropna()
        if len(hist_monthly) < 2:
            return None

        current_price = hist["Close"].iloc[-1]
        total_units = 0
        total_invested = 0
        months_active = 0
        months_paused = 0

        for idx_date, row in hist_monthly.iterrows():
            buy_price = row["Close"]
            if buy_price > 0:
                # Check if this month was paused
                ts = idx_date.to_pydatetime()
                if pause_periods and _is_month_paused(ts.year, ts.month, pause_periods):
                    months_paused += 1
                    continue  # skip purchase but units already bought keep growing
                units = monthly_amount / buy_price
                total_units += units
                total_invested += monthly_amount
                months_active += 1

        current_value = total_units * current_price
        returns_pct = (
            ((current_value - total_invested) / total_invested) * 100
            if total_invested > 0
            else 0
        )

        return {
            "invested": round(total_invested, 2),
            "current_value": round(current_value, 2),
            "returns_pct": round(returns_pct, 2),
            "profit": round(current_value - total_invested, 2),
            "months_active": months_active,
            "months_paused": months_paused,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Analyze full portfolio
# ---------------------------------------------------------------------------


def analyze_portfolio(holdings):
    """Run analysis on all holdings that have tickers (parallelized when > 3)."""
    results = []
    tickers_to_analyze = []

    for i, h in enumerate(holdings):
        if not h["ticker"]:
            results.append({"holding": h, "analysis": None, "sip_value": None})
        else:
            results.append(None)  # placeholder
            tickers_to_analyze.append((i, h))

    def _analyze_one(item):
        idx, h = item
        analysis = analyze_ticker(h["ticker"])
        sip_value = None
        if h["sip_monthly"] > 0:
            sip_value = estimate_sip_value(
                h["ticker"], h["sip_monthly"], pause_periods=h.get("sip_pause_periods")
            )
        return idx, {"holding": h, "analysis": analysis, "sip_value": sip_value}

    if len(tickers_to_analyze) <= 3:
        # Sequential — thread pool overhead not worth it for few tickers
        for item in tickers_to_analyze:
            try:
                idx, result = _analyze_one(item)
                results[idx] = result
            except Exception:
                idx = item[0]
                h = item[1]
                results[idx] = {"holding": h, "analysis": None, "sip_value": None}
    else:
        futures = {
            _SHARED_POOL.submit(_analyze_one, item): item for item in tickers_to_analyze
        }
        for future in as_completed(futures):
            try:
                idx, result = future.result()
                results[idx] = result
            except Exception:
                idx = futures[future][0]
                h = futures[future][1]
                results[idx] = {"holding": h, "analysis": None, "sip_value": None}

    return results


# ---------------------------------------------------------------------------
# Format for WhatsApp
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# NEWS FEED — Google News RSS (free, no API key)
# ---------------------------------------------------------------------------

NEWS_FEEDS = {
    "Indian Stock Market": "https://news.google.com/rss/search?q=indian+stock+market+nifty+sensex&hl=en-IN&gl=IN&ceid=IN:en",
    "Gold Price India": "https://news.google.com/rss/search?q=gold+price+india&hl=en-IN&gl=IN&ceid=IN:en",
    "Mutual Funds India": "https://news.google.com/rss/search?q=mutual+funds+india+SIP&hl=en-IN&gl=IN&ceid=IN:en",
    "Investment Opportunities": "https://news.google.com/rss/search?q=investment+opportunities+india+stocks+2026&hl=en-IN&gl=IN&ceid=IN:en",
}

# Keywords that signal actionable news
BULLISH_KEYWORDS = [
    "rally",
    "surge",
    "bull",
    "record high",
    "breakout",
    "upgrade",
    "buy",
    "outperform",
    "growth",
    "positive",
    "gains",
    "boom",
    "recovery",
]
BEARISH_KEYWORDS = [
    "crash",
    "fall",
    "bear",
    "plunge",
    "downgrade",
    "sell",
    "correction",
    "decline",
    "loss",
    "warning",
    "risk",
    "slump",
    "weak",
]


def _simple_sentiment(text):
    """Quick keyword-based sentiment: 'bullish', 'bearish', or 'neutral'."""
    text_lower = text.lower()
    bull_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
    bear_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)
    if bull_count > bear_count:
        return "bullish"
    elif bear_count > bull_count:
        return "bearish"
    return "neutral"


def _extract_summary(entry):
    """Extract a short summary from RSS entry, stripping HTML."""
    import re

    raw = entry.get("summary", entry.get("description", ""))
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", "", raw).strip()
    # Take first 200 chars
    if len(clean) > 200:
        clean = clean[:200].rsplit(" ", 1)[0] + "..."
    return clean


def fetch_news(category=None, max_items=5):
    """Fetch news from Google News RSS. Returns list of dicts."""
    feeds = NEWS_FEEDS if category is None else {category: NEWS_FEEDS.get(category, "")}
    all_news = []

    def _fetch_one_feed(cat_url):
        cat, url = cat_url
        items = []
        if not url:
            return items
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                sentiment = _simple_sentiment(entry.title)
                items.append(
                    {
                        "category": cat,
                        "title": entry.title,
                        "link": entry.link,
                        "published": entry.get("published", ""),
                        "sentiment": sentiment,
                        "summary": _extract_summary(entry),
                    }
                )
        except Exception:
            pass
        return items

    futures = [_SHARED_POOL.submit(_fetch_one_feed, item) for item in feeds.items()]
    for future in as_completed(futures):
        try:
            all_news.extend(future.result())
        except Exception:
            continue

    return all_news


def fetch_ticker_news(ticker_symbol, company_name="", max_items=5):
    """Fetch news for a specific stock/MF ticker."""
    search_term = company_name or ticker_symbol.replace(".NS", "").replace("^", "")
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(search_term)}+stock+india&hl=en-IN&gl=IN&ceid=IN:en"
    results = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
            sentiment = _simple_sentiment(entry.title)
            results.append(
                {
                    "title": entry.title,
                    "link": entry.link,
                    "published": entry.get("published", ""),
                    "sentiment": sentiment,
                    "summary": _extract_summary(entry),
                }
            )
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Per-stock NEWS IMPACT ANALYSIS — why it matters for your holding
# ---------------------------------------------------------------------------

# Keyword → impact category mapping
_NEWS_IMPACT_CATEGORIES = {
    "earnings": {
        "keywords": [
            "earnings",
            "profit",
            "revenue",
            "quarterly results",
            "q1",
            "q2",
            "q3",
            "q4",
            "net income",
            "topline",
            "bottomline",
            "EPS",
        ],
        "good": "{name}'s earnings or profits look strong — the stock price usually goes up when a company makes more money.",
        "bad": "{name}'s earnings or profits disappointed — the stock price usually drops when a company makes less money than expected.",
    },
    "management": {
        "keywords": [
            "CEO",
            "management",
            "leadership",
            "board",
            "resign",
            "appoint",
            "chairman",
            "director",
        ],
        "good": "Positive leadership news for {name} — new or strong management usually means the company is headed in a good direction.",
        "bad": "There's leadership trouble at {name} — when top people leave or there's controversy, the stock often dips until things settle.",
    },
    "regulation": {
        "keywords": [
            "regulation",
            "SEBI",
            "RBI",
            "government",
            "policy",
            "tax",
            "ban",
            "approval",
            "licence",
            "compliance",
            "fine",
            "penalty",
        ],
        "good": "Government or regulatory news is working in {name}'s favour — approvals or policy support help the stock go up.",
        "bad": "{name} is facing regulatory trouble (fines, bans, or stricter rules) — this can hurt the stock price.",
    },
    "expansion": {
        "keywords": [
            "expansion",
            "new plant",
            "acquisition",
            "merger",
            "partnership",
            "deal",
            "contract",
            "order",
            "launch",
            "capacity",
        ],
        "good": "{name} is growing — new deals, products, or expansion means more money coming in, which is good for the stock.",
        "bad": "A deal or expansion for {name} didn't go well — failed deals or overspending can drag the stock down.",
    },
    "sector": {
        "keywords": [
            "sector",
            "industry",
            "market",
            "competition",
            "demand",
            "supply",
            "commodity",
            "crude",
            "metal",
        ],
        "good": "{name}'s industry is doing well right now — when the whole sector goes up, your stock usually goes up too.",
        "bad": "{name}'s industry is struggling — even good companies can fall when their whole sector is going down.",
    },
    "analyst": {
        "keywords": [
            "upgrade",
            "downgrade",
            "target price",
            "analyst",
            "rating",
            "buy rating",
            "sell rating",
            "outperform",
            "underperform",
        ],
        "good": "Experts are recommending {name} — when analysts say 'buy', big investors usually follow, pushing the price up.",
        "bad": "Experts are warning about {name} — when analysts downgrade a stock, big investors often sell, pushing the price down.",
    },
    "dividend": {
        "keywords": ["dividend", "buyback", "bonus", "stock split", "payout"],
        "good": "{name} is sharing profits with investors (dividend/buyback) — this means the company is doing well and is confident about its future.",
        "bad": "{name} cut or reduced its dividend — this usually means the company is short on cash, which is a warning sign.",
    },
    "macro": {
        "keywords": [
            "inflation",
            "interest rate",
            "GDP",
            "recession",
            "global",
            "FII",
            "FDI",
            "dollar",
            "rupee",
            "trade war",
            "tariff",
        ],
        "good": "The economy is looking good (lower interest rates, growth) — this helps all stocks including {name}.",
        "bad": "The economy is facing problems (inflation, global tensions) — this can pull down {name}'s price even if the company is fine.",
    },
}


def analyze_news_impact(news_item, ticker_symbol="", company_name="", holding_amount=0):
    """Analyze why a news item matters for a specific holding.

    Returns dict with:
      - category: the type of news (earnings, regulation, etc.)
      - summary: one plain-English sentence explaining what this means for you
      - action: short, direct recommendation
      - sentiment_label: "Good news" / "Bad news" / "Just info"
    """
    title_lower = news_item["title"].lower()
    summary_lower = news_item.get("summary", "").lower()
    full_text = f"{title_lower} {summary_lower}"
    sentiment = news_item.get("sentiment", "neutral")

    # Identify the news category
    matched_category = None
    max_matches = 0
    for cat_key, cat_info in _NEWS_IMPACT_CATEGORIES.items():
        matches = sum(1 for kw in cat_info["keywords"] if kw.lower() in full_text)
        if matches > max_matches:
            max_matches = matches
            matched_category = cat_key

    if matched_category is None:
        matched_category = "sector"  # default fallback

    cat = _NEWS_IMPACT_CATEGORIES[matched_category]
    name = company_name or ticker_symbol.replace(".NS", "")

    # Build one clear summary + short action
    if sentiment == "bullish":
        summary = cat["good"].format(name=name)
        sentiment_label = "Good news"
        if holding_amount > 0:
            action = f"You can hold {name}. Your ₹{holding_amount:,.0f} investment looks safe."
        else:
            action = (
                f"Could be a good time to buy {name} — but watch for 1-2 days first."
            )
    elif sentiment == "bearish":
        summary = cat["bad"].format(name=name)
        sentiment_label = "Bad news"
        if holding_amount > 0:
            action = f"Keep an eye on {name}. Don't panic sell — wait and see if this gets worse."
        else:
            action = f"Wait before buying {name}. Let the price settle first."
    else:
        summary = f"This news about {name} doesn't clearly help or hurt the stock. No need to worry."
        sentiment_label = "Just info"
        action = "No action needed."

    return {
        "category": matched_category,
        "summary": summary,
        "action": action,
        "sentiment": sentiment,
        "sentiment_label": sentiment_label,
    }


def fetch_portfolio_news_with_impact(holdings, max_per_stock=3):
    """Fetch news for all portfolio holdings with impact analysis.

    Returns list of dicts: {holding, news_items: [{...news, impact: {...}}]}
    """
    results = []
    for h in holdings:
        if not h.get("ticker"):
            continue

        news_items = fetch_ticker_news(h["ticker"], h["name"], max_items=max_per_stock)
        enriched = []
        for item in news_items:
            impact = analyze_news_impact(
                item,
                ticker_symbol=h["ticker"],
                company_name=h["name"],
                holding_amount=h["amount"],
            )
            enriched.append({**item, "impact": impact})

        if enriched:
            # Count sentiments for this stock
            bull = sum(1 for n in enriched if n["sentiment"] == "bullish")
            bear = sum(1 for n in enriched if n["sentiment"] == "bearish")
            if bull > bear:
                overall = "bullish"
            elif bear > bull:
                overall = "bearish"
            else:
                overall = "neutral"

            results.append(
                {
                    "holding": h,
                    "news_items": enriched,
                    "overall_sentiment": overall,
                    "bull_count": bull,
                    "bear_count": bear,
                }
            )

    return results


# ---------------------------------------------------------------------------
# MARKET OPPORTUNITY SCANNER — Top Gainers/Losers + Sector Screening
# ---------------------------------------------------------------------------

# Major Indian stocks to scan for opportunities
WATCHLIST_TICKERS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "HINDUNILVR.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "HCLTECH.NS",
    "AXISBANK.NS",
    "ASIANPAINT.NS",
    "MARUTI.NS",
    "SUNPHARMA.NS",
    "TITAN.NS",
    "ULTRACEMCO.NS",
    "WIPRO.NS",
    "ADANIENT.NS",
    "BAJFINANCE.NS",
    "TMCV.NS",
    "TATASTEEL.NS",
    "POWERGRID.NS",
    "NTPC.NS",
    "JSWSTEEL.NS",
    "M&M.NS",
    "TECHM.NS",
    "INDUSINDBK.NS",
    "COALINDIA.NS",
]

SECTOR_TICKERS = {
    "IT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS"],
    "Banking": [
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "SBIN.NS",
        "KOTAKBANK.NS",
        "AXISBANK.NS",
    ],
    "Auto": ["MARUTI.NS", "TMCV.NS", "TMPV.NS", "M&M.NS"],
    "Pharma": ["SUNPHARMA.NS"],
    "Energy": ["RELIANCE.NS", "NTPC.NS", "POWERGRID.NS", "COALINDIA.NS"],
    "Metals": ["TATASTEEL.NS", "JSWSTEEL.NS"],
    "FMCG": ["HINDUNILVR.NS", "ITC.NS"],
    "Infrastructure": ["LT.NS", "ULTRACEMCO.NS", "ADANIENT.NS"],
    "Finance": ["BAJFINANCE.NS"],
    "Consumer": ["TITAN.NS", "ASIANPAINT.NS"],
}


def scan_top_movers(tickers=None, top_n=5):
    """Find top gainers and losers from a watchlist (batch download)."""
    tickers = tickers or WATCHLIST_TICKERS
    movers = []

    try:
        data = yf.download(
            list(tickers), period="1mo", group_by="ticker", progress=False, threads=True
        )
    except Exception:
        return [], []

    for sym in tickers:
        try:
            hist = data[sym] if len(tickers) > 1 else data
            hist = hist.dropna(subset=["Close"])
            if len(hist) < 2:
                continue
            curr = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2]
            pct = round(((curr - prev) / prev) * 100, 2)

            closes = hist["Close"].values
            rsi = compute_rsi(closes) if len(closes) >= 15 else None

            vol_ratio = None
            if len(hist) >= 6 and hist["Volume"].iloc[-1] > 0:
                avg_vol = hist["Volume"].iloc[-6:-1].mean()
                if avg_vol > 0:
                    vol_ratio = round(hist["Volume"].iloc[-1] / avg_vol, 1)

            streak = 0
            if len(hist) >= 5:
                for i in range(-1, -5, -1):
                    if hist["Close"].iloc[i] > hist["Close"].iloc[i - 1]:
                        streak += 1
                    else:
                        break

            movers.append(
                {
                    "ticker": sym,
                    "name": sym.replace(".NS", ""),
                    "price": round(float(curr), 2),
                    "change_pct": pct,
                    "rsi": rsi,
                    "vol_ratio": vol_ratio,
                    "streak": streak,
                }
            )
        except Exception:
            continue

    movers.sort(key=lambda x: x["change_pct"], reverse=True)
    gainers = movers[:top_n]
    losers = movers[-top_n:][::-1]  # worst first
    return gainers, losers


def scan_oversold_opportunities(tickers=None):
    """Find stocks that are oversold or near 52-week lows with clear buy reasoning (parallelized)."""
    tickers = tickers or WATCHLIST_TICKERS
    opportunities = []

    def _check_one(sym):
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            if len(hist) < 50:
                return None

            closes = hist["Close"].values
            curr = closes[-1]
            high_52 = float(closes.max())
            low_52 = float(closes.min())
            from_high = ((curr - high_52) / high_52) * 100
            from_low = ((curr - low_52) / low_52) * 100
            range_pct = (
                ((curr - low_52) / (high_52 - low_52)) * 100
                if high_52 != low_52
                else 50
            )

            rsi = compute_rsi(closes)
            info = t.info or {}
            pe_ratio = info.get("trailingPE")
            sector = info.get("sector", "")

            is_opp = False
            if rsi is not None and rsi < 35:
                is_opp = True
            if from_high < -25:
                is_opp = True
            if from_low < 10:
                is_opp = True

            if not is_opp:
                return None

            why_cheap = []
            if rsi is not None and rsi < 35:
                why_cheap.append(
                    f"Momentum shows it's oversold (RSI {rsi:.0f}) — sellers may be exhausted"
                )
            if from_high < -25:
                why_cheap.append(
                    f"Dropped {abs(from_high):.0f}% from its best price this year"
                )
            if from_low < 10:
                why_cheap.append("Trading near its lowest price this year")

            buy_now_score = 0
            buy_reasoning = []
            if rsi is not None and rsi < 30:
                buy_now_score += 2
                buy_reasoning.append("Very oversold — bounce likely soon")
            elif rsi is not None and rsi < 35:
                buy_now_score += 1
                buy_reasoning.append("Oversold — could bounce")
            if from_high < -30:
                buy_now_score += 2
                buy_reasoning.append("Big discount from yearly high")
            elif from_high < -25:
                buy_now_score += 1
                buy_reasoning.append("Good discount from yearly high")
            if pe_ratio and pe_ratio < 15:
                buy_now_score += 1
                buy_reasoning.append(f"Cheap valuation (PE {pe_ratio:.0f}x)")
            elif pe_ratio and pe_ratio > 40:
                buy_now_score -= 1
                buy_reasoning.append(f"Expensive valuation (PE {pe_ratio:.0f}x)")

            if len(closes) >= 6:
                change_5d = ((curr - closes[-6]) / closes[-6]) * 100
                if change_5d > 0:
                    buy_now_score += 1
                    buy_reasoning.append("Started recovering this week")
                elif change_5d < -3:
                    buy_now_score -= 1
                    buy_reasoning.append("Still falling — might get cheaper")
            else:
                change_5d = 0

            # --- Risk assessment ---
            highs_s = hist["High"].values
            lows_s = hist["Low"].values
            atr_val = compute_atr(highs_s, lows_s, closes)
            atr_pct = (atr_val / curr * 100) if atr_val and curr else 0

            if atr_pct > 4 or (rsi is not None and rsi < 25):
                risk_level = "Very High"
            elif atr_pct > 2.5 or (rsi is not None and rsi < 30):
                risk_level = "High"
            elif atr_pct > 1.5:
                risk_level = "Moderate"
            else:
                risk_level = "Low"

            # Falling knife warning
            risk_warning = ""
            if change_5d < -5 and from_high < -30:
                risk_warning = (
                    "🔪 Falling knife — price in free fall, wait for stabilization"
                )
                buy_now_score -= 2
                buy_reasoning.append(
                    "⚠️ Falling knife risk — don't catch a falling stock"
                )
            elif change_5d < -3 and from_high < -25:
                risk_warning = "⚠️ Sharp decline — may fall further before recovering"
            elif risk_level in ("Very High", "High"):
                risk_warning = f"⚠️ {risk_level} volatility (ATR {atr_pct:.1f}%) — use strict stop-loss"

            if buy_now_score >= 3:
                buy_verdict = "Yes, today looks like a good entry"
                urgency = "high"
            elif buy_now_score >= 1:
                buy_verdict = (
                    "Decent price, but you can wait 1-2 days for a better entry"
                )
                urgency = "medium"
            else:
                buy_verdict = "Not yet — wait for the price to stabilize or drop more"
                urgency = "low"

            return {
                "ticker": sym,
                "name": sym.replace(".NS", ""),
                "price": round(curr, 2),
                "rsi": rsi,
                "from_high_pct": round(from_high, 1),
                "high_52w": round(high_52, 2),
                "low_52w": round(low_52, 2),
                "range_pct": round(range_pct, 1),
                "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
                "sector": sector,
                "why_cheap": why_cheap,
                "buy_verdict": buy_verdict,
                "buy_reasoning": buy_reasoning,
                "urgency": urgency,
                "risk_level": risk_level,
                "risk_warning": risk_warning,
                "atr_pct": round(atr_pct, 1),
            }
        except Exception:
            return None

    opportunities = [r for r in _SHARED_POOL.map(_check_one, tickers) if r is not None]

    urgency_order = {"high": 0, "medium": 1, "low": 2}
    opportunities.sort(key=lambda x: urgency_order.get(x["urgency"], 3))
    return opportunities


def suggest_stock_swaps(sell_ticker, sell_amount, holdings, tickers=None):
    """Suggest stocks to buy if you sell a holding.

    Args:
        sell_ticker: ticker of stock to sell (e.g. "ONGC.NS")
        sell_amount: how much money you'd get from selling
        holdings: user's current portfolio (to exclude already-owned stocks)
        tickers: watchlist to scan (default: WATCHLIST_TICKERS)

    Returns list of suggestions sorted by buy score.
    """
    tickers = tickers or WATCHLIST_TICKERS
    owned_tickers = {h["ticker"] for h in holdings if h.get("ticker")}
    sell_name = sell_ticker.replace(".NS", "")

    suggestions = []
    for sym in tickers:
        if sym == sell_ticker or sym in owned_tickers:
            continue
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            if len(hist) < 30:
                continue

            closes = hist["Close"].values
            curr = float(closes[-1])
            info = t.info or {}
            name = sym.replace(".NS", "")
            sector = info.get("sector", "")
            pe_ratio = info.get("trailingPE")

            # How many shares can you buy?
            shares = int(sell_amount / curr) if curr > 0 else 0
            if shares < 1:
                continue

            investment = round(shares * curr, 2)
            leftover = round(sell_amount - investment, 2)

            # Quick health check
            rsi = compute_rsi(closes)
            high_52 = float(closes.max())
            low_52 = float(closes.min())
            from_high = ((curr - high_52) / high_52) * 100

            score = 0
            pros = []
            cons = []

            if rsi is not None and rsi < 35:
                score += 2
                pros.append("Oversold — good entry point")
            elif rsi is not None and rsi < 50:
                score += 1
                pros.append("Price momentum is in your favour")
            elif rsi is not None and rsi > 70:
                score -= 2
                cons.append("Overbought — price may drop soon")

            if from_high < -25:
                score += 2
                pros.append(
                    f"Down {abs(from_high):.0f}% from yearly high — big discount"
                )
            elif from_high < -15:
                score += 1
                pros.append(f"Down {abs(from_high):.0f}% from yearly high")
            elif from_high > -5:
                score -= 1
                cons.append("Near yearly high — limited upside")

            if pe_ratio and pe_ratio < 15:
                score += 1
                pros.append(f"Cheap valuation (PE {pe_ratio:.0f}x)")
            elif pe_ratio and pe_ratio > 50:
                score -= 1
                cons.append(f"Expensive (PE {pe_ratio:.0f}x)")

            # --- Risk assessment ---
            swap_highs = hist["High"].values
            swap_lows = hist["Low"].values
            atr_val = compute_atr(swap_highs, swap_lows, closes)
            atr_pct = (atr_val / curr * 100) if atr_val and curr else 0

            if atr_pct > 4 or (rsi is not None and rsi < 25):
                risk_level = "Very High"
                cons.append(f"⚠️ Very high volatility (ATR {atr_pct:.1f}%)")
                score -= 1
            elif atr_pct > 2.5 or (rsi is not None and rsi < 30):
                risk_level = "High"
                cons.append(f"⚠️ High volatility (ATR {atr_pct:.1f}%)")
            elif atr_pct > 1.5:
                risk_level = "Moderate"
            else:
                risk_level = "Low"
                pros.append("Low volatility — stable stock")

            if score < 0:
                continue  # Skip bad options

            suggestions.append(
                {
                    "ticker": sym,
                    "name": name,
                    "price": round(curr, 2),
                    "sector": sector,
                    "shares": shares,
                    "investment": investment,
                    "leftover": leftover,
                    "score": score,
                    "pros": pros,
                    "cons": cons,
                    "rsi": rsi,
                    "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
                    "from_high_pct": round(from_high, 1),
                    "risk_level": risk_level,
                }
            )
        except Exception:
            continue

    suggestions.sort(key=lambda x: x["score"], reverse=True)
    return suggestions


def scan_sector_performance():
    """Calculate average daily change per sector and return per-stock data (batch download).

    Returns dict: {sector: {"avg_change": float, "stocks": [{"name", "price", "change_pct"}, ...]}}
    """
    # Gather all unique tickers across sectors
    all_tickers = set()
    for tickers in SECTOR_TICKERS.values():
        all_tickers.update(tickers)

    all_tickers_list = list(all_tickers)

    # Batch download all ticker data at once
    try:
        data = yf.download(
            all_tickers_list,
            period="5d",
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception:
        return {}

    ticker_data = {}
    for sym in all_tickers_list:
        try:
            hist = data[sym] if len(all_tickers_list) > 1 else data
            hist = hist.dropna(subset=["Close"])
            if len(hist) >= 2:
                curr = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                pct = round(((curr - prev) / prev) * 100, 2)
                ticker_data[sym] = {
                    "ticker": sym,
                    "name": sym.replace(".NS", ""),
                    "price": round(float(curr), 2),
                    "change_pct": pct,
                }
        except Exception:
            continue

    # Build sector results from fetched data
    sector_perf = {}
    for sector, tickers in SECTOR_TICKERS.items():
        stocks = [ticker_data[sym] for sym in tickers if sym in ticker_data]
        if stocks:
            avg = round(sum(s["change_pct"] for s in stocks) / len(stocks), 2)
            stocks.sort(key=lambda x: x["change_pct"], reverse=True)
            sector_perf[sector] = {"avg_change": avg, "stocks": stocks}

    return dict(
        sorted(sector_perf.items(), key=lambda x: x[1]["avg_change"], reverse=True)
    )


# ---------------------------------------------------------------------------
# GOLD TREND ANALYSIS — weekly & monthly context
# ---------------------------------------------------------------------------


def _gold_inr_series(gold_hist, fx_hist, premium=1.03):
    """Combine gold futures + FX into INR/gram series, handling timezone mismatches."""
    import pandas as pd

    g = gold_hist["Close"].copy()
    f = fx_hist["Close"].copy()
    g.index = g.index.tz_localize(None)
    f.index = f.index.tz_localize(None)
    df = pd.DataFrame({"gold": g, "fx": f}).ffill().dropna()
    if df.empty:
        return None
    return (df["gold"] * df["fx"]) / 31.1035 * premium


def analyze_gold_trend():
    """Analyze gold price trend over multiple timeframes."""
    try:
        gold = yf.Ticker("GC=F")
        usd_inr = yf.Ticker("USDINR=X")

        gold_hist = gold.history(period="3mo")
        fx_hist = usd_inr.history(period="3mo")

        if gold_hist.empty or fx_hist.empty:
            return None

        inr_per_gram = _gold_inr_series(gold_hist, fx_hist)
        if inr_per_gram is None or len(inr_per_gram) < 5:
            return None

        current = inr_per_gram.iloc[-1]

        # Weekly change (5 trading days)
        week_ago = (
            inr_per_gram.iloc[-6] if len(inr_per_gram) >= 6 else inr_per_gram.iloc[0]
        )
        weekly_change = round(((current - week_ago) / week_ago) * 100, 2)

        # Monthly change (~22 trading days)
        month_ago = (
            inr_per_gram.iloc[-23] if len(inr_per_gram) >= 23 else inr_per_gram.iloc[0]
        )
        monthly_change = round(((current - month_ago) / month_ago) * 100, 2)

        # 3-month high/low
        high_3m = round(inr_per_gram.max(), 2)
        low_3m = round(inr_per_gram.min(), 2)

        return {
            "weekly_change": weekly_change,
            "monthly_change": monthly_change,
            "high_3m": high_3m,
            "low_3m": low_3m,
        }
    except Exception:
        return None


def predict_gold_buy(use_news=True):
    """Analyze gold price data and predict if it's a good time to buy.

    Returns dict with:
      - signal: 'BUY', 'WAIT', or 'SELL'
      - confidence: 0-100
      - reasons: list of (factor, score, explanation) tuples
      - prediction: expected direction for next 5-7 days
      - current_price: current gold price INR/gram
    """
    try:
        gold = yf.Ticker("GC=F")
        usd_inr = yf.Ticker("USDINR=X")

        gold_hist = gold.history(period="6mo")
        fx_hist = usd_inr.history(period="6mo")

        if gold_hist.empty or fx_hist.empty:
            return None

        inr_per_gram = _gold_inr_series(gold_hist, fx_hist)
        if inr_per_gram is None or len(inr_per_gram) < 30:
            return None

        prices = inr_per_gram.values
        current = prices[-1]

        # --- Factor 1: RSI (14-day) ---
        rsi = compute_rsi(prices)
        rsi_score = 0
        rsi_reason = ""
        if rsi is not None:
            if rsi <= 25:
                rsi_score = 30
                rsi_reason = (
                    f"RSI is {rsi:.0f} — gold is deeply oversold, strong buying zone"
                )
            elif rsi <= 35:
                rsi_score = 20
                rsi_reason = f"RSI is {rsi:.0f} — oversold territory, good entry point"
            elif rsi <= 45:
                rsi_score = 8
                rsi_reason = (
                    f"RSI is {rsi:.0f} — leaning towards cheap, slight buy signal"
                )
            elif rsi <= 55:
                rsi_score = 0
                rsi_reason = f"RSI is {rsi:.0f} — perfectly neutral, no momentum edge"
            elif rsi <= 65:
                rsi_score = -8
                rsi_reason = f"RSI is {rsi:.0f} — leaning towards expensive"
            elif rsi <= 75:
                rsi_score = -20
                rsi_reason = f"RSI is {rsi:.0f} — getting overbought, wait for a dip"
            else:
                rsi_score = -30
                rsi_reason = f"RSI is {rsi:.0f} — heavily overbought, high risk of drop"

        # --- Factor 2: Price vs moving averages ---
        ma10 = np.mean(prices[-10:]) if len(prices) >= 10 else None
        ma20 = np.mean(prices[-20:]) if len(prices) >= 20 else None
        ma50 = np.mean(prices[-50:]) if len(prices) >= 50 else None
        ma_score = 0
        ma_reason = ""
        if ma20 and ma50:
            pct_from_ma20 = ((current - ma20) / ma20) * 100
            pct_from_ma50 = ((current - ma50) / ma50) * 100

            if current < ma20 and current < ma50:
                ma_score = 20
                ma_reason = f"Price is {abs(pct_from_ma20):.1f}% below 20-day and {abs(pct_from_ma50):.1f}% below 50-day avg — dip buying zone"
            elif current < ma20:
                ma_score = 10
                ma_reason = f"Price is {abs(pct_from_ma20):.1f}% below 20-day avg — short-term dip"
            elif current > ma20 and current > ma50 and ma20 > ma50:
                if pct_from_ma20 > 5:
                    ma_score = -15
                    ma_reason = f"Price is {pct_from_ma20:.1f}% above 20-day avg and in strong uptrend — stretched, wait for pullback"
                else:
                    ma_score = -8
                    ma_reason = (
                        f"Price is above both averages — uptrend, slightly expensive"
                    )
            elif ma10 and ma10 < ma20:
                ma_score = 8
                ma_reason = f"Short-term avg just crossed below medium-term — possible dip forming, could be an entry soon"
            else:
                ma_score = 0
                ma_reason = f"Price is near moving averages — no clear trend"

        # --- Factor 3: Position in 3-month range ---
        high_3m = prices[-66:].max() if len(prices) >= 66 else prices.max()
        low_3m = prices[-66:].min() if len(prices) >= 66 else prices.min()
        range_pct = (
            ((current - low_3m) / (high_3m - low_3m)) * 100 if high_3m != low_3m else 50
        )
        range_score = 0
        if range_pct <= 15:
            range_score = 25
            range_reason = f"Price is near the 3-month low (bottom {range_pct:.0f}%) — strong buying level"
        elif range_pct <= 30:
            range_score = 15
            range_reason = f"Price is in the lower third of 3-month range ({range_pct:.0f}%) — good value"
        elif range_pct <= 45:
            range_score = 5
            range_reason = (
                f"Price is in the lower-mid range ({range_pct:.0f}%) — slightly cheap"
            )
        elif range_pct <= 55:
            range_score = 0
            range_reason = (
                f"Price is mid-range ({range_pct:.0f}%) — fair value, no edge"
            )
        elif range_pct <= 70:
            range_score = -5
            range_reason = f"Price is in the upper-mid range ({range_pct:.0f}%) — slightly expensive"
        elif range_pct <= 85:
            range_score = -15
            range_reason = (
                f"Price is in the upper third ({range_pct:.0f}%) — expensive territory"
            )
        else:
            range_score = -25
            range_reason = f"Price is near 3-month high (top {100 - range_pct:.0f}%) — risky to buy now"

        # --- Factor 4: Recent momentum (5-day vs 20-day) ---
        change_5d = (
            ((current - prices[-6]) / prices[-6]) * 100 if len(prices) >= 6 else 0
        )
        change_20d = (
            ((current - prices[-21]) / prices[-21]) * 100 if len(prices) >= 21 else 0
        )
        momentum_score = 0
        if change_5d < -3 and change_20d < -5:
            momentum_score = 20
            momentum_reason = f"Gold fell {change_5d:.1f}% in 5 days, {change_20d:.1f}% in 20 days — sharp correction, strong bounce likely"
        elif change_5d < -2 and change_20d < -3:
            momentum_score = 12
            momentum_reason = f"Gold fell {change_5d:.1f}% in 5 days — decent pullback, potential entry"
        elif change_5d < -1:
            momentum_score = 5
            momentum_reason = f"Gold dipped {change_5d:.1f}% in 5 days — minor pullback"
        elif change_5d > 4:
            momentum_score = -20
            momentum_reason = f"Gold surged {change_5d:+.1f}% in 5 days — very overheated, pullback imminent"
        elif change_5d > 2:
            momentum_score = -12
            momentum_reason = (
                f"Gold rose {change_5d:+.1f}% in 5 days — overheated, wait for cooling"
            )
        elif change_5d > 1:
            momentum_score = -5
            momentum_reason = f"Gold rose {change_5d:+.1f}% in 5 days — mild uptrend, slightly expensive"
        else:
            # Stable — check if 20d trend gives direction
            if change_20d < -3:
                momentum_score = 8
                momentum_reason = f"Gold stable this week but down {change_20d:.1f}% over 20 days — broader dip, could be entry"
            elif change_20d > 5:
                momentum_score = -8
                momentum_reason = f"Gold stable this week but up {change_20d:+.1f}% over 20 days — extended rally"
            else:
                momentum_score = 0
                momentum_reason = f"Gold moved {change_5d:+.1f}% in 5 days, {change_20d:+.1f}% in 20 days — sideways, no edge"

        # --- Factor 5: Volatility (10-day std dev) ---
        vol_score = 0
        vol_reason = ""
        if len(prices) >= 11:
            daily_returns = np.diff(prices[-11:]) / prices[-11:-1] * 100
            volatility = np.std(daily_returns)
            avg_vol = (
                np.std(np.diff(prices[-60:]) / prices[-60:-1] * 100)
                if len(prices) >= 60
                else volatility
            )

            if volatility > avg_vol * 1.5:
                vol_score = -8
                vol_reason = f"Gold is very choppy right now (volatility {volatility:.2f}% vs avg {avg_vol:.2f}%) — risky entry, wait for calmer market"
            elif volatility > avg_vol * 1.2:
                vol_score = -3
                vol_reason = f"Slightly elevated volatility ({volatility:.2f}% vs avg {avg_vol:.2f}%) — somewhat risky"
            elif volatility < avg_vol * 0.7:
                vol_score = 5
                vol_reason = f"Gold is calm right now (volatility {volatility:.2f}% vs avg {avg_vol:.2f}%) — good time for a stable entry"
            else:
                vol_score = 0
                vol_reason = f"Normal volatility ({volatility:.2f}%) — no extra risk"

        # --- Factor 6: Trend consistency (last 10 days) ---
        trend_score = 0
        trend_reason = ""
        if len(prices) >= 11:
            last_10 = prices[-10:]
            up_days = sum(
                1 for i in range(1, len(last_10)) if last_10[i] > last_10[i - 1]
            )
            down_days = 10 - 1 - up_days
            if down_days >= 7:
                trend_score = 12
                trend_reason = f"{down_days}/9 recent days were down — sustained selling, could be near a bottom"
            elif down_days >= 6:
                trend_score = 6
                trend_reason = f"{down_days}/9 recent days were down — consistent weakness, possible entry forming"
            elif up_days >= 7:
                trend_score = -12
                trend_reason = f"{up_days}/9 recent days were up — sustained buying, may be overextended"
            elif up_days >= 6:
                trend_score = -6
                trend_reason = f"{up_days}/9 recent days were up — consistent strength, slightly expensive"
            else:
                trend_score = 0
                trend_reason = f"Mixed recent days ({up_days} up, {down_days} down) — no clear pattern"

        # --- Factor 7: News sentiment ---
        news_score = 0
        news_reason = "News not analyzed"
        if use_news:
            try:
                gold_news = fetch_news("Gold Price India", max_items=8)
                if gold_news:
                    bull = sum(1 for n in gold_news if n["sentiment"] == "bullish")
                    bear = sum(1 for n in gold_news if n["sentiment"] == "bearish")
                    total = len(gold_news)
                    if bear > bull and bear >= 4:
                        news_score = 12
                        news_reason = f"News is heavily negative ({bear}/{total} bearish) — fear creates buying opportunities"
                    elif bear > bull and bear >= 2:
                        news_score = 6
                        news_reason = f"News is leaning negative ({bear}/{total} bearish) — could mean prices dip further (buy opportunity)"
                    elif bull > bear and bull >= 4:
                        news_score = -8
                        news_reason = f"News is very positive ({bull}/{total} bullish) — gold rally may already be priced in"
                    elif bull > bear and bull >= 2:
                        news_score = -4
                        news_reason = f"News is leaning positive ({bull}/{total} bullish) — some upside likely priced in"
                    else:
                        news_score = 0
                        news_reason = f"News sentiment is mixed ({bull} positive, {bear} negative) — no clear direction from news"
            except Exception:
                news_reason = "Could not fetch gold news"

        # --- Factor 8: US Dollar Strength (inverse correlation with gold) ---
        dollar_score = 0
        dollar_reason = ""
        try:
            dxy = yf.Ticker("DX-Y.NYB")
            dxy_hist = dxy.history(period="1mo")
            if not dxy_hist.empty and len(dxy_hist) >= 5:
                dxy_prices = dxy_hist["Close"].values
                dxy_current = dxy_prices[-1]
                dxy_20d_ago = dxy_prices[0]
                dxy_change = ((dxy_current - dxy_20d_ago) / dxy_20d_ago) * 100
                if dxy_change > 3:
                    dollar_score = 15
                    dollar_reason = f"US Dollar strengthened {dxy_change:+.1f}% this month — gold tends to fall when dollar rises, creating a buy window"
                elif dxy_change > 1.5:
                    dollar_score = 8
                    dollar_reason = f"US Dollar is rising ({dxy_change:+.1f}%) — mild headwind for gold, but potential entry point"
                elif dxy_change < -3:
                    dollar_score = -12
                    dollar_reason = f"US Dollar weakened {dxy_change:+.1f}% — gold already benefiting, may be priced in"
                elif dxy_change < -1.5:
                    dollar_score = -5
                    dollar_reason = f"US Dollar dipping ({dxy_change:+.1f}%) — supportive for gold prices"
                else:
                    dollar_score = 0
                    dollar_reason = f"US Dollar stable ({dxy_change:+.1f}%) — no currency tailwind or headwind"
        except Exception:
            dollar_reason = "Could not fetch US Dollar data"

        # --- Factor 9: Gold-Silver Ratio (institutional signal) ---
        gsr_score = 0
        gsr_reason = ""
        try:
            silver_t = yf.Ticker("SI=F")
            sv_hist = silver_t.history(period="3mo")
            if not sv_hist.empty and not gold_hist.empty:
                gold_usd = gold_hist["Close"].iloc[-1]
                silver_usd = sv_hist["Close"].iloc[-1]
                if silver_usd > 0:
                    gsr = gold_usd / silver_usd
                    if gsr > 90:
                        gsr_score = 12
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (historically high >90) — gold is expensive relative to silver, but signals fear/uncertainty which supports gold"
                    elif gsr > 80:
                        gsr_score = 5
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (elevated) — gold has safe-haven premium"
                    elif gsr < 60:
                        gsr_score = -8
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (low) — gold is cheap relative to silver, but risk appetite is high"
                    elif gsr < 70:
                        gsr_score = -3
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (normal-low) — balanced market"
                    else:
                        gsr_score = 0
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (normal range) — no relative value signal"
        except Exception:
            gsr_reason = "Could not compute Gold-Silver ratio"

        # --- Factor 10: Indian Seasonal Demand ---
        month = datetime.now().month
        seasonal_score = 0
        if month in (10, 11):  # Dhanteras, Diwali, wedding season start
            seasonal_score = 10
            seasonal_reason = "Peak gold buying season in India (Diwali/Dhanteras/weddings) — demand typically pushes prices up"
        elif month in (1, 2):  # Wedding season continues
            seasonal_score = 8
            seasonal_reason = "Indian wedding season — strong domestic demand for gold"
        elif month in (4, 5):  # Akshaya Tritiya
            seasonal_score = 6
            seasonal_reason = (
                "Akshaya Tritiya season — auspicious gold buying period in India"
            )
        elif month in (7, 8):  # Low demand
            seasonal_score = -5
            seasonal_reason = (
                "Off-season for gold in India — demand typically lower, may get cheaper"
            )
        elif month in (6, 9):  # Pre-season
            seasonal_score = 3
            seasonal_reason = "Approaching festive season — smart money starts accumulating gold around now"
        else:
            seasonal_score = 0
            seasonal_reason = (
                f"No strong seasonal pattern this month — neutral demand period"
            )

        # --- Factor 11: Market Fear / VIX ---
        vix_score = 0
        vix_reason = ""
        try:
            vix = yf.Ticker("^VIX")
            vix_hist = vix.history(period="5d")
            if not vix_hist.empty:
                vix_current = vix_hist["Close"].iloc[-1]
                if vix_current > 30:
                    vix_score = 15
                    vix_reason = f"VIX is {vix_current:.0f} (high fear) — investors flee to gold as safe haven, strongly bullish for gold"
                elif vix_current > 25:
                    vix_score = 8
                    vix_reason = f"VIX is {vix_current:.0f} (elevated) — rising fear supports gold prices"
                elif vix_current < 15:
                    vix_score = -8
                    vix_reason = f"VIX is {vix_current:.0f} (very calm) — no fear in markets, less demand for gold as safe haven"
                elif vix_current < 20:
                    vix_score = -3
                    vix_reason = f"VIX is {vix_current:.0f} (normal) — steady environment, neutral for gold"
                else:
                    vix_score = 0
                    vix_reason = (
                        f"VIX is {vix_current:.0f} (moderate) — no strong fear signal"
                    )
        except Exception:
            vix_reason = "Could not fetch VIX data"

        # --- Factor 12: US Treasury Yield / Real Rate Proxy ---
        yield_score = 0
        yield_reason = ""
        try:
            tnx = yf.Ticker("^TNX")  # 10-year US Treasury
            tnx_hist = tnx.history(period="1mo")
            if not tnx_hist.empty and len(tnx_hist) >= 5:
                yield_current = tnx_hist["Close"].iloc[-1]
                yield_prev = tnx_hist["Close"].iloc[0]
                yield_change = yield_current - yield_prev
                if yield_change > 0.3:
                    yield_score = 12
                    yield_reason = f"US 10Y yield rose {yield_change:+.2f}% to {yield_current:.2f}% — rising rates pressure gold, creating buy opportunity at lower prices"
                elif yield_change > 0.1:
                    yield_score = 5
                    yield_reason = f"US 10Y yield edging up ({yield_current:.2f}%) — mild headwind for gold"
                elif yield_change < -0.3:
                    yield_score = -10
                    yield_reason = f"US 10Y yield fell {yield_change:+.2f}% to {yield_current:.2f}% — falling rates are bullish for gold (already priced in)"
                elif yield_change < -0.1:
                    yield_score = -4
                    yield_reason = f"US 10Y yield drifting lower ({yield_current:.2f}%) — mildly supportive for gold"
                else:
                    yield_score = 0
                    yield_reason = f"US 10Y yield stable at {yield_current:.2f}% — no rate-driven pressure"
        except Exception:
            yield_reason = "Could not fetch Treasury yield data"

        # --- Combine scores ---
        reasons = []
        if rsi is not None:
            reasons.append(("Momentum (RSI)", rsi_score, rsi_reason))
        if ma_reason:
            reasons.append(("Moving Averages", ma_score, ma_reason))
        reasons.append(("3M Range Position", range_score, range_reason))
        reasons.append(("Price Momentum", momentum_score, momentum_reason))
        if vol_reason:
            reasons.append(("Volatility", vol_score, vol_reason))
        if trend_reason:
            reasons.append(("Trend Consistency", trend_score, trend_reason))
        reasons.append(("News Sentiment", news_score, news_reason))
        if dollar_reason:
            reasons.append(("US Dollar Strength", dollar_score, dollar_reason))
        if gsr_reason:
            reasons.append(("Gold-Silver Ratio", gsr_score, gsr_reason))
        reasons.append(("Seasonal Demand (India)", seasonal_score, seasonal_reason))
        if vix_reason:
            reasons.append(("Market Fear (VIX)", vix_score, vix_reason))
        if yield_reason:
            reasons.append(("US Treasury Yield", yield_score, yield_reason))

        # Apply learned weights from past prediction mistakes
        learned_weights = _load_learned_weights("gold")
        total_score = _apply_learned_weights(reasons, learned_weights)

        # Manipulation detection on gold futures
        gold_volumes = (
            gold_hist["Volume"].values if "Volume" in gold_hist.columns else None
        )
        manip = {
            "is_suspicious": False,
            "score_dampening": 1.0,
            "flags": [],
            "severity": "none",
        }
        if gold_volumes is not None and len(gold_volumes) >= 30:
            min_len = min(len(prices), len(gold_volumes))
            manip = detect_manipulation(prices[-min_len:], gold_volumes[-min_len:])
            if manip["is_suspicious"]:
                total_score = round(total_score * manip["score_dampening"])
                manip_summary = "; ".join(desc for _, desc in manip["flags"][:2])
                reasons.append(
                    (
                        "Manipulation Guard",
                        0,
                        f"⚠️ Suspicious activity detected ({manip['severity']}): {manip_summary}. Prediction dampened.",
                    )
                )

        # --- Signal determination ---
        if total_score >= 25:
            signal = "BUY"
        elif total_score >= 10:
            signal = "LEAN BUY"
        elif total_score <= -25:
            signal = "SELL"
        elif total_score <= -10:
            signal = "LEAN SELL"
        else:
            signal = "WAIT"

        # --- Confidence: how many factors agree on the direction ---
        positive_factors = sum(1 for _, s, _ in reasons if s > 0)
        negative_factors = sum(1 for _, s, _ in reasons if s < 0)
        neutral_factors = sum(1 for _, s, _ in reasons if s == 0)
        total_factors = len(reasons)

        if signal in ("BUY", "LEAN BUY"):
            agreement = positive_factors / total_factors
            score_strength = min(abs(total_score) / 50, 1.0)
        elif signal in ("SELL", "LEAN SELL"):
            agreement = negative_factors / total_factors
            score_strength = min(abs(total_score) / 50, 1.0)
        else:
            # WAIT — confidence is high when factors are genuinely neutral/mixed
            agreement = (
                neutral_factors + min(positive_factors, negative_factors)
            ) / total_factors
            score_strength = 1.0 - min(abs(total_score) / 30, 1.0)

        confidence = max(
            15, min(95, round((agreement * 0.5 + score_strength * 0.5) * 100))
        )

        # --- Prediction text ---
        if signal == "BUY":
            if change_5d < -2:
                prediction = f"Gold dropped {change_5d:.1f}% recently — expect a bounce in the next 5-7 days. Good time to buy."
            else:
                prediction = "Multiple factors favour buying — gold is likely to hold or rise this week."
        elif signal == "LEAN BUY":
            prediction = "Slightly favourable conditions — consider buying a small amount now, and more if it dips."
        elif signal == "SELL":
            if change_5d > 3:
                prediction = f"Gold surged {change_5d:+.1f}% recently — expect a pullback in the next 5-7 days."
            else:
                prediction = "Most indicators suggest gold is expensive — wait for a correction before buying."
        elif signal == "LEAN SELL":
            prediction = "Conditions lean slightly against buying — wait a few days for a better price."
        else:
            if abs(total_score) <= 3:
                prediction = "All factors are neutral — no edge either way. Watch for a clear signal before acting."
            else:
                prediction = "Mixed signals — some say buy, some say wait. Hold off for now and check again in a few days."

        # --- Risk assessment ---
        vol_pct = 0
        if len(prices) >= 11:
            dr = np.diff(prices[-11:]) / prices[-11:-1] * 100
            vol_pct = float(np.std(dr))
        if vol_pct > 2.5 or (rsi is not None and (rsi < 25 or rsi > 75)):
            risk_level = "Very High"
            risk_warning = (
                f"⚠️ Very high volatility ({vol_pct:.1f}%) — use small position size"
            )
        elif vol_pct > 1.5 or (rsi is not None and (rsi < 30 or rsi > 70)):
            risk_level = "High"
            risk_warning = f"⚠️ High volatility ({vol_pct:.1f}%) — set a stop-loss"
        elif vol_pct > 0.8:
            risk_level = "Moderate"
            risk_warning = f"Moderate volatility ({vol_pct:.1f}%) — manageable risk"
        else:
            risk_level = "Low"
            risk_warning = ""

        return {
            "signal": signal,
            "confidence": confidence,
            "total_score": total_score,
            "reasons": reasons,
            "prediction": prediction,
            "current_price": round(current, 2),
            "rsi": rsi,
            "range_pct": round(range_pct, 1),
            "change_5d": round(change_5d, 2),
            "change_20d": round(change_20d, 2),
            "risk_level": risk_level,
            "risk_warning": risk_warning,
            "manipulation": manip if manip["is_suspicious"] else None,
        }
    except Exception:
        return None


def backtest_metal_prediction(metal="gold", lookback_months=6, hold_days=7):
    """Backtest the metal prediction engine on historical data.

    Simulates predictions at multiple past dates using 7-factor scoring
    (excludes live-only factors: news, VIX, DXY, yields) to see if
    BUY/SELL signals would have been profitable.

    Args:
        metal: 'gold' or 'silver'
        lookback_months: how many months of history to test
        hold_days: days to hold after signal before checking outcome

    Returns dict with:
        - results: list of per-date outcomes
        - summary: accuracy stats
    """
    import pandas as pd

    ticker = "GC=F" if metal == "gold" else "SI=F"
    premium = GOLD_PREMIUM if metal == "gold" else SILVER_PREMIUM

    try:
        metal_t = yf.Ticker(ticker)
        fx_t = yf.Ticker("USDINR=X")
        period = f"{lookback_months + 3}mo"  # extra buffer for MAs
        metal_hist = metal_t.history(period=period)
        fx_hist = fx_t.history(period=period)

        if metal_hist.empty or fx_hist.empty:
            return None

        inr_series = _gold_inr_series(metal_hist, fx_hist, premium=premium)
        if inr_series is None or len(inr_series) < 80:
            return None

        prices = inr_series.values
        dates = inr_series.index

        # Start testing from day 66 (need 66 days for 3M range)
        # Stop hold_days before end so we can check outcome
        start_idx = max(66, 50)
        end_idx = len(prices) - hold_days - 1

        backtest_results = []

        for i in range(start_idx, end_idx, 5):  # test every 5 trading days
            test_prices = prices[: i + 1]
            current = test_prices[-1]
            future_price = prices[i + hold_days]
            actual_change_pct = ((future_price - current) / current) * 100

            # --- Compute 7 core factors (no live API calls) ---
            rsi = compute_rsi(test_prices)
            rsi_score = 0
            if rsi is not None:
                if rsi <= 25:
                    rsi_score = 30
                elif rsi <= 35:
                    rsi_score = 20
                elif rsi <= 45:
                    rsi_score = 8
                elif rsi <= 55:
                    rsi_score = 0
                elif rsi <= 65:
                    rsi_score = -8
                elif rsi <= 75:
                    rsi_score = -20
                else:
                    rsi_score = -30

            # MAs
            ma20 = np.mean(test_prices[-20:]) if len(test_prices) >= 20 else None
            ma50 = np.mean(test_prices[-50:]) if len(test_prices) >= 50 else None
            ma_score = 0
            if ma20 and ma50:
                if current < ma20 and current < ma50:
                    ma_score = 20
                elif current < ma20:
                    ma_score = 10
                elif current > ma20 and current > ma50:
                    pct_from_ma20 = ((current - ma20) / ma20) * 100
                    ma_score = -15 if pct_from_ma20 > 5 else -8
                else:
                    ma_score = 0

            # 3M range
            high_3m = (
                test_prices[-66:].max() if len(test_prices) >= 66 else test_prices.max()
            )
            low_3m = (
                test_prices[-66:].min() if len(test_prices) >= 66 else test_prices.min()
            )
            range_pct = (
                ((current - low_3m) / (high_3m - low_3m)) * 100
                if high_3m != low_3m
                else 50
            )
            if range_pct <= 15:
                range_score = 25
            elif range_pct <= 30:
                range_score = 15
            elif range_pct <= 45:
                range_score = 5
            elif range_pct <= 55:
                range_score = 0
            elif range_pct <= 70:
                range_score = -5
            elif range_pct <= 85:
                range_score = -15
            else:
                range_score = -25

            # Momentum
            change_5d = (
                ((current - test_prices[-6]) / test_prices[-6]) * 100
                if len(test_prices) >= 6
                else 0
            )
            if change_5d < -3:
                momentum_score = 20
            elif change_5d < -2:
                momentum_score = 12
            elif change_5d < -1:
                momentum_score = 5
            elif change_5d > 4:
                momentum_score = -20
            elif change_5d > 2:
                momentum_score = -12
            elif change_5d > 1:
                momentum_score = -5
            else:
                momentum_score = 0

            # Volatility
            vol_score = 0
            if len(test_prices) >= 11:
                daily_ret = np.diff(test_prices[-11:]) / test_prices[-11:-1] * 100
                vol = np.std(daily_ret)
                avg_vol = (
                    np.std(np.diff(test_prices[-60:]) / test_prices[-60:-1] * 100)
                    if len(test_prices) >= 60
                    else vol
                )
                if vol > avg_vol * 1.5:
                    vol_score = -8
                elif vol < avg_vol * 0.7:
                    vol_score = 5

            # Trend consistency
            trend_score = 0
            if len(test_prices) >= 11:
                last_10 = test_prices[-10:]
                up_days = sum(
                    1 for j in range(1, len(last_10)) if last_10[j] > last_10[j - 1]
                )
                down_days = 9 - up_days
                if down_days >= 7:
                    trend_score = 12
                elif down_days >= 6:
                    trend_score = 6
                elif up_days >= 7:
                    trend_score = -12
                elif up_days >= 6:
                    trend_score = -6

            total_score = (
                rsi_score
                + ma_score
                + range_score
                + momentum_score
                + vol_score
                + trend_score
            )

            if total_score >= 25:
                signal = "BUY"
            elif total_score >= 10:
                signal = "LEAN BUY"
            elif total_score <= -25:
                signal = "SELL"
            elif total_score <= -10:
                signal = "LEAN SELL"
            else:
                signal = "WAIT"

            # Check if signal was correct
            if signal in ("BUY", "LEAN BUY"):
                was_correct = actual_change_pct > 0
            elif signal in ("SELL", "LEAN SELL"):
                was_correct = actual_change_pct <= 0
            else:
                was_correct = abs(actual_change_pct) < 2  # WAIT = sideways

            backtest_results.append(
                {
                    "date": (
                        dates[i].strftime("%Y-%m-%d")
                        if hasattr(dates[i], "strftime")
                        else str(dates[i])[:10]
                    ),
                    "signal": signal,
                    "score": total_score,
                    "price": round(current, 2),
                    "future_price": round(future_price, 2),
                    "actual_change_pct": round(actual_change_pct, 2),
                    "was_correct": was_correct,
                    "rsi": round(rsi, 1) if rsi else None,
                }
            )

        if not backtest_results:
            return None

        total = len(backtest_results)
        correct = sum(1 for r in backtest_results if r["was_correct"])
        buy_signals = [
            r for r in backtest_results if r["signal"] in ("BUY", "LEAN BUY")
        ]
        sell_signals = [
            r for r in backtest_results if r["signal"] in ("SELL", "LEAN SELL")
        ]
        buy_correct = (
            sum(1 for r in buy_signals if r["was_correct"]) if buy_signals else 0
        )
        sell_correct = (
            sum(1 for r in sell_signals if r["was_correct"]) if sell_signals else 0
        )

        # Calculate hypothetical return if you followed BUY signals
        buy_returns = [r["actual_change_pct"] for r in buy_signals]
        avg_buy_return = round(np.mean(buy_returns), 2) if buy_returns else 0

        return {
            "metal": metal,
            "period": f"{lookback_months} months",
            "hold_days": hold_days,
            "total_signals": total,
            "results": backtest_results,
            "summary": {
                "overall_accuracy": round((correct / total) * 100) if total else 0,
                "total_tested": total,
                "correct": correct,
                "buy_signals": len(buy_signals),
                "buy_accuracy": (
                    round((buy_correct / len(buy_signals)) * 100) if buy_signals else 0
                ),
                "sell_signals": len(sell_signals),
                "sell_accuracy": (
                    round((sell_correct / len(sell_signals)) * 100)
                    if sell_signals
                    else 0
                ),
                "avg_buy_return": avg_buy_return,
            },
        }
    except Exception:
        return None


def save_gold_prediction(prediction):
    """Log a gold prediction to DB or data/gold_predictions.json for tracking accuracy."""
    import os

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "signal": prediction["signal"],
        "confidence": prediction["confidence"],
        "price_at_prediction": prediction["current_price"],
        "total_score": prediction["total_score"],
        "prediction_text": prediction["prediction"],
        "factor_scores": [
            {"name": name, "score": score, "reason": reason}
            for name, score, reason in prediction["reasons"]
        ],
        "verified": False,
        "actual_price_after": None,
        "was_correct": None,
    }

    try:
        import db as _db

        if _db.is_db_available():
            return _db.save_prediction("gold_predictions", entry, unique_keys=["date"])
    except ImportError:
        pass

    log_path = os.path.join(os.path.dirname(__file__), "data", "gold_predictions.json")

    # Load existing predictions
    predictions = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                predictions = json.load(f)
        except (json.JSONDecodeError, OSError):
            predictions = []

    # Don't duplicate same-day predictions
    today = entry["date"]
    predictions = [p for p in predictions if p["date"] != today]
    predictions.append(entry)

    tmp_path = log_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(predictions, f, indent=2)
    os.replace(tmp_path, log_path)

    return entry


def detect_manipulation(closes, volumes, window=20):
    """Detect signs of market manipulation that could distort predictions.

    Checks for: volume anomalies, pump-and-dump patterns, whipsaw reversals,
    wash-trading signals, and price-volume divergence.

    Args:
        closes: numpy array of closing prices (at least 30 values)
        volumes: numpy array of volumes (same length as closes)
        window: lookback period for averages (default 20)

    Returns dict:
        - is_suspicious: bool — True if manipulation signals found
        - score_dampening: float 0.0-1.0 — multiply total_score by this
        - flags: list of (flag_name, description) tuples
        - severity: 'none' | 'low' | 'moderate' | 'high'
    """
    import numpy as np

    flags = []

    if len(closes) < window + 10 or len(volumes) < window + 10:
        return {
            "is_suspicious": False,
            "score_dampening": 1.0,
            "flags": [],
            "severity": "none",
        }

    recent_closes = closes[-window:]
    recent_volumes = volumes[-window:]
    avg_volume = np.mean(volumes[-60:]) if len(volumes) >= 60 else np.mean(volumes)
    avg_volume = max(avg_volume, 1)  # prevent division by zero

    # --- 1. Volume spike without fundamentals ---
    # Sudden volume >4x average in last 3 days
    for i in range(-1, -4, -1):
        if volumes[i] > avg_volume * 4:
            pct_move = abs((closes[i] - closes[i - 1]) / closes[i - 1] * 100)
            if pct_move < 2:
                # Huge volume but small price move = wash trading
                flags.append(
                    (
                        "wash_trading",
                        f"Volume {volumes[i]/avg_volume:.1f}x average but price moved only {pct_move:.1f}% — possible wash trading",
                    )
                )
            else:
                flags.append(
                    (
                        "volume_spike",
                        f"Abnormal volume spike ({volumes[i]/avg_volume:.1f}x average) — could be institutional manipulation",
                    )
                )

    # --- 2. Pump-and-dump pattern ---
    # 3+ consecutive up-days with rising volume, then a sharp reversal
    daily_returns = np.diff(recent_closes) / recent_closes[:-1] * 100
    for i in range(len(daily_returns) - 4, len(daily_returns) - 1):
        if i < 2:
            continue
        # Check 3 consecutive up-days
        if (
            daily_returns[i - 2] > 0
            and daily_returns[i - 1] > 0
            and daily_returns[i] > 0
        ):
            vol_rising = (
                recent_volumes[i] > recent_volumes[i - 1]
                and recent_volumes[i - 1] > recent_volumes[i - 2]
            )
            # Then a reversal
            if i + 1 < len(daily_returns) and daily_returns[i + 1] < -2:
                if vol_rising:
                    flags.append(
                        (
                            "pump_dump",
                            "3+ up-days with rising volume followed by sharp drop — classic pump-and-dump pattern",
                        )
                    )

    # --- 3. Whipsaw detection ---
    # Rapid direction changes (>2% moves alternating direction) in last 5 days
    whipsaw_count = 0
    for i in range(-5, -1):
        if abs(daily_returns[i]) > 2 and i + 1 < len(daily_returns):
            if (daily_returns[i] > 0) != (daily_returns[i + 1] > 0) and abs(
                daily_returns[i + 1]
            ) > 2:
                whipsaw_count += 1
    if whipsaw_count >= 2:
        flags.append(
            (
                "whipsaw",
                f"{whipsaw_count} violent reversals in 5 days — erratic movement suggests manipulation or stop-loss hunting",
            )
        )

    # --- 4. Price-volume divergence ---
    # Price making new highs/lows on declining volume = weak/artificial move
    recent_high = np.max(closes[-5:])
    month_high = np.max(closes[-window:])
    if recent_high >= month_high * 0.99:
        recent_avg_vol = np.mean(volumes[-5:])
        prior_avg_vol = np.mean(volumes[-window:-5]) if len(volumes) > 5 else avg_volume
        if prior_avg_vol > 0 and recent_avg_vol < prior_avg_vol * 0.5:
            flags.append(
                (
                    "divergence_high",
                    "Price near highs but volume is drying up — rally may be artificial, not supported by real buying",
                )
            )
    recent_low = np.min(closes[-5:])
    month_low = np.min(closes[-window:])
    if recent_low <= month_low * 1.01:
        recent_avg_vol = np.mean(volumes[-5:])
        prior_avg_vol = np.mean(volumes[-window:-5]) if len(volumes) > 5 else avg_volume
        if prior_avg_vol > 0 and recent_avg_vol < prior_avg_vol * 0.5:
            flags.append(
                (
                    "divergence_low",
                    "Price near lows but volume is drying up — selloff may be artificial, not real selling pressure",
                )
            )

    # --- 5. Abnormal intraday range ---
    # If available, check if high-low range is extreme vs close-to-close move
    # (approximation using consecutive close differences)
    last_5_moves = [abs(daily_returns[i]) for i in range(-5, 0)]
    avg_move = np.mean(last_5_moves) if last_5_moves else 0
    long_avg_move = (
        np.mean([abs(r) for r in daily_returns[-20:]])
        if len(daily_returns) >= 20
        else avg_move
    )
    if long_avg_move > 0 and avg_move > long_avg_move * 3:
        flags.append(
            (
                "extreme_volatility",
                f"Recent daily moves ({avg_move:.1f}%) are {avg_move/long_avg_move:.1f}x the norm — unusual activity",
            )
        )

    # --- Determine severity and dampening ---
    severity_scores = {
        "pump_dump": 3,
        "wash_trading": 2,
        "whipsaw": 2,
        "volume_spike": 1,
        "divergence_high": 1,
        "divergence_low": 1,
        "extreme_volatility": 1,
    }
    total_severity = sum(severity_scores.get(f[0], 1) for f in flags)

    if total_severity >= 5:
        severity = "high"
        score_dampening = 0.3
    elif total_severity >= 3:
        severity = "moderate"
        score_dampening = 0.5
    elif total_severity >= 1:
        severity = "low"
        score_dampening = 0.75
    else:
        severity = "none"
        score_dampening = 1.0

    return {
        "is_suspicious": len(flags) > 0,
        "score_dampening": score_dampening,
        "flags": flags,
        "severity": severity,
    }


def _load_learned_weights(asset):
    """Load suggested_weights from past prediction analysis for an asset.

    Args:
        asset: 'gold', 'silver', or a ticker symbol like 'TCS.NS' (for stocks)

    Returns dict of {factor_name: weight_multiplier} or empty dict if no data.
    """
    import os

    if asset in ("gold", "silver"):
        log_path = os.path.join(
            os.path.dirname(__file__), "data", f"{asset}_predictions.json"
        )
    else:
        log_path = os.path.join(
            os.path.dirname(__file__), "data", "stock_predictions.json"
        )

    if not os.path.exists(log_path):
        return {}

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    # For stocks, filter to this specific ticker
    if asset not in ("gold", "silver"):
        predictions = [p for p in predictions if p.get("ticker") == asset]

    analysis = _analyze_prediction_mistakes(predictions)
    if analysis and analysis.get("suggested_weights"):
        return analysis["suggested_weights"]
    return {}


def _apply_learned_weights(reasons, weights):
    """Apply learned weight multipliers to factor scores.

    Args:
        reasons: list of (name, score, reason) tuples
        weights: dict of {factor_name: multiplier}

    Returns weighted total score (int).
    """
    if not weights:
        return sum(s for _, s, _ in reasons)
    return round(sum(s * weights.get(name, 1.0) for name, s, _ in reasons))


def _analyze_prediction_mistakes(predictions):
    """Analyze past wrong predictions to find which factors consistently fail.

    Returns dict:
      - factor_accuracy: {factor_name: {correct: N, wrong: N, accuracy: %}}
      - worst_factors: list of factor names that are most inaccurate
      - learnings: list of plain-language lessons learned
      - suggested_weights: {factor_name: weight_multiplier} — factors to trust less/more
    """
    verified = [p for p in predictions if p.get("verified") and p.get("factor_scores")]
    if not verified:
        return None

    # Track per-factor accuracy
    factor_stats = {}
    for p in verified:
        was_correct = p.get("was_correct", False)
        actual_change = p.get("actual_change_pct", 0)

        for f in p["factor_scores"]:
            name = f["name"]
            score = f["score"]
            if name not in factor_stats:
                factor_stats[name] = {
                    "correct": 0,
                    "wrong": 0,
                    "total": 0,
                    "scores_when_wrong": [],
                }

            factor_stats[name]["total"] += 1

            # A factor is "correct" if its direction matched the actual outcome
            factor_said_buy = score > 0
            factor_said_sell = score < 0
            actual_up = actual_change > 0
            actual_down = actual_change < 0

            if factor_said_buy and actual_up:
                factor_stats[name]["correct"] += 1
            elif factor_said_sell and actual_down:
                factor_stats[name]["correct"] += 1
            elif score == 0:
                # Neutral factor — correct if price didn't move much
                if abs(actual_change) < 2:
                    factor_stats[name]["correct"] += 1
                else:
                    factor_stats[name]["wrong"] += 1
                    factor_stats[name]["scores_when_wrong"].append(score)
            else:
                factor_stats[name]["wrong"] += 1
                factor_stats[name]["scores_when_wrong"].append(score)

    # Compute accuracy per factor
    factor_accuracy = {}
    for name, stats in factor_stats.items():
        total = stats["total"]
        if total == 0:
            continue
        acc = round((stats["correct"] / total) * 100)
        factor_accuracy[name] = {
            "correct": stats["correct"],
            "wrong": stats["wrong"],
            "total": total,
            "accuracy": acc,
        }

    # Find worst-performing factors
    worst_factors = sorted(
        [f for f, d in factor_accuracy.items() if d["total"] >= 2],
        key=lambda f: factor_accuracy[f]["accuracy"],
    )[:3]

    # Generate learnings
    learnings = []
    suggested_weights = {}

    for name, data in factor_accuracy.items():
        if data["total"] < 2:
            suggested_weights[name] = 1.0
            continue

        acc = data["accuracy"]
        if acc >= 70:
            suggested_weights[name] = 1.2  # Trust more
            learnings.append(
                f"✅ **{name}** has been reliable ({acc}% accurate over {data['total']} predictions) — trusting it more."
            )
        elif acc >= 50:
            suggested_weights[name] = 1.0  # Keep as-is
        elif acc >= 30:
            suggested_weights[name] = 0.7  # Trust less
            learnings.append(
                f"⚠️ **{name}** has been unreliable ({acc}% accurate over {data['total']} predictions) — reducing its weight."
            )
        else:
            suggested_weights[name] = 0.5  # Trust much less
            learnings.append(
                f"🔴 **{name}** has been mostly wrong ({acc}% accurate over {data['total']} predictions) — severely reducing its influence."
            )

    # Analyze overall pattern of wrong predictions
    wrong_preds = [p for p in verified if not p.get("was_correct")]
    if wrong_preds:
        # Check if we're biased towards buy or sell
        wrong_buy = sum(1 for p in wrong_preds if p["signal"] in ("BUY", "LEAN BUY"))
        wrong_sell = sum(1 for p in wrong_preds if p["signal"] in ("SELL", "LEAN SELL"))
        if wrong_buy > wrong_sell + 2:
            learnings.append(
                f"📊 **Bias detected**: I called BUY/LEAN BUY incorrectly {wrong_buy} times vs SELL {wrong_sell} times — I may be too optimistic."
            )
        elif wrong_sell > wrong_buy + 2:
            learnings.append(
                f"📊 **Bias detected**: I called SELL/LEAN SELL incorrectly {wrong_sell} times vs BUY {wrong_buy} times — I may be too pessimistic."
            )

    return {
        "factor_accuracy": factor_accuracy,
        "worst_factors": worst_factors,
        "learnings": learnings,
        "suggested_weights": suggested_weights,
        "total_verified": len(verified),
        "total_correct": sum(1 for p in verified if p.get("was_correct")),
    }


def get_prediction_learnings(asset="gold"):
    """Get the self-learning analysis for a prediction model.

    Args:
        asset: 'gold' or 'silver'

    Returns the mistake analysis or None if not enough data.
    """
    import os

    log_path = os.path.join(
        os.path.dirname(__file__), "data", f"{asset}_predictions.json"
    )
    if not os.path.exists(log_path):
        return None

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    return _analyze_prediction_mistakes(predictions)


def verify_gold_predictions():
    """Check past predictions against actual prices. Returns list of verified predictions."""
    import os

    log_path = os.path.join(os.path.dirname(__file__), "data", "gold_predictions.json")
    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    # Get current gold price for verification
    try:
        gold = yf.Ticker("GC=F")
        usd_inr = yf.Ticker("USDINR=X")
        gold_hist = gold.history(period="1mo")
        fx_hist = usd_inr.history(period="1mo")
        if gold_hist.empty or fx_hist.empty:
            return predictions
        common = gold_hist.index.intersection(fx_hist.index)
        gold_c = gold_hist.loc[common, "Close"]
        fx_c = fx_hist.loc[common, "Close"]
        inr = (gold_c * fx_c) / 31.1035 * 1.03
        current_price = round(inr.iloc[-1], 2) if len(inr) > 0 else None
    except Exception:
        return predictions

    if current_price is None:
        return predictions

    updated = False
    today = datetime.now()
    for p in predictions:
        if p["verified"]:
            continue
        pred_date = datetime.strptime(p["date"], "%Y-%m-%d")
        days_since = (today - pred_date).days
        if days_since < 5:
            continue  # too early to verify

        p["actual_price_after"] = current_price
        p["verified"] = True
        price_change_pct = (
            (current_price - p["price_at_prediction"]) / p["price_at_prediction"]
        ) * 100

        if p["signal"] == "BUY":
            p["was_correct"] = price_change_pct > 0  # price went up = correct
        elif p["signal"] == "SELL":
            p["was_correct"] = price_change_pct < 0  # price went down = correct
        else:  # WAIT
            p["was_correct"] = abs(price_change_pct) < 2  # stayed flat = correct

        p["actual_change_pct"] = round(price_change_pct, 2)
        updated = True

    if updated:
        with open(log_path, "w") as f:
            json.dump(predictions, f, indent=2)

    return predictions


# ---------------------------------------------------------------------------
# INDIVIDUAL STOCK BUY/SELL PREDICTION — detailed multi-factor analysis
# ---------------------------------------------------------------------------


def predict_stock_buy(ticker_symbol, company_name="", use_news=True):
    """Analyze a stock and predict if it's a good time to buy/sell.

    Uses 11 factors: RSI, Moving Averages, 52W Range, Momentum, Volume,
    PE Valuation, Trend Consistency, Enhanced News (category-weighted),
    Market Sentiment (VIX + Nifty), Company Fundamentals (earnings/revenue
    growth, ROE, debt, margins, dividends).

    Returns dict similar to predict_gold_buy().
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 30:
            return None

        closes = hist["Close"].values
        volumes = hist["Volume"].values
        current = closes[-1]
        info = ticker.info or {}
        name = company_name or ticker_symbol.replace(".NS", "")

        # --- Factor 1: RSI (14-day) ---
        rsi = compute_rsi(closes)
        rsi_score = 0
        rsi_reason = ""
        if rsi is not None:
            if rsi <= 25:
                rsi_score = 30
                rsi_reason = f"RSI is {rsi:.0f} — deeply oversold, strong buying zone"
            elif rsi <= 35:
                rsi_score = 20
                rsi_reason = f"RSI is {rsi:.0f} — oversold territory, good entry point"
            elif rsi <= 45:
                rsi_score = 8
                rsi_reason = f"RSI is {rsi:.0f} — leaning cheap"
            elif rsi <= 55:
                rsi_score = 0
                rsi_reason = f"RSI is {rsi:.0f} — neutral, no momentum edge"
            elif rsi <= 65:
                rsi_score = -8
                rsi_reason = f"RSI is {rsi:.0f} — leaning expensive"
            elif rsi <= 75:
                rsi_score = -20
                rsi_reason = f"RSI is {rsi:.0f} — overbought, wait for a dip"
            else:
                rsi_score = -30
                rsi_reason = f"RSI is {rsi:.0f} — heavily overbought, high risk of drop"

        # --- Factor 2: Price vs Moving Averages ---
        sma20 = np.mean(closes[-20:]) if len(closes) >= 20 else None
        sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else None
        sma200 = np.mean(closes[-200:]) if len(closes) >= 200 else None
        ma_score = 0
        ma_reason = ""
        if sma20 and sma50:
            pct_from_20 = ((current - sma20) / sma20) * 100
            if sma200:
                if current < sma20 and current < sma50 and current < sma200:
                    ma_score = 25
                    ma_reason = f"Price is below all key moving averages — deep value zone if fundamentals are intact"
                elif current < sma20 and current < sma50:
                    ma_score = 15
                    ma_reason = f"Price {abs(pct_from_20):.1f}% below 20-day and below 50-day avg — dip buying zone"
                elif current > sma20 and current > sma50 and sma20 > sma50:
                    if pct_from_20 > 8:
                        ma_score = -15
                        ma_reason = f"Price {pct_from_20:.1f}% above 20-day avg in strong uptrend — stretched, wait for pullback"
                    else:
                        ma_score = -5
                        ma_reason = (
                            "Price above all averages in uptrend — slightly expensive"
                        )
                elif sma50 < sma200:
                    ma_score = 10
                    ma_reason = "Long-term trend is down but could be forming a bottom"
                else:
                    ma_score = 0
                    ma_reason = "Price near moving averages — no clear trend"
            else:
                if current < sma20 and current < sma50:
                    ma_score = 15
                    ma_reason = f"Below 20-day and 50-day averages — dip zone"
                elif current > sma20 and current > sma50:
                    ma_score = -8
                    ma_reason = "Above both averages — slightly expensive"
                else:
                    ma_score = 0
                    ma_reason = "Between moving averages — mixed signal"

        # --- Factor 3: 52-week Range Position ---
        high_52w = closes.max()
        low_52w = closes.min()
        range_pct = (
            ((current - low_52w) / (high_52w - low_52w)) * 100
            if high_52w != low_52w
            else 50
        )
        range_score = 0
        if range_pct <= 15:
            range_score = 25
            range_reason = f"Near 52-week low (bottom {range_pct:.0f}%) — strong value if company is fundamentally sound"
        elif range_pct <= 30:
            range_score = 15
            range_reason = f"In the lower third ({range_pct:.0f}%) — gives safety margin for further drops"
        elif range_pct <= 45:
            range_score = 5
            range_reason = f"Lower-mid range ({range_pct:.0f}%) — slightly cheap"
        elif range_pct <= 55:
            range_score = 0
            range_reason = f"Mid-range ({range_pct:.0f}%) — fair value"
        elif range_pct <= 70:
            range_score = -5
            range_reason = f"Upper-mid range ({range_pct:.0f}%) — limited upside unless strong catalyst"
        elif range_pct <= 85:
            range_score = -15
            range_reason = f"Upper third ({range_pct:.0f}%) — expensive, most gains already captured"
        else:
            range_score = -25
            range_reason = f"Near 52-week high (top {100 - range_pct:.0f}%) — very risky to buy at all-time highs"

        # --- Factor 4: Momentum (5-day + 20-day) ---
        change_5d = (
            ((current - closes[-6]) / closes[-6]) * 100 if len(closes) >= 6 else 0
        )
        change_20d = (
            ((current - closes[-21]) / closes[-21]) * 100 if len(closes) >= 21 else 0
        )
        momentum_score = 0
        if change_5d < -5 and change_20d < -10:
            momentum_score = 22
            momentum_reason = f"Fell {change_5d:.1f}% in 5 days, {change_20d:.1f}% in 20 days — sharp correction, strong bounce candidate"
        elif change_5d < -3 and change_20d < -5:
            momentum_score = 15
            momentum_reason = (
                f"Fell {change_5d:.1f}% in 5 days — decent pullback, potential entry"
            )
        elif change_5d < -1:
            momentum_score = 5
            momentum_reason = f"Dipped {change_5d:.1f}% in 5 days — minor pullback"
        elif change_5d > 6:
            momentum_score = -20
            momentum_reason = f"Surged {change_5d:+.1f}% in 5 days — very overheated, pullback imminent"
        elif change_5d > 3:
            momentum_score = -12
            momentum_reason = (
                f"Rose {change_5d:+.1f}% in 5 days — overheated, wait for cooling"
            )
        elif change_5d > 1:
            momentum_score = -5
            momentum_reason = f"Rose {change_5d:+.1f}% in 5 days — mild uptrend"
        else:
            if change_20d < -5:
                momentum_score = 8
                momentum_reason = f"Stable this week but down {change_20d:.1f}% over 20 days — could be entry point"
            elif change_20d > 10:
                momentum_score = -8
                momentum_reason = f"Stable this week but up {change_20d:+.1f}% over 20 days — extended rally"
            else:
                momentum_score = 0
                momentum_reason = f"Moved {change_5d:+.1f}% in 5d — sideways, no edge"

        # --- Factor 5: Volume Analysis ---
        vol_score = 0
        vol_reason = ""
        if len(volumes) >= 21:
            avg_vol_20 = np.mean(volumes[-21:-1])
            latest_vol = volumes[-1]
            vol_ratio = latest_vol / avg_vol_20 if avg_vol_20 > 0 else 1

            if vol_ratio > 3 and change_5d < -2:
                vol_score = 10
                vol_reason = f"Volume {vol_ratio:.1f}x higher during a drop — could be capitulation (buying opportunity)"
            elif vol_ratio > 2 and change_5d > 2:
                vol_score = -5
                vol_reason = f"Volume {vol_ratio:.1f}x higher during a rise — strong interest but may be exhaustion"
            elif vol_ratio < 0.5:
                vol_score = 0
                vol_reason = (
                    f"Very low volume today — no conviction in either direction"
                )
            else:
                vol_score = 0
                vol_reason = f"Normal volume ({vol_ratio:.1f}x of average)"

        # --- Factor 6: PE Valuation ---
        pe_score = 0
        pe_reason = ""
        pe_ratio = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        sector_name = info.get("sector", "")

        if pe_ratio:
            if pe_ratio < 10:
                pe_score = 20
                pe_reason = f"PE ratio {pe_ratio:.1f}x — very cheap valuation, market may be underpricing this company"
            elif pe_ratio < 15:
                pe_score = 12
                pe_reason = f"PE ratio {pe_ratio:.1f}x — attractively valued"
            elif pe_ratio < 25:
                pe_score = 0
                pe_reason = f"PE ratio {pe_ratio:.1f}x — fairly valued"
            elif pe_ratio < 40:
                pe_score = -8
                pe_reason = f"PE ratio {pe_ratio:.1f}x — expensive, needs strong growth to justify"
            elif pe_ratio < 60:
                pe_score = -15
                pe_reason = f"PE ratio {pe_ratio:.1f}x — very expensive, high expectations baked in"
            else:
                pe_score = -20
                pe_reason = f"PE ratio {pe_ratio:.1f}x — extremely expensive, any disappointment could cause a sharp fall"

            # Adjust if forward PE is much lower (expected earnings growth)
            if forward_pe and pe_ratio > 20 and forward_pe < pe_ratio * 0.7:
                pe_score += 5
                pe_reason += (
                    f" (but forward PE is {forward_pe:.1f}x — earnings growth expected)"
                )
        else:
            pe_reason = "No PE data available — cannot assess valuation"

        # --- Factor 7: Trend Consistency (last 10 days) ---
        trend_score = 0
        trend_reason = ""
        if len(closes) >= 11:
            last_10 = closes[-10:]
            up_days = sum(
                1 for i in range(1, len(last_10)) if last_10[i] > last_10[i - 1]
            )
            down_days = 9 - up_days
            if down_days >= 7:
                trend_score = 12
                trend_reason = f"{down_days}/9 recent days were down — sustained selling, could be near bottom"
            elif down_days >= 6:
                trend_score = 6
                trend_reason = f"{down_days}/9 days down — consistent weakness, possible entry forming"
            elif up_days >= 7:
                trend_score = -12
                trend_reason = (
                    f"{up_days}/9 days up — sustained buying, may be overextended"
                )
            elif up_days >= 6:
                trend_score = -6
                trend_reason = (
                    f"{up_days}/9 days up — consistent strength, slightly expensive"
                )
            else:
                trend_score = 0
                trend_reason = (
                    f"Mixed days ({up_days} up, {down_days} down) — no clear pattern"
                )

        # --- Factor 8: Enhanced News Analysis ---
        news_score = 0
        news_reason = "News not analyzed"
        if use_news:
            try:
                stock_news = fetch_ticker_news(ticker_symbol, company_name, max_items=8)
                if stock_news:
                    # Category-weighted scoring using analyze_news_impact
                    _CAT_WEIGHTS = {
                        "earnings": 2.0,
                        "regulation": 1.5,
                        "analyst": 1.5,
                        "expansion": 1.2,
                        "management": 1.0,
                        "dividend": 1.0,
                        "sector": 0.8,
                        "macro": 0.7,
                    }
                    weighted_sentiment = 0
                    cat_counts = {}
                    for n in stock_news:
                        impact = analyze_news_impact(n, ticker_symbol, name)
                        cat = impact["category"]
                        w = _CAT_WEIGHTS.get(cat, 1.0)
                        cat_counts[cat] = cat_counts.get(cat, 0) + 1
                        if impact["sentiment"] == "bullish":
                            weighted_sentiment -= w  # positive news = priced in
                        elif impact["sentiment"] == "bearish":
                            weighted_sentiment += (
                                w  # negative news = buying opportunity
                            )

                    total = len(stock_news)
                    top_cat = (
                        max(cat_counts, key=cat_counts.get) if cat_counts else "general"
                    )

                    if weighted_sentiment >= 6:
                        news_score = 15
                        news_reason = f"Heavy negative news ({total} articles, mostly {top_cat}) — fear creates strong buying opportunities"
                    elif weighted_sentiment >= 3:
                        news_score = 8
                        news_reason = f"Negative news bias ({total} articles, {top_cat} dominant) — potential dip-buy opportunity"
                    elif weighted_sentiment >= 1:
                        news_score = 3
                        news_reason = f"Slightly negative news ({total} articles) — minor buying window"
                    elif weighted_sentiment <= -6:
                        news_score = -10
                        news_reason = f"Very positive news ({total} articles, {top_cat} dominant) — rally likely priced in, risky to chase"
                    elif weighted_sentiment <= -3:
                        news_score = -5
                        news_reason = f"Positive news bias ({total} articles) — some upside already priced in"
                    elif weighted_sentiment <= -1:
                        news_score = -2
                        news_reason = f"Slightly positive news ({total} articles) — minor premium already baked in"
                    else:
                        news_score = 0
                        news_reason = f"Mixed/neutral news ({total} articles) — no clear sentiment edge"
                else:
                    news_reason = "No recent news found"
            except Exception:
                news_reason = "Could not fetch news"

        # --- Factor 9: Market Sentiment (India VIX + Nifty trend) ---
        mkt_score = 0
        mkt_reason = ""
        try:
            mkt = _get_market_trend()
            if mkt:
                nifty_rsi = mkt.get("nifty_rsi")
                nifty_chg = mkt.get("nifty_change_1m", 0)
                vix_val = mkt.get("vix")

                # VIX component
                vix_part = 0
                if vix_val is not None:
                    if vix_val > 30:
                        vix_part = 10  # extreme fear = buying opportunity
                    elif vix_val > 22:
                        vix_part = 5
                    elif vix_val < 12:
                        vix_part = -5  # complacency = risky
                    elif vix_val < 15:
                        vix_part = -2

                # Nifty trend component
                nifty_part = 0
                if nifty_rsi is not None:
                    if nifty_rsi < 30:
                        nifty_part = 8  # market oversold
                    elif nifty_rsi < 40:
                        nifty_part = 4
                    elif nifty_rsi > 75:
                        nifty_part = -8  # market overbought
                    elif nifty_rsi > 65:
                        nifty_part = -3

                # Nifty monthly change
                chg_part = 0
                if nifty_chg < -8:
                    chg_part = 8  # market correction
                elif nifty_chg < -4:
                    chg_part = 4
                elif nifty_chg > 10:
                    chg_part = -6  # market euphoria
                elif nifty_chg > 6:
                    chg_part = -3

                mkt_score = vix_part + nifty_part + chg_part
                # Cap the score
                mkt_score = max(-20, min(20, mkt_score))

                parts = []
                if vix_val is not None:
                    parts.append(f"VIX {vix_val}")
                if nifty_rsi is not None:
                    parts.append(f"Nifty RSI {nifty_rsi:.0f}")
                if nifty_chg:
                    parts.append(f"Nifty 1M {nifty_chg:+.1f}%")
                detail = ", ".join(parts)

                if mkt_score >= 10:
                    mkt_reason = f"Market fearful ({detail}) — broad correction creates buying opportunities across stocks"
                elif mkt_score >= 5:
                    mkt_reason = f"Market slightly stressed ({detail}) — favourable environment for selective buying"
                elif mkt_score <= -10:
                    mkt_reason = f"Market euphoric ({detail}) — broad rally may be overextended, risky to buy aggressively"
                elif mkt_score <= -5:
                    mkt_reason = f"Market running hot ({detail}) — be cautious, pullback possible"
                else:
                    mkt_reason = (
                        f"Market neutral ({detail}) — no strong headwind or tailwind"
                    )
        except Exception:
            mkt_reason = "Could not fetch market sentiment data"

        # --- Factor 10: Company History (fundamentals track record) ---
        hist_score = 0
        hist_reason = ""
        try:
            earnings_growth = info.get("earningsGrowth")  # QoQ
            revenue_growth = info.get("revenueGrowth")  # QoQ
            roe = info.get("returnOnEquity")
            debt_equity = info.get("debtToEquity")
            profit_margin = info.get("profitMargins")
            dividend_yield_val = info.get("dividendYield")

            hist_parts = []
            hist_sub = 0

            # Earnings growth
            if earnings_growth is not None:
                eg_pct = earnings_growth * 100
                if eg_pct > 25:
                    hist_sub += 8
                    hist_parts.append(f"earnings growing {eg_pct:+.0f}%")
                elif eg_pct > 10:
                    hist_sub += 4
                    hist_parts.append(f"earnings growing {eg_pct:+.0f}%")
                elif eg_pct > 0:
                    hist_sub += 1
                    hist_parts.append(f"earnings growing {eg_pct:+.0f}%")
                elif eg_pct > -10:
                    hist_sub -= 3
                    hist_parts.append(f"earnings declining {eg_pct:+.0f}%")
                else:
                    hist_sub -= 8
                    hist_parts.append(f"earnings falling sharply {eg_pct:+.0f}%")

            # Revenue growth
            if revenue_growth is not None:
                rg_pct = revenue_growth * 100
                if rg_pct > 20:
                    hist_sub += 5
                    hist_parts.append(f"revenue up {rg_pct:+.0f}%")
                elif rg_pct > 5:
                    hist_sub += 2
                    hist_parts.append(f"revenue up {rg_pct:+.0f}%")
                elif rg_pct < -5:
                    hist_sub -= 5
                    hist_parts.append(f"revenue down {rg_pct:+.0f}%")
                elif rg_pct < 0:
                    hist_sub -= 2
                    hist_parts.append(f"revenue flat/down {rg_pct:+.0f}%")

            # ROE (return on equity)
            if roe is not None:
                roe_pct = roe * 100
                if roe_pct > 20:
                    hist_sub += 4
                    hist_parts.append(f"ROE {roe_pct:.0f}% (excellent)")
                elif roe_pct > 12:
                    hist_sub += 2
                    hist_parts.append(f"ROE {roe_pct:.0f}% (good)")
                elif roe_pct < 5:
                    hist_sub -= 3
                    hist_parts.append(f"ROE {roe_pct:.0f}% (poor)")

            # Debt-to-equity
            if debt_equity is not None:
                if debt_equity < 30:
                    hist_sub += 3
                    hist_parts.append(f"D/E {debt_equity:.0f}% (low debt)")
                elif debt_equity > 150:
                    hist_sub -= 4
                    hist_parts.append(f"D/E {debt_equity:.0f}% (high debt)")
                elif debt_equity > 100:
                    hist_sub -= 2
                    hist_parts.append(f"D/E {debt_equity:.0f}% (moderate debt)")

            # Profit margin
            if profit_margin is not None:
                pm_pct = profit_margin * 100
                if pm_pct > 20:
                    hist_sub += 3
                    hist_parts.append(f"margin {pm_pct:.0f}% (strong)")
                elif pm_pct > 10:
                    hist_sub += 1
                elif pm_pct < 3:
                    hist_sub -= 3
                    hist_parts.append(f"margin {pm_pct:.0f}% (thin)")

            # Dividend consistency (paying dividends = established company)
            if dividend_yield_val and dividend_yield_val > 0.03:
                hist_sub += 2
                hist_parts.append(f"dividend {dividend_yield_val*100:.1f}%")
            elif dividend_yield_val and dividend_yield_val > 0.01:
                hist_sub += 1

            # Cap the history score
            hist_score = max(-20, min(20, hist_sub))

            if hist_parts:
                detail = ", ".join(hist_parts[:4])
                if hist_score >= 10:
                    hist_reason = f"Strong company fundamentals ({detail}) — quality business, supports buying"
                elif hist_score >= 5:
                    hist_reason = (
                        f"Decent company fundamentals ({detail}) — solid track record"
                    )
                elif hist_score <= -10:
                    hist_reason = f"Weak company fundamentals ({detail}) — deteriorating business, add with caution"
                elif hist_score <= -5:
                    hist_reason = f"Concerning fundamentals ({detail}) — some red flags in financials"
                else:
                    hist_reason = (
                        f"Mixed fundamentals ({detail}) — neither strong nor weak"
                    )
        except Exception:
            hist_reason = "Could not fetch company history data"

        # --- Combine scores ---
        reasons = []
        if rsi is not None:
            reasons.append(("RSI", rsi_score, rsi_reason))
        if ma_reason:
            reasons.append(("Moving Averages", ma_score, ma_reason))
        reasons.append(("52W Range Position", range_score, range_reason))
        reasons.append(("Momentum", momentum_score, momentum_reason))
        if vol_reason:
            reasons.append(("Volume", vol_score, vol_reason))
        if pe_reason:
            reasons.append(("PE Valuation", pe_score, pe_reason))
        if trend_reason:
            reasons.append(("Trend Consistency", trend_score, trend_reason))
        reasons.append(("News Sentiment", news_score, news_reason))
        if mkt_reason:
            reasons.append(("Market Sentiment", mkt_score, mkt_reason))
        if hist_reason:
            reasons.append(("Company Fundamentals", hist_score, hist_reason))

        # Apply learned weights from past prediction mistakes
        learned_weights = _load_learned_weights(ticker_symbol)
        total_score = _apply_learned_weights(reasons, learned_weights)

        # Manipulation detection — dampen score if suspicious activity detected
        manip = detect_manipulation(closes, volumes)
        if manip["is_suspicious"]:
            total_score = round(total_score * manip["score_dampening"])
            manip_summary = "; ".join(desc for _, desc in manip["flags"][:2])
            reasons.append(
                (
                    "Manipulation Guard",
                    0,
                    f"⚠️ Suspicious activity detected ({manip['severity']}): {manip_summary}. Prediction dampened to {int(manip['score_dampening']*100)}% confidence.",
                )
            )

        # Signal determination
        if total_score >= 25:
            signal = "BUY"
        elif total_score >= 10:
            signal = "LEAN BUY"
        elif total_score <= -25:
            signal = "SELL"
        elif total_score <= -10:
            signal = "LEAN SELL"
        else:
            signal = "WAIT"

        # Confidence
        positive_factors = sum(1 for _, s, _ in reasons if s > 0)
        negative_factors = sum(1 for _, s, _ in reasons if s < 0)
        neutral_factors = sum(1 for _, s, _ in reasons if s == 0)
        total_factors = len(reasons)

        if signal in ("BUY", "LEAN BUY"):
            agreement = positive_factors / total_factors
            score_strength = min(abs(total_score) / 80, 1.0)
        elif signal in ("SELL", "LEAN SELL"):
            agreement = negative_factors / total_factors
            score_strength = min(abs(total_score) / 80, 1.0)
        else:
            agreement = (
                neutral_factors + min(positive_factors, negative_factors)
            ) / total_factors
            score_strength = 1.0 - min(abs(total_score) / 30, 1.0)

        confidence = max(
            15, min(95, round((agreement * 0.5 + score_strength * 0.5) * 100))
        )

        # Prediction text
        if signal == "BUY":
            prediction = f"{name} looks undervalued right now — most indicators suggest it's a good time to buy."
        elif signal == "LEAN BUY":
            prediction = f"{name} is slightly favourable — consider buying a small amount now and more if it dips."
        elif signal == "SELL":
            prediction = f"{name} looks overvalued — consider booking profits or at least setting a stop-loss."
        elif signal == "LEAN SELL":
            prediction = (
                f"{name} is slightly unfavourable — wait for a better entry point."
            )
        else:
            prediction = f"Mixed signals for {name} — hold your position and wait for clearer direction."

        # --- Risk assessment ---
        highs = hist["High"].values
        lows = hist["Low"].values
        atr_val = compute_atr(highs, lows, closes)
        atr_pct = (atr_val / current * 100) if atr_val and current else 0
        sl = compute_stop_loss(current, atr_val) if atr_val else None

        # Classify risk level
        if atr_pct > 4 or (rsi is not None and (rsi < 25 or rsi > 75)):
            risk_level = "Very High"
        elif atr_pct > 2.5 or (rsi is not None and (rsi < 30 or rsi > 70)):
            risk_level = "High"
        elif atr_pct > 1.5:
            risk_level = "Moderate"
        else:
            risk_level = "Low"

        risk_warning = ""
        if risk_level == "Very High":
            risk_warning = f"⚠️ Very high volatility (ATR {atr_pct:.1f}%) — use strict stop-loss, small position size"
        elif risk_level == "High":
            risk_warning = f"⚠️ High volatility (ATR {atr_pct:.1f}%) — set a stop-loss before entering"
        elif risk_level == "Moderate":
            risk_warning = f"Moderate volatility (ATR {atr_pct:.1f}%) — manageable risk"

        return {
            "signal": signal,
            "confidence": confidence,
            "total_score": total_score,
            "reasons": reasons,
            "prediction": prediction,
            "current_price": round(current, 2),
            "rsi": rsi,
            "range_pct": round(range_pct, 1),
            "change_5d": round(change_5d, 2),
            "change_20d": round(change_20d, 2),
            "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
            "sector": sector_name,
            "name": name,
            "risk_level": risk_level,
            "risk_warning": risk_warning,
            "atr": round(atr_val, 2) if atr_val else None,
            "atr_pct": round(atr_pct, 1),
            "stop_loss": sl,
            "manipulation": manip if manip["is_suspicious"] else None,
            "market_sentiment": mkt_score,
            "company_fundamentals_score": hist_score,
        }
    except Exception:
        return None


def save_stock_prediction(prediction, ticker_symbol):
    """Log a stock prediction to DB or data/stock_predictions.json for tracking accuracy."""
    import os

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "ticker": ticker_symbol,
        "name": prediction.get("name", ticker_symbol),
        "signal": prediction["signal"],
        "confidence": prediction["confidence"],
        "price_at_prediction": prediction["current_price"],
        "total_score": prediction["total_score"],
        "prediction_text": prediction["prediction"],
        "factor_scores": [
            {"name": name, "score": score, "reason": reason}
            for name, score, reason in prediction["reasons"]
        ],
        "verified": False,
        "actual_price_after": None,
        "was_correct": None,
    }

    try:
        import db as _db

        if _db.is_db_available():
            return _db.save_prediction(
                "stock_predictions", entry, unique_keys=["date", "ticker"]
            )
    except ImportError:
        pass

    log_path = os.path.join(os.path.dirname(__file__), "data", "stock_predictions.json")

    predictions = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                predictions = json.load(f)
        except (json.JSONDecodeError, OSError):
            predictions = []

    # Don't duplicate same-day + same-ticker predictions
    today = entry["date"]
    predictions = [
        p
        for p in predictions
        if not (p["date"] == today and p.get("ticker") == ticker_symbol)
    ]
    predictions.append(entry)

    tmp_path = log_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(predictions, f, indent=2)
    os.replace(tmp_path, log_path)

    return entry


def verify_stock_predictions():
    """Check past stock predictions against actual prices. Returns list of verified predictions."""
    import os

    log_path = os.path.join(os.path.dirname(__file__), "data", "stock_predictions.json")
    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    updated = False
    today = datetime.now()
    for p in predictions:
        if p.get("verified"):
            continue
        pred_date = datetime.strptime(p["date"], "%Y-%m-%d")
        if (today - pred_date).days < 5:
            continue  # too early to verify

        ticker_symbol = p.get("ticker")
        if not ticker_symbol:
            continue

        try:
            t = yf.Ticker(ticker_symbol)
            hist = t.history(period="5d")
            if hist.empty:
                continue
            current_price = round(float(hist["Close"].iloc[-1]), 2)
        except Exception:
            continue

        p["actual_price_after"] = current_price
        p["verified"] = True
        price_change_pct = (
            (current_price - p["price_at_prediction"]) / p["price_at_prediction"]
        ) * 100

        if p["signal"] in ("BUY", "LEAN BUY"):
            p["was_correct"] = price_change_pct > 0
        elif p["signal"] in ("SELL", "LEAN SELL"):
            p["was_correct"] = price_change_pct < 0
        else:  # WAIT
            p["was_correct"] = abs(price_change_pct) < 3

        p["actual_change_pct"] = round(price_change_pct, 2)
        updated = True

    if updated:
        tmp_path = log_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(predictions, f, indent=2)
        os.replace(tmp_path, log_path)

    return predictions


def get_stock_prediction_learnings(ticker_symbol=None):
    """Get self-learning analysis for stock predictions.

    Args:
        ticker_symbol: specific ticker to analyze, or None for all stocks combined.

    Returns the mistake analysis or None if not enough data.
    """
    import os

    log_path = os.path.join(os.path.dirname(__file__), "data", "stock_predictions.json")
    if not os.path.exists(log_path):
        return None

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if ticker_symbol:
        predictions = [p for p in predictions if p.get("ticker") == ticker_symbol]

    return _analyze_prediction_mistakes(predictions)


# ---------------------------------------------------------------------------
# SCANNER SUGGESTION TRACKING
# ---------------------------------------------------------------------------


def save_scanner_suggestion(suggestion):
    """Log a scanner buy suggestion to DB or data/scanner_predictions.json for tracking."""
    import os

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "ticker": suggestion["ticker"],
        "name": suggestion["name"],
        "signal": (
            "BUY"
            if suggestion["urgency"] == "high"
            else ("LEAN BUY" if suggestion["urgency"] == "medium" else "WAIT")
        ),
        "urgency": suggestion["urgency"],
        "price_at_prediction": suggestion["price"],
        "rsi": suggestion.get("rsi"),
        "from_high_pct": suggestion.get("from_high_pct"),
        "buy_verdict": suggestion.get("buy_verdict", ""),
        "buy_reasoning": suggestion.get("buy_reasoning", []),
        "risk_level": suggestion.get("risk_level", ""),
        "pe_ratio": suggestion.get("pe_ratio"),
        "sector": suggestion.get("sector", ""),
        "verified": False,
        "actual_price_7d": None,
        "actual_price_30d": None,
        "was_correct_7d": None,
        "was_correct_30d": None,
    }

    try:
        import db as _db

        if _db.is_db_available():
            return _db.save_prediction(
                "scanner_predictions", entry, unique_keys=["date", "ticker"]
            )
    except ImportError:
        pass

    log_path = os.path.join(
        os.path.dirname(__file__), "data", "scanner_predictions.json"
    )

    predictions = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                predictions = json.load(f)
        except (json.JSONDecodeError, OSError):
            predictions = []

    # Don't duplicate same-day + same-ticker
    today = entry["date"]
    predictions = [
        p
        for p in predictions
        if not (p["date"] == today and p.get("ticker") == suggestion["ticker"])
    ]
    predictions.append(entry)

    tmp_path = log_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(predictions, f, indent=2)
    os.replace(tmp_path, log_path)

    return entry


def verify_scanner_predictions():
    """Check past scanner suggestions against actual price movement.

    Verifies at two intervals:
    - 7 days: short-term bounce (was the buy call right?)
    - 30 days: medium-term trend (did it recover?)
    """
    import os

    log_path = os.path.join(
        os.path.dirname(__file__), "data", "scanner_predictions.json"
    )
    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    updated = False
    today = datetime.now()

    for p in predictions:
        pred_date = datetime.strptime(p["date"], "%Y-%m-%d")
        days_elapsed = (today - pred_date).days
        ticker = p.get("ticker")
        if not ticker:
            continue
        pred_price = p.get("price_at_prediction", 0)
        if pred_price <= 0:
            continue

        need_7d = days_elapsed >= 7 and not p.get("verified_7d")
        need_30d = days_elapsed >= 30 and not p.get("verified_30d")

        if not need_7d and not need_30d:
            continue

        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="3mo")
            if hist.empty:
                continue

            if need_7d:
                target_7d = pred_date + timedelta(days=7)
                after_7d = hist[hist.index >= target_7d.strftime("%Y-%m-%d")]
                if not after_7d.empty:
                    price_7d = round(float(after_7d["Close"].iloc[0]), 2)
                    change_7d = ((price_7d - pred_price) / pred_price) * 100
                    p["actual_price_7d"] = price_7d
                    p["change_pct_7d"] = round(change_7d, 2)
                    p["verified_7d"] = True
                    # BUY/LEAN BUY correct if price went up; WAIT correct if stayed flat
                    if p["signal"] in ("BUY", "LEAN BUY"):
                        p["was_correct_7d"] = change_7d > 0
                    else:
                        p["was_correct_7d"] = abs(change_7d) < 3
                    updated = True

            if need_30d:
                target_30d = pred_date + timedelta(days=30)
                after_30d = hist[hist.index >= target_30d.strftime("%Y-%m-%d")]
                if not after_30d.empty:
                    price_30d = round(float(after_30d["Close"].iloc[0]), 2)
                    change_30d = ((price_30d - pred_price) / pred_price) * 100
                    p["actual_price_30d"] = price_30d
                    p["change_pct_30d"] = round(change_30d, 2)
                    p["verified_30d"] = True
                    if p["signal"] in ("BUY", "LEAN BUY"):
                        p["was_correct_30d"] = change_30d > 0
                    else:
                        p["was_correct_30d"] = abs(change_30d) < 3
                    updated = True

                    # Mark overall verified once 30d is done
                    p["verified"] = True
                    p["was_correct"] = p.get("was_correct_30d")
                    p["actual_price_after"] = price_30d
                    p["actual_change_pct"] = round(change_30d, 2)

        except Exception:
            continue

    if updated:
        tmp_path = log_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(predictions, f, indent=2)
        os.replace(tmp_path, log_path)

    return predictions


def get_scanner_prediction_learnings():
    """Analyze scanner suggestion accuracy — which urgency levels / signals work best."""
    import os

    log_path = os.path.join(
        os.path.dirname(__file__), "data", "scanner_predictions.json"
    )
    if not os.path.exists(log_path):
        return None

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    return _analyze_prediction_mistakes(predictions)


# ---------------------------------------------------------------------------
# SILVER PRICE TRACKING — same approach as gold
# ---------------------------------------------------------------------------


def get_silver_price():
    """Fetch silver price in INR per gram (international silver converted via USD/INR).
    Chennai silver ≈ international price + ~5% premium (GST + making).
    """
    try:
        silver = yf.Ticker("SI=F")  # Silver futures USD/troy oz
        usd_inr = yf.Ticker("USDINR=X")

        silver_data = silver.history(period="5d")
        fx_data = usd_inr.history(period="5d")

        if silver_data.empty or fx_data.empty:
            return None

        silver_usd = silver_data["Close"].iloc[-1]
        rate = fx_data["Close"].iloc[-1]

        # 1 troy ounce = 31.1035 grams
        silver_inr_per_gram = (silver_usd * rate) / 31.1035
        chennai_per_gram = silver_inr_per_gram * 1.05  # ~5% premium

        # Daily change
        change_pct = None
        if len(silver_data) >= 2 and len(fx_data) >= 2:
            prev_silver = silver_data["Close"].iloc[-2]
            prev_fx = fx_data["Close"].iloc[-2]
            prev_per_gram = (prev_silver * prev_fx) / 31.1035 * 1.05
            change_pct = round(
                ((chennai_per_gram - prev_per_gram) / prev_per_gram) * 100, 2
            )

        return {
            "per_gram": round(chennai_per_gram, 2),
            "per_100gram": round(chennai_per_gram * 100, 2),
            "per_kg": round(chennai_per_gram * 1000, 2),
            "change_pct": change_pct,
        }
    except Exception:
        return None


def analyze_silver_trend():
    """Analyze silver price trend over multiple timeframes."""
    try:
        silver = yf.Ticker("SI=F")
        usd_inr = yf.Ticker("USDINR=X")

        silver_hist = silver.history(period="3mo")
        fx_hist = usd_inr.history(period="3mo")

        if silver_hist.empty or fx_hist.empty:
            return None

        inr_per_gram = _gold_inr_series(silver_hist, fx_hist, premium=1.05)
        if inr_per_gram is None or len(inr_per_gram) < 5:
            return None

        current = inr_per_gram.iloc[-1]
        week_ago = (
            inr_per_gram.iloc[-6] if len(inr_per_gram) >= 6 else inr_per_gram.iloc[0]
        )
        month_ago = (
            inr_per_gram.iloc[-23] if len(inr_per_gram) >= 23 else inr_per_gram.iloc[0]
        )

        return {
            "weekly_change": round(((current - week_ago) / week_ago) * 100, 2),
            "monthly_change": round(((current - month_ago) / month_ago) * 100, 2),
            "high_3m": round(inr_per_gram.max(), 2),
            "low_3m": round(inr_per_gram.min(), 2),
        }
    except Exception:
        return None


def predict_silver_buy(use_news=True):
    """Analyze silver price data and predict if it's a good time to buy.

    Uses same 7-factor approach as gold: RSI, MAs, range, momentum,
    volatility, trend consistency, news.
    """
    try:
        silver = yf.Ticker("SI=F")
        usd_inr = yf.Ticker("USDINR=X")

        silver_hist = silver.history(period="6mo")
        fx_hist = usd_inr.history(period="6mo")

        if silver_hist.empty or fx_hist.empty:
            return None

        inr_per_gram = _gold_inr_series(silver_hist, fx_hist, premium=1.05)
        if inr_per_gram is None or len(inr_per_gram) < 30:
            return None

        prices = inr_per_gram.values
        current = prices[-1]

        # --- Factor 1: RSI ---
        rsi = compute_rsi(prices)
        rsi_score = 0
        rsi_reason = ""
        if rsi is not None:
            if rsi <= 25:
                rsi_score = 30
                rsi_reason = (
                    f"RSI is {rsi:.0f} — silver is deeply oversold, strong buying zone"
                )
            elif rsi <= 35:
                rsi_score = 20
                rsi_reason = f"RSI is {rsi:.0f} — oversold territory, good entry point"
            elif rsi <= 45:
                rsi_score = 8
                rsi_reason = f"RSI is {rsi:.0f} — leaning towards cheap"
            elif rsi <= 55:
                rsi_score = 0
                rsi_reason = f"RSI is {rsi:.0f} — neutral zone"
            elif rsi <= 65:
                rsi_score = -8
                rsi_reason = f"RSI is {rsi:.0f} — leaning towards expensive"
            elif rsi <= 75:
                rsi_score = -20
                rsi_reason = f"RSI is {rsi:.0f} — getting overbought"
            else:
                rsi_score = -30
                rsi_reason = f"RSI is {rsi:.0f} — heavily overbought"

        # --- Factor 2: Moving averages ---
        ma10 = np.mean(prices[-10:]) if len(prices) >= 10 else None
        ma20 = np.mean(prices[-20:]) if len(prices) >= 20 else None
        ma50 = np.mean(prices[-50:]) if len(prices) >= 50 else None
        ma_score = 0
        ma_reason = ""
        if ma20 and ma50:
            pct_from_ma20 = ((current - ma20) / ma20) * 100
            if current < ma20 and current < ma50:
                ma_score = 20
                ma_reason = f"Price is {abs(pct_from_ma20):.1f}% below 20-day avg — dip buying zone"
            elif current < ma20:
                ma_score = 10
                ma_reason = f"Price is {abs(pct_from_ma20):.1f}% below 20-day avg — short-term dip"
            elif current > ma20 and current > ma50 and ma20 > ma50:
                if pct_from_ma20 > 5:
                    ma_score = -15
                    ma_reason = (
                        f"Price is {pct_from_ma20:.1f}% above 20-day avg — stretched"
                    )
                else:
                    ma_score = -8
                    ma_reason = "Price above both averages — slightly expensive"
            elif ma10 and ma10 < ma20:
                ma_score = 8
                ma_reason = (
                    "Short-term avg crossing below medium-term — possible dip forming"
                )
            else:
                ma_score = 0
                ma_reason = "Price is near moving averages — no clear trend"

        # --- Factor 3: 3-month range position ---
        high_3m = prices[-66:].max() if len(prices) >= 66 else prices.max()
        low_3m = prices[-66:].min() if len(prices) >= 66 else prices.min()
        range_pct = (
            ((current - low_3m) / (high_3m - low_3m)) * 100 if high_3m != low_3m else 50
        )
        range_score = 0
        if range_pct <= 15:
            range_score = 25
            range_reason = (
                f"Near 3-month low (bottom {range_pct:.0f}%) — strong buying level"
            )
        elif range_pct <= 30:
            range_score = 15
            range_reason = f"Lower third of range ({range_pct:.0f}%) — good value"
        elif range_pct <= 45:
            range_score = 5
            range_reason = f"Lower-mid range ({range_pct:.0f}%) — slightly cheap"
        elif range_pct <= 55:
            range_score = 0
            range_reason = f"Mid-range ({range_pct:.0f}%) — fair value"
        elif range_pct <= 70:
            range_score = -5
            range_reason = f"Upper-mid range ({range_pct:.0f}%) — slightly expensive"
        elif range_pct <= 85:
            range_score = -15
            range_reason = f"Upper third ({range_pct:.0f}%) — expensive"
        else:
            range_score = -25
            range_reason = f"Near 3-month high (top {100 - range_pct:.0f}%) — risky"

        # --- Factor 4: Momentum ---
        change_5d = (
            ((current - prices[-6]) / prices[-6]) * 100 if len(prices) >= 6 else 0
        )
        change_20d = (
            ((current - prices[-21]) / prices[-21]) * 100 if len(prices) >= 21 else 0
        )
        momentum_score = 0
        if change_5d < -3 and change_20d < -5:
            momentum_score = 20
            momentum_reason = f"Silver fell {change_5d:.1f}% in 5d, {change_20d:.1f}% in 20d — sharp correction"
        elif change_5d < -2:
            momentum_score = 12
            momentum_reason = (
                f"Silver fell {change_5d:.1f}% in 5 days — decent pullback"
            )
        elif change_5d < -1:
            momentum_score = 5
            momentum_reason = (
                f"Silver dipped {change_5d:.1f}% in 5 days — minor pullback"
            )
        elif change_5d > 4:
            momentum_score = -20
            momentum_reason = (
                f"Silver surged {change_5d:+.1f}% in 5 days — very overheated"
            )
        elif change_5d > 2:
            momentum_score = -12
            momentum_reason = f"Silver rose {change_5d:+.1f}% in 5 days — overheated"
        elif change_5d > 1:
            momentum_score = -5
            momentum_reason = f"Silver rose {change_5d:+.1f}% in 5 days — mild uptrend"
        else:
            if change_20d < -3:
                momentum_score = 8
                momentum_reason = f"Stable this week but down {change_20d:.1f}% over 20 days — broader dip"
            elif change_20d > 5:
                momentum_score = -8
                momentum_reason = f"Stable this week but up {change_20d:+.1f}% over 20 days — extended rally"
            else:
                momentum_score = 0
                momentum_reason = f"Silver moved {change_5d:+.1f}% in 5d — sideways"

        # --- Factor 5: Volatility ---
        vol_score = 0
        vol_reason = ""
        if len(prices) >= 11:
            daily_returns = np.diff(prices[-11:]) / prices[-11:-1] * 100
            volatility = np.std(daily_returns)
            avg_vol = (
                np.std(np.diff(prices[-60:]) / prices[-60:-1] * 100)
                if len(prices) >= 60
                else volatility
            )
            if volatility > avg_vol * 1.5:
                vol_score = -8
                vol_reason = f"Very choppy ({volatility:.2f}% vs avg {avg_vol:.2f}%) — risky entry"
            elif volatility < avg_vol * 0.7:
                vol_score = 5
                vol_reason = f"Calm market ({volatility:.2f}% vs avg {avg_vol:.2f}%) — stable entry"
            else:
                vol_score = 0
                vol_reason = f"Normal volatility ({volatility:.2f}%)"

        # --- Factor 6: Trend consistency ---
        trend_score = 0
        trend_reason = ""
        if len(prices) >= 11:
            last_10 = prices[-10:]
            up_days = sum(
                1 for i in range(1, len(last_10)) if last_10[i] > last_10[i - 1]
            )
            down_days = 9 - up_days
            if down_days >= 7:
                trend_score = 12
                trend_reason = f"{down_days}/9 recent days down — sustained selling, could be near bottom"
            elif down_days >= 6:
                trend_score = 6
                trend_reason = f"{down_days}/9 recent days down — consistent weakness"
            elif up_days >= 7:
                trend_score = -12
                trend_reason = f"{up_days}/9 recent days up — may be overextended"
            elif up_days >= 6:
                trend_score = -6
                trend_reason = f"{up_days}/9 recent days up — consistent strength"
            else:
                trend_score = 0
                trend_reason = f"Mixed recent days ({up_days} up, {down_days} down)"

        # --- Factor 7: News ---
        news_score = 0
        news_reason = "News not analyzed"
        if use_news:
            try:
                silver_news = fetch_news("Silver Price India", max_items=8)
                if silver_news:
                    bull = sum(1 for n in silver_news if n["sentiment"] == "bullish")
                    bear = sum(1 for n in silver_news if n["sentiment"] == "bearish")
                    total = len(silver_news)
                    if bear > bull and bear >= 4:
                        news_score = 12
                        news_reason = f"News is heavily negative ({bear}/{total}) — fear creates opportunities"
                    elif bear > bull and bear >= 2:
                        news_score = 6
                        news_reason = f"News leaning negative ({bear}/{total}) — possible dip opportunity"
                    elif bull > bear and bull >= 4:
                        news_score = -8
                        news_reason = f"News very positive ({bull}/{total}) — rally may be priced in"
                    elif bull > bear and bull >= 2:
                        news_score = -4
                        news_reason = f"News leaning positive ({bull}/{total}) — some upside priced in"
                    else:
                        news_score = 0
                        news_reason = f"Mixed news ({bull} positive, {bear} negative)"
            except Exception:
                news_reason = "Could not fetch silver news"

        # --- Factor 8: US Dollar Strength (inverse correlation) ---
        dollar_score = 0
        dollar_reason = ""
        try:
            dxy = yf.Ticker("DX-Y.NYB")
            dxy_hist = dxy.history(period="1mo")
            if not dxy_hist.empty and len(dxy_hist) >= 5:
                dxy_prices = dxy_hist["Close"].values
                dxy_current = dxy_prices[-1]
                dxy_20d_ago = dxy_prices[0]
                dxy_change = ((dxy_current - dxy_20d_ago) / dxy_20d_ago) * 100
                if dxy_change > 3:
                    dollar_score = 12
                    dollar_reason = f"US Dollar strengthened {dxy_change:+.1f}% — silver tends to fall, buy window"
                elif dxy_change > 1.5:
                    dollar_score = 6
                    dollar_reason = f"US Dollar rising ({dxy_change:+.1f}%) — mild headwind for silver"
                elif dxy_change < -3:
                    dollar_score = -10
                    dollar_reason = f"US Dollar weakened {dxy_change:+.1f}% — silver already benefiting"
                elif dxy_change < -1.5:
                    dollar_score = -4
                    dollar_reason = f"US Dollar dipping ({dxy_change:+.1f}%) — supportive for silver"
                else:
                    dollar_score = 0
                    dollar_reason = (
                        f"US Dollar stable ({dxy_change:+.1f}%) — no currency signal"
                    )
        except Exception:
            dollar_reason = "Could not fetch US Dollar data"

        # --- Factor 9: Gold-Silver Ratio (silver-specific) ---
        gsr_score = 0
        gsr_reason = ""
        try:
            gold_t = yf.Ticker("GC=F")
            gold_h = gold_t.history(period="3mo")
            if not gold_h.empty and not silver_hist.empty:
                gold_usd = gold_h["Close"].iloc[-1]
                silver_usd = silver_hist["Close"].iloc[-1]
                if silver_usd > 0:
                    gsr = gold_usd / silver_usd
                    # For silver: high ratio means silver is CHEAP relative to gold
                    if gsr > 90:
                        gsr_score = 15
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (very high) — silver is historically cheap vs gold, strong buy signal"
                    elif gsr > 80:
                        gsr_score = 8
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (high) — silver undervalued relative to gold"
                    elif gsr < 60:
                        gsr_score = -10
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (low) — silver is expensive relative to gold"
                    elif gsr < 70:
                        gsr_score = -4
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (normal-low) — silver fairly priced"
                    else:
                        gsr_score = 0
                        gsr_reason = f"Gold-Silver ratio is {gsr:.0f}x (normal) — no relative value signal"
        except Exception:
            gsr_reason = "Could not compute Gold-Silver ratio"

        # --- Factor 10: Indian Seasonal Demand ---
        month = datetime.now().month
        seasonal_score = 0
        if month in (10, 11):
            seasonal_score = 8
            seasonal_reason = "Festive season (Diwali/Dhanteras) — silver demand rises for utensils and gifts"
        elif month in (1, 2):
            seasonal_score = 5
            seasonal_reason = "Wedding season — silver jewellery demand supports prices"
        elif month in (4, 5):
            seasonal_score = 4
            seasonal_reason = "Akshaya Tritiya — auspicious metal buying period"
        elif month in (7, 8):
            seasonal_score = -4
            seasonal_reason = "Off-season for precious metals — demand typically lower"
        else:
            seasonal_score = 0
            seasonal_reason = "No strong seasonal pattern this month"

        # --- Factor 11: Market Fear / VIX ---
        vix_score = 0
        vix_reason = ""
        try:
            vix = yf.Ticker("^VIX")
            vix_hist = vix.history(period="5d")
            if not vix_hist.empty:
                vix_current = vix_hist["Close"].iloc[-1]
                if vix_current > 30:
                    vix_score = 10
                    vix_reason = f"VIX is {vix_current:.0f} (high fear) — precious metals benefit as safe haven"
                elif vix_current > 25:
                    vix_score = 5
                    vix_reason = f"VIX is {vix_current:.0f} (elevated) — some flight to safety supports silver"
                elif vix_current < 15:
                    vix_score = -6
                    vix_reason = f"VIX is {vix_current:.0f} (very calm) — less safe-haven demand for silver"
                elif vix_current < 20:
                    vix_score = -2
                    vix_reason = (
                        f"VIX is {vix_current:.0f} (normal) — neutral for silver"
                    )
                else:
                    vix_score = 0
                    vix_reason = (
                        f"VIX is {vix_current:.0f} (moderate) — no strong signal"
                    )
        except Exception:
            vix_reason = "Could not fetch VIX data"

        # --- Factor 12: US Treasury Yield ---
        yield_score = 0
        yield_reason = ""
        try:
            tnx = yf.Ticker("^TNX")
            tnx_hist = tnx.history(period="1mo")
            if not tnx_hist.empty and len(tnx_hist) >= 5:
                yield_current = tnx_hist["Close"].iloc[-1]
                yield_prev = tnx_hist["Close"].iloc[0]
                yield_change = yield_current - yield_prev
                if yield_change > 0.3:
                    yield_score = 10
                    yield_reason = f"US 10Y yield rose {yield_change:+.2f}% to {yield_current:.2f}% — creates buy opportunity for silver"
                elif yield_change > 0.1:
                    yield_score = 4
                    yield_reason = (
                        f"US 10Y yield edging up ({yield_current:.2f}%) — mild headwind"
                    )
                elif yield_change < -0.3:
                    yield_score = -8
                    yield_reason = f"US 10Y yield fell {yield_change:+.2f}% — bullish for silver, already priced in"
                elif yield_change < -0.1:
                    yield_score = -3
                    yield_reason = f"US 10Y yield drifting lower — mildly supportive"
                else:
                    yield_score = 0
                    yield_reason = f"US 10Y yield stable at {yield_current:.2f}% — no rate pressure"
        except Exception:
            yield_reason = "Could not fetch Treasury yield data"

        # --- Combine ---
        reasons = []
        if rsi is not None:
            reasons.append(("Momentum (RSI)", rsi_score, rsi_reason))
        if ma_reason:
            reasons.append(("Moving Averages", ma_score, ma_reason))
        reasons.append(("3M Range Position", range_score, range_reason))
        reasons.append(("Price Momentum", momentum_score, momentum_reason))
        if vol_reason:
            reasons.append(("Volatility", vol_score, vol_reason))
        if trend_reason:
            reasons.append(("Trend Consistency", trend_score, trend_reason))
        reasons.append(("News Sentiment", news_score, news_reason))
        if dollar_reason:
            reasons.append(("US Dollar Strength", dollar_score, dollar_reason))
        if gsr_reason:
            reasons.append(("Gold-Silver Ratio", gsr_score, gsr_reason))
        reasons.append(("Seasonal Demand (India)", seasonal_score, seasonal_reason))
        if vix_reason:
            reasons.append(("Market Fear (VIX)", vix_score, vix_reason))
        if yield_reason:
            reasons.append(("US Treasury Yield", yield_score, yield_reason))

        # Apply learned weights from past prediction mistakes
        learned_weights = _load_learned_weights("silver")
        total_score = _apply_learned_weights(reasons, learned_weights)

        # --- Manipulation detection ---
        silver_volumes = (
            silver_hist["Volume"].values if "Volume" in silver_hist.columns else None
        )
        manip = {
            "is_suspicious": False,
            "score_dampening": 1.0,
            "flags": [],
            "severity": "none",
        }
        if silver_volumes is not None and len(silver_volumes) >= 30:
            # Align lengths: prices from inr_per_gram may differ from silver_hist
            min_len = min(len(prices), len(silver_volumes))
            manip = detect_manipulation(prices[-min_len:], silver_volumes[-min_len:])
            if manip["is_suspicious"]:
                total_score = int(total_score * manip["score_dampening"])
                manip_summary = "; ".join(desc for _, desc in manip["flags"][:2])
                reasons.append(
                    (
                        "Manipulation Guard",
                        -10,
                        f"Suspicious activity detected ({manip['severity']}): {manip_summary}",
                    )
                )

        if total_score >= 25:
            signal = "BUY"
        elif total_score >= 10:
            signal = "LEAN BUY"
        elif total_score <= -25:
            signal = "SELL"
        elif total_score <= -10:
            signal = "LEAN SELL"
        else:
            signal = "WAIT"

        positive_factors = sum(1 for _, s, _ in reasons if s > 0)
        negative_factors = sum(1 for _, s, _ in reasons if s < 0)
        neutral_factors = sum(1 for _, s, _ in reasons if s == 0)
        total_factors = len(reasons)

        if signal in ("BUY", "LEAN BUY"):
            agreement = positive_factors / total_factors
            score_strength = min(abs(total_score) / 50, 1.0)
        elif signal in ("SELL", "LEAN SELL"):
            agreement = negative_factors / total_factors
            score_strength = min(abs(total_score) / 50, 1.0)
        else:
            agreement = (
                neutral_factors + min(positive_factors, negative_factors)
            ) / total_factors
            score_strength = 1.0 - min(abs(total_score) / 30, 1.0)

        confidence = max(
            15, min(95, round((agreement * 0.5 + score_strength * 0.5) * 100))
        )

        if signal == "BUY":
            prediction = (
                f"Silver dropped {change_5d:.1f}% recently — expect a bounce in the next 5-7 days."
                if change_5d < -2
                else "Conditions favour buying — silver likely to hold or rise this week."
            )
        elif signal == "LEAN BUY":
            prediction = "Slightly favourable — consider buying a small amount now."
        elif signal == "SELL":
            prediction = (
                f"Silver surged {change_5d:+.1f}% recently — expect a pullback."
                if change_5d > 3
                else "Most indicators say silver is expensive — wait."
            )
        elif signal == "LEAN SELL":
            prediction = "Conditions lean against buying — wait a few days for a dip."
        else:
            prediction = "Mixed signals — hold off and check again in a few days."

        # --- Risk assessment ---
        sv_vol_pct = 0
        if len(prices) >= 11:
            sv_dr = np.diff(prices[-11:]) / prices[-11:-1] * 100
            sv_vol_pct = float(np.std(sv_dr))
        if sv_vol_pct > 3.0 or (rsi is not None and (rsi < 25 or rsi > 75)):
            risk_level = "Very High"
            risk_warning = (
                f"⚠️ Very high volatility ({sv_vol_pct:.1f}%) — use small position size"
            )
        elif sv_vol_pct > 2.0 or (rsi is not None and (rsi < 30 or rsi > 70)):
            risk_level = "High"
            risk_warning = f"⚠️ High volatility ({sv_vol_pct:.1f}%) — set a stop-loss"
        elif sv_vol_pct > 1.0:
            risk_level = "Moderate"
            risk_warning = f"Moderate volatility ({sv_vol_pct:.1f}%) — manageable risk"
        else:
            risk_level = "Low"
            risk_warning = ""

        return {
            "signal": signal,
            "confidence": confidence,
            "total_score": total_score,
            "reasons": reasons,
            "prediction": prediction,
            "current_price": round(current, 2),
            "rsi": rsi,
            "range_pct": round(range_pct, 1),
            "change_5d": round(change_5d, 2),
            "change_20d": round(change_20d, 2),
            "risk_level": risk_level,
            "risk_warning": risk_warning,
            "manipulation": manip if manip["is_suspicious"] else None,
        }
    except Exception:
        return None


def save_silver_prediction(prediction):
    """Log a silver prediction to DB or data/silver_predictions.json."""
    import os

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "signal": prediction["signal"],
        "confidence": prediction["confidence"],
        "price_at_prediction": prediction["current_price"],
        "total_score": prediction["total_score"],
        "prediction_text": prediction["prediction"],
        "factor_scores": [
            {"name": name, "score": score, "reason": reason}
            for name, score, reason in prediction["reasons"]
        ],
        "verified": False,
        "actual_price_after": None,
        "was_correct": None,
    }

    try:
        import db as _db

        if _db.is_db_available():
            return _db.save_prediction(
                "silver_predictions", entry, unique_keys=["date"]
            )
    except ImportError:
        pass

    log_path = os.path.join(
        os.path.dirname(__file__), "data", "silver_predictions.json"
    )
    predictions = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                predictions = json.load(f)
        except (json.JSONDecodeError, OSError):
            predictions = []

    today = entry["date"]
    predictions = [p for p in predictions if p["date"] != today]
    predictions.append(entry)

    tmp_path = log_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(predictions, f, indent=2)
    os.replace(tmp_path, log_path)

    return entry


def verify_silver_predictions():
    """Check past silver predictions against actual prices."""
    import os

    log_path = os.path.join(
        os.path.dirname(__file__), "data", "silver_predictions.json"
    )
    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "r") as f:
            predictions = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    try:
        silver = yf.Ticker("SI=F")
        usd_inr = yf.Ticker("USDINR=X")
        silver_hist = silver.history(period="1mo")
        fx_hist = usd_inr.history(period="1mo")
        if silver_hist.empty or fx_hist.empty:
            return predictions
        inr_per_gram = _gold_inr_series(silver_hist, fx_hist, premium=1.05)
        current_price = (
            round(inr_per_gram.iloc[-1], 2)
            if inr_per_gram is not None and len(inr_per_gram) > 0
            else None
        )
    except Exception:
        return predictions

    if current_price is None:
        return predictions

    updated = False
    today = datetime.now()
    for p in predictions:
        if p.get("verified"):
            continue
        pred_date = datetime.strptime(p["date"], "%Y-%m-%d")
        if (today - pred_date).days < 5:
            continue

        p["actual_price_after"] = current_price
        p["verified"] = True
        price_change_pct = (
            (current_price - p["price_at_prediction"]) / p["price_at_prediction"]
        ) * 100

        if p["signal"] in ("BUY", "LEAN BUY"):
            p["was_correct"] = price_change_pct > 0
        elif p["signal"] in ("SELL", "LEAN SELL"):
            p["was_correct"] = price_change_pct < 0
        else:
            p["was_correct"] = abs(price_change_pct) < 2

        p["actual_change_pct"] = round(price_change_pct, 2)
        updated = True

    if updated:
        tmp_path = log_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(predictions, f, indent=2)
        os.replace(tmp_path, log_path)

    return predictions


# ---------------------------------------------------------------------------
# MUTUAL FUND NAV TRACKING — AMFI India API (free, no key)
# ---------------------------------------------------------------------------

AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"


def fetch_mf_nav_batch(scheme_codes):
    """Fetch NAVs for multiple schemes in one download."""
    results = {}
    try:
        req = urllib.request.Request(
            AMFI_NAV_URL, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        code_set = set(str(c) for c in scheme_codes)
        for line in content.splitlines():
            parts = line.strip().split(";")
            if len(parts) >= 5 and parts[0].strip() in code_set:
                code = parts[0].strip()
                results[code] = {
                    "scheme_code": code,
                    "scheme_name": parts[3].strip(),
                    "nav": float(parts[4].strip()),
                    "date": parts[5].strip() if len(parts) > 5 else "",
                }
    except Exception:
        pass
    return results


def _aggregate_transactions(transactions):
    """Aggregate a list of transactions into summary stats.

    Returns dict with total_quantity, total_invested, weighted_avg_price,
    earliest_date, latest_date, highest_price_txn, largest_qty_txn.
    """
    total_qty = 0
    total_invested = 0
    earliest = None
    latest = None
    highest_price = 0
    highest_price_txn = None
    largest_qty = 0
    largest_qty_txn = None

    for txn in transactions:
        qty = float(txn.get("quantity", 0))
        price = float(txn.get("buy_price", 0))
        total_qty += qty
        total_invested += price * qty
        if price > highest_price:
            highest_price = price
            highest_price_txn = txn
        if qty > largest_qty:
            largest_qty = qty
            largest_qty_txn = txn
        d = txn.get("buy_date", "")
        if d:
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                if earliest is None or dt < earliest:
                    earliest = dt
                if latest is None or dt > latest:
                    latest = dt
            except ValueError:
                pass

    weighted_avg = total_invested / total_qty if total_qty > 0 else 0
    return {
        "total_quantity": total_qty,
        "total_invested": total_invested,
        "weighted_avg_price": weighted_avg,
        "earliest_date": earliest,
        "latest_date": latest,
        "highest_price_txn": highest_price_txn,
        "largest_qty_txn": largest_qty_txn,
    }


def load_portfolio_extended(path="data/portfolio.json", from_rows=None):
    """Load portfolio from JSON or pre-loaded rows with buy_date, buy_price, quantity fields.

    Supports two investment modes:
      - lumpsum: amount = buy_price × quantity (supports multi-transaction)
      - sip: amount = sip_monthly × months_elapsed

    If from_rows is provided, uses those dicts directly instead of reading from file.
    """
    holdings = []
    try:
        if from_rows is not None:
            data = from_rows
        else:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        for row in data:
            investment_mode = row.get("investment_mode", "lumpsum")
            sip_monthly = float(row.get("sip_monthly", 0) or 0)

            # Multi-transaction support: use transactions array if present
            transactions = row.get("transactions", [])
            if transactions and investment_mode == "lumpsum":
                agg = _aggregate_transactions(transactions)
                buy_price = agg["weighted_avg_price"]
                quantity = agg["total_quantity"]
                amount = agg["total_invested"]
                earliest = agg["earliest_date"]
                buy_date_str = earliest.strftime("%Y-%m-%d") if earliest else ""
                buy_date = earliest
            else:
                buy_price = float(row.get("buy_price", 0))
                quantity = float(row.get("quantity", 1))
                buy_date_str = row.get("buy_date", "")
                buy_date = None
                if buy_date_str:
                    try:
                        buy_date = datetime.strptime(buy_date_str, "%Y-%m-%d").date()
                    except ValueError:
                        pass

                # For SIP entries, compute amount from monthly × months elapsed
                if investment_mode == "sip" and sip_monthly > 0 and buy_date:
                    months_elapsed = (
                        datetime.now().date().year - buy_date.year
                    ) * 12 + (datetime.now().date().month - buy_date.month)
                    amount = sip_monthly * max(months_elapsed, 1)
                else:
                    amount = buy_price * quantity

            days_held = (datetime.now().date() - buy_date).days if buy_date else 0

            holdings.append(
                {
                    "name": row["name"],
                    "ticker": row.get("ticker", "").strip(),
                    "amount": amount,
                    "buy_price": buy_price,
                    "quantity": quantity,
                    "buy_date": buy_date_str,
                    "days_held": days_held,
                    "is_ltcg": days_held > 365,
                    "type": row.get("type", "stock"),
                    "investment_mode": investment_mode,
                    "sip_monthly": sip_monthly,
                    "sip_date": int(row.get("sip_date", 0) or 0),
                    "amfi_code": row.get("amfi_code", "").strip(),
                    "transactions": transactions,
                }
            )
    except FileNotFoundError:
        pass
    return holdings


# ---------------------------------------------------------------------------
# PORTFOLIO DIVERSIFICATION SCORE
# ---------------------------------------------------------------------------


def compute_diversification(holdings, analysis_results=None):
    """Compute portfolio diversification metrics and warnings.

    Returns dict with:
      - type_allocation: {type: percentage}
      - sector_allocation: {sector: percentage} (for stocks with analysis data)
      - hhi: Herfindahl-Hirschman Index (0-10000, lower = more diverse)
      - score: 0-100 (higher = better diversified)
      - warnings: list of warning strings
    """
    if not holdings:
        return None

    total = sum(h["amount"] for h in holdings)
    if total <= 0:
        return None

    # --- Type allocation ---
    type_alloc = {}
    for h in holdings:
        t = h["type"]
        type_alloc[t] = type_alloc.get(t, 0) + h["amount"]
    type_pct = {k: round((v / total) * 100, 1) for k, v in type_alloc.items()}

    # --- Sector allocation (from analysis results) ---
    sector_alloc = {}
    if analysis_results:
        for r in analysis_results:
            a = r.get("analysis")
            h = r["holding"]
            if a and a.get("sector"):
                sector_alloc[a["sector"]] = (
                    sector_alloc.get(a["sector"], 0) + h["amount"]
                )
    sector_pct = {k: round((v / total) * 100, 1) for k, v in sector_alloc.items()}

    # --- Individual holding concentration ---
    holding_pcts = [
        (h["name"], round((h["amount"] / total) * 100, 1)) for h in holdings
    ]

    # --- HHI (using individual holding weights) ---
    weights = [(h["amount"] / total) * 100 for h in holdings]
    hhi = round(sum(w**2 for w in weights), 0)

    # --- Score: 0-100, lower HHI = better ---
    # HHI ranges: 10000 (one holding) to ~100/n (perfectly equal)
    n = len(holdings)
    min_hhi = 10000 / n if n > 0 else 10000
    if n <= 1:
        score = 0
    else:
        score = max(
            0, min(100, round(100 * (1 - (hhi - min_hhi) / (10000 - min_hhi)), 0))
        )

    # --- Warnings (each is a tuple: (warning_text, fix_text)) ---
    warnings = []

    # Find under-represented sectors for suggestions
    all_known_sectors = {
        "Technology",
        "Financial Services",
        "Healthcare",
        "Consumer Defensive",
        "Energy",
        "Industrials",
        "Basic Materials",
        "Communication Services",
        "Consumer Cyclical",
        "Utilities",
        "Real Estate",
    }
    present_sectors = set(sector_pct.keys())
    missing_sectors = all_known_sectors - present_sectors
    suggest_sectors = (
        sorted(missing_sectors)[:3] if missing_sectors else ["IT", "Healthcare", "FMCG"]
    )

    for name, pct in holding_pcts:
        amt = next((h["amount"] for h in holdings if h["name"] == name), 0)
        if pct > 40:
            sell_amt = round(amt * (pct - 20) / pct)
            warnings.append(
                (
                    f"🔴 {name} is {pct}% of portfolio — extremely concentrated!",
                    f"Sell ~₹{sell_amt:,} of {name} to bring it down to ~20%. "
                    f"Spread that amount across 2-3 holdings in different sectors "
                    f"like {', '.join(suggest_sectors[:2])}. "
                    f"Or start a ₹{round(sell_amt / 3, -2):,.0f}/month SIP in a Nifty 50 index fund.",
                )
            )
        elif pct > 25:
            sell_amt = round(amt * (pct - 15) / pct)
            warnings.append(
                (
                    f"⚠️ {name} is {pct}% of portfolio — consider rebalancing",
                    f"Reduce {name} by ~₹{sell_amt:,} to bring it to ~15%. "
                    f"Consider moving that into sectors you don't own yet: "
                    f"{', '.join(suggest_sectors[:3])}.",
                )
            )

    for sector, pct in sector_pct.items():
        if pct > 50:
            warnings.append(
                (
                    f"🔴 {sector} sector is {pct}% — very concentrated!",
                    f"You have too much in {sector}. "
                    f"Add stocks or funds from other sectors like {', '.join(suggest_sectors[:3])} "
                    f"to reduce this below 30%.",
                )
            )
        elif pct > 35:
            warnings.append(
                (
                    f"⚠️ {sector} sector is {pct}% — consider diversifying",
                    f"Your {sector} exposure is high. "
                    f"Next time you invest, pick from sectors like {', '.join(suggest_sectors[:2])} instead.",
                )
            )

    if len(holdings) < 5:
        warnings.append(
            (
                "💡 Only {0} holdings — consider adding more for diversification".format(
                    len(holdings)
                ),
                f"Aim for 10-15 holdings across different sectors. "
                f"Consider adding stocks from {', '.join(suggest_sectors[:3])} "
                f"or a diversified mutual fund.",
            )
        )

    if "mutual_fund" not in type_alloc and "stock" in type_alloc:
        warnings.append(
            (
                "💡 No mutual funds — consider adding index funds for stability",
                "Start a monthly SIP in a Nifty 50 index fund (e.g. UTI Nifty 50) "
                "for ₹500-1,000/month. Index funds give broad market exposure with low fees.",
            )
        )

    stock_pct = type_pct.get("stock", 0)
    if stock_pct > 80:
        warnings.append(
            (
                "⚠️ {0}% in direct stocks — high risk, consider adding MFs or debt".format(
                    stock_pct
                ),
                f"Move 20-30% of your portfolio to mutual funds or fixed deposits. "
                f"A Nifty 50 SIP or a balanced advantage fund can reduce your risk.",
            )
        )

    return {
        "type_pct": type_pct,
        "sector_pct": sector_pct,
        "holding_pcts": holding_pcts,
        "hhi": hhi,
        "score": score,
        "warnings": warnings,
    }
