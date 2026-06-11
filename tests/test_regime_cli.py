import contextlib
import io
import json
import unittest
from unittest import mock

from core.regime_classifier import DRY_RUN_INPUTS
from tools import regime_autocycle


class RegimeCliTests(unittest.TestCase):
    def test_cli_once_works(self):
        # Hermetic (QA-003): stub out yfinance and the sibling-snapshot
        # adapter so the CLI test makes no network calls and reads no state
        # from other repos. Artifact writes land in the conftest sandbox.
        output = io.StringIO()
        with mock.patch(
            "core.market_data_reader.read_market_regime_inputs",
            return_value=(DRY_RUN_INPUTS, "yfinance_error"),
        ), mock.patch(
            "workflow.regime_cycle.load_regime_input_from_snapshots",
            return_value=(DRY_RUN_INPUTS, "synthetic_fallback"),
        ):
            with contextlib.redirect_stdout(output):
                exit_code = regime_autocycle.main(["--once"])
        payload = json.loads(output.getvalue())
        from core.regime_contracts import VALID_REGIMES
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_REGIME")
        self.assertTrue(payload["dry_run"])
        # Contract guarantees a valid regime; fallback inputs fail closed
        # to UNKNOWN per QA-002.
        self.assertIn(payload["regime"], VALID_REGIMES)
        self.assertEqual(payload["regime"], "UNKNOWN")
        self.assertGreaterEqual(payload["confidence"], 0)
        self.assertLessEqual(payload["confidence"], 100)


if __name__ == "__main__":
    unittest.main()
