"""Consolidated fail-closed regression contract for the pure regime classifiers.

A single tripwire over the three pure, broker-free classifiers — it pins the
fail-closed discipline so a future change cannot let a malformed input produce a
confident classification:

* ``classify_volatility`` → ``UNKNOWN`` (never raises) for every non-real /
  out-of-range score;
* ``classify_risk`` → ``UNKNOWN`` (never raises) for every malformed signal set;
* ``RegimeInput.validate`` → raises ``ValueError`` for every non-real /
  out-of-range score (the strict input gate), and a valid input classifies to a
  known regime with a 0–100 confidence.

Hermeticity: imports only the pure ``core`` classifiers + stdlib. No broker, no
network, no I/O, no runtime read/write. Broker-free under
``python -S -m unittest tests.test_regime_failclosed_contract``.
"""
from __future__ import annotations

import math
import unittest

from core.volatility_classifier import classify_volatility
from core.risk_classifier import RISK_ON, RISK_OFF, UNKNOWN, classify_risk
from core.regime_classifier import RegimeInput, classify_regime

# A battery of values that must never yield a confident classification.
_BAD_SCALARS = (None, "x", True, False, float("nan"), float("inf"), float("-inf"),
                [], {}, object())
_OUT_OF_RANGE_VOL = (-0.1, 1.1, -1.0, 2.0)
_KNOWN_REGIMES = {"HIGH_VOLATILITY", "BULL", "BEAR", "SIDEWAYS", "UNKNOWN"}


class VolatilityFailClosedTest(unittest.TestCase):
    def test_bad_scalars_are_unknown(self) -> None:
        for v in _BAD_SCALARS + _OUT_OF_RANGE_VOL:
            with self.subTest(value=v):
                self.assertEqual(classify_volatility(v).volatility_env, "UNKNOWN")

    def test_valid_score_is_known(self) -> None:
        self.assertIn(classify_volatility(0.5).volatility_env,
                      {"LOW_VOL", "NORMAL", "HIGH_VOL"})


class RiskFailClosedTest(unittest.TestCase):
    def test_malformed_signals_are_unknown(self) -> None:
        for signals in (None, {}, "x", [], 123, {"regime": "NOPE"},
                        {"regime": "BULL"}):  # missing required fields
            with self.subTest(signals=signals):
                result = classify_risk(signals)
                self.assertEqual(result.label, UNKNOWN)

    def test_label_is_always_in_contract(self) -> None:
        self.assertIn(classify_risk(None).label, {RISK_ON, RISK_OFF, UNKNOWN})


class RegimeInputGateTest(unittest.TestCase):
    def test_bad_inputs_raise_on_validate(self) -> None:
        for bad in _BAD_SCALARS + (-2.0, 2.0):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    RegimeInput(trend_score=bad, volatility_score=0.5).validate()
                with self.assertRaises(ValueError):
                    RegimeInput(trend_score=0.0, volatility_score=bad).validate()

    def test_valid_input_classifies_to_known_regime(self) -> None:
        for trend, vol in ((0.9, 0.2), (-0.9, 0.2), (0.0, 0.05), (0.1, 0.95)):
            with self.subTest(trend=trend, vol=vol):
                inp = RegimeInput(trend_score=trend, volatility_score=vol)
                inp_valid = inp.validate() or inp  # validate() returns None
                result = classify_regime(inp)
                self.assertIn(result.market_regime, _KNOWN_REGIMES)
                self.assertTrue(0 <= result.confidence <= 100)
                self.assertTrue(math.isfinite(result.confidence))


if __name__ == "__main__":
    unittest.main()
