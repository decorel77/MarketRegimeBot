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
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_REGIME")
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["regime"], "UNKNOWN")
        self.assertEqual(payload["confidence"], 0)


if __name__ == "__main__":
    unittest.main()

