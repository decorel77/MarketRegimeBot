"""Tests for workflow/regime_cycle.py — Phase 2 snapshot and safety, Phase 3 market data."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from core.regime_classifier import RegimeInput
from workflow import regime_cycle


class SnapshotGenerationTests(unittest.TestCase):
    def test_dry_run_writes_only_own_snapshot(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        result_path = Path(result["result_snapshot_path"]).resolve()
        self.assertEqual(result_path, regime_cycle.RESULT_SNAPSHOT_PATH.resolve())

    def test_snapshot_contains_required_fields(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        for field in ("project", "status", "market_regime", "confidence", "risk_level", "reason", "dry_run"):
            with self.subTest(field=field):
                self.assertIn(field, payload)

    def test_snapshot_project_is_market_regime_bot(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["project"], "MarketRegimeBot")

    def test_snapshot_status_safe_dry_run(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_REGIME")

    def test_snapshot_dry_run_true(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertTrue(payload["dry_run"])

    def test_snapshot_reason_is_list(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertIsInstance(payload["reason"], list)

    def test_default_synthetic_inputs_fail_closed_to_unknown(self):
        # QA-002: DRY_RUN_INPUTS (trend=0.8, vol=0.2) would classify as BULL,
        # but a synthetic fallback source must never publish a plausible fake
        # regime — it fails closed to UNKNOWN/confidence 0.
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            use_market_data=False,
            use_snapshot_inputs=False,
        )
        self.assertEqual(result["regime"], "UNKNOWN")
        self.assertEqual(result["confidence"], 0)
        self.assertFalse(result["data_is_real"])

    def test_custom_bear_inputs(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=-0.8, volatility_score=0.3),
        )
        self.assertEqual(result["regime"], "BEAR")

    def test_custom_sideways_inputs(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=0.1, volatility_score=0.2),
        )
        self.assertEqual(result["regime"], "SIDEWAYS")

    def test_custom_high_volatility_inputs(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=0.0, volatility_score=0.9),
        )
        self.assertEqual(result["regime"], "HIGH_VOLATILITY")


class DryRunSafetyTests(unittest.TestCase):
    def test_write_result_refuses_outside_project(self):
        from core.regime_contracts import build_unknown_regime_decision
        decision = build_unknown_regime_decision()
        outside_path = Path(tempfile.gettempdir()) / "market_regime_outside.json"
        with self.assertRaises(ValueError):
            regime_cycle.write_result_snapshot(decision, outside_path)

    def test_no_broker_order_trading_modules_imported(self):
        regime_cycle.run_regime_cycle(write_snapshot=False)
        forbidden = ("broker", "order", "trading")
        bad = [
            name for name in sys.modules
            if any(f in name.lower() for f in forbidden)
            and not name.startswith(("unittest", "test"))
            and "regime" not in name.lower()
        ]
        self.assertEqual(bad, [])

    def test_result_always_dry_run_true(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=False)
        self.assertTrue(result["dry_run"])

    def test_confidence_in_bounds(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=False)
        self.assertGreaterEqual(result["confidence"], 0)
        self.assertLessEqual(result["confidence"], 100)


class Phase3MarketDataTests(unittest.TestCase):
    """Phase 3: verify volatility_env field and _download_fn injection."""

    def _make_mock_download(self, spy_closes, qqq_closes, vix_close):
        """Return a callable that mimics yfinance.download for tests."""
        import pandas as pd

        spy = spy_closes
        qqq = qqq_closes

        def mock_download(tickers, **kwargs):
            if isinstance(tickers, str):
                # VIX single-ticker call
                idx = pd.date_range("2026-01-01", periods=len([vix_close]), freq="B")
                df = pd.DataFrame({"Close": [vix_close]}, index=idx)
                return df
            # Multi-ticker call: SPY + QQQ
            n = max(len(spy), len(qqq))
            idx = pd.date_range("2026-01-01", periods=n, freq="B")
            cols = pd.MultiIndex.from_arrays(
                [["Close", "Close"], ["QQQ", "SPY"]],
                names=["Price", "Ticker"],
            )
            data = {("Close", "SPY"): spy[:n], ("Close", "QQQ"): qqq[:n]}
            df = pd.DataFrame(data, index=idx[:n])
            df.columns = pd.MultiIndex.from_tuples(
                list(data.keys()), names=["Price", "Ticker"]
            )
            return df

        return mock_download

    def test_result_contains_volatility_env(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=0.6, volatility_score=0.2),
        )
        self.assertIn("volatility_env", result)

    def test_low_vol_score_produces_low_vol_env(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=0.6, volatility_score=0.1),
        )
        self.assertEqual(result["volatility_env"], "LOW_VOL")

    def test_mid_vol_score_produces_normal_env(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=0.6, volatility_score=0.45),
        )
        self.assertEqual(result["volatility_env"], "NORMAL")

    def test_high_vol_score_produces_high_vol_env(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=0.0, volatility_score=0.8),
        )
        self.assertEqual(result["volatility_env"], "HIGH_VOL")

    def test_input_source_in_result(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=0.6, volatility_score=0.2),
        )
        self.assertIn("input_source", result)
        self.assertEqual(result["input_source"], "explicit")

    def test_snapshot_contains_volatility_env(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=True,
            inputs=RegimeInput(trend_score=0.6, volatility_score=0.2),
        )
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertIn("volatility_env", payload)

    def test_snapshot_contains_input_source(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=True,
            inputs=RegimeInput(trend_score=0.6, volatility_score=0.2),
        )
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertIn("input_source", payload)

    def test_download_fn_injection_produces_yfinance_source(self):
        closes = [100.0 + i for i in range(22)]
        mock_fn = self._make_mock_download(closes, closes, 18.0)
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            use_market_data=True,
            _download_fn=mock_fn,
        )
        self.assertEqual(result["input_source"], "yfinance")

    def test_download_fn_injection_produces_valid_regime(self):
        closes = [100.0 + i for i in range(22)]
        mock_fn = self._make_mock_download(closes, closes, 18.0)
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            use_market_data=True,
            _download_fn=mock_fn,
        )
        from core.regime_contracts import VALID_REGIMES
        self.assertIn(result["regime"], VALID_REGIMES)

    def test_market_data_failure_falls_back_to_snapshot_adapter(self):
        def failing_download(*a, **kw):
            raise RuntimeError("network error")

        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            use_market_data=True,
            _download_fn=failing_download,
        )
        # Falls back gracefully — should not raise
        self.assertIn("regime", result)

    def test_use_market_data_false_skips_yfinance(self):
        called = []

        def spy_fn(*a, **kw):
            called.append(1)
            raise RuntimeError("should not be called")

        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            use_market_data=False,
            _download_fn=spy_fn,
        )
        # _download_fn only used when use_market_data=True
        self.assertEqual(called, [])
        self.assertIn("regime", result)


if __name__ == "__main__":
    unittest.main()
