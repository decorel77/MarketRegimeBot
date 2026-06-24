import unittest

from core.regime_contracts import (
    RegimeSafetyState,
    RegimeValidationError,
    RegimeDecision,
    build_unknown_regime_decision,
)


class RegimeContractsTests(unittest.TestCase):
    def test_default_regime_unknown(self):
        decision = build_unknown_regime_decision()
        self.assertEqual(decision.market_regime, "UNKNOWN")
        self.assertEqual(decision.risk_level, "UNKNOWN")

    def test_confidence_between_0_and_100(self):
        decision = build_unknown_regime_decision()
        self.assertGreaterEqual(decision.confidence, 0)
        self.assertLessEqual(decision.confidence, 100)

    def test_safety_flags_disabled(self):
        payload = build_unknown_regime_decision().to_dict()
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["broker_execution_enabled"])
        self.assertFalse(payload["order_placement_enabled"])
        self.assertFalse(payload["live_trading_enabled"])
        self.assertFalse(payload["money_movement_enabled"])
        self.assertFalse(payload["writes_to_other_projects_enabled"])
        self.assertFalse(payload["allocation_export_enabled"])

    def test_invalid_confidence_rejected(self):
        decision = build_unknown_regime_decision()
        unsafe = decision.__class__(
            project=decision.project,
            status=decision.status,
            market_regime=decision.market_regime,
            confidence=101,
            risk_level=decision.risk_level,
            safety=decision.safety,
        )
        with self.assertRaises(RegimeValidationError):
            unsafe.validate()


class RegimeConfidenceTypeTests(unittest.TestCase):
    """A malformed confidence *type* must raise RegimeValidationError, never an
    opaque TypeError, and bool True must not be accepted as confidence 1."""

    def _decision(self, confidence):
        return RegimeDecision(
            project="MarketRegimeBot",
            status="SAFE_DRY_RUN_REGIME",
            market_regime="BULL",
            confidence=confidence,
            risk_level="NORMAL",
            safety=RegimeSafetyState(),
        )

    def test_bool_confidence_rejected(self):
        # True is an int subclass — must not slip through as confidence 1.
        for bad in (True, False):
            with self.assertRaises(RegimeValidationError):
                self._decision(bad).validate()

    def test_non_numeric_confidence_raises_contract_error(self):
        for bad in ("50", None, [50], {"c": 50}):
            with self.assertRaises(RegimeValidationError):
                self._decision(bad).validate()

    def test_non_finite_confidence_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(RegimeValidationError):
                self._decision(bad).validate()

    def test_well_formed_int_and_float_confidence_accepted(self):
        for ok in (0, 50, 100, 50.0):
            self._decision(ok).validate()  # must not raise


if __name__ == "__main__":
    unittest.main()

