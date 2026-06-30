"""Tests for the hard-stop mis-classification sensitivity study (REGIME-TRUST-002).

Research/reporting only; pins the synthetic invariants and the report's
research-only markers. No real data, no threshold change, writes nothing.
Runs under the broker-free pandas pytest venv (and, since it imports only the
pure classifier, under plain -S as well).
"""
from __future__ import annotations

import unittest

from research.regime_hard_stop_sensitivity import (
    HARD_STOP_REGIMES,
    classify_state,
    lattice_offsets,
    run_sensitivity_study,
    sensitivity_at_state,
    triggers_hard_stop,
)


class HardStopPredicateTest(unittest.TestCase):
    def test_hard_stop_set_is_high_risk_regimes(self) -> None:
        self.assertEqual(HARD_STOP_REGIMES, frozenset({"HIGH_VOLATILITY", "BEAR"}))
        self.assertTrue(triggers_hard_stop("BEAR"))
        self.assertTrue(triggers_hard_stop("HIGH_VOLATILITY"))
        for benign in ("BULL", "SIDEWAYS", "UNKNOWN"):
            self.assertFalse(triggers_hard_stop(benign))

    def test_classify_state_clamps_out_of_domain(self) -> None:
        # Perturbation may push inputs out of range; classify must not raise.
        self.assertEqual(classify_state(2.0, -1.0), "BULL")
        self.assertEqual(classify_state(-2.0, 0.0), "BEAR")
        self.assertEqual(classify_state(0.0, 5.0), "HIGH_VOLATILITY")


class LatticeTest(unittest.TestCase):
    def test_lattice_includes_origin_and_is_square(self) -> None:
        offsets = lattice_offsets(2, 0.1)
        self.assertIn((0.0, 0.0), offsets)
        self.assertEqual(len(offsets), 25)  # (2*2+1)^2

    def test_lattice_rejects_bad_args(self) -> None:
        with self.assertRaises(ValueError):
            lattice_offsets(-1, 0.1)
        with self.assertRaises(ValueError):
            lattice_offsets(2, 0.0)


class SensitivityTest(unittest.TestCase):
    def test_clear_bull_has_no_false_hard_stop_under_small_noise(self) -> None:
        s = sensitivity_at_state(0.9, 0.1, lattice_offsets(2, 0.05))
        self.assertFalse(s.true_hard_stop)
        self.assertEqual(s.hard_stop_samples, 0)  # never mis-stopped
        self.assertEqual(s.flip_rate, 0.0)

    def test_clear_bear_is_hard_stop_and_robust_to_small_noise(self) -> None:
        s = sensitivity_at_state(-0.9, 0.1, lattice_offsets(2, 0.05))
        self.assertTrue(s.true_hard_stop)
        # deep bear: small noise never reaches the -0.5 bear / 0.7 vol boundary
        self.assertEqual(s.hard_stop_samples, s.samples)
        self.assertEqual(s.flip_rate, 0.0)

    def test_near_boundary_benign_state_can_false_hard_stop(self) -> None:
        # Just on the benign side of the bear threshold (t=-0.45): enough noise
        # crosses into BEAR -> a non-zero false hard-stop is detectable.
        s = sensitivity_at_state(-0.45, 0.1, lattice_offsets(3, 0.05))
        self.assertFalse(s.true_hard_stop)
        self.assertGreater(s.hard_stop_samples, 0)

    def test_determinism(self) -> None:
        a = sensitivity_at_state(-0.45, 0.1, lattice_offsets(3, 0.05))
        b = sensitivity_at_state(-0.45, 0.1, lattice_offsets(3, 0.05))
        self.assertEqual(a, b)


class StudyReportTest(unittest.TestCase):
    def _study(self):
        return run_sensitivity_study(
            trend_grid=[-0.9, -0.45, 0.0, 0.45, 0.9],
            vol_grid=[0.1, 0.5, 0.65, 0.8],
            noise_levels=[0.0, 0.05, 0.1, 0.2],
            generated_at="2026-06-30T00:00:00+00:00",
        )

    def test_report_carries_research_markers(self) -> None:
        r = self._study()
        self.assertTrue(r["research_only"])
        self.assertTrue(r["not_for_live_trading"])
        self.assertIs(r["data_is_real"], False)

    def test_zero_noise_has_zero_error_rates(self) -> None:
        r = self._study()
        zero = next(b for b in r["by_noise_level"] if b["noise_level"] == 0.0)
        self.assertEqual(zero["false_hard_stop_rate"], 0.0)
        self.assertEqual(zero["missed_hard_stop_rate"], 0.0)

    def test_false_hard_stop_rate_nondecreasing_in_noise(self) -> None:
        # More measurement noise can only add, never remove, threshold crossings
        # pooled over the symmetric lattice -> rate is non-decreasing.
        r = self._study()
        rates = [b["false_hard_stop_rate"] for b in r["by_noise_level"]]
        for lo, hi in zip(rates, rates[1:]):
            self.assertLessEqual(lo, hi + 1e-9)

    def test_missed_hard_stop_rate_is_reported(self) -> None:
        r = self._study()
        for b in r["by_noise_level"]:
            self.assertIsNotNone(b["missed_hard_stop_rate"])
            self.assertGreaterEqual(b["missed_hard_stop_rate"], 0.0)

    def test_determinism_of_report(self) -> None:
        self.assertEqual(self._study(), self._study())

    def test_rejects_empty_grids(self) -> None:
        with self.assertRaises(ValueError):
            run_sensitivity_study(trend_grid=[], vol_grid=[0.1], noise_levels=[0.0])


if __name__ == "__main__":
    unittest.main()
