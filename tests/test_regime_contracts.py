import unittest

from core.regime_contracts import RegimeValidationError, build_unknown_regime_decision


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


if __name__ == "__main__":
    unittest.main()

