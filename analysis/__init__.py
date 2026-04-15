"""Analysis engine — split into submodules for maintainability.

All public symbols are re-exported here so existing imports continue to work:
    from analysis import analyze_portfolio, compute_rsi, fetch_news, ...
"""

from analysis._technicals import *  # noqa: F401,F403
from analysis._core import *  # noqa: F401,F403
from analysis._data_sources import (  # noqa: F401
    fetch_price_data,
    get_data_source,
    is_data_stale,
    get_stale_symbols,
)

# Private names used by other modules (star-import skips _ prefixed names)
from analysis._core import (  # noqa: F401
    _is_month_paused,
    _aggregate_transactions,
    _cached_amfi_nav_file,
    _get_market_trend,
    _gold_inr_series,
    _analyze_ticker_impl,
    _simple_sentiment,
    _extract_summary,
    _NEWS_IMPACT_CATEGORIES,
    _load_learned_weights,
    _apply_learned_weights,
    _analyze_prediction_mistakes,
)
