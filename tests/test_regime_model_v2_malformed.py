"""Malformed-input fail-closed tests for Regime Model v2 (research-stage, pure).

Separate unittest module (no pytest import) so it runs broker-free under
``python -S -m unittest``. compute_v2_inputs promises to return None on bad
data; these tests lock that it does so for a malformed container / element /
vix instead of raising, and that RegimeInputV2.validate rejects bool.
"""

from __future__ import annotations

import unittest

from core import regime_model_v2 as v2


def _good_window(n: int = 12) -> list[float]:
    return [100.0 + i for i in range(n)]


class ComputeV2InputsMalformedTests(unittest.TestCase):
    def test_non_sequence_series_returns_none(self):
        good = _good_window()
        for spy in (None, 5, 3.14, {"a": 1}):
            with self.subTest(spy=spy):
                self.assertIsNone(v2.compute_v2_inputs(spy, good, 20.0))
        for qqq in (None, 7, "string"):
            with self.subTest(qqq=qqq):
                # a string has a len() but its chars are non-numeric -> None
                self.assertIsNone(v2.compute_v2_inputs(good, qqq, 20.0))

    def test_non_numeric_element_returns_none(self):
        good = _good_window()
        self.assertIsNone(v2.compute_v2_inputs(["x"] * 12, good, 20.0))
        self.assertIsNone(v2.compute_v2_inputs([None] * 12, good, 20.0))

    def test_bool_element_returns_none(self):
        good = _good_window()
        self.assertIsNone(v2.compute_v2_inputs([True] * 12, good, 20.0))

    def test_non_finite_element_returns_none(self):
        good = _good_window()
        bad = _good_window()
        bad[-1] = float("nan")
        self.assertIsNone(v2.compute_v2_inputs(bad, good, 20.0))
        bad[-1] = float("inf")
        self.assertIsNone(v2.compute_v2_inputs(bad, good, 20.0))

    def test_malformed_vix_returns_none(self):
        good = _good_window()
        for vix in (None, "hi", True, float("nan"), float("inf"), 0.0, -5.0):
            with self.subTest(vix=vix):
                self.assertIsNone(v2.compute_v2_inputs(good, good, vix))

    def test_well_formed_inputs_still_compute(self):
        good = _good_window()
        result = v2.compute_v2_inputs(good, good, 20.0)
        self.assertIsNotNone(result)
        result.validate()  # must not raise


class RegimeInputV2ValidateTests(unittest.TestCase):
    def test_bool_factor_rejected(self):
        # True must not pass the [-1, 1] / [0, 1] bounds as 1.0.
        with self.assertRaises(ValueError):
            v2.RegimeInputV2(True, 0.5, 0.0, 0.0, 0.0).validate()

    def test_non_numeric_factor_rejected(self):
        with self.assertRaises(ValueError):
            v2.RegimeInputV2("0.5", 0.5, 0.0, 0.0, 0.0).validate()

    def test_non_finite_factor_rejected(self):
        with self.assertRaises(ValueError):
            v2.RegimeInputV2(float("nan"), 0.5, 0.0, 0.0, 0.0).validate()

    def test_well_formed_factors_accepted(self):
        v2.RegimeInputV2(0.5, 0.5, 0.2, -0.3, 0.1).validate()  # must not raise


if __name__ == "__main__":
    unittest.main()
