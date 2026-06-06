"""Tests for workflow/regime_cycle.py — Phase 2 snapshot and safety."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from core.regime_classifier import RegimeInput
from workflow import regime_cycle


class SnapshotGenerationTests(unittest.TestCase):
    def test_dry_run_writes_only_own_snapshot(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        result_path = Path(result["result_snapshot_path"]).resolve()
        self.assertEqual(result_path, regime_cycle.RESULT_SNAPSHOT_PATH.resolve())

    def test_snapshot_contains_required_fields(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        for field in ("project", "status", "market_regime", "confidence", "risk_level", "reason", "dry_run"):
            with self.subTest(field=field):
                self.assertIn(field, payload)

    def test_snapshot_project_is_market_regime_bot(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["project"], "MarketRegimeBot")

    def test_snapshot_status_safe_dry_run(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_REGIME")

    def test_snapshot_dry_run_true(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertTrue(payload["dry_run"])

    def test_snapshot_reason_is_list(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        payload = json.loads(
            Path(result["result_snapshot_path"]).read_text(encoding="utf-8")
        )
        self.assertIsInstance(payload["reason"], list)

    def test_default_synthetic_inputs_produce_bull(self):
        # DRY_RUN_INPUTS = trend=0.8, vol=0.2 → BULL
        result = regime_cycle.run_regime_cycle(write_snapshot=False)
        self.assertEqual(result["regime"], "BULL")
        self.assertEqual(result["confidence"], 80)

    def test_custom_bear_inputs(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=-0.8, volatility_score=0.3),
        )
        self.assertEqual(result["regime"], "BEAR")

    def test_custom_sideways_inputs(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=0.1, volatility_score=0.2),
        )
        self.assertEqual(result["regime"], "SIDEWAYS")

    def test_custom_high_volatility_inputs(self):
        result = regime_cycle.run_regime_cycle(
            write_snapshot=False,
            inputs=RegimeInput(trend_score=0.0, volatility_score=0.9),
        )
        self.assertEqual(result["regime"], "HIGH_VOLATILITY")


class DryRunSafetyTests(unittest.TestCase):
    def test_write_result_refuses_outside_project(self):
        from core.regime_contracts import build_unknown_regime_decision
        decision = build_unknown_regime_decision()
        outside_path = Path(tempfile.gettempdir()) / "market_regime_outside.json"
        with self.assertRaises(ValueError):
            regime_cycle.write_result_snapshot(decision, outside_path)

    def test_no_broker_order_trading_modules_imported(self):
        regime_cycle.run_regime_cycle(write_snapshot=False)
        forbidden = ("broker", "order", "trading")
        bad = [
            name for name in sys.modules
            if any(f in name.lower() for f in forbidden)
            and not name.startswith(("unittest", "test"))
            and "regime" not in name.lower()
        ]
        self.assertEqual(bad, [])

    def test_result_always_dry_run_true(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=False)
        self.assertTrue(result["dry_run"])

    def test_confidence_in_bounds(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=False)
        self.assertGreaterEqual(result["confidence"], 0)
        self.assertLessEqual(result["confidence"], 100)


if __name__ == "__main__":
    unittest.main()
