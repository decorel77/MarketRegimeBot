"""Tests for core/volatility_classifier.py."""

import math
import unittest

from core.volatility_classifier import (
    VOL_HIGH_MIN,
    VOL_LOW_MAX,
    VolatilityResult,
    classify_volatility,
)


class TestLowVol(unittest.TestCase):
    def test_zero_score_is_low_vol(self):
        r = classify_volatility(0.0)
        self.assertEqual(r.volatility_env, "LOW_VOL")

    def test_score_below_threshold_is_low_vol(self):
        r = classify_volatility(VOL_LOW_MAX - 0.01)
        self.assertEqual(r.volatility_env, "LOW_VOL")

    def test_low_vol_confidence_is_int(self):
        r = classify_volatility(0.0)
        self.assertIsInstance(r.confidence, int)

    def test_low_vol_confidence_100_at_zero(self):
        r = classify_volatility(0.0)
        self.assertEqual(r.confidence, 100)

    def test_low_vol_confidence_drops_near_boundary(self):
        r_far = classify_volatility(0.0)
        r_near = classify_volatility(VOL_LOW_MAX - 0.01)
        self.assertGreater(r_far.confidence, r_near.confidence)


class TestNormal(unittest.TestCase):
    def test_midpoint_is_normal(self):
        mid = (VOL_LOW_MAX + VOL_HIGH_MIN) / 2.0
        r = classify_volatility(mid)
        self.assertEqual(r.volatility_env, "NORMAL")

    def test_at_low_boundary_is_normal(self):
        r = classify_volatility(VOL_LOW_MAX)
        self.assertEqual(r.volatility_env, "NORMAL")

    def test_just_below_high_boundary_is_normal(self):
        r = classify_volatility(VOL_HIGH_MIN - 0.001)
        self.assertEqual(r.volatility_env, "NORMAL")

    def test_normal_confidence_highest_at_midpoint(self):
        mid = (VOL_LOW_MAX + VOL_HIGH_MIN) / 2.0
        r_mid = classify_volatility(mid)
        r_edge = classify_volatility(VOL_LOW_MAX)
        self.assertGreaterEqual(r_mid.confidence, r_edge.confidence)


class TestHighVol(unittest.TestCase):
    def test_at_high_threshold_is_high_vol(self):
        r = classify_volatility(VOL_HIGH_MIN)
        self.assertEqual(r.volatility_env, "HIGH_VOL")

    def test_score_one_is_high_vol(self):
        r = classify_volatility(1.0)
        self.assertEqual(r.volatility_env, "HIGH_VOL")

    def test_high_vol_confidence_is_int(self):
        r = classify_volatility(1.0)
        self.assertIsInstance(r.confidence, int)

    def test_high_vol_confidence_higher_further_above_threshold(self):
        r_near = classify_volatility(VOL_HIGH_MIN)
        r_far = classify_volatility(1.0)
        self.assertGreaterEqual(r_far.confidence, r_near.confidence)


class TestUnknown(unittest.TestCase):
    def test_negative_score_is_unknown(self):
        r = classify_volatility(-0.1)
        self.assertEqual(r.volatility_env, "UNKNOWN")

    def test_above_one_is_unknown(self):
        r = classify_volatility(1.1)
        self.assertEqual(r.volatility_env, "UNKNOWN")

    def test_none_input_is_unknown(self):
        r = classify_volatility(None)
        self.assertEqual(r.volatility_env, "UNKNOWN")

    def test_string_input_is_unknown(self):
        r = classify_volatility("high")
        self.assertEqual(r.volatility_env, "UNKNOWN")

    def test_unknown_confidence_is_zero(self):
        r = classify_volatility(-0.5)
        self.assertEqual(r.confidence, 0)

    def test_bool_true_is_unknown_not_high_vol(self):
        # float(True) == 1.0 would otherwise classify as HIGH_VOL with full
        # confidence; a bool is not a real volatility score → fail closed.
        r = classify_volatility(True)
        self.assertEqual(r.volatility_env, "UNKNOWN")
        self.assertEqual(r.confidence, 0)

    def test_bool_false_is_unknown_not_low_vol(self):
        # float(False) == 0.0 would otherwise classify as LOW_VOL with full
        # confidence; a bool is not a real volatility score → fail closed.
        r = classify_volatility(False)
        self.assertEqual(r.volatility_env, "UNKNOWN")
        self.assertEqual(r.confidence, 0)

    def test_nan_score_is_unknown(self):
        r = classify_volatility(float("nan"))
        self.assertEqual(r.volatility_env, "UNKNOWN")

    def test_infinity_score_is_unknown(self):
        r = classify_volatility(float("inf"))
        self.assertEqual(r.volatility_env, "UNKNOWN")


class TestVolatilityResult(unittest.TestCase):
    def test_to_dict_has_required_keys(self):
        r = classify_volatility(0.5)
        d = r.to_dict()
        for key in ("volatility_env", "confidence", "vol_score", "reason", "schema_version"):
            with self.subTest(key=key):
                self.assertIn(key, d)

    def test_vol_score_preserved_in_result(self):
        r = classify_volatility(0.45)
        self.assertAlmostEqual(r.vol_score, 0.45, places=3)

    def test_result_is_frozen(self):
        r = classify_volatility(0.5)
        with self.assertRaises((AttributeError, TypeError)):
            r.volatility_env = "LOW_VOL"


class TestNoBrokerImports(unittest.TestCase):
    def test_no_broker_imports(self):
        import ast
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "core" / "volatility_classifier.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        broker_modules = {"ib_insync", "ibapi", "TWS"}
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        self.assertFalse(imports & broker_modules)


if __name__ == "__main__":
    unittest.main()
