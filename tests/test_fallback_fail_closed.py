"""QA-002: fallback regimes must be UNKNOWN, never plausible.

Before QA-002, any yfinance failure or synthetic fallback classified
``DRY_RUN_INPUTS`` (trend 0.8 / vol 0.2) into BULL/confidence 80 — flagged
``data_is_real: false``, but a believable fake value that was safe only while
every consumer forever checked the flag.

Now: only live market data (yfinance) and explicitly injected test inputs may
be classified. Every other source publishes UNKNOWN / confidence 0 /
risk UNKNOWN with the raw scores preserved under the diagnostic key
``fallback_inputs``.

No live network: yfinance is always mocked or bypassed here.
"""

import unittest

from core.regime_classifier import DRY_RUN_INPUTS, RegimeInput
from utils.regime_export_writer import build_regime_export
from workflow import regime_cycle
from workflow.regime_cycle import is_trusted_input_source

UNTRUSTED_SOURCES = (
    "synthetic_fallback",
    "yfinance_error",
    "NovaAllocationBot+NovaBotV2Options",
    "NovaAllocationBot",
    "NovaBotV2Options",
    "unknown",
)


def _failing_download(*args, **kwargs):
    raise RuntimeError("network down")


def _none_download(*args, **kwargs):
    return None


def _mock_yfinance_download(spy, qqq, vix):
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


class TrustRuleTests(unittest.TestCase):
    def test_yfinance_trusted(self):
        self.assertTrue(is_trusted_input_source("yfinance"))

    def test_explicit_trusted(self):
        self.assertTrue(is_trusted_input_source("explicit"))

    def test_fallback_sources_untrusted(self):
        for src in UNTRUSTED_SOURCES:
            with self.subTest(src=src):
                self.assertFalse(is_trusted_input_source(src))


class FallbackFailsClosedTests(unittest.TestCase):
    def _assert_unknown_shape(self, result):
        self.assertEqual(result["regime"], "UNKNOWN")
        self.assertEqual(result["confidence"], 0)
        self.assertEqual(result["risk_level"], "UNKNOWN")
        self.assertEqual(result["volatility_env"], "UNKNOWN")
        self.assertFalse(result["data_is_real"])

    def test_synthetic_fallback_fails_closed(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            use_market_data=False,
            use_snapshot_inputs=False,
        )
        self.assertEqual(result["input_source"], "synthetic_fallback")
        self._assert_unknown_shape(result)

    def test_yfinance_error_fails_closed(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            use_market_data=True,
            use_snapshot_inputs=False,
            _download_fn=_failing_download,
        )
        self.assertEqual(result["input_source"], "yfinance_error")
        self._assert_unknown_shape(result)

    def test_queue_manual_verification_command(self):
        # Exact invocation from the QA-002 verification step. Whichever
        # fallback path it lands on (yfinance_error or sibling snapshots),
        # the published regime must be UNKNOWN/0/not-real.
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            use_market_data=True,
            _download_fn=_none_download,
        )
        self._assert_unknown_shape(result)

    def test_fallback_inputs_preserved_as_diagnostics(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            use_market_data=False,
            use_snapshot_inputs=False,
        )
        diag = result["decision"]["fallback_inputs"]
        self.assertEqual(diag["trend_score"], DRY_RUN_INPUTS.trend_score)
        self.assertEqual(diag["volatility_score"], DRY_RUN_INPUTS.volatility_score)
        self.assertTrue(diag["synthetic_dry_run_inputs"])

    def test_fallback_export_is_unknown(self):
        # The TacticBot-facing export built from a fail-closed decision must
        # also be UNKNOWN — both artifacts come from the same decision.
        decision = regime_cycle._build_fallback_unknown_decision(
            DRY_RUN_INPUTS, "synthetic_fallback"
        )
        payload = build_regime_export(decision)
        self.assertEqual(payload["market_regime"], "UNKNOWN")
        self.assertEqual(payload["confidence"], 0)
        self.assertFalse(payload["data_is_real"])


class NoPlausibleFakeRegimeProofTests(unittest.TestCase):
    """DoD: no code path can emit a non-UNKNOWN regime with
    ``data_is_real: false`` except explicit-injection test mode."""

    def test_builder_forces_unknown_for_every_untrusted_source(self):
        # DRY_RUN_INPUTS would classify BULL/80 — prove the builder refuses
        # to classify it for any untrusted source label.
        for src in UNTRUSTED_SOURCES:
            with self.subTest(src=src):
                decision = regime_cycle._build_decision_from_inputs(
                    DRY_RUN_INPUTS, src
                )
                self.assertEqual(decision.market_regime, "UNKNOWN")
                self.assertEqual(decision.confidence, 0)
                self.assertEqual(decision.risk_level, "UNKNOWN")
                self.assertFalse(decision.data_is_real)

    def test_no_cycle_combination_emits_plausible_fake(self):
        # Sweep every non-explicit cycle entry combination that cannot reach
        # real data: whatever path input resolution takes, data_is_real False
        # must imply regime UNKNOWN.
        combos = [
            dict(use_market_data=False, use_snapshot_inputs=False),
            dict(use_market_data=False, use_snapshot_inputs=True),
            dict(use_market_data=True, use_snapshot_inputs=False,
                 _download_fn=_failing_download),
            dict(use_market_data=True, use_snapshot_inputs=True,
                 _download_fn=_failing_download),
            dict(use_market_data=True, use_snapshot_inputs=True,
                 _download_fn=_none_download),
        ]
        for combo in combos:
            with self.subTest(combo=str(combo)):
                result = regime_cycle.run_regime_cycle(
                    write_snapshot=False, write_export=False, **combo
                )
                self.assertFalse(result["data_is_real"])
                self.assertEqual(result["regime"], "UNKNOWN")
                self.assertEqual(result["confidence"], 0)

    def test_explicit_injection_is_the_only_exception(self):
        # Explicit test injection may still classify (documented exception):
        # the regime is computed but stays data_is_real False / explicit.
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            inputs=RegimeInput(
                trend_score=DRY_RUN_INPUTS.trend_score,
                volatility_score=DRY_RUN_INPUTS.volatility_score,
            ),
        )
        self.assertEqual(result["input_source"], "explicit")
        self.assertEqual(result["regime"], "BULL")
        self.assertFalse(result["data_is_real"])

    def test_real_yfinance_data_still_classifies(self):
        # Mocked-but-real-shaped yfinance data must keep classifying normally.
        closes = [100.0 + i for i in range(22)]
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            write_export=False,
            use_market_data=True,
            _download_fn=_mock_yfinance_download(closes, closes, 18.0),
        )
        self.assertEqual(result["input_source"], "yfinance")
        self.assertTrue(result["data_is_real"])
        self.assertNotEqual(result["regime"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
