import contextlib
import io
import json
import unittest

from tools import regime_autocycle


class RegimeCliTests(unittest.TestCase):
    def test_cli_once_works(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = regime_autocycle.main(["--once"])
        payload = json.loads(output.getvalue())
        from core.regime_contracts import VALID_REGIMES
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_REGIME")
        self.assertTrue(payload["dry_run"])
        # Phase 3: live or synthetic inputs — contract guarantees a valid regime
        self.assertIn(payload["regime"], VALID_REGIMES)
        self.assertGreaterEqual(payload["confidence"], 0)
        self.assertLessEqual(payload["confidence"], 100)


if __name__ == "__main__":
    unittest.main()

