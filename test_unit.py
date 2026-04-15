"""Unit tests for pure functions and critical logic paths."""

import unittest
from analysis._technicals import (
    compute_rsi,
    rsi_signal,
    trend_signal,
    ma_crossover,
    compute_ema,
    compute_macd,
    compute_bollinger_bands,
    compute_atr,
    detect_candlestick_patterns,
    compute_stop_loss,
    position_size,
)


class TestRSI(unittest.TestCase):
    def test_rsi_none_when_insufficient_data(self):
        self.assertIsNone(compute_rsi([1, 2, 3], period=14))

    def test_rsi_all_gains(self):
        prices = list(range(1, 30))  # monotonically increasing
        result = compute_rsi(prices)
        self.assertEqual(result, 100.0)

    def test_rsi_returns_float(self):
        prices = [100 + i * (-1) ** i for i in range(30)]
        result = compute_rsi(prices)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, 100)


class TestRSISignal(unittest.TestCase):
    def test_none_input(self):
        self.assertEqual(rsi_signal(None), "N/A")

    def test_overbought(self):
        self.assertIn("Overbought", rsi_signal(75))

    def test_oversold(self):
        self.assertIn("Oversold", rsi_signal(25))

    def test_neutral(self):
        self.assertIn("Neutral", rsi_signal(50))


class TestTrendSignal(unittest.TestCase):
    def test_strong_uptrend(self):
        result = trend_signal(110, 105, 100)  # price > sma50 > sma200
        self.assertIn("Strong Uptrend", result)

    def test_strong_downtrend(self):
        result = trend_signal(90, 95, 100)  # price < sma50 < sma200
        self.assertIn("Strong Downtrend", result)

    def test_na_when_missing(self):
        self.assertEqual(trend_signal(100, None, None), "N/A")


class TestMACrossover(unittest.TestCase):
    def test_golden_cross(self):
        result = ma_crossover(95, 100, 101, 100)  # sma50 crosses above sma200
        self.assertIn("GOLDEN CROSS", result)

    def test_death_cross(self):
        result = ma_crossover(105, 100, 99, 100)  # sma50 crosses below sma200
        self.assertIn("DEATH CROSS", result)

    def test_no_crossover(self):
        self.assertIsNone(ma_crossover(105, 100, 106, 100))

    def test_none_inputs(self):
        self.assertIsNone(ma_crossover(None, 100, 101, 100))


class TestEMA(unittest.TestCase):
    def test_ema_insufficient_data(self):
        self.assertIsNone(compute_ema([1, 2], 5))

    def test_ema_returns_float(self):
        result = compute_ema(list(range(1, 20)), 5)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)


class TestMACD(unittest.TestCase):
    def test_macd_insufficient_data(self):
        self.assertIsNone(compute_macd(list(range(20))))

    def test_macd_sufficient_data(self):
        import numpy as np

        prices = np.sin(np.linspace(0, 10, 50)) * 10 + 100
        result = compute_macd(prices)
        self.assertIsNotNone(result)
        self.assertIn("macd", result)
        self.assertIn("signal", result)
        self.assertIn("histogram", result)


class TestBollingerBands(unittest.TestCase):
    def test_insufficient_data(self):
        self.assertIsNone(compute_bollinger_bands(list(range(10)), period=20))

    def test_returns_dict(self):
        import numpy as np

        prices = np.random.randn(30) * 5 + 100
        result = compute_bollinger_bands(prices)
        self.assertIsNotNone(result)
        self.assertIn("upper", result)
        self.assertIn("lower", result)
        self.assertIn("pct_b", result)
        self.assertGreater(result["upper"], result["lower"])


class TestATR(unittest.TestCase):
    def test_insufficient_data(self):
        self.assertIsNone(compute_atr([1], [1], [1]))

    def test_returns_float(self):
        import numpy as np

        n = 30
        highs = np.random.randn(n) * 2 + 105
        lows = np.random.randn(n) * 2 + 95
        closes = np.random.randn(n) * 2 + 100
        result = compute_atr(highs, lows, closes)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0)


class TestCandlestickPatterns(unittest.TestCase):
    def test_empty_for_short_data(self):
        self.assertEqual(detect_candlestick_patterns([1], [1], [1], [1]), [])

    def test_doji_detected(self):
        # Doji: open ≈ close, body is tiny relative to range
        opens = [100, 100, 100]
        highs = [110, 110, 110]
        lows = [90, 90, 90]
        closes = [100, 100, 100.5]  # very small body
        patterns = detect_candlestick_patterns(opens, highs, lows, closes)
        names = [p[0] for p in patterns]
        self.assertIn("Doji", names)


class TestStopLoss(unittest.TestCase):
    def test_atr_method(self):
        result = compute_stop_loss(100, 5, method="atr")
        self.assertEqual(result["stop_loss"], 90)  # 100 - 2*5
        self.assertGreater(result["target_1"], 100)
        self.assertGreater(result["target_2"], result["target_1"])

    def test_percent_method(self):
        result = compute_stop_loss(100, None, method="percent")
        self.assertEqual(result["stop_loss"], 95)


class TestPositionSize(unittest.TestCase):
    def test_basic(self):
        result = position_size(100000, 1, 500, 490)
        self.assertEqual(result["qty"], 100)  # risk 1000, risk/share 10 => 100 shares

    def test_zero_risk(self):
        result = position_size(100000, 1, 500, 500)
        self.assertEqual(result["qty"], 0)


class TestSanitize(unittest.TestCase):
    def test_sanitize_ticker(self):
        from analysis._core import sanitize_ticker

        self.assertEqual(sanitize_ticker("  reliance.ns  "), "RELIANCE.NS")
        self.assertEqual(sanitize_ticker("abc<script>"), "ABCSCRIPT")

    def test_sanitize_amount(self):
        from analysis._core import sanitize_amount

        self.assertEqual(sanitize_amount(500), 500)
        self.assertEqual(sanitize_amount(-100), 0)
        self.assertEqual(sanitize_amount(999999999), 100000000)

    def test_sanitize_text(self):
        from analysis._core import sanitize_text

        self.assertEqual(sanitize_text("  hello  "), "hello")
        long_text = "a" * 300
        self.assertEqual(len(sanitize_text(long_text, max_length=200)), 200)


class TestCalculators(unittest.TestCase):
    """Test the pure calculator functions from views/calculators.py."""

    def test_future_value_sip(self):
        from views.calculators import _future_value_sip

        # 10000/month for 12 months at 12% should give > 120000
        result = _future_value_sip(10000, 12, 12)
        self.assertGreater(result, 120000)

    def test_future_value_lumpsum(self):
        from views.calculators import _future_value_lumpsum

        # 100000 at 10% for 10 years
        result = _future_value_lumpsum(100000, 10, 10)
        self.assertAlmostEqual(result, 259374.25, delta=5)

    def test_required_sip(self):
        from views.calculators import _required_sip

        # Target 1 crore in 20 years at 12%
        result = _required_sip(10000000, 12, 20)
        self.assertGreater(result, 0)
        self.assertLess(result, 10000000)

    def test_inflation_adjusted(self):
        from views.calculators import _inflation_adjusted

        # 100 after 10 years at 6% inflation
        result = _inflation_adjusted(100, 6, 10)
        self.assertGreater(result, 100)


class TestTaxPlanning(unittest.TestCase):
    """Test the tax calculation functions."""

    def test_old_regime_no_tax_below_threshold(self):
        from views.tax_planning import _calc_old_regime_tax

        self.assertEqual(_calc_old_regime_tax(250000), 0)

    def test_old_regime_basic_tax(self):
        from views.tax_planning import _calc_old_regime_tax

        tax = _calc_old_regime_tax(1000000)
        self.assertGreater(tax, 0)

    def test_new_regime_rebate(self):
        from views.tax_planning import _calc_new_regime_tax

        # Income ≤ 12L gets rebate under new regime FY 2025-26
        tax = _calc_new_regime_tax(1200000)
        self.assertEqual(tax, 0)

    def test_new_regime_above_rebate(self):
        from views.tax_planning import _calc_new_regime_tax

        tax = _calc_new_regime_tax(2000000)
        self.assertGreater(tax, 0)


if __name__ == "__main__":
    unittest.main()
