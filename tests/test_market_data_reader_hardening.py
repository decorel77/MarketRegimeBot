"""Malformed-input hardening tests for market_data_reader pure helpers.

SAFE / synthetic: tests ONLY the pure helpers ``_finite_number``,
``_compute_trend_score`` and ``_compute_volatility_score`` with injected
in-memory values. It never calls ``read_market_regime_inputs`` and never imports
pandas / yfinance — so there is no live download, no scheduler, and no runtime
export.
"""
import unittest

from core.market_data_reader import (
    _VIX_HIGH,
    _VIX_LOW,
    _compute_trend_score,
    _compute_volatility_score,
    _finite_number,
)


class FiniteNumberTests(unittest.TestCase):
    def test_accepts_real_numbers(self):
        for good in (0, 1, -3, 5.0, 1e9, -2.5):
            with self.subTest(good=good):
                self.assertTrue(_finite_number(good))

    def test_rejects_bool_nan_inf_and_non_numbers(self):
        for bad in (True, False, float("nan"), float("inf"), float("-inf"),
                    "5", None, [5], {"v": 5}, complex(1, 0)):
            with self.subTest(bad=bad):
                self.assertFalse(_finite_number(bad))


class ComputeTrendScoreHardeningTests(unittest.TestCase):
    def test_non_mapping_prices_returns_none(self):
        for bad in (None, ["SPY"], "SPY", 5, (1, 2)):
            with self.subTest(bad=bad):
                self.assertIsNone(_compute_trend_score(bad))

    def test_non_sequence_close_series_returns_none(self):
        for bad in ({"SPY": 100.0}, {"SPY": None}, {"SPY": {"close": 1}}):
            with self.subTest(bad=bad):
                self.assertIsNone(_compute_trend_score(bad))

    def test_zero_or_negative_base_price_returns_none(self):
        # A zero base price would raise ZeroDivisionError without the guard.
        self.assertIsNone(_compute_trend_score({"SPY": [0.0, 105.0], "QQQ": [100.0, 105.0]}))
        self.assertIsNone(_compute_trend_score({"SPY": [-10.0, 105.0], "QQQ": [100.0, 105.0]}))

    def test_non_finite_elements_return_none(self):
        for bad_series in ([float("nan"), 105.0], [100.0, float("inf")], [True, 105.0]):
            with self.subTest(bad_series=bad_series):
                self.assertIsNone(
                    _compute_trend_score({"SPY": bad_series, "QQQ": [100.0, 105.0]})
                )

    def test_valid_prices_still_compute(self):
        score = _compute_trend_score({"SPY": [100.0, 105.0], "QQQ": [100.0, 108.0]})
        self.assertIsNotNone(score)
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)


class ComputeVolatilityScoreHardeningTests(unittest.TestCase):
    def test_malformed_vix_returns_none(self):
        for bad in (float("nan"), float("inf"), float("-inf"), None, "20", True, False):
            with self.subTest(bad=bad):
                self.assertIsNone(_compute_volatility_score(bad))

    def test_non_positive_vix_returns_none(self):
        for bad in (0.0, -1.0, -40.0):
            with self.subTest(bad=bad):
                self.assertIsNone(_compute_volatility_score(bad))

    def test_valid_vix_still_maps(self):
        self.assertEqual(0.0, _compute_volatility_score(_VIX_LOW))
        self.assertEqual(1.0, _compute_volatility_score(_VIX_HIGH))
        mid = (_VIX_LOW + _VIX_HIGH) / 2
        self.assertAlmostEqual(_compute_volatility_score(mid), 0.5, places=2)


if __name__ == "__main__":
    unittest.main()
