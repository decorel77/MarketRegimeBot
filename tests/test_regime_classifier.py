"""Tests for core/regime_classifier.py — Phase 2 classification logic."""

import unittest

from core.regime_classifier import RegimeInput, classify_regime


class BullClassificationTests(unittest.TestCase):
    def test_strong_positive_trend_is_bull(self):
        result = classify_regime(RegimeInput(trend_score=0.8, volatility_score=0.2))
        self.assertEqual(result.market_regime, "BULL")

    def test_bull_confidence_matches_trend(self):
        result = classify_regime(RegimeInput(trend_score=0.8, volatility_score=0.2))
        self.assertEqual(result.confidence, 80)

    def test_bull_risk_level_normal(self):
        result = classify_regime(RegimeInput(trend_score=0.8, volatility_score=0.2))
        self.assertEqual(result.risk_level, "NORMAL")

    def test_bull_reason_non_empty(self):
        result = classify_regime(RegimeInput(trend_score=0.8, volatility_score=0.2))
        self.assertTrue(len(result.reason) > 0)

    def test_boundary_above_bull_threshold_is_bull(self):
        result = classify_regime(RegimeInput(trend_score=0.51, volatility_score=0.1))
        self.assertEqual(result.market_regime, "BULL")


class BearClassificationTests(unittest.TestCase):
    def test_strong_negative_trend_is_bear(self):
        result = classify_regime(RegimeInput(trend_score=-0.8, volatility_score=0.3))
        self.assertEqual(result.market_regime, "BEAR")

    def test_bear_confidence_from_abs_trend(self):
        result = classify_regime(RegimeInput(trend_score=-0.8, volatility_score=0.3))
        self.assertEqual(result.confidence, 80)

    def test_bear_risk_level_high(self):
        result = classify_regime(RegimeInput(trend_score=-0.8, volatility_score=0.3))
        self.assertEqual(result.risk_level, "HIGH")

    def test_bear_reason_non_empty(self):
        result = classify_regime(RegimeInput(trend_score=-0.8, volatility_score=0.3))
        self.assertTrue(len(result.reason) > 0)

    def test_boundary_below_bear_threshold_is_bear(self):
        result = classify_regime(RegimeInput(trend_score=-0.51, volatility_score=0.1))
        self.assertEqual(result.market_regime, "BEAR")


class SidewaysClassificationTests(unittest.TestCase):
    def test_low_trend_low_vol_is_sideways(self):
        result = classify_regime(RegimeInput(trend_score=0.1, volatility_score=0.2))
        self.assertEqual(result.market_regime, "SIDEWAYS")

    def test_sideways_risk_level_low(self):
        result = classify_regime(RegimeInput(trend_score=0.1, volatility_score=0.2))
        self.assertEqual(result.risk_level, "LOW")

    def test_sideways_reason_non_empty(self):
        result = classify_regime(RegimeInput(trend_score=0.1, volatility_score=0.2))
        self.assertTrue(len(result.reason) > 0)

    def test_flat_zero_scores_is_sideways(self):
        result = classify_regime(RegimeInput(trend_score=0.0, volatility_score=0.0))
        self.assertEqual(result.market_regime, "SIDEWAYS")

    def test_slightly_negative_low_vol_is_sideways(self):
        result = classify_regime(RegimeInput(trend_score=-0.1, volatility_score=0.2))
        self.assertEqual(result.market_regime, "SIDEWAYS")


class HighVolatilityClassificationTests(unittest.TestCase):
    def test_high_vol_is_high_volatility(self):
        result = classify_regime(RegimeInput(trend_score=0.0, volatility_score=0.9))
        self.assertEqual(result.market_regime, "HIGH_VOLATILITY")

    def test_high_vol_confidence_from_vol_score(self):
        result = classify_regime(RegimeInput(trend_score=0.0, volatility_score=0.9))
        self.assertEqual(result.confidence, 90)

    def test_high_vol_risk_level_high(self):
        result = classify_regime(RegimeInput(trend_score=0.0, volatility_score=0.9))
        self.assertEqual(result.risk_level, "HIGH")

    def test_high_vol_overrides_bull_trend(self):
        # Even with a bullish trend, extreme volatility takes priority
        result = classify_regime(RegimeInput(trend_score=0.8, volatility_score=0.9))
        self.assertEqual(result.market_regime, "HIGH_VOLATILITY")

    def test_boundary_just_above_vol_threshold(self):
        result = classify_regime(RegimeInput(trend_score=0.0, volatility_score=0.71))
        self.assertEqual(result.market_regime, "HIGH_VOLATILITY")


class ConfidenceBoundsTests(unittest.TestCase):
    def test_confidence_never_below_zero(self):
        for ts, vs in [(-1.0, 1.0), (0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]:
            with self.subTest(trend_score=ts, volatility_score=vs):
                result = classify_regime(RegimeInput(trend_score=ts, volatility_score=vs))
                self.assertGreaterEqual(result.confidence, 0)

    def test_confidence_never_above_100(self):
        for ts, vs in [(-1.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.5, 0.5)]:
            with self.subTest(trend_score=ts, volatility_score=vs):
                result = classify_regime(RegimeInput(trend_score=ts, volatility_score=vs))
                self.assertLessEqual(result.confidence, 100)

    def test_invalid_trend_score_raises(self):
        with self.assertRaises(ValueError):
            classify_regime(RegimeInput(trend_score=1.5, volatility_score=0.5))

    def test_invalid_volatility_score_raises(self):
        with self.assertRaises(ValueError):
            classify_regime(RegimeInput(trend_score=0.0, volatility_score=1.5))

    def test_negative_volatility_raises(self):
        with self.assertRaises(ValueError):
            classify_regime(RegimeInput(trend_score=0.0, volatility_score=-0.1))


if __name__ == "__main__":
    unittest.main()
