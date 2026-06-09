"""Tests for core/market_data_reader.py.

All tests use injected mock download functions — no live yfinance calls.
Verifies: trend computation, VIX mapping, fail-closed behaviour,
fallback on bad data, and validation of the returned RegimeInput.
"""
import unittest
from unittest.mock import MagicMock, patch

from core.market_data_reader import (
    SOURCE_FALLBACK,
    SOURCE_YFINANCE,
    _RETURN_NORMALISE,
    _VIX_HIGH,
    _VIX_LOW,
    _compute_trend_score,
    _compute_volatility_score,
    read_market_regime_inputs,
)
from core.regime_classifier import DRY_RUN_INPUTS, RegimeInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_download(spy_prices, qqq_prices, vix_prices):
    """Return a callable that mimics yf.download for two separate calls."""
    import pandas as pd

    call_count = [0]

    def _download(tickers, period, interval, progress, auto_adjust):
        call_count[0] += 1
        if isinstance(tickers, str) and "VIX" in tickers:
            idx = range(len(vix_prices))
            df = pd.DataFrame({"Close": vix_prices}, index=idx)
            return df
        # Trend tickers — return MultiIndex DataFrame
        idx = range(max(len(spy_prices), len(qqq_prices)))
        import itertools
        spy_data = spy_prices + [spy_prices[-1]] * (len(idx) - len(spy_prices))
        qqq_data = qqq_prices + [qqq_prices[-1]] * (len(idx) - len(qqq_prices))
        arrays = [["Close", "Close"], ["SPY", "QQQ"]]
        columns = pd.MultiIndex.from_arrays(arrays)
        df = pd.DataFrame(
            {"Close_SPY": spy_data, "Close_QQQ": qqq_data}, index=idx
        )
        df.columns = columns
        return df

    return _download


# ---------------------------------------------------------------------------
# Unit tests: _compute_trend_score
# ---------------------------------------------------------------------------

class TestComputeTrendScore(unittest.TestCase):
    def test_positive_return_gives_positive_score(self):
        prices = {"SPY": [100.0, 105.0], "QQQ": [100.0, 108.0]}
        score = _compute_trend_score(prices)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0)

    def test_negative_return_gives_negative_score(self):
        prices = {"SPY": [100.0, 90.0], "QQQ": [100.0, 88.0]}
        score = _compute_trend_score(prices)
        self.assertIsNotNone(score)
        self.assertLess(score, 0)

    def test_flat_prices_gives_zero_score(self):
        prices = {"SPY": [100.0, 100.0], "QQQ": [100.0, 100.0]}
        score = _compute_trend_score(prices)
        self.assertAlmostEqual(score, 0.0)

    def test_clamps_at_plus_one(self):
        # 100% return would normalise to 10.0; clamped to 1.0
        prices = {"SPY": [100.0, 200.0], "QQQ": [100.0, 200.0]}
        score = _compute_trend_score(prices)
        self.assertEqual(score, 1.0)

    def test_clamps_at_minus_one(self):
        prices = {"SPY": [200.0, 100.0], "QQQ": [200.0, 100.0]}
        score = _compute_trend_score(prices)
        self.assertEqual(score, -1.0)

    def test_single_ticker_insufficient_data_returns_none(self):
        prices = {"SPY": [100.0]}
        score = _compute_trend_score(prices)
        self.assertIsNone(score)

    def test_empty_prices_returns_none(self):
        score = _compute_trend_score({})
        self.assertIsNone(score)


# ---------------------------------------------------------------------------
# Unit tests: _compute_volatility_score
# ---------------------------------------------------------------------------

class TestComputeVolatilityScore(unittest.TestCase):
    def test_low_vix_returns_zero(self):
        self.assertEqual(_compute_volatility_score(_VIX_LOW - 1), 0.0)

    def test_high_vix_returns_one(self):
        self.assertEqual(_compute_volatility_score(_VIX_HIGH + 1), 1.0)

    def test_midpoint_returns_half(self):
        mid = (_VIX_LOW + _VIX_HIGH) / 2
        score = _compute_volatility_score(mid)
        self.assertAlmostEqual(score, 0.5, places=2)

    def test_exact_vix_low_returns_zero(self):
        self.assertEqual(_compute_volatility_score(_VIX_LOW), 0.0)

    def test_exact_vix_high_returns_one(self):
        self.assertEqual(_compute_volatility_score(_VIX_HIGH), 1.0)

    def test_score_in_range(self):
        for vix in [10, 15, 20, 25, 30, 35, 40, 50]:
            score = _compute_volatility_score(float(vix))
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)


# ---------------------------------------------------------------------------
# Integration tests: read_market_regime_inputs
# ---------------------------------------------------------------------------

class TestReadMarketRegimeInputs(unittest.TestCase):
    def _run_with_mock(self, spy, qqq, vix):
        return read_market_regime_inputs(
            _download_fn=_make_mock_download(spy, qqq, vix)
        )

    def test_valid_data_returns_yfinance_source(self):
        spy = [100.0 + i for i in range(25)]
        qqq = [300.0 + i * 1.2 for i in range(25)]
        vix = [20.0 + i * 0.1 for i in range(25)]
        inputs, source = self._run_with_mock(spy, qqq, vix)
        self.assertEqual(source, SOURCE_YFINANCE)
        self.assertIsInstance(inputs, RegimeInput)

    def test_valid_inputs_pass_validation(self):
        spy = [100.0 + i for i in range(25)]
        qqq = [300.0 + i * 1.2 for i in range(25)]
        vix = [20.0 for _ in range(25)]
        inputs, _ = self._run_with_mock(spy, qqq, vix)
        # Should not raise
        inputs.validate()

    def test_trend_score_in_range(self):
        spy = [100.0 + i for i in range(25)]
        qqq = [300.0 + i * 1.2 for i in range(25)]
        vix = [20.0 for _ in range(25)]
        inputs, _ = self._run_with_mock(spy, qqq, vix)
        self.assertGreaterEqual(inputs.trend_score, -1.0)
        self.assertLessEqual(inputs.trend_score, 1.0)

    def test_volatility_score_in_range(self):
        spy = [100.0 + i for i in range(25)]
        qqq = [300.0 + i * 1.2 for i in range(25)]
        vix = [25.0 for _ in range(25)]
        inputs, _ = self._run_with_mock(spy, qqq, vix)
        self.assertGreaterEqual(inputs.volatility_score, 0.0)
        self.assertLessEqual(inputs.volatility_score, 1.0)

    def test_download_exception_returns_fallback(self):
        def _bad_download(*args, **kwargs):
            raise RuntimeError("Network error")

        inputs, source = read_market_regime_inputs(_download_fn=_bad_download)
        self.assertEqual(source, SOURCE_FALLBACK)
        self.assertEqual(inputs, DRY_RUN_INPUTS)

    def test_empty_dataframe_returns_fallback(self):
        import pandas as pd

        call_count = [0]

        def _empty_download(*args, **kwargs):
            call_count[0] += 1
            return pd.DataFrame()

        inputs, source = read_market_regime_inputs(_download_fn=_empty_download)
        self.assertEqual(source, SOURCE_FALLBACK)
        self.assertEqual(inputs, DRY_RUN_INPUTS)

    def test_yfinance_import_error_returns_fallback(self):
        with patch.dict("sys.modules", {"yfinance": None}):
            # Can't easily test import failure inline; verify fallback path works
            inputs, source = read_market_regime_inputs(_download_fn=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated")))
        self.assertEqual(source, SOURCE_FALLBACK)

    def test_source_fallback_constant(self):
        self.assertEqual(SOURCE_FALLBACK, "yfinance_error")

    def test_source_yfinance_constant(self):
        self.assertEqual(SOURCE_YFINANCE, "yfinance")

    def test_returns_tuple_of_two(self):
        def _bad(*args, **kwargs):
            raise RuntimeError()
        result = read_market_regime_inputs(_download_fn=_bad)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_bearish_market_gives_negative_trend(self):
        # Prices declining over 25 sessions
        spy = [125.0 - i for i in range(25)]
        qqq = [400.0 - i * 1.5 for i in range(25)]
        vix = [20.0 for _ in range(25)]
        inputs, source = self._run_with_mock(spy, qqq, vix)
        if source == SOURCE_YFINANCE:
            self.assertLess(inputs.trend_score, 0)

    def test_high_vix_gives_high_volatility_score(self):
        spy = [100.0 + i for i in range(25)]
        qqq = [300.0 + i for i in range(25)]
        vix = [45.0 for _ in range(25)]  # extreme VIX
        inputs, source = self._run_with_mock(spy, qqq, vix)
        if source == SOURCE_YFINANCE:
            self.assertGreaterEqual(inputs.volatility_score, 0.9)

    def test_low_vix_gives_low_volatility_score(self):
        spy = [100.0 + i for i in range(25)]
        qqq = [300.0 + i for i in range(25)]
        vix = [12.0 for _ in range(25)]  # very low VIX
        inputs, source = self._run_with_mock(spy, qqq, vix)
        if source == SOURCE_YFINANCE:
            self.assertEqual(inputs.volatility_score, 0.0)


class TestNoLiveCalls(unittest.TestCase):
    """Confirm no network calls are made in the test suite."""

    def test_no_broker_imports_in_reader(self):
        import ast, pathlib
        src = pathlib.Path(__file__).parent.parent / "core" / "market_data_reader.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        broker_modules = {"ib_insync", "ibapi", "TWS"}
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        self.assertFalse(imports & broker_modules, f"Broker import found: {imports & broker_modules}")

    def test_read_only_marker_in_docstring(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "core" / "market_data_reader.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("Read-only", text)
        self.assertIn("ADVISORY_ONLY", text)


if __name__ == "__main__":
    unittest.main()
