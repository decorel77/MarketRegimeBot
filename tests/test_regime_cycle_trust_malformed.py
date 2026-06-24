"""Malformed-input fail-closed tests for regime_cycle pure trust/realness path.

Separate unittest module (no pytest import, no snapshot/export write) so it runs
broker-free under ``python -S -m unittest``. Pins that a malformed (non-string)
input_source fails closed to *untrusted* / *not real* — never raising and never
treating an unexpected type as live data. Uses only pure, no-write helpers:
``is_real_market_data`` / ``is_trusted_input_source`` (string comparisons) and
``_build_decision_from_inputs`` (builds + validates a decision, writes nothing).
"""

from __future__ import annotations

import unittest

from core.regime_classifier import DRY_RUN_INPUTS
from workflow import regime_cycle
from workflow.regime_cycle import is_real_market_data, is_trusted_input_source

# Non-string / malformed sources that must never be trusted or treated as real.
MALFORMED_SOURCES = (None, 0, 1, True, False, 3.14, [], {}, ("yfinance",))


class TrustRealnessMalformedSourceTests(unittest.TestCase):
    def test_non_string_source_never_trusted(self):
        for src in MALFORMED_SOURCES:
            with self.subTest(src=src):
                self.assertFalse(is_trusted_input_source(src))

    def test_non_string_source_never_real(self):
        for src in MALFORMED_SOURCES:
            with self.subTest(src=src):
                self.assertFalse(is_real_market_data(src))

    def test_string_lookalikes_not_trusted(self):
        # Near-misses must not be trusted (only exact "yfinance"/"explicit").
        for src in ("YFINANCE", " yfinance", "yfinance_error", "Explicit", "synthetic_fallback"):
            with self.subTest(src=src):
                self.assertFalse(is_trusted_input_source(src))

    def test_exact_trusted_sources_still_trusted(self):
        self.assertTrue(is_trusted_input_source("yfinance"))
        self.assertTrue(is_trusted_input_source("explicit"))
        self.assertTrue(is_real_market_data("yfinance"))


class BuildDecisionMalformedSourceTests(unittest.TestCase):
    """_build_decision_from_inputs must fail closed to UNKNOWN for an untrusted
    or malformed (non-string) source — building a valid decision, never raising,
    and writing nothing."""

    def test_non_string_source_fails_closed_to_unknown(self):
        for src in MALFORMED_SOURCES:
            with self.subTest(src=src):
                decision = regime_cycle._build_decision_from_inputs(DRY_RUN_INPUTS, src)
                decision.validate()  # must not raise
                self.assertEqual(decision.market_regime, "UNKNOWN")
                self.assertEqual(decision.confidence, 0)
                self.assertEqual(decision.risk_level, "UNKNOWN")
                self.assertFalse(decision.data_is_real)

    def test_untrusted_string_source_fails_closed(self):
        decision = regime_cycle._build_decision_from_inputs(DRY_RUN_INPUTS, "synthetic_fallback")
        self.assertEqual(decision.market_regime, "UNKNOWN")
        self.assertFalse(decision.data_is_real)

    def test_explicit_source_is_classified_not_unknown(self):
        # The trusted "explicit" source IS classified (DRY_RUN_INPUTS -> a real
        # regime), confirming the guard only blocks untrusted/malformed sources.
        decision = regime_cycle._build_decision_from_inputs(DRY_RUN_INPUTS, "explicit")
        decision.validate()
        self.assertNotEqual(decision.market_regime, "UNKNOWN")
        self.assertFalse(decision.data_is_real)  # explicit is trusted but not "real"


if __name__ == "__main__":
    unittest.main()
