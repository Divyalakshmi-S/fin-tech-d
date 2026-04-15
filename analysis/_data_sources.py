"""
Multi-source market data fetcher with automatic fallback.

Priority order:
  1. yfinance (primary — covers stocks, indices, commodities, FX)
  2. NSE India direct (fallback for .NS stocks/indices)
  3. Local price cache (stale data with warning)

All callers should use `fetch_price_data()` instead of `yf.Ticker().history()`
to benefit from automatic failover.
"""

from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Price cache — last-resort fallback when all APIs fail
# ---------------------------------------------------------------------------

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_CACHE_FILE = os.path.join(_CACHE_DIR, "price_cache.json")


def _load_cache() -> dict:
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    tmp = _CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, default=str)
    os.replace(tmp, _CACHE_FILE)


def _update_cache(symbol: str, data: pd.DataFrame):
    """Cache the last closing price + timestamp."""
    if data is None or data.empty:
        return
    try:
        cache = _load_cache()
        last_close = float(data["Close"].iloc[-1])
        cache[symbol] = {
            "close": last_close,
            "date": str(data.index[-1]),
            "cached_at": datetime.now().isoformat(),
        }
        _save_cache(cache)
    except Exception:
        pass


def _load_cached_price(symbol: str) -> pd.DataFrame | None:
    """Load last-known price from cache. Returns single-row DataFrame or None."""
    cache = _load_cache()
    entry = cache.get(symbol)
    if not entry:
        return None
    try:
        idx = pd.DatetimeIndex([pd.Timestamp(entry["date"])])
        return pd.DataFrame(
            {
                "Open": [entry["close"]],
                "High": [entry["close"]],
                "Low": [entry["close"]],
                "Close": [entry["close"]],
                "Volume": [0],
            },
            index=idx,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Source 1: yfinance (primary)
# ---------------------------------------------------------------------------


def _fetch_yfinance(symbol: str, period: str = "1y") -> pd.DataFrame | None:
    """Fetch from Yahoo Finance via yfinance."""
    try:
        data = yf.Ticker(symbol).history(period=period)
        if data is not None and not data.empty:
            return data
    except Exception as e:
        logger.debug("yfinance failed for %s: %s", symbol, e)
    return None


# ---------------------------------------------------------------------------
# Source 2: NSE India direct (for .NS symbols)
# ---------------------------------------------------------------------------


def _fetch_nse_direct(nse_symbol: str, period: str = "1y") -> pd.DataFrame | None:
    """Fetch from NSE India using nsetools for current price,
    or jugaad-data for historical data."""
    # Try nsetools for current/recent price
    try:
        from nsetools import Nse

        nse = Nse()
        quote = nse.get_quote(nse_symbol)
        if quote:
            price = quote.get("lastPrice") or quote.get("closePrice")
            if price:
                idx = pd.DatetimeIndex([pd.Timestamp.now().normalize()])
                return pd.DataFrame(
                    {
                        "Open": [price],
                        "High": [quote.get("dayHigh", price)],
                        "Low": [quote.get("dayLow", price)],
                        "Close": [price],
                        "Volume": [quote.get("totalTradedVolume", 0)],
                    },
                    index=idx,
                )
    except ImportError:
        logger.debug("nsetools not installed, skipping NSE direct")
    except Exception as e:
        logger.debug("nsetools failed for %s: %s", nse_symbol, e)

    # Try jugaad-data for historical
    try:
        from jugaad_data.nse import stock_df

        period_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "5y": 1825}
        days = period_map.get(period, 365)
        end = datetime.now().date()
        start = end - timedelta(days=days)
        df = stock_df(symbol=nse_symbol, from_date=start, to_date=end)
        if df is not None and not df.empty:
            df = df.rename(
                columns={
                    "DATE": "Date",
                    "CLOSE": "Close",
                    "OPEN": "Open",
                    "HIGH": "High",
                    "LOW": "Low",
                    "VOLUME": "Volume",
                    "NO OF TRADES": "Volume",
                }
            )
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                if col not in df.columns:
                    df[col] = 0
            return df[["Open", "High", "Low", "Close", "Volume"]]
    except ImportError:
        logger.debug("jugaad-data not installed, skipping historical NSE")
    except Exception as e:
        logger.debug("jugaad-data failed for %s: %s", nse_symbol, e)

    return None


# ---------------------------------------------------------------------------
# Source 3: BSE India (for .BO symbols)
# ---------------------------------------------------------------------------


def _fetch_bse_direct(bse_code: str) -> pd.DataFrame | None:
    """Fetch from BSE India using bsedata for current price."""
    try:
        from bsedata.bse import BSE

        b = BSE()
        quote = b.getQuote(bse_code)
        if quote:
            price = float(quote.get("currentValue", "0").replace(",", ""))
            if price > 0:
                idx = pd.DatetimeIndex([pd.Timestamp.now().normalize()])
                return pd.DataFrame(
                    {
                        "Open": [price],
                        "High": [
                            float(quote.get("dayHigh", str(price)).replace(",", ""))
                        ],
                        "Low": [
                            float(quote.get("dayLow", str(price)).replace(",", ""))
                        ],
                        "Close": [price],
                        "Volume": [
                            int(quote.get("totalTradedQuantity", "0").replace(",", ""))
                        ],
                    },
                    index=idx,
                )
    except ImportError:
        logger.debug("bsedata not installed, skipping BSE direct")
    except Exception as e:
        logger.debug("bsedata failed for %s: %s", bse_code, e)
    return None


# ---------------------------------------------------------------------------
# Public API — unified fetcher with fallback chain
# ---------------------------------------------------------------------------

# Track data source used for transparency
_last_source: dict[str, str] = {}


def fetch_price_data(symbol: str, period: str = "1y") -> pd.DataFrame | None:
    """Fetch price data for a symbol with automatic multi-source fallback.

    Args:
        symbol: Ticker symbol (e.g., 'TCS.NS', 'GC=F', '^NSEI')
        period: yfinance-style period string ('1mo', '3mo', '6mo', '1y', '5y')

    Returns:
        DataFrame with OHLCV columns, or None if all sources fail.
        Use `get_data_source(symbol)` to check which source was used.
    """
    # 1. yfinance (primary)
    data = _fetch_yfinance(symbol, period)
    if data is not None and not data.empty:
        _last_source[symbol] = "yfinance"
        _update_cache(symbol, data)
        return data

    # 2. NSE direct fallback (for .NS symbols)
    if symbol.endswith(".NS"):
        nse_symbol = symbol.replace(".NS", "")
        data = _fetch_nse_direct(nse_symbol, period)
        if data is not None and not data.empty:
            _last_source[symbol] = "nse_direct"
            _update_cache(symbol, data)
            return data

    # 3. BSE direct fallback (for .BO symbols)
    if symbol.endswith(".BO"):
        bse_code = symbol.replace(".BO", "")
        data = _fetch_bse_direct(bse_code)
        if data is not None and not data.empty:
            _last_source[symbol] = "bse_direct"
            _update_cache(symbol, data)
            return data

    # 4. Cache fallback (stale data)
    data = _load_cached_price(symbol)
    if data is not None:
        _last_source[symbol] = "cache"
        logger.warning("Using cached price for %s — live data unavailable", symbol)
        return data

    _last_source[symbol] = "none"
    return None


def get_data_source(symbol: str) -> str:
    """Return which data source was last used for a symbol.
    One of: 'yfinance', 'nse_direct', 'bse_direct', 'cache', 'none'.
    """
    return _last_source.get(symbol, "unknown")


def is_data_stale(symbol: str) -> bool:
    """Check if data for a symbol came from cache (potentially stale)."""
    return _last_source.get(symbol) == "cache"


def get_stale_symbols() -> list[str]:
    """Return list of symbols currently served from stale cache."""
    return [s for s, src in _last_source.items() if src == "cache"]
