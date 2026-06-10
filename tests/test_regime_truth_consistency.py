"""REPAIR-005: MarketRegimeBot fixture-to-live truth + two-output reconciliation.

Guards the three things REPAIR-005 fixed:

  1. ``result_snapshot.json`` and ``regime_export.json`` are built from a single
     ``RegimeDecision``, so they always agree (no more confidence 60 vs 80 drift).
  2. ``input_source`` truthfully names the data origin.
  3. ``data_is_real`` is True only for live market data (yfinance); every fixture/
     synthetic/snapshot-derived source leaves it False so consumers reject it.

No live network: yfinance is always mocked or bypassed here.
"""

import json
import unittest
from pathlib import Path

from core.market_data_reader import SOURCE_YFINANCE
from core.regime_classifier import RegimeInput
from core.regime_contracts import RegimeDecision, RegimeSafetyState
from utils.regime_export_writer import build_regime_export
from workflow import regime_cycle
from workflow.regime_cycle import is_real_market_data


def _mock_download(spy, qqq, vix):
    """Return a callable mimicking yfinance.download for SPY/QQQ + VIX."""
    import pandas as pd

    def download(tickers, **kwargs):
        if isinstance(tickers, str):  # single-ticker VIX call
            idx = pd.date_range("2026-01-01", periods=1, freq="B")
            return pd.DataFrame({"Close": [vix]}, index=idx)
        n = max(len(spy), len(qqq))
        idx = pd.date_range("2026-01-01", periods=n, freq="B")
        data = {("Close", "SPY"): spy[:n], ("Close", "QQQ"): qqq[:n]}
        df = pd.DataFrame(data, index=idx[:n])
        df.columns = pd.MultiIndex.from_tuples(
            list(data.keys()), names=["Price", "Ticker"]
        )
        return df

    return download


class RealnessRuleTests(unittest.TestCase):
    def test_yfinance_is_real(self):
        self.assertTrue(is_real_market_data(SOURCE_YFINANCE))

    def test_fixture_and_derived_sources_not_real(self):
        for src in (
            "explicit",
            "synthetic_fallback",
            "yfinance_error",
            "NovaAllocationBot+NovaBotV2Options",
            "unknown",
        ):
            with self.subTest(src=src):
                self.assertFalse(is_real_market_data(src))


class LiveDataMarksRealTests(unittest.TestCase):
    def test_yfinance_cycle_marks_data_real(self):
        closes = [100.0 + i for i in range(22)]
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            use_market_data=True,
            _download_fn=_mock_download(closes, closes, 18.0),
        )
        self.assertEqual(result["input_source"], "yfinance")
        self.assertTrue(result["data_is_real"])

    def test_explicit_inputs_not_real(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            inputs=RegimeInput(trend_score=0.6, volatility_score=0.2),
        )
        self.assertEqual(result["input_source"], "explicit")
        self.assertFalse(result["data_is_real"])

    def test_synthetic_fallback_not_real(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            use_market_data=False,
            use_snapshot_inputs=False,
        )
        self.assertEqual(result["input_source"], "synthetic_fallback")
        self.assertFalse(result["data_is_real"])

    def test_failed_yfinance_not_real(self):
        def failing(*a, **kw):
            raise RuntimeError("network down")

        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            use_market_data=True,
            use_snapshot_inputs=False,
            _download_fn=failing,
        )
        self.assertFalse(result["data_is_real"])


class TwoOutputReconciliationTests(unittest.TestCase):
    """Both outputs come from one decision, so every shared field agrees."""

    def _decision(self, **kw) -> RegimeDecision:
        defaults = dict(
            project="MarketRegimeBot",
            status="SAFE_DRY_RUN_REGIME",
            market_regime="SIDEWAYS",
            confidence=73,
            risk_level="LOW",
            safety=RegimeSafetyState(),
            reason=("range-bound",),
            volatility_env="LOW_VOL",
            input_source="yfinance",
            data_is_real=True,
        )
        defaults.update(kw)
        d = RegimeDecision(**defaults)
        d.validate()
        return d

    def test_snapshot_and_export_agree(self):
        d = self._decision()
        snap = d.to_dict()
        exp = build_regime_export(d)
        for field in ("confidence", "market_regime", "risk_level",
                      "volatility_env", "input_source", "data_is_real"):
            with self.subTest(field=field):
                self.assertEqual(snap[field], exp[field])

    def test_result_snapshot_contains_data_is_real(self):
        self.assertIn("data_is_real", self._decision().to_dict())

    def test_export_contains_data_is_real(self):
        self.assertIn("data_is_real", build_regime_export(self._decision()))

    def test_fixture_decision_marked_not_real(self):
        d = self._decision(input_source="explicit", data_is_real=False)
        self.assertFalse(d.to_dict()["data_is_real"])
        self.assertFalse(build_regime_export(d)["data_is_real"])


class OnDiskPairConsistencyTests(unittest.TestCase):
    """A single cycle call writes BOTH files from one decision, so the on-disk
    pair must agree (mirrors the queue verification command). Self-contained:
    writes a known pair and reads it straight back, independent of any ambient
    state other tests may have left on the shared artifact paths."""

    def test_cycle_writes_consistent_pair(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=True,
            write_export=True,
            inputs=RegimeInput(trend_score=0.6, volatility_score=0.2),
        )
        snap = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        exp = json.loads(
            Path(result["regime_export_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(snap["confidence"], exp["confidence"])
        self.assertEqual(snap["market_regime"], exp["market_regime"])
        self.assertEqual(snap["input_source"], exp["input_source"])
        self.assertEqual(snap["data_is_real"], exp["data_is_real"])
        # explicit (non-live) inputs must be flagged not-real
        self.assertEqual(snap["input_source"], "explicit")
        self.assertFalse(snap["data_is_real"])


if __name__ == "__main__":
    unittest.main()
