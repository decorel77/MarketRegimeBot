"""Tests for the hard-stop persistence / recovery-lag study (REGIME-TRUST-003).

Research/reporting only; pins the synthetic invariants and the report's
research-only markers. No real data, no threshold change, writes nothing. Imports
only the pure classifier + the REGIME-TRUST-002 harness, so it runs under the
broker-free pandas pytest venv (and under plain -S).
"""
from __future__ import annotations

import unittest

from research.regime_hard_stop_persistence import (
    REPORT_SCHEMA_VERSION,
    boundary_false_stop,
    causal_moving_average,
    measure_recovery_lag,
    run_persistence_study,
    step_recovery_trend,
)


class SmoothingTest(unittest.TestCase):
    def test_window_one_is_identity(self) -> None:
        self.assertEqual(causal_moving_average([1.0, 2.0, 3.0], 1), [1.0, 2.0, 3.0])

    def test_partial_window_at_start(self) -> None:
        # window=2: [1, (1+3)/2, (3+5)/2]
        self.assertEqual(causal_moving_average([1.0, 3.0, 5.0], 2), [1.0, 2.0, 4.0])

    def test_invalid_window_raises(self) -> None:
        with self.assertRaises(ValueError):
            causal_moving_average([1.0], 0)

    def test_step_trend_shape(self) -> None:
        s = step_recovery_trend(bear_level=-0.8, recovery_level=-0.3, pre_steps=3, post_steps=2)
        self.assertEqual(s, [-0.8, -0.8, -0.8, -0.3, -0.3])


class RecoveryLagTest(unittest.TestCase):
    def test_no_smoothing_recovers_instantly(self) -> None:
        r = measure_recovery_lag(window=1, recovery_level=-0.3)
        self.assertEqual(r.recovery_lag_steps, 0)
        self.assertFalse(r.persisted_to_end)
        self.assertTrue(r.true_is_recovery)

    def test_smoothing_introduces_lag(self) -> None:
        r5 = measure_recovery_lag(window=5, recovery_level=-0.3)
        r10 = measure_recovery_lag(window=10, recovery_level=-0.3)
        self.assertIsNotNone(r5.recovery_lag_steps)
        self.assertGreater(r5.recovery_lag_steps, 0)
        # A longer smoothing window cannot recover faster than a shorter one.
        self.assertGreaterEqual(r10.recovery_lag_steps, r5.recovery_lag_steps)

    def test_non_recovery_persists_and_is_flagged(self) -> None:
        # "recovery" still below the bear threshold is not a true recovery; the
        # hard-stop must persist to the end (fail-safe: never reports a recovery
        # that did not happen).
        r = measure_recovery_lag(window=5, recovery_level=-0.6)
        self.assertFalse(r.true_is_recovery)
        self.assertTrue(r.persisted_to_end)
        self.assertIsNone(r.recovery_lag_steps)


class BoundaryFalseStopTest(unittest.TestCase):
    def test_benign_center_yields_false_stops_across_boundary(self) -> None:
        b = boundary_false_stop(center=-0.45, half_width=0.1, points=21)
        self.assertFalse(b.true_hard_stop)          # centre is benign (SIDEWAYS)
        self.assertIsNotNone(b.false_hard_stop_rate)
        self.assertGreater(b.false_hard_stop_rate, 0.0)  # dips below -0.5 trip BEAR
        self.assertLess(b.false_hard_stop_rate, 1.0)

    def test_bear_center_has_no_false_rate(self) -> None:
        b = boundary_false_stop(center=-0.8, half_width=0.1, points=21)
        self.assertTrue(b.true_hard_stop)
        self.assertIsNone(b.false_hard_stop_rate)


class ReportTest(unittest.TestCase):
    def test_report_markers_and_shape(self) -> None:
        rep = run_persistence_study(generated_at="2026-06-30T00:00:00+00:00")
        self.assertEqual(rep["schema_version"], REPORT_SCHEMA_VERSION)
        self.assertTrue(rep["research_only"])
        self.assertTrue(rep["not_for_live_trading"])
        self.assertFalse(rep["data_is_real"])
        self.assertEqual(rep["thresholds"]["trend_bear_threshold"], -0.5)
        self.assertTrue(rep["recovery_lag"]["rows"])
        self.assertTrue(rep["boundary_false_stop"]["rows"])

    def test_report_is_byte_reproducible(self) -> None:
        a = run_persistence_study(generated_at="2026-06-30T00:00:00+00:00")
        b = run_persistence_study(generated_at="2026-06-30T00:00:00+00:00")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
