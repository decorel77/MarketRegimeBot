import json
import sys
import tempfile
import unittest
from pathlib import Path

from workflow import regime_cycle


class RegimeCycleTests(unittest.TestCase):
    def test_dry_run_writes_only_own_snapshot(self):
        result = regime_cycle.run_regime_cycle(write_snapshot=True)
        result_path = Path(result["result_snapshot_path"]).resolve()
        self.assertEqual(result_path, regime_cycle.RESULT_SNAPSHOT_PATH.resolve())
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["project"], "MarketRegimeBot")
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_REGIME")
        self.assertEqual(payload["market_regime"], "UNKNOWN")
        self.assertEqual(payload["confidence"], 0)

    def test_write_result_refuses_outside_project(self):
        decision = regime_cycle.build_unknown_regime_decision()
        outside_path = Path(tempfile.gettempdir()) / "market_regime_outside.json"
        with self.assertRaises(ValueError):
            regime_cycle.write_result_snapshot(decision, outside_path)

    def test_no_broker_order_trading_modules_are_imported(self):
        regime_cycle.run_regime_cycle(write_snapshot=False)
        forbidden_fragments = ("broker", "order", "trading")
        imported = [
            name
            for name in sys.modules
            if any(fragment in name.lower() for fragment in forbidden_fragments)
        ]
        imported = [
            name
            for name in imported
            if not name.startswith("unittest")
            and not name.startswith("test")
            and "regime" not in name.lower()
        ]
        self.assertEqual(imported, [])


if __name__ == "__main__":
    unittest.main()

