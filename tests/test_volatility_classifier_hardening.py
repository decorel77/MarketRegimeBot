"""Malformed-input hardening tests for core/volatility_classifier.

SAFE / synthetic: pure in-memory calls to ``classify_volatility``. No IO, no
download, no scheduler, no runtime export. Locks the strict real-number type
gate so numeric strings and other non-real-number types fail closed to UNKNOWN
instead of producing a fabricated, confident classification.
"""
import unittest
from decimal import Decimal

from core.volatility_classifier import classify_volatility


class VolatilityClassifierHardeningTests(unittest.TestCase):
    def test_numeric_string_is_unknown_not_classified(self):
        # The core regression: "0.5" must NOT become a confident NORMAL result.
        for bad in ("0.5", "1.0", "0", "0.85", " 0.5 "):
            with self.subTest(bad=bad):
                r = classify_volatility(bad)
                self.assertEqual("UNKNOWN", r.volatility_env)
                self.assertEqual(0, r.confidence)

    def test_container_inputs_are_unknown(self):
        for bad in ([0.5], (0.5,), {"score": 0.5}, {0.5}):
            with self.subTest(bad=bad):
                r = classify_volatility(bad)
                self.assertEqual("UNKNOWN", r.volatility_env)

    def test_decimal_and_complex_are_unknown(self):
        for bad in (Decimal("0.5"), complex(0.5, 0), bytearray(b"0.5")):
            with self.subTest(bad=bad):
                r = classify_volatility(bad)
                self.assertEqual("UNKNOWN", r.volatility_env)

    def test_bool_and_nan_and_inf_remain_unknown(self):
        for bad in (True, False, float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad=bad):
                self.assertEqual("UNKNOWN", classify_volatility(bad).volatility_env)

    def test_genuine_floats_still_classify(self):
        self.assertEqual("LOW_VOL", classify_volatility(0.0).volatility_env)
        self.assertEqual("NORMAL", classify_volatility(0.45).volatility_env)
        self.assertEqual("HIGH_VOL", classify_volatility(1.0).volatility_env)

    def test_genuine_ints_still_classify(self):
        self.assertEqual("LOW_VOL", classify_volatility(0).volatility_env)
        self.assertEqual("HIGH_VOL", classify_volatility(1).volatility_env)


if __name__ == "__main__":
    unittest.main()
